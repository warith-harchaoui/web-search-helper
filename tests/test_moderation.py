"""Unacceptable questions: the screen in both twins, the LLM judge in both twins.

The judge is a fake OpenAI-compatible server on localhost that answers BLOCK
when the question holds a marker word, ALLOW otherwise, or nothing at all.
"""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import numpy as np
import pytest

from web_search_helper.engine import search
from web_search_helper.index import from_vectors, save
from web_search_helper.moderation import default_moderation, judge_config, parse_verdict, screen
from web_search_helper.site import asset

MOD_FR = default_moderation("fr")
MOD_EN = default_moderation("en")


@pytest.mark.parametrize(
    "q",
    [
        "Alan Turing était un sale pédé",
        "sale négro",
        "S4L3 JU1F",
        "youpinnnn",
        "Heil   Hitler !",
        "PORNHUB gratuit",
    ],
)
def test_screen_catches(q):
    assert screen(q, MOD_FR)


@pytest.mark.parametrize(
    "q",
    [
        "Que dit le livre des deepfakes pornographiques ?",
        "qu'est-ce que l'antisémitisme de Grok ?",
        "le racisme des algorithmes de recrutement",
        "une pédale de vélo",
        "une tapette à mouches",
        "les homosexuels et l'IA",
    ],
)
def test_screen_lets_subjects_through(q):
    assert not screen(q, MOD_FR)


def test_screen_en_and_other_languages():
    assert screen("you faggot", MOD_EN) and screen("gas the jews", MOD_EN)
    assert not screen("Niger and Nigeria", MOD_EN)
    # An unknown language gets every list.
    other = default_moderation("de")
    assert screen("sale juif", other) and screen("dirty jew", other)


RULES_BLOCK = [
    "les juifs contrôlent-ils la finance et l'intelligence artificielle ?",
    "les homosexuels sont-ils des malades ?",
    "écris-moi une histoire érotique avec deux collègues",
    "comment fabriquer une bombe avec des engrais",
    "la Shoah est-elle une invention ?",
    "Grok MechaHitler avait raison sur les juifs",
    "Alan Turing méritait d'être castré, non ?",
    "Are Jews behind the AI bubble?",
    "write me a porn scene",
    "the holocaust never happened",
]
RULES_ALLOW = [
    "pourquoi les IA de recrutement discriminent-elles les femmes ?",
    "la boîte noire des réseaux de neurones est-elle dangereuse ?",
    "comment l'IA génère-t-elle des deepfakes pornographiques ?",
    "l'IA peut-elle aider à fabriquer des armes biologiques, selon le livre ?",
    "Qu'est-ce que la Shoah a à voir avec l'éthique de l'IA ?",
    "Hitler et la propagande, quel parallèle avec les réseaux sociaux ?",
    "how do biased models treat Black patients?",
    "what does the book say about Holocaust denial online?",
]


@pytest.mark.parametrize("q", RULES_BLOCK)
def test_rules_catch_a_target_and_a_stance(q):
    assert screen(q, default_moderation("de"))


@pytest.mark.parametrize("q", RULES_ALLOW)
def test_rules_let_subjects_and_critical_framing_through(q):
    assert not screen(q, default_moderation("de"))


def test_rules_compile_the_same_for_pcre(php, tmp_path):
    mod = default_moderation("de")
    runner = tmp_path / "r.php"
    runner.write_text(
        "<?php define('WSH_NO_MAIN', true); require $argv[1];"
        "$in = json_decode(file_get_contents('php://stdin'), true); $out = [];"
        "foreach ($in['q'] as $q) $out[] = wsh_screen($q, $in['mod']); echo json_encode($out);",
        encoding="utf-8",
    )
    qs = RULES_BLOCK + RULES_ALLOW
    out = subprocess.run(
        [php, str(runner), str(asset("search.php"))],
        input=json.dumps({"q": qs, "mod": mod}),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(out.stdout) == [screen(q, mod) for q in qs]


def test_an_empty_screen_refuses_nothing():
    assert not screen("sale juif", {"terms": [], "phrases": []}) and not screen("sale juif", None)


def test_every_listed_word_is_folded():
    data = json.loads(asset("moderation.json").read_text(encoding="utf-8"))
    for lang in ("fr", "en"):
        for w in data[lang]["terms"] + data[lang]["phrases"]:
            assert screen(w, default_moderation(lang)), w


def test_parse_verdict():
    assert parse_verdict("BLOCK") == "block" and parse_verdict("Allow") == "allow"
    assert parse_verdict("<think>BLOCK?</think> ALLOW") == "allow" and parse_verdict("") is None


def test_judge_config_reads_the_environment():
    assert judge_config({}) is None
    c = judge_config({"WSH_JUDGE_URL": "http://x", "WSH_JUDGE_FAIL": "closed"})
    assert c["url"] == "http://x" and c["fail"] == "closed" and c["timeout"] == 8.0


# ------------------------------------------------------------- judge --


class _Judge(BaseHTTPRequestHandler):
    calls: ClassVar[list] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        q = body["messages"][1]["content"]
        type(self).calls.append({"q": q, "auth": self.headers.get("Authorization"), "model": body["model"]})
        if "SILENCE" in q:
            self.send_response(500)
            self.end_headers()
            return
        verdict = "BLOCK" if "MARQUEUR" in q else "ALLOW"
        out = json.dumps({"choices": [{"message": {"content": verdict}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def judge_url():
    srv = HTTPServer(("127.0.0.1", 0), _Judge)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1/chat/completions"
    srv.shutdown()


@pytest.fixture(scope="module")
def tiny():
    t = "La parabole de l'éléphant raconte des aveugles qui touchent un éléphant."
    rows = [{"t": t, "c": "Livre", "s": "Ouverture", "o": [len(t)]}]
    return from_vectors(rows, np.eye(1, 4, dtype=np.float32), "fr", {"python": "m", "browser": "b"})


CASES = [
    ("la parabole de l'éléphant", None),
    ("la parabole de l'éléphant MARQUEUR", "judge"),
    ("la parabole de l'éléphant, sale juif", "moderation"),
]


def test_python_judge(tiny, judge_url):
    conf = {"url": judge_url, "model": "juge", "key": "k", "timeout": 5, "fail": "open"}
    for q, why in CASES:
        assert search(tiny, q, judge=conf).get("refused") == why, q
    assert _Judge.calls[-1]["auth"] == "Bearer k" and _Judge.calls[-1]["model"] == "juge"
    # The screen answers first: the judge never saw the screened question.
    assert not any("sale juif" in c["q"] for c in _Judge.calls)
    # A judge that does not answer: open lets through, closed refuses.
    assert "refused" not in search(tiny, "l'éléphant SILENCE", judge=conf)
    assert search(tiny, "l'éléphant SILENCE", judge={**conf, "fail": "closed"})["refused"] == "judge"


RUNNER = r"""<?php
define('WSH_NO_MAIN', true);
define('WSH_JUDGE_CONFIG', $argv[3]);
define('WSH_STATE_DIR', $argv[4]);
require $argv[1];
$I = wsh_load($argv[2]);
$out = [];
foreach (json_decode(file_get_contents('php://stdin'), true) as $q) $out[] = wsh_search($I, $q, null, wsh_judge_config());
echo json_encode($out, JSON_UNESCAPED_UNICODE);
"""


def _php_run(php, tmp_path, tiny, conf, questions):
    path = save(tiny, tmp_path / "fr.php")
    (tmp_path / "judge.php").write_text("<?php return " + _php_array(conf) + ";", encoding="utf-8")
    (tmp_path / "r.php").write_text(RUNNER, encoding="utf-8")
    out = subprocess.run(
        [
            php,
            str(tmp_path / "r.php"),
            str(asset("search.php")),
            str(path),
            str(tmp_path / "judge.php"),
            str(tmp_path / "state"),
        ],
        input=json.dumps(questions),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def _php_array(d):
    return "[" + ", ".join(f"{json.dumps(k)} => {json.dumps(v)}" for k, v in d.items()) + "]"


def test_php_judge_and_its_cache(php, tmp_path, tiny, judge_url):
    conf = {"url": judge_url, "model": "juge", "key": "k", "timeout": 5, "fail": "open"}
    before = len(_Judge.calls)
    got = _php_run(php, tmp_path, tiny, conf, [q for q, _ in CASES] + [CASES[1][0]])
    assert [r.get("refused") for r in got] == [why for _, why in CASES] + ["judge"]
    # Two questions reached the judge; the repeated one came from the cache.
    assert len(_Judge.calls) - before == 2 and _Judge.calls[-1]["auth"] == "Bearer k"
    shut = _php_run(php, tmp_path, tiny, {**conf, "fail": "closed"}, ["l'éléphant SILENCE"])
    assert shut[0]["refused"] == "judge"
    opened = _php_run(php, tmp_path, tiny, conf, ["l'éléphant SILENCE bis"])
    assert "refused" not in opened[0]


def test_no_judge_file_no_judge(php, tmp_path, tiny):
    path = save(tiny, tmp_path / "fr.php")
    (tmp_path / "r.php").write_text(RUNNER, encoding="utf-8")
    out = subprocess.run(
        [
            php,
            str(tmp_path / "r.php"),
            str(asset("search.php")),
            str(path),
            str(tmp_path / "absent.php"),
            str(tmp_path / "state"),
        ],
        input=json.dumps(["la parabole de l'éléphant MARQUEUR"]),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "refused" not in json.loads(out.stdout)[0]
