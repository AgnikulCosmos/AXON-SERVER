from fastapi import FastAPI
from ddgs import DDGS

app = FastAPI()

@app.get("/query")
def query(q: str):
    with DDGS() as ddgs:
        results = list(ddgs.text(q, max_results=5))

    return {
        "tool": "ddgs",
        "query": q,
        "results": results
    }
