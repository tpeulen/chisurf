"""Native simulator settings preserve the original reader's numerical owner."""

from types import SimpleNamespace

import numpy as np
import pytest

from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup


def test_array_spectrum_constructs_and_view_never_changes_supplied_values():
    """User-provided arrays and calibration survive frontend construction."""
    setup = TCSPCSimulatorSetup(lifetime_spectrum=np.array([0.7, 3.1, 0.3, 1.2]),
                                rotation_spectrum=np.array([0.31, 2.4]), seed=154,
                                sample_name="Supplied", g_factor=1.7, l1=.05, l2=.08,
                                irf_mean=2.3, irf_sigma=.16, record_provenance=False)
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp
    before = (setup.lifetime_spectrum.copy(), setup.rotation_spectrum.copy())
    app = SimulatorSettingsApp(setup, context=SimpleNamespace(api=None))
    try:
        np.testing.assert_array_equal(setup.lifetime_spectrum, before[0])
        np.testing.assert_array_equal(setup.rotation_spectrum, before[1])
        assert (setup.sample_name, setup.g_factor, setup.l1, setup.l2, setup.seed) == (
            "Supplied", 1.7, .05, .08, 154)
        assert (setup.irf_mean, setup.irf_sigma) == (2.3, .16)
    finally:
        app.close()


@pytest.mark.parametrize("contents", [".4 1.1\n.6 4.1\n", ".4,1.1\n.6,4.1\n", ".4 1.1 .6 4.1\n"])
def test_lifetime_file_and_text_preserve_interleaved_values(tmp_path, contents):
    """Flat and paired spectrum files update the owning reader only after parsing."""
    setup = TCSPCSimulatorSetup(record_provenance=False)
    path = tmp_path / "spectrum.txt"
    path.write_text(contents)
    setup.load_lifetime_spectrum_file(str(path))
    np.testing.assert_array_equal(setup.lifetime_spectrum, [.4, 1.1, .6, 4.1])
    assert setup.lifetime_spectrum_file == str(path)
    setup.lifetime_spectrum_text = "-0.2; 0; 1.2; 3.5"
    np.testing.assert_array_equal(setup.lifetime_spectrum, [-.2, 0, 1.2, 3.5])
    with pytest.raises(ValueError):
        setup.lifetime_spectrum_text = "1, invalid"
    np.testing.assert_array_equal(setup.lifetime_spectrum, [-.2, 0, 1.2, 3.5])


@pytest.mark.parametrize("mode", ["vm", "vv/vh"])
@pytest.mark.parametrize("seed,noise", [(154, True), (None, True), (None, False)])
def test_preview_is_reader_output_and_add_uses_the_exact_cached_group(mode, seed, noise):
    """Add never draws fresh noise or discards a polarized member of the preview."""
    from chisurf.core.api.context import PluginContext
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    setup = TCSPCSimulatorSetup(lifetime_spectrum=[.4, 1.1, .6, 4.1],
                                rotation_spectrum=[.2, 1], polarization=mode,
                                n_tac=512, seed=seed, add_noise=noise, record_provenance=False)
    submitted = []
    api = SimpleNamespace(load_dataset=lambda **kw: submitted.append(kw) or {"ok": True})
    context = PluginContext(api=api)
    app = SimulatorSettingsApp(setup, context=context)
    try:
        app.model.simulate_preview()
        preview = app.model.preview
        if seed is not None or not noise:
            expected = setup.read()
            for actual, oracle in zip(preview, expected):
                np.testing.assert_array_equal(actual.y, oracle.y)
        app.model.add_preview()
        assert submitted[0]["dataset"] is preview
        assert submitted[0]["experiment_reader"] is setup
        assert len(preview) == (1 if mode == "vm" else 2)
        assert all(curve.data_reader is setup for curve in preview)
    finally:
        app.close()


def test_session_irf_uses_selected_member_uid_and_unload_restores_gaussian():
    """Duplicate names cannot silently substitute the first curve of a group."""
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    calls = []
    api = SimpleNamespace(
        list_datasets=lambda: [{"uid": "group", "name": "Group", "members": [
            {"uid": "first", "name": "same", "length": 3},
            {"uid": "second", "name": "same", "length": 3}]}],
        get_dataset_curve_data=lambda **kw: calls.append(kw) or {"ok": True, "x": [0, 1, 2], "y": [0, 9, 0]},
    )
    setup = TCSPCSimulatorSetup(record_provenance=False)
    app = SimulatorSettingsApp(setup, context=SimpleNamespace(api=api))
    try:
        options = app.model.irf_options()
        app.model.irf_candidate = options[1][0]
        app.model.select_irf()
        assert calls == [{"dataset_uid": "group", "member_uid": "second"}]
        np.testing.assert_array_equal(setup.instrument_response_function.y, [0, 9, 0])
        app.model.unload_irf()
        assert setup.instrument_response_function is None
    finally:
        app.close()


def test_real_api_group_member_selection_preserves_active_member():
    """The frontend uses the owning session API with exact parent/member identities."""
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.api.context import PluginContext
    from chisurf.core.data import DataCurve, DataCurveGroup
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp
    from chisurf.server.session import SessionState

    first = DataCurve(x=np.arange(4.), y=np.array([0., 1., 0., 0.]), name="same")
    second = DataCurve(x=np.arange(4.), y=np.array([0., 0., 9., 0.]), name="same")
    group = DataCurveGroup([first, second], name="Measured responses")
    api = ChiSurfAPI(state=SessionState(datasets=[group], fits=[]))
    app = SimulatorSettingsApp(TCSPCSimulatorSetup(record_provenance=False), context=PluginContext(api=api))
    try:
        selected = [value for value, label in app.model.irf_options()
                    if second.unique_identifier in value]
        assert len(selected) == 1
        app.model.irf_candidate = selected[0]
        app.model.select_irf()
        np.testing.assert_array_equal(app.reader.instrument_response_function.y, second.y)
        np.testing.assert_array_equal(group.y, first.y)
        assert app.model.irf_choices()[0][0] == ""
    finally:
        app.close()


def test_nullable_seed_and_invalid_inputs_preserve_previous_values(tmp_path):
    """Invalid editing/file input is explicit and cannot partially replace science values."""
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    reader = TCSPCSimulatorSetup(lifetime_spectrum=[1, 4], seed=154, record_provenance=False)
    app = SimulatorSettingsApp(reader, context=SimpleNamespace(api=None))
    try:
        app.model.seed_text = ""
        assert reader.seed is None
        app.model.seed_text = "8"
        assert reader.seed == 8
        app.model.seed_text = "bad"
        assert reader.seed == 8 and app.model.status
        original = reader.lifetime_spectrum.copy()
        invalid = tmp_path / "bad.txt"
        invalid.write_text("not a spectrum")
        app.model.load_lifetime_spectrum_file(str(invalid))
        np.testing.assert_array_equal(reader.lifetime_spectrum, original)
        assert reader.lifetime_spectrum_file == "" and app.model.status
    finally:
        app.close()


def test_native_tabs_reveal_real_controls_and_simulate_add_callbacks():
    """Only the selected tab submits controls; preview/Add activate actual handlers."""
    from emtk.testing import Driver

    from chisurf.core.api.context import PluginContext
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    submitted = []
    api = SimpleNamespace(list_datasets=lambda: [], load_dataset=lambda **kw: submitted.append(kw) or {"ok": True})
    reader = TCSPCSimulatorSetup(lifetime_spectrum=[1, 4], rotation_spectrum=[.2, 1],
                                seed=154, n_tac=512, record_provenance=False)
    app = SimulatorSettingsApp(reader, context=PluginContext(api=api))
    try:
        driver = Driver(app, size=(900, 760))
        driver.draw()
        assert {"simulator.decay", "simulator.anisotropy", "simulator.preview"} <= set(driver.ids())
        assert driver.rect("sample_name") is not None
        assert "g_factor" not in driver.ids() and "simulate_preview" not in driver.ids()
        driver.click("simulator.anisotropy")
        assert driver.rect("rotation_spectrum_text") is not None
        assert "sample_name" not in driver.ids()
        driver.click("simulator.preview")
        driver.click("simulate_preview")
        preview = app.model.preview
        driver.click("add_preview")
        assert submitted[0]["dataset"] is preview
        assert app.model.status
    finally:
        app.close()


def test_tab_switch_commits_typed_spectrum_file_once(tmp_path, monkeypatch):
    """Preview consumes the typed custom source without requiring an extra Enter."""
    from emtk.testing import Driver

    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    path = tmp_path / "spectrum.txt"
    path.write_text(".25 1\n.75 8\n")
    reader = TCSPCSimulatorSetup(lifetime_spectrum=[1,4], seed=154, record_provenance=False)
    load = reader.load_lifetime_spectrum_file
    loaded = []

    def record(filename):
        """Count actual owner callbacks rather than form inventory entries."""
        loaded.append(filename)
        load(filename)

    monkeypatch.setattr(reader, "load_lifetime_spectrum_file", record)
    app = SimulatorSettingsApp(reader, context=SimpleNamespace(api=None))
    try:
        driver = Driver(app, size=(900,760))
        driver.draw()
        driver.click("lifetime_spectrum_file")
        driver.type(str(path))
        driver.click("simulator.preview")
        np.testing.assert_array_equal(reader.lifetime_spectrum, [.25,1,.75,8])
        assert reader.lifetime_spectrum_file == str(path)
        assert loaded == [str(path)]
        driver.click("simulate_preview")
        np.testing.assert_array_equal(app.model.preview[0].y, reader.read()[0].y)
        driver.click("simulator.decay")
        driver.click("simulator.anisotropy")
        assert loaded == [str(path)]
    finally:
        app.close()


def test_invalid_pending_source_survives_switch_without_mutating_reader(tmp_path):
    """Invalid input stays editable, with its error visible and valid science retained."""
    from emtk.testing import Driver

    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    reader = TCSPCSimulatorSetup(lifetime_spectrum=[1,4], record_provenance=False)
    app = SimulatorSettingsApp(reader, context=SimpleNamespace(api=None))
    missing = str(tmp_path / "missing.txt")
    try:
        driver = Driver(app, size=(900,760))
        driver.draw()
        driver.click("lifetime_spectrum_file")
        driver.type(missing)
        driver.click("simulator.preview")
        np.testing.assert_array_equal(reader.lifetime_spectrum, [1,4])
        source = app.sources["lifetime_spectrum_file"]
        assert source.state.buffers["path"] == missing
        assert reader.lifetime_spectrum_file == "" and app.model.status
    finally:
        app.close()


@pytest.mark.parametrize("closed", [False, True])
def test_pending_source_flush_respects_closed_and_read_only_state(tmp_path, closed):
    """Tab lifecycle cannot bypass the source owner's existing write guards."""
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    path = tmp_path / "spectrum.txt"
    path.write_text(".25 1\n.75 8\n")
    reader = TCSPCSimulatorSetup(lifetime_spectrum=[1,4], record_provenance=False)
    app = SimulatorSettingsApp(reader, context=SimpleNamespace(api=None))
    source = app.sources["lifetime_spectrum_file"]
    source.state.buffers["path"] = str(path)
    if closed:
        app.close()
    else:
        source.options["read_only"] = True
    try:
        app._used("simulator.preview")
        np.testing.assert_array_equal(reader.lifetime_spectrum, [1,4])
        assert reader.lifetime_spectrum_file == ""
        assert source.state.buffers["path"] == str(path)
    finally:
        app.close()
