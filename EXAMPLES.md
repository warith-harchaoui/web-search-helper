# web-search-helper Examples

[🇫🇷](https://github.com/warith-harchaoui/web-search-helper/blob/main/EXEMPLES.md)&nbsp;&nbsp;|&nbsp;&nbsp;[🇬🇧](https://github.com/warith-harchaoui/web-search-helper/blob/main/EXAMPLES.md)

A self-contained cookbook. Every command here was run against
`web-search-helper 0.2.0` with the `[embed]` extra and the default model
(`paraphrase-multilingual-MiniLM-L12-v2`), on an Apple Silicon Mac, on
2026-11-15, and the output shown is what came back. Cosines and timings depend
on the machine and the model version; the verdicts (`"sure"`) are what to
compare.

## Table of Contents

- [Setup](#setup)
- [1. Build an index](#1-build-an-index)
- [2. Before calibration, the engine refuses](#2-before-calibration-the-engine-refuses)
- [3. Calibrate the "I cannot answer" rule](#3-calibrate-the-i-cannot-answer-rule)
- [4. Ask a question the corpus answers](#4-ask-a-question-the-corpus-answers)
- [5. Ask a question it does not answer](#5-ask-a-question-it-does-not-answer)
- [6. The words-only first call](#6-the-words-only-first-call)
- [7. Install into a site and time the PHP engine](#7-install-into-a-site-and-time-the-php-engine)
- [8. The same from Python](#8-the-same-from-python)
- [Command line](#command-line)

## Setup

```bash
pip install 'web-search-helper[embed]'    # or, from a clone: pip install -e '.[embed]'
```

The examples use a four-section corpus about beekeeping. Save it as
`corpus-en/beekeeping.md`:

```markdown
# Beekeeping notes

## Spring inspection

Open the hive on a warm, still afternoon, above fifteen degrees. Look for eggs standing upright at the bottom of the cells: they prove the queen was laying three days ago. Count the frames covered with bees rather than the bees themselves.

## Swarming

A colony swarms when it runs out of room. Queen cells hanging from the bottom bars of the frames are the warning sign. Adding a super before the main nectar flow gives the bees space and usually prevents the swarm.

## Varroa

The varroa mite feeds on the bees' fat bodies and spreads viruses. Count the mites that fall on a sticky board over three days; more than ten a day in late summer calls for a treatment, ideally with oxalic acid when the colony has no brood.

## Winter

A colony needs about fifteen kilograms of honey to see the winter through. Weigh the hive by lifting it from behind. Leave the bees alone in cold weather: every opening costs them heat they cannot spare.
```

And two question files, one question per line: `inside-en.txt` for questions
the corpus answers, `outside-en.txt` for questions it does not.

```bash
printf 'When should I treat against varroa?\nHow do I stop a colony from swarming?\nHow much honey does a hive need for winter?\nWhat do eggs in the cells tell me?\n' > inside-en.txt
printf 'How do I bake sourdough bread?\nWhat is the capital of Australia?\nWhich train goes to Lyon?\nHow do I change a bicycle tyre?\n' > outside-en.txt
```

## 1. Build an index

```bash
web-search-helper build corpus-en/ -o build/en.php --lang en
# en: 4 passages, 4 windows, 4 sections, 93 words -> build/en.php
# ann-router at a 100 ms budget: exact. The PHP engine scans exhaustively; `web-search-helper bench build/en.php` measures whether that fits.
```

The first run downloads the model (about 480 MB) into the Hugging Face cache.
The index is a PHP file that answers 404 when requested by URL; its data
follows `__halt_compiler();`.

## 2. Before calibration, the engine refuses

The default thresholds are deliberately strict. On a new corpus, even a
question it answers is refused:

```bash
web-search-helper search build/en.php "When should I treat against varroa?" --explain
# {
#   "sure": false,
#   "terms": ["varroa"],
#   "explain": {"best": 0.0734, "conj": false, "df1": 0, "typed": 6, "top": 0.4057, "sectop": 0.4057}
# }
```

`top` (0.41) is the best window's cosine and `sectop` the best section's; both
are under the default `sem_min` of 0.55. Refusing is the safe failure: an
uncalibrated index says nothing rather than something wrong.

## 3. Calibrate the "I cannot answer" rule

```bash
web-search-helper calibrate build/en.php --inside inside-en.txt --outside outside-en.txt --write
# {
#   "thresholds_before": {"sem_min": 0.55, "sec_min": 0.561, "lex_min": 5.0, "df_min": 9},
#   "routes": {
#     "df_min": {"value": 9, "margin": null},
#     "lex_min": {"value": 5.0, "margin": null},
#     "sem_min": {"value": 0.31, "margin": 0.0954},
#     "sec_min": {"value": 0.31, "margin": 0.0954}
#   },
#   "thresholds": {"sem_min": 0.31, "sec_min": 0.31, "lex_min": 5.0, "df_min": 9},
#   "wrong": [],
#   "n": {"inside": 4, "outside": 4}
# }
# thresholds written to build/en.php
```

The meaning threshold drops to 0.31, halfway between the inside and outside
questions, with a margin of 0.095 on each side. `"wrong": []` means every
calibration question now gets the right verdict. A `null` margin means the
questions never used that route, so its threshold is left as it was. Use
`--dry-run` to read the report without writing it. Four questions on each side
are enough for a demonstration; a real corpus wants a few dozen.

## 4. Ask a question the corpus answers

```bash
web-search-helper search build/en.php "When should I treat against varroa?"
# {
#   "sure": true,
#   "terms": ["varroa"],
#   "hits": [
#     {
#       "doc": "Beekeeping notes",
#       "section": "Varroa",
#       "url": "",
#       "meta": {},
#       "text": "The varroa mite feeds on the bees' fat bodies and spreads viruses. Count the mites that fall on a sticky board over three days; more than ten a day in late summer calls for a treatment, ideally with oxalic acid when the colony has no brood.",
#       "o": [240],
#       "cos": [0.4057],
#       "before": false,
#       "after": false
#     },
#     ... three more hits: Swarming, Spring inspection, Winter
#   ]
# }
```

A question that shares no word with its answer is found by meaning:

```bash
web-search-helper search build/en.php "How do I keep my bees from leaving?"
# "sure": true, hits in this order: Swarming (cos 0.572), Winter (0.581), Spring inspection, Varroa
```

`terms` came back as `["bees", "from", "laying"]`: the typo tolerance read
`leaving` as `laying`, a word of the corpus, because `leaving` is absent from
it. On a four-passage corpus the fusion of the two rankings still puts
Swarming first.

## 5. Ask a question it does not answer

```bash
web-search-helper search build/en.php "How do I bake sourdough bread?" --explain
# {
#   "sure": false,
#   "terms": [],
#   "explain": {"best": 0.0, "conj": false, "df1": 0, "typed": 6, "top": 0.2149, "sectop": 0.2149}
# }
```

No word found, and the best cosine (0.21) is under the calibrated 0.31: no
hits at all. This is what `search.php` sends a visitor, and nothing of the
corpus goes with it.

## 6. The words-only first call

The page calls the server twice: words only first, before the model has loaded
in the browser, then words and meaning.

```bash
web-search-helper search build/en.php "varroa oxalic" --words-only
# {
#   "sure": false,
#   "terms": ["varroa", "oxalic"]
# }
```

Both words are in the corpus, but on four short passages their BM25 stays
under `lex_min` (5.0), so the words route alone does not commit; the second
call, with meaning, decides. On a corpus of a few hundred passages the same
query commits from the first call.

## 7. Install into a site and time the PHP engine

```bash
web-search-helper install site/ build/fr.php build/en.php --demo
# site/search.php
# site/web-search.js
# site/web-search.d.ts
# site/writer-plan.json
# site/demo.html
# site/search-data/.htaccess
# site/search-data/fr.php
# site/search-data/en.php
# Upload search.php, web-search.js and the whole data folder, .htaccess included; then run `web-search-helper check-online <url> --lang …`.

web-search-helper bench build/en.php --runs 5 --question "varroa"
# {
#   "load_ms": 7.21,
#   "search_ms_median": 0.47,
#   "search_ms_max": 2.64,
#   "vectors": 4,
#   "memory_mb": 0.84,
#   "php": "8.5.9",
#   "slowing_extensions": ["pcov"]
# }
# warning: pcov loaded; it slows PHP loops several times over and is rarely on a production server. Measure there too (check-online reports the endpoint's time).
```

`build/fr.php` is the same corpus in French (see [EXEMPLES.md](https://github.com/warith-harchaoui/web-search-helper/blob/main/EXEMPLES.md)).
`web-search-helper serve site/` serves the folder with `php -S`, as the
hosting would; the demo answers at `http://127.0.0.1:8765/demo.html?lang=en`.
After uploading, `web-search-helper check-online https://example.org/search/ --lang en`
checks that the index file is not served and that the endpoint answers.

## 8. The same from Python

```python
import web_search_helper as wsh

emb = wsh.SentenceTransformerEmbedder()  # paraphrase-multilingual-MiniLM-L12-v2
idx = wsh.build(wsh.read_corpus("corpus-en/"), emb, "en")
inside = open("inside-en.txt").read().splitlines()
outside = open("outside-en.txt").read().splitlines()
report = wsh.calibrate(idx, inside, outside, emb)
idx.meta["thresholds"] = report["thresholds"]
print(report["thresholds"], report["wrong"])
# {'sem_min': 0.31, 'sec_min': 0.31, 'lex_min': 5.0, 'df_min': 9} []

for q in ["How much honey for the winter?", "Who won the 1998 World Cup?"]:
    r = wsh.search(idx, q, emb.encode([q])[0])
    print(q, "->", r["sure"], [h["section"] for h in r.get("hits", [])])
# How much honey for the winter? -> True ['Winter', 'Spring inspection', 'Varroa', 'Swarming']
# Who won the 1998 World Cup? -> False []
```

`wsh.calibrate` returns the report and leaves the index untouched; the
thresholds are set by hand, then `wsh.save(idx, "build/en.php")` writes the
file `search.php` reads. `wsh.search` without a question vector is the
words-only call of example 6.

## Command line

| Command | What it does |
|---|---|
| `build CORPUS -o INDEX --lang L` | Index a `.jsonl`, a Markdown/text file or a folder of them. `--model hash` builds without weights, for a dry run. |
| `calibrate INDEX --inside F --outside F [--write]` | Measure the thresholds of the "I cannot answer" rule. |
| `search INDEX QUESTION [--explain] [--words-only]` | Answer as `search.php` would. |
| `install SITE INDEX... [--demo]` | Copy `search.php`, `web-search.js` and the indexes into the site folder. |
| `serve SITE` | Serve the folder with `php -S`. |
| `bench INDEX [--budget-ms N]` | Time the PHP engine; fails above the budget. |
| `check-online URL --lang L` | After upload: is the corpus private, and does the endpoint answer? |

`web-search-helper COMMAND --help` lists every option.
