"""The index file: everything the PHP engine needs, in one file it never serves.

The file is a PHP script that, requested by URL, answers 404 and exits. The
data follows ``__halt_compiler();``, which PHP never parses. The corpus is
therefore served in clear at no address, even when the web server ignores the
``.htaccess`` that also denies the folder (an FTP client that skips dotfiles
is enough for that).

Layout after the header (little-endian):

=========  ====================================================================
``WSH1``   magic
u32 + JSON metadata: config, thresholds, passages, section of each passage
u32 × 4    number of vectors, sections, words, bytes of postings
f32        window vectors, ``n_vec × dim``, passages in order
f32        section centroids, ``n_sec × dim``
u32 + str  the lexicon, words joined by ``\\n``, in order of first appearance
u32        ``n_words + 1`` offsets into the postings
(u32,u16)  postings: (passage, term frequency), passages in increasing order
u32        length of each passage in tokens
=========  ====================================================================

Everything that can be computed once is computed here, so that a request only
reads: the lexical index, the section centroids, the window offsets.

>>> from web_search_helper.corpus import Passage
>>> from web_search_helper.embed import HashEmbedder
>>> idx = build([Passage("Un éléphant dans une pièce.", "Doc", "S")], HashEmbedder(), "fr")
>>> data = to_bytes(idx)
>>> data.startswith(HEADER), from_bytes(data).passages[0]["t"]
(True, 'Un éléphant dans une pièce.')
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .corpus import Passage
from .embed import Embedder, window_texts
from .text import stopwords as default_stopwords
from .text import tokenize

#: Requested by URL, the file answers 404 and stops. ``search.php`` checks the
#: same bytes before reading.
HEADER = b"<?php http_response_code(404); exit; __halt_compiler();"
MAGIC = b"WSH1"
FORMAT = 1

#: Thresholds of the "I cannot answer" rule. Defaults are those measured on the
#: corpus this engine was first built for; `calibrate` measures yours.
DEFAULT_THRESHOLDS = {
    "sem_min": 0.55,   # cosine of the best window
    "sec_min": 0.56,   # cosine of the best section centroid
    "lex_min": 5.0,    # BM25 of the best passage, when every word was found
    "df_min": 9,       # one-word query: passages that must contain the word
}
DEFAULT_LIMITS = {"per_hour": 120, "per_day": 400, "q_max": 300}
DEFAULT_RANKING = {"display_k": 6, "pool_k": 25, "answer_pool": 15, "rrf_k": 60}


@dataclass
class Index:
    meta: dict
    passages: list[dict]
    section_of: list[int]
    vectors: np.ndarray            # (n_vec, dim) float32
    centroids: np.ndarray          # (n_sec, dim) float32
    words: list[str]
    postings: dict[str, list[tuple[int, int]]]
    lengths: list[int]
    first_vec: list[int] = field(default_factory=list)

    def __post_init__(self):
        if not self.first_vec:
            cur = 0
            for p in self.passages:
                self.first_vec.append(cur)
                cur += len(p["o"])
            if cur != len(self.vectors):
                raise ValueError(f"{cur} windows announced, {len(self.vectors)} vectors")

    @property
    def lang(self) -> str:
        return self.meta["lang"]

    @property
    def stop(self) -> frozenset[str]:
        return frozenset(self.meta["stopwords"])


def build(passages: list[Passage], embedder: Embedder, lang: str,
          stop: frozenset[str] | None = None, thresholds: dict | None = None,
          limits: dict | None = None, ranking: dict | None = None,
          batch: int = 256) -> Index:
    """Cut, embed and index ``passages``."""
    if not passages:
        raise ValueError("empty corpus")
    stop = default_stopwords(lang) if stop is None else stop
    rows = [p.to_dict() for p in passages]

    texts: list[str] = []
    for r in rows:
        ends = embedder.windows(r["t"])
        r["o"] = ends
        texts.extend(window_texts(r["t"], ends))
    vecs = np.concatenate([embedder.encode(texts[k:k + batch])
                           for k in range(0, len(texts), batch)]).astype(np.float32)

    # Sections in order of first appearance; a centroid is the normalised sum
    # of the section's windows. It judges whether a whole SECTION is about the
    # question, which a single window can seem to be by accident of vocabulary.
    keys: dict[tuple[str, str], int] = {}
    section_of = [keys.setdefault((r["c"], r["s"]), len(keys)) for r in rows]
    cents = np.zeros((len(keys), vecs.shape[1]), dtype=np.float64)
    cur = 0
    for r, s in zip(rows, section_of):
        n = len(r["o"])
        cents[s] += vecs[cur:cur + n].sum(axis=0)
        cur += n
    norms = np.linalg.norm(cents, axis=1, keepdims=True)
    cents = np.divide(cents, norms, out=np.zeros_like(cents), where=norms > 0).astype(np.float32)

    words: list[str] = []
    postings: dict[str, list[tuple[int, int]]] = {}
    lengths: list[int] = []
    for i, r in enumerate(rows):
        toks = tokenize(r["t"], stop)
        lengths.append(len(toks) or 1)
        tf: dict[str, int] = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        for w, c in tf.items():
            if w not in postings:
                postings[w] = []
                words.append(w)
            postings[w].append((i, c))

    meta = {
        "format": FORMAT,
        "lang": lang,
        "dim": int(vecs.shape[1]),
        "model": {"python": embedder.name, "browser": embedder.browser},
        "stopwords": sorted(stop),
        "thresholds": {**DEFAULT_THRESHOLDS, **(thresholds or {})},
        "limits": {**DEFAULT_LIMITS, **(limits or {})},
        "ranking": {**DEFAULT_RANKING, **(ranking or {})},
        "avg_len": sum(lengths) / len(lengths),
    }
    return Index(meta, rows, section_of, vecs, cents, words, postings, lengths)


def to_bytes(idx: Index) -> bytes:
    meta = json.dumps({**idx.meta, "passages": idx.passages, "section": idx.section_of},
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    lex = "\n".join(idx.words).encode("utf-8")
    offsets, blob = [], bytearray()
    for w in idx.words:
        offsets.append(len(blob))
        for i, c in idx.postings[w]:
            blob += struct.pack("<IH", i, min(c, 65535))
    offsets.append(len(blob))
    return b"".join([
        HEADER, MAGIC, struct.pack("<I", len(meta)), meta,
        struct.pack("<IIII", len(idx.vectors), len(idx.centroids), len(idx.words), len(blob)),
        idx.vectors.astype("<f4").tobytes(), idx.centroids.astype("<f4").tobytes(),
        struct.pack("<I", len(lex)), lex,
        struct.pack(f"<{len(offsets)}I", *offsets), bytes(blob),
        struct.pack(f"<{len(idx.lengths)}I", *idx.lengths),
    ])


def from_bytes(data: bytes) -> Index:
    if not data.startswith(HEADER) or data[len(HEADER):len(HEADER) + 4] != MAGIC:
        raise ValueError("not a web-search-helper index")
    o = len(HEADER) + 4
    (lm,) = struct.unpack_from("<I", data, o)
    o += 4
    meta = json.loads(data[o:o + lm])
    o += lm
    n_vec, n_sec, n_words, n_blob = struct.unpack_from("<IIII", data, o)
    o += 16
    dim = meta["dim"]
    vecs = np.frombuffer(data, "<f4", n_vec * dim, o).reshape(n_vec, dim)
    o += n_vec * dim * 4
    cents = np.frombuffer(data, "<f4", n_sec * dim, o).reshape(n_sec, dim)
    o += n_sec * dim * 4
    (ll,) = struct.unpack_from("<I", data, o)
    o += 4
    words = data[o:o + ll].decode("utf-8").split("\n") if ll else []
    o += ll
    offsets = struct.unpack_from(f"<{n_words + 1}I", data, o)
    o += 4 * (n_words + 1)
    blob = data[o:o + n_blob]
    o += n_blob
    postings = {}
    for k, w in enumerate(words):
        postings[w] = [struct.unpack_from("<IH", blob, j)
                       for j in range(offsets[k], offsets[k + 1], 6)]
    passages = meta.pop("passages")
    section_of = meta.pop("section")
    lengths = list(struct.unpack_from(f"<{len(passages)}I", data, o))
    return Index(meta, passages, section_of, np.array(vecs), np.array(cents),
                 words, postings, lengths)


def save(idx: Index, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(to_bytes(idx))
    tmp.replace(path)
    return path


def load(path: str | Path) -> Index:
    return from_bytes(Path(path).read_bytes())
