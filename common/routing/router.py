from common.routing.safety import contains_profanity
from common.routing.greeting import get_greeting_response, is_greeting
from common.constants import MODEL_KEYWORDS, AGNIKUL_PEOPLE, LLM_MODEL
from common.routing.intent_router import IntentRouter
from common.llm.ollama_helper import get_working_ollama_base_url
from prompts.routing import GREETING_SYSTEM_PROMPT, CONFIRM_ROUTE_PROMPT, DISAMBIGUATE_ROUTE_PROMPT
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


def _get_intent_router(threshold: Optional[float] = None) -> IntentRouter:
    global _intent_router
    if _intent_router is None:
        _intent_router = IntentRouter(threshold=threshold)
    return _intent_router


def get_erp_route_config(route_name: str) -> Optional[dict]:
    """Get a route config by name using the shared IntentRouter's SemanticRouter.
    Avoids creating a new SemanticRouter instance and re-scanning routes.json."""
    return _get_intent_router().get_route_config(route_name)


async def generate_greeting_response(query: str) -> str:
    prompt = f"{GREETING_SYSTEM_PROMPT}\n\nUser Greeting: {query}\n\nAxon Response:"
    resp = await _get_router_llm().ainvoke(prompt)
    return resp.content.strip()


from common.routing.intent_router import TOP_LEVEL_CATEGORIES, ERP_ROUTE_NAMES

async def _confirm_route_with_llm(query: str, route_desc: str) -> bool:
    from common.llm.ollama_helper import get_working_ollama_base_url
    import ollama
    import os
    import re

    prompt = CONFIRM_ROUTE_PROMPT.format(route_desc=route_desc, query=query)

    try:
        model = os.getenv("LLM_MODEL", "qwen3.5:0.8b")
        async with ollama.AsyncClient(host=get_working_ollama_base_url()) as client:
            resp = await client.generate(
                model=model,
                prompt=prompt,
                options={"temperature": 0.0, "num_predict": 120}
            )
            if hasattr(resp, "response"):
                ans = resp.response.strip()
            elif isinstance(resp, dict):
                ans = resp.get("response", "").strip()
            else:
                ans = str(resp).strip()
            ans = re.sub(r'[^0-9]', '', ans)
            logger.info(f"[LLM CONFIRMATION] Query: {query!r} | Desc: {route_desc!r} | Ans: {ans!r}")
            if "1" in ans:
                return True
    except Exception as e:
        logger.warning(f"Failed to confirm route with LLM: {e}")

    return False


def _heuristic_disambiguation(query: str, category: str) -> Optional[str]:
    q = query.lower()
    view_words = {"show", "view", "list", "check", "track", "history", "status", "active", "find"}
    create_words = {"create", "submit", "raise", "report", "new", "make", "add", "post", "file", "register"}

    if category == "ticket":
        if any(w in q for w in view_words):
            return "erp_tickets_list"
        if any(w in q for w in create_words) or "lag" in q or "bug" in q or "issue" in q or "error" in q:
            return "erp_tickets_create"
    elif category == "feedback":
        if any(w in q for w in view_words):
            return "erp_feedback_list"
        if any(w in q for w in create_words) or "feedback" in q:
            return "erp_feedback_create"
    elif category == "suggestion":
        if any(w in q for w in view_words):
            return "erp_suggestions_list"
        if any(w in q for w in create_words) or "suggest" in q or "suggestion" in q:
            return "erp_suggestion_create"
    elif category == "lost_found":
        if any(w in q for w in view_words):
            return "lost_found_list"
        if any(w in q for w in create_words) or "lost" in q or "found" in q:
            return "lost_found_create"
    return None


async def _disambiguate_route_with_llm(query: str, route_name: str) -> str:
    category = None
    if "ticket" in route_name:
        category = "ticket"
    elif "feedback" in route_name:
        category = "feedback"
    elif "suggestion" in route_name:
        category = "suggestion"
    elif "lost_found" in route_name or re.search(r'\b(lost|found)\b', query.lower()):
        category = "lost_found"

    if not category:
        return route_name

    h_route = _heuristic_disambiguation(query, category)
    if h_route:
        logger.info(f"[Heuristic Disambiguation] Query: {query!r} | Category: {category} -> {h_route}")
        return h_route

    if category == "ticket":
        options = {"create": "erp_tickets_create", "view": "erp_tickets_list"}
    elif category == "feedback":
        options = {"create": "erp_feedback_create", "view": "erp_feedback_list"}
    elif category == "suggestion":
        options = {"create": "erp_suggestion_create", "view": "erp_suggestions_list"}
    else:  # lost_found
        options = {"create": "lost_found_create", "view": "lost_found_list"}

    from common.llm.ollama_helper import get_working_ollama_base_url
    import ollama
    import os

    prompt = DISAMBIGUATE_ROUTE_PROMPT.format(category=category.upper(), query=query.strip().capitalize())

    try:
        model = os.getenv("LLM_MODEL", "qwen3.5:0.8b")
        async with ollama.AsyncClient(host=get_working_ollama_base_url()) as client:
            resp = await client.generate(
                model=model,
                prompt=prompt,
                options={"temperature": 0.0, "num_predict": 120}
            )
            if hasattr(resp, "response"):
                ans = resp.response.strip().lower()
            elif isinstance(resp, dict):
                ans = resp.get("response", "").strip().lower()
            else:
                ans = str(resp).strip().lower()
            ans = re.sub(r'[^a-z]', '', ans)
            logger.info(f"[LLM DISAMBIGUATION] Query: {query!r} | Category: {category} | Ans: {ans!r}")
            if ans in options:
                logger.info(f"[LLM DISAMBIGUATION] Selected {ans} -> {options[ans]} for query {query!r}")
                return options[ans]
    except Exception as e:
        logger.warning(f"Failed to disambiguate route with LLM: {e}")

    return route_name



# ── Domain keyword vocabulary for typo correction ──────────────────────────
# Words the semantic router cares about. difflib will fuzzy-match user words
# against this list and replace close-enough matches before embedding.
_ERP_VOCAB = {
    "leave", "balance", "track",
    "food", "canteen", "booking", "log", "meal", "dinner", "lunch", "breakfast",
    "ticket", "feedback", "suggestion", "create", "submit", "raise", "report",
    "lost", "found", "item", "management", "support", "erp",
    "fleet", "hr", "payroll", "finance", "inventory", "procurement",
    "casual", "sick", "allocated", "remaining", "taken",
}

def _normalize_query(query: str) -> str:
    """
    Correct obvious typos in domain-specific words before embedding.
    Only fixes words that are >=4 chars and have a close match (cutoff 0.70)
    so short words and proper nouns are left untouched.
    """
    import difflib
    words = query.split()
    corrected = []
    for word in words:
        # Strip punctuation for matching, preserve it for output
        stripped = word.strip("!?.,;:'\"").lower()
        if len(stripped) >= 4 and stripped not in _ERP_VOCAB:
            matches = difflib.get_close_matches(stripped, _ERP_VOCAB, n=1, cutoff=0.80)
            if matches:
                # Replace the stripped part, preserving original case pattern and surrounding punctuation
                prefix = word[: len(word) - len(word.lstrip("!?.,;:'\""))]
                suffix = word[len(word.rstrip("!?.,;:'\"")):]
                fixed = matches[0]
                # Preserve capitalisation if original word started with uppercase
                if word and word[0].isupper():
                    fixed = fixed.capitalize()
                corrected.append(prefix + fixed + suffix)
                logger.debug(f"[QueryNormalizer] Corrected {stripped!r} → {matches[0]!r}")
                continue
        corrected.append(word)
    return " ".join(corrected)


async def route_query(query: str) -> str:
    if contains_profanity(query):
        return "PROFANITY"

    if is_greeting(query):
        return f"GREETING_RESPONSE:{get_greeting_response()}"

    # Forcing TOOLS for public/country-specific space queries early
    q_lower = query.lower().strip("!?.,'")
    public_entities = {
        "india", "isro", "spacex", "nasa", "china", "russia", "esa", "blue origin",
        "rocket lab", "jaxa", "roscosmos", "cnsa", "united states", "japan", "france", "uk"
    }
    space_stems = {"rocket", "rockte", "launch", "satellite", "mission", "engine", "booster"}
    
    has_public = any(re.search(r'\b' + re.escape(entity) + r'\b', q_lower) for entity in public_entities)
    has_space = any(stem in q_lower for stem in space_stems)
    
    if has_public and has_space:
        logger.info(f"[Router] Forcing TOOLS for public space query: {query!r}")
        return "TOOLS"

    # Force RAG for any query that contains an Agnikul-specific entity or domain term.
    # This ensures questions like "What about Dhanush?" are answered from the knowledge base.
    from common.constants import RAG_TERMS
    q_words = set(re.findall(r'\b[a-z]+\b', q_lower))
    if q_words & RAG_TERMS:
        logger.info(f"[Router] Forcing RAG for Agnikul-domain query: {query!r}")
        return "RAG"

    # Normalize query — fix domain-specific typos before embedding lookup
    normalized_query = _normalize_query(query)
    if normalized_query != query:
        logger.info(f"[Router] Typo corrected: {query!r} → {normalized_query!r}")
    query = normalized_query

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

    # Hybrid Semantic-LLM classifier
    router = _get_intent_router(threshold=0.45)
    semantic = router._get_semantic()
    match_result = semantic.match(query) if semantic else None

    if match_result:
        route_name = match_result["route"]["route_name"]
        confidence = match_result["confidence"]

        logger.info(f"[Router] Semantic candidate match: {route_name} with confidence {confidence:.4f}")

        # 1. Verification/Confirmation for low confidence
        if confidence < 0.75:
            route_desc = match_result["route"].get("description", "")
            is_valid = await _confirm_route_with_llm(query, route_desc)
            if not is_valid:
                logger.info(f"[Router] LLM rejected candidate match {route_name} for query {query!r}")
                route_name = "QWEN"

        # 2. Create vs List Disambiguation
        if route_name != "QWEN":
            route_name = await _disambiguate_route_with_llm(query, route_name)

        if route_name in TOP_LEVEL_CATEGORIES:
            return route_name
        elif route_name in ERP_ROUTE_NAMES:
            return f"ERP_ROUTE:{route_name}"

    return "QWEN"
