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
# Cache holder for valid app names from Frappe
_VALID_APP_NAMES_CACHE = None

# Add this function to fetch valid app names from Frappe
def _get_valid_app_names_from_frappe() -> list:
    """Fetch valid app names from Frappe with caching."""
    global _VALID_APP_NAMES_CACHE

    if _VALID_APP_NAMES_CACHE is not None:
        return _VALID_APP_NAMES_CACHE

    
    try:
        from orchestrator.mcp_registry import list_erp_apps
        response = list_erp_apps(limit=200)
        data = response.get("message", response) if isinstance(response, dict) else {}
        
        if isinstance(data, dict):
            records = data.get("data", [])
            if isinstance(records, list):
                _VALID_APP_NAMES_CACHE = [str(r.get("name", "")).strip() for r in records if r.get("name")]
                return _VALID_APP_NAMES_CACHE
    except Exception as e:
        logging.warning(f"Failed to fetch app names from Frappe: {e}")
    
    # Fallback: use whatever is present in the site config / no app-name validation.
    # Returning an empty list ensures we don't raise at import-time.
    _VALID_APP_NAMES_CACHE = []
    return _VALID_APP_NAMES_CACHE



# Update the APP_NAME_MAPPING to use dynamic values
def _build_app_name_mapping():
    """Build app name mapping from Frappe's actual data."""
    valid_names = _get_valid_app_names_from_frappe()

    if valid_names:
        mapping = {}
        for name in valid_names:
            aliases = [
                name.lower(),
                name.lower().replace(" ", ""),
                name.lower().replace("&", "and"),
                name.lower().replace("management", "mgmt"),
            ]
            if "management" in name.lower():
                base = name.lower().replace(" management", "")
                aliases.append(base)
            mapping[name] = list(set(aliases))
        return mapping

    # Fallback: hardcoded mapping with correct app_name values
    return {
        "core": ["core", "core erp", "agnikul core", "agnikul core erp"],
        "erp_support": ["erp_support", "erp support", "support", "erp"],
        "fleet_management": ["fleet_management", "fleet management", "fleet", "fleet mgmt"],
        "food": ["food", "food booking", "food and beverages", "food & beverages", "canteen", "meals"],
        "hr_operations": ["hr_operations", "hr operations", "hr", "human resources", "hr ops"],
        "maintenance_management": ["maintenance_management", "maintenance management", "maintenance", "maintenance mgmt"],
        "packaging_management": ["packaging_management", "packaging management", "packaging", "packaging mgmt"],
    }


# Then use this dynamic mapping instead of the static one
APP_NAME_MAPPING = _build_app_name_mapping()

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
            # Strip JSON-schema placeholder values that small LLMs echo verbatim
            # (e.g. qwen2.5:0.5b returns "string()" when it cannot extract a real value).
            extracted_params = {
                k: v for k, v in extracted_params.items()
                if not _is_schema_placeholder(v)
            }
            logger.debug("LLM extraction result (after placeholder strip): %s", extracted_params)
    except Exception as exc:
        logger.warning("LLM parameter extraction failed: %s — using fallback", exc)

    # ── 2. Deterministic fallback ────────────────────────────────────────
    fallback = _keyword_extract(query, params_schema)
    fallback.update(_erp_support_extract(query, route_config, params_schema))

    for key, value in fallback.items():
        # Deterministic fallback (especially regex/enums) is much more accurate
        # than small LLM extraction, so we override the LLM if a fallback matched.
        extracted_params[key] = value

    # Qwen 0.5b often hallucinates the `app_name` into `module` when it's absent.
    # We must do this check AFTER fallback merge, in case LLM only extracted module.
    if extracted_params.get("module") and extracted_params.get("app_name"):
        if str(extracted_params["module"]).lower() == str(extracted_params["app_name"]).lower():
            del extracted_params["module"]

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
        elif param == "name":
            lf_name = re.search(r"\b(LF-\d{2}-\d{4}-\d{4,6})\b", query, re.I)
            if lf_name:
                extracted[param] = lf_name.group(1).upper()

    return extracted


# Legacy hardcoded fallback mapping removed.
# AXON-SERVER now builds APP_NAME_MAPPING dynamically from Frappe installed apps
# (via list_erp_apps). This prevents validation failures due to mismatched
# canonical ERP app names.

# ── Priority alias mapping ──────────────────────────────────────────────────
# Users naturally say "High", "Medium", "Low" etc. but the ticket schema uses
# P0–P3.  This mapping bridges the gap.  The *first match wins*, so order
# matters ("critical" before "high" because both map differently).
_PRIORITY_ALIAS_MAP = {
    # Natural language → P-level (for ticket schema P0/P1/P2/P3)
    "critical": "P0",
    "urgent":   "P0",
    "high":     "P1",
    "medium":   "P2",
    "moderate":  "P2",
    "low":      "P3",
    "minor":    "P3",
}


def _erp_support_extract(query: str, route_config: dict, schema: dict) -> dict:

    route_name = route_config.get("route_name", "")
    if not route_name.startswith("erp_"):
        return {}

    extracted: dict = {}

    if "priority" in schema:
        priority_options = schema["priority"]
        if isinstance(priority_options, list):
            # 1. Try exact enum match first (e.g. "P0", "P1", "High", "Low")
            for option in priority_options:
                if re.search(rf"\b{re.escape(option)}\b", query, re.I):
                    extracted["priority"] = option
                    break

            # 2. Fallback: map natural-language aliases to enum values
            if "priority" not in extracted:
                q_lower = query.lower()
                for alias, mapped_value in _PRIORITY_ALIAS_MAP.items():
                    if re.search(rf"\b{re.escape(alias)}\b", q_lower):
                        # Only apply if the mapped value exists in the schema enum
                        if mapped_value in priority_options:
                            extracted["priority"] = mapped_value
                            break

    if "ratings" in schema:
        rating = re.search(r"\bratings?\s*[:=]?\s*([1-5](?:\.\d+)?)\b", query, re.I)
        if rating:
            extracted["ratings"] = float(rating.group(1))

    # ── 1. First, try to extract app_name using explicit string patterns ──
    explicit_app_name = None
    if "app_name" in schema:
        for pattern in [
            r"\bfor\s+([A-Za-z0-9_& .-]+?)\s+app(?:lication)?\b",
            r"\bapp(?:lication)?\s*[:=]?\s*([A-Za-z0-9_& .-]+?)(?=,|\s+module\b|\s+priority\b|\s+with\b|\s+feedback\b|\s+description\b|$)",
            r"\bfor\s+(?:app(?:lication)?\s+)?([A-Za-z0-9_& .-]+?)(?=,|\s+module\b|\s+priority\b|\s+with\b|\s+feedback\b|\s+description\b|$)",
        ]:
            match = re.search(pattern, query, re.I)
            if match:
                val = _clean_extracted_text(match.group(1))
                if val:
                    # Clean trailing 'app' or 'application' suffixes if captured
                    val = re.sub(r'\s+app(?:lication)?$', '', val, flags=re.I).strip()
                    explicit_app_name = val
                    break

        if explicit_app_name:
            # Map explicit_app_name to its canonical name if it matches an alias
            cand_lower = explicit_app_name.strip().lower()
            mapped = False
            for canonical, aliases in APP_NAME_MAPPING.items():
                if cand_lower == canonical.lower() or any(cand_lower == alias.lower() for alias in aliases):
                    extracted["app_name"] = canonical
                    mapped = True
                    break
            if not mapped:
                extracted["app_name"] = explicit_app_name

    # ── 2. Fallback: scan whole query for aliases if no explicit app name was extracted ──
    if "app_name" in schema and "app_name" not in extracted:
        q_lower = query.lower()
        app_aliases = []
        for canonical, aliases in APP_NAME_MAPPING.items():
            for alias in aliases:
                app_aliases.append((alias, canonical))
        app_aliases.sort(key=lambda x: len(x[0]), reverse=True)

        for alias, canonical in app_aliases:
            pattern = rf"(?:^|(?<=\W)){re.escape(alias)}(?=\W|$)"
            match = re.search(pattern, q_lower)
            if match:
                # Avoid matching the app name if it is actually specifying a module
                preceding_text = q_lower[:match.start()].strip()
                if preceding_text.endswith("module") or preceding_text.endswith("module:") or preceding_text.endswith("module =") or preceding_text.endswith("modules"):
                    continue
                extracted["app_name"] = canonical
                break

    string_patterns = {
        "app_name": [
            r"\bapp(?:lication)?\s*[:=]\s*([A-Za-z0-9_& .-]+?)(?=,|\s+module\b|\s+priority\b|\s+with\b|\s+feedback\b|\s+description\b|$)",
            r"\bapp(?:lication)?\s+([A-Za-z0-9_& .-]+?)(?=,|\s+module\b|\s+priority\b|\s+with\b|\s+feedback\b|\s+description\b|$)",
            r"\bfor\s+(?:app(?:lication)?\s+)?([A-Za-z0-9_& .-]+?)(?=,|\s+module\b|\s+priority\b|\s+with\b|\s+feedback\b|\s+description\b|$)",
            r"\bfor\s+([A-Za-z0-9_& .-]+?)\s+app(?:lication)?\b",
        ],
        "module": [
            r"\bmodule\s*[:=]\s*([A-Za-z0-9_& .-]+?)(?=,|\s+priority\b|\s+description\b|\s+issue\b|$)",
            r"\bmodule\s+([A-Za-z0-9_& .-]+?)(?=,|\s+priority\b|\s+description\b|\s+issue\b|$)",
        ],
        "description": [
            r"\bdescription\s*[:=]\s*(.+)$",
            r"\bdescription\s+(.+)$",
            r"\bissue\s*[:=]\s*(.+)$",
            r"\bissue\s+(.+)$",
        ],
        "feedback": [
            r"\bfeedback\s*[:=]\s*(.+?)(?=\s+\bhelps\b|\s+\bratings?\b|$)",
            r"\bfeedback\s+(.+?)(?=\s+\bhelps\b|\s+\bratings?\b|$)",
            r"\bsaying\s+(.+?)(?=\s+\bhelps\b|\s+\bratings?\b|$)",
        ],
        "helps": [
            r"\bhelps\s*[:=]\s*(.+)$",
            r"\bhelps\s+(.+)$",
        ],
        "attachments": [
            r"\battachments?\s*[:=]\s*(.+)$",
            r"\battachments?\s+(.+)$",
        ],
        "roles": [
            r"\broles\s*[:=]\s*(.+?)(?=,?\s+\bdescription\b|$)",
            r"\broles\s+(.+?)(?=,?\s+\bdescription\b|$)",
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


# JSON-schema type names that small LLMs echo verbatim instead of real values.
_SCHEMA_PLACEHOLDERS = frozenset({
    "string", "string()", "integer", "integer()", "number", "number()",
    "boolean", "boolean()", "array", "array()", "object", "object()",
    "null", "none", "<string>", "<integer>", "<number>", "<boolean>",
    "str", "int", "float", "bool",
})


def _is_schema_placeholder(value) -> bool:
    """Return True when value looks like a JSON Schema type name, not real data."""
    if not isinstance(value, str):
        return False
    return value.strip().lower() in _SCHEMA_PLACEHOLDERS


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
        elif ptype == "date":
            val_str = str(value).strip()
            if val_str.lower() in _TEMPORAL_KEYWORDS:
                cleaned[key] = val_str
            else:
                import re
                if re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
                    cleaned[key] = val_str
        elif ptype == "datetime":
            val_str = str(value).strip()
            import re
            if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$", val_str):
                cleaned[key] = val_str
        else:
            # string — keep user-provided casing for DocType values.
            cleaned[key] = str(value).strip() if value else None
            if cleaned[key] is None:
                del cleaned[key]

    return cleaned
