from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import asyncio
import sys
import os
import re
import uuid
from pathlib import Path
from io import StringIO
import httpx

from orchestrator.dispatcher import run_agent
from orchestrator.agent import (
    MARKER_REASONING_START,
    MARKER_REASONING_END,
    MARKER_TOOL_START,
    MARKER_TOOL_END,
    MARKER_FINAL_START,
    MARKER_FINAL_END,
)

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

# Triggering hot-reload to apply HNSW dummy query self-healing fixes
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    import logging
    logger = logging.getLogger("orchestrator")
    logger.info("FastAPI startup: Bootstrapping Ollama models...")
    
    models_to_pull = ["mxbai-embed-large", "qwen2.5:1.5b"]
    for model in models_to_pull:
        try:
            logger.info(f"Ensuring Ollama model '{model}' is pulled...")
            async with httpx.AsyncClient(timeout=600.0) as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL()}/api/pull",
                    json={"name": model, "stream": False}
                )
                resp.raise_for_status()
            logger.info(f"Model '{model}' is ready.")
        except Exception as e:
            logger.error(f"Failed to ensure model '{model}': {e}")

@app.get("/health")
async def health():
    """Health check endpoint with Ollama model list."""
    ollama_models = []
    ollama_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL()}/api/tags")
            if resp.status_code == 200:
                ollama_status = "ok"
                models_data = resp.json().get("models", [])
                ollama_models = [m.get("name") for m in models_data]
            else:
                ollama_status = f"error: {resp.status_code}"
    except Exception as e:
        ollama_status = f"failed: {str(e)}"

    return {
        "status": "ok",
        "version": "1.0",
        "ollama_status": ollama_status,
        "ollama_models": ollama_models
    }

from typing import Optional

DEFAULT_TIMEOUT = 1000
from common.ollama_helper import get_working_ollama_base_url

def OLLAMA_BASE_URL() -> str:
    return get_working_ollama_base_url()

TITLE_MODEL = "qwen2.5:1.5b"

class QueryRequest(BaseModel):
    query: Optional[str] = None
    question: Optional[str] = None
    message: Optional[str] = None
    content: Optional[str] = None
    text: Optional[str] = None
    session_id: Optional[str] = None
    timeout: Optional[int] = DEFAULT_TIMEOUT

    def normalized_query(self) -> str:
        for value in (self.query, self.question, self.message, self.content, self.text):
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

class TitleGenerationRequest(BaseModel):
    messages: list  # [{"role": "...", "content": "..."}]
    last_title_message_count: int = 0
    force: bool = False
    timeout: Optional[int] = DEFAULT_TIMEOUT


def frappe_headers_from_request(request: Request) -> dict:
    forwarded = {}
    for name in ("authorization", "cookie", "x-frappe-csrf-token"):
        value = request.headers.get(name)
        if value:
            forwarded[name] = value
    return forwarded



# ---------------- NORMAL QUERY ----------------

@app.post("/v1/query")
async def query_api(req: QueryRequest, request: Request):
    question = req.normalized_query()
    if not question:
        raise HTTPException(status_code=400, detail="`query` must be a non-empty string.")

    result = await run_agent(question, frappe_headers_from_request(request), req.session_id)
    return {"response": result}


# ---------------- TITLE GENERATION ----------------

@app.post("/v1/generate-title")
async def generate_title_endpoint(req: TitleGenerationRequest):
    """
    Title generation with strict 5-message batching logic.
    """

    messages = req.messages or []
    total_messages = len(messages)
    last_title_count = req.last_title_message_count or 0
    force = req.force

    if total_messages == 0:
        return {
            "success": True,
            "title": "New Chat",
            "message_count": 0
        }

    # -------------------------------
    # BATCHING LOGIC (Exact Logic)
    # -------------------------------

    current_completed_batch = total_messages // 5
    last_completed_batch = last_title_count // 5 if last_title_count > 0 else 0

    if last_title_count == 0 and total_messages >= 1:
        should_generate = True
    elif current_completed_batch > last_completed_batch:
        should_generate = True
    else:
        should_generate = False

    if not should_generate and not force:
        return {
            "success": True,
            "skipped": True,
            "message_count": total_messages,
            "next_update_at": (current_completed_batch + 1) * 5
        }

    # -------------------------------
    # DETERMINE MESSAGE RANGE
    # -------------------------------

    if last_title_count == 0:
        start_idx = 0
        end_idx = total_messages
    else:
        batch_to_use = current_completed_batch
        start_idx = (batch_to_use - 1) * 5
        end_idx = min(start_idx + 5, total_messages)

    batch_messages = messages[start_idx:end_idx]

    # -------------------------------
    # GREETING FILTER
    # -------------------------------

    simple_greetings = {"hi", "hello", "hey", "hii", "hola", "hiya", "yo", "sup", "greetings"}

    meaningful_messages = []
    for msg in batch_messages:
        content = (msg.get("content") or "").strip().lower()
        content_clean = content.rstrip("!?.,'\"\\r\\n")
        if content_clean not in simple_greetings:
            meaningful_messages.append(msg)

    if not meaningful_messages:
        meaningful_messages = batch_messages

    # -------------------------------
    # BUILD PROMPT
    # -------------------------------

    messages_text = []
    for msg in meaningful_messages:
        role = msg.get("role", "User")
        content = msg.get("content", "")[:200]
        messages_text.append(f"{role}: {content}")

    conversation_summary = "\n".join(messages_text)

    from prompts.registry import TITLE_GENERATION_PROMPT
    prompt = TITLE_GENERATION_PROMPT.format(conversation_summary=conversation_summary)

    try:
        async with httpx.AsyncClient(timeout=req.timeout or DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL()}/api/chat",
                json={
                    "model": TITLE_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
            )
            resp.raise_for_status()
            data = resp.json()

        raw_title = (data.get("message", {}).get("content", "") or "").strip()

        # Clean title of any markdown formatting (headers, bold, etc.) and emojis
        cleaned_title = raw_title.strip()
        cleaned_title = re.sub(r'^#+\s*', '', cleaned_title)
        cleaned_title = cleaned_title.replace("**", "").replace("*", "").replace("__", "").replace("_", "").replace("`", "")
        # Strip unicode emojis
        cleaned_title = re.sub(r'[\U00010000-\U0010ffff]', '', cleaned_title)
        cleaned_title = re.sub(r'[\u2600-\u27BF]', '', cleaned_title)
        cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
        # Strip leading/trailing colons/hyphens/spaces
        cleaned_title = re.sub(r'^[:\-\s]+', '', cleaned_title).strip()
        cleaned_title = re.sub(r'[:\-\s]+$', '', cleaned_title).strip()

        title = cleaned_title

        if len(title) > 60:
            title = title[:57] + "..."
        elif len(title) < 3:
            title = "New Chat"

        return {
            "success": True,
            "title": title,
            "message_count": total_messages,
            "last_title_message_count": total_messages,
            "batch_used": f"{start_idx + 1}-{end_idx}"
        }

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Title generation timeout")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- STREAMING HELPERS ----------------

def clean_line(line: str) -> str:
    line = re.sub(r'^\s*event:\s*', '', line)
    return line.replace("\x00", "").replace("\r", "")


def sse_event(data: str, event_type: str | None = None) -> str:
    safe = data.replace("\x00", "").replace("\r", "")
    if event_type:
        return f"event: {event_type}\ndata: {safe}\n\n"
    return f"data: {safe}\n\n"


# ---------------- STREAMING ENDPOINT ----------------

@app.post("/v1/stream")
async def stream_query(request: Request):

    body = await request.json()
    question = (
        body.get("query")
        or body.get("question")
        or body.get("message")
        or body.get("content")
        or body.get("text")
        or ""
    )
    if isinstance(question, str):
        question = question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    async def event_generator():

        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output

        last_pos = 0
        current_section = None

        try:
            session_id = body.get("session_id")
            task = asyncio.create_task(run_agent(question, frappe_headers_from_request(request), session_id))

            # Compile regex for markers
            markers = [
                MARKER_REASONING_START, MARKER_REASONING_END,
                MARKER_TOOL_START, MARKER_TOOL_END,
                MARKER_FINAL_START, MARKER_FINAL_END
            ]
            pattern = "|".join(map(re.escape, markers))
            
            # Use capturing group to keep the delimiters (markers) in the result
            split_regex = re.compile(f"({pattern})")

            while not task.done():
                await asyncio.sleep(0.05)

                captured_output.seek(0)
                text = captured_output.read()

                if len(text) > last_pos:
                    new_text = text[last_pos:]
                    last_pos = len(text)

                    # Split by markers, keeping markers in the list
                    parts = split_regex.split(new_text)

                    for part in parts:
                        if not part:
                            continue
                        
                        # Check if part is a marker
                        if part == MARKER_REASONING_START:
                            yield sse_event("", "reasoning_start")
                            current_section = "reasoning"
                        elif part == MARKER_REASONING_END:
                            yield sse_event("", "reasoning_end")
                            current_section = None
                        elif part == MARKER_TOOL_START:
                            yield sse_event("", "tool_start")
                            current_section = "tool"
                        elif part == MARKER_TOOL_END:
                            yield sse_event("", "tool_end")
                            current_section = None
                        elif part == MARKER_FINAL_START:
                            yield sse_event("", "final_start")
                            current_section = "final"
                        elif part == MARKER_FINAL_END:
                            yield sse_event("", "final_end")
                            current_section = None
                        else:
                            # It's content
                            # Split by newlines to be safe with SSE (though sse_event handles newlines by replacing them technically, 
                            # usually it's cleaner to send separate data chunks if they are distinct lines)
                            # However, for pure streaming text, we might want to preserve the flow.
                            # But clean_line() strips stuff.
                            # Let's try to preserve the content as much as possible but respect SSE structure.
                            
                            # If we use clean_line on the whole part, we might lose internal newlines that are important.
                            # Let's split by lines for safer SSE emission.
                            
                            lines = part.split('\n')
                            for line in lines:
                                cleaned = clean_line(line)
                                if cleaned:
                                    yield sse_event(cleaned, current_section or "output")
            
            await task

            captured_output.seek(0)
            remaining_text = captured_output.read()
            if len(remaining_text) > last_pos:
                new_text = remaining_text[last_pos:]
                last_pos = len(remaining_text)

                parts = split_regex.split(new_text)

                for part in parts:
                    if not part:
                        continue

                    if part == MARKER_REASONING_START:
                        yield sse_event("", "reasoning_start")
                        current_section = "reasoning"
                    elif part == MARKER_REASONING_END:
                        yield sse_event("", "reasoning_end")
                        current_section = None
                    elif part == MARKER_TOOL_START:
                        yield sse_event("", "tool_start")
                        current_section = "tool"
                    elif part == MARKER_TOOL_END:
                        yield sse_event("", "tool_end")
                        current_section = None
                    elif part == MARKER_FINAL_START:
                        yield sse_event("", "final_start")
                        current_section = "final"
                    elif part == MARKER_FINAL_END:
                        yield sse_event("", "final_end")
                        current_section = None
                    else:
                        for line in part.split('\n'):
                            cleaned = clean_line(line)
                            if cleaned:
                                yield sse_event(cleaned, current_section or "output")

            yield sse_event("[DONE]", "done")

        except Exception as e:
            yield sse_event(f"Error: {str(e)}", "error")

        finally:
            sys.stdout = old_stdout

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@app.get("/v1/tools")
def tools_list():
    """List available tools."""
    from orchestrator.tool_dispatcher import TOOL_ENDPOINTS
    from orchestrator.mcp_registry import MCP_REGISTRY
    tools = [
        {"name": name, "description": f"Endpoint: {url}"}
        for name, url in TOOL_ENDPOINTS.items()
    ]
    tools.extend(
        {
            "name": tool.name,
            "description": tool.description,
            "method": tool.method,
            "http_method": tool.http_method,
        }
        for tool in MCP_REGISTRY.values()
    )
    return {"tools": tools}


@app.post("/v1/upload")
async def upload_file(file: UploadFile = File(...)):
    """File upload endpoint."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    upload_id = str(uuid.uuid4())
    dest_dir = UPLOADS_DIR / upload_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / Path(file.filename).name

    try:
        contents = await file.read()
        with dest_path.open("wb") as f:
            f.write(contents)

        return {
            "upload_id": upload_id,
            "filepath": str(dest_path.resolve())
        }
    except Exception as e:
        raise HTTPException(status_code=505, detail=f"Failed to save file: {e}")
