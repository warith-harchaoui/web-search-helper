import shutil

import pytest

from web_search_helper.corpus import Passage
from web_search_helper.embed import HashEmbedder
from web_search_helper.index import build

CORPUS = [
    ("Le livre", "Ouverture", ("La parabole de l'éléphant raconte des aveugles qui touchent chacun une "
     "partie de l'animal. Chacun croit connaître l'éléphant entier. Aucun ne se trompe sur ce qu'il "
     "touche, tous se trompent sur le tout. C'est l'image du livre : chaque discipline tient une "
     "partie de l'intelligence artificielle.")),
    ("Le livre", "Ouverture", ("Un agent est un programme qui agit. Il reçoit des permissions, il "
     "exécute des actions, et ses actions ont des conséquences. Gouverner un agent, c'est gouverner "
     "ce qu'on l'autorise à faire. Les permissions dorment souvent : un droit accordé une fois reste "
     "ouvert longtemps.")),
    ("Le livre", "Le mur des données", ("Le mur des données désigne le moment où les textes humains "
     "disponibles ne suffisent plus à entraîner de plus grands modèles. Les laboratoires cherchent "
     "alors des données synthétiques. Ce mur est discuté, mesuré, contesté.")),
    ("Le livre", "Le mur des données", ("Les données synthétiques posent un problème de qualité. Un "
     "modèle entraîné sur ses propres sorties perd de la diversité. Les chercheurs parlent "
     "d'effondrement. L'agent qui produit les données n'est pas neutre.")),
    ("Annexe", "Audit", ("Un audit vérifie qu'un agent n'a fait que ce qui lui était permis. "
     "L'audit lit les journaux, compare les actions aux permissions, et signale les écarts. "
     "Sans journal, pas d'audit ; sans audit, pas de confiance.")),
] + [("Annexe", f"Note {k}", (f"Note numéro {k} sur l'audit des agents et des permissions, "
      f"avec des chiffres comme {2020 + k} et des mots rares comme zéphyr{k}.")) for k in range(12)]


@pytest.fixture(scope="session")
def passages():
    return [Passage(t, d, s, url=f"page.html#{k}") for k, (d, s, t) in enumerate(CORPUS)]


@pytest.fixture(scope="session")
def embedder():
    return HashEmbedder(dim=32, window_words=12)


@pytest.fixture(scope="session")
def index(passages, embedder):
    return build(passages, embedder, "fr", thresholds={"sem_min": 0.3, "sec_min": 0.2, "df_min": 3, "lex_min": 2.0})


@pytest.fixture(scope="session")
def php():
    exe = shutil.which("php")
    if not exe:
        pytest.skip("php not on PATH")
    return exe
