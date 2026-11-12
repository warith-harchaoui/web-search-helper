"""The suite's other doors: HTTP API, MCP, the /gui page, the skill."""

from pathlib import Path

import pytest

from web_search_helper.index import save

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client(index, index_en, tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    save(index, tmp_path / "fr.php")
    save(index_en, tmp_path / "en.php")
    monkeypatch.setenv("WSH_DATA_DIR", str(tmp_path))
    from web_search_helper.api import create_app

    return TestClient(create_app())


def test_indexes(client):
    langs = {i["lang"] for i in client.get("/indexes").json()}
    assert langs == {"fr", "en"}


def test_query_speaks_search_php(client):
    r = client.post("/query", json={"lang": "en", "q": "What is the parable of the elephant?"}).json()
    assert r["sure"] and "parable" in r["hits"][0]["text"]
    r = client.post("/query", json={"lang": "fr", "q": "la recette du cassoulet toulousain"}).json()
    assert r == {"sure": False, "terms": r["terms"]}
    assert client.post("/query", json={"lang": "../x", "q": "a"}).status_code == 400
    assert client.post("/query", json={"lang": "de", "q": "a"}).status_code == 404
    assert client.post("/query", json={"lang": "fr", "q": "agent", "v": [1.0]}).status_code == 400


def test_search_embeds_server_side(client):
    r = client.post(
        "/search", json={"lang": "fr", "question": "audit des permissions", "explain": True}
    ).json()
    assert r["explain"]["top"] is not None


def test_gui_points_at_query(client):
    html = client.get("/gui").text
    assert "endpoint: 'query'" in html and "search.php" not in html
    assert "export class WebSearch" in client.get("/web-search.js").text


def test_mcp_tools():
    pytest.importorskip("fastapi_mcp")
    from web_search_helper import mcp_server

    paths = {r.path for r in mcp_server.app.routes}
    assert "/mcp" in paths
    assert set(mcp_server.EXPOSED) == {"indexes", "search", "calibrate", "check_online"}


def test_triggers_mirrored_into_skill():
    root = (ROOT / "TRIGGERS.md").read_text(encoding="utf-8")
    skill = (ROOT / "skills/web-search-helper/references/triggers.md").read_text(encoding="utf-8")
    assert root == skill, "TRIGGERS.md and the skill's copy disagree"


def test_skill_description_fits():
    text = (ROOT / "skills/web-search-helper/SKILL.md").read_text(encoding="utf-8")
    front = text.split("---")[1]
    desc = front.split("description:")[1].split("license:")[0]
    assert len(" ".join(desc.replace(">-", "").split())) <= 1024
