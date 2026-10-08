"""Audit declared and imperative tooltip contracts without importing GUI code."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLS = frozenset(
    {
        "button",
        "small_button",
        "checkbox",
        "selectable",
        "combo",
        "begin_combo",
        "input_text",
        "slider_float",
        "slider_int",
    }
)
SECTION_TYPES = frozenset(
    {
        "value",
        "choice",
        "toggle",
        "toggle_row",
        "custom",
        "table",
        "data_table",
        "plot",
        "panel",
        "group",
        "dock_area",
        "wizard_step",
    }
)
SKIP_PARTS = frozenset(
    {
        "test",
        "tests",
        "build",
        ".pixi",
        ".git",
        "__pycache__",
        "site-packages",
        "junk",
        "node_modules",
    }
)


@dataclass(frozen=True)
class Finding:
    """One stable contract location, with source line retained separately for review."""

    path: str
    location: str
    code: str
    detail: str
    line: int | None = None

    @property
    def key(self) -> str:
        """Identify the missing contract without coupling a baseline to line offsets."""
        return f"{self.path}#{self.location}:{self.code}"


def _nonempty(value) -> bool:
    """Whether a declared explanation contains actual text."""
    return isinstance(value, str) and bool(value.strip())


def audit_json(text: str, path: str) -> list[Finding]:
    """Inspect nested sections and named view templates; reject unreadable declarations."""
    findings = []
    try:
        root = json.loads(text)
    except (ValueError, TypeError) as exc:
        return [Finding(path, "/", "invalid-json", str(exc))]
    if not isinstance(root, (dict, list)):
        return [Finding(path, "/", "invalid-view", "Expected a view object or section list.")]

    def missing(location, code, detail):
        findings.append(Finding(path, location, code, detail))

    def explained(node):
        return any(_nonempty(node.get(key)) for key in ("description", "tooltip"))

    def walk(node, location):
        if isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{location}/{index}")
            return
        if not isinstance(node, dict):
            return
        kind = node.get("type")
        if kind in SECTION_TYPES:
            # Anonymous grouping rows have no displayed item to hover.
            anonymous = kind in {"panel", "group", "dock_area"} and not any(
                _nonempty(node.get(key)) for key in ("title", "label", "name")
            )
            if not anonymous and not explained(node):
                missing(
                    location,
                    "section-tooltip",
                    f"{kind} {node.get('attr') or node.get('key') or node.get('title') or ''}",
                )
        if kind in {"button_row", "toggle_row"}:
            key = "buttons" if kind == "button_row" else "items"
            for index, item in enumerate(node.get(key) or []):
                if isinstance(item, dict) and not explained(item):
                    missing(
                        f"{location}/{key}/{index}",
                        "item-tooltip",
                        str(item.get("action") or item.get("attr") or item.get("label") or ""),
                    )
        if kind == "choice" and node.get("style") in {"radio", "radio_list"}:
            options = node.get("options") or node.get("choices") or []
            notes = node.get("descriptions") or []
            if isinstance(options, list):
                for index, option in enumerate(options):
                    if index >= len(notes) or not _nonempty(notes[index]):
                        missing(f"{location}/descriptions/{index}", "radio-tooltip", str(option))
        if kind in {"table", "data_table"} or (
            kind == "custom" and node.get("key") == "data_table"
        ):
            options = node.get("options") if isinstance(node.get("options"), dict) else {}
            columns = options.get("columns", node.get("columns", []))
            prefix = f"{location}/options" if "columns" in options else location
            for index, column in enumerate(columns or []):
                if isinstance(column, dict) and not explained(column):
                    missing(
                        f"{prefix}/columns/{index}",
                        "column-tooltip",
                        str(column.get("key") or column.get("title") or ""),
                    )
        for key, value in node.items():
            # Schema and arbitrary configuration/data are not view sections.
            if key not in {"$defs", "definitions", "properties", "hidden_when", "data", "defaults"}:
                walk(value, f"{location}/{key}")

    walk(root, "")
    return findings


def _dotted(node: ast.AST) -> str:
    """Return a lexical name without evaluating source expressions."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    return ""


def audit_python(text: str, path: str) -> list[Finding]:
    """Require a tooltip after a direct immediate-mode control in the same block."""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [Finding(path, "/", "invalid-python", str(exc), exc.lineno)]
    aliases = {"im", "im_widgets"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "emtk":
            aliases.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in {"im", "im_widgets"}
            )
        elif isinstance(node, ast.Import):
            aliases.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in {"emtk.im", "emtk.im_widgets"}
            )

    def api(call, names):
        dotted = _dotted(call.func) if isinstance(call, ast.Call) else ""
        return any(dotted == f"{alias}.{name}" for alias in aliases for name in names)

    def tip(call):
        if not api(call, {"set_item_tooltip"}) or not call.args:
            return False
        arg = call.args[0]
        return not isinstance(arg, ast.Constant) or _nonempty(arg.value)

    helpers = {}

    def collect_helpers(node, scope=""):
        for item in getattr(node, "body", []):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls = [call for call in ast.walk(item) if isinstance(call, ast.Call)]
                if any(tip(call) for call in calls):
                    helpers[(scope, item.name)] = item
            elif isinstance(item, ast.ClassDef):
                collect_helpers(item, item.name)

    collect_helpers(tree)

    def helper(call, scope):
        name = _dotted(call.func)
        key = (scope, name.removeprefix("self.")) if name.startswith("self.") else ("", name)
        function = helpers.get(key)
        if function is None:
            return False
        if any(api(nested, CONTROLS) for nested in ast.walk(function)):
            return False  # the helper's tooltip would describe its own new item
        # Do not accept a helper known to receive an empty explanation.
        params = [arg.arg for arg in function.args.args]
        if params and params[0] == "self":
            params = params[1:]
        values = (
            dict(zip(params[-len(function.args.defaults) :], function.args.defaults))
            if function.args.defaults
            else {}
        )
        values.update(zip(params, call.args))
        values.update((kw.arg, kw.value) for kw in call.keywords if kw.arg)
        for nested in ast.walk(function):
            if tip(nested) and isinstance(nested.args[0], ast.Name):
                value = values.get(nested.args[0].id)
                if isinstance(value, ast.Constant) and not _nonempty(value.value):
                    return False
        return True

    findings = []
    occurrences: Counter[str] = Counter()

    def top_calls(statement):
        # Conditional bodies have their own blocks; a clicked-only tip cannot
        # explain a button while hovered without clicking it.
        fields = ("test",) if isinstance(statement, (ast.If, ast.While)) else ("value",)
        for field in fields:
            expression = getattr(statement, field, None)
            if expression is not None:

                def calls(node):
                    if isinstance(node, ast.Lambda):
                        return
                    if isinstance(node, ast.Call):
                        yield node
                    for child in ast.iter_child_nodes(node):
                        yield from calls(child)

                yield from calls(expression)

    def transparent(statement):
        """Last-item bookkeeping/style changes can precede help without drawing a new item."""
        if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            return False
        for node in ast.walk(statement):
            if isinstance(node, ast.Call):
                dotted = _dotted(node.func)
                for alias in aliases:
                    if dotted.startswith(alias + "."):
                        name = dotted[len(alias) + 1 :]
                        if not (
                            name.startswith(("get_", "is_", "calc_", "push_style", "pop_style"))
                            or name
                            in {"end_disabled", "begin_disabled", "same_line", "set_item_tooltip"}
                        ):
                            return False
        return True

    def block(statements, scope, function, tail=()):
        for index, statement in enumerate(statements):
            for call in top_calls(statement):
                if not api(call, CONTROLS):
                    continue
                present = False
                for following in [*statements[index + 1 :], *tail]:
                    candidates = list(top_calls(following))
                    if any(tip(candidate) or helper(candidate, scope) for candidate in candidates):
                        present = True
                        break
                    if not transparent(following):
                        break
                label = ast.unparse(call.args[0]) if call.args else "<unlabelled>"
                anchor = f"{scope + '.' if scope else ''}{function}/{_dotted(call.func).split('.')[-1]}({label})"
                occurrences[anchor] += 1
                if not present:
                    findings.append(
                        Finding(
                            path,
                            f"{anchor}[{occurrences[anchor]}]",
                            "control-tooltip",
                            "Follow this control with set_item_tooltip or its local tooltip helper.",
                            call.lineno,
                        )
                    )
            if isinstance(statement, ast.ClassDef):
                block(statement.body, statement.name, "<class>")
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                block(statement.body, scope, statement.name)
            else:
                for field in ("body", "orelse", "finalbody"):
                    children = getattr(statement, field, None)
                    if isinstance(children, list):
                        # A tip after an if/else describes the last item drawn
                        # by either branch. A tip after a loop only describes
                        # its final iteration, so never inherit that tail.
                        branch_tail = (
                            [*statements[index + 1 :], *tail]
                            if isinstance(statement, ast.If)
                            else ()
                        )
                        block(children, scope, function, branch_tail)
                for handler in getattr(statement, "handlers", []):
                    block(handler.body, scope, function)
                for case in getattr(statement, "cases", []):
                    block(case.body, scope, function)

    block(tree.body, "", "<module>")
    return findings


def audit_translation_python(text: str, path: str) -> list[Finding]:
    """Report bare visible literals at declared emtk text sinks without importing a GUI.

    Parameters
    ----------
    text : str
        Authored Python source.
    path : str
        Repository-relative source identity.

    Returns
    -------
    list[Finding]
        Literal locations or an actionable parse error. Wrapped expressions and
        dynamic values are outside this static literal contract.
    """
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        return [Finding(path, "/", "invalid-python", str(exc), exc.lineno)]
    sinks = {
        "text",
        "text_wrapped",
        "text_disabled",
        "button",
        "checkbox",
        "selectable",
        "set_item_tooltip",
    }
    namespaces = {"im", "emtk.im"}
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "emtk.im":
                    namespaces.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if node.module == "emtk" and alias.name == "im":
                    namespaces.add(alias.asname or alias.name)
                elif node.module == "emtk.im":
                    imported[alias.asname or alias.name] = alias.name
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        prefix, _, method = name.rpartition(".")
        if name in imported:
            method = imported[name]
        elif prefix not in namespaces:
            continue
        values = []
        if method in sinks and node.args:
            values.append(("arg0", node.args[0]))
        if method == "input_text":
            values.extend(("hint", kw.value) for kw in node.keywords if kw.arg == "hint")
        for position, value in values:
            if (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and not value.value.startswith("##")
                and any(character.isalpha() for character in value.value)
            ):
                findings.append(
                    Finding(
                        path,
                        f"call@{node.lineno}:{node.col_offset}/{position}",
                        "untranslated-literal",
                        value.value,
                        node.lineno,
                    )
                )
    return findings


def _included(path: str) -> bool:
    """Exclude copied builds, tests and scaffolds from shipped-source coverage."""
    parts = Path(path).parts
    return not any(
        part in SKIP_PARTS or "cookiecutter" in part or "{{" in part for part in parts
    ) and not Path(path).name.startswith("test_")


def _kind(path: str, contract: str = "tooltip") -> str | None:
    """Select view declarations and the imperative GUI trees required by the contract."""
    if not _included(path):
        return None
    if (
        contract == "translation"
        and path.endswith(".py")
        and (
            path.startswith("chisurf/emtk/")
            or path.startswith("chisurf/plugins/")
            or path.startswith("modules/ndxplorer/ndxplorer/")
        )
    ):
        return "python"
    if path.endswith("view.json"):
        return "json"
    if path.endswith(".py") and (
        path.startswith("chisurf/emtk/")
        or path.startswith("modules/ndxplorer/ndxplorer/")
        or (path.startswith("chisurf/plugins/") and "gui" in Path(path).parts)
    ):
        return "python"
    return None


def audit_tree(
    root: Path = ROOT, *, revision: str | None = None, contract: str = "tooltip"
) -> dict:
    """Measure committed bytes separately from the live tree, recording companion identities."""
    if contract not in {"tooltip", "translation"}:
        raise ValueError(f"Unknown UI contract: {contract}")
    sources = {}
    owners = {}

    def repository(folder, prefix, ref):
        owners[prefix or "."] = subprocess.check_output(
            ["git", "rev-parse", ref], cwd=folder, text=True
        ).strip()
        entries = subprocess.check_output(["git", "ls-tree", "-rz", ref], cwd=folder).split(b"\0")
        blobs = []
        for entry in entries:
            if not entry:
                continue
            meta, name = entry.decode().split("\t", 1)
            mode, _, object_id = meta.split()
            path = f"{prefix}/{name}" if prefix else name
            kind = _kind(path, contract)
            if mode == "160000" and path == "modules/ndxplorer":
                repository(root / path, path, object_id)
            elif mode == "120000" and path == "modules/chimol" and (root / path).exists():
                repository(root / path, path, "HEAD")
            elif kind and mode in {"100644", "100755"}:
                blobs.append((path, kind, object_id))
        if blobs:
            data = subprocess.check_output(
                ["git", "cat-file", "--batch"],
                cwd=folder,
                input="".join(f"{object_id}\n" for _, _, object_id in blobs).encode(),
            )
            offset = 0
            for path, kind, _ in blobs:
                end = data.index(b"\n", offset)
                _, object_type, size = data[offset:end].decode().split()
                if object_type != "blob":
                    raise ValueError(f"Expected source blob for {path}, received {object_type}.")
                offset = end + 1
                stop = offset + int(size)
                sources[path] = (kind, data[offset:stop].decode())
                offset = stop + 1

    if revision is not None:
        repository(root, "", revision)
    else:
        for base in ("chisurf", "modules"):
            folder = root / base
            if folder.exists():
                for path in folder.rglob("*"):
                    relative = str(path.relative_to(root))
                    kind = _kind(relative, contract)
                    if kind and path.is_file():
                        sources[relative] = (kind, path.read_text())
        # pathlib does not descend module symlinks as part of root.rglob.
        for prefix in ("modules/chimol", "modules/ndxplorer"):
            folder = root / prefix
            if folder.exists():
                for path in folder.rglob("*"):
                    kind = _kind(f"{prefix}/{path.relative_to(folder)}", contract)
                    if kind and path.is_file():
                        sources[f"{prefix}/{path.relative_to(folder)}"] = (kind, path.read_text())
    if contract == "translation":
        sources = {path: item for path, item in sources.items() if item[0] == "python"}
    findings = []
    digest = hashlib.sha256()
    for path, (kind, source) in sorted(sources.items()):
        digest.update(path.encode() + b"\0" + hashlib.sha256(source.encode()).digest())
        if contract == "translation":
            findings.extend(audit_translation_python(source, path))
        else:
            findings.extend(
                audit_json(source, path) if kind == "json" else audit_python(source, path)
            )
    return {
        "revision": revision or "working-tree",
        "owners": owners,
        "source_digest": digest.hexdigest(),
        "files": dict(Counter(kind for kind, _ in sources.values())),
        "counts": dict(Counter(finding.code for finding in findings)),
        "findings": [{**asdict(finding), "key": finding.key} for finding in findings],
    }


def baseline_delta(report: dict, allowed: set[str]) -> tuple[set[str], set[str]]:
    """Return new and stale allowances so the accepted debt can only shrink."""
    actual = {item["key"] for item in report["findings"]}
    return actual - allowed, allowed - actual


def main() -> int:
    """Write a complete audit ledger without creating or expanding allowances."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--revision")
    parser.add_argument("--contract", choices=("tooltip", "translation"), default="tooltip")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_tree(args.root, revision=args.revision, contract=args.contract)
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")
    return int(bool(report["findings"]))


if __name__ == "__main__":
    raise SystemExit(main())
