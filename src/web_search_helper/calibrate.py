"""Measure the thresholds of the "I cannot answer" rule on YOUR corpus.

The engine answers only when one of three routes says the corpus treats the
question (see ``engine.sure_enough``). Each route has a threshold, and a
threshold guessed is a threshold wrong: the cosines move every time the corpus
is re-indexed. So they are measured, from two lists of questions you write:

- ``inside``: questions the corpus answers;
- ``outside``: questions it does not, ideally some that borrow its vocabulary
  (they are the hard ones).

Each threshold is placed halfway between the two families, on the questions
that this route alone must decide:

- ``df_min``: one-word queries; between the most frequent outside word and the
  rarest inside word;
- ``sem_min``: between the highest outside best-window cosine and the lowest
  inside one among the questions the word route does not already save;
- ``sec_min``: the same, on the best section centroid;
- ``lex_min``: between the best outside BM25 that passed the conjunctive pass
  and the lowest inside one.

When the families overlap, no value separates them; the report says so and
keeps the previous value. Then the whole rule is replayed, and every question
that still falls on the wrong side is listed.

The question vectors here come from the Python model; the page computes them
with transformers.js. The two agree to about 1e-2 on cosines, which is why a
margin is reported: a threshold with less margin than that is fragile.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .engine import lexical, semantic, sure_enough
from .index import Index


@dataclass
class Measure:
    q: str
    inside: bool
    has_terms: bool
    typed: int
    df1: int
    conj: bool
    best: float
    top: float
    sectop: float


def measure(idx: Index, questions: list[str], inside: bool, embedder) -> list[Measure]:
    vecs = embedder.encode(questions) if questions else np.zeros((0, idx.meta["dim"]))
    out = []
    for q, v in zip(questions, vecs):
        kw = lexical(q, idx)
        sem = semantic(v, idx)
        out.append(
            Measure(
                q,
                inside,
                bool(kw["terms"]),
                kw["typed"],
                kw["df1"],
                kw["conj"],
                kw["best"],
                sem["top"],
                sem["sectop"],
            )
        )
    return out


def _halfway(low_side: list[float], high_side: list[float]):
    """Midpoint between max(low_side) and min(high_side), or None if they overlap."""
    if not low_side or not high_side:
        return None, None
    lo, hi = max(low_side), min(high_side)
    if lo >= hi:
        return None, hi - lo
    return (lo + hi) / 2, (hi - lo) / 2


def calibrate(idx: Index, inside: list[str], outside: list[str], embedder) -> dict:
    """New thresholds and a report; ``idx.meta`` is left untouched."""
    th = dict(idx.meta["thresholds"])
    ms = measure(idx, inside, True, embedder) + measure(idx, outside, False, embedder)
    report: dict = {"thresholds_before": dict(th), "routes": {}}

    one = [m for m in ms if m.typed == 1]
    v, margin = _halfway([m.df1 for m in one if not m.inside], [m.df1 for m in one if m.inside])
    if v is not None:
        th["df_min"] = int(np.floor(v)) + 1 if v != int(v) else int(v)
    report["routes"]["df_min"] = {"value": th["df_min"], "margin": margin}

    many = [m for m in ms if m.typed > 1]
    lex_in = [m.best for m in many if m.inside and m.conj]
    lex_out = [m.best for m in many if not m.inside and m.conj]
    v, margin = _halfway(lex_out, lex_in)
    if v is not None:
        th["lex_min"] = round(v, 3)
    report["routes"]["lex_min"] = {"value": th["lex_min"], "margin": margin}

    need = [m for m in many if m.inside and not (m.conj and m.best >= th["lex_min"])]
    out_many = [m for m in many if not m.inside]
    for key, attr in (("sem_min", "top"), ("sec_min", "sectop")):
        v, margin = _halfway([getattr(m, attr) for m in out_many], [getattr(m, attr) for m in need])
        if v is not None:
            th[key] = round(v, 3)
        report["routes"][key] = {"value": th[key], "margin": margin}

    wrong = []
    for m in ms:
        kw = {
            "terms": [1] if m.has_terms else [],
            "typed": m.typed,
            "df1": m.df1,
            "conj": m.conj,
            "best": m.best,
        }
        got = sure_enough(kw, {"top": m.top, "sectop": m.sectop}, th)
        if got != m.inside:
            wrong.append(
                {
                    "q": m.q,
                    "expected": "answer" if m.inside else "refuse",
                    "top": round(m.top, 3),
                    "sectop": round(m.sectop, 3),
                    "best": round(m.best, 2),
                    "conj": m.conj,
                    "df1": m.df1,
                }
            )
    report["thresholds"] = th
    report["wrong"] = wrong
    report["n"] = {"inside": len(inside), "outside": len(outside)}
    return report
