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


def heuristic_classify(query: str) -> str | None:
    q = query.lower().strip()
    
    # Check for prefix IDs or tracking patterns for track_request
    track_patterns = [
        r'\btrack\s+request\b',
        r'\bstatus\s+of\b',
        r'\bcheck\s+ticket\b',
        r'\bview\s+details\b',
    ]
    prefixes = ["pc-", "mm-", "mt-", "dl-", "erp_i_", "erp-sf-", "fbsg-", "sug-", "erp-ru-", "erp-faq-", "erp-m-"]
    has_prefix = any(p in q for p in prefixes)
    has_track_pattern = any(re.search(pat, q) for pat in track_patterns)
    if has_prefix or q.startswith("track request"):
        return "track_request"

    # lost_found_list
    lost_found_list_patterns = [
        "show lost and found", "view lost items", "list lost", "lost and found items", 
        "lost & found items", "show lost items", "show found items", "view lost and found",
        "list found items", "show found ones"
    ]
    if any(pat in q for pat in lost_found_list_patterns):
        return "lost_found_list"

    # lost_found_create
    lost_found_create_patterns = [
        "lost my", "found a", "report lost", "register a found", "reported lost", "reported found",
        "mark as found", "mark found", "mark lf-"
    ]
    if any(pat in q for pat in lost_found_create_patterns) or "lf-" in q or q.startswith("mark "):
        return "lost_found_create"

    # erp_feedback_create
    feedback_patterns = [
        "submit feedback", "give feedback", "leave feedback", "give a feedback", 
        "leave my feedback", "i want to submit feedback", "i want to give feedback", "feedback:"
    ]
    if any(pat in q for pat in feedback_patterns):
        return "erp_feedback_create"

    # erp_suggestion_create
    suggestion_patterns = [
        "submit suggestion", "submit a suggestion", "have a suggestion", "leave suggestion", 
        "suggestion:", "improve something", "enhancement request"
    ]
    if any(pat in q for pat in suggestion_patterns):
        return "erp_suggestion_create"

    # erp_tickets_list
    tickets_list_patterns = [
        "my tickets", "show tickets", "view my support tickets", "view support tickets", 
        "list my support tickets", "list support tickets", "list tickets", "show my tickets"
    ]
    if any(pat in q for pat in tickets_list_patterns):
        return "erp_tickets_list"

    # erp_tickets_create
    tickets_create_patterns = [
        "raise a ticket", "create support ticket", "submit ticket", "open a support request", 
        "raise a p0", "raise a p1", "raise a p2", "create a p0", "create a p1", "create a p2", 
        "lodge a p0", "lodge a p1", "lodge a p2", "raise a support ticket", "create a support ticket", 
        "lodge a support ticket", "facing a loading lag", "report an issue with", "raise a critical ticket",
        "open a support ticket"
    ]
    if any(pat in q for pat in tickets_create_patterns):
        return "erp_tickets_create"

    # food_log_list
    food_log_patterns = [
        "food log", "meal log", "food logs", "meal logs", "book food", "book lunch", "book dinner", 
        "book breakfast", "canteen food bookings", "meal requests", "did i book food", "book food yesterday",
        "food log for today", "did i book lunch"
    ]
    if any(pat in q for pat in food_log_patterns):
        return "food_log_list"

    return None


async def get_intelligent_route(query: str) -> str:
    # 1. Run deterministic Python-based heuristic classifier first
    h_category = heuristic_classify(query)
    if h_category:
        logger.info(f"[Semantic Router] Query: {query!r} routed to ERP route: {h_category} by heuristics")
        return f"ERP_ROUTE:{h_category}"

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
