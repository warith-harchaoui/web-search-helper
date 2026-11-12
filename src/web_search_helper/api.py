"""FastAPI HTTP surface (optional ``[api]`` extra), and the ``/gui`` page.

The production server is ``search.php``; this app is the suite's HTTP door to
the same engine, for agents, scripts and local testing without PHP. Every
route has an explicit ``operation_id``: :mod:`web_search_helper.mcp_server`
exposes exactly those as MCP tools, so a route renamed here renames its tool.

- ``POST /query`` speaks ``search.php``'s protocol (``{lang, q, v?}``), so the
  page's ``web-search.js`` can point at it; ``/gui`` does exactly that.
- ``POST /search`` takes a plain question and embeds it server-side, for
  callers without a browser model.
- ``GET /indexes`` lists the indexes served; ``POST /calibrate`` measures
  thresholds (never writes); ``POST /check-online`` audits a deployed site.

Indexes are read from ``WSH_DATA_DIR`` (default ``./search-data``), one
``<lang>.php`` per language, as ``search.php`` reads them.

Run it with::

    pip install 'web-search-helper[api,embed]'
    WSH_DATA_DIR=site/search-data uvicorn web_search_helper.api:app --port 8040

Author: Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, HTMLResponse
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "the HTTP API needs the [api] extra. Run: pip install 'web-search-helper[api]'"
    ) from exc

import numpy as np

from . import __version__
from .calibrate import calibrate as run_calibrate
from .engine import search as run_search
from .index import Index, load
from .site import asset
from .site import check_online as run_check_online

_LANG = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")


def data_dir() -> Path:
    return Path(os.environ.get("WSH_DATA_DIR", "search-data"))


@lru_cache(maxsize=8)
def _index(path: str, mtime: float) -> Index:
    return load(path)


def get_index(lang: str) -> Index:
    if not _LANG.match(lang):
        raise HTTPException(400, "lang")
    p = data_dir() / f"{lang}.php"
    if not p.exists():
        raise HTTPException(404, f"no index for {lang!r} in {data_dir()}")
    return _index(str(p), p.stat().st_mtime)


@lru_cache(maxsize=2)
def _embedder(name: str, browser: str):
    from .embed import make_embedder

    return make_embedder(name, browser)


def embedder_for(idx: Index):
    m = idx.meta["model"]
    return _embedder(m["python"], m["browser"])


class QueryRequest(BaseModel):
    lang: str
    q: str
    v: list[float] | None = None


class SearchRequest(BaseModel):
    lang: str
    question: str
    words_only: bool = False
    explain: bool = False


class CalibrateRequest(BaseModel):
    lang: str
    inside: list[str]
    outside: list[str]


class CheckOnlineRequest(BaseModel):
    base_url: str
    langs: list[str]
    question: str = "test"
    data_dir: str = "search-data"


def create_app() -> FastAPI:
    app = FastAPI(
        title="web-search-helper",
        description="Search a private corpus: excerpts that answer, or an honest refusal.",
        version=__version__,
    )

    @app.get("/indexes", operation_id="indexes")
    def indexes() -> list[dict]:
        """The indexes served: language, model, size and thresholds."""
        out = []
        for p in sorted(data_dir().glob("*.php")):
            try:
                idx = _index(str(p), p.stat().st_mtime)
            except ValueError:
                continue
            out.append(
                {
                    "lang": idx.lang,
                    "model": idx.meta["model"],
                    "passages": len(idx.passages),
                    "windows": len(idx.vectors),
                    "thresholds": idx.meta["thresholds"],
                }
            )
        return out

    @app.post("/query", operation_id="query")
    def query(body: QueryRequest) -> dict:
        """search.php's protocol: a question and, optionally, its vector."""
        idx = get_index(body.lang)
        if len(body.q.strip()) == 0 or len(body.q) > idx.meta["limits"]["q_max"]:
            raise HTTPException(400, "q")
        qv = None
        if body.v is not None:
            if len(body.v) != idx.meta["dim"]:
                raise HTTPException(400, "v")
            qv = np.asarray(body.v, dtype=np.float64)
            n = np.linalg.norm(qv)
            if not n:
                raise HTTPException(400, "v")
            qv = (qv / n).astype(np.float32)
        return run_search(idx, body.q, qv)

    @app.post("/search", operation_id="search")
    def search(body: SearchRequest) -> dict:
        """Ask a question in plain text; the server embeds it."""
        idx = get_index(body.lang)
        qv = None if body.words_only else embedder_for(idx).encode([body.question])[0]
        return run_search(idx, body.question, qv, explain=body.explain)

    @app.post("/calibrate", operation_id="calibrate")
    def calibrate(body: CalibrateRequest) -> dict:
        """Measure the refusal thresholds on two lists of questions (writes nothing)."""
        idx = get_index(body.lang)
        return run_calibrate(idx, body.inside, body.outside, embedder_for(idx))

    @app.post("/check-online", operation_id="check_online")
    def check_online(body: CheckOnlineRequest) -> dict:
        """After an upload: does any byte of the corpus leak, and does search.php answer?"""
        return run_check_online(body.base_url, body.langs, body.question, body.data_dir)

    @app.get("/gui", response_class=HTMLResponse, include_in_schema=False)
    def gui() -> str:
        """The demo page, pointed at /query instead of search.php."""
        html = Path(asset("demo.html")).read_text(encoding="utf-8")
        return html.replace("endpoint: 'search.php'", "endpoint: 'query'")

    @app.get("/web-search.js", include_in_schema=False)
    def client() -> FileResponse:
        return FileResponse(asset("web-search.js"), media_type="text/javascript")

    return app


app = create_app()


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8040")))


if __name__ == "__main__":  # pragma: no cover
    main()
