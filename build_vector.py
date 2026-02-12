from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
import json
import os

DATASET_PATH = "dataset.json"
DB_PATH = "./chroma_langchain_db"
COLLECTION_NAME = "agnikul_data"

embeddings = OllamaEmbeddings(
    model="mxbai-embed-large",
    base_url="http://ollama:11434"
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

print(f"Prepared {len(documents)} documents for embedding")

vector_store = Chroma(
    persist_directory=DB_PATH,
    embedding_function=embeddings,
    collection_name=COLLECTION_NAME
)

vector_store.add_documents(documents)


print("Vector database rebuilt successfully.")
