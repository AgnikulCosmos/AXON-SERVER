import os
import uuid
import asyncio
from pathlib import Path
from typing import Optional
import re
import sys
from io import StringIO

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

#from agent import run_agent, MARKER_REASONING_START, MARKER_REASONING_END, MARKER_TOOL_START, MARKER_TOOL_END, MARKER_FINAL_START, MARKER_FINAL_END
from tools.registry import TOOLS

from dispatcher import run_agent
from agent import (
    MARKER_REASONING_START,
    MARKER_REASONING_END,
    MARKER_TOOL_START,
    MARKER_TOOL_END,
    MARKER_FINAL_START,
    MARKER_FINAL_END,
)

app = FastAPI(title="Agnikul Agent API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
DEFAULT_TIMEOUT = 1000


class QueryRequest(BaseModel):
    query: str
    timeout: Optional[int] = DEFAULT_TIMEOUT


def clean_line(line: str) -> str:
    """
    Minimal cleaning: remove only nulls / carriage returns and leading stray 'event:' prefixes.
    Keep '*' and other markdown characters intact.
    """
    # remove any leading "event:" literal that might be present (but don't remove '|')
    line = re.sub(r'^\s*event:\s*', '', line)
    return line.replace("\x00", "").replace("\r", "").strip()


def sse_event(data: str, event_type: Optional[str] = None) -> str:
    """Format SSE event."""
    safe = data.replace("\x00", "").replace("\r", "")
    if event_type:
        return f"event: {event_type}\ndata: {safe}\n\n"
    else:
        return f"data: {safe}\n\n"


@app.post("/v1/query")
async def query_endpoint(req: QueryRequest):
    """Non-streaming query endpoint."""
    if not req.query or not isinstance(req.query, str):
        raise HTTPException(status_code=400, detail="`query` must be a non-empty string.")

    request_id = str(uuid.uuid4())

    try:
        # Run agent with timeout
        result = await asyncio.wait_for(
            run_agent(req.query),
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


@app.post("/v1/stream")
async def stream_query(request: Request):
    """
    Streaming endpoint using async generator.
    Captures stdout from agent and converts to SSE events.
    """
    body = await request.json()
    question = body.get("query", "") or body.get("question", "") or ""

    if not question:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    async def event_generator():
        """Async generator for SSE events that streams as agent writes to stdout."""
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output

        last_pos = 0
        current_section = None

        try:
            # Start agent as a background task so we can poll its stdout
            task = asyncio.create_task(run_agent(question))

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
                        line_stripped = raw_line.strip()
                        if not line_stripped:
                            continue

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
                        cleaned = clean_line(line_stripped)
                        if cleaned:
                            yield sse_event(cleaned, event_type=current_section or "output")

            # Ensure any remaining output is processed after task completes
            await task  # propagate errors if any
            captured_output.seek(0)
            final_text = captured_output.read()
            if len(final_text) > last_pos:
                for raw_line in final_text[last_pos:].splitlines():
                    line_stripped = raw_line.strip()
                    if not line_stripped:
                        continue
                    cleaned = clean_line(line_stripped)
                    if cleaned:
                        # Try to detect markers one last time
                        if line_stripped == MARKER_FINAL_START:
                            yield sse_event("", event_type="final_start")
                            continue
                        if line_stripped == MARKER_FINAL_END:
                            yield sse_event("", event_type="final_end")
                            continue
                        yield sse_event(cleaned, event_type="final")

            yield sse_event("[DONE]", event_type="done")

        except Exception as e:
            yield sse_event(f"Error: {str(e)}", event_type="error")

        finally:
            sys.stdout = old_stdout

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@app.get("/v1/tools")
def tools_list():
    """List available tools."""
    tools = [
        {
            "name": t.name,
            "description": t.description if hasattr(t, "description") else ""
        }
        for t in TOOLS
    ]
    return {"tools": tools}


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0"}


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
