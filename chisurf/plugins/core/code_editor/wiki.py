"""The LLM Wiki the assistant reads: list and filter its pages, and feed the codebase into it.

Toolkit-free (moved out of the retired Qt agent panel): the emtk assistant's *Wiki* window draws
:class:`WikiIndex` and runs :func:`populate_from_codebase` on a worker. The wiki lives in
``<repo>/llm-wiki/wiki`` with the sections ``entities``, ``concepts``, ``sources`` and
``synthesis``; ``index.md`` lists the pages and ``log.md`` records each populate.
"""

from __future__ import annotations

import datetime as _dt
import pathlib
from collections.abc import Callable

from chisurf.plugins.core.code_editor.wiki_indexer import build_api_index

__all__ = ["SECTIONS", "WikiIndex", "populate_from_codebase", "repository_root", "wiki_dir"]

#: The page folders of the wiki, in the order they are listed.
SECTIONS = ("entities", "concepts", "sources", "synthesis")


def repository_root() -> pathlib.Path:
    """The source checkout this package lives in."""
    return pathlib.Path(__file__).resolve().parents[4]


def wiki_dir(root: pathlib.Path | None = None) -> pathlib.Path:
    """``<root>/llm-wiki/wiki`` (``root`` defaults to :func:`repository_root`)."""
    return (root or repository_root()) / "llm-wiki" / "wiki"


def page_title(path: pathlib.Path) -> str:
    """A page's ``title:`` front matter, else its first ``# `` heading, else its file stem."""
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except OSError:
        return path.stem
    if len(lines) > 1 and lines[0] == "---":
        for line in lines[1:]:
            if line == "---":
                break
            if line.startswith("title:"):
                return line.split(":", 1)[1].strip()
    for line in lines:
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


class WikiIndex:
    """The wiki's pages as ``"section: title"`` entries, filtered by a search text."""

    def __init__(self, directory: pathlib.Path | None = None) -> None:
        self.directory = directory or wiki_dir()
        self.pages: dict[str, pathlib.Path] = {}
        self.index_text = ""
        self.message = ""
        self.reload()

    def reload(self) -> None:
        """Re-read ``index.md`` and the section folders."""
        self.pages = {}
        if not self.directory.exists():
            self.index_text, self.message = "", "LLM Wiki not found."
            return
        index = self.directory / "index.md"
        self.index_text = index.read_text(encoding="utf-8") if index.exists() else ""
        self.message = "" if index.exists() else "Wiki index.md not found."
        for section in SECTIONS:
            folder = self.directory / section
            if folder.exists():
                for path in sorted(folder.glob("*.md")):
                    self.pages[f"{section}: {page_title(path)}"] = path

    def entries(self, search: str = "") -> list[str]:
        """The entries whose text contains *search* (case-insensitive), in listing order."""
        needle = search.strip().lower()
        return [entry for entry in self.pages if not needle or needle in entry.lower()]

    def read(self, entry: str) -> str:
        """The text of the page *entry* names (``""`` when it is gone)."""
        path = self.pages.get(entry)
        try:
            return path.read_text(encoding="utf-8") if path is not None else ""
        except OSError:
            return ""


def _source_page(title: str, path: str, content: str, today: str) -> str:
    return f"""---
title: {title}
type: source
sources: [{path}]
related: []
created: {today}
updated: {today}
---

# {title}

Source file: `{path}`

## Code Content

```python
{content[:5000]}
```
"""


def _concept_page(title: str, item: dict[str, str], today: str) -> str:
    return f"""---
title: {title}__{item["name"]}
type: concept
sources: [{item["path"]}]
related: [[{title}]]
created: {today}
updated: {today}
---

# {item["name"]}

Type: {item["type"]}

Source: `{item["path"]}`

## Definition

```python
{item["definition"]}
```
"""


def _larger_concepts(files: list[pathlib.Path]) -> list[dict[str, str]]:
    """Classes (their first 80 lines) of *files*, at most 20."""
    concepts: list[dict[str, str]] = []
    for py_file in files:
        try:
            lines = py_file.read_text(encoding="utf-8").split("\n")
        except Exception:
            continue
        current, start, body = None, 0, []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("class "):
                if current and body:
                    concepts.append({"name": current, "type": "class", "definition": "\n".join(body)[:3000]})
                current = stripped.split("(", 1)[0].split(" ", 1)[1].strip().rstrip(":")
                start, body = i, lines[i : min(i + 80, len(lines))]
            elif current and i > start + 80:
                concepts.append({"name": current, "type": "class", "definition": "\n".join(body)[:3000]})
                current, body = None, []
        if current and body:
            concepts.append({"name": current, "type": "class", "definition": "\n".join(body)[:3000]})
    return concepts[:20]


def populate_from_codebase(
    root: pathlib.Path | None = None, progress: Callable[[str], None] | None = None
) -> int:
    """Write the ``chisurf/`` sources into the wiki, a page per package, and rebuild the API index.

    Parameters
    ----------
    root : pathlib.Path, optional
        Repository root (default :func:`repository_root`).
    progress : callable, optional
        ``progress(text)`` after each package.

    Returns
    -------
    int
        Number of source pages written.
    """
    root = root or repository_root()
    directory = wiki_dir(root)
    sources, concepts_dir = directory / "sources", directory / "concepts"
    for folder in (sources, concepts_dir, directory / "synthesis"):
        folder.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    groups: dict[str, list[pathlib.Path]] = {}
    for py_file in (root / "chisurf").rglob("*.py"):
        if "__pycache__" in py_file.parts or "test" in py_file.parts:
            continue
        parts = py_file.relative_to(root / "chisurf").parts
        key = "/".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "root")
        groups.setdefault(key, []).append(py_file)
    pages: list[str] = []
    count = 0
    for number, (key, files) in enumerate(groups.items(), start=1):
        title = key.replace("/", "_")[:80]
        paths, chunks = [], []
        for py_file in files:
            rel = py_file.relative_to(root).as_posix()
            paths.append(rel)
            try:
                text = py_file.read_text(encoding="utf-8")
            except Exception:
                continue
            chunks.append(f"\n\n## File: `{rel}`\n\n```python\n{text[:4000]}\n```")
        (sources / f"{title}.md").write_text(
            _source_page(title, ", ".join(paths), "\n".join(chunks), today), encoding="utf-8"
        )
        for item in _larger_concepts(files):
            item["path"] = ", ".join(paths[:5])
            (concepts_dir / f"{title}__{item['name']}.md").write_text(
                _concept_page(title, item, today), encoding="utf-8"
            )
            pages.append(f"[[{title}__{item['name']}]]")
        pages.append(f"[[{title}]]")
        count += 1
        if progress is not None:
            progress(f"Processed {number}/{len(groups)}: {key}")
    index = (
        f"---\ntitle: Wiki Index\ntype: index\nupdated: {today}\n---\n\n# Wiki Index\n\n"
        "> Catalog of all wiki pages for the ChiSurf codebase. Updated by the agent on every ingest.\n\n"
        "## Codebase Sources\n\n" + "".join(f"- [[{page}]]\n" for page in sorted(set(pages))[:100])
    )
    (directory / "index.md").write_text(index, encoding="utf-8")
    entry = f"\n## [{today}] populate | Fed {count} codebase files into LLM Wiki\n"
    log = directory / "log.md"
    if log.exists():
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(entry)
    else:
        log.write_text("---\ntitle: Activity Log\ntype: log\n---\n\n# Activity Log\n" + entry, encoding="utf-8")
    build_api_index(root)
    return count
