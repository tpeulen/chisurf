"""Regenerate the release plugin checklist without importing plugin code."""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = (
    "plugin",
    "name",
    "view",
    "help",
    "guide",
    "qt",
    "emtk",
    "qtimp",
    "always",
    "setup",
    "ui",
    "pg",
    "demo",
    "hidden",
)
HEADER = (
    "plugin",
    "display_name",
    "view.json",
    "help.md",
    "guide.json",
    "Qt entry",
    "emtk entry",
    "imports Qt",
    "Cond.ALWAYS reference",
    "setup reference",
    ".ui",
    "pyqtgraph/.native reference",
    "demo.py",
    "hidden",
)
BEGIN = "<!-- plugin-inventory:start -->\n"
END = "<!-- plugin-inventory:end -->"


def _test_path(path: Path) -> bool:
    """Exclude template and test resources from the shipped plugin checklist."""
    return any(
        part in {"test", "tests", "__pycache__"} or "cookiecutter" in part for part in path.parts
    ) or path.name.startswith("test_")


def _dotted(node: ast.AST) -> str:
    """Return the lexical name of an imported or referenced symbol."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    return ""


def inventory(plugin_root: Path, *, revision: str | None = None) -> list[dict]:
    """Report production files belonging to each manifest, excluding nested plugins.

    Parameters
    ----------
    plugin_root : pathlib.Path
        Directory containing the plugin manifests.
    revision : str, optional
        Git revision to measure in an isolated archive; otherwise measure the working tree.

    Returns
    -------
    list of dict
        Deterministically ordered source-presence records. These do not assert
        that a GUI constructs or that its controls/tour function.
    """
    if revision is not None:
        root = Path(
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"], cwd=plugin_root, text=True
            ).strip()
        )
        relative = plugin_root.resolve().relative_to(root.resolve())
        archive = subprocess.check_output(
            ["git", "archive", "--format=tar", revision, "--", str(relative)], cwd=root
        )
        with tempfile.TemporaryDirectory(prefix="chisurf-plugin-inventory-") as scratch:
            with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                bundle.extractall(scratch, filter="data")
            return inventory(Path(scratch) / relative)
    manifests = sorted(p for p in plugin_root.rglob("manifest.json") if not _test_path(p))
    owners = {p.parent for p in manifests}
    rows = []
    for manifest in manifests:
        folder = manifest.parent
        try:
            data = json.loads(manifest.read_text())
            if not isinstance(data, dict):
                raise ValueError("Expected a manifest object")
            entrypoints = data.get("entrypoints") or {}
            if not isinstance(entrypoints, dict):
                raise ValueError("Expected an entrypoints object")
        except (OSError, ValueError) as error:
            raise ValueError(f"Invalid plugin manifest {manifest}: {error}") from error
        files = []
        for path in folder.rglob("*"):
            if not path.is_file() or _test_path(path.relative_to(plugin_root)):
                continue
            owner = next(parent for parent in path.parents if parent in owners)
            if owner == folder:
                files.append(path)
        names = {p.name for p in files}
        imports: set[str] = set()
        references: set[str] = set()
        for source in files:
            if source.suffix != ".py":
                continue
            try:
                tree = ast.parse(source.read_text(), filename=str(source))
            except (OSError, UnicodeError, SyntaxError) as error:
                raise ValueError(f"Invalid plugin source {source}: {error}") from error
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.add(node.module or "")
                elif isinstance(node, (ast.Name, ast.Attribute)):
                    references.add(_dotted(node))
        row = {
            "plugin": folder.relative_to(plugin_root).as_posix(),
            "name": data.get("display_name", ""),
            "view": any(name.endswith("view.json") for name in names),
            "help": "help.md" in names,
            "guide": "guide.json" in names,
            "qt": bool(entrypoints.get("gui")),
            "emtk": bool(entrypoints.get("emtk")),
            "qtimp": any(
                name.split(".")[0] in {"qtpy", "PyQt5", "PyQt6", "PySide", "PySide2", "PySide6"}
                for name in imports
            ),
            "always": any(name.endswith("Cond.ALWAYS") for name in references),
            "setup": any(
                "channel_definition" in name or "optical_configuration" in name
                for name in imports | references
            ),
            "ui": any(name.endswith(".ui") for name in names),
            "pg": any(name.split(".")[0] == "pyqtgraph" for name in imports)
            or any(name.endswith(".native") for name in references),
            "demo": "demo.py" in names,
            "hidden": bool(data.get("menu_hidden")),
        }
        rows.append(row)
    return rows


def render_markdown(rows: list[dict]) -> str:
    """Render the current records as a deterministic checklist with qualified counts."""

    def cell(value):
        if isinstance(value, bool):
            return "✓" if value else "—"
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(HEADER) + " |", "|" + "---|" * len(COLUMNS)]
    lines.extend("| " + " | ".join(cell(row[key]) for key in COLUMNS) + " |" for row in rows)
    summary = [f"{len(rows)} plugins"]
    summary.extend(
        f"missing {key}={sum(not row[key] for row in rows)}" for key in ("view", "help", "guide")
    )
    summary.extend(
        f"{key}={sum(bool(row[key]) for row in rows)}"
        for key in ("qt", "emtk", "qtimp", "always", "setup", "ui", "pg", "demo")
    )
    lines += ["", "; ".join(summary) + ".", ""]
    return "\n".join(lines)


def main() -> None:
    """Print the inventory or update the tracked checklist and owning appendix."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root")
    parser.add_argument("--json", action="store_true", help="Print machine-readable records")
    parser.add_argument("--revision", help="Measure a committed revision in an isolated archive")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Update the committed-source appendix and both tree receipts",
    )
    args = parser.parse_args()
    rows = inventory(
        args.root / "chisurf" / "plugins",
        revision=args.revision or ("HEAD" if args.write else None),
    )
    text = render_markdown(rows)
    if args.write:
        receipts = args.root / "okf" / "validation" / "release-readiness-w6g"
        receipts.mkdir(parents=True, exist_ok=True)
        working = inventory(args.root / "chisurf" / "plugins")
        frontmatter = (
            "---\ntype: Validation\ntitle: Plugin source inventory\n"
            "description: Generated source presence and references; runtime acceptance remains separate.\n---\n\n"
        )
        (receipts / "plugin-inventory-worktree.md").write_text(
            frontmatter + render_markdown(working)
        )
        (receipts / "plugin-inventory-worktree.json").write_text(
            json.dumps(working, indent=2) + "\n"
        )
        (receipts / "plugin-inventory.md").write_text(frontmatter + text)
        (receipts / "plugin-inventory.json").write_text(json.dumps(rows, indent=2) + "\n")
        prd = args.root / "okf" / "prds" / "prd-154.md"
        document = prd.read_text()
        if BEGIN in document:
            before, rest = document.split(BEGIN, 1)
            _, after = rest.split(END, 1)
            document = before + BEGIN + text + END + after
        else:
            appendix = document.index("## Appendix A")
            match = re.search(r"^\| plugin \| display_name \|", document[appendix:], re.M)
            if match is None:
                raise ValueError("The owning appendix has no plugin inventory table")
            table = appendix + match.start()
            stop = document.index("\n---\n\n## Part E", table)
            document = document[:table] + BEGIN + text + END + "\n" + document[stop:]
        prd.write_text(document)
    else:
        print(json.dumps(rows, indent=2) if args.json else text, end="\n" if args.json else "")


if __name__ == "__main__":
    main()
