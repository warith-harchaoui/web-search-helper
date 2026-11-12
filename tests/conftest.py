import shutil

import pytest

from web_search_helper.corpus import Passage
from web_search_helper.embed import HashEmbedder
from web_search_helper.index import build

CORPUS = [
    (
        "Le livre",
        "Ouverture",
        (
            "La parabole de l'éléphant raconte des aveugles qui touchent chacun une "
            "partie de l'animal. Chacun croit connaître l'éléphant entier. Aucun ne se trompe sur ce qu'il "
            "touche, tous se trompent sur le tout. C'est l'image du livre : chaque discipline tient une "
            "partie de l'intelligence artificielle."
        ),
    ),
    (
        "Le livre",
        "Ouverture",
        (
            "Un agent est un programme qui agit. Il reçoit des permissions, il "
            "exécute des actions, et ses actions ont des conséquences. Gouverner un agent, c'est gouverner "
            "ce qu'on l'autorise à faire. Les permissions dorment souvent : un droit accordé une fois reste "
            "ouvert longtemps."
        ),
    ),
    (
        "Le livre",
        "Le mur des données",
        (
            "Le mur des données désigne le moment où les textes humains "
            "disponibles ne suffisent plus à entraîner de plus grands modèles. Les laboratoires cherchent "
            "alors des données synthétiques. Ce mur est discuté, mesuré, contesté."
        ),
    ),
    (
        "Le livre",
        "Le mur des données",
        (
            "Les données synthétiques posent un problème de qualité. Un "
            "modèle entraîné sur ses propres sorties perd de la diversité. Les chercheurs parlent "
            "d'effondrement. L'agent qui produit les données n'est pas neutre."
        ),
    ),
    (
        "Annexe",
        "Audit",
        (
            "Un audit vérifie qu'un agent n'a fait que ce qui lui était permis. "
            "L'audit lit les journaux, compare les actions aux permissions, et signale les écarts. "
            "Sans journal, pas d'audit ; sans audit, pas de confiance."
        ),
    ),
] + [
    (
        "Annexe",
        f"Note {k}",
        (
            f"Note numéro {k} sur l'audit des agents et des permissions, "
            f"avec des chiffres comme {2020 + k} et des mots rares comme zéphyr{k}."
        ),
    )
    for k in range(12)
]


CORPUS_EN = [
    (
        "The book",
        "Opening",
        (
            "The parable of the elephant tells of blind men who each touch one "
            "part of the animal. Each believes he knows the whole elephant. None is wrong about what he "
            "touches; all are wrong about the whole. That is the image of the book: every discipline "
            "holds one part of artificial intelligence."
        ),
    ),
    (
        "The book",
        "Opening",
        (
            "An agent is a program that acts. It receives permissions, it "
            "performs actions, and its actions have consequences. Governing an agent means governing "
            "what it is allowed to do. Permissions often lie dormant: a right granted once stays "
            "open for a long time."
        ),
    ),
    (
        "The book",
        "The data wall",
        (
            "The data wall is the moment when the available human texts "
            "no longer suffice to train larger models. Laboratories then look for synthetic data. "
            "This wall is debated, measured, contested."
        ),
    ),
    (
        "The book",
        "The data wall",
        (
            "Synthetic data raise a quality problem. A model trained on "
            "its own outputs loses diversity. Researchers speak of collapse. The agent that produces "
            "the data is not neutral."
        ),
    ),
    (
        "Appendix",
        "Audit",
        (
            "An audit checks that an agent did only what it was permitted to do. "
            "The audit reads the logs, compares actions with permissions, and reports the gaps. "
            "Without logs, no audit; without audit, no trust."
        ),
    ),
] + [
    (
        "Appendix",
        f"Note {k}",
        (
            f"Note number {k} on the audit of agents and permissions, "
            f"with figures such as {2020 + k} and rare words such as zephyr{k}."
        ),
    )
    for k in range(12)
]

THRESHOLDS = {"sem_min": 0.3, "sec_min": 0.2, "df_min": 3, "lex_min": 2.0}


def _passages(corpus):
    return [Passage(t, d, s, url=f"page.html#{k}") for k, (d, s, t) in enumerate(corpus)]


@pytest.fixture(scope="session")
def passages():
    return _passages(CORPUS)


@pytest.fixture(scope="session")
def embedder():
    return HashEmbedder(dim=32, window_words=12)


@pytest.fixture(scope="session")
def index(passages, embedder):
    return build(passages, embedder, "fr", thresholds=THRESHOLDS)


@pytest.fixture(scope="session")
def index_en(embedder):
    return build(_passages(CORPUS_EN), embedder, "en", thresholds=THRESHOLDS)


@pytest.fixture(scope="session", params=["fr", "en"])
def lang_index(request, index, index_en):
    return index if request.param == "fr" else index_en


@pytest.fixture(scope="session")
def php():
    exe = shutil.which("php")
    if not exe:
        pytest.skip("php not on PATH")
    return exe
