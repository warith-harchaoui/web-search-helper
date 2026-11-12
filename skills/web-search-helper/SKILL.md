---
name: web-search-helper
description: >-
  Add a search box to a website over a corpus that must NOT be published (a
  manuscript, a course, an internal knowledge base), when the host offers PHP
  and nothing else. Indexes locally, serves from one PHP file, embeds the
  question in the browser, returns short excerpts or an honest "I cannot
  answer", and composes an extractive answer (no LLM).
  Fires on "search my book / course / docs from my website", "RAG without a
  backend", "semantic search in PHP", "client-side search without publishing
  the corpus", "the search JSON exposes my whole text", "calibrate the 'I
  don't know' threshold", "rechercher dans mon livre depuis mon site",
  "recherche sémantique en PHP", and on `web-search-helper`, `import
  web_search_helper as wsh`. Do NOT use to choose a vector database
  (ann-router), to run a local LLM (best-engine-ai-helper), or for a public
  static site whose corpus may be shipped whole (a client-only index fits
  there). The trigger catalogue is in `references/triggers.md`.
license: BSD-3-Clause
metadata:
  author: Warith Harchaoui
  package: web-search-helper
  suite: ai-helpers
  homepage: https://github.com/warith-harchaoui/web-search-helper
---

# web-search-helper

Search a private corpus from a website, PHP as the only server. Part of the
AI Helpers suite.

## Before anything: verify it is installed

```bash
web-search-helper --version
php -v          # the endpoint needs PHP >= 7.4 with mbstring, locally to test
```

If missing: `pip install 'web-search-helper[embed]'` (the extra brings
sentence-transformers; without it only the `hash` dry-run model works).

## The workflow

```bash
web-search-helper build corpus/ -o build/fr.php --lang fr     # .jsonl, Markdown or a folder
web-search-helper calibrate build/fr.php --inside in.txt --outside out.txt --write
web-search-helper search build/fr.php "a question" --explain   # what the server will answer
web-search-helper install site/ build/fr.php build/en.php       # search.php + web-search.js + data
web-search-helper serve site/                                   # php -S, local twin of the host
web-search-helper bench build/fr.php                            # PHP time per search
web-search-helper check-online https://example.org/x/ --lang fr --lang en   # after upload
```

One index per language; the page says which language it asks. In the page:
`import { WebSearch, composeAnswer, mount } from './web-search.js'`.

## Rules of thumb

- **Calibrate before trusting the refusals.** Ask the user for 10–20 questions
  the corpus answers and 10–20 it does not, including some that borrow its
  vocabulary. Report the margins `calibrate` prints; a margin under 0.02 on a
  cosine is fragile, because the browser's model and the Python one differ by
  about that much.
- **Never ship the raw corpus.** The index file is a PHP script that answers
  404; also upload `search-data/.htaccess`. Run `check-online` after every
  upload and report any leak.
- **Exhaustive search is deliberate.** Do not swap in HNSW to save time unless
  `bench` exceeds the budget on the real host: the refusal rule judges the
  absolute best cosine, which an approximate index can miss.
- **The answer is extractive.** `composeAnswer` picks corpus sentences
  verbatim; no LLM writes. If the user wants generated prose, that is a
  separate design decision (an in-browser LLM, Chrome's Prompt API, or PHP
  calling a hosted API), not a flag.

For every flag, read `references/cli-reference.md`.
