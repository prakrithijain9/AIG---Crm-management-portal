"""Closest-name matching for search terms with typos, different word order or "&" vs "and".

Used only when exact "contains" search finds nothing. Plain difflib over the names, so no
database extension or migration is needed. It reads every name, which is fine for thousands
of records; past that, move to PostgreSQL's pg_trgm.
"""

import re
from collections.abc import Iterable, Sequence
from difflib import SequenceMatcher
from functools import lru_cache
from typing import TypeVar

Key = TypeVar("Key")

THRESHOLD = 0.75  # average word similarity needed to suggest a name
WORD_FLOOR = 0.7  # every word typed must be at least this close to some word in the name
MIN_GUESS_LENGTH = 3  # shorter words must match exactly
# Words people add around a name that say nothing about which record they mean.
FILLER = frozenset(
    "a an and the of for at to co company companies corp inc llc ltd limited group "
    "deal deals contact contacts activity activities account accounts "
    "thing things stuff one guys people client clients customer customers".split()
)


def words(value: str) -> list[str]:
    """The words that identify a record: lower case, punctuation and filler words removed."""
    cleaned = re.sub(r"[^\w]+", " ", value.casefold().replace("&", " and "))
    return [word for word in cleaned.split() if word not in FILLER]


@lru_cache(maxsize=50_000)  # names repeat words heavily (company names across deals)
def _word_score(typed: str, word: str) -> float:
    if typed == word:
        return 1.0
    # Numbers are identifiers: invoice 1042 is not a misspelling of invoice 1043.
    if len(typed) < MIN_GUESS_LENGTH or any(c.isdigit() for c in typed + word):
        return 0.0
    return SequenceMatcher(None, typed, word).ratio()


def similarity(query: str, text: str) -> float:
    """0 to 1: how well the words of ``query`` are covered by the words of ``text``."""
    typed, named = words(query), words(text)
    if not typed or not named:
        return 0.0
    if len(typed) > 1 and "".join(typed) in named:  # "north wind" for "Northwind"
        return 1.0
    scores = [max(_word_score(t, w) for w in named) for t in typed]
    if min(scores) < WORD_FLOOR:
        return 0.0
    return sum(scores) / len(scores)


def closest(query: str, items: Iterable[tuple[Key, Sequence[str]]], limit: int = 5) -> list[Key]:
    """Keys of the best matching items, best first. Each item is (key, texts to compare against)."""
    scored: list[tuple[float, int, Key]] = []
    for position, (key, texts) in enumerate(items):
        # The texts together too, so "Priya Northwind" can match a name plus its company.
        score = max(similarity(query, t) for t in [*texts, " ".join(texts)])
        if score >= THRESHOLD:
            scored.append((score, position, key))
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    return [key for _, _, key in scored[:limit]]
