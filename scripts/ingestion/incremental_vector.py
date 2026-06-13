from pathlib import Path
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document

# Resolve paths safely
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_PATH = BASE_DIR / "dataset.json"
CHROMA_PATH = BASE_DIR / "chroma_langchain_db"


def add_new_vectors(entries: list):
    import os
    import chromadb
    embeddings = OllamaEmbeddings(model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"))

    host = os.getenv("CHROMA_SERVER_HOST")
    port = os.getenv("CHROMA_SERVER_PORT", "8000")
    
    if not host:
        if os.path.exists('/.dockerenv'):
            host = "chroma"
            port = "8000"
        else:
            host = "127.0.0.1"
            port = "8007"
            
    try:
        client = chromadb.HttpClient(host=host, port=int(port))
        client.heartbeat()
        db = Chroma(
            client=client,
            embedding_function=embeddings
        )
    except Exception as err:
        print(f"Could not connect to ChromaDB server at http://{host}:{port} ({err}). Falling back to local file DB.")
        db = Chroma(
            persist_directory=str(CHROMA_PATH),
            embedding_function=embeddings
        )

    # Fetch existing IDs from vector DB
    existing = db.get(include=["metadatas"])
    existing_ids = {
        m["id"]
        for m in existing.get("metadatas", [])
        if m and "id" in m
    }

    docs_to_add = []

    for entry in entries:
        entry_id = entry["id"]
        if entry_id in existing_ids:
            continue  # already embedded

        docs_to_add.append(
            Document(
                page_content=f"{entry['title']}\n{entry['content']}",
                metadata={
                    "id": entry_id,
                    "source": entry.get("source"),
                }
            )
        )

    if not docs_to_add:
        print("No new vectors to add.")
        return

    db.add_documents(docs_to_add)

    print(f"Added {len(docs_to_add)} new vectors.")
