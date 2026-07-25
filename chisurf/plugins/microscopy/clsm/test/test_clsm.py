"""Headless tests for the CLSM plugin (core / api / services / cli / gui).

The image tests use the real CLSM fixtures under ``<repo>/test/data/clsm``; they
skip cleanly when ``tttrlib`` or the data files are unavailable.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

# <repo>/chisurf/plugins/microscopy/clsm/test/test_clsm.py -> parents[5] == <repo>
REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
DATA_DIR = REPO_ROOT / "test" / "data" / "clsm"
SP5 = DATA_DIR / "Leica_SP5.ptu"


def _require_data():
    pytest.importorskip("tttrlib")
    if not SP5.exists():
        pytest.skip(f"CLSM test data not available: {SP5}")


# ── pure helpers (no data needed) ───────────────────────────────────────────


def test_frc_and_noise_pure():
    from chisurf.plugins.microscopy.clsm.core import frc

    rng = np.random.RandomState(0)
    a, b = rng.rand(64, 64), rng.rand(64, 64)
    density, bins = frc.compute_frc(a, b)
    assert density.shape == bins.shape
    assert np.isclose(frc.gaussian_kernel(7, 3).sum(), 1.0)
    assert np.all(frc.counting_noise(np.array([0.0, 4.0, 9.0])) == np.array([1.0, 2.0, 3.0]))


def test_brush_kernel_deselect_is_negative():
    from chisurf.plugins.microscopy.clsm.core import imaging

    assert imaging.brush_kernel(7, 3, select=False).min() < 0
    assert imaging.brush_kernel(7, 3, select=True).min() >= 0


def test_setups_presets():
    from chisurf.plugins.microscopy.clsm.core import setups

    presets = setups.builtin_setups()
    assert "Leica SP5" in presets
    assert presets["Leica SP5"]["frame_marker"] == [4, 6]


def test_contract_descriptor():
    from chisurf.plugins.microscopy.clsm.api import contract

    desc = contract.contract_descriptor()
    assert desc["plugin_id"] == "clsm"
    assert contract.METHOD_DECAY in desc["methods"]


# ── core / api with real data ───────────────────────────────────────────────


def test_core_image_representation_decay_frc():
    _require_data()
    import tttrlib

    from chisurf.plugins.microscopy.clsm.api.models import ClsmSetup
    from chisurf.plugins.microscopy.clsm.core import frc, imaging, setups

    tttr = tttrlib.TTTR(str(SP5), "PTU")
    preset = setups.builtin_setups()["Leica SP5"]
    detected = setups.read_clsm_markers(tttr)
    setup = ClsmSetup.from_preset(preset, channels=[0, 1])
    if detected.get("pixel_per_line"):
        setup.pixel_per_line = detected["pixel_per_line"]

    clsm = imaging.build_clsm_image(tttr, setup)
    assert clsm.n_frames > 0 and clsm.n_lines > 0 and clsm.n_pixel > 0

    image = imaging.representation(clsm, tttr, "Intensity", 1)
    assert image.ndim == 3
    current, s1, s2 = imaging.reduce_frames(image, "sum")
    assert current.shape == s1.shape == s2.shape

    mask = (current > current.mean()).astype(np.uint8)
    t, y, ey = imaging.decay_of_selection(clsm, tttr, mask, tac_coarsening=4, stack_frames=True)
    assert t.shape == y.shape == ey.shape
    assert y.sum() > 0

    density, bins = frc.compute_frc(s1, s2)
    assert density.shape == bins.shape


def test_mean_micro_time_is_in_ns_and_discriminates():
    """The mean-micro-time map is in ns and *Min #Ph* discards pixels.

    Pins RF-030: the ``get_mean_micro_time`` call used to pass ``n_ph_min`` into
    ``microtime_resolution``, which scaled the whole image by *Min #Ph* and
    discriminated nothing.
    """
    _require_data()
    import tttrlib

    from chisurf.plugins.microscopy.clsm.api.models import ClsmSetup
    from chisurf.plugins.microscopy.clsm.core import imaging, setups

    tttr = tttrlib.TTTR(str(SP5), "PTU")
    preset = setups.builtin_setups()["Leica SP5"]
    detected = setups.read_clsm_markers(tttr)
    setup = ClsmSetup.from_preset(preset, channels=[0, 1])
    if detected.get("pixel_per_line"):
        setup.pixel_per_line = detected["pixel_per_line"]
    clsm = imaging.build_clsm_image(tttr, setup)

    res_ns = imaging.micro_time_resolution_ns(tttr)
    assert 0.0 < res_ns < 1.0  # a TCSPC channel is sub-nanosecond
    span_ns = res_ns * tttr.get_header().number_of_micro_time_channels

    low = imaging.representation(clsm, tttr, "Mean micro time", 1)
    high = imaging.representation(clsm, tttr, "Mean micro time", 20)
    assert low.ndim == high.ndim == 3

    # A mean arrival time lies inside the micro-time window, and discriminated
    # pixels come back as 0.0 rather than as a negative resolution multiple.
    for image in (low, high):
        assert image.min() >= 0.0
        assert image.max() <= span_ns

    # Raising *Min #Ph* must discard pixels, not rescale the image.
    n_low = int((low > 0.0).sum())
    n_high = int((high > 0.0).sum())
    assert n_high < n_low
    assert not np.allclose(high.max(), low.max() * 20.0)


def test_api_orchestration_and_save(tmp_path):
    _require_data()
    from chisurf.plugins.microscopy.clsm import api

    info = api.image_info(str(SP5), setup_name="Leica SP5", channels=[0, 1])
    assert info["n_frames"] > 0
    assert info["micro_time_resolution_ns"] > 0

    out = tmp_path / "decay.txt"
    dec = api.extract_decay(
        str(SP5),
        setup_name="Leica SP5",
        channels=[0, 1],
        threshold=0.5,
        tac_coarsening=4,
        output_path=str(out),
    )
    assert dec["n_photons"] > 0
    assert out.exists()
    assert len(dec["counts"]) == len(dec["time_ns"])

    frc = api.compute_frc(str(SP5), setup_name="Leica SP5", channels=[0, 1])
    assert len(frc["correlation"]) == len(frc["frequency"])


# ── services / client ───────────────────────────────────────────────────────


def test_register_services():
    from chisurf.plugins.microscopy.clsm.api import contract
    from chisurf.plugins.microscopy.clsm.backend.services import register_services
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    register_services(dispatcher)
    for method in contract.ALL_METHODS:
        assert dispatcher.has_method(method)


def test_client_inprocess_roundtrip():
    from chisurf.plugins.microscopy.clsm.client import ClsmClient

    client = ClsmClient()
    assert client.contract()["plugin_id"] == "clsm"
    assert "Leica SP5" in client.setups()


def test_client_decay_real_data():
    _require_data()
    from chisurf.plugins.microscopy.clsm.client import ClsmClient

    dec = ClsmClient().decay(str(SP5), setup_name="Leica SP5", channels=[0, 1], threshold=0.5)
    assert dec["n_photons"] > 0


# ── cli ─────────────────────────────────────────────────────────────────────


def test_cli_contract_and_setups():
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.clsm.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["contract"])
    assert result.exit_code == 0
    assert "clsm" in result.output

    result = runner.invoke(cli, ["setups", "--json"])
    assert result.exit_code == 0
    assert "Leica SP5" in result.output


# ── view-model (no Qt) ──────────────────────────────────────────────────────


def test_view_model_workflow():
    _require_data()
    from chisurf.plugins.microscopy.clsm.gui.view_model import ClsmViewModel

    vm = ClsmViewModel()
    events: list[str] = []
    vm.add_observer(events.append)

    vm.apply_preset("Leica SP5")
    vm.setup.channels_text = "0,1"
    vm.load_tttr(str(SP5))
    assert vm.setup.pixel_per_line > 0  # auto-detected

    vm.add_clsm()
    vm.add_representation()
    assert vm.current_image is not None

    vm.selection_mask = (vm.current_image > vm.current_image.mean()).astype(np.float64)
    decay = vm.recompute_decay()
    assert decay is not None and np.sum(decay["counts"]) > 0
    vm.add_decay_curve()
    assert len(vm.decay_series()) == 2  # saved curve + current selection
    assert len(vm.frc_series()) == 1
    assert {"setup", "clsm", "image", "decay"} <= set(events)


# ── regions (no data needed) ────────────────────────────────────────────────


def _painted_view_model():
    """Build a view model with a synthetic image and a painted selection."""
    from chisurf.plugins.microscopy.clsm.gui.view_model import ClsmViewModel

    vm = ClsmViewModel()
    image = np.zeros((16, 16), dtype=np.float64)
    image[4:8, 5:11] = 20.0
    vm.current_image = image
    vm.selection_mask = np.zeros_like(image)
    vm.selection_mask[4:8, 5:11] = 1.0
    return vm


def test_a_brushed_selection_is_a_region_and_can_be_measured():
    """The paint buffer, the saved region and the measurement are one system."""
    vm = _painted_view_model()

    roi = vm.selection_roi()
    assert roi is not None
    assert roi.to_mask((16, 16)).sum() == 24

    props = vm.region_properties()
    assert props.area == 24
    assert props.intensity_mean == 20.0
    assert props.centroid == (5.5, 7.5)
    # The list row says how big and how bright — the two numbers that decide
    # whether a selection is worth a decay.
    assert vm.region_summary() == "24 px, 20.0 ph/px"


def test_saved_regions_round_trip_through_the_selection():
    vm = _painted_view_model()
    vm.add_roi("cell")
    assert list(vm.rois) == ["cell"]
    assert vm.roi_entries() == [{"name": "cell", "summary": "24 px, 20.0 ph/px"}]

    vm.clear_selection()
    assert vm.selection_roi() is None

    vm.apply_roi("cell")
    np.testing.assert_array_equal(vm.selection_mask > 0, vm.rois["cell"].to_mask((16, 16)))

    vm.remove_roi("cell")
    assert vm.rois == {}


def test_regions_survive_a_file_round_trip(tmp_path):
    """JSON keeps the region itself; a mask image keeps only its pixels."""
    vm = _painted_view_model()
    vm.add_roi("cell")

    as_json = tmp_path / "cell.json"
    vm.save_roi("cell", str(as_json))
    vm.remove_roi("cell")
    vm.load_roi(str(as_json))
    assert "cell" in vm.rois
    np.testing.assert_array_equal(
        vm.rois["cell"].to_mask((16, 16)), vm.selection_roi().to_mask((16, 16))
    )

    pytest.importorskip("tifffile")
    as_mask = tmp_path / "cell.tif"
    vm.save_roi("cell", str(as_mask))
    vm.load_roi(str(as_mask), name="from_mask")
    np.testing.assert_array_equal(
        vm.rois["from_mask"].to_mask((16, 16)), vm.rois["cell"].to_mask((16, 16))
    )


def test_selection_array_accepts_a_region_or_an_array():
    """The one seam where a drawn region and a painted array meet."""
    from chisurf.core.roi import EllipseROI
    from chisurf.plugins.microscopy.clsm.core.imaging import selection_array

    from_roi = selection_array(EllipseROI(5, 5, 3), (12, 12))
    assert from_roi.dtype == np.uint8
    assert from_roi.sum() == 29

    painted = np.zeros((12, 12))
    painted[2:4, 2:4] = 7.0
    painted[6, 6] = -1.0  # a de-selected pixel, as the "erase" brush writes
    from_array = selection_array(painted, (12, 12))
    assert from_array.sum() == 4


# ── gui smoke (Qt) ──────────────────────────────────────────────────────────


def test_tool_widget_creation(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    from qtpy import QtWidgets

    from chisurf.plugins.microscopy.clsm.gui.tool import CLSMPixelSelect

    widget = CLSMPixelSelect()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert widget.model is not None
    assert widget.auto_form is not None
