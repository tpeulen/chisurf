"""Drift-correction plugin: both source kinds, end to end.

The two paths differ in a way worth pinning: a TIFF stack is corrected by
shifting intensities, a photon stream by moving photons between pixels. The
latter is what keeps the corrected confocal image usable for lifetime and
correlation analysis, so it gets its own round-trip test on real data.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.microscopy.img_drift import core

_CLSM = pathlib.Path(__file__).resolve().parents[5] / "test" / "data" / "clsm" / "PQ_Olympus_MFIS.ht3"


@pytest.fixture
def drifting_tiff(tmp_path):
    """Write a TIFF stack with a known linear drift and return its path."""
    from chisurf.core.fio.image import imread, imwrite

    rng = np.random.default_rng(0)
    base = rng.random((40, 40)) * 100.0
    stack = np.stack(
        [np.roll(base, (2 * k, -k), axis=(0, 1)) for k in range(5)]
    ).astype(np.float32)
    path = tmp_path / "drift.tif"
    imwrite(path, stack)
    return path


# --- image stacks ----------------------------------------------------------
def test_measure_recovers_the_injected_drift(drifting_tiff):
    """The measured displacement matches the translation written into the file."""
    result = core.measure_drift(str(drifting_tiff))
    assert result.kind == "image"
    assert result.n_frames == 5
    np.testing.assert_allclose(
        result.shifts, [[0, 0], [2, -1], [4, -2], [6, -3], [8, -4]]
    )
    assert result.total_drift == pytest.approx(np.hypot(8, 4))


def test_correction_sharpens_the_projection(drifting_tiff):
    """The summed projection is sharper after correction than before.

    This is the visual check the tool shows, so it is worth asserting: drift
    blurs the projection, and removing it concentrates the same signal.
    """
    result = core.measure_drift(str(drifting_tiff))
    assert result.after.std() > result.before.std()
    assert result.before.sum() == pytest.approx(result.after.sum())


def test_corrected_stack_covers_every_channel(drifting_tiff):
    """The correction measured on one channel is applied to the whole stack."""
    data, shifts = core.corrected_stack(str(drifting_tiff))
    assert data.ndim == 4                      # (frame, channel, y, x)
    assert data.shape[0] == len(shifts) == 5
    # every frame of the corrected stack matches the first
    for k in range(1, data.shape[0]):
        np.testing.assert_allclose(data[k, 0], data[0, 0])


def test_exports_are_written(drifting_tiff, tmp_path):
    """Both export paths produce readable files."""
    from chisurf.core.fio.image import imread, imwrite

    result = core.measure_drift(str(drifting_tiff))
    csv = core.write_shifts_csv(result.shifts, str(tmp_path / "s.csv"))
    rows = pathlib.Path(csv).read_text().strip().splitlines()
    assert rows[0] == "frame,dx_px,dy_px,magnitude_px"
    assert len(rows) == 6                      # header + 5 frames

    data, _ = core.corrected_stack(str(drifting_tiff), shifts=result.shifts)
    tif = core.write_stack_tiff(data, str(tmp_path / "c.tif"))
    assert np.asarray(imread(tif)).shape[0] == 5


def test_a_single_frame_is_rejected(tmp_path):
    """One frame gives nothing to align, and says so rather than returning zeros."""
    from chisurf.core.fio.image import imread, imwrite

    path = tmp_path / "one.tif"
    imwrite(path, np.zeros((8, 8), dtype=np.float32))
    with pytest.raises(ValueError, match="at least two"):
        core.measure_drift(str(path))


def test_result_summary_is_json_friendly(drifting_tiff):
    """The summary dict survives a JSON round-trip (CLI and RPC use it)."""
    import json

    summary = core.measure_drift(str(drifting_tiff)).to_dict()
    restored = json.loads(json.dumps(summary))
    assert restored["n_frames"] == 5
    assert restored["kind"] == "image"
    assert len(restored["shifts"]) == 5


# --- photon streams --------------------------------------------------------
@pytest.mark.skipif(not _CLSM.exists(), reason="CLSM test data not present")
def test_photon_image_round_trips_through_an_injected_drift():
    """A known drift injected into a confocal image is measured and undone exactly.

    The correction moves photons between pixels, so the restored image must be
    bit-identical to the original and conserve every photon — the property that
    makes the corrected image still usable for lifetime and correlation work.
    """
    import tttrlib

    from chisurf.core.fluorescence.imaging.drift import (
        clsm_transform_pairs,
        correct_clsm_drift,
    )

    tttr = tttrlib.TTTR(str(_CLSM), "HT3")
    clsm = tttrlib.CLSMImage(tttr_data=tttr, channels=[0], fill=True)
    original = np.asarray(clsm.intensity).copy()
    n_frames = original.shape[0]

    injected = np.stack([np.array([2.0 * k, -1.0 * k]) for k in range(n_frames)])
    clsm.transform(clsm_transform_pairs(original.shape, -injected, mode="wrap"))
    drifted = np.asarray(clsm.intensity).copy()

    assert drifted.sum() == original.sum(), "injection must conserve photons"
    assert not np.array_equal(drifted, original)

    measured = correct_clsm_drift(clsm, reference="first")
    restored = np.asarray(clsm.intensity)

    np.testing.assert_allclose(measured, injected)
    np.testing.assert_array_equal(restored, original)
    assert restored.sum() == original.sum()


@pytest.mark.skipif(not _CLSM.exists(), reason="CLSM test data not present")
def test_correct_photon_image_returns_a_usable_clsm():
    """The plugin's photon-stream entry point returns a corrected CLSM image."""
    clsm, shifts = core.correct_photon_image(str(_CLSM), reading_routine="HT3")
    intensity = np.asarray(clsm.intensity)
    assert intensity.ndim == 3
    assert shifts.shape == (intensity.shape[0], 2)
    assert np.isfinite(shifts).all()


def test_photon_entry_point_rejects_an_image_file(drifting_tiff):
    """Pointing the photon path at a TIFF fails loudly rather than half-working."""
    with pytest.raises(ValueError, match="not a photon stream"):
        core.correct_photon_image(str(drifting_tiff))


# --- view model ------------------------------------------------------------
def test_view_model_drives_the_whole_flow(drifting_tiff, tmp_path):
    """Load, measure and export through the Qt-free view model."""
    from chisurf.plugins.microscopy.img_drift.gui.view_model import DriftViewModel

    vm = DriftViewModel()
    assert vm.set_filename(str(drifting_tiff)) is True
    assert vm.channel_names
    assert vm.compute() is True

    assert len(vm.shift_rows()) == 5
    assert len(vm.drift_series()) == 3          # dx, dy, |d|
    assert vm.before_image() is not None and vm.after_image() is not None
    assert "px" in vm.status

    written = vm.export(
        stack_path=str(tmp_path / "c.tif"), shifts_path=str(tmp_path / "s.csv")
    )
    assert set(written) == {"stack", "shifts"}
    assert pathlib.Path(written["stack"]).is_file()


def test_view_model_reports_a_missing_file_without_raising():
    """A bad path leaves the model in a clean, explained state."""
    from chisurf.plugins.microscopy.img_drift.gui.view_model import DriftViewModel

    vm = DriftViewModel()
    assert vm.set_filename("/definitely/not/here.tif") is False
    assert vm.compute() is False
    assert vm.result is None
    assert vm.shift_rows() == [] and vm.drift_series() == []


def test_view_spec_loads_and_names_real_sources():
    """Every plot/table source the view spec names exists on the view model."""
    from chisurf.plugins.microscopy.img_drift.gui.view_model import DriftViewModel

    vm = DriftViewModel()
    spec = vm.view_spec()
    assert spec is not None
    for attr in ("drift_series", "shift_rows", "before_image", "after_image",
                 "channel_names", "set_filename"):
        assert hasattr(vm, attr), f"view spec references missing {attr!r}"


# --- toolbox integration ---------------------------------------------------
def test_drift_is_registered_in_the_imaging_toolbox():
    """The tool is reachable from Image Tools, before the numbered pipeline.

    Drift correction is pre-processing: every per-pixel map in the numbered
    steps is built from frames that must already be aligned, so the panel has
    to sit ahead of them and inside the pipeline order the 'Next' button walks.
    """
    from chisurf.plugins.microscopy.imaging_tools.gui.tool import (
        IMAGING_PANELS,
        ImagingToolsTool,
    )

    names = [p["name"] for p in IMAGING_PANELS]
    roles = [p.get("role") for p in IMAGING_PANELS]
    assert "drift" in roles, "the drift panel is not registered in the toolbox"

    # ordered before every numbered analysis step
    assert names.index("Drift") < names.index("1. Intensity")
    order = ImagingToolsTool.PIPELINE_ORDER
    assert "drift" in order
    assert order.index("drift") < order.index("pixel_intensity")

    panel = IMAGING_PANELS[roles.index("drift")]
    assert callable(panel["factory"])
    assert panel.get("description"), "every navigation entry needs a description"
