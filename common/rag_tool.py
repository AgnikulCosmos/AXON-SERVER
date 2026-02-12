
# rag_tool.py
from langchain_core.tools import Tool
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
import traceback
from common.vector import retriever, vector_store

# -----------------------------
# LLM for factual summarization
# -----------------------------
_summarizer_llm = ChatOllama(
    model="qwen2.5:3b",
    temperature=0,
    base_url="http://ollama:11434"
)

_summary_template = """
You are a factual assistant.

Answer the user's question using ONLY the information provided below.
If the information is missing, respond with:
"Information not available in the knowledge base."

Do NOT mention sources.
Do NOT say "not in context".
Do NOT add explanations outside the answer.

Context:
{context}

Question:
{question}

Answer:
"""

_prompt = PromptTemplate.from_template(_summary_template)
_summary_chain = _prompt | _summarizer_llm | StrOutputParser()

# -----------------------------
# Retrieval
# -----------------------------
def retrieve_documents(query: str, k: int = 5):
    try:
        return retriever.invoke(query)
    except Exception:
        try:
            return vector_store.similarity_search(query, k=k)
        except Exception:
            return []

# -----------------------------
# RAG entry point
# -----------------------------
def rag_search(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        return "Invalid query."

    try:
        docs = retriever.invoke(query)
    except Exception as e:
        return f"RAG retrieval error:\n{traceback.format_exc()}"

    if not docs:
        return "Information not available in the knowledge base."

    # Build context strictly from retrieved content
    context_parts = []
    for d in docs:
        text = getattr(d, "page_content", None)
        if text:
            context_parts.append(text)

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
        return "Information not available in the knowledge base."

# -----------------------------
# Tool registration
# -----------------------------
rag_tool = Tool(
    name="agnikul_rag_search",
    func=rag_search,
    description="Search the internal Agnikul knowledge base and return a concise factual answer."
)














#from langchain_core.tools import Tool
# from common.vector import retriever
# import traceback

# def rag_search(query: str) -> str:
#     if not isinstance(query, str) or not query.strip():
#         return "Invalid query."

#     try:
#         docs = retriever.invoke(query)
#         print(f"[RAG] Retrieved {len(docs)} docs")
#     except Exception:
#         return "Information not available in the knowledge base."

#     if not docs:
#         return "Information not available in the knowledge base."

#     context_parts = []
#     for d in docs:
#         text = getattr(d, "page_content", None)
#         if text:
#             context_parts.append(text)

#     context_text = "\n\n".join(context_parts)

#     MAX_CHARS = 12000
#     if len(context_text) > MAX_CHARS:
#         context_text = context_text[:MAX_CHARS]

#     return context_text


# rag_tool = Tool(
#     name="agnikul_rag_search",
#     func=rag_search,
#     description=(
#         "Retrieve relevant internal Agnikul knowledge. "
#         "Returns raw factual context for the LLM to summarize."
#     )
# )
