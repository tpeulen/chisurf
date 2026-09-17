"""Plugin manager: the logic, and then that the panel actually builds.

The old file asserted three attribute *names* existed on the widget and nothing
else, so every real defect passed it -- a rename that corrupted source files, a
"Hide Disabled" that hid nothing, a startup ``KeyError``, an icon import that had
never resolved. These tests go at the behaviour instead, and almost all of them
need no display, because the behaviour now lives outside the widget.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from chisurf.plugins.core.plugin_manager.api import install as installer
from chisurf.plugins.core.plugin_manager.api.records import (
    collect_rows,
    read_module_docstring,
)
from chisurf.plugins.core.plugin_manager.api.settings_io import PluginSettings


def _record(**overrides):
    """A discovery record with sensible defaults."""
    record = {
        "manifest_id": "alpha",
        "manifest_version": "1.0.0",
        "plugin_name": "Tools:Alpha",
        "description": "Alpha tool.",
        "module_path": "chisurf.plugins.alpha",
        "package_dir": "/tmp/alpha",
        "source": "built-in",
        "requires": {},
        "optional_requires": {},
    }
    record.update(overrides)
    return record


# ── rows ────────────────────────────────────────────────────────────────


def test_rows_carry_the_dependency_graph_in_both_directions():
    """The reverse index is the point: who breaks if this is switched off."""
    rows = collect_rows(
        [
            _record(manifest_id="lib", plugin_name="Lib"),
            _record(manifest_id="a", plugin_name="A", requires={"lib": "*"}),
            _record(manifest_id="b", plugin_name="B", requires={"lib": "*"}),
            _record(manifest_id="c", plugin_name="C", optional_requires={"lib": "*"}),
        ]
    )
    by_id = {row.plugin_id: row for row in rows}
    assert by_id["lib"].required_by == ["a", "b"]
    assert by_id["lib"].optional_for == ["c"]
    assert by_id["a"].requires == {"lib": "*"}


def test_disabling_reports_exactly_what_breaks():
    """An optional dependant is not broken by disabling; a hard one is."""
    rows = collect_rows(
        [
            _record(manifest_id="lib", plugin_name="Lib"),
            _record(manifest_id="a", plugin_name="A", requires={"lib": "*"}),
            _record(manifest_id="c", plugin_name="C", optional_requires={"lib": "*"}),
        ]
    )
    lib = next(r for r in rows if r.plugin_id == "lib")
    assert lib.blocking_dependants(disabled=[]) == ["a"]
    # A dependant that is itself off cannot break.
    assert lib.blocking_dependants(disabled=["a"]) == []


def test_a_disabled_plugin_is_matched_by_its_legacy_display_name():
    """Settings written before ids were used must still be honoured.

    ``disabled_plugins`` has historically held display names, so a plugin that
    gained a manifest id would otherwise silently come back on.
    """
    rows = collect_rows([_record()], disabled=["Tools:Alpha"])
    assert rows[0].disabled
    rows = collect_rows([_record()], disabled=["Alpha"])
    assert rows[0].disabled
    rows = collect_rows([_record()], disabled=["alpha"])
    assert rows[0].disabled


def test_status_names_what_a_plugin_is():
    rows = collect_rows(
        [
            _record(manifest_id="lib", library=True),
            _record(manifest_id="cli", cli_only=True),
            _record(manifest_id="exp", experimental=True),
            _record(manifest_id="dep", deprecated=True),
        ]
    )
    status = {row.plugin_id: row.status_text() for row in rows}
    assert status == {
        "lib": "library",
        "cli": "cli only",
        "exp": "experimental",
        "dep": "deprecated",
    }


def test_statefulness_summary_respects_the_global_mode():
    """The old summary ignored the mode and always claimed "plugin default"."""
    rows = collect_rows([_record()], statefulness={"mode": "disabled"})
    assert rows[0].statefulness == "stateless (all)"
    rows = collect_rows([_record()], statefulness={"per_plugin": {"alpha": True}})
    assert rows[0].statefulness == "stateful"


def test_read_module_docstring_survives_an_unreadable_package(tmp_path):
    assert read_module_docstring(tmp_path) == ""
    (tmp_path / "__init__.py").write_text('"""Hello."""\n')
    assert read_module_docstring(tmp_path) == "Hello."


# ── settings ────────────────────────────────────────────────────────────


def test_edits_do_not_touch_the_live_settings_until_applied():
    """The old manager mutated the live lists by reference, before Save."""
    live = {"disabled_plugins": ["keep"], "other": "untouched"}
    settings = PluginSettings(live)
    settings.set_disabled("alpha", True)

    assert live["disabled_plugins"] == ["keep"], "live settings changed before apply()"
    assert settings.dirty

    settings.apply(live)
    assert set(live["disabled_plugins"]) == {"keep", "alpha"}
    assert live["other"] == "untouched", "apply() rewrote a key it does not own"
    assert not settings.dirty


def test_enabling_clears_every_alias():
    """A legacy display-name entry must go too, or the plugin re-disables."""
    settings = PluginSettings({"disabled_plugins": ["Tools:Alpha", "alpha"]})
    settings.set_disabled("alpha", False, aliases=["Tools:Alpha"])
    assert settings.disabled == []


def test_revert_discards_everything():
    settings = PluginSettings({"disabled_plugins": []})
    settings.set_disabled("alpha", True)
    settings.set_toolbar("beta", True)
    assert settings.dirty
    settings.revert()
    assert not settings.dirty
    assert settings.disabled == [] and settings.toolbar == []


def test_move_renumbers_the_whole_sequence():
    """The old move set neighbour±1 and let the integers drift apart."""
    settings = PluginSettings({})
    order = ["a", "b", "c", "d"]
    settings.move("c", order, -1)
    assert settings.order == {"a": 0, "c": 1, "b": 2, "d": 3}
    # every weight distinct and contiguous
    assert sorted(settings.order.values()) == [0, 1, 2, 3]


def test_move_at_the_edges_does_nothing():
    settings = PluginSettings({})
    settings.move("a", ["a", "b"], -1)
    assert settings.order == {}
    settings.move("b", ["a", "b"], +1)
    assert settings.order == {}


# ── install ─────────────────────────────────────────────────────────────


def _plugin_tree(root, name="demo_plugin", manifest=True):
    tree = root / name
    tree.mkdir(parents=True)
    (tree / "__init__.py").write_text('"""Demo."""\nname = "Tools:Demo"\n')
    if manifest:
        (tree / "manifest.json").write_text(
            json.dumps({"id": name, "version": "1.0.0", "display_name": "Tools:Demo"})
        )
    return tree


def test_a_folder_without_an_init_is_refused(tmp_path):
    (tmp_path / "not_a_plugin").mkdir()
    plan = installer.inspect_source(tmp_path / "not_a_plugin")
    assert not plan.ok
    assert "no __init__.py" in plan.problems[0]


def test_an_invalid_manifest_is_refused_before_anything_is_copied(tmp_path):
    tree = _plugin_tree(tmp_path, manifest=False)
    (tree / "manifest.json").write_text(json.dumps({"id": "demo"}))  # no version
    plan = installer.inspect_source(tree)
    assert not plan.ok
    assert "manifest.json is invalid" in plan.problems[0]


def test_a_plugin_without_a_manifest_installs_with_a_warning(tmp_path):
    tree = _plugin_tree(tmp_path, manifest=False)
    plan = installer.inspect_source(tree)
    assert plan.ok
    assert any("no manifest.json" in w for w in plan.warnings)


def test_an_archive_that_escapes_its_destination_is_refused(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../escaped.py", "pwned = True")
    plan = installer.inspect_source(archive)
    assert not plan.ok
    assert "escapes the destination" in plan.problems[0]


def test_a_zip_is_installable(tmp_path, monkeypatch):
    tree = _plugin_tree(tmp_path / "src")
    archive = tmp_path / "demo.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in tree.rglob("*"):
            zf.write(path, path.relative_to(tree.parent).as_posix())

    destination_root = tmp_path / "user_plugins"
    destination_root.mkdir()
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: destination_root)

    plan = installer.inspect_source(archive)
    assert plan.ok, plan.problems
    assert plan.plugin_name == "demo_plugin"

    installed = installer.install(plan)
    assert (installed / "__init__.py").is_file()
    assert (installed / "manifest.json").is_file()


def test_uninstall_refuses_a_builtin(tmp_path, monkeypatch):
    """Built-in plugins ship with the app; deleting one is not a user action."""
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: tmp_path / "user")
    (tmp_path / "user").mkdir()
    builtin = tmp_path / "builtin" / "thing"
    builtin.mkdir(parents=True)
    with pytest.raises(ValueError, match="user plugin directory"):
        installer.uninstall(builtin)
    assert builtin.exists(), "a refused uninstall must not delete anything"


# ── the view model ──────────────────────────────────────────────────────


def test_view_model_hides_disabled_plugins_when_asked():
    """The old 'Hide Disabled' checkbox set a flag that nothing ever read."""
    from chisurf.plugins.core.plugin_manager.gui.view_model import PluginManagerViewModel

    model = PluginManagerViewModel(settings_block={"disabled_plugins": []})
    model._rows = collect_rows(
        [
            _record(manifest_id="on", plugin_name="On"),
            _record(manifest_id="off", plugin_name="Off"),
        ],
        disabled=["off"],
    )

    model.show_disabled = False
    assert [r.plugin_id for r in model.visible_rows()] == ["on"]
    model.show_disabled = True
    assert len(model.visible_rows()) == 2


def test_view_model_details_name_the_dependants():
    from chisurf.plugins.core.plugin_manager.gui.view_model import PluginManagerViewModel

    model = PluginManagerViewModel(settings_block={})
    model._rows = collect_rows(
        [
            _record(manifest_id="lib", plugin_name="Lib"),
            _record(manifest_id="a", plugin_name="A", requires={"lib": "*"}),
        ]
    )
    model.select_row({"id": "lib"})
    text = model.details_text()
    assert "Required by" in text and "`a`" in text

    relations = {row["relation"] for row in model.dependency_rows()}
    assert relations == {"required by"}


def test_view_model_marks_a_missing_dependency():
    from chisurf.plugins.core.plugin_manager.gui.view_model import PluginManagerViewModel

    model = PluginManagerViewModel(settings_block={})
    model._rows = collect_rows([_record(manifest_id="a", requires={"ghost": "*"})])
    model.select_row({"id": "a"})
    row = model.dependency_rows()[0]
    assert row["plugin"] == "ghost" and row["status"] == "missing"


def _model_with_manifest(tmp_path, display_name="Tools:Alpha"):
    """A view model over one plugin backed by a real manifest on disk."""
    from chisurf.plugins.core.plugin_manager.gui.view_model import PluginManagerViewModel

    (tmp_path / "manifest.json").write_text(
        json.dumps({"id": "alpha", "version": "1.0.0", "display_name": display_name})
    )
    model = PluginManagerViewModel(settings_block={})
    model._rows = collect_rows([_record(package_dir=str(tmp_path))])
    model.select_row({"id": "alpha"})
    return model


def test_rename_edits_the_manifest_and_keeps_the_menu_path(tmp_path, monkeypatch):
    """The old rename regexed __init__.py and never touched the manifest.

    Discovery reads ``manifest.display_name``, so editing anything else was a
    no-op that still rewrote source.
    """
    model = _model_with_manifest(tmp_path)
    monkeypatch.setattr(model, "reload", lambda **_kw: None)

    assert model.rename_selected("Beta") == ""
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert data["display_name"] == "Tools:Beta", "menu path was not preserved"
    assert data["id"] == "alpha", "rename must not change the id"


def test_rename_leaves_the_source_file_alone(tmp_path, monkeypatch):
    """The corrupting half of the old rename: it rewrote __init__.py."""
    source = tmp_path / "__init__.py"
    original = 'name = "Tools:Alpha"\ndisplay_name = "Tools:Alpha"\n'
    source.write_text(original)
    model = _model_with_manifest(tmp_path)
    monkeypatch.setattr(model, "reload", lambda **_kw: None)

    model.rename_selected("Beta")
    assert source.read_text() == original, "rename edited the plugin source"


@pytest.mark.parametrize(
    "name, why",
    [("", "an empty name"), ("   ", "whitespace only"), ("A:B", "a menu path")],
)
def test_rename_refuses_bad_names(tmp_path, monkeypatch, name, why):
    model = _model_with_manifest(tmp_path)
    monkeypatch.setattr(model, "reload", lambda **_kw: None)
    assert model.rename_selected(name), f"accepted {why}"


def test_rename_without_a_manifest_says_so(tmp_path, monkeypatch):
    from chisurf.plugins.core.plugin_manager.gui.view_model import PluginManagerViewModel

    model = PluginManagerViewModel(settings_block={})
    model._rows = collect_rows([_record(package_dir=str(tmp_path))])
    model.select_row({"id": "alpha"})
    monkeypatch.setattr(model, "reload", lambda **_kw: None)
    assert "no manifest.json" in model.rename_selected("Beta")


# ── the panel ───────────────────────────────────────────────────────────


def test_the_view_spec_matches_the_schema():
    """A misspelled key in the view spec is a silently dropped control."""
    from chisurf.core.dataspec.schema import validate_view_spec
    from chisurf.plugins.core.plugin_manager.gui.view_model import _VIEW_JSON

    assert validate_view_spec(json.loads(_VIEW_JSON.read_text())) == []


def test_every_bound_attribute_exists_on_the_model():
    """A view spec naming an attribute the model lacks renders a dead control."""
    from chisurf.plugins.core.plugin_manager.gui.view_model import (
        _VIEW_JSON,
        PluginManagerViewModel,
    )

    model = PluginManagerViewModel(settings_block={})
    spec = json.loads(_VIEW_JSON.read_text())

    missing = []

    def walk(section):
        for key in ("attr", "source", "options_source", "selected_call"):
            target = section.get(key)
            if target and not hasattr(model, target):
                missing.append(f"{section.get('type')}.{key} -> {target}")
        for name in ("source", "selected_call"):
            target = (section.get("options") or {}).get(name)
            if target and not hasattr(model, target):
                missing.append(f"custom.{name} -> {target}")
        for child in section.get("sections", []):
            walk(child)

    for section in spec["sections"]:
        walk(section)
    assert not missing, "view spec binds to attributes the model does not have:\n  " + "\n  ".join(
        missing
    )


def test_plugin_manager_widget_creation(qapp, qtbot):
    """The panel builds, and shows every plugin discovery found."""
    from chisurf.plugins.core.plugin_manager import PluginManagerWidget

    widget = PluginManagerWidget()
    qtbot.addWidget(widget)
    assert "Plugin" in widget.windowTitle()
    assert widget.model.rows, "no plugins reached the panel"
    # the table source and the model agree
    assert len(widget.model.plugin_rows()) == len(widget.model.visible_rows())
