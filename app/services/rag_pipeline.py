import os
import pdfplumber
import chromadb
from app.utils.text_splitter import split_text
from app.utils.embedding_utils import get_embedding

# Initialize Chroma client and collection
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
client = chromadb.PersistentClient(path=CHROMA_DIR)
collection = client.get_or_create_collection(name="kontext")


def ingest_file(path: str, user_id: str = "demo"):
    """
    Ingest a document (PDF or TXT) into the Chroma vector store for the given user.
    If the user already has documents, their previous ones are cleared first.
    """
    
    text = ""
    if path.lower().endswith(".pdf"):
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                text += (p.extract_text() or "") + "\n"
    else:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

    
    chunks = split_text(text, chunk_size=500, overlap=50)

    
    try:
        existing = collection.get(where={"user_id": user_id})
        if existing and len(existing.get("ids", [])) > 0:
            collection.delete(ids=existing["ids"])
            print(f"Cleared {len(existing['ids'])} old docs for {user_id}")
    except Exception as e:
        print(f"[WARN] Failed to clear old docs: {e}")

   
    ids, metadatas, embeddings = [], [], []
    for i, chunk in enumerate(chunks):
        ids.append(f"{user_id}_{i}")
        metadatas.append({"chunk": i, "user_id": user_id})
        embeddings.append(get_embedding(chunk))

    collection.add(
        documents=chunks,
        metadatas=metadatas,
        ids=ids,
        embeddings=embeddings,
    )
    return {"inserted_chunks": len(chunks)}


def retrieve_relevant_docs(user_id: str, query: str, k: int = 5):
    """Retrieve top-k relevant chunks for the user's query."""
    q_emb = get_embedding(query)
    try:
        results = collection.query(
            query_embeddings=[q_emb],
            where={"user_id": user_id},
            n_results=k,
        )
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        return [{"content": doc, "metadata": meta} for doc, meta in zip(documents, metadatas)]
    except Exception as e:
        print(f"[RAG Error] {e}")
        return []


def clear_user_docs(user_id: str):
    """Manually clear all documents for a given user."""
    try:
        existing = collection.get(where={"user_id": user_id})
        if existing and len(existing.get("ids", [])) > 0:
            collection.delete(ids=existing["ids"])
            return {"deleted": len(existing["ids"])}
    except Exception as e:
        print(f"[WARN] Failed to clear user docs: {e}")
    return {"deleted": 0}
