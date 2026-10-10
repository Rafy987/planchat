from functools import cache

from fastembed import TextEmbedding

from app.config import settings

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384  # bge-small turns any text into a list of 384 numbers


@cache  # load the model once, then reuse it (loading takes a few seconds)
def get_model() -> TextEmbedding:
    return TextEmbedding(MODEL_NAME, cache_dir=str(settings.embedding_cache_dir))


def embed_texts(texts: list[str]) -> list:
    """Turn each text into a vector. fastembed processes them in batches for speed."""
    return list(get_model().embed(texts))
