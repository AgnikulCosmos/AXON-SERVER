
#-----------TESTING ROUTER-----------------
# from orchestrator.planning.semantic_router import SemanticRouter
# router = SemanticRouter()
# result = router.match("show my leave requests")
# print("ROUTER TEST \n")
# print("ROUTE:", result["route"]["route_name"])
# print("CONFIDENCE:", result["confidence"])

#export FRAPPE_API_KEY="541f37530c6e5fd"
#export FRAPPE_API_SECRET="0cfc685c914cdfd"

#-----------TESTING PARAMETER EXTRACTOR-------
# from orchestrator.planning.parameter_extractor import extract_parameters
# route_config = {
#     "parameters": {
#         "meal": ["breakfast", "lunch", "dinner"],
#         "date": "date"
#     }
# }
# print("PARAMETER EXTRACTOR TEST \n")
# print(extract_parameters("is my lunch consumed today", route_config))

#-----------TESTING FILTER MAPPER------------------
# from orchestrator.planning.filter_mapper import map_filters
# params = {"meal": "lunch", "date": "today"}
# route = {
#     "field_mapping": {
#         "meal": "type",
#         "date": "updated_on"
#     },
#     "parameters": {
#         "meal": ["breakfast","lunch","dinner"],
#         "date": "date"
#     }
# }
# print("FILTER MAPPER TEST \n")
# print(map_filters(params, route))



#---------------TESTING FILTER VALIDATOR----------
# from orchestrator.planning.filter_validator import validate_filters
# filters = {
#     "type": "Lunch",
#     "fake_field": "test"
# }
# route = {
#     "route_name": "consumption_log",
#     "field_mapping": {
#         "meal": "type"
#     }
# }
# print("FILTER VALIDATOR TEST \n")
# print(validate_filters(filters, route))

#------- PIPELINE -----------------
# from orchestrator.planning.router_pipeline import process
# print(" PIPLINE TEST \n")
# print(process("list the tasks"))

#-----------FULL PIPELINE-------------

# ── Toggle this flag to enable/disable LLM response ─────────────────────
USE_LLM_RESPONSE = True

from orchestrator.planning.router_pipeline import process
from orchestrator.erp_tool_dispatcher import prepare_tool_call
from orchestrator.frappe_client import call_frappe

if USE_LLM_RESPONSE:
    from orchestrator.llm.response_generator import generate_response

print("FULL PIPELINE + FRAPPE TEST\n")

query = "mention the dates in which i have consumed lunch"

plan = process(query)
print("Execution Plan:", plan)

tool_call = prepare_tool_call(plan)

print("Tool Call:", tool_call)

result = call_frappe(tool_call)

print("Frappe Response:", result)

# ── LLM Response Stage (optional) ───────────────────────────────────────
if USE_LLM_RESPONSE:
    data = result.get("message", {}).get("data")
    if data:
        answer = generate_response(query, data)
        print("\n🤖 AI Answer:\n", answer)
    else:
        print("\n⚠ No data in Frappe response to generate AI answer.")
