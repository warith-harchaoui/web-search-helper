# Changelog

## [Unreleased]

### Added

- Every command line ends its `--help` on one line, after a blank one: `⭐️ on GitHub: https://github.com/warith-harchaoui/web-search-helper`. A test checks it for each console script. README.md and LISEZMOI.md carry one invitation to star the repository, right after the paragraph that says what the tool does.

## [0.3.0] — 2026-11-16

The repository follows the suite's reference member (audio-helper) file for
file. Nothing changes in the search itself: `search.php`, `engine.py` and
`web-search.js` answer exactly as in 0.2.0.

- CI renamed `ci.yml` (badges follow): ruff pinned to 0.15.21, tests on
  Python 3.10 and 3.13, PHP checked before the parity test.
- Depends on `os-helper>=4.2,<5`, like every member: directories, copies,
  existence checks and the bench's temporary PHP file go through it, and so
  do the logs (`osh.info`, `osh.warning`, `osh.error`). The bench's warnings
  still reach stderr by default; the new info lines stay silent unless
  `osh.verbosity(1)` asks for them.
- `requirements.txt` (the core dependencies, mirrored from `pyproject.toml`
  and checked by `tests/test_requirements_mirror_pyproject.py`),
  `requirements-dev.txt`, `environment.yaml`, and in `assets/` the Poetry
  helpers `requirements_to_toml.py` and `manual_poetry.sh`.
- `CODING.md` (the suite's coding standard) and `CONTRIBUTING.md`, which
  states the parity rule: a change to ranking, verdict, excerpts or tokenizer
  lands in `engine.py` and `search.php` in the same commit.
- Fix: `web-search-helper-api --help` and `web-search-helper-mcp --help`
  started a server and never returned. Both are click commands now, with
  `--host` and `--port` (also `WSH_HOST`, `WSH_PORT`; `PORT` still works);
  `tests/test_every_command_answers_help.py` runs every console script with
  `--help` under a timeout.
- Fix: `/gui` never offered the written answer, because the API did not
  serve the `writer-plan.json` that `web-search.js` fetches next to itself.
  It does now, and the API gains `GET /health` (not an MCP tool).
- `Dockerfile` and `docker-compose.yml`: the HTTP API on port 8040, indexes
  mounted read-only from `./search-data` (`WSH_DATA_DIR`), a healthcheck on
  `/health`; build-args `WITH_EMBED=1` and `WITH_MCP=1` add those extras.
- `scripts/check_triggers.py`, run by `tests/test_skill.py`: every capability
  must be named in the skill's description, under the 1024-character cap,
  with a SKIP clause, and `TRIGGERS.md` must mirror the skill's copy. It found
  two capabilities the description left out, the written answer in the
  browser and the leak check after upload; both are named now, and in the
  trigger catalogue. `skills/README.md` (installing the skill) and
  `references/surfaces.md` (library, website files, HTTP API, MCP, `/gui`).
- Two more guards from audio-helper: `tests/test_doc_commands.py` parses every
  `web-search-helper <sub>` line in the fenced blocks of the READMEs, the
  examples, `GUI.md`, `CONTRIBUTING.md` and the skill against the click
  definitions (40 lines, all valid); `tests/test_readme_install_pin.py`
  refuses a Markdown file that pins this package to a git tag instead of
  `pip install web-search-helper`.
- `GUI.md`: the `/gui` page, what it shows (two-pass search, excerpts or
  refusal, extractive answer, written answer when the machine can bear it)
  and what it deliberately leaves out.
- `assets/diagrams/how-it-works` and `comment-ca-marche` (SVG, PNG): your
  machine indexes, the PHP server searches and judges, the visitor's browser
  embeds the question and composes the answer. Shown under "How it works" /
  "Comment ça marche", next to a new "The Promise" / "La promesse": what is
  guaranteed private, what travels (model weights), what remains possible
  (patient scraping).

## [0.2.0] — 2026-11-15

First release on PyPI.

- A pre-push gate (ruff, then the full test suite on the commit being
  pushed), a test that refuses any machine path or hard-coded absolute path
  in tracked files, and CI actions off Node 20, as across the suite.

- The bandwidth probe measures the line the way the model will load: one
  Range request per weight shard, all at once, timed from the first byte.
  On livre-elephant the old probe (one shard, whole request) said 5.4 MB/s
  where the model's 3.1 GB came down at 18 MB/s, and withheld the writer
  from a line that could take it; the new one reads 11 to 23 MB/s there.
  `measureBandwidth` takes one URL or several.
- Excerpts never cut a TeX formula. A window bound inside `$$…$$`, `\[…\]`
  or `\(…\)` moves out of it, in search.php and engine.py alike. Found on a
  book whose display formulas run past the 400 characters that sentence
  snapping looks ahead: 8 excerpts out of 486 ended half way through one,
  which KaTeX then printed raw.
- `from_vectors` and `vectors_from_int8`: build an index from embeddings a
  site already computes, without re-embedding (and with the same vectors, to
  compare engines). Window ends may repeat: an empty window left by another
  pipeline keeps its vector aligned.
- Optional written answer in the visitor's browser: `Writer`, `chooseRung`,
  `probeDevice`, `measureBandwidth`, `checkGrounding`, and a button in
  `mount(..., { writer: true })`. The model comes from `writer-plan.json`,
  best-engine-ai-helper's ladder for the `rag-answer` usage (Gemma 4 E4B
  then E2B, q4f16 or q4, ranked by scores measured on the task; LFM2 1.2B
  measured and left out), chosen at run time from WebGPU,
  shader-f16, device memory, storage, mobile, data saver, the cache and the
  bandwidth measured on the model's own files. `chooseRung` is checked
  against best-engine's `browser.choose` on 2 251 simulated devices. A
  written answer whose sentences the cited excerpts do not support is set
  aside. `install` copies the plan.
- `scripts/eval_writer.py` measures each rung on a corpus's own questions in
  Chrome on WebGPU (an answer counts when grounded and in the question's
  language); `scripts/make_writer_plan.py` regenerates the plan and the
  parity fixture from best-engine-ai-helper.
- Joins the AI Helpers suite: agent skill (`skills/web-search-helper/`),
  `CITATION.cff`, CI running the PHP parity test on every push.
- English tested like French: parity test over both languages; on the
  book this tool was extracted from, 15/15 English and 19/19 French guard
  questions fall on the right side (answer or refusal).
- Bilingual demo page (`?lang=fr` / `?lang=en`).
- Default `sec_min` 0.561, the value measured on that book.
- `bench` warns when pcov or xdebug distorts the timing.
- `install` accepts an index built straight into the site folder; `--demo`
  copies the bilingual demo page, now a package asset.
- HTTP API (`web-search-helper-api`, `[api]`) with a `/gui` page, and MCP
  server (`web-search-helper-mcp`, `[mcp]`), as across the suite.
- `TRIGGERS.md`, mirrored into the skill and checked by a test.
- Fix: the hash test embedder records its parameters in the index, so an
  index built at 32 dimensions is queried at 32.

## [0.1.0] — 2026-11-12

First version, extracted from the search engine of a book's companion
website.

- `build`: JSONL, Markdown or text corpus → one index file per language, a PHP
  script that answers 404 when requested by URL.
- `search.php`: BM25 with conjunctive pass and typo tolerance, best-window and
  section cosines, reciprocal rank fusion, "I cannot answer" verdict, excerpts
  of at most two windows, quota per address.
- `web-search.js` (+ `.d.ts`): question embedding with transformers.js,
  two-step query (words, then meaning), extractive answer composition, minimal
  widget.
- `calibrate`: thresholds measured halfway between questions the corpus answers
  and questions it does not.
- `bench`, `serve`, `install`, `check-online`.
- `engine.py`, the Python twin of `search.php`, checked against it by
  `tests/test_php_parity.py`.
