"""The search, in Python: the reference twin of ``assets/search.php``.

The PHP file is what answers visitors; this module answers the same question
the same way, so that thresholds can be measured (``calibrate``) and the PHP
engine checked against it (``tests/test_php_parity.py``). Any change to the
ranking goes into BOTH, or the parity test fails.

Three signals, two engines, one verdict:

- **words**: BM25 (k1 = 1.5, b = 0.75) with a conjunctive pass first (if some
  passages contain every word of the question, only they compete), a
  coverage² weight otherwise, and a timid typo tolerance (a word is replaced
  by its neighbours only when it is absent from the corpus);
- **meaning**: the cosine of each passage's best window, and the cosine of the
  best section centroid;
- **fusion**: reciprocal rank fusion of the two rankings (k = 60);
- **verdict**: answer only if one of three routes says the corpus treats the
  question; otherwise return nothing at all.
"""

from __future__ import annotations

import math
import re
import unicodedata

import numpy as np

from .index import Index
from .text import tokenize


def max_typos(w: str) -> int:
    return 0 if len(w) < 4 else (1 if len(w) < 7 else 2)


def within(a: str, b: str, budget: int) -> int:
    """Levenshtein distance, or ``budget + 1`` as soon as it is exceeded.

    >>> within("elefant", "elephant", 2), within("art", "zzzzzz", 1)
    (2, 2)
    """
    if abs(len(a) - len(b)) > budget:
        return budget + 1
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        best = i
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            best = min(best, cur[j])
        if best > budget:
            return budget + 1
        prev = cur
    return prev[-1]


def _by_length(idx: Index) -> dict[int, list[str]]:
    cache = getattr(idx, "_by_length", None)
    if cache is None:
        cache = {}
        for w in idx.words:
            cache.setdefault(len(w), []).append(w)
        idx._by_length = cache
    return cache


def expand_terms(q_terms: list[str], idx: Index) -> list[list[tuple[str, float]]]:
    """One group per question word: the word itself, or up to three neighbours.

    Neighbours rank by corpus frequency over (1 + distance)², and keep only
    those weighing at least a quarter of the best. A word unknown even from
    afar keeps an EMPTY group: it still counts against coverage and blocks the
    conjunctive pass, so an off-topic question does not shrink to the one word
    the corpus happens to use.
    """
    groups = []
    for t in q_terms:
        if t in idx.postings:
            groups.append([(t, 1.0)])
            continue
        budget = max_typos(t)
        cands = []
        if budget:
            by_len = _by_length(idx)
            for n in range(len(t) - budget, len(t) + budget + 1):
                for w in by_len.get(n, []):
                    d = within(t, w, budget)
                    if d <= budget:
                        cands.append((w, d, len(idx.postings[w]) / ((1 + d) ** 2)))
        if not cands:
            groups.append([])
            continue
        cands.sort(key=lambda c: -c[2])
        floor = cands[0][2] / 4
        groups.append([(w, 1 / (1 + d)) for w, d, r in cands if r >= floor][:3])
    return groups


def lexical(q: str, idx: Index) -> dict:
    q_terms = list(dict.fromkeys(tokenize(q, idx.stop)))
    typed = len(q.split())
    pool_k = idx.meta["ranking"]["pool_k"]
    if not q_terms:
        return {"ranked": [], "terms": [], "best": 0.0, "conj": False, "df1": 0, "typed": typed}
    groups = expand_terms(q_terms, idx)
    G, N = len(groups), len(idx.passages)
    tf: dict[int, list[float]] = {}
    cands: list[int] = []
    for gi, g in enumerate(groups):
        for w, weight in g:
            for i, c in idx.postings.get(w, []):
                if i not in tf:
                    tf[i] = [0.0] * G
                    cands.append(i)
                tf[i][gi] += c * weight
    df = [sum(1 for i in cands if tf[i][gi]) for gi in range(G)]
    idf = [math.log(1 + (N - d + 0.5) / (d + 0.5)) for d in df]
    k1, b, avg = 1.5, 0.75, idx.meta["avg_len"]
    conj, union = [], []
    for i in cands:
        s, matched = 0.0, 0
        for gi in range(G):
            x = tf[i][gi]
            if not x:
                continue
            matched += 1
            s += idf[gi] * (x * (k1 + 1)) / (x + k1 * (1 - b + b * idx.lengths[i] / avg))
        cov = matched / G
        (conj if matched == G else union).append((s * cov * cov, i))
    pool = conj or union
    pool.sort(key=lambda e: (-e[0], e[1]))
    return {
        "ranked": [i for _, i in pool[:pool_k]],
        "terms": [w for g in groups for w, _ in g],
        "best": pool[0][0] if pool else 0.0,
        "conj": bool(conj),
        "df1": df[0] if G == 1 else 0,
        "typed": typed,
    }


def semantic(qv: np.ndarray, idx: Index) -> dict:
    pool_k = idx.meta["ranking"]["pool_k"]
    dots = idx.vectors.astype(np.float64) @ qv.astype(np.float64)
    best = np.array([dots[a : a + len(p["o"])].max() for a, p in zip(idx.first_vec, idx.passages)])
    order = sorted(range(len(best)), key=lambda i: -best[i])
    sec = idx.centroids.astype(np.float64) @ qv.astype(np.float64)
    return {
        "ranked": order[:pool_k],
        "top": float(best[order[0]]),
        "sectop": float(sec.max()) if len(sec) else -1.0,
    }


def sure_enough(kw: dict, sem: dict | None, th: dict) -> bool:
    """The verdict: three routes in OR, because none suffices everywhere.

    - one typed word: only its PRESENCE decides (it must appear in at least
      ``df_min`` passages); its embedding is too poor to judge;
    - meaning: best window ≥ ``sem_min`` AND best section ≥ ``sec_min``;
    - words: every word found in one passage AND its BM25 ≥ ``lex_min``.
    """
    if not kw["terms"]:
        return False
    if kw["typed"] == 1:
        return kw["df1"] >= th["df_min"]
    if sem is not None and sem["top"] >= th["sem_min"] and sem["sectop"] >= th["sec_min"]:
        return True
    return kw["conj"] and kw["best"] >= th["lex_min"]


def rrf(a: list[int], b: list[int], k: int, top: int) -> list[int]:
    scores: dict[int, float] = {}
    for ranking in (a, b):
        for r, i in enumerate(ranking):
            scores[i] = scores.get(i, 0.0) + 1 / (k + r + 1)
    return [i for i, _ in sorted(scores.items(), key=lambda e: -e[1])][:top]


def _starts_upper(s: str) -> bool:
    # Twin of PHP's /^[«"“(]*[\p{Lu}\p{Lt}0-9]/u.
    s = s.lstrip('«"“(')
    return bool(s) and (unicodedata.category(s[0]) in ("Lu", "Lt") or s[0] in "0123456789")


def excerpt(i: int, qv: np.ndarray | None, terms: list[str], idx: Index) -> dict:
    """Two windows of passage ``i``, snapped to sentence boundaries.

    The best window and its better neighbour: a few sentences, never the whole
    passage. The start moves forward to the first whole sentence; the end
    moves forward to the end of the current sentence (at most 400 characters).
    Window bounds and cosines travel with the excerpt: the page needs them to
    compose its extractive answer.
    """
    p = idx.passages[i]
    t, o = p["t"], p["o"]
    n, nf = len(t), len(o)
    if qv is not None:
        a = idx.first_vec[i]
        note = [float(x) for x in idx.vectors[a : a + nf].astype(np.float64) @ qv.astype(np.float64)]
    else:
        tset = set(terms)
        note = []
        for f in range(nf):
            start = o[f - 1] if f else 0
            note.append(float(sum(1 for w in tokenize(t[start : o[f]]) if w in tset)))
    m = note.index(max(note))
    lo = hi = m
    if nf > 1:
        if m == 0:
            hi = 1
        elif m == nf - 1 or note[m - 1] > note[m + 1]:
            lo = m - 1
        else:
            hi = m + 1
    start = o[lo - 1] if lo else 0
    end = o[hi]
    if start > 0:
        for mm in re.finditer(r"[.!?…]\s+", t[start:end]):
            if _starts_upper(t[start + mm.end() :]):
                if mm.end() < end - start:
                    start += mm.end()
                break
    if end < n:
        tail = t[end : end + 400]
        for mm in re.finditer(r"[.!?…]", tail):
            rest = tail[mm.end() :]
            if not rest.strip() or (rest[:1].isspace() and _starts_upper(rest.lstrip())):
                end += mm.end()
                break
    bounds = [max(0, min(o[f], end) - start) for f in range(lo, hi + 1)]
    bounds[-1] = end - start
    return {
        "doc": p["c"],
        "section": p["s"],
        "url": p.get("u", ""),
        "meta": p.get("m", {}),
        "text": t[start:end],
        "o": bounds,
        "cos": [note[f] if qv is not None else 0.0 for f in range(lo, hi + 1)],
        "before": start > 0,
        "after": end < n,
    }


def search(idx: Index, q: str, qv: np.ndarray | None = None, explain: bool = False) -> dict:
    """What ``search.php`` answers to ``q`` (and the question vector ``qv``)."""
    q = q.strip()
    kw = lexical(q, idx)
    sem = semantic(qv, idx) if qv is not None else None
    sure = sure_enough(kw, sem, idx.meta["thresholds"])
    out: dict = {"sure": sure, "terms": kw["terms"]}
    if explain:
        out["explain"] = {
            "best": kw["best"],
            "conj": kw["conj"],
            "df1": kw["df1"],
            "typed": kw["typed"],
            "top": sem["top"] if sem else None,
            "sectop": sem["sectop"] if sem else None,
        }
    if not sure:
        return out
    r = idx.meta["ranking"]
    keep = (
        rrf(kw["ranked"], sem["ranked"], r["rrf_k"], r["answer_pool"])
        if sem
        else kw["ranked"][: r["display_k"]]
    )
    out["hits"] = [excerpt(i, qv, kw["terms"], idx) for i in keep]
    return out
