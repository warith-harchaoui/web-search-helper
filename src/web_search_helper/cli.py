"""``web-search-helper`` command line."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__


def _embedder(model: str, browser: str | None):
    if model == "hash":
        from .embed import HashEmbedder

        return HashEmbedder()
    from .embed import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder(model, browser)


def _lines(path: str) -> list[str]:
    return [
        x.strip()
        for x in Path(path).read_text(encoding="utf-8").splitlines()
        if x.strip() and not x.lstrip().startswith("#")
    ]


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version")
def main():
    """Search a private corpus from a website: index here, PHP there."""


@main.command()
@click.argument("corpus", type=click.Path(exists=True))
@click.option(
    "-o", "--out", required=True, type=click.Path(), help="Index file to write, e.g. search-data/fr.php."
)
@click.option("--lang", required=True, help="Language code of the corpus (fr, en…).")
@click.option(
    "--model",
    default="paraphrase-multilingual-MiniLM-L12-v2",
    show_default=True,
    help="sentence-transformers model; 'hash' for a dry run without weights.",
)
@click.option("--browser-model", default=None, help="transformers.js twin, if the model is not a known one.")
@click.option(
    "--stopwords",
    type=click.Path(exists=True),
    default=None,
    help="One stopword per line (replaces the default list).",
)
@click.option(
    "--target-words", default=220, show_default=True, help="Passage size when cutting Markdown/text."
)
@click.option("--per-hour", default=120, show_default=True, help="Requests per address per hour.")
@click.option("--per-day", default=400, show_default=True, help="Requests per address per day.")
def build(corpus, out, lang, model, browser_model, stopwords, target_words, per_hour, per_day):
    """Index CORPUS (a .jsonl, a Markdown/text file, or a folder of them)."""
    from .corpus import read_corpus
    from .index import build as build_index
    from .index import save
    from .text import fold

    passages = read_corpus(corpus, target_words)
    stop = frozenset(fold(w) for w in _lines(stopwords)) if stopwords else None
    idx = build_index(
        passages,
        _embedder(model, browser_model),
        lang,
        stop,
        limits={"per_hour": per_hour, "per_day": per_day},
    )
    save(idx, out)
    click.echo(
        f"{lang}: {len(idx.passages)} passages, {len(idx.vectors)} windows, "
        f"{len(idx.centroids)} sections, {len(idx.words)} words -> {out}"
    )
    try:
        import ann_router as ar

        c = ar.route(
            ar.Criteria(
                n_vectors=len(idx.vectors),
                dim=idx.meta["dim"],
                dynamic=False,
                target_recall=0.95,
                latency_budget_ms=100,
            )
        )
        click.echo(
            f"ann-router at a 100 ms budget: {c.backend}. The PHP engine scans exhaustively; "
            f"`web-search-helper bench {out}` measures whether that fits."
        )
    except ImportError:
        pass


@main.command()
@click.argument("index", type=click.Path(exists=True))
@click.option(
    "--inside",
    required=True,
    type=click.Path(exists=True),
    help="Questions the corpus answers, one per line.",
)
@click.option(
    "--outside",
    required=True,
    type=click.Path(exists=True),
    help="Questions it does not answer, one per line.",
)
@click.option("--write/--dry-run", default=False, help="Write the new thresholds into INDEX.")
def calibrate(index, inside, outside, write):
    """Measure the thresholds of the "I cannot answer" rule."""
    from .calibrate import calibrate as run
    from .index import load, save

    idx = load(index)
    model = idx.meta["model"]
    rep = run(idx, _lines(inside), _lines(outside), _embedder(model["python"], model["browser"]))
    click.echo(json.dumps(rep, ensure_ascii=False, indent=2))
    if write:
        idx.meta["thresholds"] = rep["thresholds"]
        save(idx, index)
        click.echo(f"thresholds written to {index}", err=True)
    sys.exit(1 if rep["wrong"] else 0)


@main.command()
@click.argument("index", type=click.Path(exists=True))
@click.argument("question")
@click.option("--words-only", is_flag=True, help="Do not embed the question (the first call of the page).")
@click.option("--explain", is_flag=True, help="Show the measures behind the verdict.")
def search(index, question, words_only, explain):
    """Ask INDEX a QUESTION, as search.php would answer it."""
    from .engine import search as run
    from .index import load

    idx = load(index)
    qv = None
    if not words_only:
        m = idx.meta["model"]
        qv = _embedder(m["python"], m["browser"]).encode([question])[0]
    click.echo(json.dumps(run(idx, question, qv, explain), ensure_ascii=False, indent=2))


@main.command()
@click.argument("site", type=click.Path())
@click.argument("indexes", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--data-dir", default="search-data", show_default=True)
def install(site, indexes, data_dir):
    """Copy search.php, web-search.js and INDEXES into the SITE folder."""
    from .site import install as run

    for p in run(site, list(indexes), data_dir):
        click.echo(p)
    click.echo(
        "Upload search.php, web-search.js and the whole data folder, .htaccess included; "
        "then run `web-search-helper check-online <url> --lang …`."
    )


@main.command()
@click.argument("site", type=click.Path(exists=True))
@click.option("--port", default=8765, show_default=True)
def serve(site, port):
    """Serve SITE with `php -S`, as the hosting would."""
    from .site import serve as run

    proc = run(site, port)
    click.echo(f"http://127.0.0.1:{port}/  (Ctrl-C to stop)")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


@main.command()
@click.argument("index", type=click.Path(exists=True))
@click.option("--runs", default=5, show_default=True)
@click.option("--question", default="test question", show_default=True)
@click.option("--budget-ms", default=150.0, show_default=True, help="Fail above this median search time.")
def bench(index, runs, question, budget_ms):
    """Time the PHP engine on INDEX (needs php on PATH)."""
    from .site import bench as run

    r = run(index, runs, question)
    click.echo(json.dumps(r, indent=2))
    if r.get("slowing_extensions"):
        click.echo(
            f"warning: {', '.join(r['slowing_extensions'])} loaded; it slows PHP loops several "
            "times over and is rarely on a production server. Measure there too "
            "(check-online reports the endpoint's time).",
            err=True,
        )
    if r["search_ms_median"] > budget_ms:
        click.echo(
            f"median {r['search_ms_median']:.0f} ms is over the {budget_ms:g} ms budget: "
            "time to consider an approximate index (see ann-router).",
            err=True,
        )
        sys.exit(1)


@main.command("check-online")
@click.argument("base_url")
@click.option("--lang", "langs", multiple=True, required=True)
@click.option("--question", default="test")
@click.option("--data-dir", default="search-data", show_default=True)
def check_online(base_url, langs, question, data_dir):
    """After uploading: is the corpus private, and does search.php answer?"""
    from .site import check_online as run

    r = run(base_url, list(langs), question, data_dir)
    click.echo(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
