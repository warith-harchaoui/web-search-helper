"""Unacceptable questions: refused before any search, in two layers.

1. **The screen**, always on, in the index itself. A short list of words and
   phrases that are abusive in every context (slurs, pornographic sites,
   Nazi slogans), matched as whole words after folding, digit-for-letter
   substitutions undone and stretched letters shortened. A subject is never
   on the list: a reader may ask what the corpus says about racism or
   deepfake pornography, and the screen must let that through.
2. **The judge**, a language model asked one question: is this question
   acceptable at all? It settles what no list can, a prejudice stated in
   polite words, or a slur dressed as a question about the corpus. It runs
   when a site configures one (``judge.php`` next to the indexes, or
   ``WSH_JUDGE_*`` for the Python door), and in the browser, before the
   written answer, with the writer's own model.

``assets/search.php`` holds the PHP twin of :func:`screen`;
``tests/test_php_parity.py`` checks them on the same questions.

>>> mod = default_moderation("fr")
>>> screen("Alan Turing était un sale pédé", mod), screen("Que dit le livre du racisme ?", mod)
(True, False)
>>> screen("p3d3eee", mod), screen("Le Niger", default_moderation("en"))
(True, False)
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from functools import cache
from importlib import resources

from .text import _is_word_char, fold

#: Digits and signs typed for letters, undone before matching.
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_RUN3 = re.compile(r"(.)\1{2,}")


@cache
def _asset() -> dict:
    return json.loads(
        (resources.files("web_search_helper") / "assets" / "moderation.json").read_text(encoding="utf-8")
    )


def default_moderation(lang: str) -> dict:
    """The shipped lists for ``lang`` (all languages merged for any other), and the judge's prompt."""
    data = _asset()
    langs = (
        [lang] if lang in data and lang != "judge" else [k for k in data if not k.startswith(("_", "judge"))]
    )
    terms = sorted({t for k in langs for t in data[k]["terms"]})
    phrases = sorted({p for k in langs for p in data[k]["phrases"]})
    return {"terms": terms, "phrases": phrases, "judge": dict(data["judge"])}


def words(q: str) -> list[str]:
    """The question's words as the screen reads them: folded, de-leeted, every word kept."""
    out, cur = [], []
    for c in fold(q).translate(LEET) + " ":
        if _is_word_char(c):
            cur.append(c)
        elif cur:
            out.append("".join(cur))
            cur = []
    return out


def screen(q: str, mod: dict | None) -> bool:
    """True when ``q`` contains a listed word or phrase."""
    if not mod or not (mod.get("terms") or mod.get("phrases")):
        return False
    terms = set(mod.get("terms", []))
    ws = words(q)
    # A stretched letter ("pédééé") is read with the run cut to two, then to one.
    seen = [{w, _RUN3.sub(r"\1\1", w), _RUN3.sub(r"\1", w)} for w in ws]
    if any(v & terms for v in seen):
        return True
    line = " " + " ".join(_RUN3.sub(r"\1", w) for w in ws) + " "
    plain = " " + " ".join(ws) + " "
    return any(f" {p} " in line or f" {p} " in plain for p in mod.get("phrases", []))


# ------------------------------------------------------------- judge --


def judge_config(env: dict | None = None) -> dict | None:
    """The judge the Python door uses, from ``WSH_JUDGE_URL``, ``_MODEL``, ``_KEY``, ``_TIMEOUT``, ``_FAIL``.

    ``url`` is an OpenAI-compatible chat completions endpoint (a provider's,
    or a local server such as Ollama's ``http://localhost:11434/v1/chat/completions``).
    None when no URL is set.
    """
    env = os.environ if env is None else env
    if not env.get("WSH_JUDGE_URL"):
        return None
    return {
        "url": env["WSH_JUDGE_URL"],
        "model": env.get("WSH_JUDGE_MODEL", ""),
        "key": env.get("WSH_JUDGE_KEY", ""),
        "timeout": float(env.get("WSH_JUDGE_TIMEOUT", "8")),
        "fail": env.get("WSH_JUDGE_FAIL", "open"),
    }


def parse_verdict(text: str) -> str | None:
    """``"block"``, ``"allow"``, or None when the reply says neither.

    >>> parse_verdict("BLOCK"), parse_verdict(" allow."), parse_verdict("<think>…</think>\\nBLOCK"), parse_verdict("?")
    ('block', 'allow', 'block', None)
    """
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).upper()
    b, a = t.rfind("BLOCK"), t.rfind("ALLOW")
    if b < 0 and a < 0:
        return None
    return "block" if b > a else "allow"


def judge(q: str, config: dict, prompt: dict | None = None) -> str | None:
    """Ask the configured model whether ``q`` is acceptable: ``"allow"``, ``"block"``, or None on failure.

    Only network errors and unreadable replies give None; the caller applies
    ``config["fail"]`` (``"open"`` lets the question through, ``"closed"``
    refuses it).
    """
    prompt = prompt or _asset()["judge"]
    body = {
        "model": config.get("model", ""),
        "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"].replace("{q}", q)},
        ],
        "temperature": 0,
        "max_tokens": 400,
    }
    headers = {"Content-Type": "application/json"}
    if config.get("key"):
        headers["Authorization"] = f"Bearer {config['key']}"
    req = urllib.request.Request(config["url"], json.dumps(body).encode(), headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=config.get("timeout", 8)) as r:
            reply = json.loads(r.read())
        return parse_verdict(reply["choices"][0]["message"]["content"])
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def refused(q: str, mod: dict | None, config: dict | None = None) -> str | None:
    """Why ``q`` is refused (``"moderation"``, ``"judge"``), or None when it may be searched."""
    if screen(q, mod):
        return "moderation"
    if config:
        v = judge(q, config, (mod or {}).get("judge"))
        if v == "block" or (v is None and config.get("fail") == "closed"):
            return "judge"
    return None
