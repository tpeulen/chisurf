"""ChiSurf has few formats, and each one is the answer to a different question.

The problem this guards against is not that ChiSurf *reads* many formats — it
must, because instruments and other programs write many. It is that ChiSurf was
**writing** many: a curve could be saved as CSV, as YAML, through `save_xy`,
through the vv/vh stack or through one of the FCS writers, and none of those
five could say what the x axis was in.

So the rule is a split, not a count:

* **Reading**: as many formats as there are things to read. A reader is an
  import path and adding one costs nothing.
* **Writing**: one format per *kind of thing*, and the rest are exports the
  user asks for by name.

| what | ChiSurf writes | notes |
|---|---|---|
| a measurement — photons and everything derived | `.pto` | `curve_point`, `burst`, `pixel`, `dwell`… all in one file |
| a curve — decay, correlation, anisotropy, IRF | a `curve_point` artifact | not a file of its own |
| a table — bursts, pixels, molecules, tracks | an artifact at its grain | |
| a raster | TIFF, carried inside the container | a scientific raster stays readable by other tools |
| a project — datasets, fits, session | `.csp` | a different scope: many measurements |
| metadata for deposition | mmCIF | an export |

Everything else — `.bur` and its `…4` relatives, `.imaging.h5`, `kristine`,
`pycorrfit`, `photon-hdf5`, CSV — is either an **import source** or an
**export**, and both are fine. What is not fine is a *new* way for ChiSurf to
write something it already has a home for.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1] / "chisurf"


def test_a_curve_has_one_shape_wherever_it_is_written():
    """x, y and — when they carry information — ex, ey and the mask."""
    from chisurf.core.fio.pto import Measurement

    assert Measurement.CURVE_COLUMNS == ("x", "y", "ex", "ey", "mask")


def test_a_curve_round_trips_through_the_container(tmp_path: Path):
    from chisurf.core.data import DataCurve

    x = np.linspace(0.0, 25.0, 256)
    y = 900.0 * np.exp(-x / 4.1)
    ey = np.sqrt(np.maximum(y, 1.0))
    mask = (x > 2.0).astype(float)

    curve = DataCurve(x=x, y=y, ey=ey, mask=mask)
    curve.name = "decay"
    target = tmp_path / "curve.pto"
    curve.save(str(target))

    back = DataCurve()
    back.load(str(target))
    np.testing.assert_allclose(back.x, x)
    np.testing.assert_allclose(back.y, y)
    np.testing.assert_allclose(back.ey, ey)
    # The mask is part of the result: which points a fit ignored is exactly
    # what a bare two-column export loses.
    np.testing.assert_allclose(back.mask, mask)


def test_an_absent_uncertainty_is_not_written_as_zeros(tmp_path: Path):
    """A zero uncertainty is a claim, and a curve that never had one should not
    make it.
    """
    from chisurf.core.data import DataCurve
    from chisurf.core.fio.pto import Measurement

    x = np.linspace(0.0, 1.0, 32)
    curve = DataCurve(x=x, y=np.ones_like(x))
    curve.name = "flat"
    target = tmp_path / "flat.pto"
    curve.save(str(target))

    with Measurement.open(target) as m:
        stored = m.get_curve("flat")
    assert "ex" not in stored
    assert set(stored) >= {"x", "y"}


def test_a_curve_says_what_its_axes_are_in(tmp_path: Path):
    """An FCS lag axis is milliseconds and a TCSPC axis is nanoseconds.

    Nothing about the numbers says which, and reading one for the other is a
    mistake that never surfaces as an error — it surfaces as a diffusion time
    off by a factor of a million.
    """
    from chisurf.core.data import DataCurve
    from chisurf.core.fio.pto import Measurement

    curve = DataCurve(x=np.logspace(-3, 3, 64), y=np.linspace(1.4, 1.0, 64))
    curve.name = "correlation"
    curve.X_UNITS = "milliseconds"
    curve.Y_UNITS = "dimensionless"
    curve.ARTIFACT_KIND = "fcs_correlation"
    curve.OPERATION_TYPE = "fcs_correlation"

    target = tmp_path / "fcs.pto"
    curve.save(str(target))
    with Measurement.open(target) as m:
        stored = m.get_curve("correlation")
        assert m.artifacts()[-1].kind == "fcs_correlation"
    assert stored["x_units"] == "milliseconds"
    assert stored["y_units"] == "dimensionless"


def test_the_readers_say_what_they_read():
    """A reader that knows the axis must record it — that is where the
    knowledge is, and the only place it exists.
    """
    fcs = (ROOT / "core" / "fio" / "fluorescence" / "fcs" / "__init__.py").read_text()
    assert 'curve.X_UNITS = "milliseconds"' in fcs

    tcspc = (ROOT / "core" / "fio" / "fluorescence" / "tcspc.py").read_text()
    assert 'curve.X_UNITS = "nanoseconds"' in tcspc


#: Modules allowed to write a curve in a format of their own.
#:
#: A **shrinking** list, and never somewhere to add yourself. Each entry is
#: either a legacy format kept because another program reads it, or an export
#: the user asks for by name — not a way for ChiSurf to save its own work.
CURVE_EXPORT_ALLOWLIST = {
    "core/fio/ascii.py",  # generic x/y export
    "core/fio/vv_vh.py",  # the historic stacked decay
    "core/fio/fluorescence/fcs/kristine.py",  # read by other groups' tools
    "core/fio/fluorescence/fcs/fcs_yaml.py",  # multi-curve export
    "core/fio/fluorescence/fcs/china.py",  # MATLAB export
    "core/fio/fluorescence/fcs/__init__.py",  # dispatches the above
}


def test_no_new_module_invents_a_curve_format():
    """Adding a *reader* is free. Adding a sixth way to write a curve is not."""
    offenders: list[str] = []
    # `..._container` is the sanctioned path, not a format of its own — it
    # writes *into* the measurement's file.
    pattern = re.compile(
        r"^def write_\w*(?:curve|decay|fcs|correlation)\w*(?<!_container)\s*\(", re.M
    )
    for path in ROOT.rglob("*.py"):
        if "/test" in str(path):
            continue
        relative = str(path.relative_to(ROOT))
        if relative in CURVE_EXPORT_ALLOWLIST:
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if pattern.search(text):
            offenders.append(relative)

    assert not offenders, (
        "a curve is a `curve_point` artifact in the measurement's container "
        "(Measurement.put_curve). These modules write one in a format of their "
        "own:\n  " + "\n  ".join(sorted(offenders))
    )


def test_the_allowlist_only_names_files_that_exist():
    """A stale entry silently re-permits whatever later takes that path."""
    missing = [name for name in CURVE_EXPORT_ALLOWLIST if not (ROOT / name).is_file()]
    assert not missing, f"remove these from the allow-list: {sorted(missing)}"


def test_reading_many_formats_is_not_the_problem():
    """Pinned so the guard above is never 'fixed' by deleting readers.

    ChiSurf reads a dozen FCS formats and should; six of them cannot write at
    all, which is exactly the right shape for an import path.
    """
    fcs_dir = ROOT / "core" / "fio" / "fluorescence" / "fcs"
    readers = [p for p in fcs_dir.glob("*.py") if re.search(r"^def read", p.read_text(), re.M)]
    assert len(readers) >= 8, "the FCS import paths should not be shrinking"
