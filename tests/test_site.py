"""End to end through a real PHP server: install, serve, ask, try to steal."""

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request

import pytest
from click.testing import CliRunner

from web_search_helper.cli import main
from web_search_helper.index import save
from web_search_helper.site import install


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def site(php, index, tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    ix = save(index, tmp_path_factory.mktemp("build") / "fr.php")
    install(root, [ix])
    port = _free_port()
    state = tmp_path_factory.mktemp("state")
    # Quota state kept in the test's own folder, not the system temp dir.
    (root / "search.php").write_text(
        (root / "search.php")
        .read_text(encoding="utf-8")
        .replace("sys_get_temp_dir() . '/web-search-helper'", repr(str(state))),
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        [php, "-S", f"127.0.0.1:{port}", "-t", str(root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}/"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "search.php", timeout=1)
        except urllib.error.HTTPError:
            break
        except OSError:
            time.sleep(0.1)
    yield base
    proc.terminate()


def _post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_index_file_serves_nothing(site):
    try:
        with urllib.request.urlopen(site + "search-data/fr.php", timeout=5) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    assert status == 404 and body == b""


def test_answer_and_refusal(site):
    status, r = _post(site + "search.php", {"lang": "fr", "q": "Quelle est la parabole de l'éléphant ?"})
    assert status == 200 and r["sure"] and "parabole" in r["hits"][0]["text"]
    status, r = _post(site + "search.php", {"lang": "fr", "q": "la recette du cassoulet toulousain"})
    assert status == 200 and r == {"sure": False, "terms": r["terms"]}


def test_bad_requests(site):
    assert _post(site + "search.php", {"lang": "../etc", "q": "x"})[0] == 400
    assert _post(site + "search.php", {"lang": "de", "q": "x"})[0] == 404
    assert _post(site + "search.php", {"lang": "fr", "q": "x" * 1000})[0] == 400
    assert _post(site + "search.php", {"lang": "fr", "q": "agent", "v": [1, 2]})[0] == 400


def test_cli_dry_run(tmp_path):
    corpus = tmp_path / "c.md"
    corpus.write_text("# Doc\n\n## Une partie\n\nUn éléphant dans la pièce. " * 3, encoding="utf-8")
    out = tmp_path / "fr.php"
    r = CliRunner().invoke(main, ["build", str(corpus), "-o", str(out), "--lang", "fr", "--model", "hash"])
    assert r.exit_code == 0, r.output
    r = CliRunner().invoke(main, ["search", str(out), "éléphant pièce", "--words-only"])
    assert r.exit_code == 0 and '"sure"' in r.output


def test_quota(php, tmp_path):
    from web_search_helper.site import asset

    runner = tmp_path / "q.php"
    runner.write_text(
        "<?php define('WSH_NO_MAIN', true); define('WSH_STATE_DIR', $argv[2]);\n"
        "require $argv[1]; $_SERVER['REMOTE_ADDR'] = '203.0.113.7';\n"
        "$r = []; for ($k = 0; $k < 4; $k++) $r[] = wsh_quota(['per_hour' => 3, 'per_day' => 10]);\n"
        "$_SERVER['REMOTE_ADDR'] = '203.0.113.8'; $r[] = wsh_quota(['per_hour' => 3, 'per_day' => 10]);\n"
        "echo json_encode($r);",
        encoding="utf-8",
    )
    out = subprocess.run(
        [php, str(runner), str(asset("search.php")), str(tmp_path / "state")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(out) == [True, True, True, False, True]
    # The address itself is never written down.
    assert not any("203.0.113" in p.read_text(errors="ignore") for p in (tmp_path / "state").iterdir())
