# GUI: web-search-helper

This document has two parts: **(1) what ships today**, the search page served
at `GET /gui` by the FastAPI app, and **(2) what the page deliberately leaves
out**. web-search-helper's real interface is the search box of *your* website;
the page described here is the same widget, run against the local API so you
can try an index before uploading it.

The page keeps the suite's house style: **vanilla JS, no build step, no
framework, no npm.** It is `demo.html`, a package asset, plus
`web-search.js`, the client every site uses.

---

## Part 1: what ships today, the search page

A single, self-contained HTML page served by the existing FastAPI app.

- **Route**: `GET /gui`. Source: `src/web_search_helper/assets/demo.html`,
  wired in `src/web_search_helper/api.py`, which rewrites its endpoint from
  `search.php` to the API's own `/query`. The page then loads
  `/web-search.js` and, for the written answer, `/writer-plan.json`, both
  served by the same app.
- **Languages**: French and English. `GET /gui?lang=fr|en` picks both the
  index (`fr.php` or `en.php` in `WSH_DATA_DIR`) and the interface; a link at
  the top switches between them. Any other value falls back to English.
- **Run it**:
  ```bash
  pip install 'web-search-helper[api]'
  WSH_DATA_DIR=site/search-data web-search-helper-api
  # open http://127.0.0.1:8040/gui?lang=fr
  ```
  Or in a container: `docker compose up --build`, indexes read from
  `./search-data`.

The same page also ships to a real site: `web-search-helper install site/
build/fr.php --demo` copies it as `demo.html`, pointed at `search.php`, and
`web-search-helper serve site/` runs it with `php -S`. The API version exists
for a machine without PHP, and for agents that drive a browser.

### 1. Ask, in two passes

- Type a question and press the button. `mount()` from `web-search.js` sends
  it twice: words only first, which answers at once while the embedding model
  is still loading, then words and meaning once the browser has embedded the
  question with transformers.js.
- The first visit downloads that model into the browser (about 120 MB for the
  default multilingual MiniLM); the browser keeps it afterwards.

### 2. Excerpts, or an honest refusal

- When the corpus treats the question, the page lists up to six excerpts:
  document and section (linked when the index carries a URL), then the best
  window of the passage and its better neighbour, never the whole passage.
- When it does not, the page says **"I cannot answer that."** and nothing
  else. That refusal is the verdict of the engine, the same one `search.php`
  returns, not an empty list.

### 3. An extractive answer

- Above the excerpts, `composeAnswer` writes a short answer made of the
  corpus's own sentences, verbatim, chosen by maximal marginal relevance, with
  the sections it drew from. Nothing is generated.

### 4. A written answer, when the machine can bear it

- `mount(..., { writer: true })` reads `writer-plan.json`, the ladder
  best-engine-ai-helper ranks for the `rag-answer` usage, probes the machine
  (WebGPU, shader-f16, memory, storage, data saver, the cache) and measures
  the line on the model's own files. When a rung fits, a button offers to
  write the answer with that model, naming its download size.
- The model runs in the visitor's browser and cites the excerpts as [1],
  [2]… A written answer whose sentences the cited excerpts do not support is
  set aside, with a notice; the extractive answer stays.
- When nothing fits, there is no button and nothing else changes.

### Stack (as shipped)

- Front end: one HTML page and one ES module (`web-search.js`, typed by
  `web-search.d.ts`). Embedding and the written answer: transformers.js,
  loaded from a CDN by the browser.
- Back end: the FastAPI app (`web_search_helper.api`); `/query` speaks the
  protocol of `search.php` and runs `engine.py`, its reference twin. The page
  adds no server logic.

---

## Part 2: what the page deliberately leaves out

- **No index building, no calibration in the browser.** Those run on your
  machine (`web-search-helper build`, `calibrate`) or through the API's
  `POST /calibrate`; the page only asks questions.
- **No quota.** `search.php` limits each address per hour and per day; the
  local API does not, because it is meant for you and your agents, not for
  visitors.
- **No corpus browsing.** A page that listed the passages would defeat the
  point of the project: the corpus is never published, and the page only ever
  receives excerpts that answer a question.
- **No server-side model for the written answer.** The answer is written in
  the visitor's browser or not at all; neither `search.php` nor the API runs
  a language model.

## Success metric

> Before uploading anything, you type the questions your readers will ask,
> see which ones the corpus answers and which ones it refuses, and the page
> you test is byte for byte the client your site will run.
