"""Embedders: one model on the build machine, its twin in the browser.

The index is embedded here, with sentence-transformers; the visitor's question
is embedded in the page, with transformers.js. Both must be the same model,
or cosines compare vectors from two different spaces. ``MODELS`` pairs each
supported Python name with its browser (ONNX) twin.

Long passages are cut into WINDOWS that the model reads entirely (it ignores
everything past its token limit), and a passage scores the best cosine of its
windows. The end offset of each window is kept: it tells the page WHERE in a
passage the answer is, and it bounds the excerpt the server sends back.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from .text import strip_math, tokenize

#: Python model -> transformers.js model of the same weights.
MODELS = {
    "paraphrase-multilingual-MiniLM-L12-v2": "Xenova/paraphrase-multilingual-MiniLM-L12-v2",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": "Xenova/paraphrase-multilingual-MiniLM-L12-v2",
    "all-MiniLM-L6-v2": "Xenova/all-MiniLM-L6-v2",
    "sentence-transformers/all-MiniLM-L6-v2": "Xenova/all-MiniLM-L6-v2",
}
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    name: str  # Python-side model name
    browser: str  # transformers.js model id
    dim: int

    def windows(self, text: str) -> list[int]:
        """End offsets (in characters) of the windows covering ``text``."""

    def encode(self, texts: list[str]) -> np.ndarray:
        """L2-normalised float32 vectors, one row per text."""


class SentenceTransformerEmbedder:
    """A sentence-transformers model, cut into windows by its own tokenizer."""

    def __init__(self, name: str = DEFAULT_MODEL, browser: str | None = None):
        from sentence_transformers import SentenceTransformer

        if browser is None and name not in MODELS:
            raise ValueError(
                f"no known transformers.js twin for {name!r}; pass browser=… "
                f"(known: {', '.join(sorted(set(MODELS)))})"
            )
        self.name = name
        self.browser = browser or MODELS[name]
        self.model = SentenceTransformer(name)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        # Two tokens go to the start and end markers.
        self.window = int(self.model.max_seq_length) - 2

    def windows(self, text: str) -> list[int]:
        tok = self.model.tokenizer
        # Tokenising to CUT, not to encode: lift the length limit for this call
        # only, or every long passage prints a warning. try/finally because
        # the same tokenizer encodes next, where the limit must hold.
        saved = tok.model_max_length
        tok.model_max_length = int(1e9)
        try:
            spans = tok(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
        finally:
            tok.model_max_length = saved
        ends = [spans[min(k + self.window, len(spans)) - 1][1] for k in range(0, len(spans), self.window)]
        # The last window runs to the end of the text: the tokenizer stops at
        # the last non-blank character, and a final sentence would fall out.
        return (ends[:-1] + [len(text)]) if ends else [len(text)]

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(
            texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False
        ).astype(np.float32)


class HashEmbedder:
    """Deterministic bag-of-words vectors, for tests and offline dry runs.

    Not a semantic model: two texts are close when they share words. It lets
    the whole pipeline, PHP included, be tested without downloading weights.
    """

    name = "hash"
    browser = "hash"

    def __init__(self, dim: int = 64, window_words: int = 40):
        self.dim = dim
        self.window_words = window_words

    def windows(self, text: str) -> list[int]:
        ends, count = [], 0
        for k, c in enumerate(text):
            if c.isspace() and k and not text[k - 1].isspace():
                count += 1
                if count % self.window_words == 0:
                    ends.append(k)
        return ends + [len(text)]

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float64)
        for r, t in enumerate(texts):
            for w in tokenize(t):
                h = int.from_bytes(hashlib.blake2b(w.encode(), digest_size=8).digest(), "little")
                out[r, h % self.dim] += 1.0 if (h >> 32) & 1 else -1.0
        n = np.linalg.norm(out, axis=1, keepdims=True)
        out = np.divide(out, n, out=np.zeros_like(out), where=n > 0)
        return out.astype(np.float32)


def window_texts(text: str, ends: list[int]) -> list[str]:
    """The text of each window, formulas reduced to their symbols."""
    starts = [0] + ends[:-1]
    return [strip_math(text[a:b]) for a, b in zip(starts, ends)]
