"""Text normalisation shared by the index builder and the PHP engine.

The PHP endpoint tokenises the visitor's question; this module tokenises the
corpus at build time. The two must cut words the same way, or a word present
in the corpus will never be found. Every rule here therefore has a twin in
``assets/search.php``, and ``tests/test_php_parity.py`` runs both on the same
strings.

>>> fold("Éléphant")
'elephant'
>>> tokenize("La parabole de l'éléphant", stopwords("fr"))
['parabole', 'elephant']
"""

from __future__ import annotations

import re
import unicodedata

#: Default stopword lists. Short on purpose: BM25's idf already discounts
#: frequent words; these only remove words too frequent to mean anything in a
#: question. Folded spellings are what count, since tokens are folded first.
STOPWORDS = {
    "fr": (
        "le la les un une des de du et est sont que qui pour dans sur par ce cet "
        "cette ces son sa ses avec sans plus moins pas ne ou mais donc car ni si "
        "comme quand tout tous toute toutes il elle ils elles nous vous etre avoir "
        "fait faire quel quelle quels quelles quoi dont cela ceci leur leurs "
        "pourquoi comment"
    ),
    "en": (
        "the a an of and is are that which for in on by this these those his her "
        "its with without more less not or but so as when what how why there here "
        "it he she they we you be have do does did"
    ),
}

_MATH = re.compile(r"\$\$([\s\S]+?)\$\$|\\\(([\s\S]+?)\\\)")
_MACRO = re.compile(r"\\[a-zA-Z]+\s*")
_BRACES = re.compile(r"[{}\\]")


def stopwords(lang: str) -> frozenset[str]:
    """Folded stopwords for ``lang``; empty for a language without a list.

    >>> "the" in stopwords("en"), len(stopwords("xx"))
    (True, 0)
    """
    return frozenset(fold(w) for w in STOPWORDS.get(lang, "").split())


def fold(s: str) -> str:
    """Lower-case, then strip accents (NFD, combining marks U+0300–U+036F).

    >>> fold("Œuvre à Noël")
    'œuvre a noel'
    """
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if not 0x300 <= ord(c) <= 0x36F)


def strip_math(s: str) -> str:
    r"""Keep only the symbols of ``$$…$$`` and ``\(…\)`` formulas.

    >>> strip_math(r"a \(\mathbf{x}_i\) b")
    'a x_i b'
    """

    def keep(m: re.Match) -> str:
        inner = m.group(1) or m.group(2) or ""
        return _BRACES.sub("", _MACRO.sub("", inner))

    return _MATH.sub(keep, s)


def _is_word_char(c: str) -> bool:
    # Same class as PCRE's [\p{L}\p{N}].
    return unicodedata.category(c)[0] in "LN"


def tokenize(s: str, stop: frozenset[str] = frozenset()) -> list[str]:
    """Words of more than two characters, folded, stopwords removed.

    >>> tokenize("What is the data wall?", stopwords("en"))
    ['data', 'wall']
    """
    out, cur = [], []
    for c in fold(strip_math(s)) + " ":
        if _is_word_char(c):
            cur.append(c)
        elif cur:
            w = "".join(cur)
            cur = []
            if len(w) > 2 and w not in stop:
                out.append(w)
    return out
