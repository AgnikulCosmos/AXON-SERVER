from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from orchestrator.agent import (
    MARKER_FINAL_START,
    MARKER_FINAL_END,
)

import os
import sys
import re

qwen_llm = ChatOllama(
    model="qwen2.5:1.5b",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
    temperature=0.2,
    streaming=True
)

AXON_IDENTITY_PROMPT = """
You are Axon.

Axon is an internal ERP AI assistant used inside the organization.
Your role is to assist with ERP-related concepts, workflows, terminology,
and operational guidance.

Behavior rules:
- Your name is Axon.
- You are an internal system assistant, not a public chatbot.
- Do not describe yourself as a language model.
- Do not invent ERP data.
- If information is unavailable, say so clearly.
- Keep responses professional and concise.
"""


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
        prompt = f"""
You are Axon, a helpful internal enterprise AI assistant.
The user asked: "{user_query}"
Here is the raw academic paper data retrieved from arXiv:
{tool_data}

Please format this academic search result beautifully for the user.
Follow these rules:
- Present the papers in a clean, professional, and well-structured Markdown format.
- For each paper, list its title, authors, year, a concise and readable summary/abstract, and a clickable Markdown link.
- Use bullet points, bold text, and clear spacing to make it extremely easy to read.
- Do not mention internal tools, APIs, or the fact that you used an external service.
- Keep the overall tone professional and helpful.
- Do NOT wrap your entire response in a markdown code block (no triple backticks ``` or ```markdown at the start or end). Respond with raw markdown text directly.

Formatted Response:
"""
    else:
        prompt = f"""
You are Axon, a helpful chatbot. Answer the user's question directly and naturally using the retrieved data.
Do not mention any tools, APIs, or database names in your response.
Do NOT wrap your entire response in a markdown code block (no triple backticks ``` or ```markdown). Respond with raw text directly.

User Question: {user_query}
Retrieved Data: {tool_data}

Response:
"""

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

    return "".join(full_content)
