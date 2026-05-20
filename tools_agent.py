import sys
import asyncio
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, ToolMessage
from tools.registry import TOOLS
from agent import (
    MARKER_TOOL_START, MARKER_TOOL_END,
    MARKER_FINAL_START, MARKER_FINAL_END,
    stream_text_word_by_word
)

tool_llm = ChatOllama(
    model="qwen2.5:0.5b",
    temperature=0
).bind_tools(TOOLS)

async def run_tools_agent(query: str):
    messages = [HumanMessage(content=query)]

    response = await tool_llm.ainvoke(messages)

    # If no tool is needed → answer directly
    if not response.tool_calls:
        sys.stdout.write(f"{MARKER_FINAL_START}\n")
        await stream_text_word_by_word(str(response.content))
        sys.stdout.write(f"{MARKER_FINAL_END}\n")
        sys.stdout.flush()
        return response.content

    # Execute tools
    for tool_call in response.tool_calls:
        tool = next(t for t in TOOLS if t.name == tool_call["name"])

        sys.stdout.write(f"{MARKER_TOOL_START}\n")
        result = tool.func(**tool_call["args"])
        await stream_text_word_by_word(str(result))
        sys.stdout.write(f"{MARKER_TOOL_END}\n")

        #  SPECIAL CASE: arXiv → RETURN DIRECT
        if tool.name == "arxiv":
            sys.stdout.write(f"{MARKER_FINAL_START}\n")
            await stream_text_word_by_word(str(result))
            sys.stdout.write(f"{MARKER_FINAL_END}\n")
            sys.stdout.flush()
            return result

        #  DEFAULT: other tools continue to LLM
        messages.append(ToolMessage(
            content=str(result),
            tool_call_id=tool_call["id"]
        ))


    # Final answer after tools
    final = await tool_llm.ainvoke(messages)
    sys.stdout.write(f"{MARKER_FINAL_START}\n")
    await stream_text_word_by_word(str(final.content))
    sys.stdout.write(f"{MARKER_FINAL_END}\n")
    sys.stdout.flush()

    return final.content
