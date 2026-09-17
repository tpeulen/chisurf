"""Agent tools for answering a *user's* question out of the documentation.

The codebase tools next door answer "what is the API?" for a model that is
writing code. These answer "how do I do this, and what does it mean?" for a
scientist who is using the program — a different corpus, a different ranking,
and one rule the other does not have: **an answer must come from a page, and
must say which page**.

Three tools, in the order they are meant to be used:

``browse_documentation``
    the map. Every page's kind, title and one-line description, filterable by
    kind and by tag. This is what the Open-Knowledge-Format header buys: the
    model *chooses* a page instead of guessing at one, and it costs one call.
``search_documentation``
    the ranked lookup, when the map is too coarse or the wording is unusual.
``read_documentation``
    the page, or one section of it. Reference pages run to hundreds of lines
    and the question is usually about one heading.

All read-only, all on the user's own documentation.
"""

from __future__ import annotations

import logging
from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_READ, ToolError, ToolRegistry

logger = logging.getLogger(__name__)

registry = ToolRegistry()

#: How many entries a browse call will list before it insists on a filter. The
#: whole corpus is ~570 pages; a listing that long crowds out the question.
BROWSE_LIMIT = 60

#: What ``scope`` selects, spelled out for the model. The distinction matters:
#: a user asking how to fuse bursts must not be answered from a migration note
#: about the burst-fusion module, and an agent writing a plugin must not be
#: told to read the end-user guide.
SCOPE_HELP = (
    "'user' (default) searches the documentation of the program — guides, "
    "concepts, fundamentals, plugin reference. 'code' searches the knowledge "
    "bundle describing how ChiSurf is built — architecture, subsystems, "
    "developer notes — which is what you want when writing code against it. "
    "'all' searches both."
)


def _scope(scope: str) -> dict[str, Any]:
    """Translate a scope name into index filters."""
    name = str(scope or "user").strip().lower()
    if name == "code":
        return {"bundle": "okf"}
    if name == "all":
        return {}
    if name != "user":
        raise ToolError(f"scope must be 'user', 'code' or 'all', not {scope!r}")
    return {"user_only": True}


def _near(available, wanted: str, limit: int = 3) -> list[str]:
    """Return the available names closest to *wanted*."""
    from chisurf.core.agent.doc_index import _edit_distance

    target = str(wanted).strip().lower()
    if not target:
        return []
    scored = [(_edit_distance(target, str(name).lower(), 3), str(name)) for name in available]
    return [name for distance, name in sorted(scored) if distance <= 3][:limit]


def _index():
    """Return the documentation index, built or cached."""
    from chisurf.core.agent.doc_index import DocIndex

    return DocIndex.load()


@registry.add(
    name="browse_documentation",
    description=(
        "Show the map of ChiSurf's documentation: every page's kind, title "
        "and one-line description.\n"
        "Call this FIRST for a question about how to use ChiSurf or what a "
        "method means — it is one call and it tells you which page answers "
        "the question, instead of searching for words that may not be the "
        "ones the page uses.\n"
        "Filter by 'kind' (Concept explains the theory, Guide gives the "
        "step-by-step procedure, Plugin Reference lists a tool's controls, "
        "Fundamentals covers the underlying photophysics, File Format "
        "describes what can be loaded) and by 'tag' (a subject such as fret, "
        "fcs, tcspc, bursts, imaging). Call with no arguments to see which "
        "kinds and tags exist."
    ),
    parameters={
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "description": "Page kind, e.g. 'Guide', 'Concept', 'Plugin Reference'.",
            },
            "tag": {
                "type": "string",
                "description": "Subject tag, e.g. 'fret', 'fcs', 'bursts'.",
            },
            "scope": {
                "type": "string",
                "enum": ["user", "code", "all"],
                "description": SCOPE_HELP,
            },
        },
    },
    safety=SAFETY_READ,
)
def browse_documentation(
    context: AgentContext,
    kind: str = "",
    tag: str = "",
    scope: str = "user",
) -> dict[str, Any]:
    """List the documentation by kind and tag."""
    index = _index()
    entries = index.filter(kind=kind, tag=tag, **_scope(scope))

    if not entries:
        if kind or tag:
            # A subject the reader names is a *search*, not a tag, and this is
            # the error a model hits when it tries the user's words as one.
            # Saying "here are 26 kinds and 20 tags" sent it round again; the
            # near matches and one instruction do not.
            near = _near(index.tags(), tag) if tag else _near(index.kinds(), kind)
            hint = f" Did you mean {', '.join(near)}?" if near else ""
            raise ToolError(
                f"no pages with kind={kind!r} tag={tag!r}.{hint} "
                f"A tag is a broad subject, not a search term — for a word from "
                f"the user's question use search_documentation instead. "
                f"Kinds: {', '.join(index.kinds())}. "
                f"Commonest tags: {', '.join(list(index.tags())[:20])}."
            )
        raise ToolError("the documentation index is empty")

    # Unfiltered, the corpus is too long to be a useful listing; report the
    # shape of it and let the model narrow down.
    if not kind and not tag and len(entries) > BROWSE_LIMIT:
        return {
            "ok": True,
            "n_pages": len(entries),
            "note": (
                "too many pages to list. Narrow with 'kind' or 'tag' — the "
                "counts below say how many pages each would give you."
            ),
            "kinds": {
                name: count
                for name, count in index.kinds().items()
                if any(entry.type == name for entry in entries)
            },
            "tags": dict(list(index.tags().items())[:40]),
        }

    return {
        "ok": True,
        "kind": kind,
        "tag": tag,
        "n_pages": len(entries),
        "pages": [entry.summary() for entry in entries[:BROWSE_LIMIT]],
        "truncated": len(entries) > BROWSE_LIMIT,
    }


@registry.add(
    name="search_documentation",
    description=(
        "Search ChiSurf's user documentation — the guides, the concept pages, "
        "the fundamentals, the file formats and every plugin's reference "
        "page.\n"
        "Use this when browse_documentation did not obviously contain the "
        "answer, or when the user used a word you want to look up literally. "
        "Each hit carries the page's kind and description, so you can tell an "
        "explanation from a procedure before reading either."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for, e.g. 'gamma correction' or 'burst search'.",
            },
            "kind": {"type": "string", "description": "Restrict to one page kind."},
            "tag": {"type": "string", "description": "Restrict to one subject tag."},
            "limit": {"type": "integer", "description": "Maximum pages. Default 6."},
            "scope": {
                "type": "string",
                "enum": ["user", "code", "all"],
                "description": SCOPE_HELP,
            },
        },
        "required": ["query"],
    },
    safety=SAFETY_READ,
)
def search_documentation(
    context: AgentContext,
    query: str,
    kind: str = "",
    tag: str = "",
    limit: int = 6,
    scope: str = "user",
) -> dict[str, Any]:
    """Search the documentation, header-first."""
    index = _index()
    hits = index.search(query, limit=limit, kind=kind, tag=tag, **_scope(scope))
    if not hits:
        near = index.near_spellings(query)
        if near:
            spellings = "; ".join(
                f"{word} -> {' / '.join(options)}" for word, options in near.items()
            )
            raise ToolError(
                f"nothing matches {query!r}, but the documentation uses a near "
                f"spelling: {spellings}. Search again with it. Do not tell the "
                f"user their term does not exist until you have."
            )
        raise ToolError(
            f"nothing in the documentation matches {query!r}. Try "
            f"browse_documentation to see what kinds and subjects exist, or "
            f"different words — the pages may use another spelling."
        )
    result = {"ok": True, "query": query, "n_results": len(hits), "pages": hits}
    corrected = hits[0].get("corrected_from") if hits else None
    if corrected:
        # The hits are for a *different* spelling, and an answer that does not
        # say so reads as though the user's own word was found.
        result["corrected_from"] = corrected
        result["note"] = (
            "no page uses the word as written; these are for the spelling the "
            "documentation uses. Say so in your answer."
        )
    return result


@registry.add(
    name="read_documentation",
    description=(
        "Read a documentation page, or one section of it, as prose.\n"
        "Pass the 'document' path that browse_documentation or "
        "search_documentation reported. Give 'section' to read a single "
        "heading — reference pages are long and the question is usually about "
        "one part. Call with 'outline_only' to see the headings first.\n"
        "The result also lists the related pages, which is how you find the "
        "guide that goes with a concept."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document": {
                "type": "string",
                "description": "Page path, e.g. 'docs/guides/58_burst_fusion.md'.",
            },
            "section": {
                "type": "string",
                "description": "A heading on the page; matched as a substring.",
            },
            "outline_only": {
                "type": "boolean",
                "description": "Return only the headings, not the prose.",
            },
            "max_lines": {"type": "integer", "description": "Maximum lines. Default 200."},
        },
        "required": ["document"],
    },
    safety=SAFETY_READ,
)
def read_documentation(
    context: AgentContext,
    document: str,
    section: str = "",
    outline_only: bool = False,
    max_lines: int = 200,
) -> dict[str, Any]:
    """Return a page's prose, its outline, or one of its sections."""
    from chisurf.core.agent import doc_index

    index = _index()
    entry = index.get(document)
    if entry is None:
        raise ToolError(
            f"no documentation page called {document!r}. Use "
            f"search_documentation or browse_documentation to find its path."
        )
    body = doc_index.read_body(entry.document)
    if body is None:
        raise ToolError(f"{entry.document} could not be read")

    headings = doc_index.outline(body)
    payload: dict[str, Any] = {
        "ok": True,
        **entry.summary(),
        "outline": headings,
        "related": [other.summary() for other in index.related(entry)],
    }
    if outline_only:
        return payload

    if section:
        text = doc_index.read_section(body, section)
        if not text:
            raise ToolError(
                f"{entry.document} has no section matching {section!r}. "
                f"Its headings are: {', '.join(headings[:20])}"
            )
        payload["section"] = section
    else:
        text = body

    lines = text.splitlines()
    payload["truncated"] = len(lines) > int(max_lines)
    payload["content"] = "\n".join(lines[: int(max_lines)])[: context.max_result_chars]
    return payload
