import requests
import logging

logging.basicConfig(level=logging.INFO)


TOOL_ENDPOINTS = {
    "wiki": "http://wiki:8002/query",
    "ddgs": "http://ddgs:8005/query",
    "arxiv": "http://arxiv:8003/query",
}

async def dispatch_tool(query: str):
    tool = _infer_tool(query)

    if tool not in TOOL_ENDPOINTS:
        return tool, f"Unknown tool: {tool}"

    url = TOOL_ENDPOINTS[tool]
    clean_q = _clean_query(query, tool)

    logging.info(f"[TOOL DISPATCH] Tool={tool}, URL={url}, Q={clean_q}")

    try:
        response = requests.get(url, params={"q": clean_q}, timeout=50)
        response.raise_for_status()

        if tool == "arxiv":
            return tool, response.text  

        return tool, response.json()

    except Exception as e:
        logging.error(f"[TOOL DISPATCH ERROR] Tool={tool} Error={e}")
        return tool, f"Tool {tool} failed to execute."



def _infer_tool(query: str) -> str:
    q = query.lower()
    if "arxiv" in q or "paper" in q or "research" in q:
        return "arxiv"
    if "wiki" in q or "wikipedia" in q:
        return "wiki"
    return "ddgs"


def _clean_query(query: str, tool: str) -> str:
    q = query.lower()
    for word in ["use", "wiki", "wikipedia", "arxiv", "paper", "research", "ddgs", "ddg" , "search", ","]:
        q = q.replace(word, " ")
    return q.strip()

