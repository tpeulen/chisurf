"""File I/O for the Help plugin — document discovery and access."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import chisurf as cs
import chisurf.core.settings
import chisurf.plugins
from chisurf.plugins.core.help.api import review
from chisurf.plugins.core.help.api.markdown import extract_title
from chisurf.plugins.core.help.api.render import document_title

#: Suffixes discovered under ``docs/`` (the manual is reStructuredText).
DOC_SUFFIXES = (".md", ".rst")

#: Project-root files shown in the "Core" category.
CORE_DOC_FILES = ("README.md", "CHANGELOG.md")

#: Project-root directories scanned for "Core" documentation. An allow-list:
#: the repository also carries agent scratch space, an internal knowledge
#: bundle and tool dot-directories, none of which are user documentation.
CORE_DOC_ROOTS = ("examples", "modules")


@dataclass
class DocEntry:
    """Single documentation entry from discovery."""

    path: str
    title: str
    category: str
    file_name: str
    size: int
    review_status: str = review.STATUS_REVIEWED
    reviewer: str = ""
    review_date: str = ""


@dataclass
class DocInfo:
    """Full document index produced by :func:`discover_docs`."""

    entries: list[DocEntry] = field(default_factory=list)
    tree: dict[str, list[dict]] = field(default_factory=dict)


def discover_docs() -> DocInfo:
    """Discover all documentation files.

    Covers Markdown throughout the project and the reStructuredText user manual.
    Entries in review-tracked directories carry their sign-off status.

    Returns
    -------
    DocInfo
        All discovered documents with tree structure and flat list.

    """
    entries: list[DocEntry] = []
    tree: dict[str, list[dict]] = {
        "User manual": [],
        "Documentation": [],
        "Core": [],
        "Plugins": [],
    }

    base = pathlib.Path(cs.__file__).resolve().parent
    root = base.parent

    # Project documentation: the reStructuredText manual is kept in its own
    # category because it is the part under human-review gating.
    docs_dir = root / "docs"
    manual_dir = docs_dir / "manual"
    if docs_dir.exists():
        paths = sorted(
            p for p in docs_dir.rglob("*") if p.suffix.lower() in DOC_SUFFIXES and p.is_file()
        )
        for path in paths:
            try:
                rel = path.relative_to(docs_dir)
            except ValueError:
                rel = path.name
            in_manual = _is_within(path, manual_dir)
            category = "User manual" if in_manual else "Documentation"
            title = _get_title(path, str(rel))
            entry = _make_entry(path, title, category, str(rel))
            entries.append(entry)
            tree[category].append(
                {
                    "path": str(path),
                    "title": title,
                    "file_name": str(rel),
                    "review_status": entry.review_status,
                }
            )

    # Core project .md files
    for path in core_doc_paths(root):
        rel = path.relative_to(root)
        title = _get_title(path, str(rel))
        entries.append(
            DocEntry(
                path=str(path),
                title=title,
                category="Core",
                file_name=str(rel),
                size=path.stat().st_size,
            )
        )
        tree["Core"].append({"path": str(path), "title": title, "file_name": str(rel)})

    # Plugin docs
    try:
        plugin_infos = list(cs.plugins.iter_plugins())
    except Exception:
        plugin_infos = []

    for info in plugin_infos:
        plugin_dir = pathlib.Path(info.get("package_dir")).resolve()
        markdown_files = sorted(plugin_dir.rglob("*.md"))
        if not markdown_files:
            continue

        readme_path = None
        for p in markdown_files:
            if p.name.lower() in {"readme.md", "readme"}:
                readme_path = p
                break
        if readme_path is not None:
            readme_text = readme_path.read_text(encoding="utf-8")
            readme_title = extract_title(readme_text)
        else:
            readme_title = None

        plugin_name = info.get("plugin_name") or info.get("module_name") or plugin_dir.name
        clean_name = plugin_name.split(":")[-1].strip() if ":" in plugin_name else plugin_name
        plugin_label = readme_title or clean_name or plugin_dir.name

        plugin_tree_entries = []
        for md_path in markdown_files:
            try:
                rel = md_path.relative_to(plugin_dir)
            except ValueError:
                rel = md_path.name
            title = _get_title(md_path, str(rel))
            entries.append(
                DocEntry(
                    path=str(md_path),
                    title=title,
                    category=f"Plugins/{plugin_label}",
                    file_name=str(rel),
                    size=md_path.stat().st_size,
                )
            )
            plugin_tree_entries.append(
                {"path": str(md_path), "title": title, "file_name": str(rel)}
            )

        # Use the category-style grouping
        tree_key = f"Plugins/{plugin_label}"
        tree[tree_key] = plugin_tree_entries

    return DocInfo(entries=entries, tree=tree)


def read_doc(path_str: str) -> str | None:
    """Read a documentation file.

    Parameters
    ----------
    path_str : str
        Filesystem path to the Markdown file.

    Returns
    -------
    str or None
        File contents, or *None* if the file cannot be read.

    """
    path = pathlib.Path(path_str)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def save_doc(path_str: str, content: str) -> bool:
    """Save *content* to a documentation file.

    Parameters
    ----------
    path_str : str
        Filesystem path to write to.
    content : str
        New file content.

    Returns
    -------
    bool
        *True* on success.

    """
    path = pathlib.Path(path_str)
    try:
        path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def search_docs(query: str) -> list[dict]:
    """Search documentation files for *query*.

    Parameters
    ----------
    query : str
        Lowercased search term.

    Returns
    -------
    list of dict
        Matching entries with ``path``, ``title``, ``match_type``.

    """
    results: list[dict] = []
    query_lower = query.lower()
    try:
        info = discover_docs()
    except Exception:
        return results

    for entry in info.entries:
        path = pathlib.Path(entry.path)
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            text = ""

        lower_text = text.lower()

        if query_lower in entry.title.lower():
            match_type = "title"
        elif query_lower in entry.file_name.lower():
            match_type = "filename"
        elif query_lower in lower_text:
            match_type = "content"
        else:
            continue

        results.append(
            {
                "path": entry.path,
                "title": entry.title,
                "match_type": match_type,
            }
        )

    return results


def core_doc_paths(root: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Collect the project-level Markdown shown in the "Core" category.

    The roots are allow-listed rather than deny-listed: a working tree also
    holds scratch directories, the internal knowledge bundle and tool
    dot-directories, and none of those are user documentation. Plugin pages are
    skipped here because the "Plugins" category owns them. Both the document
    index and the GUI tree read the category through this one function.

    Parameters
    ----------
    root : pathlib.Path, optional
        Project root directory. Defaults to the parent of the ``chisurf``
        package.

    Returns
    -------
    list of pathlib.Path
        Sorted, de-duplicated Markdown files.

    """
    if root is None:
        root = pathlib.Path(cs.__file__).resolve().parent.parent
    paths = {root / name for name in CORE_DOC_FILES}
    for sub in CORE_DOC_ROOTS:
        directory = root / sub
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.md"):
            rel = path.relative_to(root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if "plugins" in rel.parts:
                continue
            paths.add(path)
    return sorted(p for p in paths if p.is_file())


# ── helpers ─────────────────────────────────────────────────────────


def _get_title(path: pathlib.Path, fallback: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return fallback
    title = document_title(text, path)
    return title if title else fallback


def _is_within(path: pathlib.Path, directory: pathlib.Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _make_entry(path: pathlib.Path, title: str, category: str, file_name: str) -> DocEntry:
    """Build a :class:`DocEntry`, attaching review status for tracked pages."""
    status = review.status_of(path)
    return DocEntry(
        path=str(path),
        title=title,
        category=category,
        file_name=file_name,
        size=path.stat().st_size,
        review_status=status.status,
        reviewer=status.reviewer,
        review_date=status.date,
    )
