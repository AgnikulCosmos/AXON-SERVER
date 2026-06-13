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

{{ "intent": "GREETING" | "ERP" | "COMPANY" | "GENERAL" | "TOOLS" }}

No explanations.
No additional text.

"""


GREETING_SYSTEM_PROMPT = """
You are Axon, an internal enterprise AI assistant for Agnikul Cosmos.
Your role is to be helpful, professional, and concise.

The user has sent a greeting. Reply with a polite, welcoming message.
Do not ask follow-up questions.
Do not mention that you are an AI unless relevant.
Keep the tone warm but professional.
"""


CLASSIFICATION_PROMPT = """You are the master intent classifier and router for the AXON enterprise assistant.
Your task is to classify the user's query into exactly one of the following 11 categories:

1. "lost_found_list": Use this if the user wants to list, show, search, or view existing lost and found items (e.g. "view lost items", "show found ones", "list lost", "lost and found items").
2. "lost_found_create": Use this if the user wants to report, submit, or record a new lost or found item (e.g. "lost my key", "found a wallet", "report lost item", "mark as found", "register a found item").
3. "erp_tickets_list": Use this if the user wants to view, list, check, or show their support tickets or ticket status (e.g. "my tickets", "show tickets", "view my support tickets", "check ticket status").
4. "erp_tickets_create": Use this if the user wants to open, raise, create, or submit a support ticket (e.g. "raise a ticket", "create support ticket", "submit ticket", "open a support request").
5. "erp_feedback_create": Use this if the user wants to submit, give, or leave feedback (e.g. "submit feedback", "give a feedback", "leave my feedback").
6. "erp_suggestion_create": Use this if the user wants to give, submit, or leave suggestions or suggestions to improve (e.g. "submit suggestion", "improve something", "enhancement request").
7. "track_request": Use this if the user wants to track status, check request details, or look up any ticket, request, record, manual, or FAQ by a prefix ID like PC-, MM-, MT-, DL-, ERP_I_, ERP-SF-, FBSG-, SUG-, ERP-RU-, ERP-FAQ-, or ERP-M- (e.g. "track request PC-2026-0001", "status of MM-2026-0003", "check ticket ERP_I_9876", "view details of my request PC-06-26-1024").
8. "food_log_list": Use this if the user wants to list, view, or check food/meal booking logs, canteen log history, or meal requests for themselves or a team (e.g. "show my food log", "what did I book for lunch today?", "check my canteen food bookings for this week", "list my meal requests from yesterday to today").
9. "pr_leave_tracker": Use this if the user wants to check their leave balances, how many leaves they have left, how many leaves they have taken, or see their leave tracker summary (e.g. "show my leave balance", "how many casual leaves do I have left", "check my sick leave balance", "available casual and sick leaves", "what is my casual leave balance").
10. "RAG": Use this if the user is asking about Agnikul Cosmos company details, its founders, milestones, launches, vehicles (Agnibaan, Agnilet), or internal corporate or HR policies (leaves, holidays, canteen menu, dress code, reimbursements).
11. "TOOLS": Use this for general rocketry concepts, general science, external lookups, general world knowledge, or external web search (e.g., "what is a rocket engine", "how does a rocket launch", "weather in chennai").

Few-Shot Examples:
Query: "show lost and found items" -> Category: "lost_found_list"
Query: "i lost my bag today" -> Category: "lost_found_create"
Query: "i found a phone in canteen" -> Category: "lost_found_create"
Query: "list all my support tickets" -> Category: "erp_tickets_list"
Query: "can you raise a support ticket for me?" -> Category: "erp_tickets_create"
Query: "I am facing a loading lag issue in Fleet Management." -> Category: "erp_tickets_create"
Query: "report an issue with the payroll app" -> Category: "erp_tickets_create"
Query: "i want to give feedback about the canteen food" -> Category: "erp_feedback_create"
Query: "i have a suggestion to improve the canteen menu" -> Category: "erp_suggestion_create"
Query: "track request PC-2026-0001" -> Category: "track_request"
Query: "what is the status of MT-2026-0005?" -> Category: "track_request"
Query: "show my food log" -> Category: "food_log_list"
Query: "check my meal bookings for this week" -> Category: "food_log_list"
Query: "show my leave balance" -> Category: "pr_leave_tracker"
Query: "how many casual leaves do I have left" -> Category: "pr_leave_tracker"
Query: "check my sick leave balance" -> Category: "pr_leave_tracker"
Query: "how many launches has agnikul done?" -> Category: "RAG"
Query: "tell me about Agnibaan and Agnilet" -> Category: "RAG"
Query: "what is the casual leave policy?" -> Category: "RAG"
Query: "what is a rocket engine?" -> Category: "TOOLS"
Query: "how does a rocket launch?" -> Category: "TOOLS"
Query: "weather in chennai today" -> Category: "TOOLS"

Respond ONLY with a JSON object matching this structure:
{{
  "category": "<one of the 11 categories above>"
}}

User Query: {query}
JSON Output:"""


PARAMETER_EXTRACTION_PROMPT = """You are a strict parameter extractor for an enterprise ERP system.

Given a user query and a parameter schema, extract ONLY the parameters that are clearly and explicitly present in the query.

Rules:
- Only extract parameters defined in the schema.
- If a parameter has an enum list, the extracted value MUST be one of those options.
- If a parameter has a type like "string", "date", "number", "datetime", "boolean", extract the value the user mentioned.
- For dates, return one of the following keywords if mentioned: today, yesterday, tomorrow, this week, last week, this month, last month, this year, last year. Or return an ISO date (YYYY-MM-DD) if a specific date is mentioned.
- For booleans, return true or false.
- If a parameter is NOT mentioned in the query, do NOT include it in the JSON.
- CRITICAL: Do NOT extract generic intent-triggering phrases or command verbs (e.g. "I want to create a ticket", "raise a support ticket", "submit suggestion") as the "description" or "feedback" parameters. These are triggers, not actual descriptions or feedback content. Leave them out of the JSON if no real issue description is given.
- CRITICAL: Do NOT extract generic nouns like "support" as the "app_name" parameter unless the user explicitly names the application (e.g. "app_name: erp_support" or "for erp_support app").
- Return valid JSON only. No explanation, no comments, no markdown formatting.

Few-Shot Examples:

Example 1:
Query: "I lost my blue access card in the cafeteria today"
Schema:
{{
  "item_name": "string",
  "lost_location": "string",
  "lost_date": "date",
  "lost_description": "string"
}}
Output:
{{
  "item_name": "Access Card",
  "lost_location": "cafeteria",
  "lost_date": "today",
  "lost_description": "blue access card"
}}

Example 2:
Query: "I need to create a support ticket"
Schema:
{{
  "app_name": ["Food and Beverages", "ERP Support", "Fleet Management"],
  "priority": ["Low", "Medium", "High"],
  "description": "string"
}}
Output:
{{}}

Example 3:
Query: "Adding a night-mode theme in Fleet management would significantly reduce eye strain."
Schema:
{{
  "app_name": ["Food and Beverages", "ERP Support", "Fleet Management"],
  "feedback": "string",
  "helps": "string"
}}
Output:
{{
  "app_name": "Fleet Management",
  "feedback": "Adding a night-mode theme",
  "helps": "significantly reduce eye strain"
}}

Example 4:
Query: "I am facing a loading lag issue in Fleet Management."
Schema:
{{
  "app_name": ["Food and Beverages", "ERP Support", "Fleet Management"],
  "priority": ["Low", "Medium", "High"],
  "description": "string"
}}
Output:
{{
  "app_name": "Fleet Management",
  "description": "loading lag issue"
}}

Now perform the extraction:
Schema:
{schema}

User Query:
{query}

Respond ONLY with the JSON object of extracted parameters:
"""


CONFIRM_ROUTE_PROMPT = """Task: Determine if the User Message matches the intent of the Action Description.

Action Description: {route_desc}
User Message: "{query}"

Rules:
- Select 1 (Yes) if the User Message matches the specific intent (creating, listing, viewing, checking, or performing) described in the Action Description.
- Select 2 (No) if the User Message is a greeting, general chat, asking about your identity/capabilities, asking a public world knowledge question, or completely unrelated to the Action Description.

Examples:
- Action Description: Report a lost item or found item.
  User Message: "I lost my keys" -> Answer: 1
- Action Description: Report a lost item or found item.
  User Message: "hello there" -> Answer: 2
- Action Description: View details of a ticket by ID.
  User Message: "track ERP_I_72" -> Answer: 1

Answer with only the number 1 or 2:"""


DISAMBIGUATE_ROUTE_PROMPT = """Task: Decide if the user query is asking to "create" a new entry or "view" existing entries.

Category: {category}

Rules for "create":
- The user wants to submit, raise, report, create, add, open, file, register, or write a NEW item/ticket/feedback/suggestion.
- Examples: "I lost my wallet", "Submit a feedback", "I want to raise a ticket", "report a bug", "create a suggestion", "give feedback".

Rules for "view":
- The user wants to show, check, list, view, read, search, or see EXISTING items/tickets/feedback/suggestions.
- Examples: "list lost and found", "show my tickets", "view feedback list", "check my suggestions".

Query: "{query}"

Output exactly one word: "create" or "view". Do not include any other text, reasoning, or punctuation.

Answer:"""

