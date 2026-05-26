import os
import shutil
import json
import logging
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "chroma_langchain_db_user_local"))
DATASET_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "dataset.json"))

COLLECTION_NAME = "agnikul_data"

embeddings = OllamaEmbeddings(
    model="mxbai-embed-large",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
)

logger = logging.getLogger("orchestrator")

_vector_store = None
_retriever = None

def build_db_from_scratch():
    logger.info(f"Building vector database from {DATASET_PATH}...")
    try:
        if os.path.exists(DB_PATH):
            shutil.rmtree(DB_PATH)
    except Exception as err:
        logger.error(f"Failed to clear corrupt directory {DB_PATH}: {err}")
    
    try:
        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as err:
        logger.error(f"Failed to read dataset.json: {err}")
        data = []
    
    documents = []
    for item in data:
        text_blocks = []
        if item.get("title"):
            text_blocks.append(item["title"])
        if item.get("content"):
            text_blocks.append(item["content"])
        
        questions = item.get("questions", [])
        if isinstance(questions, list) and questions:
            text_blocks.append("Related questions:")
            for q in questions:
                text_blocks.append(f"- {q}")
        
        keywords = item.get("keywords", [])
        if isinstance(keywords, list) and keywords:
            text_blocks.append("Keywords: " + ", ".join(keywords))
        
        text = "\n".join(text_blocks).strip()
        if text:
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "id": str(item.get("id") or ""),
                        "source": str(item.get("source") or ""),
                        "intent_tags": ",".join(item.get("intent_tags", [])) if item.get("intent_tags") else ""
                    }
                )
            )
            
    try:
        store = Chroma(
            persist_directory=DB_PATH,
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME
        )
        if documents:
            store.add_documents(documents)
        logger.info("Vector database successfully rebuilt.")
        return store
    except Exception as err:
        logger.error(f"Failed to build vector database: {err}")
        return None


def _load_vector_store():
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    try:
        store = Chroma(
            persist_directory=DB_PATH,
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME
        )
        _ = store.similarity_search("test", k=1)
        _vector_store = store
        return _vector_store
    except Exception as err:
        logger.error(f"Chroma DB load failed ({err}). Attempting to rebuild...")
        _vector_store = build_db_from_scratch()
        return _vector_store


def get_vector_retriever():
    global _retriever
    if _retriever is not None:
        return _retriever

    store = _load_vector_store()
    if store is None:
        return None

    try:
        _retriever = store.as_retriever(search_kwargs={"k": 5})
        return _retriever
    except Exception as err:
        logger.error(f"Failed to create vector retriever: {err}")
        return None
