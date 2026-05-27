from langchain_ollama import ChatOllama
from common.safety import contains_profanity
from common.greeting import get_greeting_response, is_greeting
from orchestrator.planning.semantic_router import SemanticRouter
import os
import logging

logger = logging.getLogger(__name__)

router_llm = ChatOllama(
    model="qwen2.5:1.5b",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
    temperature=0,
    format="json"
)

erp_semantic_router = SemanticRouter()

ROUTER_PROMPT = """
You are a strict intent router for an enterprise AI system.

Your job is to determine WHERE the answer must come from — 
not what the topic is.

Classify the query into exactly ONE category based on 
the SOURCE OF TRUTH required to answer it.

------------------------------------------------------------
CATEGORY DEFINITIONS (SOURCE-BASED LOGIC)
------------------------------------------------------------

1) GREETING
Pure conversational messages.
No information retrieval or reasoning required.

Examples:
- hi
- hello
- good morning
- thanks
- how are you

------------------------------------------------------------

2) ERP  (RAG REQUIRED - INTERNAL KNOWLEDGE BASE)

Select ERP if the query requires:
- Internal company policies
- HR rules, leave policies, approvals
- IT procedures, access workflows
- Manufacturing processes
- Safety protocols
- Internal documentation
- Operational SOPs
- Organization-specific workflows
- Any answer that depends on private/internal structured data

Key principle:
If the answer depends on INTERNAL enterprise knowledge
that is NOT publicly available → ERP.

------------------------------------------------------------

3) COMPANY  (RAG REQUIRED - COMPANY KNOWLEDGE BASE)

Select COMPANY if the query requires:
- Facts about Agnikul Cosmos
- Founders, history, launches
- Vehicles, engines, technology
- Milestones or announcements
- Company-specific public information
- Organizational details specific to Agnikul

Key principle:
If the question asks about Agnikul-specific factual data
that must be retrieved from curated company sources → COMPANY.

------------------------------------------------------------

4) GENERAL  (DIRECT LLM REASONING)

Select GENERAL if the query:
- Can be answered using general world knowledge
- Involves math, coding, logic, explanation
- Is conceptual or theoretical
- Is instructional or creative
- Does NOT require company-specific retrieval
- Does NOT require system/tool execution

Key principle:
If a well-trained LLM can answer without retrieval
from enterprise or company documents → GENERAL.

------------------------------------------------------------

5) TOOLS  (EXTERNAL SEARCH OR SYSTEM ACTION REQUIRED)

Select TOOLS if the query:
- Explicitly requests web search
- Mentions wikipedia, wiki, duckduckgo, ddg
- Mentions arxiv, research paper, citation, bibtex, DOI
- Requires external lookup
- Requires system-level action or execution
- Is ambiguous and cannot be answered directly

Key principle:
If the system must call a tool or external service → TOOLS.

------------------------------------------------------------

CRITICAL ROUTING RULES

- Choose exactly ONE category.
- ERP and COMPANY always imply RAG retrieval.
- GENERAL must NOT use retrieval.
- TOOLS must involve external systems or live lookups.
- If unsure between GENERAL and ERP/COMPANY:
    → Ask: "Does this require internal/company-specific knowledge?"
      If yes → ERP or COMPANY.
      If no → GENERAL.

------------------------------------------------------------

Respond ONLY with valid JSON:

{ "intent": "GREETING" | "ERP" | "COMPANY" | "GENERAL" | "TOOLS" }

No explanations.
No additional text.

"""


# -----------------------------
# Intent → System Route Mapping
# -----------------------------
GREETING_SYSTEM_PROMPT = """
You are Axon, an internal enterprise AI assistant for Agnikul Cosmos.
Your role is to be helpful, professional, and concise.

The user has sent a greeting. Reply with a polite, welcoming message.
Do not ask follow-up questions.
Do not mention that you are an AI unless relevant.
Keep the tone warm but professional.
"""

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

    query_lower = query.lower()

    # Bypasses ERP ticket/feedback/suggestion creation checks for leave queries
    is_leave_query = any(kw in query_lower for kw in ["leave", "casual leave", "sick leave", "earned leave", "privilege leave", "time off", "holiday"])

    # Detect Lost and Found creation/reporting
    lost_create_keywords = ["lost my", "lost a", "report a lost", "record a lost", "report lost", "record lost", "lost item"]
    found_create_keywords = ["found a", "found my", "mark as found", "mark found", "mark erp lost as found"]
    
    if any(kw in query_lower for kw in lost_create_keywords) or any(kw in query_lower for kw in found_create_keywords) or ("mark " in query_lower and " as found" in query_lower):
        return "ERP_ROUTE:lost_found_create"
        
    lost_list_keywords = ["list lost", "show lost", "view lost", "lost items", "lost ones", "lost and found"]
    if any(kw in query_lower for kw in lost_list_keywords):
        return "ERP_ROUTE:lost_found_list"

    # 1. Detect ERP ticket creation by keywords
    ticket_create_keywords = [
        "raise a", "create a", "lodge a", "submit a",
        "ticket", "support ticket", "erp ticket",
        "raise support", "create support"
    ]
    if not is_leave_query and any(kw in query_lower for kw in ticket_create_keywords):
        return "ERP_ROUTE:erp_tickets_create"

    # 2. Detect feedback creation by keywords
    feedback_keywords = ["give feedback", "submit feedback", "review"]
    if not is_leave_query and any(kw in query_lower for kw in feedback_keywords):
        return "ERP_ROUTE:erp_feedback_create"

    # 3. Detect suggestion creation by keywords
    suggestion_keywords = ["suggestion", "improve", "enhancement"]
    if not is_leave_query and any(kw in query_lower for kw in suggestion_keywords):
        return "ERP_ROUTE:erp_suggestion_create"

    # 4. Detect organization/company related questions
    organization_keywords = [
        "agnikul", "cosmos", "agnibaan", "agnilet", "semi-cryo", "sorcerer", "rocket", "engine",
        "leave", "holiday", "policy", "policies", "hr", "canteen", "founder", "founded", "ceo", "payroll",
        "salary", "benefits", "employee", "employees", "allowance", "mediclaim", "insurance", "probation",
        "appraisal", "increment", "office", "work hour", "attendance", "reimbursement", "travel",
        "vehicle tracking", "fleet management", "food and beverages", "leave type", "leave balance",
        "work from home", "wfh", "dress code", "working days", "probation period", "sick leave",
        "casual leave", "maternity leave", "paternity leave", "probationary", "notice period"
    ]
    if any(kw in query_lower for kw in organization_keywords):
        return "RAG"

    # 5. Default fallback is TOOLS (which handles wiki, arxiv, and ddgs fallbacks)
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
