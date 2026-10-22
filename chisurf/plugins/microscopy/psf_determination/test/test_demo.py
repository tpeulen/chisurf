"""The PSF tool's example: five generated beads whose FWHM the fit must recover."""

from chisurf.plugins.microscopy.psf_determination.demo import TRUE_FWHM, make_demo
from chisurf.plugins.microscopy.psf_determination.gui.app import make_app


def test_make_demo_writes_a_bead_z_stack():
    """The demo stack exists on disk for scripts, though the tool needs no file."""
    path = make_demo()
    assert path.is_file() and path.stat().st_size > 0


def test_load_example_finds_and_fits_the_beads():
    """The affordance loads the generated stack; detect and fit recover the FWHM."""
    app = make_app()
    app.load_example()
    assert app.model.stack is not None
    found = app.model.detect_beads()
    assert found > 0
    app.model.fit_all()
    text = app.model.results_text
    assert str(int(TRUE_FWHM["lateral_nm"])) in text
    assert "FWHM" in text
