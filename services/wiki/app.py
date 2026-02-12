from fastapi import FastAPI
import wikipedia
from wikipedia.exceptions import PageError, DisambiguationError

app = FastAPI()

@app.get("/query")
def query(q: str):
    try:
        page = wikipedia.page(
            q,
            auto_suggest=True,   
        )
        summary = wikipedia.summary(
            page.title,
            sentences=2,
            auto_suggest=True,
            redirect=True
        )

        return {
            "tool": "wiki",
            "query": q,
            "title": page.title,
            "summary": summary
        }

    except DisambiguationError as e:
        return {
            "tool": "wiki",
            "query": q,
            "error": "Ambiguous query",
            "options": e.options[:5]
        }

    except PageError:
        return {
            "tool": "wiki",
            "query": q,
            "error": "No Wikipedia page found"
        }

    except Exception as e:
        return {
            "tool": "wiki",
            "query": q,
            "error": str(e)
        }
