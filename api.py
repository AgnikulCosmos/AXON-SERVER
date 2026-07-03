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

from common.llm.ollama_helper import get_working_ollama_base_url

def get_ollama_url() -> str:
    return get_working_ollama_base_url()

TITLE_MODEL = os.getenv("LLM_MODEL", "qwen3.5:0.8b")


async def _wait_for_ollama(retries: int = 12, delay: float = 5.0) -> bool:
    for attempt in range(1, retries + 1):
        try:
            async with ollama.AsyncClient(host=get_ollama_url()) as client:
                await client.list()
            return True
        except Exception as e:
            logger.warning(f"Ollama not ready (attempt {attempt}/{retries}) - error: {e}")
        await asyncio.sleep(delay)
    return False


async def _pull_model(model: str, retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Pulling model '{model}' (attempt {attempt}/{retries})...")
            async with ollama.AsyncClient(host=get_ollama_url()) as client:
                await client.pull(model)
            return True
        except Exception as e:
            logger.error(f"Failed to pull model '{model}': {e}")
            if attempt < retries:
                await asyncio.sleep(3.0)
    return False


async def _verify_model(model: str) -> bool:
    try:
        async with ollama.AsyncClient(host=get_ollama_url()) as client:
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
        os.getenv("LLM_MODEL", "qwen3.5:0.8b"),
    ]
    for model in models_to_pull:
        if await _verify_model(model):
            logger.info(f"Model '{model}' already available")
            continue

        if await _pull_model(model):
            logger.info(f"Model '{model}' is ready.")
        else:
            logger.error(f"Model '{model}' could not be pulled after retries")

    try:
        logger.info("Pre-building semantic router embeddings...")
        from common.routing.router import _get_intent_router
        loop = asyncio.get_running_loop()
        router = await loop.run_in_executor(None, _get_intent_router)
        await loop.run_in_executor(None, router._get_semantic)
        logger.info("Semantic router embeddings are pre-built and ready.")
    except Exception as e:
        logger.error(f"Failed to pre-build semantic router embeddings: {e}")



@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_ensure_ollama_models())
    yield


from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Agnikul Agent API", version="1.0", lifespan=lifespan)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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
    session_id: Optional[str] = None

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

_title_locks = {}

async def _call_ollama(prompt: str, max_tokens: int = 30) -> str:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{get_ollama_url()}/api/generate",
                json={
                    "model": TITLE_MODEL,
                    "prompt": prompt,
                    "template": "{{ .Prompt }}",
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": max_tokens},
                },
            )
            resp.raise_for_status()
            data = resp.json()
        response_text = data.get("response", "") or ""
        thinking_text = data.get("thinking", "") or ""
        
        raw_val = ""
        if thinking_text:
            if "<think>" in thinking_text:
                raw_val = thinking_text.split("<think>")[0].strip()
            else:
                raw_val = thinking_text.strip()
        
        if not raw_val:
            raw_val = response_text.strip()

        # Clean <think>...</think> block
        import re as _re
        raw_val = _re.sub(r'<think>.*?</think>', '', raw_val, flags=_re.DOTALL).strip()
        raw_val = _re.sub(r'<think>.*$', '', raw_val, flags=_re.DOTALL).strip()
        
        # Take the first line that is NOT a thinking indicator
        first_line = ""
        for line in raw_val.splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip lines that are just thinking headers/indicators
            lower_line = line.lower().rstrip(":")
            if lower_line in (
                "thinking", "thought", "reasoning", "thinking process", 
                "thought process", "response", "answer", "title", "summary"
            ):
                continue
            if lower_line.startswith(("thinking process", "thought process", "thinking:", "thought:", "reasoning:")):
                continue
            first_line = line
            break
            
        if not first_line:
            # Fallback: if all lines were skipped, take the first non-empty one anyway
            for line in raw_val.splitlines():
                line = line.strip()
                if line:
                    first_line = line
                    break
                    
        raw_val = first_line or raw_val

        # Strip model special tokens that leak into output
        raw_val = _re.sub(r'<\|[^|>]+\|>', '', raw_val)
        raw_val = _re.sub(r'<\[[^\]]+\]>', '', raw_val)
        raw_val = _re.sub(r'</?think>', '', raw_val)
        raw_val = _re.sub(r'\s+', ' ', raw_val).strip()

        return raw_val
    except Exception as e:
        logger.warning(f"Failed to generate output with LLM: {e}")
        return ""


@app.post("/v1/generate-title")
async def generate_title_endpoint(req: TitleGenerationRequest):
    """
    Title generation with strict 5-message batching logic and session-based serialization queue.
    """
    session_id = req.session_id or "default"
    if session_id not in _title_locks:
        _title_locks[session_id] = asyncio.Lock()

    async with _title_locks[session_id]:
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
        # BATCHING LOGIC (Enhanced for early turns)
        # Wait for at least 2 messages (one user + one assistant) before first title
        # so we have a complete exchange to name the conversation from.
        # -------------------------------
        current_completed_batch = total_messages // 5
        last_completed_batch = last_title_count // 5 if last_title_count > 0 else 0

        if last_title_count == 0 and total_messages >= 2:
            # First title: require at least one complete exchange (user + assistant)
            should_generate = True
        elif last_title_count > 0 and total_messages <= 6 and total_messages > last_title_count:
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
            end_idx = total_messages
        else:
            batch_to_use = current_completed_batch
            end_idx = min((batch_to_use) * 5, total_messages)

        context_messages = messages[:end_idx]

        # -------------------------------
        # GREETING FILTER
        # -------------------------------
        meaningful_messages = []
        for msg in context_messages:
            content = (msg.get("content") or "").strip().lower()
            content_clean = content.rstrip("!?.,'\"\r\n")
            if content_clean not in SIMPLE_GREETINGS:
                meaningful_messages.append(msg)

        if not meaningful_messages:
            meaningful_messages = context_messages

        # -------------------------------
        # BUILD CONVERSATION TEXT
        # -------------------------------
        messages_text = []
        for msg in meaningful_messages:
            role = msg.get("role", "User")
            content = msg.get("content", "")[:200]
            messages_text.append(f"{role}: {content}")

        conversation_text = "\n".join(messages_text)

        def get_fallback_title() -> str:
            import re as _re
            _greetings = {
                "hi", "hello", "hey", "good morning", "good afternoon",
                "good evening", "howdy", "yo", "sup", "greetings", "hiya"
            }
            user_msg = ""
            for msg in reversed(messages):
                if msg.get("role", "").lower() != "user":
                    continue
                candidate = msg.get("content", "").strip()
                if candidate.lower().rstrip("!?.,\'\"") not in _greetings and len(candidate) > 3:
                    user_msg = candidate
                    break
            if not user_msg:
                return "New Chat"

            if user_msg.startswith(("/", "I want to ", "submit a ", "Raise a ")):
                clean_msg = _re.sub(r"^/[a-zA-Z0-9]+\s+", "", user_msg)
                clean_msg = _re.sub(r"^(I want to|submit a|Raise a|report a)\s+", "", clean_msg, flags=_re.IGNORECASE)
            else:
                clean_msg = user_msg

            words = clean_msg.split()
            fallback = " ".join(words[:6]) if len(words) > 6 else " ".join(words)
            fallback = fallback.strip("\"'.,!?;: ")
            fallback = _re.sub(r'[*#_`~]', '', fallback).strip()
            if fallback:
                fallback = fallback[0].upper() + fallback[1:]
            return fallback or "New Chat"

        try:
            from prompts.agent import CONVERSATION_SUMMARIZATION_PROMPT, TITLE_FROM_SUMMARY_PROMPT
            
            # Step 1: Summarize context
            sum_prompt = CONVERSATION_SUMMARIZATION_PROMPT.format(conversation=conversation_text)
            summary = await _call_ollama(sum_prompt, max_tokens=150)
            if not summary:
                summary = conversation_text[:300]

            # Step 2: Generate title from summary
            title_prompt = TITLE_FROM_SUMMARY_PROMPT.format(summary=summary)
            title = await _call_ollama(title_prompt, max_tokens=40)
            
            # Remove *, # like markdown styling
            import re as _re
            title = _re.sub(r'[*#_`~]', '', title).strip()
            title = title.strip("\"'").strip()

            # Trim to a sane length: max 70 chars (allows 4-7 word titles comfortably)
            if len(title) > 70:
                title = title[:67] + "..."
            elif len(title) < 4:
                title = get_fallback_title()

            return {
                "success": True,
                "title": title,
                "message_count": total_messages,
                "last_title_message_count": total_messages,
                "batch_used": f"1-{end_idx}"
            }

        except Exception as e:
            logger.warning(f"Failed to generate title with LLM ({e}). Falling back to heuristic.")
            fallback_title = get_fallback_title()
            return {
                "success": True,
                "title": fallback_title,
                "message_count": total_messages,
                "last_title_message_count": total_messages,
                "batch_used": "fallback"
            }

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

            last_ping_time = asyncio.get_event_loop().time()
            # While the agent is running, repeatedly check for new output and yield it
            while not task.done():
                await asyncio.sleep(0.08)  # poll interval; adjust for desired responsiveness
                captured_output.seek(0)
                text = captured_output.read()
                
                has_output = False
                if len(text) > last_pos:
                    has_output = True
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

                # Send keep-alive ping comment if idle for > 1.0 second
                current_time = asyncio.get_event_loop().time()
                if has_output:
                    last_ping_time = current_time
                elif current_time - last_ping_time > 1.0:
                    yield ": ping\n\n"
                    last_ping_time = current_time

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
            resp = await client.get(f"{get_ollama_url()}/api/tags")
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

        filename = Path(file.filename).name
        return {
            "upload_id": upload_id,
            "filepath": f"/api/method/axon.api.get_uploaded_file?upload_id={upload_id}&filename={filename}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")


@app.get("/v1/session_status/{session_id}")
async def get_session_status(session_id: str):
    from orchestrator.dispatcher import PENDING_ERP_SESSIONS
    pending = PENDING_ERP_SESSIONS.get(session_id)
    pending_route = pending.get("route_name") if pending else None
    missing_fields = pending.get("_missing_fields") if pending else []
    upload_enabled = bool(pending_route == "erp_tickets_create")
    return {
        "session_id": session_id,
        "pending_route": pending_route,
        "missing_fields": missing_fields or [],
        "upload_enabled": upload_enabled,
        "upload_field": "attachments" if upload_enabled else None,
    }


# Trigger reload config: switch to qwen2.5:0.5b

@app.get("/v1/admin/dataset")
async def get_dataset():
    dataset_path = Path("dataset.json")
    if not dataset_path.exists():
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})
    import json
    return JSONResponse(status_code=200, content=json.loads(dataset_path.read_text()))

from fastapi import BackgroundTasks

def build_db_in_background():
    import subprocess
    try:
        subprocess.run(["python", "build_vector.py"], check=True)
    except Exception as e:
        logger.error(f"Failed to rebuild vector db: {e}")

@app.post("/v1/admin/dataset/update")
async def update_dataset(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    dataset_path = Path("dataset.json")
    import json
    dataset_path.write_text(json.dumps(data, indent=2))
    
    background_tasks.add_task(build_db_in_background)
    return {"success": True, "message": "Dataset updated, vector rebuild started."}
