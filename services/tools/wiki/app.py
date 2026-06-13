from fastapi import FastAPI
import requests

app = FastAPI()

HEADERS = {
    "User-Agent": "AXON-Wiki-Service/1.0"
}

@app.get("/query")
def query(q: str):

    try:
        search_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + q.replace(" ", "_")

        response = requests.get(
            search_url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        return {
            "tool": "wiki",
            "query": q,
            "title": data.get("title"),
            "summary": data.get("extract"),
            "url": data.get("content_urls", {})
                .get("desktop", {})
                .get("page")
        }

    except Exception as e:
        return {
            "tool": "wiki",
            "query": q,
            "error": str(e)
        }
