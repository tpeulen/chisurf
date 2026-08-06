"""The assistant's map of the documentation, built from its OKF headers.

Answering "how do I fuse bursts?" from a corpus of ~450 markdown files is a
retrieval problem, and full-text search is a bad way to solve it. The word
*burst* appears in a theory page, four guides, thirty plugin reference pages
and a developer note about a migration; ranking those by term frequency puts
the longest file first and the page that answers the question somewhere below
it. The model then reads the wrong page and answers confidently from it.

Every page carries an
`Open Knowledge Format <https://github.com/GoogleCloudPlatform/knowledge-catalog>`_
header — its ``type``, ``title``, ``description`` and ``tags`` — and that
header is what turns the corpus into a map:

``type``
    *What kind of answer is this?* A ``Concept`` explains, a ``Guide``
    instructs, a ``Plugin Reference`` enumerates controls, a
    ``Development Note`` is about the code and is the wrong source for a
    user's question. A question can be routed to a kind of page before any
    page is read.
``description``
    One sentence per page, written by its author. Four hundred of them fit in
    a single tool result, so the model can *choose* rather than guess.
``tags``
    The cross-cutting axis directories cannot express: the FRET concept, the
    FRET guides and the FRET plugins share a tag and nothing else.

Three bundles are indexed and they answer different questions:

============================  ======================================
``docs/``                     how the *program* is used and what the
                              methods mean — the user's documentation
``okf/``                      how ChiSurf is *built* — for a question
                              about the code
the assistant's own bundle    what fluorescence analysis and ChiSurf's
                              objects *mean*, written for this purpose
============================  ======================================

The index is cached beside the API index and rebuilt when the documentation
changes.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Bundles that are indexed, in the order a tie is broken.
BUNDLES: tuple[str, ...] = ("assistant", "docs", "okf")

#: Page kinds that answer a *user's* question about using the program. A
#: question that is not about the code should not be answered from a
#: development note, however well it matches.
USER_TYPES: frozenset[str] = frozenset(
    {
        "Getting Started",
        "Fundamentals",
        "Concept",
        "Guide",
        "Manual Page",
        "Reference",
        "File Format",
        "Plugin Reference",
        "Bibliography",
        "Index",
        "Documentation",
    }
)

#: Documents that record *what changed* rather than *how things work*. They
#: are enormous and mention everything, so by raw hit count they would win
#: every search while answering no question.
_CHANGELOG_NAMES = frozenset({"log.md", "changelog.md", "history.md", "assessment.md"})

#: Words a natural-language question is made of. They are longer than the
#: three-character floor and appear on every page, so left in the query they
#: rank by *how chatty a page is* — "what does chi2r mean" returned the two
#: longest guides before the page about chi-square.
_QUERY_STOPWORDS = frozenset(
    """about after all and any are but can does doing done for from get gets
    give gives had has have how into its like made make means mean much need
    needs not now off out over say see set should show shows some such than
    that the their them then there these they this those tell use used uses
    using want was way what when where which who why will with within without
    would you your chisurf""".split()
)

#: Where the interface's spelling of a thing is not the documentation's.
#: A user asks about "chi2r" because that is the label on the fit; the pages
#: that explain it write "reduced chi-square", so the two never met.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "chi2r": ("chi-square", "chi2", "goodness"),
    "chi2": ("chi-square", "reduced"),
    "chisqr": ("chi-square",),
    "irf": ("instrument response",),
    "tcspc": ("time-correlated", "lifetime", "decay"),
    "fcs": ("correlation",),
    "smfret": ("single-molecule", "fret", "burst"),
    "alex": ("stoichiometry", "alternating"),
    "pie": ("alternating", "interleaved"),
    "kappa2": ("orientation", "kappa"),
    "r0": ("förster", "forster", "radius"),
    "tttr": ("photon", "time-tagged"),
    "dw": ("durbin", "watson"),
    "mcmc": ("sampling", "posterior"),
    "roi": ("region",),
    "psf": ("point-spread",),
    "flim": ("lifetime imaging",),
}

_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*(?:\{\s*#[-\w]+\s*\})?$", re.M)
_MYST_ANCHOR = re.compile(r"^\([A-Za-z0-9_.-]+\)=\s*$", re.M)


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split a document into its parsed OKF header and its prose.

    Parameters
    ----------
    text : str
        The full file content.

    Returns
    -------
    tuple
        ``(metadata, body)``. The metadata is ``{}`` when the document has no
        header or the header does not parse; the body never contains it.
    """
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}, text
    body = text[match.end() :]
    try:
        import yaml

        loaded = yaml.safe_load(match.group(1))
    except Exception:
        return {}, body
    return (loaded if isinstance(loaded, dict) else {}), body


@dataclass(frozen=True)
class DocEntry:
    """One documentation page, as the assistant sees it before reading it."""

    document: str
    bundle: str
    type: str
    title: str
    description: str
    tags: tuple[str, ...] = ()
    anchor: str = ""
    audience: str = ""
    headings: tuple[str, ...] = ()
    n_lines: int = 0
    #: The page is a listing — mostly table rows pointing elsewhere, like the
    #: figure/table registers or the plugin catalogue. It mentions everything
    #: and explains nothing, so it wins a term-frequency search while
    #: answering no question.
    listing: bool = False

    def one_line(self) -> str:
        """Return the entry as a single line of a browsable listing."""
        tags = f" [{', '.join(self.tags)}]" if self.tags else ""
        return f"{self.document} — {self.title}: {self.description}{tags}"

    def summary(self) -> dict[str, Any]:
        """Return the compact form used in a tool result."""
        return {
            "document": self.document,
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
        }


@dataclass
class DocIndex:
    """A searchable, browsable index of every documented page."""

    entries: list[DocEntry] = field(default_factory=list)

    # ── construction ──────────────────────────────────────────────────

    @classmethod
    def build(cls) -> DocIndex:
        """Index every page of every bundle from scratch."""
        entries: list[DocEntry] = []
        for bundle, root, base in _bundle_roots():
            for path in sorted(root.rglob("*.md")):
                if _skipped(path):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                entries.append(_entry(path, text, bundle, base))
        return cls(entries)

    @classmethod
    def load(cls, refresh: bool = False) -> DocIndex:
        """Return the index, rebuilding only when the documentation changed.

        Parameters
        ----------
        refresh : bool
            Rebuild even when the cache looks current.

        Returns
        -------
        DocIndex
        """
        fingerprint = _fingerprint()
        cache = _cache_path()
        if not refresh and cache is not None and cache.is_file():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                if payload.get("fingerprint") == fingerprint:
                    return cls(
                        [
                            DocEntry(
                                **{
                                    **entry,
                                    "tags": tuple(entry.get("tags", ())),
                                    "headings": tuple(entry.get("headings", ())),
                                }
                            )
                            for entry in payload.get("entries", [])
                        ]
                    )
            except Exception:
                logger.debug("documentation index cache unreadable; rebuilding", exc_info=True)

        index = cls.build()
        if cache is not None:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(
                    json.dumps(
                        {
                            "fingerprint": fingerprint,
                            "entries": [asdict(entry) for entry in index.entries],
                        }
                    ),
                    encoding="utf-8",
                )
            except Exception:
                logger.debug("could not cache the documentation index", exc_info=True)
        return index

    # ── navigation ────────────────────────────────────────────────────

    def kinds(self) -> dict[str, int]:
        """Return every page ``type`` present, with how many pages carry it."""
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.type] = counts.get(entry.type, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def tags(self) -> dict[str, int]:
        """Return every tag in use, with how many pages carry it."""
        counts: dict[str, int] = {}
        for entry in self.entries:
            for tag in entry.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def filter(
        self,
        *,
        kind: str = "",
        tag: str = "",
        bundle: str = "",
        user_only: bool = False,
    ) -> list[DocEntry]:
        """Return the pages matching every constraint given.

        Parameters
        ----------
        kind : str
            An OKF ``type``, matched case-insensitively.
        tag : str
            A tag the page must carry.
        bundle : str
            ``"docs"``, ``"okf"`` or ``"assistant"``.
        user_only : bool
            Drop pages written for someone changing the code.

        Returns
        -------
        list of DocEntry
        """
        wanted_kind = kind.strip().lower()
        wanted_tag = tag.strip().lower()
        wanted_bundle = bundle.strip().lower()
        selected = []
        for entry in self.entries:
            if wanted_kind and entry.type.lower() != wanted_kind:
                continue
            if wanted_tag and wanted_tag not in entry.tags:
                continue
            if wanted_bundle and entry.bundle != wanted_bundle:
                continue
            if user_only and not _is_user_page(entry):
                continue
            selected.append(entry)
        return sorted(selected, key=lambda entry: (entry.type, entry.title))

    # ── search ────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        limit: int = 6,
        *,
        kind: str = "",
        tag: str = "",
        bundle: str = "",
        user_only: bool = False,
        context_lines: int = 8,
    ) -> list[dict[str, Any]]:
        """Return the pages most likely to answer *query*, best first.

        The header is weighted far above the body, which is the whole point of
        having one: a page whose *description* is about the subject beats a
        page that happens to say the word forty times.

        Parameters
        ----------
        query : str
            Words to look for.
        limit : int
            Maximum number of pages to report.
        kind, tag, bundle : str
            Restrict the search the way :meth:`filter` does.
        user_only : bool
            Exclude developer pages.
        context_lines : int
            Lines of prose to quote around the best match.

        Returns
        -------
        list of dict
            ``{"document", "type", "title", "description", "tags", "score",
            "excerpt"}`` per hit.
        """
        words = [term for term in re.split(r"[^\w]+", str(query).lower()) if len(term) > 2]
        terms = [term for term in words if term not in _QUERY_STOPWORDS]
        # A question made entirely of common words is still a question; fall
        # back to them rather than returning nothing.
        terms = terms or words
        if not terms:
            return []
        # An expansion is worth less than the word the user typed: it widens
        # the net without letting a synonym outrank a direct hit.
        expansions = [
            expansion for term in terms for expansion in _SYNONYMS.get(term, ())
            if expansion not in terms
        ]

        candidates = self.filter(kind=kind, tag=tag, bundle=bundle, user_only=user_only)
        hits: list[tuple[float, dict[str, Any]]] = []
        for entry in candidates:
            body = read_body(entry.document)
            if body is None:
                continue
            lowered = body.lower()
            title = entry.title.lower()
            description = entry.description.lower()
            headings = " ".join(entry.headings).lower()

            score = 0.0
            for term in terms:
                if term in title:
                    score += 8.0
                if term in description:
                    score += 5.0
                if term in entry.tags:
                    score += 4.0
                if term in headings:
                    score += 2.0
                occurrences = lowered.count(term)
                if occurrences:
                    # Normalise by length: a long page mentioning the word
                    # often is not more relevant than a short one about it.
                    score += occurrences / max(1.0, (len(body) / 4000.0) ** 0.5)
            for expansion in expansions:
                if expansion in title or expansion in description:
                    score += 2.0
                elif expansion in lowered:
                    score += 0.5
            if not score:
                continue
            # Every word present beats a single word repeated.
            if all(
                term in lowered or term in title or term in description or term in entry.tags
                for term in terms
            ):
                score += 6.0
            score *= _BUNDLE_WEIGHT.get(entry.bundle, 1.0)
            if entry.listing:
                score *= 0.3

            hits.append((score, {**entry.summary(), "score": round(score, 2),
                                 "excerpt": _excerpt(body, terms, context_lines)}))

        hits.sort(key=lambda item: -item[0])
        return [payload for _, payload in hits[: max(1, int(limit))]]

    def get(self, document: str) -> DocEntry | None:
        """Return the entry for a page path, tolerating a bare file name."""
        wanted = str(document).strip().lstrip("/")
        for entry in self.entries:
            if entry.document == wanted:
                return entry
        stem = pathlib.PurePosixPath(wanted).name
        for entry in self.entries:
            if pathlib.PurePosixPath(entry.document).name == stem:
                return entry
        for entry in self.entries:
            if entry.anchor and entry.anchor == wanted:
                return entry
        return None

    def related(self, entry: DocEntry, limit: int = 5) -> list[DocEntry]:
        """Return the pages sharing the most tags with *entry*.

        Parameters
        ----------
        entry : DocEntry
            The page to find neighbours of.
        limit : int
            Maximum number of neighbours.

        Returns
        -------
        list of DocEntry
        """
        own = set(entry.tags)
        if not own:
            return []
        scored = [
            (len(own & set(other.tags)), other)
            for other in self.entries
            if other.document != entry.document
        ]
        scored = [(shared, other) for shared, other in scored if shared]
        scored.sort(key=lambda item: (-item[0], item[1].title))
        return [other for _, other in scored[: max(1, int(limit))]]


#: The assistant's own bundle is written for exactly this purpose and is
#: deliberately concise; ``okf/`` describes the code and is rarely what a user
#: asked about.
_BUNDLE_WEIGHT = {"assistant": 1.5, "docs": 1.2, "okf": 1.0}


def _bundle_roots() -> list[tuple[str, pathlib.Path, pathlib.Path]]:
    """Return ``(bundle, root, base)`` for every bundle that is present.

    *base* is what a document path is reported relative to, so the identifier
    a tool result carries can be passed straight back to :func:`read_body`.
    """
    from chisurf.core.agent.knowledge import knowledge_base_root, repository_root

    repository = repository_root()
    roots: list[tuple[str, pathlib.Path, pathlib.Path]] = []
    bundle = knowledge_base_root()
    if bundle.is_dir():
        roots.append(("assistant", bundle, bundle.parent))
    for name in ("docs", "okf"):
        directory = repository / name
        if directory.is_dir():
            roots.append((name, directory, repository))
    return roots


def _skipped(path: pathlib.Path) -> bool:
    """Return whether a markdown file is not a documentation page."""
    if path.name.lower() in _CHANGELOG_NAMES:
        return True
    return bool({"_build", "_ext", "_old_manual", "__pycache__"}.intersection(path.parts))


def _entry(path: pathlib.Path, text: str, bundle: str, base: pathlib.Path) -> DocEntry:
    """Build the index entry for one page."""
    meta, body = split_front_matter(text)
    try:
        document = path.relative_to(base).as_posix()
    except ValueError:
        document = path.name
    headings = tuple(match.group(2).strip() for match in _HEADING.finditer(body))
    title = str(meta.get("title") or (headings[0] if headings else path.stem))
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return DocEntry(
        document=document,
        bundle=bundle,
        type=str(meta.get("type") or "Documentation"),
        title=title,
        description=str(meta.get("description") or ""),
        tags=tuple(str(tag).strip().lower() for tag in tags if str(tag).strip()),
        anchor=str(meta.get("anchor") or ""),
        audience=str(meta.get("audience") or ""),
        headings=headings[:40],
        n_lines=body.count("\n") + 1,
        listing=_is_listing(body),
    )


def _is_listing(body: str) -> bool:
    """Return whether a page is mostly a table of pointers to other pages.

    The figure, table and code registers and the plugin catalogue are indexes.
    They name every subject in the documentation, so on raw term frequency
    they outrank the page that actually explains the subject.
    """
    lines = [line for line in body.splitlines() if line.strip()]
    if len(lines) < 20:
        return False
    rows = sum(1 for line in lines if line.lstrip().startswith("|"))
    return rows / len(lines) > 0.5


def _is_user_page(entry: DocEntry) -> bool:
    """Return whether a page answers a question about *using* ChiSurf."""
    if entry.audience == "developer":
        return False
    if entry.bundle == "okf":
        return False
    return entry.type in USER_TYPES


def _excerpt(body: str, terms: list[str], context_lines: int) -> str:
    """Return the passage of *body* densest in *terms*."""
    lines = body.splitlines()
    best_line, best_hits = 0, 0
    for number, line in enumerate(lines):
        lowered = line.lower()
        hits = sum(term in lowered for term in terms)
        if hits > best_hits:
            best_line, best_hits = number, hits
    start = max(0, best_line - context_lines // 2)
    return "\n".join(lines[start : start + context_lines]).strip()


def resolve(document: str) -> pathlib.Path | None:
    """Return the file a document identifier names, or ``None``.

    Parameters
    ----------
    document : str
        A path as an index entry reports it, or a bare file name.

    Returns
    -------
    pathlib.Path or None
    """
    wanted = str(document).strip().lstrip("/")
    if not wanted:
        return None
    for _bundle, root, base in _bundle_roots():
        candidate = (base / wanted).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    name = pathlib.PurePosixPath(wanted).name
    for _bundle, root, _base in _bundle_roots():
        matches = sorted(root.rglob(name))
        if matches:
            return matches[0]
    return None


def read_body(document: str) -> str | None:
    """Return a page's prose, with its OKF header removed.

    Parameters
    ----------
    document : str
        A path as an index entry reports it.

    Returns
    -------
    str or None
        The prose, or ``None`` when the page cannot be read.
    """
    path = resolve(document)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    _meta, body = split_front_matter(text)
    return body


def read_section(body: str, section: str) -> str:
    """Return one section of a page, heading included.

    A reference page runs to hundreds of lines and a question usually concerns
    one of its headings; returning the whole page spends the context window on
    the parts that were not asked about.

    Parameters
    ----------
    body : str
        The page's prose.
    section : str
        A heading, matched case-insensitively as a substring.

    Returns
    -------
    str
        The section, or ``""`` when no heading matches.
    """
    wanted = str(section).strip().lower()
    if not wanted:
        return ""
    lines = body.splitlines()
    start = -1
    level = 6
    for number, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and wanted in match.group(2).strip().lower():
            start, level = number, len(match.group(1))
            break
    if start < 0:
        return ""
    end = len(lines)
    for number in range(start + 1, len(lines)):
        match = _HEADING.match(lines[number])
        if match and len(match.group(1)) <= level:
            end = number
            break
    return "\n".join(lines[start:end]).strip()


def outline(body: str) -> list[str]:
    """Return a page's headings, indented by level."""
    return [
        "  " * (len(match.group(1)) - 1) + match.group(2).strip()
        for match in _HEADING.finditer(body)
    ]


def _cache_path() -> pathlib.Path | None:
    """Return where the index is cached, or ``None`` when there is nowhere."""
    try:
        from chisurf.core.settings import get_path

        return pathlib.Path(get_path("settings")) / "agent_doc_index.json"
    except Exception:
        return None


def _fingerprint(roots: Iterable[tuple[str, pathlib.Path, pathlib.Path]] | None = None) -> str:
    """Return a cheap fingerprint of the documentation's state."""
    newest = 0.0
    count = 0
    for _bundle, root, _base in roots or _bundle_roots():
        for path in root.rglob("*.md"):
            if _skipped(path):
                continue
            try:
                newest = max(newest, path.stat().st_mtime)
            except OSError:
                continue
            count += 1
    return f"{count}:{newest:.0f}"
