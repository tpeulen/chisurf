"""Headless tests for the colocalization metrics, image loader, and plugin core."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.imaging import colocalization as coloc
from chisurf.core.fluorescence.imaging.image_source import load_image_stack
from chisurf.plugins.microscopy.img_coloc import core as plugin_core


def _blob_image(shape=(64, 64), centers=((20, 20), (40, 45)), sigma=5.0, amplitude=100.0):
    """Return a 2-D image with Gaussian blobs at *centers*."""
    y, x = np.mgrid[: shape[0], : shape[1]]
    img = np.zeros(shape, dtype=float)
    for cy, cx in centers:
        img += amplitude * np.exp(-((y - cy) ** 2 + (x - cx) ** 2) / (2 * sigma**2))
    return img


# --- coefficients ------------------------------------------------------------


def test_pearson_limits():
    """PCC is +1 for identical, -1 for inverted, ~0 for independent channels."""
    rng = np.random.default_rng(0)
    a = rng.normal(size=5000)
    assert coloc.pearson(a, a) == pytest.approx(1.0)
    assert coloc.pearson(a, -a) == pytest.approx(-1.0)
    assert abs(coloc.pearson(a, rng.normal(size=5000))) < 0.05


def test_manders_overlap_and_fractions():
    """MOC is 1 for proportional channels; M1/M2 report the split fractions."""
    a = np.array([[0.0, 4.0], [2.0, 0.0]])
    assert coloc.manders_overlap(a, 3.0 * a) == pytest.approx(1.0)
    # B present only where A == 4 → all of A's intensity there is 4/6.
    b = np.array([[0.0, 1.0], [0.0, 0.0]])
    m1, m2 = coloc.manders_fractions(a, b)
    assert m1 == pytest.approx(4.0 / 6.0)
    assert m2 == pytest.approx(1.0)


def test_li_icq_signs():
    """ICQ is positive for dependent and negative for segregated staining."""
    a = np.linspace(0.0, 1.0, 400)
    assert coloc.li_icq(a, a) == pytest.approx(0.5, abs=1e-9)
    assert coloc.li_icq(a, -a) == pytest.approx(-0.5, abs=1e-9)


def test_spearman_is_rank_based():
    """Spearman stays 1 under a monotonic non-linear transform where PCC drops."""
    a = np.linspace(0.1, 10.0, 200)
    b = np.exp(a)
    assert coloc.spearman(a, b) == pytest.approx(1.0)
    assert coloc.pearson(a, b) < 0.9


def test_estimate_background_quantile():
    """The background estimate is the requested low quantile of the image."""
    img = np.arange(100, dtype=float).reshape(10, 10)
    assert coloc.estimate_background(img, 0.05) == pytest.approx(np.quantile(img, 0.05))


def test_costes_threshold_separates_background():
    """Costes' thresholds land above a pure-noise background and below the signal."""
    rng = np.random.default_rng(1)
    signal = _blob_image()
    a = signal + rng.normal(5.0, 1.0, signal.shape)
    b = 0.8 * signal + rng.normal(5.0, 1.0, signal.shape)
    out = coloc.costes_threshold(a, b)
    assert np.isfinite(out["threshold_a"])
    assert out["slope"] > 0
    assert 0.0 < out["threshold_a"] < float(a.max())


def test_costes_significance_separates_real_from_random():
    """The randomization test passes for real colocalization and fails for noise."""
    rng = np.random.default_rng(2)
    signal = _blob_image()
    a = signal + rng.normal(0.0, 1.0, signal.shape)
    b = signal + rng.normal(0.0, 1.0, signal.shape)
    real = coloc.costes_significance(a, b, block=4, n_randomizations=50, seed=3)
    assert real["p_value"] > 0.95
    noise_a = rng.normal(size=signal.shape)
    noise_b = rng.normal(size=signal.shape)
    random = coloc.costes_significance(noise_a, noise_b, block=4, n_randomizations=50, seed=3)
    assert random["p_value"] < 0.95


def test_van_steensel_peaks_at_the_true_offset():
    """The CCF profile peaks at the shift that realigns a translated channel."""
    signal = _blob_image()
    shifted = np.roll(signal, 6, axis=1)
    out = coloc.van_steensel(signal, shifted, max_shift=12)
    assert out["peak_shift"] == 6
    aligned = coloc.van_steensel(signal, signal, max_shift=12)
    assert aligned["peak_shift"] == 0


def test_joint_histogram_shape_and_counts():
    """The joint histogram bins every finite pixel pair."""
    rng = np.random.default_rng(4)
    a = rng.random(1000)
    b = rng.random(1000)
    hist = coloc.joint_histogram(a, b, bins=16)
    assert hist["histogram"].shape == (16, 16)
    assert hist["histogram"].sum() == 1000


def test_colocalization_metrics_gate_selects_pixels():
    """A scatter gate reduces the pixel count and yields its own coefficients."""
    signal = _blob_image()
    result = coloc.colocalization_metrics(signal, signal, threshold_a=1.0, threshold_b=1.0)
    assert result.metrics["pearson"] == pytest.approx(1.0)
    assert result.metrics["n_pixels"] < signal.size
    gated = coloc.colocalization_metrics(
        signal, signal, threshold_a=1.0, threshold_b=1.0, gate=(50.0, 100.0, 50.0, 100.0)
    )
    assert gated.metrics["n_pixels_gated"] < gated.metrics["n_pixels"]
    assert np.isfinite(gated.metrics["gated_pearson"])


# --- image loading + plugin core ---------------------------------------------


@pytest.fixture
def two_channel_tiff(tmp_path):
    """Write a 2-frame, 2-channel TIFF stack and return ``(path, channel_a, channel_b)``."""
    tifffile = pytest.importorskip("tifffile")
    signal = _blob_image()
    a = np.stack([signal, signal])
    b = np.stack([0.7 * signal, 0.7 * signal])
    stack = np.stack([a, b], axis=1).astype(np.float32)  # (T, C, Y, X)
    path = tmp_path / "coloc.tif"
    tifffile.imwrite(str(path), stack, imagej=True, metadata={"axes": "TCYX"})
    return path, signal, 0.7 * signal


def test_load_image_stack_reads_tcyx(two_channel_tiff):
    """A TIFF hyperstack is loaded as (frame, channel, y, x) with named channels."""
    path, _, _ = two_channel_tiff
    stack = load_image_stack(path)
    assert stack.data.shape == (2, 2, 64, 64)
    assert stack.channel_names == ["ch0", "ch1"]
    assert stack.kind == "image"
    # Summing both frames doubles the single-frame intensity.
    assert stack.image(0).sum() == pytest.approx(2 * stack.image(0, frame=0).sum(), rel=1e-5)


def test_load_image_stack_single_plane(tmp_path):
    """A plain 2-D image becomes a one-frame, one-channel stack."""
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "single.tif"
    tifffile.imwrite(str(path), _blob_image().astype(np.float32))
    stack = load_image_stack(path)
    assert stack.data.shape == (1, 1, 64, 64)


def test_compute_colocalization_on_tiff(two_channel_tiff):
    """The plugin core recovers a perfect correlation for proportional channels."""
    path, _, _ = two_channel_tiff
    out = plugin_core.compute_colocalization(path, 0, 1, threshold_a=1.0, threshold_b=1.0)
    assert out["metrics"]["pearson"] == pytest.approx(1.0, abs=1e-4)
    assert out["metrics"]["manders_overlap"] == pytest.approx(1.0, abs=1e-4)
    assert out["channel_names"] == ["ch0", "ch1"]
    assert out["shape"] == (64, 64)


def test_compute_colocalization_needs_two_channels(tmp_path):
    """A single-channel image is rejected with a clear error."""
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "one.tif"
    tifffile.imwrite(str(path), _blob_image().astype(np.float32))
    with pytest.raises(ValueError, match="needs two"):
        plugin_core.compute_colocalization(path, 0, 1)


def test_metric_rows_are_ordered_and_formatted(two_channel_tiff):
    """The presentation table lists the coefficients in order with readable values."""
    path, _, _ = two_channel_tiff
    out = plugin_core.compute_colocalization(path, 0, 1)
    rows = plugin_core.metric_rows(out["metrics"])
    names = [r["name"] for r in rows]
    assert names[0].startswith("Pearson")
    assert all(isinstance(r["value"], str) for r in rows)


def test_view_model_runs_headless(two_channel_tiff):
    """The Qt-free view-model computes, fills the channel list, and gates."""
    from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel

    path, _, _ = two_channel_tiff
    vm = ColocViewModel()
    vm.set_filename(str(path))
    assert vm.compute() is True
    assert vm.channel_names() == ["ch0", "ch1"]
    assert vm.image_a() is not None
    assert vm.histogram_image() is not None
    assert vm.metric_rows()
    vm.set_gate_from_rect(0, 0, vm.bins, vm.bins)
    assert vm.gate_enabled is True
    assert vm.gate_rect() is not None


# --- detector setup + view spec ----------------------------------------------


def test_setup_windows_become_channels():
    """A picked detector setup offers its named windows as channels immediately."""
    from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel

    vm = ColocViewModel()
    vm.apply_setup_settings(
        {
            "name": "demo",
            "detectors": {
                "green": {"chs": [0, 1], "micro_time_ranges": []},
                "red": {"chs": [4, 5], "micro_time_ranges": []},
            },
        }
    )
    assert vm.setup_name == "demo"
    # Names are available before any file is loaded — the setup defines them.
    assert vm.channel_names() == ["green", "red"]
    assert vm.detectors["green"]["chs"] == [0, 1]
    vm.apply_setup_settings({"name": "", "detectors": {}})
    assert vm.channel_names() == []


def test_setup_windows_ignored_for_camera_images(two_channel_tiff):
    """Detector windows apply to photon streams only; a TIFF keeps its own channels."""
    from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel

    path, _, _ = two_channel_tiff
    vm = ColocViewModel()
    vm.apply_setup_settings({"name": "demo", "detectors": {"green": {"chs": [0]}}})
    vm.set_filename(str(path))
    assert vm.compute() is True
    assert vm.channel_names() == ["ch0", "ch1"]


def test_view_spec_parses_and_binds_every_attribute():
    """Every attribute the view spec binds exists on the view-model, with a tooltip."""
    from chisurf.core.dataspec import Section
    from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel

    vm = ColocViewModel()
    spec = vm.view_spec()

    def walk(sections):
        for section in sections:
            yield section
            yield from walk(getattr(section, "sections", ()) or ())

    bound = [s for s in walk(spec.sections) if isinstance(s, Section) and getattr(s, "attr", None)]
    assert bound, "view spec binds no attributes"
    for section in bound:
        assert hasattr(vm, section.attr), f"missing model attribute {section.attr!r}"
        assert getattr(section, "description", ""), f"{section.attr!r} has no tooltip"


def test_help_resource_ships_next_to_the_view_spec():
    """The ? modal's help file sits next to the view spec and covers the method.

    The button itself lives in the tool's toolbar (``add_toolbar_help``), not in a
    panel, so only the shipped resource is checked here — Qt-free.
    """
    from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel

    vm = ColocViewModel()
    help_md = vm._view_json.parent / "help.md"
    assert help_md.is_file()
    text = help_md.read_text()
    for expected in ("Workflow", "Pearson", "Manders", "Costes", "van Steensel"):
        assert expected in text


def test_settings_panel_has_no_inline_text_blocks():
    """Status/help never occupy panel space — no `info` section in the spec.

    Live status goes to the host's status bar and long help behind the toolbar's
    ``?`` modal; an inline text block would just eat the form.
    """
    from chisurf.core.dataspec import InfoSection
    from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel

    def walk(sections):
        for section in sections:
            yield section
            yield from walk(getattr(section, "sections", ()) or ())

    spec = ColocViewModel().view_spec()
    assert not [s for s in walk(spec.sections) if isinstance(s, InfoSection)]


def test_data_source_section_is_used_for_the_input_file():
    """The input file uses the shared data-source control (disk + database + drop)."""
    from chisurf.core.dataspec import CustomSection
    from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel

    def walk(sections):
        for section in sections:
            yield section
            yield from walk(getattr(section, "sections", ()) or ())

    spec = ColocViewModel().view_spec()
    sources = [
        s for s in walk(spec.sections) if isinstance(s, CustomSection) and s.key == "data_source"
    ]
    assert len(sources) == 1
    options = sources[0].options
    assert options["attr"] == "filename"
    assert options["call"] == "set_filename"
    assert options.get("mmfdb_kinds"), "the database picker must be offered"
    assert options.get("description")


# --- 2-D CCF, intensity profiles, spatial ROI --------------------------------


def test_cross_correlation_2d_finds_a_diagonal_offset():
    """The 2-D plane peaks at the (dy, dx) that realigns a diagonally shifted channel."""
    signal = _blob_image()
    shifted = np.roll(signal, (5, -3), axis=(0, 1))
    out = coloc.cross_correlation_2d(signal, shifted, max_shift=12)
    assert (out["peak_dy"], out["peak_dx"]) == (5, -3)
    # A purely vertical offset is invisible to the horizontal-only profile …
    vertical = np.roll(signal, 4, axis=0)
    assert coloc.van_steensel(signal, vertical, max_shift=12)["peak_shift"] == 0
    # … but not to the plane.
    assert coloc.cross_correlation_2d(signal, vertical, max_shift=12)["peak_dy"] == 4


def test_cross_correlation_2d_agrees_with_the_1d_profile():
    """The plane's central row reproduces the van Steensel profile."""
    signal = _blob_image()
    shifted = np.roll(signal, 6, axis=1)
    plane = coloc.cross_correlation_2d(signal, shifted, max_shift=10)
    profile = coloc.van_steensel(signal, shifted, max_shift=10)
    assert plane["peak_dy"] == 0
    assert plane["peak_dx"] == profile["peak_shift"]
    assert plane["peak"] == pytest.approx(profile["peak_ccf"], abs=0.02)


def test_pearson_profile_resolves_correlation_along_intensity():
    """Correlation carried only by bright pixels shows up in the profile, not in one PCC."""
    rng = np.random.default_rng(5)
    signal = _blob_image()
    a = signal + rng.normal(0.0, 3.0, signal.shape)
    b = signal + rng.normal(0.0, 3.0, signal.shape)
    profile = coloc.pearson_profile(a, b, bins=8, versus="a")
    values = profile["pearson"]
    counts = profile["counts"]
    assert profile["x"].size == 8
    assert counts.sum() <= a.size
    assert np.isfinite(values).any()
    # The dim bins are dominated by independent noise, the bright ones by signal.
    finite = np.isfinite(values)
    assert values[finite][0] < 0.5
    assert np.nanmax(values) > values[finite][0]


def test_pearson_profile_versus_ratio_is_supported():
    """Binning by the A/B intensity ratio works and reports its axis."""
    signal = _blob_image() + 1.0
    profile = coloc.pearson_profile(signal, 0.5 * signal, bins=6, versus="ratio")
    assert profile["versus"] == "ratio"
    assert profile["x"].size == 6


def test_roi_restricts_every_coefficient():
    """A spatial ROI selects which pixels are analysed at all."""
    rng = np.random.default_rng(6)
    shape = (64, 64)
    a = rng.random(shape) + 1.0
    b = a.copy()
    # Right half is anti-correlated with the left half's relation.
    b[:, 32:] = 2.0 - a[:, 32:]
    left = np.zeros(shape, dtype=bool)
    left[:, :32] = True
    right = ~left

    whole = coloc.colocalization_metrics(a, b)
    in_left = coloc.colocalization_metrics(a, b, roi=left)
    in_right = coloc.colocalization_metrics(a, b, roi=right)

    assert in_left.metrics["n_pixels_total"] == 32 * 64
    assert in_left.metrics["roi_area_fraction"] == pytest.approx(0.5)
    assert in_left.metrics["pearson"] == pytest.approx(1.0, abs=1e-6)
    assert in_right.metrics["pearson"] == pytest.approx(-1.0, abs=1e-6)
    # The whole image mixes both populations, so it sits between them.
    assert in_right.metrics["pearson"] < whole.metrics["pearson"] < in_left.metrics["pearson"]


def test_roi_is_reported_and_optional():
    """An empty or absent ROI leaves the analysis on the whole image."""
    signal = _blob_image()
    empty = np.zeros_like(signal, dtype=bool)
    result = coloc.colocalization_metrics(signal, signal, roi=empty)
    assert result.roi is None
    assert "roi_area_fraction" not in result.metrics
    with pytest.raises(ValueError, match="same shape"):
        coloc.colocalization_metrics(signal, signal, roi=np.zeros((3, 3), dtype=bool))


def test_view_model_exposes_the_new_views(two_channel_tiff):
    """The 2-D CCF map, the profiles and the ROI brush are reachable from the tool."""
    from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel

    path, _, _ = two_channel_tiff
    vm = ColocViewModel()
    vm.ccf_max_shift = 8
    vm.set_filename(str(path))
    assert vm.compute() is True
    assert vm.ccf_map_image() is not None
    assert vm.profile_series()
    # The brush paints into a mask of the image's shape …
    assert np.asarray(vm.roi_mask).shape == vm.image_a().shape
    assert vm.brush_kernel().shape == (vm.brush_size, vm.brush_size)
    # … and painting restricts the analysed pixel count.
    vm.roi_mask[:32, :] = 1.0
    vm.on_roi_drawn()
    assert vm._metrics["n_pixels_total"] == 32 * 64
    vm.clear_roi()
    assert vm._metrics["n_pixels_total"] == 64 * 64


# --- object-based colocalization ---------------------------------------------


def _puncta_image(centres, shape=(128, 128), sigma=2.0, amplitude=100.0):
    """Return an image with Gaussian puncta at *centres*."""
    y, x = np.mgrid[: shape[0], : shape[1]]
    img = np.zeros(shape, dtype=float)
    for cy, cx in centres:
        img += amplitude * np.exp(-((y - cy) ** 2 + (x - cx) ** 2) / (2 * sigma**2))
    return img


def test_segment_objects_counts_and_locates_puncta():
    """Segmentation finds every punctum and puts its centroid on the true centre."""
    centres = [(20, 30), (60, 70), (100, 40)]
    objects = coloc.segment_objects(_puncta_image(centres))
    assert objects.count == 3
    found = sorted(tuple(np.round(c).astype(int)) for c in objects.centroids)
    assert found == sorted(centres)
    assert (objects.areas > 0).all()
    assert (objects.intensities > 0).all()


def test_segment_objects_drops_small_specks():
    """``min_size`` discards noise-sized detections."""
    image = _puncta_image([(30, 30)], sigma=2.0)
    image[100, 100] = 1000.0  # a single hot pixel
    assert coloc.segment_objects(image, min_size=1).count == 2
    assert coloc.segment_objects(image, min_size=4).count == 1


def test_object_colocalization_counts_partners():
    """The coincident fraction reflects how many objects have a partner in range."""
    a_centres = [(20, 20), (20, 60), (60, 20), (60, 60), (100, 100)]
    # Four partners displaced by 1 px, the fifth punctum of A is alone.
    b_centres = [(21, 20), (21, 60), (61, 20), (61, 60)]
    out = coloc.object_colocalization(
        _puncta_image(a_centres), _puncta_image(b_centres), distance=3.0
    )
    metrics = out["metrics"]
    assert metrics["n_objects_a"] == 5
    assert metrics["n_objects_b"] == 4
    assert metrics["object_fraction_a_near_b"] == pytest.approx(4 / 5)
    assert metrics["object_fraction_b_near_a"] == pytest.approx(1.0)
    assert metrics["object_median_distance_b"] == pytest.approx(1.0, abs=0.2)


def test_object_tolerance_controls_what_counts_as_coincident():
    """Objects 5 px apart coincide at a 6 px tolerance and not at a 2 px one."""
    a = _puncta_image([(40, 40)])
    b = _puncta_image([(45, 40)])
    near = coloc.object_colocalization(a, b, distance=6.0)["metrics"]
    far = coloc.object_colocalization(a, b, distance=2.0)["metrics"]
    assert near["object_fraction_a_near_b"] == pytest.approx(1.0)
    assert far["object_fraction_a_near_b"] == pytest.approx(0.0)


def test_object_centroid_inside_and_overlap():
    """Centre-inside-object and area-overlap agree for perfectly coincident puncta."""
    image = _puncta_image([(50, 50), (80, 20)])
    out = coloc.object_colocalization(image, image, distance=1.0)
    metrics = out["metrics"]
    assert metrics["object_fraction_a_in_b"] == pytest.approx(1.0)
    assert metrics["object_mean_overlap_a"] == pytest.approx(1.0)
    assert metrics["object_median_distance_a"] == pytest.approx(0.0, abs=1e-6)


def test_object_analysis_is_reachable_from_the_metrics_entry_point():
    """``colocalization_metrics`` folds the object metrics into the same table."""
    a = _puncta_image([(30, 30), (70, 70)])
    b = _puncta_image([(30, 31)])
    result = coloc.colocalization_metrics(a, b, object_analysis=True, object_distance=3.0)
    assert result.objects
    assert result.metrics["n_objects_a"] == 2
    assert result.metrics["object_fraction_a_near_b"] == pytest.approx(0.5)
    rows = {r["name"] for r in plugin_core.metric_rows(result.metrics)}
    assert "Objects in A" in rows
    assert "Objects: fraction A with B partner" in rows


def test_object_distance_histogram_bins_the_distances():
    """The distance histogram counts every finite nearest-neighbour distance."""
    histogram = coloc.object_distance_histogram([1.0, 1.5, 2.0, np.nan], bins=4)
    assert histogram["counts"].sum() == 3
    assert histogram["x"].size == 4


def test_object_analysis_respects_the_roi():
    """A spatial ROI excludes objects outside it from the object analysis too."""
    a = _puncta_image([(20, 20), (100, 100)])
    b = _puncta_image([(20, 21), (100, 101)])
    roi = np.zeros(a.shape, dtype=bool)
    roi[:64, :64] = True
    result = coloc.colocalization_metrics(a, b, object_analysis=True, roi=roi)
    assert result.metrics["n_objects_a"] == 1
    assert result.metrics["n_objects_b"] == 1


def test_view_model_exposes_the_object_views():
    """The object map and the distance histogram reach the tool."""
    import tifffile

    from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel

    a = _puncta_image([(30, 30), (70, 70), (100, 40)])
    b = _puncta_image([(30, 31), (70, 71)])
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/puncta.tif"
        tifffile.imwrite(
            path, np.stack([a, b]).astype(np.float32), imagej=True, metadata={"axes": "CYX"}
        )
        vm = ColocViewModel()
        vm.object_analysis = True
        vm.object_distance = 3.0
        vm.set_filename(path)
        assert vm.compute() is True
    assert vm._metrics["n_objects_a"] == 3
    assert vm._metrics["object_fraction_a_near_b"] == pytest.approx(2 / 3)
    label_map = vm.object_map_image()
    assert label_map is not None
    assert set(np.unique(label_map)) <= {0.0, 1.0, 2.0, 3.0}
    assert 3.0 in np.unique(label_map)  # coincident pixels are marked
    assert vm.object_distance_series()


# --- CLI (the headless surface) ----------------------------------------------


@pytest.fixture
def cli_runner():
    """Return a click test runner."""
    from click.testing import CliRunner

    return CliRunner()


def test_cli_reports_the_coefficients(cli_runner, two_channel_tiff):
    """The default CLI run prints a readable coefficient table."""
    from chisurf.plugins.microscopy.img_coloc.cli import cli

    path, _, _ = two_channel_tiff
    result = cli_runner.invoke(cli, [str(path), "-a", "0", "-b", "1", "--auto-background"])
    assert result.exit_code == 0, result.output
    assert "Pearson PCC (thresholded)" in result.output
    assert "channels ['ch0', 'ch1']" in result.output


def test_cli_json_output_is_machine_readable(cli_runner, two_channel_tiff):
    """``--json`` emits the full metric mapping."""
    import json

    from chisurf.plugins.microscopy.img_coloc.cli import cli

    path, _, _ = two_channel_tiff
    result = cli_runner.invoke(cli, [str(path), "-a", "0", "-b", "1", "--json"])
    assert result.exit_code == 0, result.output
    metrics = json.loads(result.output)
    assert metrics["pearson"] == pytest.approx(1.0, abs=1e-4)
    assert "manders_m1" in metrics


def test_cli_writes_a_results_file(cli_runner, two_channel_tiff, tmp_path):
    """``-o`` writes the metrics as JSON next to whatever the user asked for."""
    import json

    from chisurf.plugins.microscopy.img_coloc.cli import cli

    path, _, _ = two_channel_tiff
    out = tmp_path / "metrics.json"
    result = cli_runner.invoke(cli, [str(path), "-a", "0", "-b", "1", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "pearson" in json.loads(out.read_text())


def test_cli_exposes_every_analysis(cli_runner, tmp_path):
    """Costes, the shift profile, the 2-D plane, profiles and objects are all reachable."""
    import json

    tifffile = pytest.importorskip("tifffile")
    from chisurf.plugins.microscopy.img_coloc.cli import cli

    a = _puncta_image([(30, 30), (70, 70), (100, 40)])
    b = _puncta_image([(30, 31), (70, 71)])
    path = tmp_path / "puncta.tif"
    tifffile.imwrite(
        str(path), np.stack([a, b]).astype(np.float32), imagej=True, metadata={"axes": "CYX"}
    )

    result = cli_runner.invoke(
        cli,
        [
            str(path),
            "-a",
            "0",
            "-b",
            "1",
            "--auto-background",
            "--costes-threshold",
            "--costes-test",
            "--randomizations",
            "20",
            "--ccf-shift",
            "6",
            "--ccf-2d",
            "--profiles",
            "--objects",
            "--object-distance",
            "3",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    metrics = json.loads(result.output)
    assert "costes_p_value" in metrics
    assert "ccf_peak_shift" in metrics and "ccf2d_peak_dx" in metrics
    assert metrics["n_objects_a"] == 3
    assert metrics["object_fraction_a_near_b"] == pytest.approx(2 / 3)


def test_cli_rejects_a_single_channel_image(cli_runner, tmp_path):
    """A one-channel file fails loudly instead of reporting nonsense."""
    tifffile = pytest.importorskip("tifffile")
    from chisurf.plugins.microscopy.img_coloc.cli import cli

    path = tmp_path / "one.tif"
    tifffile.imwrite(str(path), _blob_image().astype(np.float32))
    result = cli_runner.invoke(cli, [str(path)])
    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert "needs two" in str(result.exception)


def test_cli_warns_when_no_pixel_passes(cli_runner, two_channel_tiff):
    """An impossible threshold produces the warning rather than a silent 'n/a' table."""
    from chisurf.plugins.microscopy.img_coloc.cli import cli

    path, _, _ = two_channel_tiff
    result = cli_runner.invoke(
        cli, [str(path), "-a", "0", "-b", "1", "--threshold-a", "1e9", "--threshold-b", "1e9"]
    )
    assert result.exit_code == 0, result.output
    assert "warning:" in result.output
