import common.config_loader
import common.streaming.sse

common.streaming.sse.install_stdout_proxy()
import os
import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import re
from io import StringIO
import httpx

import ollama

from common.streaming.sse import task_stdout, clean_line, sse_event, install_stdout_proxy
from common.constants import SIMPLE_GREETINGS

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator.dispatcher import run_agent
from orchestrator.agent import (
    MARKER_REASONING_START,
    MARKER_REASONING_END,
    MARKER_TOOL_START,
    MARKER_TOOL_END,
    MARKER_FINAL_START,
    MARKER_FINAL_END,
)

logger = logging.getLogger("api")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
TITLE_MODEL = os.getenv("LLM_MODEL", "qwen2.5:0.5b")


async def _wait_for_ollama(retries: int = 12, delay: float = 5.0) -> bool:
    for attempt in range(1, retries + 1):
        try:
            async with ollama.AsyncClient(host=OLLAMA_BASE_URL) as client:
                await client.list()
            return True
        except Exception:
            pass
        logger.warning(f"Ollama not ready (attempt {attempt}/{retries}), retrying in {delay}s...")
        await asyncio.sleep(delay)
    return False


async def _pull_model(model: str, retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Pulling model '{model}' (attempt {attempt}/{retries})...")
            async with ollama.AsyncClient(host=OLLAMA_BASE_URL) as client:
                await client.pull(model)
            return True
        except Exception as e:
            logger.error(f"Failed to pull model '{model}': {e}")
            if attempt < retries:
                await asyncio.sleep(3.0)
    return False


async def _verify_model(model: str) -> bool:
    try:
        async with ollama.AsyncClient(host=OLLAMA_BASE_URL) as client:
            await client.chat(model=model, messages=[{"role": "user", "content": "ping"}])
        return True
    except Exception:
        return False


async def _ensure_ollama_models():
    logger.info("Bootstrapping Ollama models...")
    if not await _wait_for_ollama():
        logger.error("Ollama did not become healthy — skipping model pull")
        return

    models_to_pull = [
        os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
        os.getenv("LLM_MODEL", "qwen2.5:0.5b"),
    ]
    for model in models_to_pull:
        if await _verify_model(model):
            logger.info(f"Model '{model}' already available")
            continue

        if await _pull_model(model):
            logger.info(f"Model '{model}' is ready.")
        else:
            logger.error(f"Model '{model}' could not be pulled after retries")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _ensure_ollama_models()
    yield


app = FastAPI(title="Agnikul Agent API", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
DEFAULT_TIMEOUT = 1000


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
    for name in (
        "authorization",
        "cookie",
        "host",
        "x-forwarded-host",
        "x-frappe-csrf-token",
        "x-frappe-site-name",
    ):
        value = request.headers.get(name)
        if value:
            forwarded[name] = value
    return forwarded

def extract_final_text(agent_output: str) -> str:
    """
    Extract only final answer content from agent output.
    Removes reasoning/tool markers if present.
    """
    if not agent_output:
        return ""

    # If markers exist, extract content between FINAL markers
    if MARKER_FINAL_START in agent_output and MARKER_FINAL_END in agent_output:
        try:
            return agent_output.split(MARKER_FINAL_START)[1].split(MARKER_FINAL_END)[0].strip()
        except Exception:
            pass

    return agent_output.strip()

@app.post("/v1/query")
async def query_endpoint(req: QueryRequest, request: Request):
    """Non-streaming query endpoint."""
    question = req.normalized_query()
    print(f"[API Log] Received session_id: {req.session_id}")
    if not question:
        raise HTTPException(status_code=400, detail="`query` must be a non-empty string.")

    request_id = str(uuid.uuid4())

    try:
        # Run agent with timeout
        result = await asyncio.wait_for(
            run_agent(question, frappe_headers_from_request(request), req.session_id),
            timeout=req.timeout or DEFAULT_TIMEOUT
        )

        return JSONResponse(
            status_code=200,
            content={
                "request_id": request_id,
                "status": "ok",
                "response": result
            }
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={
                "request_id": request_id,
                "status": "timeout",
                "error": f"Agent timed out after {req.timeout or DEFAULT_TIMEOUT} seconds"
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "request_id": request_id,
                "status": "error",
                "error": str(e)
            }
        )

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

    meaningful_messages = []
    for msg in batch_messages:
        content = (msg.get("content") or "").strip().lower()
        content_clean = content.rstrip("!?.,'\"\r\n")
        if content_clean not in SIMPLE_GREETINGS:
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

    from prompts.agent import TITLE_GENERATION_PROMPT
    prompt = TITLE_GENERATION_PROMPT.format(conversation_summary=conversation_summary)

    try:
        async with httpx.AsyncClient(timeout=req.timeout or DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
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

        title = raw_title.strip().strip("\"'").strip()

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

@app.post("/v1/stream")
async def stream_query(request: Request):
    """
    Streaming endpoint using async generator.
    Captures stdout from agent and converts to SSE events.
    """
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
        """Async generator for SSE events that streams as agent writes to stdout."""
        captured_output = StringIO()
        token = task_stdout.set(captured_output)

        last_pos = 0
        current_section = None

        try:
            # Start agent as a background task so we can poll its stdout
            session_id = body.get("session_id")
            task = asyncio.create_task(run_agent(question, frappe_headers_from_request(request), session_id))

            # While the agent is running, repeatedly check for new output and yield it
            while not task.done():
                await asyncio.sleep(0.08)  # poll interval; adjust for desired responsiveness
                captured_output.seek(0)
                text = captured_output.read()
                if len(text) > last_pos:
                    new_text = text[last_pos:]
                    last_pos = len(text)
                    # process new_text line-by-line
                    for raw_line in new_text.splitlines():
                        if not raw_line:
                            continue
                        line_stripped = raw_line.strip()

                        # Detect markers exactly (they are printed on their own lines)
                        if line_stripped == MARKER_REASONING_START:
                            yield sse_event("", event_type="reasoning_start")
                            current_section = "reasoning"
                            continue
                        elif line_stripped == MARKER_REASONING_END:
                            yield sse_event("", event_type="reasoning_end")
                            current_section = None
                            continue
                        elif line_stripped == MARKER_TOOL_START:
                            yield sse_event("", event_type="tool_start")
                            current_section = "tool"
                            continue
                        elif line_stripped == MARKER_TOOL_END:
                            yield sse_event("", event_type="tool_end")
                            current_section = None
                            continue
                        elif line_stripped == MARKER_FINAL_START:
                            yield sse_event("", event_type="final_start")
                            current_section = "final"
                            continue
                        elif line_stripped == MARKER_FINAL_END:
                            yield sse_event("", event_type="final_end")
                            current_section = None
                            continue

                        # Content lines: emit using current_section if set, otherwise default to "output"
                        cleaned = clean_line(raw_line)
                        if cleaned != "":
                            yield sse_event(cleaned, event_type=current_section or "output")

            # Ensure any remaining output is processed after task completes
            await task  # propagate errors if any
            captured_output.seek(0)
            final_text = captured_output.read()
            if len(final_text) > last_pos:
                for raw_line in final_text[last_pos:].splitlines():
                    if not raw_line:
                        continue
                    line_stripped = raw_line.strip()
                    # Try to detect markers one last time
                    if line_stripped == MARKER_FINAL_START:
                        yield sse_event("", event_type="final_start")
                        continue
                    if line_stripped == MARKER_FINAL_END:
                        yield sse_event("", event_type="final_end")
                        continue
                    cleaned = clean_line(raw_line)
                    if cleaned != "":
                        yield sse_event(cleaned, event_type="final")

            yield sse_event("[DONE]", event_type="done")

        except Exception as e:
            yield sse_event(f"Error: {str(e)}", event_type="error")

        finally:
            task_stdout.reset(token)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@app.get("/v1/tools")
def tools_list():
    """List available tools."""
    from services.tools.tool_dispatcher import TOOL_ENDPOINTS
    from services.erp.mcp_registry import MCP_REGISTRY
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


@app.get("/health")
async def health():
    """Health check endpoint with Ollama model list."""
    ollama_models = []
    ollama_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                ollama_status = "ok"
                # Map models to a simpler list of names for readability
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
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

# Trigger reload config: switch to qwen2.5:0.5b

