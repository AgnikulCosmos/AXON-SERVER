from common.routing.safety import contains_profanity
from common.routing.greeting import get_greeting_response, is_greeting
from common.constants import MODEL_KEYWORDS, AGNIKUL_PEOPLE, LLM_MODEL
from common.routing.intent_router import IntentRouter
from common.llm.ollama_helper import get_working_ollama_base_url
from prompts.routing import GREETING_SYSTEM_PROMPT
from typing import Optional
import re
import logging

logger = logging.getLogger(__name__)

_router_llm = None


def _get_router_llm():
    global _router_llm
    if _router_llm is None:
        try:
            from langchain_ollama import ChatOllama
            _router_llm = ChatOllama(
                model=LLM_MODEL,
                base_url=get_working_ollama_base_url(),
                temperature=0,
                format="json"
            )
        except Exception as e:
            logger.warning("Failed to initialise router LLM: %s", e)
            _router_llm = False
    return _router_llm or None

_intent_router: IntentRouter | None = None


def _get_intent_router() -> IntentRouter:
    global _intent_router
    if _intent_router is None:
        _intent_router = IntentRouter()
    return _intent_router


def get_erp_route_config(route_name: str) -> Optional[dict]:
    """Get a route config by name using the shared IntentRouter's SemanticRouter.
    Avoids creating a new SemanticRouter instance and re-scanning routes.json."""
    return _get_intent_router().get_route_config(route_name)


async def generate_greeting_response(query: str) -> str:
    prompt = f"{GREETING_SYSTEM_PROMPT}\n\nUser Greeting: {query}\n\nAxon Response:"
    resp = await _get_router_llm().ainvoke(prompt)
    return resp.content.strip()


async def route_query(query: str) -> str:
    if contains_profanity(query):
        return "PROFANITY"

    if is_greeting(query):
        return f"GREETING_RESPONSE:{get_greeting_response()}"

    q = query.lower().strip("!?.,'")
    if any(k in q for k in MODEL_KEYWORDS):
        logger.info(f"[Router] Intercepted base model query: {query!r}")
        return "GREETING_RESPONSE:I cannot disclose the details of the base model here."

    identity_queries = {
        "who are you", "what is your name", "who is axon", "tell me about yourself",
        "what are your capabilities", "what can you do", "what are you capable of",
        "introduce yourself", "what can axon do for me", "what can axon help with"
    }
    if q in identity_queries:
        logger.info(f"[Router] Intercepted identity query: {query!r}")
        return "IDENTITY"

    _who_match = re.search(r'\bwho\s+is\b', q)
    if _who_match and not any(name in q for name in AGNIKUL_PEOPLE):
        logger.info(f"[Router] Forcing TOOLS for public-figure query: {query!r}")
        return "TOOLS"

    router = _get_intent_router()
    result = router.classify(query)
    if result is not None:
        return result

    return "QWEN"
