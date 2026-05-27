import asyncio
import json
import uuid
import os
import sys

# Add root directory to python path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Mock execute_erp_support_plan to return double-nested success dictionary when complete,
# but raise MissingParametersError if fields are missing.
import orchestrator.dispatcher as d
from orchestrator.erp_support_client import MissingParametersError

def mock_execute_erp_support_plan(plan):
    params = plan.get("parameters") or {}
    missing = []
    for f in ["item_name", "lost_location", "lost_description"]:
        if not params.get(f):
            missing.append(f)
    if missing:
        raise MissingParametersError(missing)
    return {
        "message": {
            "message": {
                "name": "LF-27-0526-00010",
                "doctype": "Lost And Found",
                "status": "success"
            }
        }
    }

d.execute_erp_support_plan = mock_execute_erp_support_plan

from orchestrator.dispatcher import _run_agent, PENDING_ERP_SESSIONS

async def run_test():
    session_id = str(uuid.uuid4())
    print(f"Starting end-to-end integration test with session_id: {session_id}")
    
    # -------------------------------------------------------------
    # TURN 1: Initial report query
    # -------------------------------------------------------------
    print("\n--- TURN 1: Initial query ---")
    query_1 = "I lost my item"
    print(f"User: {query_1}")
    response_1 = await _run_agent(query_1, session_id=session_id)
    print(f"Agent Response:\n{response_1}")
    
    # Verify session is created and missing fields are set
    assert session_id in PENDING_ERP_SESSIONS, "Session was not registered!"
    pending_plan = PENDING_ERP_SESSIONS[session_id]
    missing = pending_plan.get("_missing_fields") or []
    print(f"Pending missing fields in session: {missing}")
    assert "item_name" in missing, "Missing item_name!"
    assert "lost_location" in missing, "Missing lost_location!"
    assert "lost_description" in missing, "Missing lost_description!"

    # -------------------------------------------------------------
    # TURN 2: Provide item_name and lost_location
    # -------------------------------------------------------------
    print("\n--- TURN 2: Provide partial details ---")
    query_2 = "item_name: Access Card, lost_location: cafeteria"
    print(f"User: {query_2}")
    response_2 = await _run_agent(query_2, session_id=session_id)
    print(f"Agent Response:\n{response_2}")
    
    # Verify only lost_description is missing now
    pending_plan = PENDING_ERP_SESSIONS[session_id]
    missing = pending_plan.get("_missing_fields") or []
    print(f"Pending missing fields in session: {missing}")
    assert len(missing) == 1 and missing[0] == "lost_description", "Expected only lost_description to be missing!"

    # -------------------------------------------------------------
    # TURN 3: Provide lost_description in plain English
    # -------------------------------------------------------------
    print("\n--- TURN 3: Provide description and complete ---")
    query_3 = "It is a blue access card with my employee photo"
    print(f"User: {query_3}")
    response_3 = await _run_agent(query_3, session_id=session_id)
    print(f"Agent Response:\n{response_3}")
    
    # Verify session is cleaned up after successful completion
    assert session_id not in PENDING_ERP_SESSIONS, "Session was not cleaned up!"
    print("\nVerification: Response formatting matches expected string response.")
    assert "Reference ID: LF-27-0526-00010" in response_3, f"Unexpected response format: {response_3!r}"
    
    print("\n🎉 INTEGRATION TEST PASSED SUCCESSFULLY! End-to-end multi-turn flow is fully functional and beautiful.")

if __name__ == "__main__":
    asyncio.run(run_test())
