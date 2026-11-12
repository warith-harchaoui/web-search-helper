# web-search-helper — CLI reference

Generated from `--help`; every command exits non-zero on failure (`calibrate` when a question stays on the wrong side, `bench` over budget, `check-online` on a leak).

```text
Usage: web-search-helper [OPTIONS] COMMAND [ARGS]...

  Search a private corpus from a website: index here, PHP there.

Options:
  -V, --version  Show the version and exit.
  -h, --help     Show this message and exit.

Commands:
  bench         Time the PHP engine on INDEX (needs php on PATH).
  build         Index CORPUS (a .jsonl, a Markdown/text file, or a folder...
  calibrate     Measure the thresholds of the "I cannot answer" rule.
  check-online  After uploading: is the corpus private, and does...
  install       Copy search.php, web-search.js and INDEXES into the SITE...
  search        Ask INDEX a QUESTION, as search.php would answer it.
  serve         Serve SITE with `php -S`, as the hosting would.
```

### `web-search-helper build`

```text
Usage: web-search-helper build [OPTIONS] CORPUS

  Index CORPUS (a .jsonl, a Markdown/text file, or a folder of them).

Options:
  -o, --out PATH          Index file to write, e.g. search-data/fr.php.
                          [required]
  --lang TEXT             Language code of the corpus (fr, en…).  [required]
  --model TEXT            sentence-transformers model; 'hash' for a dry run
                          without weights.  [default: paraphrase-multilingual-
                          MiniLM-L12-v2]
  --browser-model TEXT    transformers.js twin, if the model is not a known
                          one.
  --stopwords PATH        One stopword per line (replaces the default list).
  --target-words INTEGER  Passage size when cutting Markdown/text.  [default:
                          220]
  --per-hour INTEGER      Requests per address per hour.  [default: 120]
  --per-day INTEGER       Requests per address per day.  [default: 400]
  -h, --help              Show this message and exit.
```

### `web-search-helper calibrate`

```text
Usage: web-search-helper calibrate [OPTIONS] INDEX

  Measure the thresholds of the "I cannot answer" rule.

Options:
  --inside PATH        Questions the corpus answers, one per line.  [required]
  --outside PATH       Questions it does not answer, one per line.  [required]
  --write / --dry-run  Write the new thresholds into INDEX.
  -h, --help           Show this message and exit.
```

### `web-search-helper search`

```text
Usage: web-search-helper search [OPTIONS] INDEX QUESTION

  Ask INDEX a QUESTION, as search.php would answer it.

Options:
  --words-only  Do not embed the question (the first call of the page).
  --explain     Show the measures behind the verdict.
  -h, --help    Show this message and exit.
```

### `web-search-helper install`

```text
Usage: web-search-helper install [OPTIONS] SITE INDEXES...

  Copy search.php, web-search.js and INDEXES into the SITE folder.

Options:
  --data-dir TEXT  [default: search-data]
  -h, --help       Show this message and exit.
```

### `web-search-helper serve`

```text
Usage: web-search-helper serve [OPTIONS] SITE

  Serve SITE with `php -S`, as the hosting would.

Options:
  --port INTEGER  [default: 8765]
  -h, --help      Show this message and exit.
```

### `web-search-helper bench`

```text
Usage: web-search-helper bench [OPTIONS] INDEX

  Time the PHP engine on INDEX (needs php on PATH).

Options:
  --runs INTEGER     [default: 5]
  --question TEXT    [default: test question]
  --budget-ms FLOAT  Fail above this median search time.  [default: 150.0]
  -h, --help         Show this message and exit.
```

### `web-search-helper check-online`

```text
Usage: web-search-helper check-online [OPTIONS] BASE_URL

  After uploading: is the corpus private, and does search.php answer?

Options:
  --lang TEXT      [required]
  --question TEXT
  --data-dir TEXT  [default: search-data]
  -h, --help       Show this message and exit.
```

