from sentence_transformers import SentenceTransformer

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("BAAI/bge-base-en")
    return _model


def get_embedding(text: str):
    model = get_model()
    return model.encode(text, normalize_embeddings=True).tolist()