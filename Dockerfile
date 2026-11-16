# syntax=docker/dockerfile:1.6
#
# web-search-helper: container image of the HTTP API (and its /gui page).
#
# The production server of this project is search.php, on any PHP host; this
# image serves the suite's HTTP door to the same engine (engine.py, the
# reference twin of search.php), for agents, scripts and local testing. It
# needs no PHP.
#
# The image installs the [api] extra. Two build-args add the rest:
#   WITH_EMBED=1  the [embed] extra (sentence-transformers, ~2 GB with torch),
#                 needed by POST /search and POST /calibrate, which embed the
#                 question server-side. Without it, POST /query (the question
#                 embedded by the browser, which is what /gui does) and indexes
#                 built with the `hash` model work as they are.
#   WITH_MCP=1    the [mcp] extra; then run `web-search-helper-mcp` instead.
#
# Build:
#   docker build -t web-search-helper .
#   docker build --build-arg WITH_EMBED=1 -t web-search-helper:embed .
#
# Run (HTTP on 0.0.0.0:8040, indexes read from ./search-data):
#   docker run --rm -p 8040:8040 -v "$PWD/search-data:/data/search-data:ro" web-search-helper
#   # open http://localhost:8040/gui?lang=fr
#
# Run the CLI one-shot:
#   docker run --rm -v "$PWD:/work" -w /work web-search-helper \
#     web-search-helper search build/fr.php "a question" --words-only

FROM python:3.12-slim

# Non-root runtime user; the app never needs root at runtime.
RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

# --- deps -------------------------------------------------------------------
# requirements.txt first (core deps only) so this layer caches independently
# of source changes; the package itself, with its extras, comes right below.
COPY --chown=app:app requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# src layout: the package and its assets (search.php, web-search.js, the
# writer plan, the demo page) live under src/.
COPY --chown=app:app pyproject.toml README.md LICENSE ./
COPY --chown=app:app src ./src

ARG WITH_EMBED=0
ARG WITH_MCP=0
RUN extras="api" \
 && if [ "$WITH_EMBED" = "1" ]; then extras="$extras,embed"; fi \
 && if [ "$WITH_MCP" = "1" ]; then extras="$extras,mcp"; fi \
 && pip install --no-cache-dir ".[$extras]"

# --- runtime ----------------------------------------------------------------
USER app
EXPOSE 8040
# One <lang>.php index per language, as search.php reads them; mount the
# site's search-data folder here.
ENV PYTHONUNBUFFERED=1 \
    WSH_DATA_DIR=/data/search-data
VOLUME ["/data/search-data"]

# Default: serve the API on every interface of the container. Override for
# one-shot CLI usage, or with `web-search-helper-mcp --host 0.0.0.0 --port 8041`.
CMD ["web-search-helper-api", "--host", "0.0.0.0", "--port", "8040"]
