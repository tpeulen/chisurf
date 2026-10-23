"""Canonical cached photon demos retain scientific inputs and wait for real user actions."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import pytest

MODULES = (
    "chisurf.plugins.fcs.fcs_correlator.demo",
    "chisurf.plugins.burst.burst_fcs_correlator.demo",
)


@pytest.fixture(autouse=True)
def scratch_settings(tmp_path, monkeypatch):
    """Keep generated photon data and application state inside the test directory."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "database.sqlite"))


@pytest.mark.parametrize("module_name", MODULES)
def test_demo_primary_path_cache_and_explicit_overwrite(module_name, tmp_path, monkeypatch):
    """A matching cache is reused, explicit overwrite regenerates only declared members."""
    module = importlib.import_module(module_name)
    assert module.demo_folder() == tmp_path / "settings" / "demos" / module_name.split(".")[-2]
    path = module.make_demo()
    assert isinstance(path, Path) and path.is_file()
    # the burst demo's primary member is the .pto container (photons inside)
    assert path.name == (
        module.CONTAINER_NAME if hasattr(module, "CONTAINER_NAME")
        else module.TABLE_NAME if hasattr(module, "TABLE_NAME")
        else module.SPC_FILENAME
    )
    directory = path.parent
    originals = {name: (directory / name).read_bytes() for name in module.MEMBERS}
    record = json.loads((directory / "demo.json").read_text())
    assert record["parameters"] == module.DEMO
    assert record["sha256"] == {
        name: hashlib.sha256(data).hexdigest() for name, data in originals.items()
    }
    saved = module.photon_stream
    monkeypatch.setattr(
        module, "photon_stream", lambda *a, **k: pytest.fail("valid cache regenerated")
    )
    assert module.make_demo() == path
    monkeypatch.setattr(module, "photon_stream", saved)
    unrelated = directory / "measurement-not-part-of-demo.txt"
    unrelated.write_text("owned by the user")
    module.make_demo(overwrite=True)
    if hasattr(module, "CONTAINER_NAME"):
        # a container carries identity fields (ids, times) beside the data: the
        # regenerated member is checked as a whole, not byte against byte
        assert (directory / module.CONTAINER_NAME).is_file()
    else:
        assert originals == {name: (directory / name).read_bytes() for name in module.MEMBERS}
    assert unrelated.read_text() == "owned by the user"
    assert not list(directory.glob(".demo-*"))


@pytest.mark.parametrize("module_name", MODULES)
def test_demo_cache_rejects_changed_parameters_missing_and_corrupted_members(
    module_name, tmp_path, monkeypatch
):
    """Cache identity covers effective physical parameters and every emitted data member."""
    module = importlib.import_module(module_name)
    path = module.make_demo(tmp_path / "demo")
    primary = path if hasattr(module, "CONTAINER_NAME") else path.parent / module.SPC_FILENAME
    original = primary.read_bytes()
    monkeypatch.setitem(module.DEMO, "seed", module.DEMO["seed"] + 1)
    module.make_demo(path.parent)
    assert primary.read_bytes() != original
    monkeypatch.setitem(module.DEMO, "seed", module.DEMO["seed"] - 1)
    module.make_demo(path.parent)
    if not hasattr(module, "CONTAINER_NAME"):
        assert primary.read_bytes() == original
    for name in module.MEMBERS:
        member = path.parent / name
        correct = member.read_bytes()
        member.write_bytes(b"corrupt")
        module.make_demo(path.parent)
        if hasattr(module, "CONTAINER_NAME"):
            assert member.read_bytes() != b"corrupt" and member.is_file()
        else:
            assert member.read_bytes() == correct
        member.unlink()
        module.make_demo(path.parent)
        if hasattr(module, "CONTAINER_NAME"):
            assert member.is_file()
        else:
            assert member.read_bytes() == correct
    (path.parent / "demo.json").write_text("malformed")
    module.make_demo(path.parent)
    assert json.loads((path.parent / "demo.json").read_text())["parameters"] == module.DEMO


@pytest.mark.parametrize("module_name", MODULES)
def test_failed_regeneration_preserves_previous_demo(module_name, tmp_path, monkeypatch):
    """A failed writer leaves the previous files and sidecar usable."""
    import tttrlib

    module = importlib.import_module(module_name)
    path = module.make_demo(tmp_path / "demo")
    before = {name: (path.parent / name).read_bytes() for name in (*module.MEMBERS, "demo.json")}
    monkeypatch.setattr(tttrlib.TTTR, "write", lambda *args, **kwargs: False)
    with pytest.raises(OSError):
        module.make_demo(path.parent, overwrite=True)
    assert before == {name: (path.parent / name).read_bytes() for name in before}
    assert not list(path.parent.glob(".demo-*"))


@pytest.mark.parametrize("module_name", MODULES)
def test_demo_physical_events_match_declared_generator(module_name, tmp_path):
    """Both cached files carry the original ordered micro/macro times and detector routing."""
    import tttrlib

    module = importlib.import_module(module_name)
    path = module.make_demo(tmp_path / "demo")
    expected = module.photon_stream(module.DEMO["seed"])
    if hasattr(module, "CONTAINER_NAME"):
        from chisurf.core.fio.staging import open_tttr

        stream = open_tttr(path, None)  # the photons live inside the container
    else:
        stream = tttrlib.TTTR(str(path.parent / module.SPC_FILENAME))
    for getter, values in zip(
        ("get_macro_times", "get_micro_times", "get_routing_channel"), expected[:3]
    ):
        np.testing.assert_array_equal(getattr(stream, getter)(), values)
    assert stream.header.macro_time_resolution == pytest.approx(module.DEMO["macro_resolution_s"])
    assert stream.header.micro_time_resolution == pytest.approx(module.DEMO["micro_resolution_s"])
    if hasattr(module, "TABLE_NAME"):
        assert path.read_text() == "".join(f"{first} {last}\n" for first, last in expected[3])


@pytest.mark.parametrize("burst", (False, True), ids=("FCS", "burst-FCS"))
def test_load_example_tour_awaits_actual_button_release(burst):
    """The canonical second step points at the delivered action, which does not auto-analyse."""
    if burst:
        from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app
        from chisurf.plugins.burst.burst_fcs_correlator.test.driving import BurstDriver

        app = create_app()
        driver = BurstDriver(app)

        def get_paths():
            return app.controller.files
    else:
        from chisurf.plugins.fcs.fcs_correlator.gui.app import make_app
        from chisurf.plugins.fcs.fcs_correlator.test.test_emtk_workflow import Hub

        app = make_app()
        driver = Hub(app)

        def get_paths():
            return app.files_step.checked_files

    try:
        app.tour.start(1)
        driver.draw(3)
        step = app.tour.steps[1]
        assert step["target"] == {"name": "load_example"} and step["await"]
        assert app.tour.awaiting and not get_paths()
        box = driver.rect("load_example")
        app.pointer_move(box[0] + box[2] / 2, box[1] + box[3] / 2)
        driver.draw(1)
        app.press(box[0] + box[2] / 2, box[1] + box[3] / 2)
        driver.draw(1)
        assert app.tour.awaiting and not get_paths()
        app.release()
        driver.draw(3)
        assert not app.tour.awaiting and len(get_paths()) == 1
        if burst:
            assert not app.controller.running and not app.controller._curves
        else:
            assert app.selected == "files"
    finally:
        app.close()


def test_elided_demo_input_keeps_full_filename_and_folder_accessible():
    """The standard long demo folder leaves both full identities reachable by cell hover."""
    from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app
    from chisurf.plugins.burst.burst_fcs_correlator.test.driving import BurstDriver

    app = create_app()
    driver = BurstDriver(app)
    try:
        driver.draw(3)
        driver.click("load_example")
        control = driver.control("file_rows")
        bx, by, _, _ = control._body_box
        x = bx
        for column, width in zip(control._shown, control._widths):
            if column.key in {"name", "where"}:
                tooltip, _ = control.tooltip_at(x + width / 2, by + control._row_h / 2)
                assert control.value(0, column.key) in tooltip
            x += width
    finally:
        app.close()


def test_example_guide_reveals_files_from_correlator_without_pressing_it():
    """Opening Guide on another page reveals the demo control and still awaits its release."""
    from chisurf.plugins.fcs.fcs_correlator.gui.app import make_app as make_correlator
    from chisurf.plugins.fcs.fcs_correlator.test.test_emtk_workflow import Hub

    app = make_correlator()
    driver = Hub(app)
    try:
        app.select("correlator")
        driver.draw(3)
        driver.click("guide")
        driver.press_text("Next ►")
        assert app.selected == "files" and app.tour.step_idx == 1
        assert app.tour.awaiting and not app.files_step.checked_files
        box = driver.rect("load_example")
        app.pointer_move(box[0] + box[2] / 2, box[1] + box[3] / 2)
        driver.draw(1)
        app.press(box[0] + box[2] / 2, box[1] + box[3] / 2)
        driver.draw(1)
        assert app.tour.awaiting and not app.files_step.checked_files
        app.release()
        driver.draw(3)
        assert not app.tour.awaiting and len(app.files_step.checked_files) == 1
        assert not app.correlator_model._correlations
    finally:
        app.close()
