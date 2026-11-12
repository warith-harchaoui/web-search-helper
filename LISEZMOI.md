# web-search-helper

[🇫🇷](LISEZMOI.md) · [🇬🇧](README.md)

**Interroger un corpus privé depuis un site web, avec PHP pour seul serveur.**
Le corpus s'indexe sur votre machine ; un fichier PHP répond aux questions ; la
page calcule le vecteur de chaque question dans le navigateur. Le corpus n'est
jamais publié : le visiteur reçoit quelques phrases de ce qui répond, ou un
« Je ne sais pas répondre » honnête, et rien d'autre.

Licence BSD 3-Clause. Auteur : Warith Harchaoui.

## Pourquoi

Une recherche entièrement dans le navigateur doit lui envoyer le corpus, puisqu'on
ne cherche que dans ce qu'on a. C'est acceptable pour une documentation publique,
pas pour un manuscrit, un cours ou une base interne. Chiffrer le fichier n'y
change rien : la clé doit être dans la page, elle aussi.

La plupart des hébergements offrent PHP et rien d'autre. web-search-helper
tient dans ce cadre.

| Où | Ce qui tourne | Ce qu'il faut |
|---|---|---|
| votre machine | découper, vectoriser, indexer ; mesurer les seuils | Python ≥ 3.10, `sentence-transformers` |
| le serveur | `search.php` : BM25, cosinus, fusion, verdict ; rend des extraits | PHP ≥ 7.4 avec mbstring |
| le navigateur | `web-search.js` : vecteur de la question (transformers.js), réponse composée de phrases du corpus | un navigateur qui lit les modules ES |

## Comment il cherche

- **Les mots** : BM25, passe conjonctive d'abord, tolérance timide aux fautes
  (« elefant » trouve « éléphant » parce que « elefant » est absent du corpus).
- **Le sens** : chaque passage est découpé en fenêtres que le modèle lit en
  entier ; un passage vaut le cosinus de sa meilleure fenêtre. Chaque section
  a aussi un centroïde.
- **La fusion** : fusion de rang réciproque des deux classements.
- **Le verdict** : le moteur ne répond que si l'une de trois voies dit que le
  corpus traite la question (sens de la fenêtre ET de la section, ou tous les
  mots trouvés avec un BM25 fort, ou, pour un mot seul, sa présence dans assez
  de passages). Sinon il ne rend rien. Un classement rend toujours quelque
  chose ; seule une mesure absolue sait dire non.

La recherche est exhaustive. `ann-router` choisirait HNSW dès 1 000 vecteurs
pour un budget de 10 ms, mais ce budget est celui de numpy, les corpus visés sont
petits, et le verdict juge le meilleur cosinus en valeur ABSOLUE, qu'un index
approché peut manquer. `web-search-helper bench` mesure le temps PHP sur votre
index et échoue au-delà du budget.

## Contre l'aspiration

1. Rien n'est rendu quand le corpus ne traite pas la question.
2. Un passage revient en extrait : sa meilleure fenêtre et la meilleure de ses
   voisines, recalées sur des fins de phrase. Jamais le passage entier.
3. Un plafond par adresse, par heure et par jour (empreinte salée de l'adresse,
   aucune autre trace).
4. Le fichier d'index est un script PHP : appelé par une URL, il répond un 404
   vide. Le dossier reçoit en plus un `.htaccess` qui refuse tout.

Un visiteur patient, avec des milliers de questions bien choisies, peut encore
recueillir une bonne part du corpus. Ces mesures le ralentissent, elles ne
l'empêchent pas.

## Démarrage

```bash
pip install 'web-search-helper[embed]'
web-search-helper build corpus/ -o build/fr.php --lang fr
web-search-helper calibrate build/fr.php --inside dedans.txt --outside dehors.txt --write
web-search-helper search build/fr.php "Quelle est la parabole de l'éléphant ?" --explain
web-search-helper install site/ build/fr.php
cp examples/demo.html site/index.html
web-search-helper serve site/
web-search-helper bench build/fr.php
web-search-helper check-online https://exemple.org/recherche/ --lang fr
```

Le reste (format JSONL, client JavaScript, API Python, limites) est décrit dans
le [README anglais](README.md).
