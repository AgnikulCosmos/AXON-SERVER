# orchestrator/planning/filter_validator.py

"""
Filter Validator
----------------
Ensures that the filters produced by the filter mapper are safe, valid, and
free of hallucinated fields before they are sent to the Frappe backend.
"""

import logging

logger = logging.getLogger(__name__)

# Operators allowed in Frappe filters
_VALID_OPERATORS = {
    "=", "!=", "<", ">", "<=", ">=",
    "like", "not like",
    "in", "not in",
    "between",
    "is", "is not",
}


def validate_filters(
    filters: dict,
    route_config: dict,
) -> dict:
    """
    Validate *filters* against the route configuration.

    Rules applied:
        1. Every filter key must correspond to a value in ``field_mapping``.
        2. Remove any hallucinated / unknown fields.
        3. Ensure operator-based values use valid operators.
        4. Ensure values are of an acceptable type (str, int, float, bool,
           list).

    Returns a cleaned ``dict`` of filters.
    """
    field_mapping = route_config.get("field_mapping", {})
    allowed_fields = set(field_mapping.values())

    validated: dict = {}

    for field, value in filters.items():
        # ── 1. Field must be in field_mapping values ─────────────────────
        if field not in allowed_fields:
            logger.warning(
                "Dropping hallucinated filter field '%s' "
                "(not in field_mapping for route '%s')",
                field,
                route_config.get("route_name", "?"),
            )
            continue

        # ── 2. Validate operator-style values  e.g. ["between", [...]] ──
        if isinstance(value, list) and len(value) == 2:
            operator = value[0]
            if isinstance(operator, str) and operator.lower() in _VALID_OPERATORS:
                operand = value[1]
                if not _is_valid_operand(operand):
                    logger.warning(
                        "Dropping filter '%s': invalid operand %r",
                        field, operand,
                    )
                    continue
                validated[field] = value
                continue
         
        #── 3. Validate scalar values ────────────────────────────────────
        if not _is_valid_scalar(value):
            logger.warning(
                "Dropping filter '%s': unsupported value type %s",
                field, type(value).__name__,
            )
            continue

        validated[field] = value

    return validated


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _is_valid_scalar(value) -> bool:
    """Return True if *value* is an acceptable scalar filter value."""
    return isinstance(value, (str, int, float, bool))


def _is_valid_operand(operand) -> bool:
    """Return True if *operand* (the RHS of an operator filter) is valid."""
    if isinstance(operand, (str, int, float, bool)):
        return True
    if isinstance(operand, list):
        return all(isinstance(v, (str, int, float, bool)) for v in operand)
    return False
