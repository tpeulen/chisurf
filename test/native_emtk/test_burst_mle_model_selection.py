"""Registered models retain their own inputs through the native Burst MLE workflow."""

import copy
import hashlib
import json
import shutil
import threading

import numpy as np
import pytest

from chisurf.core.fluorescence.mle.fit2x import parameter_names_of
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.burst.burst_mle_analysis import engine, state_split
from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel


@pytest.fixture
def physical_model(tmp_path):
    """Use the shipped BH measurement, with all exports confined to a private copy."""
    from chisurf.plugins.burst.burst_mle_analysis.tests.conftest import (
        BURST_TABLE,
        CHANNEL_SETTINGS,
        REPO_DATA,
    )

    target = tmp_path / "measurement"
    shutil.copytree(REPO_DATA, target)
    session = engine.MleSession()
    session.set_detectors(CHANNEL_SETTINGS["detectors"], "SPC-130")
    session.add_burst_files([target / BURST_TABLE])
    session.auto_extract()
    assert session.outcome is not None
    return MleViewModel(session)


@pytest.mark.parametrize("name", ["fit23", "fit24", "fit25"])
def test_physical_preview_and_worker_match_actual_facade(name, physical_model):
    """Preview and one real burst worker dispatch the chosen model to the same facade."""
    from chisurf.core.datastore import take_rows
    from chisurf.plugins.burst.burst_mle_analysis._mp_worker import _build_fitter

    model = physical_model
    model.fit_model = name
    model.refit()
    session = model.session
    x0, fixed = session.parameter_vector()
    cfg = session.batch_config("green")
    direct = _build_fitter(cfg).fit(session.decay, x0, fixed, include_model=True)
    np.testing.assert_array_equal(session.outcome.x, direct.x)
    np.testing.assert_array_equal(session.outcome.model, direct.model_curve)
    assert model.tau_result == direct.tau
    if name == "fit25":
        assert direct.result("selected_index") in range(4)
        assert model.parameter_records()[0]["start"] == 0.5
    session.df_bursts = take_rows(session.df_bursts, np.arange(1))
    rows = session.run_batch(max_workers=1)
    assert len(rows) == 2
    for row in rows:
        detector = row["Detector"]
        cfg = session.batch_config(detector)
        hist = session.inspect_burst(0)[detector]
        result = _build_fitter(cfg).fit(hist, cfg["x0"], cfg["fixed"])
        assert row[f"Tau ({detector})"] == pytest.approx(result.tau)
        if name == "fit25":
            assert row[f"selected_index ({detector})"] == result.result("selected_index")
            assert row[f"tau1 ({detector})"] == cfg["x0"][0]
    # The completed run keeps its schema and starts after a new model is selected.
    session.set_model("fit24" if name != "fit24" else "fit23")
    written = session.export_results()
    assert written
    settings_file = written[0].parent / "channel_settings.json"
    payload = json.loads(settings_file.read_text())
    assert payload["green"]["model"] == name


def test_fit23_matches_frozen_physical_preview_and_finite_exports(physical_model):
    """Authored Fit23 defaults preserve the actual before arrays and three-burst files."""
    from chisurf.core.datastore import take_rows

    session = physical_model.session
    # Real measured baseline captured before the chooser/model-vector changes.
    hashes_before = {
        "x": "cdfa56c66f297e44cea8ed532a9dfa098920aaad2b197896f73184201b1a8984",
        "data": "09509f246e6479db7ab7783f309cadfa2e2f37e756041a92bf84c0b81365da37",
        "curve": "ec959cbfe226a77a4dc0abae7b62c24ad78ff5babe28938a00dd6ace7858c75d",
    }
    for key, actual in [
        ("x", session.outcome.x),
        ("data", session.outcome.data),
        ("curve", session.outcome.model),
    ]:
        assert hashlib.sha256(actual.tobytes()).hexdigest() == hashes_before[key]
    session.df_bursts = take_rows(session.df_bursts, np.arange(3))
    assert len(session.run_batch(max_workers=1)) == 6
    written = session.export_results()
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in written}
    assert hashes == {
        "m000.bg4": "246beac976f870427018c1e782d132d3cd0332557311af3886821ab5dc3d90bd",
        "m000.br4": "62e1793e7275bbdd9ca497e7fa9d3b501a2c046721b1f8f227a2b505bbb103dd",
    }


@pytest.mark.parametrize("name", ["fit23", "fit24", "fit25"])
def test_registered_vectors_and_per_model_edits_survive_settings(name, tmp_path):
    """The facade's free slots, saved edits and fixed flags have the same order."""
    model = MleViewModel()
    model.fit_model = name
    names = list(parameter_names_of(name))
    assert [r["name"] for r in model.parameter_records()] == names
    values, flags = model.session.parameter_vector()
    assert len(values) == len(flags) == len(names)
    if name == "fit23":
        np.testing.assert_array_equal(values, [4, 0.1, 0.38, 1.22])
        np.testing.assert_array_equal(flags, [0, 1, 1, 1])
    model.edit_parameter({"name": names[0]}, "start", 3.125)
    if name != "fit25":
        model.edit_parameter({"name": names[0]}, "fixed", True)
    model.fit_model = "fit24" if name != "fit24" else "fit23"
    model.fit_model = name
    assert model.parameter_records()[0]["start"] == 3.125
    assert model.parameter_records()[0]["fixed"] is True
    path = tmp_path / "settings.json"
    model.save_settings(path)
    restored = MleViewModel()
    restored.load_settings(path)
    assert restored.fit_model == name
    assert restored.parameter_records() == model.parameter_records()
    other = restored.session.settings_of("red")
    assert other.model_values is not restored.session.settings.model_values


@pytest.mark.parametrize("name", ["fit26", "fit_nexp", "misspelled"])
def test_unavailable_model_rejects_without_changing_selected_fit(name):
    """A model that needs different inputs cannot silently become Fit23."""
    model = MleViewModel()
    assert model.fit_model_options() == ["fit23", "fit24", "fit25", "tail"]
    assert "fit26" in model.model_availability()
    with pytest.raises(ValueError):
        model.fit_model = name
    assert model.fit_model == "fit23"


def test_actual_native_choice_pointer_commits_and_notifies_used():
    """A genuine AutoForm choice updates the selected model and the tour's await target."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    app = create_app()
    driver = Driver(app, (1280, 900))
    used = []
    tour = app.tour
    tour.steps = [
        {
            "title": "Fit model",
            "text": "Choose a different model.",
            "target": {"name": "fit_model"},
            "await": {"hint": "Choose Fit24."},
        }
    ]

    def notify(name):
        """Observe the actual form notification while retaining the real tour callback."""
        used.append(name)
        tour.notify_used(name)

    app.form.on_used = notify
    try:
        driver.frame(3)
        assert "fit_model" in driver.ids()
        assert tour.get_target_rect("fit_model") is not None
        tour.start()
        assert tour.awaiting
        driver.click("fit_model")
        driver.click(dict(app.model.fit_model_choices())["fit24"])
        driver.frame(2)
        assert app.model.fit_model == "fit24"
        assert "fit_model" in used
        assert not tour.awaiting
        assert [row["name"] for row in app.model.parameter_records()] == list(
            parameter_names_of("fit24")
        )
    finally:
        tour.stop()
        app.close()


@pytest.mark.parametrize("name", ["fit24", "fit25"])
def test_actual_container_stores_registry_parameter_units(name, tmp_path):
    """The actual PTO writer records units for model-aware lifetime parameter columns."""
    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.pto import Measurement
    from chisurf.plugins.burst.burst_mle_analysis.core.export import write_mle_container

    source = tmp_path / "measurement.ptu"
    source.write_bytes(b"")
    columns = {f"{p} (green)": np.array([1.0, 2.0]) for p in parameter_names_of(name)}
    path = write_mle_container(
        source, {"green": store_from_arrays(columns)}, parameters={"model": name}
    )
    with Measurement.open(path, writable=False) as measurement:
        obj = next(
            o for o in measurement.artifacts() if o.name.endswith("/mle green")
        )  # in its own run
        import tttrlib

        table = tttrlib.pto_store(measurement._f, obj.uid)
        # Datastore metadata is the persisted contract, not a prefix-helper assertion.
        for i in range(table.n_columns()):
            column = table[i]
            if column.name().startswith("tau"):
                assert column.units() == "nanoseconds"


def test_fit25_state_seed_preserves_candidates_and_mixed_state_schema():
    """A classified lifetime is an output, never a replacement candidate input."""
    cfg25 = {
        "model": "fit25",
        "param_names": list(parameter_names_of("fit25")),
        "x0": np.array([0.5, 1.5, 2.5, 4.0, 0.0]),
    }
    cfg24 = {
        "model": "fit24",
        "param_names": list(parameter_names_of("fit24")),
        "x0": np.array([1.0, 0.0, 4.0, 0.5, 0.0]),
    }
    cfgs = {"green": cfg25, "red": cfg24}
    fits = {
        det: {
            0: {
                "x": np.array([2.5, 1.5, 2.5, 4.0, 0.0]),
                "two_istar": 1.0,
                "cp": 20,
                "cs": 30,
                "selected_index": 2.0,
            }
        }
        for det in cfgs
    }
    job = tuple([None] * 9 + [cfgs])
    assert state_split.seed_state_fits([job], fits) == 1
    np.testing.assert_array_equal(cfg25["state_x0"][0], cfg25["x0"])
    assert cfg24["state_x0"][0][0] == 2.5
    rows = state_split.state_lifetime_rows(fits, "fit23", [], perdet_cfg=cfgs)
    assert rows[0]["tau1"] == 0.5
    assert rows[0]["Tau"] == 2.5
    assert rows[0]["selected_index"] == 2
    assert "A2" in rows[1] and "r0" not in rows[1]


def test_snapshot_job_isolates_session_and_rejects_live_edits(monkeypatch, physical_model):
    """A delayed real SnapshotJob never observes a live setup/model mutation."""
    model = physical_model
    started, release = threading.Event(), threading.Event()
    captured = []

    def delayed(session, **kwargs):
        """Hold a genuine worker long enough to exercise the live setter."""
        captured.append((session, copy.deepcopy(session.detectors), session.settings.model))
        started.set()
        assert release.wait(3)
        return []

    monkeypatch.setattr(engine.MleSession, "run_batch", delayed)
    job = SnapshotJob(model)
    assert job.start("run_batch")
    assert started.wait(3)
    try:
        with pytest.raises(RuntimeError):
            model.fit_model = "fit25"
        with pytest.raises(RuntimeError):
            model.set_setup({"detectors": {"changed": {"chs": [99]}}})
        assert captured[0][0] is not model.session
        assert captured[0][0].current_tttr() is model.session.current_tttr()
        assert captured[0][0].df_bursts is not model.session.df_bursts
        assert captured[0][0].tttrs.paths is captured[0][0].tttr_paths
        assert captured[0][2] == "fit23"
        assert "changed" not in captured[0][1]
    finally:
        release.set()
        job.thread.join(3)
        job.poll()
    model.fit_model = "fit25"
    assert model.fit_model == "fit25"


def test_closing_actual_app_cancels_snapshot_without_publication(monkeypatch, physical_model):
    """Closing the real native app cancels its independent worker before any late result."""
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    started, release = threading.Event(), threading.Event()

    def delayed(session, *, should_stop, **kwargs):
        """Wait until the owning app has closed, then observe its actual cancel event."""
        started.set()
        assert release.wait(3)
        assert should_stop()
        raise InterruptedError("Cancelled")

    monkeypatch.setattr(engine.MleSession, "run_batch", delayed)
    app = create_app(model=physical_model)
    original = app.model.session
    try:
        assert app.job.start("run_batch")
        assert started.wait(3)
        app.close()
        release.set()
        app.job.thread.join(3)
        app.job.poll()
        assert app.job.error == "Cancelled"
        assert app.model.session is original
        assert not app.model._snapshot_running.is_set()
    finally:
        release.set()
        app.close()


def test_already_open_detector_json_cannot_publish_during_job(monkeypatch, physical_model):
    """A real pending JSON Apply stays blocked, retaining the working setup until idle."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    started, release = threading.Event(), threading.Event()

    def delayed(session, **kwargs):
        """Hold a real snapshot job during the actual modal interaction."""
        started.set()
        assert release.wait(3)
        return []

    monkeypatch.setattr(engine.MleSession, "run_batch", delayed)
    app = create_app(model=physical_model)
    driver = Driver(app, (1280, 900))
    original = copy.deepcopy(app.editor.model.get_settings())
    draft = copy.deepcopy(original)
    draft["detectors"]["green"]["g_factor"] = 1.9
    app.editor.edit_json()
    app.editor.json_text = json.dumps(draft)
    try:
        driver.frame(3)
        assert app.job.start("run_batch")
        assert started.wait(3)
        driver.frame(2)
        driver.click(app.editor.item_rects["apply_json"])
        assert app.editor.model.get_settings() == original
        assert app.editor.read_only is True
        release.set()
        app.job.thread.join(3)
        driver.frame(3)
        assert app.editor.read_only is False
        driver.click(app.editor.item_rects["apply_json"])
        assert app.editor.model.data["detectors"]["green"]["g_factor"] == 1.9
        assert app.model.session.detectors["green"]["g_factor"] == 1.9
    finally:
        release.set()
        app.job.thread.join(3)
        app.close()


def test_completed_detector_read_is_deferred_until_snapshot_idle(monkeypatch, physical_model):
    """A real prepared TTTR read publishes once after the independent fitting job ends."""
    from concurrent.futures import Future

    from emtk.testing import Driver

    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    started, release = threading.Event(), threading.Event()

    def delayed(session, **kwargs):
        """Hold the fitting job while the independent detector read becomes ready."""
        started.set()
        assert release.wait(3)
        return []

    monkeypatch.setattr(engine.MleSession, "run_batch", delayed)
    app = create_app(model=physical_model)
    driver = Driver(app, (1280, 900))
    future = Future()
    monkeypatch.setattr(app.editor._executor, "submit", lambda *args: future)
    notices = []
    app.model._observers.append(notices.append)
    original = copy.deepcopy(app.editor.model.get_settings())
    path = next(iter(app.model.session.tttr_paths.values()))
    prepared = app.editor._read(ChannelDefinition(original), str(path))
    app.editor.read(str(path))
    try:
        assert app.job.start("run_batch")
        assert started.wait(3)
        future.set_result(prepared)
        driver.frame(2)
        assert app.editor._future is future
        assert app.editor.model.get_settings() == original
        assert not app.on_paths_dropped([str(app.model.session.bur_files[0])])
        release.set()
        app.job.thread.join(3)
        driver.frame(3)
        assert app.editor._future is None
        assert app.editor.model.preview_path == prepared.preview_path
        assert notices.count("setup") == 1
    finally:
        release.set()
        app.job.thread.join(3)
        app.close()


@pytest.mark.parametrize("prior_read_only", [False, True])
def test_existing_detector_read_only_policy_survives_job(
    monkeypatch, physical_model, prior_read_only
):
    """Idle and close restore the editor's pre-existing policy rather than unconditionally enabling it."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    started, release = threading.Event(), threading.Event()

    def delayed(session, **kwargs):
        """Expose a busy frame and then complete without modifying its copied setup."""
        started.set()
        assert release.wait(3)
        return []

    monkeypatch.setattr(engine.MleSession, "run_batch", delayed)
    app = create_app(model=physical_model)
    app.editor.read_only = prior_read_only
    driver = Driver(app, (1280, 900))
    try:
        assert app.job.start("run_batch")
        assert started.wait(3)
        driver.frame(2)
        assert app.editor.read_only is True
        release.set()
        app.job.thread.join(3)
        driver.frame(3)
        assert app.editor.read_only is prior_read_only
        app.close()
        assert app.editor.read_only is prior_read_only
    finally:
        release.set()
        app.job.thread.join(3)
        app.close()


@pytest.mark.parametrize("simultaneous", [False, True])
def test_same_stem_measurements_keep_physical_file_identity(physical_model, tmp_path, simultaneous):
    """A second real SPC named m000 must not resolve to the first measurement's photons."""
    from pathlib import Path

    import tttrlib

    session = physical_model.session
    first = session.current_tttr()
    source_burst = session.bur_files[0]
    source_root = source_burst.parent.parent.parent
    other = tmp_path / "second-measurement"
    shutil.copytree(source_root, other)
    raw = next(iter(session.tttr_paths.values()))
    alternate = Path(__file__).resolve().parents[1] / "data/tttr/BH/132/BH_SPC132.spc"
    target_raw = other / raw.relative_to(source_root)
    shutil.copyfile(alternate, target_raw)
    expected = tttrlib.TTTR(str(target_raw), "SPC-130")
    assert len(expected) != len(first)
    second_burst = other / source_burst.relative_to(source_root)
    if not simultaneous:
        session.bur_files.clear()
        session.df_bursts = None
    session.add_burst_files([second_burst])
    session.current_index = int(simultaneous)
    second = session.current_tttr()
    assert len(second) == len(expected)
    np.testing.assert_array_equal(second.routing_channels, expected.routing_channels)
    if simultaneous:
        session.current_index = 0
        np.testing.assert_array_equal(
            session.current_tttr().routing_channels, first.routing_channels
        )
        session.current_index = 1
        np.testing.assert_array_equal(
            session.current_tttr().routing_channels, expected.routing_channels
        )


def test_explicit_saved_timing_override_reaches_real_fit_and_settings(physical_model, tmp_path):
    """A declared 25 ps calibration is effective once, while the physical header stays untouched."""
    model = physical_model
    setup = {
        "detectors": copy.deepcopy(model.session.detectors),
        "windows": {},
        "tttr_reading": {
            "file_type": "SPC-130",
            "override_timing": True,
            "micro_time_resolution": 25.0,
            "macro_time_resolution": 102.4,
            "future_reading_metadata": {"units": "preserved"},
        },
    }
    tttr = model.session.current_tttr()
    physical = engine.header_time_ns(tttr, model.binning)
    model.set_setup(setup)
    cfg = model.session.batch_config("green")
    assert cfg["dt"] == 0.025 * model.binning
    assert cfg["period"] == 102.4
    assert engine.header_time_ns(model.session.current_tttr(), model.binning) == physical
    model.refit()
    from chisurf.plugins.burst.burst_mle_analysis._mp_worker import _build_fitter

    direct = _build_fitter(cfg).fit(model.session.decay, cfg["x0"], cfg["fixed"])
    np.testing.assert_array_equal(model.session.outcome.x, direct.x)
    path = tmp_path / "override.json"
    model.save_settings(path)
    restored = MleViewModel()
    restored.load_settings(path)
    assert restored.session.definition_payload()["tttr_reading"] == setup["tttr_reading"]


def test_declared_lut_and_shift_reach_actual_photons_without_global_leak(physical_model):
    """A nonidentity TAC correction and +2 shift use the same canonical reader as the preview."""
    from chisurf.core.data_io.detector_setups import setup_lut_open_kwargs
    from chisurf.core.fio.staging import open_tttr

    model = physical_model
    raw = model.session.current_tttr()
    path = next(path for path in model.session.tttr_paths.values() if path.stem == "m000")
    setup = {
        "detectors": copy.deepcopy(model.session.detectors),
        "windows": {},
        "tttr_reading": {"file_type": "SPC-130"},
        # NTAC_fract contains fractional channel coordinates, not fractions of a period.
        "channel_luts": {"0": 4095.0 * (np.arange(4096) / 4095.0) ** 1.2},
        "channel_shifts": {"0": 2},
        "apply_lut": True,
        "future_metadata": {"tag": "retained"},
    }
    expected = open_tttr(path, "SPC-130", cache=False, **setup_lut_open_kwargs(setup))
    assert not np.array_equal(raw.micro_times, expected.micro_times)
    model.set_setup(setup)
    actual = model.session.current_tttr()
    np.testing.assert_array_equal(actual.micro_times, expected.micro_times)
    assert actual is not raw
    other = engine.MleSession()
    other.set_detectors(model.session.detectors, "SPC-130")
    other.add_burst_files(model.session.bur_files)
    np.testing.assert_array_equal(other.current_tttr().micro_times, raw.micro_times)
    assert model.session.definition_payload()["future_metadata"] == {"tag": "retained"}
