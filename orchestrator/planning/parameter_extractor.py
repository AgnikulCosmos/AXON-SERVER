# orchestrator/planning/parameter_extractor.py

"""
Parameter Extractor
-------------------
Extracts structured parameters from a user query based on the matched route's
parameter schema.  Uses the Qwen LLM for intelligent extraction, with a
deterministic fallback that performs keyword matching against known enum values.

Improvements:
  • Task 3: Updated LLM prompt to support temporal expressions
  • Task 4: Extended fallback keyword detection for temporal ranges
  • Task 7: Configurable Ollama URL
"""

import json
import os
import re
import logging
from langchain_ollama import ChatOllama

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Task 7: Configurable Ollama URL ─────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── LLM for parameter extraction ────────────────────────────────────────────
_extractor_llm = ChatOllama(
    model="qwen2.5:0.5b",
    base_url=OLLAMA_URL,
    temperature=0,
    streaming=False,
)

# ── Task 3: Improved extraction prompt with temporal understanding ──────────
_EXTRACT_PROMPT = """\
You are a strict parameter extractor for an enterprise ERP system.

Given a user query and a parameter schema, extract ONLY the parameters
that are clearly present in the query.

Rules:
- Only extract parameters defined in the schema.
- If a parameter has an enum list, the extracted value MUST be one of those options.
- If a parameter has a type like "string", "date", "number", "datetime", "boolean",
  extract the raw value the user mentioned.
- For dates, return one of the following keywords if mentioned:
    today, yesterday, tomorrow,
    this week, last week,
    this month, last month,
    this year, last year
  Or return an ISO date (YYYY-MM-DD) if a specific date is mentioned.
- For booleans, return true or false.
- If a parameter is NOT mentioned in the query, do NOT include it.
- Return valid JSON only. No explanation.

Parameter Schema:
{schema}

User Query:
{query}

Respond ONLY with a JSON object of extracted parameters.
Example: {{"meal": "lunch", "date": "today"}}
If nothing can be extracted, respond with: {{}}
"""


def extract_parameters(query: str, route_config: dict) -> dict:
    """
    Extract parameters from *query* using *route_config*["parameters"] as
    the schema.

    Strategy:
        1. Try LLM extraction (accurate for complex queries).
        2. Fall back to deterministic keyword matching.
    """
    params_schema = route_config.get("parameters", {})
    if not params_schema:
        return {}

    extracted_params: dict = {}

    # ── 1. LLM extraction ───────────────────────────────────────────────
    try:
        extracted = _llm_extract(query, params_schema)
        if extracted:
            extracted_params = _normalise(extracted, params_schema)
            logger.debug("LLM extraction result: %s", extracted_params)
    except Exception as exc:
        logger.warning("LLM parameter extraction failed: %s — using fallback", exc)

    # ── 2. Deterministic fallback ────────────────────────────────────────
    fallback = _keyword_extract(query, params_schema)
    fallback.update(_erp_support_extract(query, route_config, params_schema))

    for key, value in fallback.items():
        extracted_params.setdefault(key, value)

    logger.debug("Merged extraction result: %s", extracted_params)
    return extracted_params


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════════

def _llm_extract(query: str, schema: dict) -> dict:
    """Call LLM to extract parameters."""
    prompt = _EXTRACT_PROMPT.format(
        schema=json.dumps(schema, indent=2),
        query=query,
    )
    resp = _extractor_llm.invoke(prompt)
    text = resp.content.strip()

    # Parse the JSON from the response
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    return json.loads(match.group())


# ── Task 4: Extended temporal keywords for fallback ─────────────────────────
_TEMPORAL_KEYWORDS = [
    # Multi-word keywords first (order matters for substring matching)
    "last week",
    "this week",
    "last month",
    "this month",
    "last year",
    "this year",
    # Single-word keywords
    "today",
    "yesterday",
    "tomorrow",
]


def _keyword_extract(query: str, schema: dict) -> dict:
    """
    Deterministic fallback: scan the query for enum values, date keywords,
    and temporal range expressions.
    """
    q_lower = query.lower()
    extracted: dict = {}

    for param, ptype in schema.items():
        # ── Enum list ────────────────────────────────────────────────────
        if isinstance(ptype, list):
            for option in ptype:
                if option.lower() in q_lower:
                    extracted[param] = option
                    break
        # ── Date ─────────────────────────────────────────────────────────
        elif ptype == "date":
            for kw in _TEMPORAL_KEYWORDS:
                if kw in q_lower:
                    extracted[param] = kw
                    break
            # Try ISO-date pattern
            if param not in extracted:
                iso = re.search(r"\d{4}-\d{2}-\d{2}", query)
                if iso:
                    extracted[param] = iso.group()
        # ── Datetime ─────────────────────────────────────────────────────
        elif ptype == "datetime":
            iso_dt = re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", query)
            if iso_dt:
                extracted[param] = iso_dt.group()
        # ── Boolean ──────────────────────────────────────────────────────
        elif ptype == "boolean":
            param_readable = param.replace("_", " ")
            if param_readable in q_lower:
                extracted[param] = True
        # ── String / number — skip in keyword mode (too ambiguous) ──────
        # String/number values are best left to LLM extraction

    return extracted


def _erp_support_extract(query: str, route_config: dict, schema: dict) -> dict:
    route_name = route_config.get("route_name", "")
    if not route_name.startswith("erp_"):
        return {}

    extracted: dict = {}

    if "priority" in schema:
        priority_options = schema["priority"]
        if isinstance(priority_options, list):
            for option in priority_options:
                if re.search(rf"\b{re.escape(option)}\b", query, re.I):
                    extracted["priority"] = option
                    break

    if "ratings" in schema:
        rating = re.search(r"\bratings?\s*[:=]?\s*([1-5](?:\.\d+)?)\b", query, re.I)
        if rating:
            extracted["ratings"] = float(rating.group(1))

    string_patterns = {
        "app_name": [
            r"\bapp(?:lication)?\s*[:=]?\s*([A-Za-z0-9_& .-]+?)(?=,|\s+module\b|\s+priority\b|\s+with\b|\s+feedback\b|\s+description\b|$)",
            r"\bfor\s+app(?:lication)?\s+([A-Za-z0-9_& .-]+?)(?=,|\s+module\b|\s+priority\b|\s+with\b|\s+feedback\b|\s+description\b|$)",
        ],
        "module": [
            r"\bmodule\s*[:=]?\s*([A-Za-z0-9_& .-]+?)(?=,|\s+priority\b|\s+description\b|\s+issue\b|$)",
        ],
        "description": [
            r"\bdescription\s*[:=]\s*(.+)$",
            r"\bissue\s*[:=]\s*(.+)$",
        ],
        "feedback": [
            r"\bfeedback\s*[:=]\s*(.+?)(?=\s+\bhelps\b|\s+\bratings?\b|$)",
            r"\bsaying\s+(.+?)(?=\s+\bhelps\b|\s+\bratings?\b|$)",
        ],
        "helps": [
            r"\bhelps\s*[:=]\s*(.+)$",
            r"\bhelps\s+(.+)$",
        ],
        "attachments": [
            r"\battachments?\s*[:=]\s*(.+)$",
        ],
        "roles": [
            r"\broles\s*[:=]\s*(.+?)(?=,?\s+\bdescription\b|$)",
        ],
    }

    for field, patterns in string_patterns.items():
        if field not in schema or field in extracted:
            continue
        for pattern in patterns:
            match = re.search(pattern, query, re.I)
            if match:
                value = _clean_extracted_text(match.group(1))
                if value:
                    extracted[field] = value
                    break

    return extracted


def _clean_extracted_text(value: str) -> str:
    return value.strip().strip(",.; ")


def _normalise(extracted: dict, schema: dict) -> dict:
    """
    Validate extracted values against the schema and normalise to lowercase.
    """
    cleaned: dict = {}
    for key, value in extracted.items():
        if key not in schema:
            continue  # hallucinated parameter

        ptype = schema[key]

        if isinstance(ptype, list):
            # Must be one of the enum options
            val_lower = str(value).lower()
            for option in ptype:
                if val_lower == option.lower():
                    cleaned[key] = option
                    break
        elif ptype == "boolean":
            cleaned[key] = bool(value)
        elif ptype == "number":
            try:
                cleaned[key] = float(value)
            except (ValueError, TypeError):
                pass
        else:
            # string / date / datetime — keep user-provided casing for DocType values.
            cleaned[key] = str(value).strip() if value else None
            if cleaned[key] is None:
                del cleaned[key]

    return cleaned
