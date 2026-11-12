# web-search-helper — trigger catalogue

## Fire

- "add a search to my website over my book / course / documentation"
- "RAG on my site without a backend", "RAG with PHP only", "my host only has PHP"
- "semantic search in PHP", "hybrid BM25 + embeddings search in PHP"
- "client-side search but I don't want to publish the text"
- "the search index / JSON exposes my whole manuscript"
- "the search should say 'I don't know' instead of answering anything"
- "calibrate / measure the refusal threshold of my search"
- "compose an answer from the passages without an LLM", "extractive answer"
- "transformers.js question embedding + server-side ranking"
- "rechercher dans mon livre depuis mon site", "RAG sans backend", "recherche
  sémantique en PHP", "le site ne doit pas publier le livre", "Je ne sais pas
  répondre"
- `web-search-helper`, `import web_search_helper as wsh`, `search.php`,
  `web-search.js`

## Do not fire

- choosing a vector index or database → `ann-router`
- running or choosing a local LLM → `best-engine-ai-helper`
- a public static site whose corpus may be shipped whole (Pagefind, a
  client-only index)
- web search on the internet (search engines, crawling)
- transcribing audio to build a corpus → `vocal-helper` first, then this
