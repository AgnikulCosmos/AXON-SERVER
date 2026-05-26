
# rag_tool.py
# Agnikul knowledge retrieval using Chroma vector search with dataset.json fallback.

from langchain_core.tools import Tool
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json
import os
import logging

logger = logging.getLogger("orchestrator")

# -----------------------------
# LLM for factual summarization
# -----------------------------
_summarizer_llm = ChatOllama(
    model="qwen2.5:0.5b",
    temperature=0,
    base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
)

_summary_template = """Context:
{context}

Question:
{question}

Answer the question directly based on the context above. Keep it concise.
Answer:"""

_prompt = PromptTemplate.from_template(_summary_template)
_summary_chain = _prompt | _summarizer_llm | StrOutputParser()

# -----------------------------
# Dataset loading
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "dataset.json"))

_dataset_cache = None


def _load_dataset():
    global _dataset_cache
    if _dataset_cache is not None:
        return _dataset_cache
    try:
        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            _dataset_cache = json.load(f)
        logger.info(f"Loaded {len(_dataset_cache)} entries from dataset.json")
    except Exception as err:
        logger.error(f"Failed to load dataset.json: {err}")
        _dataset_cache = []
    return _dataset_cache


# -----------------------------
# Keyword search on dataset.json
# -----------------------------
def keyword_search(query: str, k: int = 5) -> list:
    """
    Keyword-based search over dataset.json.
    Scores each entry by matching query words against
    title, content, keywords, and questions fields.
    """
    dataset = _load_dataset()
    if not dataset:
        return []

    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 2]

    scored = []
    for item in dataset:
        score = 0
        title = (item.get("title") or "").lower()
        content = (item.get("content") or "").lower()
        kw_list = [kw.lower() for kw in (item.get("keywords") or [])]
        q_list = [q.lower() for q in (item.get("questions") or [])]

        # Score by query word matches
        for word in query_words:
            if word in title:
                score += 3
            if word in content:
                score += 2
            for kw in kw_list:
                if word in kw:
                    score += 4
            for q in q_list:
                if word in q:
                    score += 3

        # Bonus: full query matches a stored question
        for q in q_list:
            if query_lower in q or q in query_lower:
                score += 10

        if score > 0:
            text_blocks = []
            if item.get("title"):
                text_blocks.append(item["title"])
            if item.get("content"):
                text_blocks.append(item["content"])
            scored.append((score, "\n".join(text_blocks)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:k]]


def vector_search(query: str, k: int = 5) -> list:
    """Vector similarity search using the Chroma DB retriever."""
    try:
        from common.vector import get_vector_retriever

        retriever = get_vector_retriever()
        if retriever is None:
            raise RuntimeError("Vector retriever unavailable")

        if hasattr(retriever, "invoke"):
            docs = retriever.invoke(query)
        else:
            docs = retriever.get_relevant_documents(query)
        results = [getattr(doc, "page_content", "") for doc in docs if getattr(doc, "page_content", "")]
        if results:
            return results[:k]
    except Exception as err:
        logger.warning(f"Vector search failed: {err}")
    return keyword_search(query, k=k)


# -----------------------------
# RAG entry point
# -----------------------------
def rag_search(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        return "Invalid query."

    # Detect if user asks to create/apply/correct unsupported administrative models (like leaves, checkins, checkouts, claim expenses, payroll corrections)
    query_lower = query.lower()
    is_action_request = any(verb in query_lower for verb in ["apply", "raise", "create", "request", "lodge", "submit", "change", "cancel", "correct", "update", "delete", "remove", "modify", "check", "mark", "register", "do", "perform"])
    is_supported_erp = any(x in query_lower for x in ["ticket", "feedback", "review", "rate", "rating", "suggestion", "improve", "enhancement"])

    if is_action_request and not is_supported_erp:
        return "I cannot directly perform this action or administrative correction (I can only create support tickets, feedback, and suggestions)."

    context_parts = vector_search(query, k=5)

    if not context_parts:
        return "Information not available in the knowledge base."

    context_text = "\n\n".join(context_parts)

    # Defensive truncation
    MAX_CHARS = 12000
    if len(context_text) > MAX_CHARS:
        context_text = context_text[:MAX_CHARS]

    try:
        return _summary_chain.invoke({
            "context": context_text,
            "question": query
        })
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        # If LLM fails, return raw context
        return context_text


# -----------------------------
# Tool registration
# -----------------------------
rag_tool = Tool(
    name="agnikul_rag_search",
    func=rag_search,
    description="Search the internal Agnikul knowledge base and return a concise factual answer."
)
