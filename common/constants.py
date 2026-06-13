import os

LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:0.5b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

AGNIKUL_PEOPLE = {
    "srinath", "moin", "satyanarayanan", "janardhana",
    "ravichandran", "spm", "raju", "chakravarthy",
}

FOUNDERS = {"srinath", "moin", "satyanarayanan", "janardhana", "ravichandran", "spm"}

KNOWN_ENTITIES = {
    "agnikul", "cosmos", "agnibaan", "agnilet", "dhanush", "sorted",
    "launchpad", "sdsc", "shar", "isro", "axon", "erp",
} | AGNIKUL_PEOPLE

ACTION_VERBS = [
    "send", "mail", "email", "post", "tweet", "slack", "schedule",
    "delete", "remove", "download", "install", "execute", "run",
    "book", "reserve", "order",
]

ALLOWED_ACTION_CONTEXTS = ["lost", "found", "food", "log", "ticket", "feedback", "suggestion", "track", "tracking"]

RAG_TERMS = {
    "agnikul", "cosmos", "agnibaan", "agnilet", "dhanush", "sorted",
    "launchpad", "sdsc", "shar", "isro", "axon", "erp",
    "srinath", "moin", "satyanarayanan", "janardhana", "ravichandran",
    "spm", "raju", "chakravarthy",
    "founder", "co-founder", "cofounder", "ceo", "coo", "professor",
    "leave", "leaves", "holiday", "holidays", "sick", "casual",
    "maternity", "paternity", "bereavement", "marriage", "festival",
    "medical", "attendance", "timesheet", "shift", "shifts",
    "overtime", "check-in", "checkout", "absent",
    "food", "canteen", "cafeteria", "meal", "meals", "breakfast",
    "lunch", "dinner", "beverage", "beverages", "menu", "booking",
    "qr code", "consumption", "caterer", "catering", "dining",
    "fleet", "ride", "rides", "commute", "driver", "cabs", "cab",
    "taxi", "passenger", "vehicle", "vehicles", "transport",
    "expense", "expenses", "budget", "reimbursement", "reimbursements",
    "claims", "claim", "bill", "bills", "appraisal", "appraisals",
    "payroll", "salary", "salary slips", "bonus", "tax",
    "tds", "insurance", "wellness",
    "cad", "dfr", "manufacturing", "argon", "helium", "nitrogen",
    "gas", "rig", "rigs", "propulsion", "combustion", "instrumentation",
    "resource", "resources", "bom", "quality", "safety",
    "ticket", "tickets", "feedback", "reviews", "review",
    "suggestion", "suggestions", "recruitment",
    "hiring", "interview", "interviewer", "candidate", "candidates",
    "visitor", "visitors",
    "policy", "policies", "guideline", "guidelines", "handbook",
    "rules", "rule",
}

ERP_KEYWORDS = {
    "ticket", "tickets", "feedback", "suggestion", "suggestions",
    "lost", "found", "track", "status", "details", "food log",
    "food logs", "meal log", "meal logs", "booking", "bookings",
    "pc-", "mm-", "mt-", "dl-", "erp_i_",
    "food", "canteen", "meal", "meals", "issue", "bug", "error",
    "lag", "slow", "crash", "fail", "problem", "report",
    "breakfast", "lunch", "dinner",
    "leave balance", "leave balances", "leaves left", "leaves remaining",
    "casual leave", "casual leaves", "sick leave", "sick leaves",
    "leave tracker", "leaves taken",
}

POLICY_KEYWORDS = {"policy", "policies", "guideline", "guidelines", "rules", "rule", "handbook"}
POLICY_DOMAINS = {"leave", "leaves", "food", "canteen", "cafeteria", "meal", "meals", "breakfast", "lunch", "dinner", "beverage", "beverages", "menu", "catering"}

MODEL_KEYWORDS = {
    "base model", "model are you", "llm are you", "model you are using",
    "llm you are using", "what model", "which model", "which llm", "what llm",
    "model is this", "model you use", "llm you use", "based on which", "based on what",
    "are you based on", "are you llama", "are you qwen", "are you gpt", "are you claude",
    "are you gemini", "are you deepseek", "are you using llama", "are you using qwen",
    "are you using gpt", "are you using deepseek", "are you using gemini", "are you using claude",
}

SIMPLE_GREETINGS = {"hi", "hello", "hey", "hii", "hola", "hiya", "yo", "sup", "greetings"}

PROFANITY_FALLBACK = (
    "Please use respectful and professional language while interacting with Axon."
)
