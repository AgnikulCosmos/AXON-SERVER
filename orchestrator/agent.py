import sys
import asyncio
from typing import List, Dict, Any
import os


from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
# from tools.registry import TOOLS

# Markers for frontend parsing
MARKER_REASONING_START = "<<<REASONING_START>>>"
MARKER_REASONING_END   = "<<<REASONING_END>>>"
MARKER_TOOL_START      = "<<<TOOL_START>>>"
MARKER_TOOL_END        = "<<<TOOL_END>>>"
MARKER_FINAL_START     = "<<<FINAL_START>>>"
MARKER_FINAL_END       = "<<<FINAL_END>>>"

WORD_STREAM_DELAY = 0.01  # 10 ms per word ≈ visible streaming

import re  # add this at the top if not already

async def stream_text_word_by_word(text: str, *, end: str = "\n") -> None:
    """
    Stream `text` to stdout while preserving whitespace (including newlines),
    but still giving a "word-by-word" feel for non-whitespace tokens.
    """
    text = text or ""
    if not text:
        return

    # Split into "word" and "whitespace" tokens, preserving newlines
    tokens = re.split(r"(\s+)", text)

    for tok in tokens:
        if tok == "":
            continue

        sys.stdout.write(tok)
        sys.stdout.flush()

        # Only delay after non-whitespace tokens, so newlines are instant
        if WORD_STREAM_DELAY and not tok.isspace():
            await asyncio.sleep(WORD_STREAM_DELAY)

    if end:
        sys.stdout.write(end)
        sys.stdout.flush()



# Initialize ChatOllama with reasoning enabled
# llm = ChatOllama(
#     model="gpt-oss:20b",
#     base_url="",
#     temperature=0.7,
#     reasoning=True, 
# )

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

llm = ChatOllama(
    model="qwen2.5:0.5b",
    base_url=OLLAMA_BASE_URL,
    temperature=0.3,
    top_p=0.9,
    repeat_penalty=1.1,
    streaming=False
)


# Bind tools to model
#llm_with_tools = llm.bind_tools(TOOLS)
ENABLE_TOOLS = False
if ENABLE_TOOLS:
    llm_with_tools = llm.bind_tools(TOOLS)
else:
    llm_with_tools = llm


# System prompt
SYSTEM_PROMPT = """
You are AXON, the intelligent assistant for Agnikul Cosmos.

You can:
- Answer general knowledge questions
- Answer ERP and operational questions
- Use tools when required to fetch or act on information

Use tools ONLY when necessary.
If no tool is needed, answer directly.
"""


async def run_axon(question: str, max_iterations: int = 5) -> str:
    """
    Modern LangChain 1.0+ agent using native tool calling and reasoning.
    Uses astream_events for unified streaming of reasoning, tool calls, and responses.

    """

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=question)
    ]
    
    for iteration in range(max_iterations):
        try:
            # Invoke model with tool binding
            response: AIMessage = await llm_with_tools.ainvoke(messages)
            
            # Parse content blocks (LangChain 1.0+ feature)
            content_blocks = response.content if isinstance(response.content, list) else [{"type": "text", "text": str(response.content)}]
            
            # Check for reasoning in additional_kwargs (ChatOllama stores it here)
            reasoning_content = response.additional_kwargs.get("reasoning_content", "")
            
            # Process reasoning if present (streamed word-by-word)
            if reasoning_content:
                sys.stdout.write(f"{MARKER_REASONING_START}\n")
                sys.stdout.flush()
                await stream_text_word_by_word(reasoning_content, end="\n")
                sys.stdout.write(f"{MARKER_REASONING_END}\n")
                sys.stdout.flush()
            
            # Check for tool calls (native LangChain feature)
            # Check for tool calls ONLY if tools are enabled
            if ENABLE_TOOLS and response.tool_calls:

                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_id = tool_call.get("id", "")
                    
                    # Emit tool section
                    sys.stdout.write(f"{MARKER_TOOL_START}\n")
                    sys.stdout.write(f"🔧 Requested tool: {tool_name}\n")
                    sys.stdout.flush()
                    
                    # Find and execute tool
                    tool = next((t for t in TOOLS if t.name == tool_name), None)
                    if not tool:
                        error_msg = f"❌ Error: Unknown tool '{tool_name}'"
                        sys.stdout.write(error_msg + "\n")
                        sys.stdout.write(f"{MARKER_TOOL_END}\n")
                        sys.stdout.flush()
                        
                        # Add error to messages
                        messages.append(response)
                        messages.append(ToolMessage(
                            content=error_msg,
                            tool_call_id=tool_id
                        ))
                        continue
                    
                    try:
                        # Execute tool
                        sys.stdout.write(f"⚙️ Calling tool with input: {tool_args}\n")
                        sys.stdout.flush()
                        
                        # Invoke tool (supports both sync and async)
                        if asyncio.iscoroutinefunction(tool.func):
                            result = await tool.func(**tool_args)
                        else:
                            result = tool.func(**tool_args)
                        
                        # Emit result (streamed)
                        sys.stdout.write("✅ Tool result:\n")
                        sys.stdout.flush()
                        await stream_text_word_by_word(str(result), end="\n")
                        sys.stdout.write(f"{MARKER_TOOL_END}\n")
                        sys.stdout.flush()

                        
                        # Add tool result to messages
                        messages.append(response)
                        messages.append(ToolMessage(
                            content=str(result),
                            tool_call_id=tool_id
                        ))
                        
                    except Exception as e:
                        error_msg = f"❌ Tool error: {str(e)}"
                        sys.stdout.write(error_msg + "\n")
                        sys.stdout.write(f"{MARKER_TOOL_END}\n")
                        sys.stdout.flush()
                        
                        messages.append(response)
                        messages.append(ToolMessage(
                            content=error_msg,
                            tool_call_id=tool_id
                        ))
                
                # Continue loop to get final answer
                continue
            
            # No tool calls - this is the final answer
            sys.stdout.write(f"{MARKER_FINAL_START}\n")
            sys.stdout.flush()

            # Extract text from content blocks
            final_text = ""
            if isinstance(response.content, list):
                for block in response.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        final_text += block.get("text", "")
                    elif isinstance(block, str):
                        final_text += block
            else:
                final_text = str(response.content)

            # Stream the final answer word-by-word
            await stream_text_word_by_word(final_text.strip(), end="\n")

            sys.stdout.write(f"{MARKER_FINAL_END}\n")
            sys.stdout.flush()

            return final_text

        
        except Exception as e:
            error_msg = f"Agent error: {str(e)}"
            print(error_msg, file=sys.stderr)
            sys.stdout.write(f"{MARKER_FINAL_START}\n")
            sys.stdout.write(error_msg + "\n")
            sys.stdout.write(f"{MARKER_FINAL_END}\n")
            sys.stdout.flush()
            return error_msg
    sys.stdout.write(f"{MARKER_FINAL_START}\n")
    sys.stdout.write("Agent finished without an explicit final answer.\n")
    sys.stdout.write(f"{MARKER_FINAL_END}\n")
    sys.stdout.flush()
    
    return "Agent exceeded maximum iterations"


def run_axon_sync(question: str, max_iterations: int = 5) -> str:
    """Synchronous wrapper for run_agent."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(run_axon(question, max_iterations))