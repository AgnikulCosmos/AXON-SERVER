from langchain_ollama import ChatOllama
from common.safety import contains_profanity
from common.greeting import is_greeting
from orchestrator.planning.semantic_router import SemanticRouter
import json
import re

router_llm = ChatOllama(
    model="qwen2.5:3b",
    base_url="http://ollama:11434",
    temperature=0
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
        # print("ROUTE DECIDED: PROFANITY")
        return "PROFANITY"
    
    # Check greeting before LLM router (saves an LLM call to the router, but calls LLM for generation)
    if is_greeting(query):
        # Generate dynamic greeting using Qwen
        # print("ROUTE DECIDED: GREETING (Generating response)")
        response_text = await generate_greeting_response(query)
        return f"GREETING_RESPONSE:{response_text}"

    resp = await router_llm.ainvoke(
        ROUTER_PROMPT + "\nQuery: " + query
    )

    try:
        match = re.search(r"\{.*\}", resp.content, re.S)
        if not match:
            # print("ROUTE DECIDED: TOOLS (no JSON)")
            return "TOOLS"

        data = json.loads(match.group())
        intent = data.get("intent", "GENERAL")

        route = INTENT_TO_ROUTE.get(intent, "TOOLS")

        # -------------------------
        # ERP → Semantic Route Match
        # -------------------------
        if route == "ERP":  # ERP or COMPANY both map to RAG
            erp_match = erp_semantic_router.match(query)

            if erp_match:
                route_name = erp_match["route"]["route_name"]
                return f"ERP_ROUTE:{route_name}"

            # If no semantic match, fallback to normal RAG
            return "RAG"

        return route

    except Exception:
        # print("ROUTE DECIDED: TOOLS (exception)")
        return "TOOLS"
