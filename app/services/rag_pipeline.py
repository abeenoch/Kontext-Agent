import os
import pdfplumber
import chromadb
from app.utils.text_splitter import split_text
from app.utils.embedding_utils import get_embedding

# Persistent Chroma storage
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
client = chromadb.PersistentClient(path=CHROMA_DIR)


def get_user_collection(user_id: str):
    """
    Create or get the collection specific to a user.
    This keeps each user's documents isolated in their own Chroma namespace.
    """
    collection_name = f"user_{user_id}_docs"
    existing = [c.name for c in client.list_collections()]
    if collection_name not in existing:
        return client.create_collection(name=collection_name)
    return client.get_collection(name=collection_name)


def ingest_file(path: str, user_id: str = "demo"):
    """
    Ingests a file (PDF or text) into the user's Chroma collection.
    Text is chunked and embedded for semantic search later.
    """
    text = ""

    # Read PDF or text file
    if path.lower().endswith(".pdf"):
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                page_text = p.extract_text()
                if page_text:
                    text += page_text + "\n"
    else:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

    # Split and embed text
    chunks = split_text(text, chunk_size=500, overlap=50)
    collection = get_user_collection(user_id)

    ids, metadatas, embeddings = [], [], []
    for i, chunk in enumerate(chunks):
        ids.append(f"{user_id}_{i}")
        metadatas.append({"chunk_index": i})
        embeddings.append(get_embedding(chunk))

    # Add to Chroma collection
    collection.add(documents=chunks, metadatas=metadatas, ids=ids, embeddings=embeddings)
    return {"user_id": user_id, "inserted_chunks": len(chunks)}


def retrieve_for_query(user_id: str, query: str, k: int = 5):
    """
    Retrieve top-k relevant chunks for a given query from the user's collection.
    """
    collection = get_user_collection(user_id)
    q_emb = get_embedding(query)
    results = collection.query(query_embeddings=[q_emb], n_results=k)

    if not results or not results.get("documents"):
        return []

    # Return a list of matched text chunks
    docs = results["documents"][0]
    metadatas = results["metadatas"][0]
    return [{"content": doc, "metadata": meta} for doc, meta in zip(docs, metadatas)]


def retrieve_relevant_docs(user_id: str, query: str, k: int = 5):
    """
    Retrieve the most relevant document chunks for a user based on a query.
    Returns a list of dicts with {content, metadata}.
    """
    user_collection_name = f"user_{user_id}_docs"
    try:
        collection = client.get_collection(user_collection_name)
    except Exception:
        # Fallback to default shared collection
        collection = client.get_or_create_collection(name="kontext")

    q_emb = get_embedding(query)
    results = collection.query(query_embeddings=[q_emb], n_results=k)

    docs = []
    for i in range(len(results["documents"][0])):
        docs.append({
            "content": results["documents"][0][i],
            "metadata": results["metadatas"][0][i]
        })
    return docs
