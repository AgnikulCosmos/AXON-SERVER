
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
from common.ollama_helper import get_working_ollama_base_url

_summarizer_llm = ChatOllama(
    model="qwen2.5:1.5b",
    temperature=0,
    base_url=get_working_ollama_base_url()
)

from prompts.registry import RAG_SUMMARY_TEMPLATE
_summary_template = RAG_SUMMARY_TEMPLATE

_prompt = PromptTemplate.from_template(_summary_template)
_summary_chain = _prompt | _summarizer_llm | StrOutputParser()

# -----------------------------
# Dataset loading
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "dataset.json"))

_dataset_cache = None
_dataset_mtime = None


def _load_dataset():
    global _dataset_cache, _dataset_mtime
    try:
        current_mtime = os.path.getmtime(DATASET_PATH)
    except Exception:
        current_mtime = None

    if _dataset_cache is not None and current_mtime == _dataset_mtime:
        return _dataset_cache
    try:
        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            _dataset_cache = json.load(f)
        _dataset_mtime = current_mtime
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

    stop_words = {
        "our", "you", "your", "yours", "he", "him", "his", "she", "her", "hers", "it", "its", "they", "them", 
        "their", "theirs", "this", "that", "these", "those", "am", "is", "are", 
        "was", "were", "be", "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", 
        "a", "an", "the", "and", "but", "if", "or", "because", "as", "until", "while", "of", "at", "by", "for", 
        "with", "about", "against", "between", "into", "through", "during", "before", "after", "above", 
        "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", "under", "again", "further", 
        "then", "once", "here", "there", "all", "any", "both", "each", "few", 
        "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", 
        "too", "very", "can", "will", "just", "should", "now", "many"
    }

    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 2]
    filtered_words = [w for w in query_words if w not in stop_words]
    if filtered_words:
        query_words = filtered_words

    scored = []
    for item in dataset:
        score = 0
        title = (item.get("title") or "").lower()
        content = (item.get("content") or "").lower()
        kw_list = [kw.lower() for kw in (item.get("keywords") or [])]
        q_list = [q.lower() for q in (item.get("questions") or [])]

        # Score by query word matches with basic stemming / substring mapping
        for word in query_words:
            stems = [word]
            if word.endswith("s") and len(word) > 3:
                stems.append(word[:-1])
            if word.endswith("ed") and len(word) > 4:
                stems.append(word[:-2])
                stems.append(word[:-1])
            if word.endswith("ing") and len(word) > 5:
                stems.append(word[:-3])

            matched = False
            for stem in stems:
                if stem in title:
                    score += 3
                    matched = True
                if stem in content:
                    score += 2
                    matched = True
                for kw in kw_list:
                    if stem in kw:
                        score += 4
                        matched = True
                for q in q_list:
                    if stem in q:
                        score += 3
                        matched = True
                if matched:
                    break

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

    import re
    query_lower = query.lower()
    query_words = set(re.findall(r"\b\w+\b", query_lower))

    action_verbs = {
        "apply", "raise", "create", "request", "lodge", "submit",
        "change", "cancel", "correct", "update", "delete", "remove",
        "modify", "check", "mark", "register", "perform"
    }
    is_action_request = any(verb in query_words for verb in action_verbs)
    is_supported_erp = any(x in query_lower for x in ["ticket", "feedback", "review", "rate", "rating", "suggestion", "improve", "enhancement"])
    informational_indicators = {
        "how", "what", "why", "who", "where", "when", "list", "show", "view",
        "policy", "policies", "rules", "guidelines", "info", "details", "information", "guideline"
    }
    is_informational = any(indicator in query_words for indicator in informational_indicators)

    if is_action_request and not is_supported_erp and not is_informational:
        return "I cannot directly perform this action or administrative correction (I can only create support tickets, feedback, and suggestions)."

    dataset = _load_dataset()

    # ── Step 1: Question-overlap matching (highest priority, no LLM) ───
    # Match user query against stored `questions` field in dataset.
    # Uses token-overlap (Jaccard) — robust against wording variations.
    _stop = {
        "is", "are", "was",
        "the", "a", "an", "tell", "me", "about", "does", "do", "did",
        "has", "have", "had", "for", "of", "in", "on", "at", "to", "its",
        "their", "they", "i", "my", "can", "will", "would", "please", "any"
    }
    q_tokens = set(w for w in re.findall(r"\b[a-z0-9]+\b", query_lower) if w not in _stop and len(w) > 2)

    if q_tokens:
        best_score = 0.0
        best_content = None

        for item in dataset:
            content = item.get("content", "")
            title = (item.get("title") or "").lower()
            stored_qs = item.get("questions", [])

            # Score against each stored question
            for stored_q in stored_qs:
                sq_tokens = set(w for w in re.findall(r"\b[a-z0-9]+\b", stored_q.lower()) if w not in _stop and len(w) > 2)
                if not sq_tokens:
                    continue
                overlap = len(q_tokens & sq_tokens)
                if overlap == 0:
                    continue
                score = overlap / len(q_tokens | sq_tokens)
                if score > best_score:
                    best_score = score
                    best_content = content

            # Also score against title (slight discount)
            title_tokens = set(w for w in re.findall(r"\b[a-z0-9]+\b", title) if w not in _stop and len(w) > 2)
            if title_tokens:
                overlap = len(q_tokens & title_tokens)
                if overlap > 0:
                    score = (overlap / len(q_tokens | title_tokens)) * 0.8
                    if score > best_score:
                        best_score = score
                        best_content = content

        if best_score >= 0.6 and best_content:
            logger.info(f"[Question Match] score={best_score:.2f} query={query!r}")
            return best_content

    # ── Step 2: Vector search + LLM (when DB is ready) ─────────────────
    try:
        from common.vector import get_vector_retriever
        retriever = get_vector_retriever()
        if retriever is not None:
            if hasattr(retriever, "invoke"):
                docs = retriever.invoke(query)
            else:
                docs = retriever.get_relevant_documents(query)
            context_parts = [getattr(d, "page_content", "") for d in docs if getattr(d, "page_content", "")]
            
            # Hybrid search: supplement vector search results with top exact keyword search results to guarantee accuracy
            kw_parts = keyword_search(query, k=3)
            for kw in kw_parts:
                if kw not in context_parts:
                    context_parts.append(kw)

            # Prune irrelevant results if query is specifically about leave or food policies
            if "leave" in query_lower and not any(w in query_lower for w in ["driver", "fleet", "maintenance", "insurance"]):
                context_parts = [p for p in context_parts if "driver" not in p.lower() and "maintenance" not in p.lower() and "insurance" not in p.lower() and "appraisal" not in p.lower()]
                kw_parts = [p for p in kw_parts if "driver" not in p.lower() and "maintenance" not in p.lower() and "insurance" not in p.lower() and "appraisal" not in p.lower()]
            if "food" in query_lower or "canteen" in query_lower:
                if not any(w in query_lower for w in ["log", "history", "yesterday", "today", "show", "list"]):
                    context_parts = [p for p in context_parts if "preference" in p.lower() or "veg" in p.lower()]
                    kw_parts = [p for p in kw_parts if "preference" in p.lower() or "veg" in p.lower()]

            if context_parts:
                context_text = "\n\n".join(context_parts)[:12000]
                try:
                    ans = _summary_chain.invoke({"context": context_text, "question": query})
                    # If LLM didn't find the info in hybrid context, fall back to direct keyword match if available
                    if "don't have that information" in ans.lower() or "do not have that information" in ans.lower():
                        if kw_parts:
                            # Let's try running summarization only on the direct keyword results
                            try:
                                return _summary_chain.invoke({"context": "\n\n".join(kw_parts), "question": query})
                            except Exception:
                                return kw_parts[0]
                    return ans
                except Exception as e:
                    logger.error(f"Summarization failed: {e}")
                    return context_parts[0]
    except Exception as err:
        logger.warning(f"Vector search failed: {err}")

    # ── Step 3: Keyword search direct return (no LLM) ──────────────────
    kw_results = keyword_search(query, k=1)
    if kw_results:
        return kw_results[0]

    return "I don't have that information in my knowledge base."


# -----------------------------
# Tool registration
# -----------------------------
rag_tool = Tool(
    name="agnikul_rag_search",
    func=rag_search,
    description="Search the internal Agnikul knowledge base and return a concise factual answer."
)
