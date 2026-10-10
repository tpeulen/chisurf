"""Guard: the actions every window shares are drawn through the one vocabulary.

**The rule.** Help, Guide, Sound, Restart, Run, Save, Open, Browse, Export, Copy,
Reset, Cancel, Close and Load example look the same in every ChiSurf emtk app:
one icon, one English source label, one tooltip and one widget kind each,
declared in :data:`chisurf.plugins.emtk_layout.ACTIONS`. The user's report that
started this — "in the game where you guess numbers the sound button looks
different" — was five games drawing Sound as a button, a checkbox and a
light-theme box, and ~90 Help/Guide buttons spelled ``Help``, ``❓ Help``,
``❓  Help``, ``📖 Guide`` and ``🧭 Guide``. Each one looked fine on its own.

So this file fails when

* Python code draws a shared action by hand: an ``im.button`` /
  ``small_button`` / ``checkbox`` / ``selectable`` / ``toggle_button`` whose
  caption (through ``tr()``, concatenation or ``icon_label``) is one of the
  shared actions, a ``button_row`` dict carrying such a ``label``, or a
  ``(caption, self.callback, …)`` row a window loops over. Draw it
  with :func:`~chisurf.plugins.emtk_layout.action_button` /
  :func:`~chisurf.plugins.emtk_layout.sound_toggle` instead;
* a declared ``button_row`` entry in a ``*.view.json`` names a shared action
  with another spelling, without the canonical ``icon``, or — for the actions
  whose tooltip is the same everywhere — with another ``description``.

Compound captions (``Save JSON``, ``Export CSV``, ``Browse IRF…``) are distinct
actions and are not matched. The check is static — no Qt, no plugin imports.

:data:`HELD` names files another work lane owns at the moment, each with the
reason; it may only shrink, and an entry whose file is already clean fails.
The vocabulary and its rationale: ``okf/subsystems/ui-vocabulary.md``.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest

from chisurf.plugins.emtk_layout import ACTIONS

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SOURCE = _ROOT / "chisurf"
#: The helper itself is where the vocabulary is drawn.
_HELPER = _SOURCE / "plugins" / "emtk_layout.py"

#: Caption (normalised: no icon, no ``##id``, no trailing ellipsis, case-folded) -> action key.
SYNONYMS = {
    "help": "help", "tool help": "help", "open help": "help",
    "guide": "guide", "tour": "guide",
    "sound": "sound", "mute": "sound",
    "restart": "restart",
    "run": "run",
    "cancel": "cancel",
    "reset": "reset",
    "save": "save",
    "open": "open",
    "browse": "browse",
    "export": "export",
    "copy": "copy",
    "close": "close",
    "load example": "example", "example": "example", "demo": "example", "load demo": "example",
}

#: Files held by another lane while this vocabulary landed: path -> why it still differs.
HELD = {
    "chisurf/emtk/help_guide.py":
        "held by the help/guide lane; its in-help 'Close' button moves to action_button('close')",
    "chisurf/plugins/core/code_editor/gui/editor_app.py":
        "held by the editor lane; toolbar '📂 Open', '✖ Close', '📋 Copy' move to action_button",
    "chisurf/plugins/core/help/gui/help_app.py":
        "held by the help-browser lane; its 'Copy' small_button moves to action_button('copy')",
    "chisurf/plugins/core/setup/gui/app.py":
        "held by the setup lane; its 'Guide' button moves to action_button('guide')",
    "chisurf/plugins/core/lightpath_simulator/gui/app.py":
        "held by the lightpath lane; its two 'Cancel' buttons move to action_button('cancel')",
    "chisurf/plugins/core/lightpath_simulator/gui/lightpath.view.json":
        "held with lightpath_simulator/gui/app.py by the lightpath lane; Help/Guide/Export entries "
        "take the canonical icon and tooltip",
    "chisurf/plugins/burst/alex_suite/gui/app.py":
        "held by the ALEX audit lane; '❓ Help' x4 and '🧭 Guide' move to action_button",
    "chisurf/plugins/burst/alex_suite/gui/step_apps.py":
        "held by the ALEX audit lane; its 'Demo' button moves to action_button('example')",
    "chisurf/plugins/tttr/ptu_alex_creator/gui/alex_emtk.view.json":
        "held by the ALEX audit lane; its 'Open…' entry takes the canonical icon",
    "chisurf/plugins/tttr/ptu_alex_creator/gui/app.py":
        "held by the ALEX audit lane; its translated Help/Guide button-row dicts move to action_item",
}

_QT_ONLY = re.compile(r"^\s*(from|import) (qtpy|PyQt5|PySide)", re.M)
_KEY = re.compile(r"^[a-z_][a-z0-9_]*$")
_WIDGETS = {"button", "small_button", "checkbox", "selectable", "toggle_button"}
_TR = {"tr", "_tr", "_"}


def normalise(caption: str) -> str:
    """The caption with its icon, ``##id``, trailing ellipsis and case removed."""
    text = caption.split("##", 1)[0].strip()
    text = re.sub(r"^[^\w]+", "", text)
    text = re.sub(r"(\.\.\.|…)$", "", text).strip()
    return text.casefold()


def _literal(node: ast.AST) -> str | None:
    """The visible text of a caption expression, through ``tr()``, ``+``, f-strings and ``icon_label``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call):
        name = getattr(node.func, "id", getattr(node.func, "attr", None))
        if name in _TR and node.args:
            return _literal(node.args[0])
        if name == "icon_label" and len(node.args) == 2:
            text = _literal(node.args[1])
            return None if text is None else f"{_literal(node.args[0]) or ''} {text}"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal(node.left), _literal(node.right)
        if left is not None or right is not None:
            return (left or "") + (right or "")
    if isinstance(node, ast.JoinedStr):
        parts = [v.value for v in node.values if isinstance(v, ast.Constant)]
        return "".join(parts) if parts else None
    return None


def _rel(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(_ROOT))
    except ValueError:
        return path.name


def python_findings(path: pathlib.Path) -> list[str]:
    """Hand-drawn shared actions in one Python file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []
    if _QT_ONLY.search(source) and "emtk" not in source:
        return []  # a legacy Qt surface: not drawn by emtk (see gui-action-vocabulary for its toolbar)
    found = []
    for node in ast.walk(tree):
        caption = None
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in _WIDGETS and node.args):
            caption = _literal(node.args[0])
        elif (isinstance(node, ast.Tuple) and len(node.elts) >= 2
              and isinstance(node.elts[1], (ast.Attribute, ast.Lambda))):
            # (caption, self.callback, tip, key) rows a window loops over to draw its buttons.
            # A row that leads with a key instead is not recognised (the key is often also a
            # tour target, so its spelling must not be forced): such rows are migrated by hand.
            caption = _literal(node.elts[0])
            if caption is not None and _KEY.match(caption):
                caption = None
        elif isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            if "label" in keys and keys & {"tip", "key", "action", "enabled"}:
                caption = _literal(node.values[[getattr(k, "value", None) for k in node.keys].index("label")])
        if caption is not None and normalise(caption) in SYNONYMS:
            action = SYNONYMS[normalise(caption)]
            found.append(f"{_rel(path)}:{node.lineno}: {caption!r} drawn by hand; "
                         f"use action_button({action!r})" if action != "sound" else
                         f"{_rel(path)}:{node.lineno}: {caption!r} drawn by hand; use sound_toggle()")
    return found


def _buttons(node, where=""):
    """Every declared button-row entry of a view spec, with its JSON pointer."""
    if isinstance(node, dict):
        for item_index, item in enumerate(node.get("buttons") or []):
            if isinstance(item, dict):
                yield f"{where}/buttons/{item_index}", item
        for key, value in node.items():
            yield from _buttons(value, f"{where}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _buttons(value, f"{where}/{index}")


def json_findings(path: pathlib.Path) -> list[str]:
    """Declared shared actions with a non-canonical label, icon or fixed tooltip."""
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    found = []
    for pointer, item in _buttons(spec):
        label = item.get("label")
        if not isinstance(label, str) or normalise(label) not in SYNONYMS:
            continue
        if item.get("label_source"):
            continue  # the drawn caption is the model's (a dialog's "No"/"Cancel"), not this action
        action = ACTIONS[SYNONYMS[normalise(label)]]
        where = f"{_rel(path)}#{pointer}"
        if label != action.label:
            found.append(f"{where}: label {label!r}, canonical {action.label!r}")
        if item.get("icon") != action.icon:
            found.append(f"{where}: icon {item.get('icon')!r}, canonical {action.icon!r}")
        description = item.get("description")
        if action.fixed_tooltip and description != action.tooltip:
            found.append(f"{where}: description {description!r}, canonical {action.tooltip!r}")
        elif not description:
            found.append(f"{where}: no description")
    return found


def _shipped(pattern: str):
    for path in sorted(_SOURCE.rglob(pattern)):
        parts = path.relative_to(_ROOT).parts
        if "__pycache__" in parts or any(p in ("test", "tests") for p in parts) or path == _HELPER:
            continue
        if "cookiecutter" in str(path):
            continue
        yield path


def all_findings() -> dict[str, list[str]]:
    """Findings per repository-relative file."""
    result: dict[str, list[str]] = {}
    for path in _shipped("*.py"):
        hits = python_findings(path)
        if hits:
            result[str(path.relative_to(_ROOT))] = hits
    for path in _shipped("*.json"):
        hits = json_findings(path)
        if hits:
            result[str(path.relative_to(_ROOT))] = hits
    return result


def test_shared_actions_are_drawn_through_the_vocabulary():
    """No file outside :data:`HELD` draws a shared action with its own spelling, icon or widget."""
    drift = {path: hits for path, hits in all_findings().items() if path not in HELD}
    assert not drift, "\n".join(hit for hits in drift.values() for hit in hits)


def test_held_files_still_need_their_edit():
    """A held file that has been migrated must leave :data:`HELD` (the list only shrinks)."""
    findings = all_findings()
    stale = [path for path in HELD if path not in findings]
    assert not stale, f"migrated, remove from HELD: {stale}"


@pytest.mark.parametrize("source, expected", [
    ('im.button(tr("❓  Help"))', 1),
    ('im.button("📖 Guide##g")', 1),
    ('im.checkbox(tr("Sound") + "##sound", on)', 1),
    ('im.small_button(icon_label("💾", tr("Save")))', 1),
    ('button_row([{"label": tr("Browse..."), "key": "browse"}])', 1),
    ('im.button(tr("Save JSON")); im.button(tr("Export CSV")); im.text(tr("Help"))', 0),
    ('action_button("help"); sound_toggle(on)', 0),
    ('rows = [("Guide", self.start_guide, tip, "guide")]', 1),
    ('pairs = [("Help", "help"), ("Save", 3)]', 0),
    ('rows = [("Save", lambda: save(), tip)]', 1),
    ('rows = [("guide", self.start_guide)]', 0),
    ('from qtpy import QtWidgets\nQtWidgets.QPushButton("Help"); im.button("Help")', 0),
])
def test_python_scan_sees_hand_drawn_variants(tmp_path, source, expected):
    """The scan catches each variant that shipped, and leaves compound captions and helpers alone."""
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    assert len(python_findings(probe)) == expected


def test_json_scan_checks_label_icon_and_fixed_tooltip(tmp_path):
    """A declared Help must use the canonical label, icon and tooltip; a Save may explain itself."""
    spec = {"sections": [{"type": "button_row", "buttons": [
        {"action": "help", "label": "❓ Help", "description": "Explain this."},
        {"action": "save", "label": "Save", "icon": ACTIONS["save"].icon, "description": "Save the fit."},
        {"action": "export_csv", "label": "Export CSV", "description": "CSV."},
    ]}]}
    probe = tmp_path / "probe.view.json"
    probe.write_text(json.dumps(spec), encoding="utf-8")
    hits = json_findings(probe)
    assert len(hits) == 3 and all("buttons/0" in hit for hit in hits)


def test_every_action_is_complete_and_translatable():
    """Each action has an icon, a label, a tooltip and a known kind, and its text is in the shared catalogue."""
    from chisurf.emtk.shared_i18n import _ROWS

    sources = {row[0] for row in _ROWS}
    for key, action in ACTIONS.items():
        assert action.icon and action.label and action.tooltip, key
        assert action.kind in ("button", "toggle"), key
        assert {action.label, action.tooltip} <= sources, key


def test_icons_are_the_canonical_glyphs():
    """The vocabulary's icons are the registry's glyphs (spelled out only to keep emtk apps Qt-free)."""
    from chisurf.gui.glyphs import Glyphs

    expected = {
        "help": Glyphs.HELP, "guide": Glyphs.BOOK, "sound": Glyphs.SOUND, "restart": Glyphs.RESTART,
        "close": Glyphs.CLOSE, "cancel": Glyphs.CLOSE, "run": Glyphs.RUN, "reset": Glyphs.RESET,
        "save": Glyphs.SAVE, "open": Glyphs.OPEN, "browse": Glyphs.OPEN, "export": Glyphs.EXPORT,
        "copy": Glyphs.COPY, "example": Glyphs.TEST,
    }
    assert {key: action.icon for key, action in ACTIONS.items()} == expected
    from chisurf.plugins.emtk_layout import SOUND_OFF_ICON

    assert SOUND_OFF_ICON == Glyphs.MUTE


def test_vocabulary_module_stays_qt_free():
    """Drawing the vocabulary in an emtk app must not load Qt."""
    import subprocess
    import sys

    code = "import sys, chisurf.plugins.emtk_layout; print('qtpy' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=_ROOT)
    assert out.stdout.strip() == "False", out.stderr
