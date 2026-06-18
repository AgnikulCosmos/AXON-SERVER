from fastapi import FastAPI
import requests

app = FastAPI()

HEADERS = {
    "User-Agent": "AXON-Wiki-Service/1.0"
}

@app.get("/query")
def query(q: str):

    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": q,
            "gsrlimit": 1,
            "prop": "extracts|info",
            "inprop": "url",
            "exintro": 1,
            "explaintext": 1,
            "format": "json"
        }

        response = requests.get(
            search_url,
            params=params,
            headers=HEADERS,
            timeout=20
        )
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        if not pages:
            # Fallback to direct title lookup
            fallback_params = {
                "action": "query",
                "titles": q,
                "prop": "extracts|info",
                "inprop": "url",
                "exintro": 1,
                "explaintext": 1,
                "redirects": 1,
                "format": "json"
            }
            response = requests.get(
                search_url,
                params=fallback_params,
                headers=HEADERS,
                timeout=20
            )
            response.raise_for_status()
            data = response.json()
            pages = data.get("query", {}).get("pages", {})

        if pages:
            page_data = list(pages.values())[0]
            title = page_data.get("title")
            summary = page_data.get("extract")
            url = page_data.get("fullurl") or (f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}" if title else "")
            
            return {
                "tool": "wiki",
                "query": q,
                "title": title,
                "summary": summary,
                "url": url
            }

        return {
            "tool": "wiki",
            "query": q,
            "error": "No page found on Wikipedia."
        }

    except Exception as e:
        return {
            "tool": "wiki",
            "query": q,
            "error": str(e)
        }

