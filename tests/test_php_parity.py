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

QUESTIONS = [
    "Quelle est la parabole de l'éléphant ?",
    "la parabol de l'elefant",            # typos
    "Qu'est-ce que le mur des données ?",
    "agent",                              # one word, frequent
    "zéphyr3",                            # one word, rare
    "la recette du cassoulet toulousain", # outside
    "audit des permissions",
    "le la les",                          # stopwords only
    "Œuvre à Noël ÉLÉPHANT",
]

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
def php_results(php, index, embedder, tmp_path_factory):
    d = tmp_path_factory.mktemp("parity")
    path = save(index, d / "fr.php")
    runner = d / "runner.php"
    runner.write_text(RUNNER, encoding="utf-8")
    cases = []
    for q in QUESTIONS:
        cases.append({"q": q, "v": None})
        cases.append({"q": q, "v": [float(x) for x in embedder.encode([q])[0]]})
    out = subprocess.run([php, str(runner), str(asset("search.php")), str(path)],
                         input=json.dumps(cases), capture_output=True, text=True, check=True)
    return cases, json.loads(out.stdout)


def _norm(v):
    a = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(a)
    return a / n if n else a


def test_tokenization_matches(php_results, index):
    cases, got = php_results
    for c, toks in zip(cases, got["tokens"]):
        assert toks == tokenize(c["q"], index.stop), c["q"]


def test_same_answers(php_results, index):
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
