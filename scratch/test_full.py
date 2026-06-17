"""
Full end-to-end feature test for AXON-SERVER.
Tests routing accuracy AND content correctness for all feature areas.
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["FRAPPE_URL"] = "http://14.99.126.171"

logging.basicConfig(level=logging.WARNING)  # suppress noise
logger = logging.getLogger("test_full")

from common.routing.router import route_query
from common.rag.rag_tool import rag_search, keyword_search

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    if detail:
        short = detail[:200].replace("\n", " ")
        print(f"         → {short}")
    return condition


results = {"pass": 0, "fail": 0}

async def assert_route(query, expected_prefix, label=None):
    lbl = label or query[:60]
    route = await route_query(query)
    ok = route.startswith(expected_prefix)
    if check(lbl, ok, f"Got: {route}"):
        results["pass"] += 1
    else:
        results["fail"] += 1
    return route


def assert_rag(query, must_contain_any, label=None):
    lbl = label or query[:60]
    result = rag_search(query)
    ok = any(kw.lower() in result.lower() for kw in must_contain_any)
    if check(lbl, ok, f"Result: {result[:200]}"):
        results["pass"] += 1
    else:
        results["fail"] += 1
    return result


async def run():
    print("\n" + "="*60)
    print("  AXON-SERVER COMPREHENSIVE FEATURE TEST")
    print("="*60)

    # ─── 1. GREETING / IDENTITY ───────────────────────────────
    print("\n[1] Greeting & Identity")
    await assert_route("hi", "GREETING_RESPONSE", "Greeting → GREETING_RESPONSE")
    await assert_route("hello axon", "GREETING_RESPONSE", "Hello → GREETING_RESPONSE")
    await assert_route("who is axon", "IDENTITY", "Identity → IDENTITY")
    await assert_route("what model are you using", "GREETING_RESPONSE", "Model query → base model shield")

    # ─── 2. ERP TICKET CREATION ───────────────────────────────
    print("\n[2] ERP Ticket Creation")
    await assert_route("I am facing a loading lag issue in Fleet Management.", "ERP_ROUTE:erp_tickets_create", "Fleet issue → erp_tickets_create")
    await assert_route("The payroll module is not loading", "ERP_ROUTE:erp_tickets_create", "Payroll issue → erp_tickets_create")
    await assert_route("I have a bug in the attendance module", "ERP_ROUTE:erp_tickets_create", "Attendance bug → erp_tickets_create")

    # ─── 3. ERP FEEDBACK CREATION ─────────────────────────────
    print("\n[3] ERP Feedback / Suggestion Creation")
    await assert_route("I want to submit feedback", "ERP_ROUTE:erp_feedback_create", "Submit feedback → erp_feedback_create")
    await assert_route("I want to give feedback about the leave module", "ERP_ROUTE:erp_feedback_create", "Give feedback → erp_feedback_create")
    await assert_route("submit a suggestion", "ERP_ROUTE:erp_suggestion_create", "Suggestion → erp_suggestion_create")
    await assert_route("I have a suggestion for the canteen system", "ERP_ROUTE:erp_suggestion_create", "Canteen suggestion → erp_suggestion_create")

    # ─── 4. TRACK REQUEST ─────────────────────────────────────
    print("\n[4] Track Request ID")
    await assert_route("track request ERP_I_9", "ERP_ROUTE:track_request", "Track ERP_I → track_request")
    await assert_route("what is the status of ERP_I_100", "ERP_ROUTE:track_request", "Status ERP_I → track_request")
    await assert_route("track PC-1234", "ERP_ROUTE:track_request", "Track PC- → track_request")

    # ─── 5. FOOD LOG / FOOD REQUESTS ──────────────────────────
    print("\n[5] Food Log & Booking")
    await assert_route("show my food log", "ERP_ROUTE:food_log_list", "Food log → food_log_list")
    await assert_route("did I book food yesterday", "ERP_ROUTE:food_requests", "Food booking → food_requests")

    # ─── 6. LOST AND FOUND ────────────────────────────────────
    print("\n[6] Lost & Found")
    await assert_route("I lost my blue access card in the canteen today.", "ERP_ROUTE:lost_found_create", "Lost card → lost_found_create")
    await assert_route("I found a laptop bag near the entrance", "ERP_ROUTE:lost_found_create", "Found bag → lost_found_create")
    await assert_route("show lost and found items", "ERP_ROUTE:lost_found_list", "List L&F → lost_found_list")
    await assert_route("list all lost items", "ERP_ROUTE:lost_found_list", "List lost → lost_found_list")

    # ─── 7. LEAVE BALANCE ─────────────────────────────────────
    print("\n[7] Leave Balance")
    await assert_route("what is my leave balance", "ERP_ROUTE:pr_leave_tracker", "Leave balance → pr_leave_tracker")
    await assert_route("how many leaves do I have left", "ERP_ROUTE:pr_leave_tracker", "Leaves left → pr_leave_tracker")

    # ─── 8. RAG — INTERNAL KNOWLEDGE ─────────────────────────
    print("\n[8] RAG Routing")
    await assert_route("what is the casual leave policy", "RAG", "Leave policy → RAG")
    await assert_route("what does Agnikul Cosmos do", "RAG", "About Agnikul → RAG")
    await assert_route("who are the founders of Agnikul", "RAG", "Founders → RAG")
    await assert_route("how many rockets they have launched", "RAG", "Rocket count → RAG")
    await assert_route("what is Agnibaan", "RAG", "Agnibaan → RAG")
    await assert_route("what is the reimbursement policy", "RAG", "Reimbursement → RAG")

    # ─── 9. RAG CONTENT CORRECTNESS ──────────────────────────
    print("\n[9] RAG Content Correctness (no LLM)")
    assert_rag("how many rockets they have launched",
               ["Agnibaan", "SOrTeD", "Mission-01", "launched", "one"],
               "Rocket count → factual answer")
    assert_rag("who are the founders of Agnikul",
               ["Srinath", "Moin", "founder"],
               "Founders → correct names")
    assert_rag("what does Agnikul Cosmos do",
               ["launch", "rocket", "satellite", "space", "orbital"],
               "Agnikul business → orbital/space content")
    assert_rag("what is the casual leave policy",
               ["casual", "leave", "day", "entitlement"],
               "Casual leave → policy content")

    # ─── 10. EXTERNAL TOOLS ROUTING ──────────────────────────
    print("\n[10] External Tools (Wiki / DDGS / arXiv)")
    await assert_route("/wiki Albert Einstein", "TOOLS", "/wiki → TOOLS")
    await assert_route("/ddgs latest news India", "TOOLS", "/ddgs → TOOLS")
    await assert_route("/arxiv transformer architecture", "TOOLS", "/arxiv → TOOLS")
    await assert_route("who is the prime minister of India", "TOOLS", "General knowledge → TOOLS")
    await assert_route("search for papers on neural networks", "TOOLS", "Research papers → TOOLS")

    # ─── 11. NORMAL / GENERAL QUESTIONS ──────────────────────
    print("\n[11] Normal / General Questions")
    await assert_route("what is a liquid rocket engine", "TOOLS", "General science → TOOLS")
    await assert_route("explain machine learning", "TOOLS", "ML explanation → TOOLS")

    # ─── SUMMARY ─────────────────────────────────────────────
    total = results["pass"] + results["fail"]
    print("\n" + "="*60)
    print(f"  RESULTS: {results['pass']}/{total} passed  |  {results['fail']} failed")
    print("="*60 + "\n")

    if results["fail"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
