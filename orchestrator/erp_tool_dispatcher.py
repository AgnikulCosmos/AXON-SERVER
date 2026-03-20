# orchestrator/erp_tool_dispatcher.py

"""
ERP Tool Dispatcher
-------------------
Accepts a structured execution plan from the router pipeline and prepares
the final tool-call payload for the Frappe backend.

This module does NOT make the actual HTTP call to Frappe — it only
produces the structured tool-call dict that downstream callers
(e.g. dispatcher.py) can use.
"""

import logging

logger = logging.getLogger(__name__)


def prepare_tool_call(plan: dict) -> dict:
    """
    Convert a router-pipeline execution plan into a structured tool-call
    payload.

    Parameters
    ----------
    plan : dict
        Output of ``router_pipeline.process()``, e.g.::

            {
                "route_name": "consumption_log",
                "method": "get_consumption_log",
                "doctype": "Consumption_Log",
                "filters": { ... },
                "confidence": 0.87
            }

    Returns
    -------
    dict
        A tool-call payload::

            {
                "tool": "get_consumption_log",
                "arguments": {
                    "filters": { ... }
                }
            }
    """
    arguments = {}

    filters = plan.get("filters")
    if filters:
        arguments["filters"] = filters

    fields = plan.get("fields")
    if fields:
        arguments["fields"] = fields

    tool_call = {
        "tool": plan["method"],
        "arguments": arguments
    }

    logger.info(
        "[ERP TOOL DISPATCH] tool=%s arguments=%s",
        tool_call["tool"],
        arguments
    )

    return tool_call
