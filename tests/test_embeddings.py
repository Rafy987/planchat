import numpy as np

from app.embeddings import EMBEDDING_DIM, embed_texts


def cosine_similarity(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# Uses the REAL model (downloads ~70 MB the first time, then it's cached).
def test_real_model_puts_similar_meaning_close_together():
    question, carpet, roof = embed_texts(
        [
            "What flooring is in Room 204?",
            "Room 204: Carpet Tile CPT-1, Interface",
            "Roof drain detail: cast iron body with dome strainer",
        ]
    )

    assert question.shape == (EMBEDDING_DIM,)
    # The question should be closer in meaning to the carpet chunk than the roof one.
    assert cosine_similarity(question, carpet) > cosine_similarity(question, roof)
