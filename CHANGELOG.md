# Changelog

## [Unreleased]

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
