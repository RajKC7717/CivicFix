"""Text embedding for deduplication, with a pluggable backend.

Two implementations satisfy the same interface:

``LexicalEmbedder`` (default)
    Stateless hashed n-grams over the *canonical English* text produced by
    :mod:`app.pipeline.lexicon`. Needs no training, no model download and no
    network, costs ~0 ms, and is fully deterministic - the same complaint always
    embeds to the same vector, today and at the demo. Because it runs on the
    normalised English summary rather than raw text, it is still cross-lingual.

``SentenceTransformerEmbedder`` (optional)
    ``paraphrase-multilingual-MiniLM-L12-v2``, used automatically when
    ``sentence-transformers`` is installed and the weights are already cached
    locally. Better on paraphrases the lexicon has not seen; costs ~3 GB of disk.

The default is deliberately the offline one (PLAN.md D1/D2): a demo that cannot
fail beats a marginally better similarity score.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Encodes texts into L2-normalised vectors whose dot product is cosine."""

    name: str

    def encode(self, texts: list[str]) -> Any:
        """Return a matrix with one row per input text."""


class LexicalEmbedder:
    """Hashed word + character n-grams. Stateless, deterministic, offline.

    Word n-grams carry the civic concepts ("open manhole", "katraj dairy");
    character n-grams absorb spelling drift ("kondhwa" / "kondhawa"). The two
    are blended and L2-normalised so a dot product is a cosine similarity.
    """

    name = "lexical-hashing-v1"
    n_features = 2**17
    word_weight = 0.65
    char_weight = 0.35

    def __init__(self) -> None:
        self._word = HashingVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            n_features=self.n_features,
            alternate_sign=False,
            norm=None,
            lowercase=True,
        )
        self._char = HashingVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            n_features=self.n_features,
            alternate_sign=False,
            norm=None,
            lowercase=True,
        )

    def encode(self, texts: list[str]) -> Any:
        safe = [t if (t and t.strip()) else "empty" for t in texts]
        word = normalize(self._word.transform(safe))
        char = normalize(self._char.transform(safe))
        return normalize(word * self.word_weight + char * self.char_weight)


class SentenceTransformerEmbedder:
    """Neural multilingual encoder. Only used when already installed and cached."""

    name = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, model: Any) -> None:
        self._model = model

    def encode(self, texts: list[str]) -> Any:
        safe = [t if (t and t.strip()) else "empty" for t in texts]
        vectors = self._model.encode(safe, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)


def _try_sentence_transformer() -> Embedder | None:
    """Load the neural encoder only if it is installed AND already downloaded.

    Never triggers a download: an unexpected 400 MB fetch in the middle of a
    live demo is exactly the failure mode this project is built to avoid.
    """
    try:  # pragma: no cover - exercised only on machines with the extra installed
        import os

        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    try:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        model = SentenceTransformer(SentenceTransformerEmbedder.name)
        logger.info("Using neural embedder: %s", SentenceTransformerEmbedder.name)
        return SentenceTransformerEmbedder(model)
    except Exception as exc:  # noqa: BLE001 - any failure means "use the fallback"
        logger.info("Neural embedder unavailable (%s); using lexical embedder", exc)
        return None


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Return the process-wide embedder, preferring the neural one if present."""
    global _embedder
    if _embedder is None:
        _embedder = _try_sentence_transformer() or LexicalEmbedder()
    return _embedder


def similarity(a: Any, b: Any) -> np.ndarray:
    """Cosine similarity matrix between two encoded batches.

    Both backends return L2-normalised rows, so the dot product *is* cosine.
    Works for scipy sparse and numpy dense alike.
    """
    product = a @ b.T
    dense = product.toarray() if hasattr(product, "toarray") else np.asarray(product)
    return np.clip(dense, 0.0, 1.0)


def reset_embedder() -> None:
    """Test hook: drop the cached embedder."""
    global _embedder
    _embedder = None
