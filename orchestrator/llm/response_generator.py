# orchestrator/llm/response_generator.py

"""
LLM Response Generator
----------------------
Converts structured Frappe API responses into natural language answers
using Qwen via Ollama.

This module is designed to be:
  • Modular — can be used standalone or integrated into any pipeline
  • Optional — callers can skip it for raw JSON output during debugging
  • Configurable — uses OLLAMA_BASE_URL env var for the Ollama endpoint
"""

import os
import json
import logging
from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

_response_llm = ChatOllama(
    model="qwen2.5:0.5b",
    base_url=OLLAMA_URL,
    temperature=0,
    streaming=False,
)

_RESPONSE_PROMPT = """\
You are an ERP assistant that converts structured data into clear answers.

Rules:
- Use the user query as context to understand what they asked.
- Answer clearly and concisely in natural language.
- If the data shows meal booking or consumption details, explain what was booked and consumed.
- If the data contains leave, attendance, or other HR records, summarize them clearly.
- If no data exists or the data list is empty, say that no records were found.
- Do NOT output raw JSON or code blocks.
- Do NOT add unnecessary caveats or disclaimers.
- Be direct and helpful.

User Query:
{query}

ERP Data:
{data}

Return only the final answer in natural language.
"""


def generate_response(query: str, frappe_data) -> str:
    """
    Convert structured Frappe API data into a natural language answer.

    Parameters
    ----------
    query : str
        The original user query for context.
    frappe_data : dict | list
        The data returned by the Frappe API (typically a list of records
        or a dict with a ``data`` key).

    Returns
    -------
    str
        A natural language answer suitable for displaying to the user.
    """
    # Serialize data for the prompt
    if isinstance(frappe_data, (dict, list)):
        data_str = json.dumps(frappe_data, indent=2, default=str)
    else:
        data_str = str(frappe_data)

    prompt = _RESPONSE_PROMPT.format(
        query=query,
        data=data_str,
    )

    logger.debug("LLM response prompt length: %d chars", len(prompt))

    try:
        response = _response_llm.invoke(prompt)
        answer = response.content.strip()
        logger.info("LLM response generated (%d chars)", len(answer))
        return answer
    except Exception as exc:
        logger.error("LLM response generation failed: %s", exc)
        return f"I retrieved the data but couldn't generate a summary. Raw data: {data_str[:500]}"
