# web-search-helper

[🇫🇷](LISEZMOI.md) · [🇬🇧](README.md)

**Search a private corpus from a website, with PHP as the only server.** You
index the corpus on your machine; one PHP file answers the questions; the page
embeds each question in the browser. The corpus is never published: a visitor
receives a few sentences of what answers the question, or an honest "I cannot
answer" and nothing else.

BSD 3-Clause licence. Author: Warith Harchaoui.

## Why

A fully client-side search must ship the corpus to the browser, because the
browser can only search what it has. That is fine for public documentation and
wrong for a manuscript, a course or an internal knowledge base. Encrypting the
file does not help: the key has to be in the page too.

Most hosting offers PHP and nothing else: no Python, no Node, no vector
database. web-search-helper fits there.

| Where | What runs | Needs |
|---|---|---|
| your machine | cut, embed and index the corpus; measure the thresholds | Python ≥ 3.10, `sentence-transformers` |
| the server | `search.php`: BM25 + cosines + fusion + verdict, returns excerpts | PHP ≥ 7.4 with mbstring |
| the browser | `web-search.js`: embeds the question (transformers.js), composes an extractive answer | an ES-module browser |

## How it searches

- **Words**: BM25, with a conjunctive pass first (when some passages contain
  every word, only they compete) and a timid typo tolerance (`elefant` finds
  `éléphant`, but only because `elefant` is absent from the corpus).
- **Meaning**: passages are cut into windows the model reads entirely; a
  passage scores the cosine of its best window. Each section also has a
  centroid.
- **Fusion**: reciprocal rank fusion of the two rankings.
- **Verdict**: the engine answers only when one of three routes says the corpus
  treats the question: the best window *and* the best section are close in
  meaning, or every word was found with a strong BM25, or (for a one-word
  query) the word appears in enough passages. Otherwise it returns nothing.
  Ranking always returns *something*; only an absolute measure can say "no".

The search is exhaustive. `ann-router` would pick HNSW from 1 000 vectors at a
10 ms budget, but that budget is numpy's, the corpus sizes here are small, and
the verdict judges the *absolute* best cosine, which an approximate index can
miss. `web-search-helper bench` measures the PHP time on your index and fails
when it goes over budget.

## Protections against scraping

1. Nothing is returned when the corpus does not treat the question.
2. A passage comes back as an excerpt: its best window and the better of its
   neighbours, snapped to sentence boundaries. Never the whole passage.
3. A quota per address, per hour and per day (salted hash of the address; no
   other trace kept).
4. The index file is a PHP script: requested by URL, it answers an empty 404.
   The data folder also gets a `.htaccess` that denies everything, in case.

Someone patient with thousands of well-chosen questions can still collect a
good part of the corpus. These measures make that slow, not impossible.

## Quick start

```bash
pip install 'web-search-helper[embed]'

# 1. Index: a .jsonl (one passage per line), a Markdown file or a folder of them.
web-search-helper build corpus/ -o build/fr.php --lang fr

# 2. Measure the thresholds on questions the corpus answers and questions it does not.
web-search-helper calibrate build/fr.php --inside inside.txt --outside outside.txt --write

# 3. Try a question, as the server will answer it.
web-search-helper search build/fr.php "Quelle est la parabole de l'éléphant ?" --explain

# 4. Copy the endpoint, the client and the index into the site; serve it locally.
web-search-helper install site/ build/fr.php
cp examples/demo.html site/index.html
web-search-helper serve site/        # http://127.0.0.1:8765/

# 5. Time the PHP engine; after upload, check that nothing leaks.
web-search-helper bench build/fr.php
web-search-helper check-online https://example.org/search/ --lang fr
```

JSONL records: `{"text": "...", "doc": "Book title", "section": "Chapter 2", "url": "page.html#x", "meta": {...}}`.
`meta` is passed through to the browser untouched.

## In the page

```html
<script type="module">
  import { WebSearch, composeAnswer } from './web-search.js';
  const ws = new WebSearch({ endpoint: 'search.php', lang: 'fr' });
  const r = await ws.ask(question, { onLexical: (first) => { /* early answer */ } });
  if (!r.sure) showUnknown();
  else show(await composeAnswer(r, { lang: 'fr', embed: ws }), r.hits);
</script>
```

`ask` makes two calls: words only first (instant, before the model has
loaded), then words and meaning. The answer composed by `composeAnswer` is made
of corpus sentences, verbatim, chosen by maximal marginal relevance; nothing is
generated. Types are in `web-search.d.ts`. `mount(form, output, options)` wires
a minimal widget.

## Python

```python
import web_search_helper as wsh

idx = wsh.build(wsh.read_corpus("corpus/"), wsh.SentenceTransformerEmbedder(), "fr")
wsh.save(idx, "build/fr.php")
print(wsh.search(idx, "the data wall", explain=True))
```

`engine.py` is the reference twin of `search.php`; `tests/test_php_parity.py`
runs both on the same questions and fails if they disagree.

## Limits

- The question's vector is computed by transformers.js in the page and the
  index by sentence-transformers here: same weights, cosines equal to about
  1e-2. Calibration reports its margins; a threshold with less margin than that
  is fragile.
- One index per language; the page says which language it asks.
- The first question downloads the model in the browser (about 120 MB for the
  default multilingual MiniLM), then the browser keeps it.
