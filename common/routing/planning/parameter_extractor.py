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
import asyncio
import logging
from langchain_ollama import ChatOllama

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Task 7: Configurable Ollama URL ─────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── LLM for parameter extraction ────────────────────────────────────────────
_extractor_llm = ChatOllama(
    model=os.getenv("LLM_MODEL", "qwen3.5:0.8b"),
    base_url=OLLAMA_URL,
    temperature=0,
    streaming=False,
)

from prompts.routing import PARAMETER_EXTRACTION_PROMPT
_EXTRACT_PROMPT = PARAMETER_EXTRACTION_PROMPT
# Cache holder for valid app names from Frappe
_VALID_APP_NAMES_CACHE = None

# Add this function to fetch valid app names from Frappe
def _get_valid_app_names_from_frappe() -> list:
    global _VALID_APP_NAMES_CACHE

    if _VALID_APP_NAMES_CACHE is not None:
        return _VALID_APP_NAMES_CACHE

    try:
        from services.erp.mcp_registry import list_erp_apps
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            response = None
        else:
            response = asyncio.run(list_erp_apps(limit=200))
        if response is not None:
            data = response.get("message", response) if isinstance(response, dict) else {}
            if isinstance(data, dict):
                records = data.get("data", [])
                if isinstance(records, list):
                    _VALID_APP_NAMES_CACHE = [str(r.get("name", "")).strip() for r in records if r.get("name")]
                    return _VALID_APP_NAMES_CACHE
    except Exception as e:
        logging.warning(f"Failed to fetch app names from Frappe: {e}")

    _VALID_APP_NAMES_CACHE = []
    return _VALID_APP_NAMES_CACHE


def _build_app_name_mapping():
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
        "Agnikul Core ERP": ["core", "core erp", "agnikul core", "agnikul core erp"],
        "ERP Support": ["erp_support", "erp support", "support", "erp"],
        "Fleet Management": ["fleet_management", "fleet management", "fleet", "fleet mgmt"],
        "Food and Beverages": ["food", "food booking", "food and beverages", "food & beverages", "canteen", "meals"],
        "HR Operations": ["hr_operations", "hr operations", "hr", "human resources", "hr ops"],
        "Maintenance Management": ["maintenance_management", "maintenance management", "maintenance", "maintenance mgmt"],
        "Packaging Management": ["packaging_management", "packaging management", "packaging", "packaging mgmt"],
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

    # Dynamic schema filtering for lost_found_create to avoid parameter confusion
    if route_config.get("route_name") == "lost_found_create":
        q_lower = query.lower()
        if "found" in q_lower:
            # Found report update flow / New found report creation flow
            allowed = ["name", "item_name", "status", "found_location", "found_date", "found_description"]
            params_schema = {k: v for k, v in params_schema.items() if k in allowed}
        else:
            # Lost report creation flow
            allowed = ["item_name", "lost_location", "lost_date", "lost_description", "status"]
            params_schema = {k: v for k, v in params_schema.items() if k in allowed}

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
            
            # Validate extracted app_name to make sure it was actually mentioned in the query
            if "app_name" in extracted_params:
                app_val = str(extracted_params["app_name"])
                app_val_lower = app_val.lower().strip()
                query_lower = query.lower()
                
                mentioned = app_val_lower in query_lower
                if not mentioned:
                    # Look up aliases in APP_NAME_MAPPING
                    for canonical, aliases in APP_NAME_MAPPING.items():
                        if canonical.lower() == app_val_lower or any(alias.lower() == app_val_lower for alias in aliases):
                            if canonical.lower() in query_lower or any(alias.lower() in query_lower for alias in aliases):
                                mentioned = True
                                extracted_params["app_name"] = canonical
                                break
                
                if not mentioned:
                    logger.info(f"Discarding hallucinated/defaulted app_name: {app_val}")
                    del extracted_params["app_name"]
            
            logger.debug("LLM extraction result (after placeholder strip and validation): %s", extracted_params)
    except Exception as exc:
        logger.warning("LLM parameter extraction failed: %s — using fallback", exc)

    # ── 2. Deterministic fallback ────────────────────────────────────────
    fallback = _keyword_extract(query, params_schema)
    fallback.update(_erp_support_extract(query, route_config, params_schema))
    fallback.update(_lost_found_extract(query, params_schema))

    for key, value in fallback.items():
        # Deterministic fallback (especially regex/enums) is much more accurate
        # than small LLM extraction, so we override the LLM if a fallback matched.
        extracted_params[key] = value

    # Qwen 0.5b often hallucinates the `app_name` into `module` when it's absent.
    # We must do this check AFTER fallback merge, in case LLM only extracted module.
    if extracted_params.get("module") and extracted_params.get("app_name"):
        if str(extracted_params["module"]).lower() == str(extracted_params["app_name"]).lower():
            del extracted_params["module"]

    # ── Post-processing / Cleanups ──────────────────────────────────────
    if "app_name" in extracted_params:
        app_val = str(extracted_params["app_name"]).strip()
        if app_val in ("erp_support", "ERP Support"):
            q_clean = query.lower()
            q_clean = re.sub(r"\bsupport\s+(?:ticket|request|plan|action|need|create|raise)s?\b", "", q_clean)
            q_clean = re.sub(r"\braise\s+(?:a\s+)?support\b", "", q_clean)
            q_clean = re.sub(r"\bcreate\s+(?:a\s+)?support\b", "", q_clean)
            if "support" not in q_clean:
                logger.info(f"Discarding generic erp_support app_name extraction: {app_val}")
                del extracted_params["app_name"]

    if "description" in extracted_params:
        desc_val = str(extracted_params["description"]).strip().lower().strip("!?.,'")
        generic_triggers = {
            "create support ticket", "raise support ticket", "raise a ticket", "lodge a ticket",
            "create a ticket", "open a support request", "lodge a support ticket", "support ticket",
            "ticket", "i need to create a ticket", "i need to create a support ticket",
            "i want to raise a ticket", "i want to raise a support ticket", "create support ticket",
            "create a support ticket", "raise a support ticket", "open a support ticket",
            "i need to raise a ticket", "raise a support request", "create a support request"
        }
        if desc_val in generic_triggers:
            logger.info(f"Discarding generic description: {desc_val}")
            del extracted_params["description"]

    if "feedback" in extracted_params:
        feed_val = str(extracted_params["feedback"]).strip().lower().strip("!?.,'")
        generic_feedback_triggers = {
            "submit feedback", "give feedback", "write feedback", "rate an application",
            "create erp support feedback", "submit a review", "submit a feedback", "give a feedback",
            "feedback", "suggestion", "create suggestion", "submit suggestion", "give suggestion",
            "canteen feedback", "canteen suggestion", "food feedback", "food suggestion",
            "feedback suggestions", "suggestions", "feedbacks"
        }
        is_generic = feed_val in generic_feedback_triggers
        
        # Discard if it is just specifying the app name, e.g. "for fleet management" or "fleet management"
        app_name_val = extracted_params.get("app_name")
        if app_name_val:
            app_name_lower = str(app_name_val).lower()
            if feed_val == f"for {app_name_lower}" or feed_val == app_name_lower:
                is_generic = True
                
        if is_generic:
            logger.info(f"Discarding generic feedback: {feed_val}")
            del extracted_params["feedback"]


    route_name = route_config.get("route_name", "")
    if route_name == "lost_found_create":
        if "name" in extracted_params:
            val = str(extracted_params["name"]).strip()
            if not val.upper().startswith("LF-"):
                logger.info(f"Discarding invalid reference name: {val!r}")
                del extracted_params["name"]

    # Clean up locations if they are just relative/temporal date keywords
    for loc_field in ["lost_location", "found_location"]:
        if loc_field in extracted_params:
            val = str(extracted_params[loc_field]).strip().lower()
            if val in ("today", "yesterday", "tomorrow", "this week", "last week", "this month", "last month"):
                logger.info(f"Discarding temporal keyword as location: {extracted_params[loc_field]}")
                del extracted_params[loc_field]

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
        elif param in ("req_id", "docname"):
            # Support both hyphen and underscore separators, e.g. ERP_I_75 or ERP-SF-0001
            req_id_match = re.search(
                r"\b((?:PC|MM|MT|DL|LF|ERP_I|ERP-SF|FBSG|SUG|ERP-RU|ERP-FAQ|ERP-M|ERP_SF)[-_]\w+(?:[-_]\w+)*)\b",
                query, re.I
            )
            if req_id_match:
                extracted[param] = req_id_match.group(1).upper()

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
        for pattern in [
            r"\bratings?\s*[:=]?\s*([1-5](?:\.\d+)?)\b",
            r"\brate\s+(?:it\s+)?([1-5](?:\.\d+)?)\b",
            r"\b([1-5](?:\.\d+)?)\s*stars?\b",
            r"\bgive\s+(?:it\s+)?([1-5](?:\.\d+)?)\b",
        ]:
            match = re.search(pattern, query, re.I)
            if match:
                extracted["ratings"] = float(match.group(1))
                break

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
            r"\b(?:in|on|for|the|at|^)\s*([A-Za-z0-9_& -]{2,20})\s+module\b",
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

    # ── Heuristic fallback for suggestions/feedback benefit markers ──
    if route_name == "erp_suggestion_create":
        if "feedback" in schema and "helps" in schema:
            if "feedback" not in extracted or "helps" not in extracted:
                q_clean = query.strip()
                benefit_pattern = r"\b(would|helps to|helps|so that|to help|in order to)\b"
                match_benefit = re.search(benefit_pattern, q_clean, re.I)
                if match_benefit:
                    marker_idx = match_benefit.start()
                    feedback_part = q_clean[:marker_idx].strip()
                    helps_part = q_clean[marker_idx:].strip()

                    # Clean up the feedback part
                    feedback_part = re.sub(r"^(?:suggest|suggestion|suggesting|adding a suggestion|i have a suggestion|submit a suggestion|submit suggestion|to improve|improve|suggest to)\b", "", feedback_part, flags=re.I).strip()
                    # Remove app name aliases if present in feedback
                    for canonical, aliases in APP_NAME_MAPPING.items():
                        for alias in aliases:
                            feedback_part = re.sub(rf"\bfor\s+(?:the\s+)?{re.escape(alias)}\b", "", feedback_part, flags=re.I)
                            feedback_part = re.sub(rf"\bin\s+(?:the\s+)?{re.escape(alias)}\b", "", feedback_part, flags=re.I)
                            feedback_part = re.sub(rf"\b{re.escape(alias)}\b", "", feedback_part, flags=re.I)

                    feedback_part = re.sub(r"\s+", " ", feedback_part).strip(",. ")
                    helps_part = re.sub(r"\s+", " ", helps_part).strip(",. ")

                    if feedback_part and len(feedback_part) > 3:
                        extracted["feedback"] = feedback_part
                    if helps_part:
                        extracted["helps"] = helps_part

    # Heuristic fallback for erp_feedback_create and erp_tickets_create when feedback/description is not yet extracted
    if "feedback" in schema and "feedback" not in extracted:
        # If it is feedback creation
        q_clean = query
        # Remove ratings patterns
        for pattern in [
            r"\bratings?\s*[:=]?\s*[1-5](?:\.\d+)?\b",
            r"\brate\s+(?:it\s+)?\s*[1-5](?:\.\d+)?\b",
            r"\b[1-5](?:\.\d+)?\s*stars?\b",
            r"\bgive\s+(?:it\s+)?\s*[1-5](?:\.\d+)?\b",
        ]:
            q_clean = re.sub(pattern, "", q_clean, flags=re.I)
        
        # Remove app name aliases if present
        for canonical, aliases in APP_NAME_MAPPING.items():
            for alias in aliases:
                q_clean = re.sub(rf"\bfor\s+(?:the\s+)?{re.escape(alias)}\b", "", q_clean, flags=re.I)
                q_clean = re.sub(rf"\bin\s+(?:the\s+)?{re.escape(alias)}\b", "", q_clean, flags=re.I)
                q_clean = re.sub(rf"\b{re.escape(alias)}\b", "", q_clean, flags=re.I)

        # Remove generic feedback verbs/triggers
        q_clean = re.sub(r"\b(submit|give|leave|write|create|send)\s+(?:a\s+)?(?:feedback|review|suggestion|rating)\b", "", q_clean, flags=re.I)
        q_clean = re.sub(r"\b(feedback|suggestions?|ratings?)\b", "", q_clean, flags=re.I)
        
        q_clean = q_clean.strip("!?.,;:'\" ")
        q_clean = re.sub(r"\s+", " ", q_clean).strip()
        # Clean leading/trailing conjunctions
        q_clean = re.sub(r"^(?:and|or|with|for|about|to)\s+", "", q_clean, flags=re.I)
        q_clean = re.sub(r"\s+(?:and|or|with|for|about|to)$", "", q_clean, flags=re.I)
        
        if q_clean and len(q_clean) > 3:
            extracted["feedback"] = q_clean

    if "description" in schema and "description" not in extracted:
        # If it is ticket creation
        q_clean = query
        # Remove priority patterns (P0-P3, High, Medium, Low)
        for val in ["low", "medium", "high", "p0", "p1", "p2", "p3"]:
            q_clean = re.sub(rf"\b{re.escape(val)}\b", "", q_clean, flags=re.I)
        # Remove app name aliases
        for canonical, aliases in APP_NAME_MAPPING.items():
            for alias in aliases:
                q_clean = re.sub(rf"\bfor\s+(?:the\s+)?{re.escape(alias)}\b", "", q_clean, flags=re.I)
                q_clean = re.sub(rf"\bin\s+(?:the\s+)?{re.escape(alias)}\b", "", q_clean, flags=re.I)
                q_clean = re.sub(rf"\b{re.escape(alias)}\b", "", q_clean, flags=re.I)
        # Remove module patterns
        q_clean = re.sub(r"\bmodule\s*[:=]?\s*[A-Za-z0-9_& .-]+?\b", "", q_clean, flags=re.I)
        # Remove generic ticket verbs/triggers
        q_clean = re.sub(r"\b(raise|create|open|lodge|submit|report)\s+(?:a\s+)?(?:ticket|issue|bug|request|problem)\b", "", q_clean, flags=re.I)
        q_clean = re.sub(r"\b(ticket|issue|bug|request|problem)\b", "", q_clean, flags=re.I)
        
        q_clean = q_clean.strip("!?.,;:'\" ")
        q_clean = re.sub(r"\s+", " ", q_clean).strip()
        # Clean leading/trailing conjunctions
        q_clean = re.sub(r"^(?:and|or|with|for|about|to)\s+", "", q_clean, flags=re.I)
        q_clean = re.sub(r"\s+(?:and|or|with|for|about|to)$", "", q_clean, flags=re.I)
        
        if q_clean and len(q_clean) > 3:
            extracted["description"] = q_clean

    return extracted


def _lost_found_extract(query: str, schema: dict) -> dict:
    """
    Deterministic fallback for Lost and Found queries to extract item_name,
    lost_location, and lost_description from standard natural language statements.
    """
    extracted = {}
    q_lower = query.lower()
    
    # If the schema is for lost_found creation
    is_lost_schema = "item_name" in schema or "lost_location" in schema
    is_found_schema = "found_location" in schema
    
    if not (is_lost_schema or is_found_schema):
        return {}

    # Extract status based on keywords
    if "status" in schema:
        if "found" in q_lower:
            extracted["status"] = "Found"
        elif "lost" in q_lower:
            extracted["status"] = "Pending"

    # Extract location (lost or found)
    # Search for patterns like: "lost it at <location>", "lost at <location>", "lost in <location>", "at <location>", "in <location>", "found it at <location>"
    location_match = re.search(r"\b(?:lost|found)(?:\s+it|\s+them|\s+my\s+[a-zA-Z0-9_ -]+)?\s+(?:at|in|near|inside|around)\s+(?:the\s+)?([A-Za-z0-9_& -]+?)(?:\.|$|\s+today|\s+yesterday|\s+tomorrow)", q_lower)
    if not location_match:
        # Fallback to simple "at <location>" or "in <location>" if it is at the end of the query or followed by punctuation
        location_match = re.search(r"\b(?:at|in|near|inside|around)\s+(?:the\s+)?([A-Za-z0-9_& -]+?)(?:\.|$|\s+today|\s+yesterday|\s+tomorrow)", q_lower)

    location_val = None
    if location_match:
        location_val = location_match.group(1).strip()
        # Filter out common temporal keywords or descriptive nouns that aren't locations
        if location_val.lower() in ("today", "yesterday", "tomorrow", "this week", "last week", "a", "an", "the", "my"):
            location_val = None

    if location_val:
        if "lost_location" in schema:
            extracted["lost_location"] = location_val.title()
        elif "found_location" in schema:
            extracted["found_location"] = location_val.title()

    # Extract item name and description
    # Pattern: "lost my <item>" or "found a <item>"
    item_match = re.search(r"\b(?:lost|found)\s+(?:my|a|an|the|some)\s+([A-Za-z0-9_ -]+?)(?:\s+(?:in|at|near|inside|around|today|yesterday|tomorrow|with|of)|\.|$)", q_lower)
    if item_match:
        extracted["item_name"] = item_match.group(1).strip().title()

    # Fallback pattern for item name: e.g. "found wallet", "found keys", "lost keys"
    if "item_name" not in extracted:
        fallback_item_match = re.search(r"\b(?:lost|found)\s+([A-Za-z0-9_-]+)(?:\s+(?:in|at|near|inside|around|today|yesterday|tomorrow|with|of)|\.|$)", q_lower)
        if fallback_item_match:
            extracted["item_name"] = fallback_item_match.group(1).strip().title()

    # If the user provides a detailed description like "The purse is black colour with logo"
    # Let's match descriptions like "<item> is/was <desc>"
    desc_match = re.search(r"\b([A-Za-z0-9_ -]+?)\s+(?:is|was|has)\s+([A-Za-z0-9_ -]+?)(?:\s+and\s+i\s+lost\s+|$|\.)", q_lower)
    if desc_match:
        subj = desc_match.group(1).strip().lower()
        desc = desc_match.group(2).strip()
        if "item_name" in extracted and extracted["item_name"].lower() in subj or subj in ("purse", "bag", "phone", "card", "keys", "wallet", "charger"):
            if "lost_description" in schema:
                extracted["lost_description"] = f"{subj.title()} is {desc}"
            elif "found_description" in schema:
                extracted["found_description"] = f"{subj.title()} is {desc}"

    # Also check traditional templates/patterns
    # Pattern 1: "I lost my <item> in the <location>"
    match1 = re.search(r"\blost my\s+([A-Za-z0-9_& -]+?)\s+in(?: the)?\s+([A-Za-z0-9_& -]+?)(?:\s+(?:today|yesterday|tomorrow|this week|last week)|\.|$)", q_lower)
    if match1:
        extracted["item_name"] = match1.group(1).strip().title()
        if "lost_location" in schema:
            extracted["lost_location"] = match1.group(2).strip().title()
        
    # Pattern 2: "I lost my <item> at <location>"
    match2 = re.search(r"\blost my\s+([A-Za-z0-9_& -]+?)\s+at\s+([A-Za-z0-9_& -]+?)(?:\s+(?:today|yesterday|tomorrow)|\.|$)", q_lower)
    if match2:
        extracted["item_name"] = match2.group(1).strip().title()
        if "lost_location" in schema:
            extracted["lost_location"] = match2.group(2).strip().title()

    # Clean up and validate
    for k in list(extracted.keys()):
        val = extracted[k]
        if not val or (isinstance(val, str) and val.lower() in ["a", "an", "the", "my", "item"]):
            del extracted[k]

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
