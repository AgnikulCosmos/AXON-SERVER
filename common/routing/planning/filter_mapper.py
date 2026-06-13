# orchestrator/planning/filter_mapper.py

"""
Filter Mapper
-------------
Converts extracted semantic parameters into Frappe-compatible database
filters using the route's ``field_mapping``.

Special handling:
  • date keywords  → ["between", [start, end]]
  • temporal ranges (this week, last month, etc.) → ["between", [start, end]]
  • datetime       → passed through
  • boolean        → 0 / 1
  • number         → numeric value
  • string/enum    → Title-cased value (Frappe convention)
"""

from datetime import datetime, timedelta
import calendar
import logging

logger = logging.getLogger(__name__)


def map_filters(
    extracted_params: dict,
    route_config: dict,
) -> dict:
    """
    Map *extracted_params* to DB-level filters using ``route_config``.

    Returns a dict ready to be passed as ``filters`` to a Frappe whitelisted
    method.
    """
    field_mapping = route_config.get("field_mapping", {})
    params_schema = route_config.get("parameters", {})
    filters: dict = {}

    for param_name, value in extracted_params.items():
        # Only map parameters that have a known field mapping
        if param_name not in field_mapping:
            logger.debug("Skipping param '%s' — no field_mapping entry", param_name)
            continue

        db_field = field_mapping[param_name]
        ptype = params_schema.get(param_name)

        # ── Date handling ────────────────────────────────────────────────
        if ptype == "date" or param_name in ("date",):
            filters[db_field] = _resolve_date(value)
            continue

        # ── Datetime handling ────────────────────────────────────────────
        if ptype == "datetime":
            filters[db_field] = _resolve_datetime(value)
            continue

        # ── Boolean handling ─────────────────────────────────────────────
        if ptype == "boolean":
            filters[db_field] = 1 if value else 0
            continue

        # ── Number handling ──────────────────────────────────────────────
        if ptype == "number":
            try:
                filters[db_field] = float(value)
            except (ValueError, TypeError):
                filters[db_field] = value
            continue

        # ── Enum / String — title-case for Frappe ────────────────────────
        filters[db_field] = _title_case_value(str(value))

    return filters


# ═════════════════════════════════════════════════════════════════════════════
# Date / datetime resolution
# ═════════════════════════════════════════════════════════════════════════════

def _resolve_date(value) -> list:
    """
    Convert a date keyword, temporal range expression, or ISO-date string
    into a ``["between", [start, end]]`` Frappe filter.

    Supported keywords:
      today, yesterday, tomorrow,
      this week, last week,
      this month, last month,
      this year, last year
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    val = str(value).strip().lower()

    # ── Simple day keywords ──────────────────────────────────────────────
    if val == "today":
        start = today
        end = today.replace(hour=23, minute=59, second=59)
    elif val == "yesterday":
        yesterday = today - timedelta(days=1)
        start = yesterday
        end = yesterday.replace(hour=23, minute=59, second=59)
    elif val == "tomorrow":
        tomorrow = today + timedelta(days=1)
        start = tomorrow
        end = tomorrow.replace(hour=23, minute=59, second=59)

    # ── Task 2: Week-level temporal ranges ───────────────────────────────
    elif val == "this week":
        # Monday of the current week → Sunday
        start = today - timedelta(days=today.weekday())
        end = (start + timedelta(days=6)).replace(hour=23, minute=59, second=59)
    elif val == "last week":
        # Monday of the previous week → Sunday of the previous week
        start = today - timedelta(days=today.weekday() + 7)
        end = (start + timedelta(days=6)).replace(hour=23, minute=59, second=59)

    # ── Task 2: Month-level temporal ranges ──────────────────────────────
    elif val == "this month":
        start = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = today.replace(day=last_day, hour=23, minute=59, second=59)
    elif val == "last month":
        # First day of previous month
        first_of_current = today.replace(day=1)
        last_month_end = first_of_current - timedelta(days=1)
        start = last_month_end.replace(day=1, hour=0, minute=0, second=0)
        end = last_month_end.replace(hour=23, minute=59, second=59)

    # ── Task 2: Year-level temporal ranges ───────────────────────────────
    elif val == "this year":
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31, hour=23, minute=59, second=59)
    elif val == "last year":
        start = today.replace(year=today.year - 1, month=1, day=1)
        end = today.replace(
            year=today.year - 1, month=12, day=31,
            hour=23, minute=59, second=59
        )

    # ── Task 2: Specific Month Names ─────────────────────────────────────
    elif val in {
        "january", "jan", "february", "feb", "march", "mar", "april", "apr",
        "may", "june", "jun", "july", "jul", "august", "aug", "september", "sep", "sept",
        "october", "oct", "november", "nov", "december", "dec"
    }:
        months = {
            "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
            "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
            "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
            "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12
        }
        m = months[val]
        start = today.replace(month=m, day=1)
        last_day = calendar.monthrange(today.year, m)[1]
        end = today.replace(month=m, day=last_day, hour=23, minute=59, second=59)

    else:
        # Try to parse an ISO date
        try:
            parsed = datetime.strptime(val[:10], "%Y-%m-%d")
            start = parsed
            end = parsed.replace(hour=23, minute=59, second=59)
        except ValueError:
            # Unparseable — return raw value so the caller can decide
            return value

    return ["between", [
        start.strftime("%Y-%m-%d %H:%M:%S"),
        end.strftime("%Y-%m-%d %H:%M:%S"),
    ]]


def _resolve_datetime(value) -> str:
    """
    Return a datetime string.  If *value* is already ISO-ish, pass it through;
    otherwise attempt a best-effort parse.
    """
    val = str(value).strip()
    try:
        parsed = datetime.fromisoformat(val)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return val


def _title_case_value(value: str) -> str:
    """
    Title-case a value for Frappe compatibility.
    e.g. "lunch" → "Lunch", "in_progress" → "In Progress"
    """
    return value.replace("_", " ").title()
