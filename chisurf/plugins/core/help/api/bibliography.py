"""The one place a work ChiSurf's documentation cites is described.

Before this, a paper was written out wherever it was needed — sometimes with a
DOI, usually without, in a different order each time, and never in a form a
reader could click. Two pages citing the same paper said it differently, and
nothing could list what the documentation rests on.

So citations are **keys** into one file, ``docs/references/bibliography.yaml``:

.. code-block:: yaml

   magde1972:
     authors: D. Magde, E. L. Elson, W. W. Webb
     title: Thermodynamic fluctuations in a reacting system
     journal: Physical Review Letters
     year: 1972
     doi: 10.1103/PhysRevLett.29.705

A page cites it with ``{cite}`magde1972```, which becomes a link — to
``https://doi.org/…`` where a DOI is known, and otherwise to a literature search
for the title, because a reader who wants the paper wants a way to *get* it, not
a formatted string. The Literature page lists every entry.

Nothing here needs Qt or Sphinx: the help browser, the ``?`` modal and the
generator that writes the Literature page all read the same file.
"""

from __future__ import annotations

import pathlib
import re
import urllib.parse
from dataclasses import dataclass, field

__all__ = [
    "Entry",
    "bibliography",
    "cite_html",
    "cite_markdown",
    "entry_url",
    "expand_citations",
    "format_entry",
    "short_citation",
    "unknown_keys",
]

#: ``{cite}`key``` and ``{cite}`key1,key2``` — the role pages use.
CITE_ROLE = re.compile(r"\{cite\}`([^`]+)`")

#: Where the bibliography lives, relative to ``docs/``.
BIBLIOGRAPHY = "references/bibliography.yaml"


@dataclass
class Entry:
    """One work the documentation cites."""

    key: str
    authors: str = ""
    title: str = ""
    journal: str = ""
    year: str = ""
    volume: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    note: str = ""
    topics: list[str] = field(default_factory=list)

    @property
    def first_author(self) -> str:
        """Surname of the first author, for a short citation."""
        first = self.authors.split(",")[0].strip()
        if not first:
            return self.key
        # "D. Magde" and "Magde, D." both give "Magde".
        parts = [p for p in first.replace(".", " ").split() if len(p) > 1]
        return parts[-1] if parts else first

    @property
    def multiple_authors(self) -> bool:
        """Whether the work has more than one author."""
        return "," in self.authors or " and " in self.authors


def _docs_root() -> pathlib.Path:
    from chisurf.plugins.core.help.api.toc import docs_root

    return docs_root()


_CACHE: dict[str, Entry] | None = None


def bibliography(refresh: bool = False) -> dict[str, Entry]:
    """Return every bibliography entry, keyed by citation key.

    Parameters
    ----------
    refresh : bool
        Re-read the file instead of using the cached parse.

    Returns
    -------
    dict
        ``{key: Entry}``; empty when the file is absent or unreadable.

    """
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE
    entries: dict[str, Entry] = {}
    path = _docs_root() / BIBLIOGRAPHY
    if path.is_file():
        try:
            import yaml

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            raw = {}
        for key, value in (raw.items() if isinstance(raw, dict) else []):
            if not isinstance(value, dict):
                continue
            topics = value.get("topics") or []
            if isinstance(topics, str):
                topics = [topics]
            entries[key] = Entry(
                key=key,
                authors=str(value.get("authors", "")),
                title=str(value.get("title", "")),
                journal=str(value.get("journal", "")),
                year=str(value.get("year", "")),
                volume=str(value.get("volume", "")),
                pages=str(value.get("pages", "")),
                doi=str(value.get("doi", "")).strip(),
                url=str(value.get("url", "")).strip(),
                note=str(value.get("note", "")),
                topics=[str(t) for t in topics],
            )
    _CACHE = entries
    return entries


def entry_url(entry: Entry) -> str:
    """Return where a reader should be sent to get this work.

    A DOI first, then an explicit URL, and failing both a literature search for
    the title — which still lands the reader on a page they can download from,
    and is honest about the fact that no identifier is recorded.
    """
    if entry.doi:
        return f"https://doi.org/{entry.doi.lstrip('/')}"
    if entry.url:
        return entry.url
    query = urllib.parse.quote_plus(f"{entry.title} {entry.journal} {entry.year}".strip())
    return f"https://search.crossref.org/search/works?q={query}&from_ui=yes"


def short_citation(entry: Entry) -> str:
    """Return the words a citation reads as: "Magde et al. (1972)"."""
    author = entry.first_author
    suffix = " et al." if entry.multiple_authors else ""
    year = f" ({entry.year})" if entry.year else ""
    return f"{author}{suffix}{year}".strip()


def format_entry(entry: Entry) -> str:
    """Return the full reference as one line of Markdown, without the link."""
    pieces = [entry.authors.rstrip(".") + "." if entry.authors else ""]
    if entry.title:
        pieces.append(f"*{entry.title.rstrip('.')}*.")
    journal = entry.journal
    if journal:
        detail = journal
        if entry.volume:
            detail += f" **{entry.volume}**"
        if entry.pages:
            detail += f", {entry.pages}"
        pieces.append(detail.rstrip(".") + ".")
    if entry.year:
        pieces.append(f"({entry.year}).")
    return " ".join(piece for piece in pieces if piece).strip()


def cite_markdown(keys: str) -> str:
    """Render one ``{cite}`` role as Markdown links.

    Parameters
    ----------
    keys : str
        The role's content: one key, or several separated by commas.

    Returns
    -------
    str
        ``[Magde et al. (1972)](https://doi.org/…)``, several joined by "; ".
        An unknown key renders as itself in code style, so a typo is visible
        rather than silently dropped.

    """
    entries = bibliography()
    parts = []
    for key in (k.strip() for k in keys.split(",")):
        if not key:
            continue
        entry = entries.get(key)
        if entry is None:
            parts.append(f"`{key}`")
            continue
        parts.append(f"[{short_citation(entry)}]({entry_url(entry)})")
    return "; ".join(parts)


def cite_html(keys: str) -> str:
    """Render one ``{cite}`` role as HTML links."""
    entries = bibliography()
    parts = []
    for key in (k.strip() for k in keys.split(",")):
        if not key:
            continue
        entry = entries.get(key)
        if entry is None:
            parts.append(f"<code>{key}</code>")
            continue
        parts.append(f'<a href="{entry_url(entry)}">{short_citation(entry)}</a>')
    return "; ".join(parts)


def expand_citations(text: str) -> str:
    """Rewrite every ``{cite}`` role in *text* into a Markdown link."""
    return CITE_ROLE.sub(lambda match: cite_markdown(match.group(1)), str(text))


def unknown_keys(text: str) -> list[str]:
    """Return the citation keys in *text* that the bibliography does not define.

    Code is skipped: a page that *documents* the citation syntax shows
    ``{cite}`key``` in a code span, and that is an example, not a citation.
    """
    entries = bibliography()
    stripped = re.sub(r"```.*?```", " ", str(text), flags=re.DOTALL)
    stripped = re.sub(r"``[^`]*``|`[^`\n]*`", " ", stripped)
    missing = []
    for match in CITE_ROLE.finditer(stripped):
        for key in (k.strip() for k in match.group(1).split(",")):
            if key and key not in entries and key not in missing:
                missing.append(key)
    return missing
