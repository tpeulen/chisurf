"""Known burst examples, effective cache parameters and real native tour actions."""

import hashlib
import json
from concurrent.futures import CancelledError
from pathlib import Path

import pytest


def test_eb_demo_cache_checks_effective_seed_and_every_member(tmp_path, monkeypatch):
    """A parameter mismatch or damaged bytes regenerates the stacked raw input."""
    from chisurf.plugins.burst.burst_ebfret import demo

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert demo.demo_folder() == tmp_path / "demos" / "burst_ebfret"
    path = demo.make_demo()
    data, modified = path.read_bytes(), path.stat().st_mtime_ns
    assert json.loads(path.with_suffix(".json").read_text()) == demo.DEMO
    assert demo.make_demo() == path
    assert path.read_bytes() == data and path.stat().st_mtime_ns == modified
    path.write_bytes(data[:-10])
    assert demo.make_demo() == path
    assert path.read_bytes() == data
    assert demo.make_demo(seed=4) == path
    assert path.read_bytes() != data
    assert json.loads(path.with_suffix(".json").read_text())["seed"] == 4
    assert demo.make_demo(overwrite=True) == path
    assert path.read_bytes() == data


def test_eb_failed_writer_preserves_the_previous_complete_cache(tmp_path, monkeypatch):
    """Regenerating a sample cannot replace a good file with a partial writer output."""
    from chisurf.plugins.burst.burst_ebfret import demo

    path = demo.make_demo(tmp_path)
    original = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}

    def fail(path, *_args, **_kwargs):
        Path(path).write_bytes(b"partial")
        raise OSError("failed simulation writer")

    monkeypatch.setattr(demo.np, "savetxt", fail)
    with pytest.raises(OSError, match="failed simulation writer"):
        demo.make_demo(tmp_path, overwrite=True)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == original
    assert demo._cache_is_good(path, demo.DEMO)


@pytest.mark.parametrize("damage", ("raw", "bur", "reading", "seed", "search", "overwrite"))
def test_fusion_cache_requires_configuration_and_complete_measurement(
    tmp_path, monkeypatch, damage
):
    """The physical stream, BUR and reading manifest all belong to one declared search."""
    from chisurf.plugins.burst.burst_fusion import demo

    settings = {"n_molecules": 30, "duration_s": 2.0}
    folder = demo.make_demo(tmp_path, settings=settings)
    before = demo.read_demo(folder)
    source = Path(before["source"])
    raw = source.read_bytes()
    modified = source.stat().st_mtime_ns
    assert demo.make_demo(tmp_path, settings=settings) == folder
    assert source.stat().st_mtime_ns == modified
    bur = folder / "bi4_bur" / (demo.DEMO_STEM + ".bur")
    bur_data = bur.read_bytes()
    if damage == "raw":
        source.write_bytes(raw[: len(raw) // 2])
    elif damage == "bur":
        bur.unlink()
    elif damage == "reading":
        (folder / "Info" / "analysis.json").unlink()
    elif damage == "seed":
        settings["seed"] = 7
    elif damage == "search":
        monkeypatch.setitem(demo.SEARCH, "min_photons", 120)
    assert demo.make_demo(tmp_path, overwrite=damage == "overwrite", settings=settings) == folder
    after = demo.read_demo(folder)
    assert demo._cache_is_good(tmp_path, {**demo.DEMO, **settings}, demo.SEARCH)
    assert after["parameters"] == {**demo.DEMO, **settings}
    assert after["search"] == demo.SEARCH
    if damage == "seed":
        assert source.read_bytes() != raw
    else:
        assert source.read_bytes() == raw
    if damage == "search":
        assert bur.read_bytes() != bur_data
    elif damage != "seed":
        assert after["bursts"] == before["bursts"], (
            "Regeneration must not append duplicate BUR rows"
        )


@pytest.mark.parametrize("failure", ("writer", "search", "cancel"))
def test_fusion_regeneration_failure_retains_previous_complete_cache(
    tmp_path, monkeypatch, failure
):
    """Writer/search failure and cooperative cancellation restore all prior cache bytes."""
    from chisurf.plugins.burst.burst_fusion import demo

    settings = {"n_molecules": 30, "duration_s": 2.0}
    folder = demo.make_demo(tmp_path, settings=settings)
    original = {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }

    def fail_writer(_stream, path, _settings):
        path.write_bytes(b"partial")
        raise OSError("writer failed")

    def fail_search(*_args):
        raise OSError("search failed")

    def cancel(fraction, _message):
        if fraction >= 0.75:
            raise CancelledError()

    if failure == "writer":
        monkeypatch.setattr(demo, "_write_tttr", fail_writer)
    elif failure == "search":
        monkeypatch.setattr(demo, "_run_burst_search", fail_search)
    with pytest.raises(CancelledError if failure == "cancel" else OSError):
        demo.make_demo(
            tmp_path,
            settings=settings,
            overwrite=True,
            progress=cancel if failure == "cancel" else None,
        )
    assert {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    } == original
    assert demo._cache_is_good(tmp_path, {**demo.DEMO, **settings}, demo.SEARCH)
    assert folder.is_dir()


def test_fusion_default_primary_and_settings_folder(tmp_path, monkeypatch):
    """The primary input is the ordinary searched analysis folder, not a metadata dict."""
    from chisurf.plugins.burst.burst_fusion import demo

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert demo.demo_folder() == tmp_path / "demos" / "burst_fusion"
    folder = demo.make_demo()
    assert isinstance(folder, Path)
    assert folder.parent == demo.demo_folder()
    record = demo.read_demo(folder)
    assert record["truth"]["n_molecules"] == 300
    assert record["bursts"] == 428
    assert hashlib.sha256(Path(record["source"]).read_bytes()).hexdigest()


def test_native_eb_example_waits_for_real_click_without_starting_fit(tmp_path, monkeypatch):
    """The new declared toolbar loads the real input and releases its highlighted await."""
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtTest, QtWidgets

    from chisurf.plugins.burst.burst_ebfret.gui.app import make_app

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app = make_app()
    host = ControlHost(app)
    host.resize(1200, 800)
    host.show()

    def frame():
        for _ in range(3):
            host.repaint()
            qapp.processEvents()

    try:
        frame()
        assert "load_example" in app.item_rects
        assert app.tour.steps[1]["target"] == {"name": "load_example"}
        app.tour.start(1)
        frame()
        assert app.tour.awaiting and not app.gui.has_data
        x, y, w, h = app.item_rects["load_example"]
        QtTest.QTest.mouseClick(
            host,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            QtCore.QPoint(int(x + w / 2), int(y + h / 2)),
        )
        frame()
        assert app.gui.has_data and not app.tour.awaiting
        assert not app.gui.running
        assert app.gui.view["n_series"] == 40
        assert all(
            app.tour.get_target_rect(step["target"]["name"]) is not None
            for step in app.tour.steps
            if step.get("target", {}).get("name")
        )
    finally:
        host.close()
        app.gui.client.close()


def test_native_fusion_example_waits_for_real_user_action(tmp_path, monkeypatch):
    """Demo loads a searched measurement; estimating recurrence remains a separate action."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_fusion.gui.app import create_app

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    app = create_app()
    driver = Driver(app, (1200, 800))
    try:
        driver.frame(3)
        tour = app.fusion_gui.tour
        tour.start(1)
        driver.frame(3)
        assert tour.awaiting and not app.model.folder
        driver.click("load_example")
        app.controller._future.result(timeout=30)
        app.controller.poll()
        driver.frame(3)
        assert not tour.awaiting
        assert app.model.demo["bursts"] == 428
        assert app.model._analysis is None
    finally:
        app.close()
