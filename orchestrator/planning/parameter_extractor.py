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

    # ── 1. LLM extraction ───────────────────────────────────────────────
    try:
        extracted = _llm_extract(query, params_schema)
        if extracted:
            normalised = _normalise(extracted, params_schema)
            logger.debug("LLM extraction result: %s", normalised)
            return normalised
    except Exception as exc:
        logger.warning("LLM parameter extraction failed: %s — using fallback", exc)

    # ── 2. Deterministic fallback ────────────────────────────────────────
    fallback = _keyword_extract(query, params_schema)
    logger.debug("Fallback extraction result: %s", fallback)
    return fallback


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
                    extracted[param] = option.lower()
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
            if val_lower in [o.lower() for o in ptype]:
                cleaned[key] = val_lower
        elif ptype == "boolean":
            cleaned[key] = bool(value)
        elif ptype == "number":
            try:
                cleaned[key] = float(value)
            except (ValueError, TypeError):
                pass
        else:
            # string / date / datetime — keep as-is, lowercased
            cleaned[key] = str(value).strip().lower() if value else None
            if cleaned[key] is None:
                del cleaned[key]

    return cleaned
