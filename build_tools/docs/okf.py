#!/usr/bin/env python
"""Open Knowledge Format front matter for the documentation pages.

`docs/` is written for people, and it is also the corpus the in-application
assistant answers from. Those two audiences want different things from the
same file. A reader wants the prose. An assistant wants to know, *before*
spending a turn reading a page, what kind of page it is, what it is about and
what it belongs with — otherwise "how do I fuse bursts?" means grepping 277
files for the word *burst* and reading whichever five score highest, which is
how a confident answer gets assembled out of a theory page, a changelog and a
developer note.

So every page carries an
`Open Knowledge Format <https://github.com/GoogleCloudPlatform/knowledge-catalog>`_
front-matter block: a YAML header naming the page's ``type``, ``title``,
``description`` and ``tags``. The block is metadata, never prose — Sphinx keeps
it out of the rendered HTML and the help browser strips it, so a reader never
sees it.

This module is the single definition of that block. It is imported by the
injector (:mod:`build_tools.docs.okf_frontmatter`, which writes the header into
hand-authored pages) *and* by the page generators, so a regenerated page does
not lose its header.

Usage::

    from build_tools.docs.okf import derive_meta, render_front_matter, split_front_matter
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

#: The specification version this bundle targets. Declared once, in the front
#: matter of the bundle-root ``docs/index.md``.
OKF_VERSION = "0.2"

#: Filenames the specification reserves; they are not concepts and are exempt
#: from the ``type`` requirement.
RESERVED_NAMES = ("index.md", "log.md")

#: The kind of page each documentation directory holds. The type is what lets
#: the assistant answer "explain X" from a concept and "how do I X" from a
#: guide, rather than treating both as text that mentions X.
DIRECTORY_TYPES: dict[str, str] = {
    "getting_started": "Getting Started",
    "fundamentals": "Fundamentals",
    "concepts": "Concept",
    "guides": "Guide",
    "manual": "Manual Page",
    "reference": "Reference",
    "reference/plugins": "Plugin Reference",
    "reference/file_formats": "File Format",
    "references": "Bibliography",
    "development": "Development Note",
}

#: Who the page is written for. The assistant answers a user's question from
#: user pages; a developer note is the right source only for a question about
#: the code.
DIRECTORY_AUDIENCE: dict[str, str] = {
    "development": "developer",
}

#: Subject keywords worth carrying as tags, mapped from the spellings that
#: appear in page titles and file names. Tags are what make the index
#: navigable by topic instead of by directory: a question about FRET should
#: reach the concept, the guides and the plugin pages at once.
TOPIC_TAGS: dict[str, tuple[str, ...]] = {
    "fret": ("fret",),
    "smfret": ("fret", "smfret", "bursts"),
    "burst": ("bursts",),
    "bursts": ("bursts",),
    "fcs": ("fcs",),
    "correlation": ("correlation",),
    "tcspc": ("tcspc",),
    "decay": ("tcspc", "decay"),
    "lifetime": ("tcspc", "lifetime"),
    "anisotropy": ("anisotropy",),
    "pda": ("pda",),
    "phasor": ("phasor",),
    "flim": ("imaging", "flim"),
    "imaging": ("imaging",),
    "image": ("imaging",),
    "microscopy": ("imaging",),
    "tttr": ("tttr", "photons"),
    "photon": ("photons",),
    "structure": ("structure",),
    "structural": ("structure",),
    "pdb": ("structure",),
    "md": ("structure", "simulation"),
    "simulation": ("simulation",),
    "simulate": ("simulation",),
    "kinetics": ("kinetics",),
    "hmm": ("kinetics", "hmm"),
    "dynamics": ("dynamics",),
    "fitting": ("fitting",),
    "fit": ("fitting",),
    "global": ("fitting", "global-analysis"),
    "uncertainty": ("uncertainty",),
    "error": ("uncertainty",),
    "mcmc": ("uncertainty", "sampling"),
    "sampling": ("sampling",),
    "plugin": ("plugins",),
    "plugins": ("plugins",),
    "gui": ("gui",),
    "cli": ("cli", "headless"),
    "headless": ("headless",),
    "scripting": ("scripting", "python"),
    "python": ("python",),
    "api": ("api",),
    "database": ("database", "mmfdb"),
    "mmfdb": ("database", "mmfdb"),
    "provenance": ("provenance",),
    "calibration": ("calibration",),
    "background": ("corrections",),
    "correction": ("corrections",),
    "install": ("installation",),
    "installation": ("installation",),
    "settings": ("settings",),
    "format": ("file-formats",),
    "formats": ("file-formats",),
    "file": ("file-formats",),
    "deer": ("deer", "epr"),
    "epr": ("epr",),
    "polymer": ("polymer",),
    "diffusion": ("diffusion",),
    "spectra": ("spectra",),
    "spectral": ("spectra",),
}

#: Words that carry no topic and would otherwise become tags.
_STOPWORDS = frozenset(
    """a an and are as at be by for from how in into is it its of on or that the
    their then there these this to use used using what when where which who why
    with your you page guide chisurf""".split()
)

_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_MYST_ANCHOR = re.compile(r"\A\(([A-Za-z0-9_.-]+)\)=\s*$")


# ── reading ───────────────────────────────────────────────────────────────


def split_front_matter(text: str) -> tuple[str, str]:
    """Split a document into its front-matter block and its body.

    Parameters
    ----------
    text : str
        The full file content.

    Returns
    -------
    tuple of str
        ``(front_matter_yaml, body)``. The YAML is ``""`` when the document
        carries no header; the body never includes the delimiters.
    """
    match = _FRONT_MATTER.match(text)
    if not match:
        return "", text
    return match.group(1), text[match.end() :]


def read_front_matter(text: str) -> dict[str, Any]:
    """Return the parsed front matter of a document, or an empty dict.

    Parameters
    ----------
    text : str
        The full file content.

    Returns
    -------
    dict
        The parsed mapping. An unparseable or non-mapping header yields ``{}``.
    """
    raw, _ = split_front_matter(text)
    if not raw.strip():
        return {}
    try:
        import yaml

        loaded = yaml.safe_load(raw)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


# ── writing ───────────────────────────────────────────────────────────────


def _quote(value: str) -> str:
    """Return *value* as a YAML scalar, quoted when it needs to be."""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    needs_quotes = (
        not text
        or text[0] in "&*!|>%@`{[#-?:,"
        or ": " in text
        or text.endswith(":")
        or text != text.strip()
        or text.lower() in {"true", "false", "null", "yes", "no", "on", "off"}
    )
    if needs_quotes:
        return "'" + text.replace("'", "''") + "'"
    return text


def render_front_matter(meta: dict[str, Any]) -> str:
    """Render a metadata mapping as an OKF front-matter block.

    Keys are emitted in the specification's order of importance rather than
    alphabetically, so the block reads as a header and not as a dump.

    Parameters
    ----------
    meta : dict
        Metadata; ``type`` is required by the specification.

    Returns
    -------
    str
        The block, delimiters included, ending in a newline.
    """
    order = (
        "okf_version",
        "type",
        "title",
        "description",
        "resource",
        "tags",
        "audience",
        "anchor",
        "status",
        "generator",
        "generated",
    )
    lines = ["---"]
    for key in order:
        if key not in meta or meta[key] in (None, "", [], {}):
            continue
        value = meta[key]
        if key == "okf_version":
            # The specification writes the version as a string; unquoted,
            # "0.2" is a YAML float and a 0.10 release would read as 0.1.
            lines.append(f'{key}: "{value}"')
        elif isinstance(value, (list, tuple)):
            lines.append(f"{key}: [{', '.join(_quote(item) for item in value)}]")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for sub_key, sub_value in value.items():
                lines.append(f"  {sub_key}: {_quote(sub_value)}")
        else:
            lines.append(f"{key}: {_quote(value)}")
    for key in sorted(set(meta) - set(order)):
        if meta[key] in (None, "", [], {}):
            continue
        lines.append(f"{key}: {_quote(meta[key])}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def apply_front_matter(text: str, meta: dict[str, Any]) -> str:
    """Return *text* with its front matter replaced by *meta*.

    Parameters
    ----------
    text : str
        The full file content, with or without an existing header.
    meta : dict
        The metadata to write.

    Returns
    -------
    str
        The document with exactly one front-matter block at the top.
    """
    _, body = split_front_matter(text)
    return render_front_matter(meta) + "\n" + body.lstrip("\n")


# ── derivation ────────────────────────────────────────────────────────────


def _clean_inline(text: str) -> str:
    """Reduce a line of Markdown to the words it says.

    Links become their label, roles become their target, emphasis and code
    fences go. A description is read by a model as plain text; leaving the
    markup in makes it noisier without saying anything more.
    """
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links
    # A cross-reference with its own words keeps them; a bare `{ref}` carries
    # only a target label, which is noise in a sentence a model will read.
    text = re.sub(r"\{[a-z:]+\}`([^`<]+?)\s*<[^>]*>`", r"\1", text)
    text = re.sub(r"\{[a-z:]+\}`[^`]*`", "", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)  # code spans
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)[*_]([^*_]+)[*_](?!\w)", r"\1", text)
    text = text.replace("\\", "")
    text = re.sub(r"\(\s*[,;]?\s*\)", "", text)  # parentheses emptied by the above
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def plain_text(text: str) -> str:
    """Return a line of Markdown reduced to the words it says.

    Parameters
    ----------
    text : str
        Markdown, possibly with links, MyST roles, code spans and emphasis.

    Returns
    -------
    str
        The same sentence without markup, whitespace collapsed.
    """
    return _clean_inline(text)


def _is_prose(line: str) -> bool:
    """Return whether a line begins ordinary prose rather than structure."""
    stripped = line.strip()
    if not stripped:
        return False
    return not stripped.startswith(
        ("#", ":::", "```", "|", ">", "- ", "* ", "+ ", "<!--", "(", "%", ".. ", "{", "[")
    )


#: Field labels that open a document's administrative preamble rather than its
#: prose. A page whose description reads "Date: 2026-06-13" describes nothing.
_PREAMBLE_LABELS = (
    "date",
    "status",
    "author",
    "authors",
    "owner",
    "version",
    "scope",
    "updated",
    "created",
    "reviewed",
    "audience",
    "summary of changes",
)


def _is_summary(candidate: str) -> bool:
    """Return whether a paragraph can serve as the page's description."""
    if len(candidate) < 25:
        return False
    if re.fullmatch(r"[-=*_\s]+", candidate):
        return False
    # An unfenced ASCII diagram is not prose. It reads as one long paragraph,
    # and it is caught two ways: by how few letters it has, and — for the
    # labelled kind, which is mostly words — by the box-drawing glyphs that
    # hold it together.
    if set(candidate) & set("│─┌┐└┘├┤┬┴┼▼▲◄►╔╗╚╝║═"):
        return False
    letters = sum(character.isalpha() for character in candidate)
    if letters / len(candidate) < 0.55:
        return False
    label = candidate.split(":", 1)[0].strip().lower()
    return label not in _PREAMBLE_LABELS


def extract_anchor(body: str) -> str:
    """Return the page's MyST target label, or ``""`` when it has none."""
    for line in body.splitlines():
        if not line.strip():
            continue
        match = _MYST_ANCHOR.match(line.strip())
        return match.group(1) if match else ""
    return ""


def extract_title(body: str) -> str:
    """Return the page's first heading as plain text."""
    for line in body.splitlines():
        if line.startswith("# "):
            # A heading may carry an explicit anchor, `# Title {#label}`; the
            # label is a target, not part of the title.
            return _clean_inline(re.sub(r"\{\s*#[-\w]+\s*\}\s*$", "", line[2:]))
    return ""


def extract_description(body: str, limit: int = 240) -> str:
    """Return a one-sentence summary taken from the page's opening prose.

    The lead paragraph of a page states what the page is about — that is what
    makes it the lead paragraph. Its first sentence is therefore a better
    description than anything derived from the title, and it is the author's
    own wording rather than a paraphrase.

    Parameters
    ----------
    body : str
        The document body, front matter already removed.
    limit : int
        Soft maximum length; a longer sentence is cut at a clause boundary.

    Returns
    -------
    str
        A single sentence without trailing punctuation stripped, or ``""``.
    """
    lines = body.splitlines()
    start = 0
    for number, line in enumerate(lines):
        if line.startswith("# "):
            start = number + 1
            break

    # Finding the lead paragraph is mostly a matter of what to ignore. Pages
    # open with a "see also the theory" admonition (whose contents are not the
    # lead — taking them produced descriptions beginning ":class: seealso"), a
    # code fence, a horizontal rule, or a run of "Date:"/"Status:" metadata
    # lines. Each of those is skipped and the search continues, rather than
    # stopping on the first thing that happens to look like prose.
    text = ""
    paragraph: list[str] = []
    fence = ""
    for line in [*lines[start:], ""]:
        stripped = line.strip()
        if fence:
            if stripped.startswith(fence):
                fence = ""
            continue
        if stripped.startswith(":::") or stripped.startswith("```"):
            marker = ":::" if stripped.startswith(":::") else "```"
            # A bare marker closes rather than opens.
            if stripped != marker:
                fence = marker
            continue
        if not stripped:
            if paragraph:
                candidate = _clean_inline(" ".join(paragraph))
                paragraph = []
                if _is_summary(candidate):
                    text = candidate
                    break
            continue
        if not paragraph and not _is_prose(line):
            continue
        paragraph.append(stripped)

    if not text:
        return ""

    # Guides open with "What you get: ..." — that *is* the description.
    text = re.sub(r"^What you get:\s*", "", text)
    text = text[:1].upper() + text[1:] if text else text

    # First sentence — and the hard part is the false ends. A single capital
    # before the stop is an initial ("J."), "e.g." is not a sentence, and a
    # stop inside a parenthesis ("(Torella et al., Biophys. J. 100 …)") ends
    # the citation, not the sentence; that one is caught by refusing a
    # candidate whose prefix leaves a bracket open.
    for match in re.finditer(r"(?<![A-Z])(?<!\be\.g)(?<!\bi\.e)(?<!\bcf)[.?!]\s+(?=[A-Z(])", text):
        candidate = text[: match.start() + 1]
        if len(candidate) < 40:
            continue
        if candidate.count("(") != candidate.count(")"):
            continue
        if re.match(r"\s*[A-Z]\.", text[match.end() - 1 :]):
            continue
        text = candidate
        break
    if len(text) > limit:
        cut = text.rfind(" — ", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(", ", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        text = text[:cut].rstrip(" ,—;:") + "…"
    return text


def derive_tags(relative: pathlib.PurePosixPath, title: str, body: str) -> list[str]:
    """Return topic tags for a page.

    Parameters
    ----------
    relative : pathlib.PurePosixPath
        The page path relative to ``docs/``.
    title : str
        The page title.
    body : str
        The document body.

    Returns
    -------
    list of str
        Tags, most structural first: the section the page lives in, then the
        subjects recognised in its name and title.
    """
    tags: list[str] = []
    section = relative.parts[0] if len(relative.parts) > 1 else ""
    if section:
        tags.append(section.replace("_", "-"))
    if len(relative.parts) > 2:
        tags.append(relative.parts[1].replace("_", "-"))

    words = re.split(r"[^A-Za-z0-9]+", f"{relative.stem} {title}".lower())
    for word in words:
        if not word or word.isdigit() or word in _STOPWORDS:
            continue
        for tag in TOPIC_TAGS.get(word, ()):
            if tag not in tags:
                tags.append(tag)

    if not tags or len(tags) < 3:
        # Fall back to the page's own vocabulary so a page still carries
        # something searchable: the distinctive words of its file name.
        for word in re.split(r"[^A-Za-z0-9]+", relative.stem.lower()):
            if len(word) > 3 and not word.isdigit() and word not in _STOPWORDS:
                if word not in tags:
                    tags.append(word)
    return tags[:8]


def page_type(relative: pathlib.PurePosixPath) -> str:
    """Return the OKF ``type`` for a page, from where it lives."""
    if relative.name in RESERVED_NAMES:
        return "Index"
    parent = relative.parent.as_posix()
    if parent in DIRECTORY_TYPES:
        return DIRECTORY_TYPES[parent]
    root = relative.parts[0] if len(relative.parts) > 1 else ""
    return DIRECTORY_TYPES.get(root, "Documentation")


def derive_meta(
    relative: pathlib.PurePosixPath,
    text: str,
    *,
    keep: dict[str, Any] | None = None,
    preserve: bool = True,
) -> dict[str, Any]:
    """Derive the OKF front matter for a documentation page.

    Parameters
    ----------
    relative : pathlib.PurePosixPath
        The page path relative to ``docs/``.
    text : str
        The full file content, header included if it already has one.
    keep : dict, optional
        Fields to preserve verbatim, overriding what is derived. Hand-tuned
        descriptions survive a re-run this way.
    preserve : bool
        Keep the values already in the file's header where they exist. Turn
        this off to overwrite them with freshly derived ones.

    Returns
    -------
    dict
        The metadata mapping, ready for :func:`render_front_matter`.
    """
    existing = read_front_matter(text)
    _, body = split_front_matter(text)

    title = extract_title(body) or relative.stem.replace("_", " ").replace("-", " ").capitalize()
    meta: dict[str, Any] = {
        "type": page_type(relative),
        "title": title,
        "description": extract_description(body),
        "tags": derive_tags(relative, title, body),
    }
    anchor = extract_anchor(body)
    if anchor:
        meta["anchor"] = anchor
    audience = DIRECTORY_AUDIENCE.get(relative.parts[0] if len(relative.parts) > 1 else "")
    if audience:
        meta["audience"] = audience

    # Anything an author added by hand is theirs, not the tool's, and a
    # regeneration that quietly reverted it would make the header untrustworthy.
    for key, value in existing.items():
        if key not in meta or preserve:
            meta[key] = value
    for key, value in (keep or {}).items():
        meta[key] = value
    return meta
