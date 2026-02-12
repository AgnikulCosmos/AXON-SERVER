from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import asyncio
import sys
import re
from io import StringIO

from orchestrator.dispatcher import run_agent
from orchestrator.agent import (
    MARKER_REASONING_START,
    MARKER_REASONING_END,
    MARKER_TOOL_START,
    MARKER_TOOL_END,
    MARKER_FINAL_START,
    MARKER_FINAL_END,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str


# ---------------- NORMAL QUERY ----------------

@app.post("/v1/query")
async def query_api(req: QueryRequest):
    result = await run_agent(req.query)
    return {"response": result}


# ---------------- STREAMING HELPERS ----------------

def clean_line(line: str) -> str:
    line = re.sub(r'^\s*event:\s*', '', line)
    return line.replace("\x00", "").replace("\r", "").strip()


def sse_event(data: str, event_type: str | None = None) -> str:
    safe = data.replace("\x00", "").replace("\r", "")
    if event_type:
        return f"event: {event_type}\ndata: {safe}\n\n"
    return f"data: {safe}\n\n"


# ---------------- STREAMING ENDPOINT ----------------

@app.post("/v1/stream")
async def stream_query(request: Request):

    body = await request.json()
    question = body.get("query", "")

    if not question:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    async def event_generator():

        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output

        last_pos = 0
        current_section = None

        try:
            task = asyncio.create_task(run_agent(question))

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

            yield sse_event("[DONE]", "done")

        except Exception as e:
            yield sse_event(f"Error: {str(e)}", "error")

        finally:
            sys.stdout = old_stdout

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
