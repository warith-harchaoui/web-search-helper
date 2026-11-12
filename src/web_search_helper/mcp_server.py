"""MCP server (optional ``[mcp]`` extra): the API's routes as agent tools.

``fastapi-mcp`` is mounted at ``/mcp`` on a copy of :mod:`web_search_helper.api`'s
app; the tools are exactly the routes listed below, by their ``operation_id``,
so the MCP door can never drift from the REST one.

Run it with::

    pip install 'web-search-helper[mcp,embed]'
    WSH_DATA_DIR=site/search-data uvicorn web_search_helper.mcp_server:app --port 8041

MCP endpoint: ``http://127.0.0.1:8041/mcp`` (Streamable HTTP).

Author: Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import os

try:
    from fastapi_mcp import FastApiMCP
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "the MCP server needs the [mcp] extra. Run: pip install 'web-search-helper[mcp]'"
    ) from exc

from .api import create_app

#: An explicit allowlist: a route added to the API becomes a tool only by a
#: deliberate edit here. ``query`` is left out on purpose: it expects a
#: 384-number vector, which no agent should be asked to produce.
EXPOSED = ["indexes", "search", "calibrate", "check_online"]


def build_server(app):
    mcp = FastApiMCP(app, include_operations=EXPOSED)
    mcp.mount_http()
    return mcp


app = create_app()
build_server(app)


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8041")))


if __name__ == "__main__":  # pragma: no cover
    main()
