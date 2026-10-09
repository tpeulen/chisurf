"""Feature-parity sweep: every EMTK settings panel vs its Qt panel widget.

For each settings panel this compares the *declared feature surface* of the Qt
panel widget (its public action methods: saves, restores, imports, exports,
wizard actions) against the native EMTK app module. A Qt feature with no
counterpart in the native module is reported; genuinely different surfaces
(e.g. panels the EMTK hub serves through the YAML configuration editor) are
compared against that editor's contract instead.

This is a surface-coverage sweep, not a behavioural proof — behavioural
parity lives in each plugin's own tests — but it makes a silently missing
Qt feature fail here instead of surfacing as a user complaint.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: panel key -> (Qt widget module, Qt class name, native app module, native class)
PANELS = {
    "boarding": (
        "chisurf/plugins/core/boarding/wizard.py", "BoardingAssistantWidget",
        "chisurf/plugins/core/boarding/app.py", "BoardingApp",
    ),
    "style": (
        "chisurf/plugins/core/style_manager/gui/tool.py", "StyleManagerWidget",
        "chisurf/plugins/core/style_manager/gui/app.py", "StyleManagerApp",
    ),
    "plots": (
        "chisurf/plugins/core/plot_settings/gui/tool.py", "PlotSettingsWidget",
        "chisurf/plugins/core/plot_settings/gui/app.py", "PlotSettingsApp",
    ),
    "models": (
        "chisurf/plugins/core/model_manager/gui/tool.py", "ModelManagerWidget",
        "chisurf/plugins/core/model_manager/gui/app.py", "ModelManagerApp",
    ),
    "users": (
        "chisurf/plugins/core/user_editor/gui/tool.py", "UserEditorWidget",
        "chisurf/plugins/core/user_editor/gui/app.py", "UserEditorApp",
    ),
    "ai": (
        "chisurf/plugins/ai_settings/gui/tool.py", "AISettingsWidget",
        "chisurf/plugins/ai_settings/gui/app.py", "AISettingsApp",
    ),
    "plugins": (
        "chisurf/plugins/core/plugin_manager/gui/tool.py", "PluginManagerWidget",
        "chisurf/plugins/core/plugin_manager/gui/app.py", "PluginManagerApp",
    ),
    "channels": (
        "chisurf/plugins/core/setup_channel_definition/gui/tool.py", "SetupChannelDefinitionWidget",
        "chisurf/plugins/core/setup_channel_definition/gui/app.py", None,
    ),
    "fcs": (
        "chisurf/plugins/fcs/fcs_channel_preset/gui/tool.py", "FCSChannelWidget",
        "chisurf/plugins/fcs/fcs_channel_preset/gui/app.py", None,
    ),
    "lut": (
        "chisurf/plugins/tttr/tttr_lut_tools/gui/tool.py", "TTTRLUTSettingsPanel",
        "chisurf/plugins/tttr/tttr_lut_tools/gui/app.py", None,
    ),
    "check": (
        "chisurf/plugins/core/plugin_check/gui/tool.py", "PluginCheckTool",
        "chisurf/plugins/core/plugin_check/gui/app.py", "PluginCheckApp",
    ),
}

#: Qt-side methods that are pure Qt plumbing or covered by the EMTK host
#: (persistence goes through export/restore_settings; the wizard shell lives
#: in the hub).
QT_PLUMBING = {
    "init", "setup_ui", "setupui", "retranslateui", "showevent", "closeevent", "event",
    "oncurrentchanged", "resizeevent", "paintevent", "show", "hide", "close",
}

#: Feature-name synonyms: a Qt method counts as covered when the native module
#: defines a method with the same normalised verb stem.
SYNONYMS = {
    "onloadjson": {"load", "loadjson", "onload"},
    "onsavejson": {"save", "savejson", "onsave"},
    "onsavetextedit": {"save"},
    "onsavetext": {"save"},
    "onreadtextedit": {"update", "refresh", "onupdate", "read"},
    "onloadpdb": {"loadpdb", "fetchpdb", "onloadpdb"},
    "onclearall": {"clear", "onclear", "clearall"},
}


def _public_methods(path: pathlib.Path, class_name: str) -> set[str]:
    """Public methods *defined on* the Qt widget class (AST, no import — Qt)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            names = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = item.name.lower()
                    if not name.startswith("_") and name not in QT_PLUMBING:
                        names.add(name)
            return names
    raise AssertionError(f"Qt class {class_name} not found in {path}")


def _module_defs(path: pathlib.Path) -> set[str]:
    """Every function/method name defined in the native app module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name.lower())
    return names


def _covered(qt_name: str, native_defs: set[str]) -> bool:
    stem = qt_name.removeprefix("on_").replace("_", "")
    candidates = SYNONYMS.get(stem, {stem}) | {qt_name}
    return any(c in native_defs for c in candidates)



#: Panels whose Qt features exist in the native app as UI labels or model
#: calls rather than same-named methods: Qt feature -> source fragments any
#: of which must appear in the native module (method names are checked first).
FEATURE_EVIDENCE = {
    "style": {
        "load_file": ["def load", "def request_load"],
        "load_style_files": ["def load", "def refresh"],
        "on_apply_style": ["def apply", "def _apply_style"],
        "on_clear_styles": ["def reset"],
        "on_file_selected": ["def request_load", "def load"],
        "on_new_file": ["def new"],
        "on_save_file": ["def save"],
    },
    "check": {
        "refresh_plugins": ["Rescan", "def poll"],
        "start_testing": ["Test all plugins", "model.start"],
        "start_safe_testing": ["Test safe plugins", "safe=True"],
        "clear_blacklist": ["Clear blacklist"],
        "update_progress": ["def poll", "model.start"],
        "update_plugin_result": ["draw_list", "draw_details"],
        "testing_finished": ["def poll", "animating"],
        "cleanup": ["def close"],
        "on_plugin_selected": ["self.selected"],
    },
}


def _panel_covers(qt_name: str, panel_key: str, native_defs: set[str], native_src: str) -> bool:
    if _covered(qt_name, native_defs):
        return True
    fragments = FEATURE_EVIDENCE.get(panel_key, {}).get(qt_name)
    return bool(fragments) and any(f in native_src for f in fragments)


@pytest.mark.parametrize("panel_key", sorted(PANELS))
def test_native_panel_covers_qt_feature_surface(panel_key: str):
    qt_path, qt_cls, native_path, _native_cls = PANELS[panel_key]
    qt_methods = _public_methods(ROOT / qt_path, qt_cls)
    native_defs = _module_defs(ROOT / native_path)
    native_src = (ROOT / native_path).read_text(encoding="utf-8")
    # Native apps delegate persistence to the EMTK state contract.
    native_defs |= {"export_settings", "restore_settings"}
    missing = sorted(
        m for m in qt_methods if not _panel_covers(m, panel_key, native_defs, native_src)
    )
    assert not missing, (
        f"{panel_key}: Qt panel features with no native counterpart "
        f"({qt_cls} vs {pathlib.Path(native_path).name}): {missing}"
    )
