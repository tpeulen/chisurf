"""Guards for the PSF calculator's model, export and authored resources.

The optics themselves are tttrlib's and are tested there; what is checked here
is that this plugin computes something physically sane, writes files another
program can actually read, and ships the guide and help the plugin standard
requires.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from chisurf.plugins.calculator.psf_calculator.core import PSFModel

PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def computed() -> PSFModel:
    """A small Airy volume -- cheap, and analytic enough to assert on."""
    model = PSFModel()
    model.nxy, model.nz, model.model = 24, 9, "airy"
    model.compute()
    return model


def test_volume_has_the_requested_shape(computed):
    assert computed.volume.shape == (computed.nz, computed.nxy, computed.nxy)


def test_peak_sits_at_the_lateral_centre(computed):
    """The brightest voxel is on axis.

    Only laterally: the Airy model is the focal-plane pattern repeated along z
    (tttrlib's ``psf_volume`` documents ``model='airy'`` as ignoring z), so its
    stack is flat axially and every plane holds the maximum equally.
    """
    _, ny, nx = computed.volume.shape
    _, y, x = np.unravel_index(int(np.argmax(computed.volume)), computed.volume.shape)
    assert (y, x) == ((ny - 1) // 2, (nx - 1) // 2)


def test_models_with_defocus_peak_in_the_focal_plane():
    """The two z-dependent models put their maximum in the centre plane."""
    for name in ("gaussian", "vectorial"):
        model = PSFModel()
        model.nxy, model.nz, model.model = 24, 9, name
        volume = model.compute()
        axial = volume[:, (24 - 1) // 2, (24 - 1) // 2]
        assert int(np.argmax(axial)) == volume.shape[0] // 2, name
        # and it must actually fall off, or the "3-D" view is a cylinder
        assert axial[0] < 0.6 * axial.max(), name


def test_lateral_width_tracks_the_scalar_limit(computed):
    """The Airy width matches 0.51 lambda/NA to a few percent.

    0.51 lambda/NA is a rounded form of the Airy FWHM (0.514 lambda/NA), so the
    measured width should sit just above it. A loose bound here would hide the
    sampling bias that the interpolated ``_fwhm`` exists to remove.
    """
    summary = computed.summary_text()
    assert "lateral FWHM" in summary
    nz, ny, _ = computed.volume.shape
    measured = computed._fwhm(computed.volume[nz // 2][ny // 2], computed.pixel_size_nm)
    scalar = 0.51 * computed.wavelength_nm / computed.na
    assert 0.98 * scalar < measured < 1.06 * scalar


def test_fwhm_interpolates_between_samples():
    """A known Gaussian is recovered to ~1 % even sampled at 30 nm.

    Counting samples at or above half-max quantizes the answer to the step and
    understates it -- it reported 150 nm for every grid here, 21 % low. The
    reported width is this tool's headline number, so it must not be a sample
    count.
    """
    true_fwhm = 200.0
    sigma = true_fwhm / 2.3548200450309493
    for step in (30.0, 10.0, 3.0):
        x = np.arange(-40, 41) * step
        measured = PSFModel._fwhm(np.exp(-(x ** 2) / (2 * sigma ** 2)), step)
        assert measured == pytest.approx(true_fwhm, rel=0.01), step


def test_save_npy_round_trips(computed, tmp_path):
    path = computed.save(tmp_path / "psf.npy")
    assert np.array_equal(np.load(path), computed.volume)


def test_save_tiff_carries_the_voxel_size(computed, tmp_path):
    """ImageJ must find the voxel size, or the stack opens unscaled."""
    tifffile = pytest.importorskip("tifffile")
    path = computed.save(tmp_path / "psf.tif")
    with tifffile.TiffFile(path) as handle:
        data = handle.asarray()
        meta = handle.imagej_metadata
        num, den = handle.pages[0].tags["XResolution"].value
    assert data.shape == computed.volume.shape
    assert np.allclose(data, computed.volume.astype(np.float32))
    assert meta["unit"] == "um"
    assert meta["spacing"] == pytest.approx(computed.z_step_nm / 1000.0)
    # XResolution is pixels per unit, so its reciprocal is the pixel size.
    assert den / num * 1000.0 == pytest.approx(computed.pixel_size_nm)


def test_save_defaults_to_npy_without_a_suffix(computed, tmp_path):
    """A typed name with no extension still produces a loadable file."""
    assert computed.save(tmp_path / "psf").suffix == ".npy"


def test_save_before_compute_is_an_error(tmp_path):
    with pytest.raises(RuntimeError):
        PSFModel().save(tmp_path / "psf.npy")


def test_export_basename_records_the_optics(computed):
    name = computed.export_basename()
    assert "airy" in name and "NA1.4" in name and "520nm" in name


def test_guide_points_at_real_attributes():
    """Every guide step must target a control the view spec actually binds.

    A tour that points at a widget which is not there silently skips the step,
    which is worse than having no tour: the user is told to press something
    that cannot be found.
    """
    steps = json.loads((PLUGIN_DIR / "gui" / "guide.json").read_text())["steps"]
    assert len(steps) >= 5
    spec = json.loads((PLUGIN_DIR / "psf_calculator.view.json").read_text())

    bound: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for key in ("attr", "target"):
                if isinstance(node.get(key), str):
                    bound.add(node[key])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec)
    missing = [
        step["title"]
        for step in steps
        if (step.get("target") or {}).get("attr")
        and step["target"]["attr"] not in bound
    ]
    assert not missing, f"guide steps target unbound attributes: {missing}"


def test_guide_await_is_true_or_a_dict():
    """``"await": false`` is not a valid spelling -- the loader rejects it.

    GuidedTour special-cases ``True`` and a mapping; anything else reaches
    ``dict(...)`` and raises. Omit the key to mean "do not wait".
    """
    steps = json.loads((PLUGIN_DIR / "gui" / "guide.json").read_text())["steps"]
    for step in steps:
        if "await" in step:
            assert step["await"] is True or isinstance(step["await"], dict)


def test_help_is_shipped_and_links_resolve():
    """Help links must point inside this repo, or the ? modal dead-ends."""
    import re

    text = (PLUGIN_DIR / "gui" / "help.md").read_text()
    assert len(text) > 500
    repo_root = PLUGIN_DIR.parents[3]
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "#")):
            continue
        assert (repo_root / target).exists(), f"help.md links to a missing {target}"
