"""Tests for the FRC resolution calculator: core, API, RPC, CLI and view model.

The images are written to disk as real TIFF stacks and read back through the
same seam the GUI uses, so the file path is exercised rather than mocked.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from chisurf.plugins.microscopy.img_frc import core


def _band_limited_stack(n_frames=8, size=128, cutoff=0.15, noise=1.0, seed=3, object_seed=1):
    """Return a frame stack of one band-limited object seen through independent noise.

    *object_seed* fixes the object, *seed* the noise: two stacks that share the
    former and differ in the latter are two acquisitions of the same sample,
    which is what a two-file FRC needs.
    """
    rng = np.random.default_rng(seed)
    field = np.random.default_rng(object_seed).normal(size=(size, size))
    fx = np.fft.fftfreq(size)[:, None]
    fy = np.fft.fftfreq(size)[None, :]
    truth = np.real(np.fft.ifft2(np.fft.fft2(field) * (np.sqrt(fx**2 + fy**2) <= cutoff)))
    truth = truth / truth.std()
    return np.stack(
        [truth + noise * rng.normal(size=truth.shape) for _ in range(n_frames)]
    )


@pytest.fixture()
def tiff_stack(tmp_path):
    """Write a band-limited stack to a multi-page TIFF and return its path."""
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "bandlimited.tif"
    tifffile.imwrite(str(path), _band_limited_stack().astype(np.float32))
    return path


def test_a_tiff_stack_resolves_its_band_limit(tiff_stack):
    """The measured resolution matches the cut-off the stack was built with."""
    result = core.analyse(str(tiff_stack))
    assert result.crossed
    assert result.kind == "image"
    assert result.n_frames == 8
    assert result.resolution == pytest.approx(1 / 0.15, rel=0.25)
    assert result.unit == "px"


def test_a_pixel_size_turns_pixels_into_nanometres(tiff_stack):
    """The same stack, quoted in nm, is the pixel answer times the pixel size."""
    in_pixels = core.analyse(str(tiff_stack))
    in_nm = core.analyse(str(tiff_stack), pixel_size_nm=25.0)
    assert in_nm.unit == "nm"
    assert in_nm.resolution == pytest.approx(25.0 * in_pixels.resolution, rel=1e-6)


def test_halves_are_two_independent_images_not_one(tiff_stack):
    """Even/odd must return different halves — the whole method rests on it."""
    a, b, info = core.halves(str(tiff_stack))
    assert a.shape == b.shape
    assert not np.allclose(a, b)
    assert info["n_frames"] == 8


def test_the_first_second_half_split_also_works(tiff_stack):
    """A detector with correlated neighbours still has an honest split."""
    result = core.analyse(str(tiff_stack), split="halves")
    assert result.crossed
    assert result.resolution == pytest.approx(1 / 0.15, rel=0.3)


def test_a_single_frame_cannot_be_split_by_frame(tmp_path):
    """One frame holds no second measurement; saying so beats returning 1.0."""
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "single.tif"
    tifffile.imwrite(str(path), _band_limited_stack(n_frames=1)[0].astype(np.float32))
    with pytest.raises(ValueError, match="at least two frames"):
        core.analyse(str(path))


def test_unknown_splits_and_missing_second_files_are_rejected(tiff_stack):
    """Both are caller mistakes that must not reach the maths."""
    with pytest.raises(ValueError, match="unknown split"):
        core.analyse(str(tiff_stack), split="diagonal")
    with pytest.raises(ValueError, match="second file"):
        core.analyse(str(tiff_stack), split="two_files")
    with pytest.raises(FileNotFoundError):
        core.analyse(str(tiff_stack.parent / "nope.tif"))


def test_two_files_correlates_two_acquisitions(tiff_stack, tmp_path):
    """The two-file split reads a second stack and correlates the two sums."""
    tifffile = pytest.importorskip("tifffile")
    second = tmp_path / "second.tif"
    tifffile.imwrite(str(second), _band_limited_stack(seed=99).astype(np.float32))  # same object, new noise
    result = core.analyse(str(tiff_stack), split="two_files", second_filename=str(second))
    assert result.crossed
    # Independent noise realisations of the same object: it still resolves the
    # band limit, and the source records both files.
    assert result.resolution == pytest.approx(1 / 0.15, rel=0.3)
    assert "+" in result.source


def test_the_summary_is_json_safe_and_leaves_the_images_out(tiff_stack):
    """An RPC caller asking for a resolution must not be sent megabytes of pixels."""
    payload = core.analyse(str(tiff_stack)).to_dict()
    json.dumps(payload)  # must not raise
    assert "half_1" not in payload
    assert payload["crossed"] is True
    assert len(payload["frequency"]) == len(payload["correlation"])


def test_csv_export_writes_every_ring(tiff_stack, tmp_path):
    """The exported table carries the curve, the threshold and the ring counts."""
    result = core.analyse(str(tiff_stack))
    path = core.write_csv(result, str(tmp_path / "frc.csv"))
    lines = pathlib.Path(path).read_text().strip().split("\n")
    assert lines[0] == "frequency_1/px,correlation,threshold,ring_pixels"
    assert len(lines) == len(result.frequency) + 1


def test_a_short_stack_can_be_forced_to_be_frames(tmp_path):
    """A four-frame TIFF is guessed to be four channels; the override fixes it.

    ``tifffile.imwrite`` labels a ``(4, y, x)`` float array ``"SYX"`` — sample
    planes, i.e. an RGB-like image — so the reader delivers one frame with four
    channels and a frame split has nothing to split. This is the ordinary case
    of a short time series, not a corner case.
    """
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "short.tif"
    tifffile.imwrite(str(path), _band_limited_stack(n_frames=4).astype(np.float32))

    with pytest.raises(ValueError, match="at least two frames"):
        core.analyse(str(path))

    result = core.analyse(str(path), axis_order="frames")
    assert result.n_frames == 4
    assert result.crossed
    assert result.resolution == pytest.approx(1 / 0.15, rel=0.3)


# ── photon streams ─────────────────────────────────────────────────────────
HT3 = pathlib.Path("test/data/clsm/PQ_Olympus_MFIS.ht3")


@pytest.mark.skipif(not HT3.is_file(), reason="CLSM photon-stream test file missing")
def test_a_photon_stream_is_measured_like_an_image():
    """A PTU/HT3 file is reconstructed into a scan image and split by frame.

    The same call as for a TIFF: the image-source seam hides which of the two it
    is, so every split, criterion and unit works on photons as well.
    """
    result = core.analyse(str(HT3), channel=0)
    assert result.kind == "tttr"
    assert result.n_frames == 40
    assert result.channel_names[0] == "ch0"
    assert result.crossed
    # A 256x256 confocal scan: the resolution is a few pixels — finer than the
    # field of view, coarser than one pixel, or the measurement is not a
    # measurement.
    assert 2.0 < result.resolution < 64.0


@pytest.mark.skipif(not HT3.is_file(), reason="CLSM photon-stream test file missing")
def test_two_detectors_of_one_photon_stream_correlate():
    """The channel split is the one that needs no frames at all."""
    result = core.analyse(
        str(HT3), split="channels", channel=0, channel_2=1, pixel_size_nm=80.0
    )
    assert result.crossed
    assert result.unit == "nm"
    assert 100.0 < result.resolution < 5000.0


@pytest.mark.skipif(not HT3.is_file(), reason="CLSM photon-stream test file missing")
def test_channels_can_be_named_rather_than_numbered():
    """Detector windows carry names; a caller should not have to count."""
    by_index = core.analyse(str(HT3), channel=1)
    by_name = core.analyse(str(HT3), channel="ch1")
    assert by_name.resolution == pytest.approx(by_index.resolution, rel=1e-9)


@pytest.mark.skipif(not HT3.is_file(), reason="CLSM photon-stream test file missing")
def test_the_cli_measures_a_photon_stream(tmp_path):
    """End to end on real photons: the headless path a batch script would take."""
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.img_frc.cli import cli

    result = CliRunner().invoke(
        cli, [str(HT3), "--channel", "ch0", "--pixel-size", "80", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["kind"] == "tttr"
    assert payload["unit"] == "nm"
    assert payload["resolution"] > 0


# ── RPC / client ───────────────────────────────────────────────────────────
def test_the_rpc_surface_answers_over_the_in_process_client(tiff_stack):
    """The GUI and the CLI both go through this path, so it is the real seam."""
    from chisurf.plugins.microscopy.img_frc.client import FrcClient

    client = FrcClient()
    assert client.describe()["plugin_id"] == "img_frc"
    assert "fixed_1/7" in client.criteria()["criteria"]
    payload = client.resolution(str(tiff_stack), pixel_size_nm=25.0)
    assert payload["unit"] == "nm"
    assert payload["resolution"] > 0


def test_rpc_errors_come_back_as_errors_not_as_exceptions(tmp_path):
    """A bad request must surface as a failed envelope the client can raise on."""
    from chisurf.plugins.microscopy.img_frc.client import FrcClient

    with pytest.raises(RuntimeError):
        FrcClient().resolution(str(tmp_path / "missing.tif"))


def test_every_declared_rpc_method_is_registered():
    """The manifest and the dispatcher must not drift apart."""
    from chisurf.core.plugin import load_manifest
    from chisurf.plugins.microscopy.img_frc.api import contract
    from chisurf.plugins.microscopy.img_frc.backend.services import (
        register_services,
    )

    manifest = load_manifest(pathlib.Path(__file__).parents[1] / "manifest.json")
    declared = {m.name for m in manifest.rpc_methods}
    assert declared == set(contract.ALL_METHODS)

    registered: dict = {}
    register_services(type("D", (), {"register": lambda self, n, h: registered.setdefault(n, h)})())
    assert set(registered) == set(contract.ALL_METHODS)


# ── CLI ────────────────────────────────────────────────────────────────────
def test_the_cli_prints_a_resolution(tiff_stack):
    """The headless path is the one a script or a methods section uses."""
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.img_frc.cli import cli

    result = CliRunner().invoke(cli, [str(tiff_stack), "--pixel-size", "25"])
    assert result.exit_code == 0, result.output
    assert "resolution:" in result.output
    assert "nm" in result.output


def test_the_cli_json_payload_parses(tiff_stack, tmp_path):
    """--json is for scripts, so it must be parseable and carry the curve."""
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.img_frc.cli import cli

    out = tmp_path / "curve.csv"
    result = CliRunner().invoke(
        cli, [str(tiff_stack), "--json", "--out-csv", str(out)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["criterion"] == "fixed_1/7"
    assert out.is_file()


def test_the_cli_fails_loudly_when_nothing_crosses(tmp_path):
    """A flat image resolves nothing; exit 0 would read as a measurement."""
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.img_frc.cli import cli

    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "noiseless.tif"
    # Eight identical frames: both halves are the same image, so the FRC is 1 at
    # every frequency and there is nothing to cross.
    stack = np.zeros((8, 32, 32), dtype=np.float32)
    stack[:, 8:24, 8:24] = 1.0
    tifffile.imwrite(str(path), stack)
    result = CliRunner().invoke(cli, [str(path)])
    assert result.exit_code != 0
    assert "never crosses" in result.output


# ── imaging toolbox ────────────────────────────────────────────────────────
def test_frc_is_a_step_of_the_imaging_toolbox():
    """It measures a recorded image, so it belongs in the pipeline — after Drift.

    Drift blurs the image and so lowers the measured resolution; measuring it on
    frames that are not yet aligned reports the drift, not the microscope.
    """
    from chisurf.plugins.microscopy.imaging_tools.gui.tool import (
        IMAGING_PANELS,
        ImagingToolsTool,
    )

    roles = [p.get("role") for p in IMAGING_PANELS]
    assert "frc" in roles
    assert roles.index("frc") > roles.index("drift")
    assert "frc" in ImagingToolsTool.PIPELINE_ORDER

    panel = IMAGING_PANELS[roles.index("frc")]
    assert callable(panel["factory"])
    assert panel["description"].strip()


def test_the_panel_adopts_the_toolbox_source_and_setup(tiff_stack):
    """Freely navigable steps must not start empty when a file is already loaded."""
    from chisurf.plugins.microscopy.img_frc.gui.view_model import FrcViewModel

    vm = FrcViewModel()
    vm.apply_pipeline_context({"source": str(tiff_stack), "hdf5": "/tmp/imaging.hdf5"})
    assert vm.filename == str(tiff_stack)
    assert vm.pipeline_hdf5 == "/tmp/imaging.hdf5"
    assert vm.channel_names  # the file was actually read, not just remembered

    vm.apply_setup_settings(
        {"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}}
    )
    assert set(vm.detectors) == {"green", "red"}


# ── view model ─────────────────────────────────────────────────────────────
def test_the_view_model_loads_measures_and_exports(tiff_stack, tmp_path):
    """Headless walk of the GUI path: no Qt, no window, same code."""
    from chisurf.plugins.microscopy.img_frc.gui.view_model import FrcViewModel

    vm = FrcViewModel()
    assert vm.frc_series() == []
    assert "Load a TIFF stack" in vm.summary_html()

    assert vm.set_filename(str(tiff_stack))
    assert vm.channel_names
    vm.pixel_size_nm = 25.0
    assert vm.compute()

    assert "nm" in vm.status
    # FRC, threshold and the crossing marker.
    assert len(vm.frc_series()) == 3
    assert vm.frc_series()[2]["no_line"] is True
    assert len(vm.ring_rows()) == len(vm.result.frequency)
    assert vm.half_1_image() is not None and vm.half_2_image() is not None
    assert "Criterion" in vm.summary_html()
    assert pathlib.Path(vm.export_csv(str(tmp_path / "vm.csv"))).is_file()


def test_a_failed_measurement_leaves_a_message_not_a_traceback(tmp_path):
    """The user gets a status line; the exception goes to the log."""
    from chisurf.plugins.microscopy.img_frc.gui.view_model import FrcViewModel

    vm = FrcViewModel()
    assert not vm.set_filename(str(tmp_path / "nope.tif"))
    assert "No image loaded" in vm.status
    # The path is kept (the user typed it and must see it), so a Measure press
    # reaches the compute and comes back as a message rather than a traceback.
    assert not vm.compute()
    assert "no such file" in vm.status


def test_the_view_spec_loads_and_names_only_real_sources(tiff_stack):
    """Every source/attr the spec names must exist, or the panel renders blank."""
    from chisurf.plugins.microscopy.img_frc.gui.view_model import FrcViewModel

    vm = FrcViewModel()
    spec = vm.view_spec()
    assert spec is not None

    text = (pathlib.Path(__file__).parents[1] / "gui" / "frc.view.json").read_text()
    named = json.loads(text)

    def walk(section):
        for key in ("source", "options_source"):
            name = section.get(key)
            if name:
                assert callable(getattr(vm, name, None)) or isinstance(
                    getattr(type(vm), name, None), property
                ), f"{key} {name!r} is not a method or property of the view model"
        target = section.get("target")
        if target:
            assert callable(getattr(vm, target, None)), f"target {target!r} is not callable"
        for child in section.get("sections", []):
            walk(child)

    for section in named["sections"]:
        walk(section)
