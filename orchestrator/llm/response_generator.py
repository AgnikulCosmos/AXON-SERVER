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
from common.llm.ollama_helper import get_working_ollama_base_url

logger = logging.getLogger(__name__)

_response_llm = ChatOllama(
    model=os.getenv("LLM_MODEL", "qwen3.5:0.8b"),
    base_url=get_working_ollama_base_url(),
    temperature=0,
    streaming=False,
)

from prompts.agent import RESPONSE_GENERATOR_PROMPT
_RESPONSE_PROMPT = RESPONSE_GENERATOR_PROMPT


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
