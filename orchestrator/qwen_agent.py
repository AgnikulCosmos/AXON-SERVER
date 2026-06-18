from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from orchestrator.agent import (
    MARKER_FINAL_START,
    MARKER_FINAL_END,
    stream_text_word_by_word
)

import os
import sys
import re
import asyncio

from common.llm.ollama_helper import get_working_ollama_base_url
from common.constants import LLM_MODEL
from prompts.agent import AXON_IDENTITY_PROMPT, SUMMARIZE_TOOL_OUTPUT_PROMPT

qwen_llm = ChatOllama(
    model=LLM_MODEL,
    base_url=get_working_ollama_base_url(),
    temperature=0.2,
    streaming=True,
    request_timeout=60,
    num_predict=300,
)


async def run_qwen(query: str) -> str:
    messages = [
        SystemMessage(content=AXON_IDENTITY_PROMPT),
        HumanMessage(content=query),
    ]

    full_content = []
    async for chunk in qwen_llm.astream(messages):
        content = chunk.content
        sys.stdout.write(content.replace("\n", "<br/>"))
        sys.stdout.flush()
        full_content.append(content)
    return "".join(full_content)

class StreamingCleaner:
    def __init__(self):
        self.buffer = ""
        self.header_processed = False

    def process_chunk(self, chunk: str) -> str:
        if self.header_processed:
            out = chunk.replace("&lt;", "<").replace("&gt;", ">")
            self.buffer += out
            if len(self.buffer) > 15:
                flush_len = len(self.buffer) - 15
                to_flush = self.buffer[:flush_len]
                self.buffer = self.buffer[flush_len:]
                return to_flush
            return ""
        else:
            self.buffer += chunk
            if len(self.buffer) >= 30 or "\n" in self.buffer or " " in self.buffer:
                stripped = self.buffer.lstrip()
                match = re.match(r'^```[a-zA-Z0-9]*\s*', stripped)
                if match:
                    self.buffer = stripped[match.end():]
                self.header_processed = True
                
                out = self.buffer.replace("&lt;", "<").replace("&gt;", ">")
                self.buffer = ""
                if len(out) > 15:
                    flush_len = len(out) - 15
                    to_flush = out[:flush_len]
                    self.buffer = out[flush_len:]
                    return to_flush
                else:
                    self.buffer = out
                    return ""
            return ""

    def finalize(self) -> str:
        final_chunk = self.buffer
        final_chunk = re.sub(r'\s*```\s*$', '', final_chunk)
        final_chunk = final_chunk.replace("&lt;", "<").replace("&gt;", ">")
        return final_chunk


async def summarize_tool_output(
    user_query: str,
    tool_name: str,
    tool_data: any
) -> str:
    if tool_name == "arxiv":
        formatted_data = str(tool_data)
        await stream_text_word_by_word(formatted_data)
        return formatted_data

    if tool_name == "wiki" and isinstance(tool_data, dict):
        title   = tool_data.get("title") or "Wikipedia"
        summary = tool_data.get("summary") or tool_data.get("extract") or ""
        url     = tool_data.get("url") or ""

        # Split into paragraphs and keep up to 3 to get a rich summary
        paragraphs = [p.strip() for p in summary.split("\n") if p.strip()]
        trimmed = "\n\n".join(paragraphs[:3])

        # Stream the summary word by word
        await stream_text_word_by_word(trimmed)

        # Append source link
        if url:
            source_line = f"\n\nSources: [{title}]({url})"
            sys.stdout.write("\n" + source_line.replace("\n", "<br/>") + "\n")
            sys.stdout.flush()
            return trimmed + source_line

        return trimmed

    if tool_name == "ddgs" and isinstance(tool_data, dict):
        results = tool_data.get("results", [])

        # Build body text: title + snippet for top 3 results
        lines = []
        source_links = []
        for res in results[:3]:
            r_title   = res.get("title", "Result").strip()
            r_snippet = res.get("body", "").strip()
            r_url     = res.get("href", "")

            if r_snippet:
                lines.append(f"{r_title}: {r_snippet}")
            if r_url:
                clean_title = re.sub(r'[\[\]]', '', r_title)
                source_links.append(f"[{clean_title}]({r_url})")

        body = "\n\n".join(lines)

        # Stream body word by word
        await stream_text_word_by_word(body)

        # Append source links
        if source_links:
            sources_str = "\n\nSources: " + " | ".join(source_links)
            sys.stdout.write("\n" + sources_str.replace("\n", "<br/>") + "\n")
            sys.stdout.flush()
            return body + sources_str

        return body

    # Fallback — stream raw string
    raw = str(tool_data)
    await stream_text_word_by_word(raw)
    return raw

