"""A start under its app's brand: ``--app acq`` is PhAcq, ``--app chimol`` ChiMOL, else ChiSurf."""
from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from chisurf.emtk.brand import BAND, CHISURF, LOGO_BOX, NAME_BOX, brand_for, splash_art  # noqa: E402
from chisurf.emtk.splash import ART  # noqa: E402


def test_the_apps_declare_their_brand_in_their_manifest():
    assert brand_for("") is CHISURF and brand_for("no-such-plugin") is CHISURF
    acq, chimol = brand_for("acq"), brand_for("chimol")
    assert (acq.name, acq.app_id) == ("PhAcq", "Peulen.PhAcq")
    assert (chimol.name, chimol.app_id) == ("ChiMOL", "Peulen.ChiMOL")
    for brand in (acq, chimol):
        assert brand.logo.is_file() and brand.icon.suffix == ".ico"
    assert CHISURF.icon.is_file()


def test_the_splash_swaps_only_the_logo_corner():
    plain = splash_art(ART, CHISURF)
    phacq = splash_art(ART, brand_for("acq"))
    assert plain.size == phacq.size
    # the logo and name changed ...
    assert plain.crop(LOGO_BOX).tobytes() != phacq.crop(LOGO_BOX).tobytes()
    assert plain.crop(NAME_BOX).tobytes() != phacq.crop(NAME_BOX).tobytes()
    # ... on the band's own grey, and the rest of the art (licence, band edges) did not
    assert phacq.getpixel((NAME_BOX[2] - 2, NAME_BOX[1] + 2)) == BAND
    right = (NAME_BOX[2] + 10, 0, plain.width, plain.height)
    assert plain.crop(right).tobytes() == phacq.crop(right).tobytes()
