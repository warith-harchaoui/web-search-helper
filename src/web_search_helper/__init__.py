"""web-search-helper — search a private corpus from a website, PHP only.

Build the index on your machine; serve it with one PHP file; embed the
question in the browser. The corpus is never published: the page receives
short excerpts of what answers the question, or nothing when the corpus does
not treat it.

>>> import web_search_helper as wsh
>>> callable(wsh.build) and callable(wsh.search)
True
"""

from __future__ import annotations

__version__ = "0.1.0"

from .calibrate import calibrate
from .corpus import Passage, read_corpus, read_jsonl
from .embed import DEFAULT_MODEL, MODELS, HashEmbedder, SentenceTransformerEmbedder
from .engine import search
from .index import Index, build, load, save
from .site import bench, check_online, install, serve

__all__ = [
    "DEFAULT_MODEL",
    "MODELS",
    "HashEmbedder",
    "Index",
    "Passage",
    "SentenceTransformerEmbedder",
    "bench",
    "build",
    "calibrate",
    "check_online",
    "install",
    "load",
    "read_corpus",
    "read_jsonl",
    "save",
    "search",
    "serve",
]
