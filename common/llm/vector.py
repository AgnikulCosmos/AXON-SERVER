import os
import shutil
import json
import logging
import time
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "chroma_langchain_db_user_local"))
DATASET_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "dataset.json"))

COLLECTION_NAME = "agnikul_data"

from common.llm.ollama_helper import get_working_ollama_base_url

embeddings = OllamaEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "mxbai-embed-large"),
    base_url=get_working_ollama_base_url()
)

logger = logging.getLogger("orchestrator")

_vector_store = None
_retriever = None

def get_chroma_store(embedding_function=embeddings):
    import chromadb
    host = os.getenv("CHROMA_SERVER_HOST")
    port = os.getenv("CHROMA_SERVER_PORT", "8000")
    
    # Auto-resolve host/port if not explicitly set
    if not host:
        if os.path.exists('/.dockerenv'):
            host = "chroma"
            port = "8000"
        else:
            host = "127.0.0.1"
            port = "8007"
            
    # Try connecting to HTTP Chroma server
    try:
        client = chromadb.HttpClient(host=host, port=int(port))
        client.heartbeat()
        logger.info(f"Connected to dockerized ChromaDB server at http://{host}:{port}")
        return Chroma(
            client=client,
            embedding_function=embedding_function,
            collection_name=COLLECTION_NAME
        )
    except Exception as err:
        logger.warning(f"Could not connect to ChromaDB server at http://{host}:{port} ({err}). Falling back to local file DB.")
        return Chroma(
            persist_directory=DB_PATH,
            embedding_function=embedding_function,
            collection_name=COLLECTION_NAME
        )

def build_db_from_scratch():
    logger.info(f"Building vector database from {DATASET_PATH}...")
    
    store = get_chroma_store()
    if store is None:
        logger.error("Failed to initialize Chroma store.")
        return None
        
    try:
        # Clear existing collection if it exists
        try:
            store.delete_collection()
        except Exception:
            pass
        
        # Clean up local directory if it exists and we fall back
        if os.path.exists(DB_PATH):
            try:
                shutil.rmtree(DB_PATH)
            except Exception as err:
                logger.error(f"Failed to clear corrupt local directory {DB_PATH}: {err}")
                
        # Re-initialize store after cleanup
        store = get_chroma_store()
    except Exception as err:
        logger.warning(f"Cleanup during scratch rebuild failed: {err}")
    
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
        if documents and store is not None:
            batch_size = 50
            total_docs = len(documents)
            for i in range(0, total_docs, batch_size):
                batch = documents[i : i + batch_size]
                store.add_documents(batch)
                logger.info(f"Successfully indexed batch {i // batch_size + 1}/{(total_docs + batch_size - 1) // batch_size} ({min(i + batch_size, total_docs)}/{total_docs} docs)")
        logger.info("Vector database successfully rebuilt.")
        return store
    except Exception as err:
        logger.error(f"Failed to build vector database: {err}")
        return None


import threading

_db_building = False

def build_db_in_background():
    global _db_building
    if _db_building:
        return
    _db_building = True

    def run():
        global _vector_store, _db_building
        for attempt in range(1, 6):
            try:
                logger.info(f"Starting background vector store rebuild (attempt {attempt}/5)...")
                store = build_db_from_scratch()
                if store is not None:
                    rebuilt_marker = os.path.join(DB_PATH, ".rebuilt_v3")
                    try:
                        os.makedirs(DB_PATH, exist_ok=True)
                        with open(rebuilt_marker, "w") as f:
                            f.write("rebuilt")
                    except Exception:
                        pass
                    _vector_store = store
                    logger.info("Background vector store rebuild complete!")
                    break
                else:
                    logger.warning(f"Background build attempt {attempt} returned None. Retrying in 10s...")
                    time.sleep(10)
            except Exception as e:
                logger.error(f"Background vector store build failed on attempt {attempt}: {e}")
                if attempt < 5:
                    time.sleep(10)
        _db_building = False

    t = threading.Thread(target=run, daemon=True)
    t.start()


def _load_vector_store():
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    # If Chroma is running in docker or reachable via port 8007, load it
    try:
        store = get_chroma_store()
        # Verify it works
        _ = store.similarity_search("test", k=1)
        _vector_store = store
        return _vector_store
    except Exception as err:
        logger.error(f"Chroma DB load/validation failed ({err}). Rebuilding in background...")

    build_db_in_background()
    return None


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
