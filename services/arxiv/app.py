from fastapi import FastAPI
import arxiv

app = FastAPI()

@app.get("/query")
def query(q: str):
    search = arxiv.Search(
        query=q,
        max_results=5,
        sort_by=arxiv.SortCriterion.Relevance
    )

    lines = []

    for i, paper in enumerate(search.results(), start=1):
        title = paper.title.strip().replace("\n", " ")
        authors = ", ".join(a.name for a in paper.authors)
        abstract = paper.summary.strip().replace("\n", " ")[:600]
        year = paper.published.year
        url = paper.entry_id

        lines.append(
            f"**{i}. {title}**\n"
            f"* Authors: {authors}\n"
            f"* Year: {year}\n"
            f"* Abstract: {abstract}...\n"
            f"* [Read Paper on arXiv]({url})\n\n"
            f"---"
        )

    if not lines:
        return "No relevant papers found."

    return "\n\n".join(lines)
