# orchestrator/llm — LLM utilities
"""
LLM module for response generation and other LLM-powered tasks.

Contains:
- response_generator: converts structured Frappe data into natural language
"""

from .response_generator import generate_response

__all__ = ["generate_response"]
