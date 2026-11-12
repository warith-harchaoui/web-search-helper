# Changelog

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
