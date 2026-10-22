"""Example data for the PSF tool: a bead z-stack with a known FWHM.

``make_demo`` writes ``psf_demo.tif``: the same five-bead stack the tool's own
*Load demo* generates (FWHM 424 nm lateral, 2120 nm axial; see
:mod:`chisurf.plugins.microscopy.demo_stack`), as a file on disk so scripts and
tests can load it the way a user's scan arrives. *Load example* runs the tool's
own demo load, which needs no file.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.microscopy import demo_stack

STEM = "psf_demo"
#: The truth the fit must recover, from the generator's sigma and sampling.
TRUE_FWHM = {"lateral_nm": 424.0, "axial_nm": 2120.0}


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the PSF tool."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "psf_determination"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the bead z-stack."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.tif"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        demo_stack.write_tif(path, demo_stack.psf_stack())
    return path


def load_into(app) -> Path:
    """The tool's own generated demo (no file needed); the written stack is for scripts."""
    app.load_demo()
    return make_demo()
