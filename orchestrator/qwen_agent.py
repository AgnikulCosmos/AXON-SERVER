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
    streaming=True
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
    if tool_name == "wiki" and isinstance(tool_data, dict):
        summary = tool_data.get("summary") or tool_data.get("extract") or ""
        url = tool_data.get("url") or ""
        title = tool_data.get("title") or "Wikipedia"
        formatted_data = f"### {title}\n\n{summary}"
        if url:
            formatted_data += f"\n\nSource: [Wikipedia]({url})"
        
        await stream_text_word_by_word(formatted_data)
        return formatted_data

    if tool_name == "ddgs" and isinstance(tool_data, dict):
        results = tool_data.get("results", [])
        lines = []
        for i, res in enumerate(results[:3], start=1):
            title = res.get("title", "Search Result").strip()
            title = re.sub(r'[\[\]]', '', title)  # clean brackets
            snippet = res.get("body", "No description available.").strip()
            url = res.get("href", "")
            if url and not url.endswith("#duckduckgo"):
                url += "#duckduckgo"
            lines.append(f"{i}. [{title}]({url})\n{snippet}")
        formatted_data = "\n\n".join(lines)
        if not formatted_data:
            formatted_data = "No search results found."
        
        await stream_text_word_by_word(formatted_data)
        return formatted_data

    if tool_name == "arxiv":
        formatted_data = str(tool_data)
        await stream_text_word_by_word(formatted_data)
        return formatted_data

    prompt = SUMMARIZE_TOOL_OUTPUT_PROMPT.format(user_query=user_query, tool_data=tool_data)

    messages = [
        SystemMessage(content=AXON_IDENTITY_PROMPT),
        HumanMessage(content=prompt),
    ]

    cleaner = StreamingCleaner()
    full_content = []
    async for chunk in qwen_llm.astream(messages):
        content = chunk.content
        processed = cleaner.process_chunk(content)
        if processed:
            sys.stdout.write(processed.replace("\n", "<br/>"))
            sys.stdout.flush()
            full_content.append(processed)

    final_processed = cleaner.finalize()
    if final_processed:
        sys.stdout.write(final_processed.replace("\n", "<br/>"))
        sys.stdout.flush()
        full_content.append(final_processed)

    response_str = "".join(full_content)
    if tool_name == "ddgs" and isinstance(tool_data, dict):
        results = tool_data.get("results", [])
        sources = []
        for res in results[:3]:
            title = res.get("title", "Source").strip()
            title = re.sub(r'[\[\]]', '', title)  # clean brackets
            url = res.get("href")
            if url:
                sources.append(f"[{title}]({url})")
        if sources:
            sources_str = "\n\n**Sources:** " + " | ".join(sources)
            sys.stdout.write(sources_str.replace("\n", "<br/>"))
            sys.stdout.flush()
            response_str += sources_str
    elif tool_name == "wiki" and isinstance(tool_data, dict):
        url = tool_data.get("url")
        title = tool_data.get("title") or "Wikipedia"
        if url:
            sources_str = f"\n\n**Sources:** [{title}]({url})"
            sys.stdout.write(sources_str.replace("\n", "<br/>"))
            sys.stdout.flush()
            response_str += sources_str

    return response_str
