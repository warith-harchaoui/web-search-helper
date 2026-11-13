# web-search-helper

[🇫🇷](https://github.com/warith-harchaoui/web-search-helper/blob/main/LISEZMOI.md)&nbsp;&nbsp;|&nbsp;&nbsp;[🇬🇧](https://github.com/warith-harchaoui/web-search-helper/blob/main/README.md)

![License](https://img.shields.io/badge/license-BSD--3--Clause-blue)
![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
![PHP](https://img.shields.io/badge/server-PHP%20only-777BB4)
[![tests](https://github.com/warith-harchaoui/web-search-helper/actions/workflows/tests.yml/badge.svg)](https://github.com/warith-harchaoui/web-search-helper/actions/workflows/tests.yml)

**Search a private corpus from a website, with PHP as the only server.** You
index the corpus on your machine; one PHP file answers the questions; the page
embeds each question in the browser. The corpus is never published: a visitor
receives a few sentences of what answers the question, or an honest "I cannot
answer" and nothing else.

`web-search-helper` belongs to the [**AI Helpers**](https://github.com/warith-harchaoui/ai-helpers)
suite. It works in French and in English out of the box (stopwords, answer
composition, interface), one index per language, and in any other language
with a stopword file. By default no LLM is involved: the answer is made of the
corpus's own sentences. Optionally, a small language model runs in the
visitor's browser and writes the answer from the excerpts, citing them; which
model depends on the visitor's machine and line, as planned by
[`best-engine-ai-helper`](https://github.com/warith-harchaoui/best-engine-ai-helper).

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
| the browser | `web-search.js`: embeds the question (transformers.js), composes an extractive answer, optionally writes one with an in-browser LLM | an ES-module browser; WebGPU for the written answer |

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
web-search-helper install site/ build/fr.php build/en.php --demo
web-search-helper serve site/        # http://127.0.0.1:8765/demo.html?lang=fr (or ?lang=en)

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

## A written answer, in the visitor's browser

`mount(form, output, { …, writer: true })` adds a button under a `sure`
result: a small language model, run by transformers.js on WebGPU in the
visitor's browser, rewrites the excerpts into an answer that cites them as
[1], [2]… Nothing leaves the browser and the server does not change.

Which model is not decided in this package. `writer-plan.json`, written by
`best-engine-ai-helper browser plan --usage rag-answer`, is an ordered ladder
ranked by scores measured on this very task: Gemma 4 E4B (0.722) then Gemma 4
E2B (0.667), each in q4f16 and q4, with exact files and sizes (3.1 to 5.6 GB).
LFM2 1.2B was measured too (0.167: most of its answers cite nothing) and left
out, so a machine that cannot fetch a Gemma keeps the extractive answer rather
than one it would set aside. `scripts/eval_writer.py` reruns the measurement on
your own corpus; `scripts/make_writer_plan.py` rewrites the plan from
best-engine. The page probes the machine (WebGPU,
shader-f16, device memory, storage, mobile, data saver), checks the browser
cache, measures the bandwidth on a Range request to the model's own files, and
takes the first rung it can fetch within `max_download_s` (180 s). Nothing fits:
no button, and the extractive answer stands. `chooseRung` is tested against
best-engine's Python `browser.choose` on 2 251 simulated devices.

The written answer is checked before it is shown: the model only sees a `sure`
result, it is told to use the excerpts only and to say when they fall short,
and every sentence it writes must find most of its content words in the
excerpts it cites (`checkGrounding`). Otherwise the page sets the written
answer aside and keeps the extractive one. The excerpts stay listed below it,
verbatim.

```js
import { Writer } from './web-search.js';
const { writer, reason } = await Writer.create('writer-plan.json');  // null when nothing fits
const answer = writer && await writer.write(result, { question, lang: 'fr', onText: show });
if (answer && answer.grounded) show(answer.text);
```

## The suite's other doors

Like every AI Helper, the engine is also reachable over HTTP and MCP, for
agents, scripts and local testing without PHP (`search.php` stays the
production server):

```bash
pip install 'web-search-helper[api,mcp,embed]'
WSH_DATA_DIR=site/search-data web-search-helper-api    # http://127.0.0.1:8040/docs, /gui
WSH_DATA_DIR=site/search-data web-search-helper-mcp    # MCP at http://127.0.0.1:8041/mcp
```

Routes: `POST /query` speaks `search.php`'s protocol, so `web-search.js` can
point at it (that is what `/gui` does); `POST /search` takes a plain question
and embeds it server-side; `GET /indexes`; `POST /calibrate` (writes
nothing); `POST /check-online`. The MCP tools are `indexes`, `search`,
`calibrate` and `check_online`. The agent skill lives in
`skills/web-search-helper/`; `TRIGGERS.md` lists what should reach for this
helper and what should not, and a test keeps it identical to the skill's copy.

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
