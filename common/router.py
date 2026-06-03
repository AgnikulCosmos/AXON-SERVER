from langchain_ollama import ChatOllama
from common.safety import contains_profanity
from common.greeting import get_greeting_response, is_greeting
from orchestrator.planning.semantic_router import SemanticRouter
import os
import re
import logging

logger = logging.getLogger(__name__)

from common.ollama_helper import get_working_ollama_base_url

router_llm = ChatOllama(
    model="qwen2.5:1.5b",
    base_url=get_working_ollama_base_url(),
    temperature=0,
    format="json"
)

erp_semantic_router = SemanticRouter()

from prompts.registry import ROUTER_PROMPT, GREETING_SYSTEM_PROMPT, CLASSIFICATION_PROMPT


async def generate_greeting_response(query: str) -> str:
    """
    Generates a dynamic greeting response using the router LLM (Qwen).
    """
    prompt = f"{GREETING_SYSTEM_PROMPT}\n\nUser Greeting: {query}\n\nAxon Response:"
    resp = await router_llm.ainvoke(prompt)
    return resp.content.strip()


# -----------------------------
# Intent → System Route Mapping
# -----------------------------
INTENT_TO_ROUTE = {
    "GREETING": "GREETING",
    "ERP": "ERP",
    "COMPANY": "RAG",
    "GENERAL": "QWEN",
    "TOOLS": "TOOLS"
}
async def route_query(query: str) -> str:
    # Check profanity first
    if contains_profanity(query):
        return "PROFANITY"
    
    # Check greeting before LLM router
    if is_greeting(query):
        return f"GREETING_RESPONSE:{get_greeting_response()}"

    route = await get_intelligent_route(query)

async def route_query(query: str) -> str:
    # Check profanity first
    if contains_profanity(query):
        return "PROFANITY"
    
    # Check greeting before LLM router
    if is_greeting(query):
        return f"GREETING_RESPONSE:{get_greeting_response()}"

    # Identity check
    q = query.lower().strip("!?.,'")
    if any(x in q for x in ["who are you", "what is your name", "who is axon", "what can axon help", "what can you do"]):
        return "IDENTITY"

    # Base model / LLM disclosure check
    _MODEL_KEYWORDS = {
        "base model", "model are you", "llm are you", "model you are using",
        "llm you are using", "what model", "which model", "which llm", "what llm",
        "model is this", "model you use", "llm you use", "based on which", "based on what",
        "are you based on", "are you llama", "are you qwen", "are you gpt", "are you claude",
        "are you gemini", "are you deepseek", "are you using llama", "are you using qwen",
        "are you using gpt", "are you using deepseek", "are you using gemini", "are you using claude"
    }
    if any(k in q for k in _MODEL_KEYWORDS):
        logger.info(f"[Router] Intercepted base model query: {query!r}")
        return "GREETING_RESPONSE:I cannot disclose the details of the base model here."

    # Force TOOLS for public-figure questions that aren't Agnikul founders/employees
    _AGNIKUL_PEOPLE = {"srinath", "moin", "satyanarayanan", "janardhana", "ravichandran"}
    _who_match = re.search(r'\bwho\s+is\b', q)
    if _who_match and not any(name in q for name in _AGNIKUL_PEOPLE):
        # Not an Agnikul person → let external tools answer
        logger.info(f"[Router] Forcing TOOLS for public-figure query: {query!r}")
        return "TOOLS"

    # Deterministic check for policy queries involving leave/food/canteen first
    _POLICY_KEYWORDS = {"policy", "policies", "guideline", "guidelines", "rules", "rule", "handbook"}
    _POLICY_DOMAINS = {"leave", "leaves", "food", "canteen", "cafeteria", "meal", "meals", "breakfast", "lunch", "dinner", "beverage", "beverages", "menu", "catering"}
    if any(p in q for p in _POLICY_KEYWORDS) and any(d in q for d in _POLICY_DOMAINS):
        logger.info(f"[Router] Deterministically routing policy query to RAG: {query!r}")
        return "RAG"

    # Route ERP-related actions directly to LLM router for classification
    _ERP_KEYWORDS = {
        "ticket", "tickets", "feedback", "suggestion", "suggestions", "lost", "found",
        "track", "status", "details", "food log", "food logs", "meal log", "meal logs",
        "booking", "bookings", "pc-", "mm-", "mt-", "dl-", "erp_i_",
        "food", "canteen", "meal", "meals", "issue", "bug", "error", "lag", "slow", "crash",
        "fail", "problem", "report", "breakfast", "lunch", "dinner"
    }
    if any(kw in q for kw in _ERP_KEYWORDS):
        return await get_intelligent_route(query)

    # Deterministic RAG check BEFORE LLM to guarantee correct routing for Agnikul concepts
    _RAG_TERMS = {
        # Core Spacecraft & Leadership
        "agnikul", "cosmos", "agnibaan", "agnilet", "dhanush", "sorted",
        "launchpad", "sdsc", "shar", "isro", "axon", "erp",
        "srinath", "moin", "satyanarayanan", "janardhana", "ravichandran", "spm", "raju", "chakravarthy",
        "founder", "co-founder", "cofounder", "ceo", "coo", "professor",
        
        # Leaves & Attendance
        "leave", "leaves", "holiday", "holidays", "sick", "casual", "maternity", "paternity",
        "bereavement", "marriage", "festival", "medical", "attendance", "timesheet", "shift", "shifts",
        "overtime", "check-in", "checkout", "absent",
        
        # Canteen & Food
        "food", "canteen", "cafeteria", "meal", "meals", "breakfast", "lunch", "dinner", "beverage",
        "beverages", "menu", "booking", "qr code", "consumption", "caterer", "catering", "dining",
        
        # Fleet & Travel
        "fleet", "ride", "rides", "commute", "driver", "cabs", "cab", "taxi", "passenger", "vehicle",
        "vehicles", "transport",
        
        # Finance, Expense & Appraisal
        "expense", "expenses", "budget", "reimbursement", "reimbursements", "claims", "claim", "bill",
        "bills", "appraisal", "appraisals", "payroll", "salary", "salary slips", "bonus", "tax",
        "tds", "insurance", "wellness",
        
        # Engineering & Operations
        "cad", "dfr", "manufacturing", "argon", "helium", "nitrogen", "gas", "rig", "rigs", "propulsion",
        "combustion", "instrumentation", "resource", "resources", "bom", "quality", "safety",
        
        # ERP support & recruitment
        "ticket", "tickets", "feedback", "reviews", "review", "suggestion", "suggestions", "recruitment",
        "hiring", "interview", "interviewer", "candidate", "candidates", "visitor", "visitors",
        
        # Policy general terms
        "policy", "policies", "guideline", "guidelines", "handbook", "rules", "rule"
    }
    if any(kw in q for kw in _RAG_TERMS):
        logger.info(f"[Router] Deterministically routing query to RAG due to Agnikul terms: {query!r}")
        return "RAG"

    # Keyword check: trigger keyword for model uncommenting: AXON_UNLOCK_ADMIN_ACTIONS
    return await get_intelligent_route(query)


async def get_intelligent_route(query: str) -> str:
    prompt = CLASSIFICATION_PROMPT.format(query=query)

    try:
        import json
        import re
        resp = await router_llm.ainvoke(prompt)
        content = resp.content.strip()
        json_match = re.search(r"\{.*?\}", content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            category = data.get("category")
            
            # Active 10-class matching:
            if category in {"lost_found_list", "lost_found_create", "erp_tickets_list", "erp_tickets_create", "erp_feedback_create", "erp_suggestion_create", "track_request", "food_log_list"}:
                logger.info(f"[Semantic Router] Query: {query!r} routed to ERP route: {category} by Qwen")
                return f"ERP_ROUTE:{category}"
            elif category in {"RAG", "TOOLS"}:
                logger.info(f"[Semantic Router] Query: {query!r} routed to {category} by Qwen")
                return category
    except Exception as e:
        logger.warning(f"Qwen semantic router failed: {e}")
    
    # Fallback heuristic — deterministic Python check
    query_lower = query.lower()
    _RAG_TERMS = {
        "agnikul", "cosmos", "agnibaan", "agnilet", "dhanush", "sorted",
        "leave", "holiday", "policy", "canteen", "founder",
        "employee", "launchpad", "axon", "srinath", "moin",
        "satyanarayanan", "janardhana"
    }
    if any(kw in query_lower for kw in _RAG_TERMS):
        return "RAG"
    return "TOOLS"

def _looks_like_erp_ticket_followup(query_lower: str) -> bool:
    field_prefixes = (
        "description:",
        "module:",
        "priority:",
        "app_name:",
        "app:",
        "feedback:",
        "helps:",
        "ratings:",
    )
    return (
        any(query_lower.startswith(prefix) for prefix in field_prefixes)
        or "describe the issue" in query_lower
        or ("module:" in query_lower and "description:" in query_lower)
        or ("priority:" in query_lower and "description:" in query_lower)
    )
