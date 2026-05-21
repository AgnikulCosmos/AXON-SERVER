import requests
import logging
import re

logging.basicConfig(level=logging.INFO)


import os

TOOL_ENDPOINTS = {
    "wiki": os.getenv("WIKI_URL", "http://wiki:8002/query"),
    "ddgs": os.getenv("DDGS_URL", "http://ddgs:8005/query"),
    "arxiv": os.getenv("ARXIV_URL", "http://arxiv:8003/query"),
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
    q = query.strip()

    if tool == "wiki":
        # Extract the actual search phrase from user intent like "Search wiki for quantum physics"
        q = q.lower()
        q = re.sub(r"\b(search|find|look up|lookup|show|tell me|what is|what are|who is|who are)\b", " ", q)
        q = re.sub(r"\b(wiki|wikipedia)\b", " ", q)
        q = re.sub(r"\b(for|about|on|page|summary)\b", " ", q)
        q = re.sub(r"\s+", " ", q).strip()
        return q or query

    if tool == "arxiv":
        q = q.lower()
        q = re.sub(r"\b(search|find|look up|lookup|show|papers?|research|citation|doi|arxiv)\b", " ", q)
        q = re.sub(r"\b(for|about|on|page|summary)\b", " ", q)
        q = re.sub(r"\s+", " ", q).strip()
        return q or query

    # Default external search tool cleanup
    q = re.sub(r"\b(use|search|find|look up|lookup|for|about|wiki|wikipedia|arxiv|paper|research|ddgs|ddg)\b", " ", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip()
    return q or query

