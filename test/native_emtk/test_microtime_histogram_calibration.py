"""Declared timing provenance and count invariance of the real measured SPC fixture."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel

SOURCE = Path(__file__).resolve().parents[2] / "test/data/tttr/BH/132/BH_SPC132.spc"


def _setup(override, binning=1):
    """Declare validation-only25 ps calibration without claiming physical ground truth."""
    return {
        "setup_name": "validation-declared-25ps",
        "detectors": {"green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]]}},
        "windows": {},
        "tttr_reading": {
            "file_type": "SPC-130",
            "micro_time_resolution": 25.0,
            "micro_time_binning": binning,
            "override_timing": override,
        },
    }


def _compute(override, binning=1):
    """Read actual photons through the owning model under one declared timing policy."""
    model = HistogramModel()
    model.auto_save = False
    model.set_setup(_setup(override, binning))
    model.add_paths([SOURCE])
    model.compute()
    return model


@pytest.mark.parametrize("binning", [1, 4])
def test_explicit_override_changes_time_scale_and_not_counts(binning):
    """Selected calibration changes physical units while retaining identical count vectors."""
    header = _compute(False, binning)
    declared = _compute(True, binning)
    reported = tttrlib.TTTR(str(SOURCE), "SPC-130").header.micro_time_resolution
    assert header.dt_ns == pytest.approx(reported * 1e9 * binning)
    assert declared.dt_ns == pytest.approx(25.0 * 1e-3 * binning)
    np.testing.assert_array_equal(declared.cumulative_ps, header.cumulative_ps)
    assert declared.fwhm_bins == header.fwhm_bins
    assert declared.fwhm_ns == pytest.approx(declared.fwhm_bins * declared.dt_ns)
    assert header.fwhm_ns == pytest.approx(header.fwhm_bins * header.dt_ns)
    assert declared.cumulative_ps.sum() > 100_000


def test_manual_histogram_time_step_precedes_setup_and_header():
    """The explicit per-histogram manual time step remains the strongest override."""
    model = HistogramModel()
    model.auto_save = False
    model.set_setup(_setup(True))
    model.dt_manual, model.dt_ns = True, 0.12
    model.add_paths([SOURCE])
    model.compute()
    assert model.dt_ns == 0.12
    assert model.fwhm_ns == pytest.approx(model.fwhm_bins * 0.12)


def test_positive_setup_timing_is_fallback_when_header_timing_is_missing(tmp_path):
    """A non-reporting source can use the declared positive fallback without inventing units."""
    source = tmp_path / "missing-clock.ptu"
    source.write_bytes(b"source supplied by the controlled reader")
    stream = SimpleNamespace(
        micro_times=np.array([0, 1, 2, 3, 1, 2, 4, 5]),
        routing_channels=np.array([8, 8, 8, 8, 0, 0, 0, 0]),
        header=SimpleNamespace(
            micro_time_resolution=0.0,
            get_effective_number_of_micro_time_channels=lambda: 8,
        ),
    )
    model = HistogramModel()
    model.auto_save = False
    model.set_setup(_setup(False))
    model.filetype = "PTU"
    model.add_paths([source])
    model.compute(reader=lambda _: stream)
    assert model.dt_ns == 0.025
    assert model.fwhm_ns == pytest.approx(model.fwhm_bins * 0.025)


@pytest.mark.parametrize("mode", ["declared", "manual", "unconfigured"])
def test_physical_inputs_polarization_toggle_keeps_routing_and_other_settings(mode, tmp_path):
    """The actual checkbox selects one combined stream and restores alternating VV/VH routes."""
    from emtk.testing import Driver

    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app

    app = create_app()
    driver = Driver(app, (1280, 900))
    try:
        if mode != "unconfigured":
            app.editor.load_definition(_setup(False))
        else:
            app.fields.filetype = "SPC-130"
        app.add_files([SOURCE])
        app.model.auto_save = False
        if mode != "declared":
            app.fields.parallel_text = "8,9"
            app.fields.perpendicular_text = "0"
        initial = (app.model.parallel.copy(), app.model.perpendicular.copy())
        ordered = [8, 0, 3] if mode == "declared" else [8, 0, 9]
        app.fields.dt_ns = 0.12
        app.fields.g_factor = 1.25
        app.fields.vv_shift = 3
        app.fields.vh_shift = -2
        app.fields.binning = 4
        values = (
            app.model.dt_ns,
            app.model.dt_manual,
            app.model.g_factor,
            app.model.vv_shift,
            app.model.vh_shift,
            app.model.filetype,
            app.model.binning,
        )
        driver.frame(3)
        driver.click("polarized")
        assert not app.model.polarized
        assert app.model.parallel == ordered
        assert app.model.perpendicular == []
        assert not app.editor.model.data["polarization_resolved"]
        if mode != "unconfigured":
            assert app.editor.model.data["detectors"]["green"]["chs"] == ordered
        else:
            assert app.editor.model.data["detectors"] == {}
        assert values == (
            app.model.dt_ns,
            app.model.dt_manual,
            app.model.g_factor,
            app.model.vv_shift,
            app.model.vh_shift,
            app.model.filetype,
            app.model.binning,
        )
        app.fields.vv_shift = app.fields.vh_shift = 0
        app.fields.binning = 1
        driver.click("compute")
        app.job.future.result(timeout=15)
        app.job.poll()
        stream = tttrlib.TTTR(str(SOURCE), "SPC-130")
        raw, _ = stream.get_microtime_histogram(1, ordered)
        np.testing.assert_array_equal(app.model.cumulative_ps[: len(raw)], raw)
        assert app.model.cumulative_ps.sum() == np.count_nonzero(
            np.isin(stream.routing_channels, ordered)
        )
        assert app.model.cumulative_perpendicular.sum() == 0
        output = tmp_path / "unpolarized.dat"
        app.model.save(output)
        np.testing.assert_array_equal(np.loadtxt(output), app.model.cumulative_ps)
        driver.click("polarized")
        assert app.model.polarized
        assert (app.model.parallel, app.model.perpendicular) == initial
        assert app.editor.model.data["polarization_resolved"]
        assert app.model.dt_ns == 0.12 and app.model.g_factor == 1.25
        driver.click("compute")
        app.job.future.result(timeout=15)
        app.job.poll()
        vv, _ = stream.get_microtime_histogram(1, initial[0])
        vh, _ = stream.get_microtime_histogram(1, initial[1])
        np.testing.assert_array_equal(app.model.cumulative_parallel[: len(vv)], vv)
        np.testing.assert_array_equal(app.model.cumulative_perpendicular[: len(vh)], vh)
    finally:
        app.close()


@pytest.mark.parametrize("entrypoint", ["api", "cli"])
def test_bid_startup_uses_saved_setup_real_photons_and_transfers_once(
    tmp_path, monkeypatch, entrypoint
):
    """Actual batch startup preserves calibrated timing, burst-folder export and transfer values."""
    import shutil

    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app

    source = tmp_path / SOURCE.name
    shutil.copyfile(SOURCE, source)
    stream = tttrlib.TTTR(str(source), "SPC-130")
    folder = tmp_path / "bi4_bur"
    folder.mkdir()
    (folder / "BH_SPC132.bst").write_text(f"0\t{len(stream.micro_times) - 1}\n")
    setup = _setup(True)

    def refresh(store):
        """Provide the named saved setup without contacting a user metadata database."""
        store.setups = {"validation-declared-25ps": setup}

    monkeypatch.setattr(ChannelDefinition, "refresh_setups", refresh)
    transferred = []
    app = create_app(add_dataset=lambda path, params: transferred.append((path, params)))
    callbacks = []
    notify = app.editor.model.on_changed

    def changed(settings):
        """Observe the actual model callback while preserving its existing behavior."""
        callbacks.append(settings)
        notify(settings)

    app.editor.model.on_changed = changed
    closed = []
    try:
        app.model.auto_save = False
        if entrypoint == "api":
            assert app.load_bid_folder(
                folder, setup_name="validation-declared-25ps", auto_transfer=True
            )
            completed = app.job.future.result(timeout=15)
        else:
            from emtk import native

            from chisurf.plugins.tttr.microtime_histogram import __main__ as launcher
            from chisurf.plugins.tttr.microtime_histogram.gui import app as app_module

            results = []

            class Host:
                """Drive actual queued CLI work without opening a hardware window."""

                def __init__(self, control, **kwargs):
                    """Verify that the original physical app reaches the public host seam."""
                    assert control is app

                def run(self):
                    """Wait for the real source read and publish through the existing job."""
                    results.append(app.job.future.result(timeout=15))
                    app.job.poll()

                def close(self):
                    """Perform real worker/editor cleanup once when the launcher returns."""
                    app.close()
                    closed.append(True)

            monkeypatch.setattr(app_module, "create_app", lambda: app)
            monkeypatch.setattr(native, "NativeHost", Host)
            assert (
                launcher.main(
                    [
                        "--bid-folder",
                        str(folder),
                        "--setup-name",
                        "validation-declared-25ps",
                        "--auto-transfer",
                    ]
                )
                == 0
            )
            assert closed == [True]
            completed = results[0]
        computed_counts = completed.cumulative_ps.copy()
        app.job.poll()
        app.job.poll()
        assert not app.job.running
        assert app.model is completed
        assert len(callbacks) == 1
        np.testing.assert_array_equal(app.model.cumulative_ps, computed_counts)
        assert app.model.dt_ns == 0.025
        reading = app.editor.model.data["tttr_reading"]
        assert reading["micro_time_resolution"] == 25.0
        assert reading["override_timing"]
        assert app.editor.model.data["detectors"] == app.model.setup["detectors"]
        assert app.model.parallel == [8, 3]
        assert app.model.perpendicular == [0]
        assert app.model.selected_bids() == [folder / "BH_SPC132.bst"]
        assert app.model.fwhm_ns == pytest.approx(app.model.fwhm_bins * 0.025)
        assert app.model.cumulative_ps.sum() == 135967
        assert len(transferred) == 1
        output, parameters = transferred[0]
        assert output.parent == folder
        assert parameters["dt"] == 0.025
        np.testing.assert_array_equal(np.loadtxt(output), app.model.cumulative_ps)
    finally:
        if not closed:
            app.close()
