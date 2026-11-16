# Exemples de web-search-helper

[🇫🇷](https://github.com/warith-harchaoui/web-search-helper/blob/main/EXEMPLES.md)&nbsp;&nbsp;|&nbsp;&nbsp;[🇬🇧](https://github.com/warith-harchaoui/web-search-helper/blob/main/EXAMPLES.md)

Un recueil autonome. Chaque commande ci-dessous a tourné avec
`web-search-helper 0.2.0`, l'extra `[embed]` et le modèle par défaut
(`paraphrase-multilingual-MiniLM-L12-v2`), sur un Mac Apple Silicon, le
2026-11-15 ; la sortie montrée est celle qui est revenue. Les cosinus comme
les temps dépendent de la machine et de la version du modèle ; ce sont les
verdicts (`"sure"`) qu'il faut comparer.

## Table des matières

- [Mise en place](#mise-en-place)
- [1. Construire un index](#1-construire-un-index)
- [2. Avant le calibrage, le moteur refuse](#2-avant-le-calibrage-le-moteur-refuse)
- [3. Calibrer la règle « je ne sais pas répondre »](#3-calibrer-la-règle--je-ne-sais-pas-répondre-)
- [4. Une question à laquelle le corpus répond](#4-une-question-à-laquelle-le-corpus-répond)
- [5. Une question à laquelle il ne répond pas](#5-une-question-à-laquelle-il-ne-répond-pas)
- [6. Le premier appel, sur les mots seuls](#6-le-premier-appel-sur-les-mots-seuls)
- [7. Installer dans un site, chronométrer le moteur PHP](#7-installer-dans-un-site-chronométrer-le-moteur-php)
- [8. La même chose en Python](#8-la-même-chose-en-python)
- [Ligne de commande](#ligne-de-commande)

## Mise en place

```bash
pip install 'web-search-helper[embed]'    # ou, depuis un clone : pip install -e '.[embed]'
```

Les exemples s'appuient sur un corpus de quatre sections sur l'apiculture.
Enregistrez-le sous `corpus-fr/apiculture.md` :

```markdown
# Carnet d'apiculture

## Visite de printemps

Ouvrez la ruche par un après-midi chaud et sans vent, au-dessus de quinze degrés. Cherchez des œufs dressés au fond des cellules : ils prouvent que la reine pondait il y a trois jours. Comptez les cadres couverts d'abeilles plutôt que les abeilles elles-mêmes.

## Essaimage

Une colonie essaime quand elle manque de place. Les cellules royales suspendues sous les cadres sont le signal d'alarme. Poser une hausse avant la grande miellée donne de l'espace aux abeilles ; cela évite le plus souvent l'essaim.

## Varroa

Le varroa se nourrit des corps gras des abeilles et propage des virus. Comptez les acariens tombés sur un lange graissé pendant trois jours ; plus de dix par jour en fin d'été appellent un traitement, de préférence à l'acide oxalique quand la colonie n'a pas de couvain.

## Hiver

Une colonie a besoin d'environ quinze kilos de miel pour passer l'hiver. Pesez la ruche en la soulevant par l'arrière. Laissez les abeilles tranquilles par temps froid : chaque ouverture leur coûte une chaleur qu'elles n'ont pas en trop.
```

Puis deux fichiers de questions, une par ligne : `dedans.txt` pour les
questions auxquelles le corpus répond, `dehors.txt` pour celles auxquelles il
ne répond pas.

```bash
printf 'Quand faut-il traiter contre le varroa ?\nComment empêcher une colonie d’essaimer ?\nCombien de miel faut-il pour l’hiver ?\nQue disent les œufs dans les cellules ?\n' > dedans.txt
printf 'Comment faire du pain au levain ?\nQuelle est la capitale de l’Australie ?\nQuel train va à Lyon ?\nComment changer un pneu de vélo ?\n' > dehors.txt
```

## 1. Construire un index

```bash
web-search-helper build corpus-fr/ -o build/fr.php --lang fr
# fr: 4 passages, 4 windows, 4 sections, 85 words -> build/fr.php
# ann-router at a 100 ms budget: exact. The PHP engine scans exhaustively; `web-search-helper bench build/fr.php` measures whether that fits.
```

Le premier lancement télécharge le modèle (environ 480 Mo) dans le cache de
Hugging Face. L'index est un fichier PHP qui répond 404 quand on le demande par
une URL ; ses données suivent `__halt_compiler();`.

## 2. Avant le calibrage, le moteur refuse

Les seuils par défaut sont volontairement stricts. Sur un corpus neuf, même
une question à laquelle il répond est refusée :

```bash
web-search-helper search build/fr.php "Quand faut-il traiter contre le varroa ?" --explain
# {
#   "sure": false,
#   "terms": ["varroa"],
#   "explain": {"best": 0.0732, "conj": false, "df1": 0, "typed": 7, "top": 0.5340, "sectop": 0.5340}
# }
```

`top` (0,53) est le cosinus de la meilleure fenêtre, `sectop` celui de la
meilleure section ; tous deux restent sous le `sem_min` par défaut de 0,55.
Refuser est l'échec sans danger : un index non calibré ne dit rien plutôt que
de dire faux.

## 3. Calibrer la règle « je ne sais pas répondre »

```bash
web-search-helper calibrate build/fr.php --inside dedans.txt --outside dehors.txt --write
# {
#   "thresholds_before": {"sem_min": 0.55, "sec_min": 0.561, "lex_min": 5.0, "df_min": 9},
#   "routes": {
#     "df_min": {"value": 9, "margin": null},
#     "lex_min": {"value": 5.0, "margin": null},
#     "sem_min": {"value": 0.383, "margin": 0.0849},
#     "sec_min": {"value": 0.383, "margin": 0.0849}
#   },
#   "thresholds": {"sem_min": 0.383, "sec_min": 0.383, "lex_min": 5.0, "df_min": 9},
#   "wrong": [],
#   "n": {"inside": 4, "outside": 4}
# }
# thresholds written to build/fr.php
```

Le seuil de sens descend à 0,383, à mi-chemin entre les questions du dedans et
celles du dehors, avec une marge de 0,085 de chaque côté. `"wrong": []` veut
dire que chaque question de calibrage reçoit désormais le bon verdict. Une
marge `null` signale une voie que les questions n'ont jamais empruntée : son
seuil reste tel quel. `--dry-run` lit le rapport sans l'écrire. Quatre
questions de chaque côté suffisent pour une démonstration ; un vrai corpus en
demande quelques dizaines.

## 4. Une question à laquelle le corpus répond

```bash
web-search-helper search build/fr.php "Quand faut-il traiter contre le varroa ?"
# {
#   "sure": true,
#   "terms": ["varroa"],
#   "hits": [
#     {
#       "doc": "Carnet d'apiculture",
#       "section": "Varroa",
#       "url": "",
#       "meta": {},
#       "text": "Le varroa se nourrit des corps gras des abeilles et propage des virus. Comptez les acariens tombés sur un lange graissé pendant trois jours ; plus de dix par jour en fin d'été appellent un traitement, de préférence à l'acide oxalique quand la colonie n'a pas de couvain.",
#       "o": [270],
#       "cos": [0.5340],
#       "before": false,
#       "after": false
#     },
#     ... trois autres résultats : Essaimage, Visite de printemps, Hiver
#   ]
# }
```

Une question qui ne partage presque aucun mot avec sa réponse se trouve par le
sens :

```bash
web-search-helper search build/fr.php "Comment garder mes abeilles de partir ?"
# "sure": true, résultats dans cet ordre : Visite de printemps (cos 0,633), Essaimage (0,611), Hiver (0,612), Varroa
```

Le seul mot retenu est `abeilles`, présent dans les quatre sections ; le sens
fait le reste. Sur un corpus de quatre passages, Essaimage arrive deuxième et
non premier : les trois premiers cosinus tiennent en deux centièmes.

## 5. Une question à laquelle il ne répond pas

```bash
web-search-helper search build/fr.php "Comment faire du pain au levain ?" --explain
# {
#   "sure": false,
#   "terms": [],
#   "explain": {"best": 0.0, "conj": false, "df1": 0, "typed": 7, "top": 0.2986, "sectop": 0.2986}
# }
```

Aucun mot trouvé, un meilleur cosinus (0,30) sous le seuil calibré de 0,383 :
aucun résultat. C'est ce que `search.php` envoie au visiteur, sans rien du
corpus avec.

## 6. Le premier appel, sur les mots seuls

La page appelle le serveur deux fois : sur les mots seuls d'abord, avant que le
modèle soit chargé dans le navigateur ; puis sur les mots avec le sens.

```bash
web-search-helper search build/fr.php "varroa oxalique" --words-only
# {
#   "sure": false,
#   "terms": ["varroa", "oxalique"]
# }
```

Les deux mots sont dans le corpus ; sur quatre passages courts, leur BM25
reste pourtant sous `lex_min` (5,0) : la voie des mots ne s'engage pas seule,
le second appel, avec le sens, tranche. Sur un corpus de quelques centaines de
passages, la même requête s'engage dès le premier appel.

## 7. Installer dans un site, chronométrer le moteur PHP

```bash
web-search-helper install site/ build/fr.php build/en.php --demo
# site/search.php
# site/web-search.js
# site/web-search.d.ts
# site/writer-plan.json
# site/demo.html
# site/search-data/.htaccess
# site/search-data/fr.php
# site/search-data/en.php
# Upload search.php, web-search.js and the whole data folder, .htaccess included; then run `web-search-helper check-online <url> --lang …`.

web-search-helper bench build/en.php --runs 5 --question "varroa"
# {
#   "load_ms": 7.21,
#   "search_ms_median": 0.47,
#   "search_ms_max": 2.64,
#   "vectors": 4,
#   "memory_mb": 0.84,
#   "php": "8.5.9",
#   "slowing_extensions": ["pcov"]
# }
# warning: pcov loaded; it slows PHP loops several times over and is rarely on a production server. Measure there too (check-online reports the endpoint's time).
```

`build/en.php` est le même corpus en anglais (voir [EXAMPLES.md](https://github.com/warith-harchaoui/web-search-helper/blob/main/EXAMPLES.md)).
`web-search-helper serve site/` sert le dossier avec `php -S`, comme le ferait
l'hébergeur ; la démonstration répond sur `http://127.0.0.1:8765/demo.html?lang=fr`.
Après l'envoi, `web-search-helper check-online https://exemple.org/recherche/ --lang fr`
vérifie que le fichier d'index n'est pas servi et que le point d'accès répond.

## 8. La même chose en Python

```python
import web_search_helper as wsh

emb = wsh.SentenceTransformerEmbedder()  # paraphrase-multilingual-MiniLM-L12-v2
idx = wsh.build(wsh.read_corpus("corpus-en/"), emb, "en")
inside = open("inside-en.txt").read().splitlines()
outside = open("outside-en.txt").read().splitlines()
report = wsh.calibrate(idx, inside, outside, emb)
idx.meta["thresholds"] = report["thresholds"]
print(report["thresholds"], report["wrong"])
# {'sem_min': 0.31, 'sec_min': 0.31, 'lex_min': 5.0, 'df_min': 9} []

for q in ["How much honey for the winter?", "Who won the 1998 World Cup?"]:
    r = wsh.search(idx, q, emb.encode([q])[0])
    print(q, "->", r["sure"], [h["section"] for h in r.get("hits", [])])
# How much honey for the winter? -> True ['Winter', 'Spring inspection', 'Varroa', 'Swarming']
# Who won the 1998 World Cup? -> False []
```

Cet exemple tourne sur le corpus anglais d'[EXAMPLES.md](https://github.com/warith-harchaoui/web-search-helper/blob/main/EXAMPLES.md),
tel qu'il a été exécuté. `wsh.calibrate` rend le rapport sans toucher à
l'index ; les seuils se posent à la main, puis `wsh.save(idx, "build/en.php")`
écrit le fichier que lit `search.php`. `wsh.search` sans vecteur de question
est l'appel sur les mots seuls de l'exemple 6.

## Ligne de commande

| Commande | Ce qu'elle fait |
|---|---|
| `build CORPUS -o INDEX --lang L` | Indexe un `.jsonl`, un fichier Markdown, un fichier texte ou un dossier qui en contient. `--model hash` construit sans poids, pour un essai à blanc. |
| `calibrate INDEX --inside F --outside F [--write]` | Mesure les seuils de la règle « je ne sais pas répondre ». |
| `search INDEX QUESTION [--explain] [--words-only]` | Répond comme le ferait `search.php`. |
| `install SITE INDEX... [--demo]` | Copie `search.php`, `web-search.js` et les index dans le dossier du site. |
| `serve SITE` | Sert le dossier avec `php -S`. |
| `bench INDEX [--budget-ms N]` | Chronomètre le moteur PHP ; échoue au-delà du budget. |
| `check-online URL --lang L` | Après l'envoi : le corpus est-il privé, le point d'accès répond-il ? |

`web-search-helper COMMANDE --help` liste toutes les options.
