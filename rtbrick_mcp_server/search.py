"""BM25 search over page sections."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List

from .extract import Page

_TOKEN = re.compile(r"[a-z0-9]+(?:[-_./:][a-z0-9]+)*")
_SPLIT = re.compile(r"[-_./:]")
_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i in is it of on or "
    "that the this to what when where which with you your".split()
)

# BM25 parameters and field weights (repeat counts) for title, heading and body tokens.
_K1 = 1.2
_B = 0.75
_TITLE_WEIGHT, _HEADING_WEIGHT = 1, 3
_MAX_HITS_PER_PAGE = 2
_SNIPPET_CHARS = 600


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str) -> List[str]:
    """Lowercase terms; compound terms like evpn-vpws also yield their parts."""
    tokens = []
    for match in _TOKEN.finditer(text.lower()):
        word = match.group()
        if word in _STOPWORDS:
            continue
        tokens.append(_stem(word))
        if _SPLIT.search(word):
            tokens.extend(_stem(p) for p in _SPLIT.split(word) if p and p not in _STOPWORDS)
    return tokens


@dataclass
class Hit:
    score: float
    source: str
    version: str
    page_title: str
    heading: str
    url: str
    snippet: str


@dataclass
class _Doc:
    source: str
    version: str
    page_url: str
    page_title: str
    heading: str
    url: str
    text: str
    tf: Counter
    length: int


class SearchIndex:
    def __init__(self) -> None:
        self._docs: List[_Doc] = []
        self._df: Counter = Counter()
        self._total_length = 0

    def __len__(self) -> int:
        return len(self._docs)

    def add_page(self, page: Page, source: str, version: str) -> None:
        title_tokens = tokenize(page.title) * _TITLE_WEIGHT
        for section in page.sections:
            if not section.text and not section.heading:
                continue
            tokens = title_tokens + tokenize(section.heading) * _HEADING_WEIGHT + tokenize(section.text)
            tf = Counter(tokens)
            self._docs.append(
                _Doc(
                    source=source,
                    version=version,
                    page_url=page.url,
                    page_title=page.title,
                    heading=section.heading,
                    url=page.section_url(section),
                    text=section.text,
                    tf=tf,
                    length=len(tokens),
                )
            )
            self._df.update(tf.keys())
            self._total_length += len(tokens)

    def search(self, query: str, limit: int = 8) -> List[Hit]:
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms or not self._docs:
            return []
        n = len(self._docs)
        avg_length = self._total_length / n
        idf: Dict[str, float] = {
            t: math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5)) for t in terms
        }
        phrase = " ".join(query.lower().split())

        scored = []
        for doc in self._docs:
            score = 0.0
            matched = 0
            for t in terms:
                f = doc.tf.get(t, 0)
                if not f:
                    continue
                matched += 1
                norm = f + _K1 * (1 - _B + _B * doc.length / avg_length)
                score += idf[t] * f * (_K1 + 1) / norm
            if not matched:
                continue
            # Prefer sections that contain every query term, and the exact phrase.
            score *= 0.5 + 0.5 * matched / len(terms)
            if len(terms) > 1 and phrase in f"{doc.heading}\n{doc.text}".lower():
                score *= 1.5
            scored.append((score, doc))

        scored.sort(key=lambda sd: (-sd[0], sd[1].url))
        hits: List[Hit] = []
        per_page: Counter = Counter()
        for score, doc in scored:
            if per_page[doc.page_url] >= _MAX_HITS_PER_PAGE:
                continue
            per_page[doc.page_url] += 1
            hits.append(
                Hit(
                    score=round(score, 2),
                    source=doc.source,
                    version=doc.version,
                    page_title=doc.page_title,
                    heading=doc.heading,
                    url=doc.url,
                    snippet=snippet(doc.text, terms),
                )
            )
            if len(hits) >= limit:
                break
        return hits


def snippet(text: str, terms: List[str]) -> str:
    """A few lines around the line that matches the most query terms."""
    lines = [ln for ln in text.split("\n") if ln.strip() and ln.strip() != "```"]
    if not lines:
        return ""
    wanted = set(terms)
    scores = [len(wanted.intersection(tokenize(ln))) for ln in lines]
    best = max(range(len(lines)), key=lambda i: scores[i])
    picked = lines[max(0, best - 1) : best + 3]
    out = "\n".join(picked)
    if len(out) > _SNIPPET_CHARS:
        out = out[:_SNIPPET_CHARS].rstrip() + "…"
    return out
