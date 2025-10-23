import os 
import pdfplumber
import chromadb
import chromadb
from app.utils.text_splitter import split_text
from app.utils.embedding_utils import get_embedding

CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
client = chromadb.PersistentClient(path=CHROMA_DIR)
collection = client.get_or_create_collection(name="kontext")


def ingest_file(path: str, user_id: str = "demo"):
    text = ""
    if path.lower().endswith(".pdf"):
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                text += p.extract_text() + "\n"
    else:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

    chunks = split_text(text, chunk_size=500, overlap=50)
    ids,metadatas,embeddings = [],[],[]
    for i, chunk in enumerate(chunks):
        ids.append(f"{user_id}_{i}")
        metadatas.append({"chunk": i})
        embeddings.append(get_embedding(chunk))
    collection.add(documents=chunks, metadatas=metadatas, ids=ids, embeddings=embeddings)
    return {"inserted_chunks": len(chunks)}

def retrive_for_query(query, k=5):
    q_emb = get_embedding(query)
    results = collection.query(query_embeddings=[q_emb], n_results=k)
    docs = "\n".join(results['documents'][0])
    return docs

