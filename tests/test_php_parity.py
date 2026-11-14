"""search.php and engine.py must give the same answer to the same question.

The PHP file answers visitors; the Python twin measures thresholds and is what
the rest of the tests trust. If they drift, calibration measures a rule the
site does not apply.
"""

import json
import subprocess

import numpy as np
import pytest

from web_search_helper.engine import search
from web_search_helper.index import save
from web_search_helper.site import asset
from web_search_helper.text import stopwords, tokenize

QUESTIONS = {
    "fr": [
        "Quelle est la parabole de l'éléphant ?",
        "la parabol de l'elefant",  # typos
        "Qu'est-ce que le mur des données ?",
        "agent",  # one word, frequent
        "zéphyr3",  # one word, rare
        "la recette du cassoulet toulousain",  # outside
        "audit des permissions",
        "le la les",  # stopwords only
        "Œuvre à Noël ÉLÉPHANT",
    ],
    "en": [
        "What is the parable of the elephant?",
        "the parabel of the elefant",  # typos
        "What is the data wall?",
        "agent",
        "zephyr3",
        "the recipe for apple pie",  # outside
        "audit of permissions",
        "the a of",  # stopwords only
        "Governing AGENTS’ permissions",
    ],
}

RUNNER = r"""<?php
define('WSH_NO_MAIN', true);
require $argv[1];
$I = wsh_load($argv[2]);
$in = json_decode(file_get_contents('php://stdin'), true);
$out = [];
foreach ($in as $c) {
    $qv = $c['v'];
    $out[] = wsh_search($I, $c['q'], $qv);
}
echo json_encode(['results' => $out, 'tokens' => array_map(function ($s) use ($I) {
    return wsh_tokenize($s, $I['stop']); }, array_column($in, 'q'))], JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION);
"""


@pytest.fixture(scope="module")
def php_results(php, lang_index, embedder, tmp_path_factory):
    index = lang_index
    d = tmp_path_factory.mktemp("parity")
    path = save(index, d / f"{index.lang}.php")
    runner = d / "runner.php"
    runner.write_text(RUNNER, encoding="utf-8")
    cases = []
    for q in QUESTIONS[index.lang]:
        cases.append({"q": q, "v": None})
        cases.append({"q": q, "v": [float(x) for x in embedder.encode([q])[0]]})
    out = subprocess.run(
        [php, str(runner), str(asset("search.php")), str(path)],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=True,
    )
    return cases, json.loads(out.stdout)


def _norm(v):
    a = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(a)
    return a / n if n else a


def test_tokenization_matches(php_results, lang_index):
    index = lang_index
    cases, got = php_results
    for c, toks in zip(cases, got["tokens"]):
        assert toks == tokenize(c["q"], index.stop), c["q"]


def test_same_answers(php_results, lang_index):
    index = lang_index
    cases, got = php_results
    for c, r in zip(cases, got["results"]):
        qv = None if c["v"] is None else _norm(c["v"]).astype(np.float32)
        ref = search(index, c["q"], qv)
        assert r["sure"] == ref["sure"], c["q"]
        assert r["terms"] == ref["terms"], c["q"]
        if not ref["sure"]:
            assert "hits" not in r
            continue
        assert [h["text"] for h in r["hits"]] == [h["text"] for h in ref["hits"]], c["q"]
        for a, b in zip(r["hits"], ref["hits"]):
            assert a["o"] == b["o"] and a["before"] == b["before"] and a["after"] == b["after"]
            assert np.allclose(a["cos"], b["cos"], atol=1e-5)


def test_some_questions_are_refused_and_some_answered(php_results):
    _, got = php_results
    verdicts = [r["sure"] for r in got["results"]]
    assert any(verdicts) and not all(verdicts)


def test_stopwords_are_folded():
    assert "etre" in stopwords("fr") and "être" not in stopwords("fr")


MATH_TEXT = (
    "Le modèle se note ainsi. Une politique associe une action à chaque situation : "
    # Longer than the 400 characters sentence snapping looks ahead: without
    # the guard, the excerpt stopped inside it.
    "$$\\mathbf{J}(\\pi) = "
    + " + ".join(f"\\gamma^{{{k}}} r_{{{k}}}" for k in range(40))
    + "$$ et on la maximise. "
    "On retire le plus petit morceau, noté \\(f_{\\theta}\\), sans perte notable. Fin du passage."
)


def test_excerpts_never_cut_a_formula(php, tmp_path):
    """A window bound inside $$…$$ or \\(…\\) moves out of it, in both twins."""
    from web_search_helper.engine import excerpt
    from web_search_helper.index import from_vectors

    t = MATH_TEXT
    cuts = [t.index("Une politique"), t.index("\\mathbf") + 3, len(t)]
    m = {"python": "m", "browser": "b"}
    idx = from_vectors([{"t": t, "c": "d", "s": "s", "o": cuts}], np.eye(3, 8, dtype=np.float32), "fr", m)
    runner = tmp_path / "x.php"
    runner.write_text(
        "<?php define('WSH_NO_MAIN', true); require $argv[1]; $I = wsh_load($argv[2]);"
        "$out = []; foreach ([0, 1, 2] as $k) { $qv = array_fill(0, 8, 0.0); $qv[$k] = 1.0;"
        " $out[] = wsh_excerpt(0, $qv, [], $I)['text']; } echo json_encode($out, JSON_UNESCAPED_UNICODE);",
        encoding="utf-8",
    )
    path = save(idx, tmp_path / "fr.php")
    out = subprocess.run(
        [php, str(runner), str(asset("search.php")), str(path)], capture_output=True, text=True, check=True
    )
    php_texts = json.loads(out.stdout)
    for k in range(3):
        text = excerpt(0, np.eye(3, 8, dtype=np.float32)[k], [], idx)["text"]
        assert text == php_texts[k]
        assert text.count("$$") % 2 == 0 and text.count("\\(") == text.count("\\)"), text
