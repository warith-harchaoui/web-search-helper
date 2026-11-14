import numpy as np

from web_search_helper.engine import search
from web_search_helper.index import from_bytes, load, save, to_bytes


def test_roundtrip(index, tmp_path):
    back = load(save(index, tmp_path / "fr.php"))
    assert back.passages == index.passages
    assert back.words == index.words and back.postings == index.postings
    assert np.array_equal(back.vectors, index.vectors)
    assert np.array_equal(back.centroids, index.centroids)
    assert back.lengths == index.lengths


def test_file_is_a_php_script_that_refuses(index):
    data = to_bytes(index)
    assert data.startswith(b"<?php http_response_code(404); exit; __halt_compiler();")
    assert from_bytes(data).meta["lang"] == "fr"


def test_lexical_answer_is_an_excerpt(index):
    r = search(index, "Quelle est la parabole de l'éléphant ?")
    assert r["sure"]
    top = r["hits"][0]
    assert "parabole" in top["text"]
    # Never more than the passage, and flagged when cut.
    full = index.passages[0]["t"]
    assert top["text"] in full
    assert top["before"] == (not full.startswith(top["text"]))


def test_refusal_returns_no_text(index):
    r = search(index, "la recette du cassoulet toulousain")
    assert r == {"sure": False, "terms": r["terms"]}


def test_typo_finds_the_word(index):
    r = search(index, "la parabol de l'elefant")
    assert "elephant" in r["terms"] and "parabole" in r["terms"]


def test_one_word_needs_presence(index):
    assert search(index, "agent")["sure"]  # in many passages
    assert not search(index, "zéphyr3")["sure"]  # in one passage only


def test_excerpts_never_exceed_two_windows(index, embedder):
    q = "audit des permissions"
    r = search(index, q, embedder.encode([q])[0])
    for h in r["hits"]:
        assert 1 <= len(h["o"]) <= 2
        assert h["o"][-1] == len(h["text"])


def test_english(index_en, embedder):
    r = search(index_en, "What is the parable of the elephant?")
    assert r["sure"] and "parable" in r["hits"][0]["text"]
    assert search(index_en, "the parabel of the elefant")["terms"][:2] == ["parable", "elephant"]
    assert not search(index_en, "the recipe for apple pie")["sure"]
    assert search(index_en, "agent")["sure"] and not search(index_en, "zephyr3")["sure"]
    q = "audit of permissions"
    for h in search(index_en, q, embedder.encode([q])[0])["hits"]:
        assert h["text"] in "".join(p["t"] for p in index_en.passages)


def test_from_vectors_keeps_the_given_vectors(index):
    from web_search_helper.index import from_vectors, vectors_from_int8

    rows = [{k: p[k] for k in ("t", "c", "s", "o")} for p in index.passages]
    again = from_vectors(rows, index.vectors, "fr", index.meta["model"], stop=index.stop)
    assert np.array_equal(again.vectors, index.vectors)
    assert again.words == index.words and np.allclose(again.centroids, index.centroids)

    q8 = np.clip(np.rint(index.vectors * 127), -127, 127).astype(np.int8).tobytes()
    back = vectors_from_int8(q8, index.meta["dim"])
    assert np.allclose(np.linalg.norm(back, axis=1), 1.0, atol=1e-5)


def test_from_vectors_checks_alignment():
    import pytest

    from web_search_helper.index import from_vectors

    m = {"python": "m", "browser": "b"}
    with pytest.raises(ValueError, match="windows announced"):
        from_vectors([{"t": "abc", "c": "d", "s": "s", "o": [3]}], np.zeros((2, 4), np.float32), "fr", m)
    with pytest.raises(ValueError, match="non-decreasing"):
        from_vectors([{"t": "abc", "c": "d", "s": "s", "o": [2, 1]}], np.zeros((2, 4), np.float32), "fr", m)
    # An empty window (a trailing " ." cut on its own) is accepted.
    from_vectors([{"t": "ab .", "c": "d", "s": "s", "o": [4, 4]}], np.eye(2, 4, dtype=np.float32), "fr", m)
