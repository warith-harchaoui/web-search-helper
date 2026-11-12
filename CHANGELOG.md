# Changelog

## [Unreleased]

- Joins the AI Helpers suite: agent skill (`skills/web-search-helper/`),
  `CITATION.cff`, CI running the PHP parity test on every push.
- English tested like French: parity test over both languages; on the
  book this tool was extracted from, 15/15 English and 19/19 French guard
  questions fall on the right side (answer or refusal).
- Bilingual demo page (`?lang=fr` / `?lang=en`).
- Default `sec_min` 0.561, the value measured on that book.
- `bench` warns when pcov or xdebug distorts the timing.
- `install` accepts an index built straight into the site folder.

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
