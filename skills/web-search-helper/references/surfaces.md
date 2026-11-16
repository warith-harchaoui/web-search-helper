# web-search-helper non-CLI surfaces

## 1. Library

```python
import web_search_helper as wsh
```

Public API (`web_search_helper.__all__`): `read_corpus`, `read_jsonl`,
`Passage`, `HashEmbedder`, `SentenceTransformerEmbedder`, `DEFAULT_MODEL`,
`MODELS`, `build`, `from_vectors`, `vectors_from_int8`, `Index`, `save`,
`load`, `search`, `calibrate`, `install`, `serve`, `bench`, `check_online`.

`build` cuts, embeds and indexes passages; `save` writes the index as a PHP
file that answers 404 when requested by URL. `search` is `engine.py`, the
reference twin of `search.php`: same ranking, same verdict, same excerpts,
checked by `tests/test_php_parity.py`. `from_vectors` indexes a corpus whose
windows are already embedded by another pipeline.

Logging and file management route through `os_helper`, the suite convention.

## 2. CLI: click (core)

`web-search-helper`, the single command line, installed with the core
package. See `cli-reference.md`.

## 3. The website: PHP + JavaScript (shipped by `install`)

| File | Runs on | Role |
|---|---|---|
| `search.php` | the PHP host (>= 7.4, mbstring) | BM25 + cosines + fusion + verdict; returns excerpts, or `"sure": false` and nothing else |
| `search-data/<lang>.php` | nowhere: requested by URL it answers 404 | the index |
| `web-search.js` (+ `.d.ts`) | the visitor's browser | embeds the question (transformers.js), composes the extractive answer, optional `Writer` |
| `writer-plan.json` | the visitor's browser | best-engine-ai-helper's ladder for the written answer |

This is the production surface. Everything below is for agents, scripts and
local testing.

## 4. HTTP API: FastAPI (`[api]`)

```bash
pip install 'web-search-helper[api,embed]'
WSH_DATA_DIR=site/search-data web-search-helper-api    # 127.0.0.1:8040, OpenAPI docs at /docs
```

| Method | Route |
|---|---|
| GET | `/health`, `/indexes`, `/gui`, `/web-search.js`, `/writer-plan.json` |
| POST | `/query` (search.php's protocol), `/search` (plain question, embedded server-side) |
| POST | `/calibrate` (writes nothing), `/check-online` |

`--host` / `--port` (or `WSH_HOST` / `WSH_PORT`) move the bind. The
`Dockerfile` and `docker-compose.yml` at the repo root serve this app on
port 8040, indexes mounted read-only.

## 5. MCP: `fastapi-mcp` over the *same* app (`[mcp]`)

```bash
pip install 'web-search-helper[mcp,embed]'
WSH_DATA_DIR=site/search-data web-search-helper-mcp    # MCP at http://127.0.0.1:8041/mcp
```

`web_search_helper.mcp_server` takes the FastAPI app from
`web_search_helper.api` and mounts `FastApiMCP` on it. The tools are an
explicit allowlist of routes: `indexes`, `search`, `calibrate`,
`check_online`. `query` is left out on purpose: it expects the question's
vector, which no agent should be asked to produce.

Register it with Claude Code:

```bash
claude mcp add web-search-helper --transport http http://127.0.0.1:8041/mcp
```

## 6. The `/gui` page (`[api]`)

`GET /gui?lang=fr|en`: the bilingual demo page, pointed at `/query`. The
question is embedded in the browser as on the real site, the answer is
composed from the excerpts, and the written answer is offered when the
machine can bear a model of the plan. See the repo's `GUI.md`.
