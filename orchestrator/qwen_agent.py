from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from orchestrator.agent import (
    MARKER_FINAL_START,
    MARKER_FINAL_END,
)

import os
qwen_llm = ChatOllama(
    model="qwen2.5:0.5b",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
    temperature=0.2,
    streaming=False
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

    response = await qwen_llm.ainvoke(messages)
    return response.content

async def summarize_tool_output(
    user_query: str,
    tool_name: str,
    tool_data: dict
) -> str:
    prompt = f"""
The user asked:
{user_query}

The following information was retrieved using the tool "{tool_name}":

{tool_data}

Your task:
- Summarize this information clearly for the user
- Be concise and professional
- Do NOT mention tools, APIs, JSON, or internal processing
- If results are empty, say that no relevant information was found
"""

    messages = [
        SystemMessage(content=AXON_IDENTITY_PROMPT),
        HumanMessage(content=prompt),
    ]

    response = await qwen_llm.ainvoke(messages)
    return response.content
