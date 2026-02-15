"""Embedding utilities with lazy loading."""
_model = None


def get_embedding(text: str):
    """Get embedding for text, lazy-loading model on first use."""
    global _model
    
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    
    return _model.encode([text])[0]
