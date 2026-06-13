from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
import json
import os

DATASET_PATH = "dataset.json"
DB_PATH = "./chroma_langchain_db_user"
COLLECTION_NAME = "agnikul_data"

embeddings = OllamaEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
)


def safe_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


if not os.path.exists(DATASET_PATH):
    raise FileNotFoundError(f"{DATASET_PATH} not found")


with open(DATASET_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

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
                    "id": safe_str(item.get("id")),
                    "source": safe_str(item.get("source")),
                    "intent_tags": ",".join(item.get("intent_tags", [])) if item.get("intent_tags") else ""
                }
            )
        )

def get_chroma_store():
    import chromadb
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
        print(f"Connected to ChromaDB server at http://{host}:{port}")
        
        # Delete existing collection to rebuild clean
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
            
        return Chroma(
            client=client,
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME
        )
    except Exception as err:
        print(f"Could not connect to ChromaDB server at http://{host}:{port} ({err}). Falling back to local file DB.")
        import shutil
        if os.path.exists(DB_PATH):
            try:
                shutil.rmtree(DB_PATH)
            except Exception as e:
                print(f"Warning: Could not clear local DB directory {DB_PATH}: {e}")
        return Chroma(
            persist_directory=DB_PATH,
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME
        )


print(f"Prepared {len(documents)} documents for embedding")

vector_store = get_chroma_store()
vector_store.add_documents(documents)

print("Vector database rebuilt successfully.")
