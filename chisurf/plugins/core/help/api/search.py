"""Rank the documentation against what the reader typed into the browser's search box.

The ranking of the retired Qt help browser, toolkit-free. A multi-word query is split into
words and every page of the table of contents is scored: a title match beats a heading match
beats a file-name match beats a body match, because a page *about* the thing asked for is
almost always the one wanted, and the whole phrase in the title wins outright. The whole query
is never matched as one string -- "anisotropy g-factor" appears verbatim in no title, and
matching it that way returned nothing while forty pages were about it.

Each hit carries an excerpt: the passage around the first match, as readable prose, with the
markup of both dialects stripped (``(concept-anisotropy)=``, a row of ``''''``, ``.. seealso::``
cost the reader more than they tell).
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Iterable

from chisurf.plugins.core.help.api import markdown as md_api
from chisurf.plugins.core.help.api import toc as toc_api

__all__ = ["Index", "excerpt", "rank"]


class Index:
    """The searchable form of each page, read once and kept."""

    def __init__(self) -> None:
        self._pages: dict[str, dict | None] = {}

    def entry(self, path) -> dict | None:
        """Return (and cache) the searchable form of *path*, or ``None`` if it cannot be read."""
        if path is None:
            return None
        key = str(path)
        if key in self._pages:
            return self._pages[key]
        page = pathlib.Path(path)
        try:
            raw = page.read_text(encoding="utf-8")
        except Exception:
            self._pages[key] = None
            return None
        # The OKF header is metadata: matching it is fine, quoting it back is not.
        raw = md_api.strip_front_matter(raw)
        headings = "\n".join(
            match.group(1) for match in re.finditer(r"^#{1,6}\s+(.+)$", raw, re.M)
        ).lower()
        entry = {
            "path": page,
            "raw": raw,
            "text": raw.lower(),
            "headings": headings,
            "file_name": page.name.lower(),
            "title": (toc_api.page_title(page) or page.stem).lower(),
        }
        self._pages[key] = entry
        return entry


def excerpt(raw: str, words: list[str], width: int = 220) -> str:
    """Return the passage around the first match in *raw*, as readable plain text."""
    text = re.sub(r"```.*?```", " ", raw, flags=re.DOTALL)
    text = re.sub(r"^---\s*\n.*?\n---\s*\n", " ", text, flags=re.DOTALL)
    text = re.sub(r"^\([A-Za-z0-9_.:-]+\)=\s*$", " ", text, flags=re.M)
    text = re.sub(r"^\s*\.\.\s+\S+::.*$", " ", text, flags=re.M)
    text = re.sub(r"^\s*:[\w-]+:.*$", " ", text, flags=re.M)
    text = re.sub(r"^([!-/:-@\[-`{-~])\1{2,}\s*$", " ", text, flags=re.M)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r":\w+:`([^`]*)`", r"\1", text)
    text = re.sub(r"\{\w+\}`([^`]*)`", r"\1", text)
    text = re.sub(r"[#*`>|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    lowered = text.lower()
    position = -1
    for word in words:
        position = lowered.find(word)
        if position >= 0:
            break
    if position < 0:
        return text[:width]
    start = max(0, position - width // 3)
    passage = text[start : start + width].strip()
    return ("…" if start else "") + passage + ("…" if start + width < len(text) else "")


def rank(nodes: Iterable, query: str, index: Index | None = None, limit: int = 40) -> list[dict]:
    """Rank the pages of *nodes* (table-of-contents nodes with ``path`` and ``title``) for *query*.

    Parameters
    ----------
    nodes : iterable of toc.Node
        The pages, in reading order.
    query : str
        What the reader typed.
    index : Index, optional
        A cache of the pages' searchable form, kept between queries.
    limit : int, optional
        Most results to return.

    Returns
    -------
    list of dict
        ``{"node", "path", "title", "score", "excerpt"}``, best first; ties in title order.
    """
    needle = query.strip().lower()
    if not needle:
        return []
    index = index or Index()
    words = [word for word in re.split(r"\s+", needle) if word]
    results = []
    for node in nodes:
        entry = index.entry(getattr(node, "path", None))
        if entry is None:
            continue
        score = 0
        for word in words:
            if word in entry["title"]:
                score += 12
            if word in entry["file_name"]:
                score += 4
            if word in entry["headings"]:
                score += 5
            count = entry["text"].count(word)
            if count:
                score += min(count, 8)
        if needle in entry["title"]:
            score += 20
        if not score:
            continue
        results.append(
            {
                "node": node,
                "path": str(entry["path"]),
                "title": node.title,
                "score": score,
                "excerpt": excerpt(entry["raw"], words),
            }
        )
    results.sort(key=lambda hit: (-hit["score"], hit["node"].title))
    return results[:limit]
