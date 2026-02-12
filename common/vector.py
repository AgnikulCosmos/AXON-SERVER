import os
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "chroma_langchain_db"))

COLLECTION_NAME = "agnikul_data"

embeddings = OllamaEmbeddings(
    model="mxbai-embed-large",
    base_url="http://ollama:11434"
)
vector_store = Chroma(
    persist_directory=DB_PATH,
    embedding_function=embeddings,
    collection_name=COLLECTION_NAME
)

retriever = vector_store.as_retriever(search_kwargs={"k": 5})
