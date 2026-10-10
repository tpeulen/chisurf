"""Audit that every state change is a navigable, resolvable history row.

Three contracts, each failing on a real defect rather than a fixture artefact:

(a) the action catalogue is consistent: a ``state`` action is replayable, and an
    action that is not replayable is one that changes nothing a snapshot holds
    (``execution`` or ``diagnostic``);
(b) every action-type literal written straight into history via
    ``record_action`` names a registered action, so the history browser and the
    replay projection can resolve it;
(c) with the canonical scientific owner bound, an edit followed by an audit row
    leaves the cursor on a row that can be navigated to.
"""

from __future__ import annotations

import ast
import pathlib

import chisurf as cs

ROOT = pathlib.Path(__file__).resolve().parents[2]

# The modules that call ``record_action`` directly (the audit-row writers).
RECORD_SITES = (
    "chisurf/core/agent/tools/fitting.py",
    "chisurf/macros/core_fit.py",
    "chisurf/macros/core_data.py",
    "chisurf/gui/main.py",
    "chisurf/gui/widgets/fitting/parameter_widgets.py",
    "chisurf/gui/widgets/fitting/fit_controller.py",
    "chisurf/gui/plots/table_plot_emtk.py",
    "chisurf/emtk/datasets.py",
)

NON_STATE_CLASSES = {"execution", "diagnostic"}


def _load_action_modules() -> None:
    """Import the modules whose ``@action`` decorators populate the registry."""
    import chisurf.core.actions  # noqa: F401
    from chisurf.core.actions import (  # noqa: F401
        dataset_actions,
        fit_actions,
        model_actions,
        parameter_actions,
        project_actions,
    )


def test_catalog_state_actions_are_replayable():
    """A ``state`` action must be replayable; a non-replayable one must not be state."""
    _load_action_modules()
    catalog = cs.action_registry.catalog()
    assert catalog, "the action registry is empty"
    bad = []
    for entry in catalog:
        cls = entry["side_effect_class"]
        if cls == "state" and entry["replayable"] is not True:
            bad.append((entry["name"], cls, entry["replayable"]))
        if entry["replayable"] is False and cls not in NON_STATE_CLASSES:
            bad.append((entry["name"], cls, entry["replayable"]))
    assert bad == [], f"inconsistent catalogue entries: {bad}"


def _unwrap(node: ast.AST) -> ast.AST:
    """Strip ``str(...)`` around an action-type expression."""
    while (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
    ):
        node = node.args[0]
    return node


def _action_type_arg(call: ast.Call) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == "action_type":
            return _unwrap(keyword.value)
    if call.args:
        return _unwrap(call.args[0])
    return None


def _callee_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _literals_in(path: pathlib.Path) -> list[tuple[str, int, str]]:
    """Collect action-type literals reaching ``record_action`` in one module.

    A literal at the call is taken directly. A parameter of the enclosing
    function (a ``_record_history(action_type, ...)`` wrapper) is followed to the
    calls of that wrapper in the same module, so the strings the module actually
    records are audited, not only the ones spelled at the call.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    found: list[tuple[str, int, str]] = []
    wrappers: dict[str, tuple[str, int]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _callee_name(node) == "record_action"):
            continue
        arg = _action_type_arg(node)
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            found.append((str(path.relative_to(ROOT)), node.lineno, arg.value))
            continue
        if not isinstance(arg, ast.Name):
            continue
        scope = parents.get(node)
        while scope is not None and not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = parents.get(scope)
        if scope is None:
            continue
        params = [a.arg for a in scope.args.posonlyargs + scope.args.args]
        if arg.id in params:
            index = params.index(arg.id)
            if params and params[0] in {"self", "cls"}:
                index -= 1
            wrappers[scope.name] = (arg.id, index)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee_name(node)
        if name not in wrappers:
            continue
        param, index = wrappers[name]
        value = None
        for keyword in node.keywords:
            if keyword.arg == param:
                value = _unwrap(keyword.value)
        if value is None and 0 <= index < len(node.args):
            value = _unwrap(node.args[index])
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found.append((str(path.relative_to(ROOT)), node.lineno, value.value))
    return found


def test_recorded_action_literals_resolve_to_registered_actions():
    """Every action type written into history names a registered action."""
    _load_action_modules()
    registry = cs.action_registry
    literals = [item for site in RECORD_SITES for item in _literals_in(ROOT / site)]
    assert literals, "no record_action literals found; the AST walk is broken"
    unresolved = [
        (path, line, name)
        for path, line, name in literals
        if not registry.has(registry.resolve_name(name))
    ]
    assert unresolved == [], f"history rows naming no registered action: {unresolved}"


def test_edit_then_audit_row_leaves_a_navigable_cursor(tmp_path):
    """A scientific edit followed by ``fit.run.finish`` keeps the cursor navigable."""
    from test.history.test_history_scientific_owner import scientific_owner

    owner, history, _raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    uid = owner.fits[0].model.parameters_all_dict["a"].unique_identifier

    def edit(session):
        session.fits[0].model.parameters_all_dict["a"].value = 5.0

    history.apply_edit(edit, "parameter.value", "set a", target_uid=uid, persist=False)
    assert history.can_navigate(history.cursor_index())
    history.record("fit.run.finish", "fit finished", persist=False)
    assert history.can_navigate(history.cursor_index())
    # Undo to the baseline and redo through both rows.
    assert history.navigate(-1)["ok"] is True
    assert history.can_navigate(history.cursor_index())
    assert history.navigate(1)["ok"] is True
    assert owner.fits[0].model.parameters_all_dict["a"].value == 5.0
