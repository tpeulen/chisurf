"""Native tours are checked through real controls without fabricating awaits."""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from build_tools.dev_utils import check_plugin_guide as checker


def test_native_discovery_never_imports_factory(tmp_path, monkeypatch):
    """A native-only manifest with a sibling tour is found without importing it."""
    folder = tmp_path / "chisurf/plugins/example/gui"
    folder.mkdir(parents=True)
    (folder / "app.py").write_text("raise RuntimeError('must not import')\n")
    (folder / "guide.json").write_text('{"steps": []}')
    (folder.parent / "manifest.json").write_text(json.dumps({
        "id": "example", "version": "1", "entrypoints": {
            "emtk": "chisurf.plugins.example.gui.app:make_app"}}))
    monkeypatch.setattr(checker, "_ROOT", tmp_path)
    assert checker._emtk_plugins_with_tours(live=True) == ["example"]


def native_app(steps, *, wired=True, notify=True):
    """Build a small actual immediate-mode app with an awaited demo control."""
    from emtk import im
    from emtk.app import ImApp

    from chisurf.emtk.help_guide import EmTkGuidedTour

    class Example(ImApp):
        def __init__(self):
            super().__init__(self.render)
            self.item_rects = {}
            self.loads = 0
            self.help_window = SimpleNamespace(sections=[("Help", ["Real help content"])])
            self.tour = EmTkGuidedTour(steps, self.item_rects.get, owner=self,
                                      wait_for_controls=wired)

        def render(self):
            vp = im.get_main_viewport()
            im.set_next_window_pos(vp.pos)
            im.set_next_window_size(vp.size)
            if im.begin("Example"):
                if im.button("Load example"):
                    self.loads += 1
                    if notify:
                        self.tour.notify_used("load_example")
                self.item_rects["load_example"] = im.get_item_rect()
                im.text("Measured data" if self.loads else "No data")
                self.item_rects["result"] = im.get_item_rect()
            im.end()
            self.tour.draw(*vp.size)
    return Example()


def run_native(monkeypatch, tmp_path, app):
    """Inject an app while retaining the actual SDK driver and screenshots."""
    monkeypatch.setattr(checker, "_load_native", lambda plugin, **kwargs: app)
    ok = checker.check_emtk("example", tmp_path, (700, 500))
    return ok, json.loads((tmp_path / "report.json").read_text())


def test_real_demo_click_releases_await(monkeypatch, tmp_path):
    """Only an actual control event may prove an opted-in await was satisfied."""
    app = native_app([{"title": "Load data", "target": {"name": "load_example"},
                       "await": {"hint": "Press Load example"}},
                      {"title": "Inspect", "target": {"name": "result"}}])
    ok, report = run_native(monkeypatch, tmp_path, app)
    assert ok and app.loads == 1
    assert report["steps"][0]["await_status"] == "fulfilled"
    assert report["steps"][0]["clicked"]
    assert (tmp_path / "step_01.png").read_bytes().startswith(b"\x89PNG")


@pytest.mark.parametrize("wired,status", [(True, "pending"), (False, "unwired")])
def test_other_await_is_not_faked(monkeypatch, tmp_path, wired, status):
    """An external or user action stays open even when its target is visible."""
    app = native_app([{"title": "Inspect result", "target": {"name": "result"},
                       "await": {"hint": "Use result"}}], wired=wired)
    ok, report = run_native(monkeypatch, tmp_path, app)
    assert not ok and report["steps"][0]["await_status"] == status
    assert not app.tour._step_used and app.loads == 0


def test_absent_target_fails(monkeypatch, tmp_path):
    """A tour card centred over the app is not evidence that its target exists."""
    app = native_app([{"title": "Missing", "target": {"name": "absent"}}])
    ok, report = run_native(monkeypatch, tmp_path, app)
    assert not ok and report["steps"][0]["target_status"] == "missing"


def test_missing_tour_fails_without_deep_model_search(monkeypatch, tmp_path):
    """Unrelated nested model tours must not hide a missing surface tour."""
    app = native_app([])
    app.model = SimpleNamespace(tour=native_app([]).tour)
    del app.tour
    # Render must not use the deleted tour; checking missing metadata precedes drawing.
    ok, report = run_native(monkeypatch, tmp_path, app)
    assert not ok and "missing-tour" in report["errors"]


def test_long_card_is_reported(monkeypatch, tmp_path):
    """Reaching the hard card cap with excess content remains a failure."""
    app = native_app([{"title": "Long", "text": "long words " * 300}])
    ok, report = run_native(monkeypatch, tmp_path, app)
    assert not ok and report["steps"][0]["truncated"]


def test_timeout_report_is_complete_and_next_tool_continues(monkeypatch, tmp_path):
    """An isolated tool timeout does not truncate the aggregate run ledger."""
    calls = []
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"], output="partial output")
        from pathlib import Path
        (Path(cmd[3]) / "report.json").write_text('{"ok": true}')
        return SimpleNamespace(returncode=0, stdout="OK   second\n", stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    result = checker._run_isolated([("native", "first"), ("native", "second")],
                                   tmp_path, (700, 500), timeout=3)
    assert len(result) == 2 and result[0]["status"] == "timeout"
    assert result[1]["status"] == "passed"
    assert all(row["report"] for row in result)
    assert calls[0][1]["env"]["QT_QPA_PLATFORM"] == "offscreen"
    assert calls[0][1]["env"]["CHISURF_SETTINGS_DIR"] != calls[1][1]["env"]["CHISURF_SETTINGS_DIR"]


def test_malformed_manifest_is_not_silently_dropped(tmp_path, monkeypatch):
    """A broken native manifest invalidates discovery rather than vanishing."""
    folder = tmp_path / "chisurf/plugins/broken"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("{not json")
    monkeypatch.setattr(checker, "_ROOT", tmp_path)
    with pytest.raises(json.JSONDecodeError):
        checker._native_plugins(live=True)


def test_hidden_cached_owner_target_fails(monkeypatch, tmp_path):
    """A previous frame's child rectangle cannot count as a visible target."""
    app = native_app([{"title": "Hidden", "target": {"name": "old"}}])
    app.tool = SimpleNamespace(item_rects={"old": (20, 20, 40, 20)})
    app.tour.get_target_rect = app.tool.item_rects.get
    ok, report = run_native(monkeypatch, tmp_path, app)
    assert not ok and report["steps"][0]["target_status"] == "missing"


def test_demo_click_with_no_await_remains_distinct(monkeypatch, tmp_path):
    """A demo can load while an authored step still declares no action wait."""
    app = native_app([{"title": "Load", "target": {"name": "load_example"}}])
    ok, report = run_native(monkeypatch, tmp_path, app)
    assert ok and app.loads == 1
    assert report["steps"][0]["await_status"] == "none"


def test_missing_help_fails(monkeypatch, tmp_path):
    """An empty help object cannot prove the shipped help resource exists."""
    app = native_app([{"title": "Inspect", "target": {"name": "result"}}])
    app.help_window.sections = []
    ok, report = run_native(monkeypatch, tmp_path, app)
    assert not ok and "missing-help" in report["errors"]


def test_demo_click_without_use_notification_stays_pending(monkeypatch, tmp_path):
    """Pressing a button alone cannot prove that the authored await is wired."""
    app = native_app([{"title": "Load", "target": {"name": "load_example"},
                       "await": True}], notify=False)
    ok, report = run_native(monkeypatch, tmp_path, app)
    assert not ok and app.loads == 1 and report["steps"][0]["clicked"]
    assert report["steps"][0]["await_status"] == "pending"


def test_native_zero_exit_without_report_does_not_pass(monkeypatch, tmp_path):
    """A subprocess crash workaround or missing child report is not verification."""
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="", stderr=""))
    rows = checker._run_isolated([("native", "example")], tmp_path, (700, 500), 3)
    assert rows[0]["status"] == "failed"
    assert "Missing native report" in rows[0]["error"]


def test_release_discovery_ignores_foreign_manifests_and_missing_live_resources(tmp_path, monkeypatch):
    """HEAD declarations survive dirty replacement and exclude untracked ports."""
    folder = tmp_path / "chisurf/plugins/example/gui"
    folder.mkdir(parents=True)
    (folder / "app.py").write_text("raise RuntimeError('not imported')\n")
    (folder / "guide.json").write_text('{"steps": []}')
    manifest = folder.parent / "manifest.json"
    manifest.write_text(json.dumps({"id": "release", "version": "1", "entrypoints": {
        "emtk": "chisurf.plugins.example.gui.app:make_app"}}))
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "chisurf/plugins/example"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=tpeulen",
                    "-c", "user.email=fixture@example.invalid", "commit", "-qm",
                    "Create committed discovery fixture"], check=True)
    manifest.write_text(manifest.read_text().replace('"release"', '"foreign"'))
    (folder / "guide.json").unlink()
    new = tmp_path / "chisurf/plugins/untracked"
    new.mkdir()
    (new / "manifest.json").write_text(json.dumps({"id": "untracked", "version": "1",
        "entrypoints": {"emtk": "chisurf.plugins.untracked.app:make_app"}}))
    monkeypatch.setattr(checker, "_ROOT", tmp_path)
    assert checker._native_plugins() == ["release"]
    assert checker._emtk_plugins_with_tours() == ["release"]
    assert checker._native_plugins(live=True) == ["foreign", "untracked"]
    assert checker._emtk_plugins_with_tours(live=True) == []
