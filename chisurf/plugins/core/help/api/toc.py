"""The table of contents the help browser navigates by.

Before this module the browser listed whatever ``rglob`` found: four buckets,
each a flat alphabetical run of file names. The user manual arrived as
seventy-nine sibling pages sorted by filename, so *Calculations*, *Calculations*
and *Calculation of confocal volume* sat next to each other while the chapter
each belonged to was nowhere on screen; the "Core" bucket offered a build
script's README next to the changelog. A reader who does not already know the
answer cannot get anywhere from that.

The documentation already carries its own structure — the ``toctree`` blocks the
shipped HTML manual is built from say what belongs where and in which order. So
that is what is read here, and the in-app tree and the website cannot drift
apart: fixing the order in one fixes it in both.

Three things this file is careful about:

* **Ordering is the author's, not the filesystem's.** Entries appear in toctree
  order. Alphabetical is only used for material that has no index at all.
* **Groups come from the page, not from a hard-coded list.** A ``.. rubric::``
  (reStructuredText) or a ``##`` heading (MyST) above a toctree names the group
  under it, which is how *Fundamentals*, *Correlation methods* and the rest
  arrive without being repeated here.
* **Developer documentation is not user documentation.** Architecture notes,
  migration plans and module READMEs are excluded unless asked for, because a
  scientist looking for the anisotropy workflow should not have to walk past
  them.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

__all__ = [
    "Node",
    "build_toc",
    "docs_root",
    "iter_pages",
    "read_index",
    "repository_root",
]

#: Suffixes a toctree entry may resolve to.
_SUFFIXES = (".md", ".rst")

#: ``Title <target>`` in a toctree entry.
_LABELLED = re.compile(r"^(?P<title>.+?)\s*<(?P<target>[^>]+)>$")

#: A toctree directive, in either dialect.
_TOCTREE_RST = re.compile(r"^\.\.\s+toctree::\s*$")
_TOCTREE_MYST = re.compile(r"^(?:`{3,}|:{3,})\{toctree\}\s*$")

#: A group heading above a toctree.
_RUBRIC = re.compile(r"^\.\.\s+rubric::\s*(?P<title>.+?)\s*$")
_MYST_HEADING = re.compile(r"^(?P<level>#{2,3})\s+(?P<title>.+?)\s*$")
_RST_SECTION_ADORNMENT = re.compile(r"^([!-/:-@\[-`{-~])\1{1,}\s*$")


@dataclass
class Node:
    """One entry in the help table of contents.

    Attributes
    ----------
    title : str
        What the reader sees.
    path : pathlib.Path or None
        The document; ``None`` for a pure grouping node.
    children : list of Node
        Nested entries, in reading order.
    kind : str
        ``"section"`` (a top-level part), ``"group"`` (a heading inside one) or
        ``"page"``.
    summary : str
        One line describing the node, shown on the start page and as a tooltip.
    """

    title: str
    path: Optional[pathlib.Path] = None
    children: list["Node"] = field(default_factory=list)
    kind: str = "page"
    summary: str = ""

    def add(self, node: "Node") -> "Node":
        """Append *node* as a child and return it."""
        self.children.append(node)
        return node

    def walk(self) -> Iterable["Node"]:
        """Yield this node and every descendant, depth first."""
        yield self
        for child in self.children:
            yield from child.walk()


def repository_root() -> pathlib.Path:
    """Return the directory holding ``docs/`` — the repository or install root."""
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docs").is_dir():
            return parent
    return here.parents[-1]


def docs_root() -> pathlib.Path:
    """Return the ``docs/`` directory."""
    return repository_root() / "docs"


# ── toctree parsing ─────────────────────────────────────────────────


def read_index(index_path: pathlib.Path) -> list[Node]:
    """Read the toctrees of *index_path* into nodes, grouped as authored.

    Parameters
    ----------
    index_path : pathlib.Path
        An ``index.rst`` or ``index.md`` holding one or more toctrees.

    Returns
    -------
    list of Node
        Groups and pages in the order the index lists them. An index whose
        toctrees are all globs yields its directory's pages, sorted by name.

    """
    if not index_path.is_file():
        return []
    text = _source(index_path)
    if not text:
        return []

    directory = index_path.parent
    lines = text.splitlines()
    nodes: list[Node] = []
    group: Optional[Node] = None
    index = 0
    # The page's own title is not a group inside itself, or the reference
    # section would open onto a single node called "Reference".
    own_title = page_title(index_path).strip().lower()

    def sink() -> list[Node]:
        return group.children if group is not None else nodes

    while index < len(lines):
        line = lines[index]

        rubric = _RUBRIC.match(line)
        if rubric:
            group = Node(rubric.group("title"), kind="group")
            nodes.append(group)
            index += 1
            continue

        heading = _heading_title(lines, index)
        if heading is not None:
            title, consumed = heading
            if title.strip().lower() != own_title:
                group = Node(title, kind="group")
                nodes.append(group)
            index += consumed
            continue

        if _TOCTREE_RST.match(line.strip()) or _TOCTREE_MYST.match(line.strip()):
            entries, caption, index = _read_toctree_block(lines, index, directory)
            if caption:
                group = Node(caption, kind="group")
                nodes.append(group)
            sink().extend(entries)
            continue

        index += 1

    # Groups that ended up empty are noise from headings that name prose rather
    # than a part of the tree.
    return [node for node in nodes if node.kind != "group" or node.children]


def _heading_title(lines: list[str], index: int) -> Optional[tuple[str, int]]:
    """Return ``(title, lines_consumed)`` when *index* starts a section heading."""
    line = lines[index]
    myst = _MYST_HEADING.match(line)
    if myst:
        return myst.group("title"), 1
    # reStructuredText: a line of text underlined by punctuation.
    if index + 1 < len(lines) and line.strip() and not line.startswith((" ", "\t", "..")):
        underline = lines[index + 1]
        if _RST_SECTION_ADORNMENT.match(underline) and len(underline.strip()) >= len(
            line.strip()
        ):
            return line.strip(), 2
    return None


def _read_toctree_block(
    lines: list[str], index: int, directory: pathlib.Path
) -> tuple[list[Node], str, int]:
    """Read one toctree, returning its entries, its caption and the next line."""
    caption = ""
    glob = False
    entries: list[Node] = []
    fenced = bool(_TOCTREE_MYST.match(lines[index].strip()))
    fence = lines[index].strip()[:3] if fenced else ""
    index += 1

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if fenced and stripped.startswith(fence):
            index += 1
            break
        if not fenced and stripped and not raw.startswith((" ", "\t")):
            break
        if not stripped:
            index += 1
            # A blank line ends a reStructuredText directive only if the next
            # content line is unindented; keep reading otherwise.
            if not fenced:
                following = _next_content(lines, index)
                if following is None or not following.startswith((" ", "\t")):
                    break
            continue

        option = re.match(r"^:(?P<key>[\w-]+):\s*(?P<value>.*)$", stripped)
        if option:
            key, value = option.group("key"), option.group("value").strip()
            if key == "caption":
                caption = value
            elif key == "glob":
                glob = True
            elif key == "hidden":
                pass
            index += 1
            continue

        node = _entry_node(stripped, directory)
        if node is not None:
            entries.append(node)
        elif "*" in stripped:
            glob = True
        index += 1

    if glob and not entries:
        entries = _directory_pages(directory)
    return entries, caption, index


def _next_content(lines: list[str], index: int) -> Optional[str]:
    """Return the next non-blank line, or ``None`` at the end."""
    while index < len(lines):
        if lines[index].strip():
            return lines[index]
        index += 1
    return None


def _entry_node(entry: str, directory: pathlib.Path) -> Optional[Node]:
    """Resolve one toctree entry to a node, or ``None`` when it names nothing."""
    title = ""
    target = entry
    labelled = _LABELLED.match(entry)
    if labelled:
        title = labelled.group("title").strip()
        target = labelled.group("target").strip()
    if not target or target.startswith(("http://", "https://")):
        return None

    path = _resolve(target, directory)
    if path is None:
        return None

    # An entry that is itself an index becomes a group holding that index's own
    # toctree -- which is how the reference section keeps its sub-parts.
    if path.stem == "index":
        children = read_index(path)
        if children:
            return Node(
                title or page_title(path) or path.parent.name,
                path=path,
                children=children,
                kind="group",
            )
    return Node(title or page_title(path) or path.stem, path=path)


def _resolve(target: str, directory: pathlib.Path) -> Optional[pathlib.Path]:
    """Resolve a toctree target to a file below *directory*."""
    candidate = (directory / target).resolve()
    for suffix in _SUFFIXES:
        with_suffix = candidate.with_suffix(suffix)
        if with_suffix.is_file():
            return with_suffix
    if candidate.is_dir():
        for suffix in _SUFFIXES:
            index = candidate / f"index{suffix}"
            if index.is_file():
                return index
    return candidate if candidate.is_file() else None


def _directory_pages(directory: pathlib.Path) -> list[Node]:
    """Every page in *directory*, sorted by file name; the glob fallback."""
    nodes = []
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in _SUFFIXES or path.stem == "index":
            continue
        nodes.append(Node(page_title(path) or path.stem, path=path))
    return nodes


# ── titles ──────────────────────────────────────────────────────────


#: Sources read while building the tree, keyed by path and modification stamp.
#: Every page is read for its title *and* its summary; without this the window
#: reads the whole documentation tree twice on each open.
_SOURCE_CACHE: dict[tuple[str, int, int], str] = {}


def _source(path: pathlib.Path) -> str:
    """Return the text of *path*, remembering it until the file changes."""
    try:
        stat = path.stat()
    except OSError:
        return ""
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    text = _SOURCE_CACHE.get(key)
    if text is None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if len(_SOURCE_CACHE) > 4000:  # a session, not a service
            _SOURCE_CACHE.clear()
        _SOURCE_CACHE[key] = text
    return text


def page_title(path: pathlib.Path) -> str:
    """Return the document's own title, or an empty string."""
    text = _source(path)
    if not text:
        return ""
    from chisurf.plugins.core.help.api.render import document_title

    return document_title(text, path) or ""


def page_summary(path: pathlib.Path, limit: int = 180) -> str:
    """Return a one-line description of *path* for the start page.

    The first real sentence of the document is used: it is written to introduce
    the page, so it describes it better than anything that could be generated.
    """
    from chisurf.plugins.core.help.api.markdown import strip_front_matter

    text = strip_front_matter(_source(path))
    if not text:
        return ""
    skip = re.compile(
        r"^\s*$|^[#=~^\-*`:.\[(]|^\.\.\s|^\||^\d+\.\s*$|^!\[|^\s*[-*+]\s"
    )
    lines = text.splitlines()
    for position, line in enumerate(lines):
        if skip.match(line):
            continue
        # A reStructuredText title is followed by an adornment line.
        if position + 1 < len(lines) and _RST_SECTION_ADORNMENT.match(lines[position + 1]):
            continue
        sentence = line.strip()
        sentence = re.sub(r"\*\*|__|\*|`|\{[a-z]+\}", "", sentence)
        sentence = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", sentence)
        if len(sentence) < 25:
            continue
        cut = sentence.find(". ")
        if 0 < cut < limit:
            return sentence[: cut + 1]
        return sentence[:limit].rstrip() + ("…" if len(sentence) > limit else "")
    return ""


# ── the tree ────────────────────────────────────────────────────────

#: How each top-level section reads in the browser, keyed by the index that
#: defines it. The *membership and order* are not here — they come from
#: ``docs/index.rst``, so a section added to the website appears in the
#: application without anyone remembering to add it in two places. This is only
#: the wording: the website's captions are parenthetical ("Concepts (theory)")
#: where a navigation row reads better with a dash, and a summary line has
#: nowhere to live in a caption at all.
_SECTION_WORDING = {
    "getting_started/index": (
        "Getting started", "Install ChiSurf, launch it, run a first analysis."),
    "fundamentals/index": (
        "Fundamentals — photophysics",
        "The excited state, transfer, the instrument and the counting "
        "statistics every method assumes."),
    "concepts/index": (
        "Concepts — the theory",
        "What each method measures, with the formulas and the assumptions."),
    "guides/index": (
        "Guides — how to in ChiSurf", "Step-by-step workflows in the real interface."),
    "manual/index": (
        "Fitting interface & examples",
        "The fitting interface itself, and complete worked examples."),
    "reference/index": (
        "Reference", "File formats, settings, parameters and the plugin catalogue."),
    "references/index": (
        "Literature", "Every work the documentation cites, each linking to the paper."),
}

#: Sections the root index lists that are not user documentation. Development is
#: shown only behind the authoring toggle, and builds its own node there.
_NOT_USER_SECTIONS = {"development/index"}

#: Files under a plugin that document the plugin for its maintainer, not its user.
_MAINTAINER_PAGES = {
    "status.md", "contract.md", "todo.md", "notes.md", "changelog.md",
    "migration.md", "handover.md", "roadmap.md", "plan.md",
}


def build_toc(
    *,
    root: Optional[pathlib.Path] = None,
    include_development: bool = False,
    plugins: Optional[Iterable[dict]] = None,
) -> Node:
    """Build the whole help table of contents.

    Parameters
    ----------
    root : pathlib.Path, optional
        Repository root; discovered from this file when omitted.
    include_development : bool, optional
        Include architecture notes, module READMEs and other maintainer
        material. Off by default: it is not user documentation.
    plugins : iterable of dict, optional
        Plugin descriptors as :func:`chisurf.plugins.iter_plugins` yields them.
        ``None`` asks the plugin registry directly.

    Returns
    -------
    Node
        The root node; its children are the sections.

    """
    base = root or repository_root()
    docs = base / "docs"
    toc = Node("ChiSurf help", kind="section")

    for index, caption in _root_sections(docs):
        if index in _NOT_USER_SECTIONS:
            continue
        path = _index_path(docs, index)
        if path is None:
            continue
        title, summary = _SECTION_WORDING.get(index, (caption or "", ""))
        section = Node(
            title or caption or page_title(path),
            path=path,
            kind="section",
            summary=summary,
        )
        # A section index without a toctree is simply a page (Getting started
        # is one long page); it still belongs in the tree, as a leaf.
        section.children = read_index(path)
        toc.add(section)

    plugin_section = _plugin_section(plugins)
    if plugin_section.children:
        toc.add(plugin_section)

    about = _about_section(base)
    if about.children:
        toc.add(about)

    if include_development:
        development = Node(
            "Developing ChiSurf",
            path=_index_path(docs, "development/index"),
            kind="section",
            summary="Architecture, benchmarks and maintainer notes.",
        )
        development.children = read_index(docs / "development/index.rst")
        development.children.extend(_module_docs(base))
        if development.children:
            toc.add(development)

    _fill_summaries(toc)
    return toc


def _root_sections(docs: pathlib.Path) -> list[tuple[str, str]]:
    """Return ``(index, caption)`` for each section ``docs/index`` lists.

    The sections of the application's tree are the sections of the website,
    read from the same file — otherwise a section added to one is simply absent
    from the other, silently and for as long as nobody opens both. (That is not
    hypothetical: ``fundamentals/`` was published on the website and missing
    from the help browser.)

    Falls back to the known order when the root index cannot be read, so a
    packaging accident degrades the wording rather than emptying the tree.
    """
    root_index = _index_path(docs, "index")
    found: list[tuple[str, str]] = []
    if root_index is not None:
        for node in read_index(root_index):
            caption = node.title if node.kind == "group" else ""
            entries = node.children if node.kind == "group" else [node]
            for entry in entries:
                if entry.path is None:
                    continue
                try:
                    relative = entry.path.relative_to(docs).with_suffix("").as_posix()
                except ValueError:
                    continue
                if relative.endswith("/index"):
                    found.append((relative, caption))
    if found:
        return found
    return [(index, "") for index in _SECTION_WORDING]


def _index_path(docs: pathlib.Path, index: str) -> Optional[pathlib.Path]:
    for suffix in _SUFFIXES:
        candidate = docs / f"{index}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _plugin_section(plugins: Optional[Iterable[dict]]) -> Node:
    """Build the per-plugin branch from the plugin registry."""
    section = Node(
        "Plugins",
        kind="section",
        summary="Every installed analysis tool, with its own documentation.",
    )
    if plugins is None:
        try:
            import chisurf.plugins as _plugins

            plugins = list(_plugins.iter_plugins())
        except Exception:
            plugins = []

    plugin_list = list(plugins or [])
    directories = {
        pathlib.Path(info["package_dir"]).resolve()
        for info in plugin_list
        if info.get("package_dir")
    }

    entries: list[tuple[str, Node]] = []
    for info in plugin_list:
        package_dir = info.get("package_dir")
        if not package_dir:
            continue
        directory = pathlib.Path(package_dir).resolve()
        # Some plugins nest others (the games menu holds five). Without this a
        # parent claims its children's documentation and the same page is
        # listed twice under two names.
        nested = [other for other in directories if other != directory and _within(other, directory)]
        pages = [
            path
            for path in sorted(directory.rglob("*.md"))
            if path.name.lower() not in _MAINTAINER_PAGES
            and "test" not in path.parts
            and not any(_within(path, child) for child in nested)
        ]
        if not pages:
            continue
        readme = next((p for p in pages if p.name.lower() == "readme.md"), None)
        name = info.get("plugin_name") or info.get("module_name") or directory.name
        label = name.split(":")[-1].strip() or directory.name
        if readme is not None:
            label = page_title(readme) or label
        others = [p for p in pages if p is not readme]
        if not others:
            node = Node(label, path=readme or pages[0])
        else:
            node = Node(label, path=readme, kind="group")
            for path in others:
                node.add(Node(_page_label(path, label, directory), path=path))
        entries.append((label.lower(), node))

    for _, node in sorted(entries, key=lambda pair: pair[0]):
        section.add(node)
    return section


def _within(path: pathlib.Path, directory: pathlib.Path) -> bool:
    """Whether *path* lies inside *directory*.

    Compared as strings: ``Path.relative_to`` costs a parse and a tuple compare
    per call, and this runs once per documentation file per nested plugin —
    2.5 s of a 2.8 s window open, measured.
    """
    return str(path).startswith(str(directory) + "/")


def _page_label(path: pathlib.Path, plugin_label: str, directory: pathlib.Path) -> str:
    """Name a plugin's extra page so it is not a copy of the plugin's own row.

    A plugin's ``gui/help.md`` opens with the plugin's name, so listed as-is it
    produces two adjacent rows reading the same thing.
    """
    title = page_title(path) or path.stem
    if title.strip().lower() != plugin_label.strip().lower():
        return title
    try:
        relative = path.relative_to(directory)
    except ValueError:
        return title
    if path.name.lower() == "help.md":
        return f"{title} — control reference"
    return f"{title} — {relative.as_posix()}"


def _about_section(base: pathlib.Path) -> Node:
    """README and release notes — what the project is, and what changed."""
    section = Node("About ChiSurf", kind="section", summary="What ChiSurf is, and what changed.")
    for name, title in (("README.md", "About ChiSurf"), ("CHANGELOG.md", "Release notes")):
        path = base / name
        if path.is_file():
            section.add(Node(title, path=path))
    return section


def _module_docs(base: pathlib.Path) -> list[Node]:
    """Documentation of the bundled sibling packages, for maintainers."""
    nodes: list[Node] = []
    modules = base / "modules"
    if not modules.is_dir():
        return nodes
    for directory in sorted(p for p in modules.iterdir() if p.is_dir()):
        pages = [
            path
            for path in sorted(directory.rglob("*.md"))
            if not any(part.startswith(".") for part in path.parts)
            and "test" not in path.parts
            and "node_modules" not in path.parts
        ]
        if not pages:
            continue
        group = Node(directory.name, kind="group")
        for path in pages[:40]:
            group.add(Node(page_title(path) or path.stem, path=path))
        nodes.append(group)
    return nodes


def _fill_summaries(node: Node) -> None:
    """Give every page a one-line summary, for tooltips and the start page."""
    for child in node.children:
        if child.path is not None and not child.summary:
            child.summary = page_summary(child.path)
        _fill_summaries(child)


def iter_pages(node: Node) -> Iterable[Node]:
    """Yield every node that has a document behind it."""
    for candidate in node.walk():
        if candidate.path is not None:
            yield candidate
