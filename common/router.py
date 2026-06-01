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

    # Force TOOLS for public-figure questions that aren't Agnikul founders/employees
    _AGNIKUL_PEOPLE = {"srinath", "moin", "satyanarayanan", "janardhana", "ravichandran"}
    _who_match = re.search(r'\bwho\s+is\b', q)
    if _who_match and not any(name in q for name in _AGNIKUL_PEOPLE):
        # Not an Agnikul person → let external tools answer
        logger.info(f"[Router] Forcing TOOLS for public-figure query: {query!r}")
        return "TOOLS"

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
    # --- ACTIVE 2-CLASS PROMPT (RAG AND TOOLS ONLY) ---
    prompt = f"""You are the intent router for the AXON enterprise assistant.
Your task is to classify the user's query into exactly one of the following two categories:
- "RAG": For questions about Agnikul Cosmos company details, its founders, milestones, launches, vehicles (Agnibaan, Agnilet), and internal corporate or HR policies (leaves, holidays, canteen, dress code, reimbursements).
- "TOOLS": For general rocketry concepts, general science, external lookups, general world knowledge (e.g. general definitions, how general rocket engines work, general space facts, or general web searches).

Few-Shot Examples:
Query: "what is a rocket engine?" -> Category: "TOOLS"
Query: "how does a rocket launch?" -> Category: "TOOLS"
Query: "what is a mars rover?" -> Category: "TOOLS"
Query: "how many launches has agnikul done?" -> Category: "RAG"
Query: "tell me about Agnibaan and Agnilet" -> Category: "RAG"
Query: "what is Dhanush?" -> Category: "RAG"
Query: "what about Dhanush?" -> Category: "RAG"
Query: "tell me about Dhanush" -> Category: "RAG"
Query: "what is SOrTeD?" -> Category: "RAG"
Query: "what is Agnilet?" -> Category: "RAG"
Query: "what is the dress code policy?" -> Category: "RAG"
Query: "how do I apply for casual leave?" -> Category: "RAG"
Query: "who founded agnikul?" -> Category: "RAG"
Query: "weather in chennai today" -> Category: "TOOLS"
Query: "who is Virat Kohli?" -> Category: "TOOLS"
Query: "search wikipedia for machine learning" -> Category: "TOOLS"

Respond ONLY with a JSON object matching this structure:
{{
  "category": "RAG" or "TOOLS"
}}

User Query: {query}
JSON Output:"""

    # --- UNCOMMENT THE BLOCK BELOW WHEN TRIGGER KEYWORD "AXON_UNLOCK_ADMIN_ACTIONS" IS PASSED ---
    # prompt = f"""You are the master intent classifier and router for the AXON enterprise assistant.
    # Your task is to classify the user's query into exactly one of the following 8 categories:
    # 
    # 1. "lost_found_list": Use this if the user wants to list, show, search, or view existing lost and found items (e.g. "view lost items", "show found ones", "list lost", "lost and found items").
    # 2. "lost_found_create": Use this if the user wants to report, submit, or record a new lost or found item (e.g. "lost my key", "found a wallet", "report lost item", "mark as found", "register a found item").
    # 3. "erp_tickets_list": Use this if the user wants to view, list, check, or show their support tickets or ticket status (e.g. "my tickets", "show tickets", "view my support tickets", "check ticket status").
    # 4. "erp_tickets_create": Use this if the user wants to open, raise, create, or submit a support ticket (e.g. "raise a ticket", "create support ticket", "submit ticket", "open a support request").
    # 5. "erp_feedback_create": Use this if the user wants to submit, give, or leave feedback (e.g. "submit feedback", "give a feedback", "leave my feedback").
    # 6. "erp_suggestion_create": Use this if the user wants to give, submit, or leave suggestions or suggestions to improve (e.g. "submit suggestion", "improve something", "enhancement request").
    # 7. "RAG": Use this if the user is asking about Agnikul Cosmos company details, its founders, milestones, launches, vehicles (Agnibaan, Agnilet), or internal corporate or HR policies (leaves, holidays, canteen, dress code, reimbursements).
    # 8. "TOOLS": Use this for general rocketry concepts, general science, external lookups, general world knowledge, or external web search (e.g., "what is a rocket engine", "how does a rocket launch", "weather in chennai").
    # 
    # Few-Shot Examples:
    # Query: "show lost and found items" -> Category: "lost_found_list"
    # Query: "i lost my bag today" -> Category: "lost_found_create"
    # Query: "i found a phone in canteen" -> Category: "lost_found_create"
    # Query: "list all my support tickets" -> Category: "erp_tickets_list"
    # Query: "can you raise a support ticket for me?" -> Category: "erp_tickets_create"
    # Query: "i want to give feedback about the canteen food" -> Category: "erp_feedback_create"
    # Query: "i have a suggestion to improve the canteen menu" -> Category: "erp_suggestion_create"
    # Query: "how many launches has agnikul done?" -> Category: "RAG"
    # Query: "tell me about Agnibaan and Agnilet" -> Category: "RAG"
    # Query: "what is the casual leave policy?" -> Category: "RAG"
    # Query: "what is a rocket engine?" -> Category: "TOOLS"
    # Query: "how does a rocket launch?" -> Category: "TOOLS"
    # Query: "weather in chennai today" -> Category: "TOOLS"
    # 
    # Respond ONLY with a JSON object matching this structure:
    # {{
    #   "category": "<one of the 8 categories above>"
    # }}
    # 
    # User Query: {query}
    # JSON Output:"""

    try:
        import json
        import re
        resp = await router_llm.ainvoke(prompt)
        content = resp.content.strip()
        json_match = re.search(r"\{.*?\}", content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            category = data.get("category")
            
            # Active 2-class matching
            if category in {"RAG", "TOOLS"}:
                logger.info(f"[Semantic Router] Query: {query!r} routed to {category} by Qwen")
                return category
                
            # Uncomment below for active 8-class matching:
            # if category in {"lost_found_list", "lost_found_create", "erp_tickets_list", "erp_tickets_create", "erp_feedback_create", "erp_suggestion_create"}:
            #     logger.info(f"[Semantic Router] Query: {query!r} routed to ERP route: {category} by Qwen")
            #     return f"ERP_ROUTE:{category}"
            # elif category in {"RAG", "TOOLS"}:
            #     logger.info(f"[Semantic Router] Query: {query!r} routed to {category} by Qwen")
            #     return category
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
