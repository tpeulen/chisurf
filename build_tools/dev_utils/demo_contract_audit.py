"""Measure authored demo API and tour contracts without importing plugin GUIs."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_tools.dev_utils.ui_contract_audit import Finding, _included  # noqa: E402


def _attribute(node, name):
    """Identify a named object method without importing GUI dependencies."""
    return isinstance(node, ast.Attribute) and node.attr == name


def _is_button(node):
    """Recognise a drawn button: ``<x>.button(...)`` or the shared ``action_button("example", ...)``."""
    if not isinstance(node, ast.Call):
        return False
    if _attribute(node.func, "button"):
        return True
    return (
        isinstance(node.func, ast.Name)
        and node.func.id == "action_button"
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "example"
    )


def _rectangle_key(node):
    """Return the authored key of an actual item rectangle registration."""
    if not isinstance(node, ast.Assign) or not (
        isinstance(node.value, ast.Call) and _attribute(node.value.func, "get_item_rect")
    ):
        return None
    for target in node.targets:
        if isinstance(target, ast.Subscript) and _attribute(target.value, "item_rects"):
            return target.slice
    return None


#: The card base whose ``toolbar(rows)`` is ``button_row(rows, remember=self.remember)``.
CARD_SHELL = "chisurf.emtk.card_shell.CardShell"


def _card_toolbar_class(tree, scope):
    """Whether ``self.toolbar`` of *scope* is :data:`CARD_SHELL`'s remembered button row.

    True for a class that names the card base directly and overrides neither ``toolbar``
    nor ``remember``, so a toolbar row's ``key`` is the rectangle the tour points at.
    """
    if not isinstance(scope, ast.ClassDef):
        return False
    imports = {
        alias.asname or alias.name: f"{node.module}.{alias.name}"
        for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 0
        for alias in node.names
    }
    if not any(isinstance(base, ast.Name) and imports.get(base.id) == CARD_SHELL for base in scope.bases):
        return False
    return not any(
        isinstance(node, ast.FunctionDef) and node.name in {"toolbar", "remember"} for node in scope.body
    )


def _tour_target_class(tree, scope, registration_sources, seen=None):
    """Follow authored imports to the shared rectangle mixin, without executing them."""
    seen = set() if seen is None else seen
    imports = {
        alias.asname or alias.name: f"{node.module}.{alias.name}"
        for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 0
        for alias in node.names
    }
    for base in scope.bases:
        if not isinstance(base, ast.Name):
            continue
        qualified = imports.get(base.id)
        if qualified == "chisurf.emtk.help_guide.TourTarget":
            return not any(
                isinstance(node, ast.FunctionDef) and node.name == "remember" for node in scope.body
            )
        if not qualified or qualified in seen:
            continue
        seen.add(qualified)
        module, name = qualified.rsplit(".", 1)
        source = registration_sources.get(module.replace(".", "/") + ".py")
        if source is None:
            continue
        try:
            parent_tree = ast.parse(source)
        except SyntaxError:
            continue
        parent = next(
            (node for node in parent_tree.body if isinstance(node, ast.ClassDef) and node.name == name),
            None,
        )
        if parent is not None and _tour_target_class(parent_tree, parent, registration_sources, seen):
            return not any(
                isinstance(node, ast.FunctionDef) and node.name == "remember" for node in scope.body
            )
    return False


def _imperative_control(tree, registration_sources):
    """Prove direct buttons or tuple-driven button helpers register the real action.

    This deliberately recognizes a small set of authored draw patterns. Callback
    names and notifications alone do not establish that a user can press a control.
    """
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.ClassDef)):
            continue
        methods = {node.name: node for node in scope.body if isinstance(node, ast.FunctionDef)}
        shared_remember = isinstance(scope, ast.ClassDef) and _tour_target_class(
            tree, scope, registration_sources
        )
        card_toolbar = _card_toolbar_class(tree, scope)
        for function in methods.values() if isinstance(scope, ast.ClassDef) else [scope]:
            nodes = list(ast.walk(function))
            has_button = any(_is_button(node) for node in nodes)
            literal_rectangle = any(
                isinstance(key := _rectangle_key(node), ast.Constant)
                and key.value == "load_example"
                for node in nodes
            )
            remembered_rectangle = shared_remember and any(
                isinstance(node, ast.Call) and _attribute(node.func, "remember")
                and len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "load_example" for node in nodes
            )
            direct_callback = any(
                isinstance(node, ast.If)
                and any(_is_button(call) for call in ast.walk(node.test))
                and any(
                    isinstance(call, ast.Call) and _attribute(call.func, "load_example")
                    for statement in node.body
                    for call in ast.walk(statement)
                )
                for node in nodes
            )
            if has_button and (literal_rectangle or remembered_rectangle) and direct_callback:
                return True
            button_row_names = {
                alias.asname or alias.name for node in tree.body
                if isinstance(node, ast.ImportFrom)
                and node.module == "chisurf.plugins.emtk_layout" and node.level == 0
                for alias in node.names if alias.name == "button_row"
            }
            for assignment in nodes:
                if not isinstance(assignment, ast.Assign):
                    continue
                call = assignment.value
                remembered_row = shared_remember and (
                    isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id in button_row_names and call.args
                    and any(keyword.arg == "remember" and _attribute(keyword.value, "remember")
                            for keyword in call.keywords)
                )
                card_row = card_toolbar and (
                    isinstance(call, ast.Call) and _attribute(call.func, "toolbar")
                    and isinstance(call.func.value, ast.Name) and call.func.value.id == "self"
                    and call.args
                )
                if not (remembered_row or card_row):
                    continue
                declared_key = any(
                    isinstance(node, ast.Dict)
                    and any(isinstance(key, ast.Constant) and key.value == "key"
                            and isinstance(value, ast.Constant) and value.value == "load_example"
                            for key, value in zip(node.keys, node.values))
                    for node in ast.walk(call.args[0])
                )
                result_names = {target.id for target in assignment.targets if isinstance(target, ast.Name)}
                callback = any(
                    isinstance(branch, ast.If)
                    and any(isinstance(node, ast.Name) and node.id in result_names
                            for node in ast.walk(branch.test))
                    and any(isinstance(node, ast.Constant) and node.value == "load_example"
                            for node in ast.walk(branch.test))
                    and any(isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Attribute)
                            and node.func.attr in {"load_example", "on_demo"}
                            for statement in branch.body for node in ast.walk(statement))
                    for branch in nodes
                )
                # A dispatch table indexed by the pressed key: ``{..., "load_example": self.load_example}[pressed]()``.
                dispatched = any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Subscript)
                    and isinstance(node.func.value, ast.Dict)
                    and isinstance(node.func.slice, ast.Name)
                    and node.func.slice.id in result_names
                    and any(
                        isinstance(key, ast.Constant) and key.value == "load_example"
                        and _attribute(value, "load_example")
                        for key, value in zip(node.func.value.keys, node.func.value.values)
                    )
                    for node in nodes
                )
                if declared_key and (callback or dispatched):
                    return True
            for loop in nodes:
                if not isinstance(loop, ast.For) or not isinstance(loop.target, ast.Tuple):
                    continue
                if not isinstance(loop.iter, (ast.Tuple, ast.List)):
                    continue
                names = [item.id if isinstance(item, ast.Name) else None for item in loop.target.elts]
                for row in loop.iter.elts:
                    if not isinstance(row, (ast.Tuple, ast.List)) or len(row.elts) != len(names):
                        continue
                    keys = [
                        names[i]
                        for i, value in enumerate(row.elts)
                        if isinstance(value, ast.Constant) and value.value == "load_example"
                    ]
                    callbacks = [
                        names[i] for i, value in enumerate(row.elts)
                        if _attribute(value, "load_example")
                    ]
                    for branch in ast.walk(loop):
                        if not isinstance(branch, ast.If) or not isinstance(branch.test, ast.Call):
                            continue
                        call = branch.test
                        if not isinstance(call.func, ast.Attribute) or call.func.attr not in methods:
                            continue
                        helper = methods[call.func.attr]
                        parameters = [arg.arg for arg in helper.args.args if arg.arg != "self"]
                        mapped_keys = {
                            parameter for parameter, argument in zip(parameters, call.args)
                            if isinstance(argument, ast.Name) and argument.id in keys
                        }
                        registrations = {
                            key.id for node in ast.walk(helper)
                            if isinstance(key := _rectangle_key(node), ast.Name)
                        }
                        helper_button = any(
                            isinstance(node, ast.Call) and _attribute(node.func, "button")
                            for node in ast.walk(helper)
                        )
                        invokes_callback = any(
                            isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Name)
                            and node.func.id in callbacks
                            for statement in branch.body for node in ast.walk(statement)
                        )
                        if helper_button and mapped_keys & registrations and invokes_callback:
                            return True
    return False


def audit_demo(source: str, guide, view, path: str, *, control_sources=None, registration_sources=None) -> list[Finding]:
    """Check configuration, cache API shape and the declared first example action.

    Parameters
    ----------
    source : str
        Producer Python source, parsed without executing it.
    guide, view : object
        Authored tour and form declarations; runtime delivery is checked separately.
    path : str
        Repository-relative producer identity.
    control_sources : dict[str, str], optional
        Owned imperative GUI sources used to prove a drawn example control.
    registration_sources : dict[str, str], optional
        Shared authored base classes used only to trace TourTarget inheritance.

    Returns
    -------
    list[Finding]
        Missing or malformed contracts, retaining source identity for repair.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [Finding(path, "/", "invalid-python", str(exc), exc.lineno)]
    findings = []

    def missing(code, detail):
        findings.append(Finding(path, "/", code, detail))

    configured = False
    functions = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "DEMO" for target in targets):
                configured = isinstance(node.value, ast.Dict) or (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "dict"
                )
    if not configured:
        missing("demo-configuration", "Declare DEMO cache parameters.")
    if "demo_folder" not in functions or isinstance(functions["demo_folder"], ast.AsyncFunctionDef):
        missing("demo-folder", "Expose demo_folder() for the settings/demos/plugin cache.")
    producer = functions.get("make_demo")
    if producer is None or isinstance(producer, ast.AsyncFunctionDef):
        missing("demo-producer", "Expose make_demo(folder=None, *, overwrite=False).")
    else:
        args = producer.args
        positional = [*args.posonlyargs, *args.args]
        if not positional or positional[0].arg != "folder":
            missing("demo-folder-argument", "The first positional argument must be folder.")
        if (
            not positional
            or len(args.defaults) != len(positional)
            or not (isinstance(args.defaults[0], ast.Constant) and args.defaults[0].value is None)
        ):
            missing("demo-optional-folder", "Omitted folder must select the declared cache.")
        names = [arg.arg for arg in args.kwonlyargs]
        if "overwrite" not in names or not (
            isinstance(args.kw_defaults[names.index("overwrite")], ast.Constant)
            and args.kw_defaults[names.index("overwrite")].value is False
        ):
            missing("demo-overwrite", "Provide keyword-only overwrite=False.")
    steps = guide.get("steps", []) if isinstance(guide, dict) else guide
    if not isinstance(steps, list) or len(steps) <= 1:
        missing("demo-tour-target", "Tour step index 1 must teach load_example.")
        missing("demo-tour-await", "The example step must wait for its actual control.")
    else:
        step = steps[1]
        target = step.get("target", {}) if isinstance(step, dict) else {}
        name = (
            target
            if isinstance(target, str)
            else next(
                (target[key] for key in ("name", "action", "attr", "key") if target.get(key)), ""
            )
            if isinstance(target, dict)
            else ""
        )
        if name != "load_example":
            missing("demo-tour-target", "Tour step index 1 must target load_example.")
        if not isinstance(step, dict) or not step.get("await"):
            missing("demo-tour-await", "The example step must wait for its actual control.")
    controls = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("action") == "load_example":
                controls.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(view)
    imperative = False
    for name, text in (control_sources or {}).items():
        try:
            control_tree = ast.parse(text, filename=name)
        except SyntaxError as exc:
            findings.append(Finding(name, "/", "invalid-python", str(exc), exc.lineno))
        else:
            imperative |= _imperative_control(control_tree, registration_sources or {})
    if not controls and not imperative:
        missing("demo-control", "Declare load_example in a view or register its actual drawn control.")
    return findings


def _teaches_the_example(text):
    """Whether a tour's step index 1 points at ``load_example`` (the tour a demo belongs to)."""
    try:
        guide = json.loads(text)
    except (ValueError, TypeError):
        return False
    steps = guide.get("steps", []) if isinstance(guide, dict) else guide
    if not isinstance(steps, list) or len(steps) <= 1 or not isinstance(steps[1], dict):
        return False
    target = steps[1].get("target", {})
    if isinstance(target, str):
        return target == "load_example"
    return isinstance(target, dict) and "load_example" in {
        target.get(key) for key in ("name", "action", "attr", "key")
    }


def audit_tree(root: Path = ROOT, *, revision: str | None = "HEAD") -> dict:
    """Read committed producer/resource bytes, keeping local prototypes diagnostic only."""
    sources = {}
    if revision is None:
        for path in (root / "chisurf/plugins").rglob("*"):
            relative = path.relative_to(root).as_posix()
            if path.is_file() and _included(relative) and path.suffix in {".py", ".json"}:
                sources[relative] = path.read_text()
        identity = "working-tree"
    else:
        identity = subprocess.check_output(
            ["git", "rev-parse", revision], cwd=root, text=True
        ).strip()
        entries = subprocess.check_output(
            ["git", "ls-tree", "-rz", revision, "--", "chisurf/plugins"], cwd=root
        ).split(b"\0")
        blobs = []
        for entry in entries:
            if not entry:
                continue
            meta, name = entry.decode().split("\t", 1)
            mode, kind, object_id = meta.split()
            if (
                mode in {"100644", "100755"}
                and kind == "blob"
                and _included(name)
                and Path(name).suffix in {".py", ".json"}
            ):
                blobs.append((name, object_id))
        data = subprocess.check_output(
            ["git", "cat-file", "--batch"],
            cwd=root,
            input="".join(f"{object_id}\n" for _, object_id in blobs).encode(),
        )
        offset = 0
        for name, _ in blobs:
            end = data.index(b"\n", offset)
            header = data[offset:end].decode().split()
            if len(header) != 3 or header[1] != "blob":
                raise ValueError(f"Cannot read demo source {name}")
            start = end + 1
            stop = start + int(header[2])
            sources[name] = data[start:stop].decode()
            offset = stop + 1
    findings = []
    records = []
    manifests = {Path(name).parent for name in sources if Path(name).name == "manifest.json"}

    def owner(name):
        """Resolve the closest authored plugin boundary for each resource."""
        return next((parent for parent in Path(name).parents if parent in manifests), None)

    for path, source in sorted(sources.items()):
        if Path(path).name != "demo.py":
            continue
        parent = Path(path).parent.as_posix()
        plugin = owner(path)
        owned = {
            name: text for name, text in sources.items()
            if owner(name) == plugin and name.startswith(parent + "/")
        }
        # A plugin that hosts several tools keeps each tool's tour beside its resources
        # (``gui/resources/<tool>/guide.json``); the demo is taught by one of them.
        guides = [
            (name, text)
            for name, text in sorted(owned.items())
            if (
                Path(name).parent.as_posix() in {parent, parent + "/gui"}
                or Path(name).parent.parent.as_posix() == parent + "/gui/resources"
            )
            and "guide" in Path(name).name
            and name.endswith(".json")
        ]
        guides.sort(key=lambda item: not _teaches_the_example(item[1]))
        views = [
            (name, text)
            for name, text in sorted(owned.items())
            if name.endswith("view.json")
        ]
        invalid = []

        def parse_resource(name, text):
            """Retain resource identity when malformed JSON cannot be audited."""
            try:
                return json.loads(text)
            except (ValueError, TypeError) as exc:
                invalid.append(Finding(name, "/", "invalid-json", str(exc)))
                return None

        parsed_guides = [parse_resource(name, text) for name, text in guides]
        view = [parse_resource(name, text) for name, text in views]
        control_sources = {
            name: text for name, text in owned.items()
            if name.endswith(".py") and "gui" in Path(name).parts
        }
        result = invalid + audit_demo(
            source, parsed_guides[0] if parsed_guides else [], view, path,
            control_sources=control_sources, registration_sources=sources,
        )
        findings.extend(result)
        records.append(
            {
                "path": path,
                "guide": guides[0][0] if guides else None,
                "views": [name for name, _ in views],
                "controls": sorted(control_sources),
                "findings": len(result),
            }
        )
    return {
        "revision": identity,
        "demos": records,
        "counts": dict(Counter(f.code for f in findings)),
        "findings": [{**asdict(f), "key": f.key} for f in findings],
    }


def main() -> int:
    """Write a complete worklist without introducing a release allowance."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_tree(args.root, revision=None if args.live else args.revision)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
    return int(bool(report["findings"]))


if __name__ == "__main__":
    raise SystemExit(main())
