import time

from emtk.testing import RecordingPainter


def test_sweep_reports_real_child_success_and_missing_native_ports():
    from chisurf.plugins.core.plugin_check.gui.model import PluginCheckModel

    model = PluginCheckModel({
        "about": {"id": "about", "entrypoints": {"emtk": "chisurf.plugins.core.about.gui.app:make_app"}},
        "pending": {"id": "pending", "entrypoints": {"gui": "missing:Tool"}},
    })
    model.delay = 0
    assert model.start()
    assert not model.start()
    deadline = time.monotonic() + 20
    while model.running and time.monotonic() < deadline:
        model.poll()
        time.sleep(0.01)
    assert not model.running
    assert model.results["about"]["status"] == "pass"
    assert model.results["pending"]["status"] == "pending"
    assert model.current == 2
    model.close()


def test_checker_lists_metadata_and_renders_native_docks():
    from chisurf.plugins.core.plugin_check.gui.app import PluginCheckApp
    from chisurf.plugins.core.plugin_check.gui.model import PluginCheckModel

    model = PluginCheckModel({"demo": {"id": "demo", "display_name": "Demo", "version": "1",
        "requires": {"base": ">=1"}, "description": "Demo metadata", "entrypoints": {}}})
    painter = RecordingPainter()
    app = PluginCheckApp(model)
    app.draw(painter, 0, 0, 1200, 800)
    assert "Test all plugins" in painter.strings
    assert "Demo metadata" in painter.strings
    assert "base: >=1" in painter.strings
    app.close()


def test_checker_failure_blacklist_and_stop_are_observable(monkeypatch):
    from chisurf.plugins.core.plugin_check.gui.model import PluginCheckModel

    model = PluginCheckModel({"bad": {"entrypoints": {"emtk": "bad:make_app"}}})
    model.delay = 0
    monkeypatch.setattr(model, "_check", lambda factory, timeout: {"status": "fail", "error": "Failure"})
    for _ in range(5):
        model.start()
        model._thread.join(2)
        model.poll()
    assert "bad" in model.blacklisted
    model.start()
    model._thread.join(2)
    model.poll()
    assert model.results["bad"]["status"] == "skipped"
    model.close()


def test_stop_terminates_a_current_slow_constructor(tmp_path, monkeypatch):
    import os

    from chisurf.plugins.core.plugin_check.gui.model import PluginCheckModel

    (tmp_path / "slow_native.py").write_text("import time\ndef make_app():\n    time.sleep(30)\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    model = PluginCheckModel({"slow": {"entrypoints": {"emtk": "slow_native:make_app"}}})
    model.delay = 0
    model.start()
    deadline = time.monotonic() + 5
    while model._process is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert model._process is not None
    process = model._process
    model.stop()
    model._thread.join(4)
    model.poll()
    assert not model.running
    assert process.poll() is not None
    assert model.message == "Cancelled"


def test_success_resets_consecutive_failure_count():
    from chisurf.plugins.core.plugin_check.gui.model import PluginCheckModel

    model = PluginCheckModel({})
    model.failures["retry"] = 4
    model._events.put(("retry", {"status": "pass"}))
    model.poll()
    model._events.put(("retry", {"status": "fail"}))
    model.poll()
    assert model.failures["retry"] == 1
    assert "retry" not in model.blacklisted
