"""The trajectory formats chimol claims must be the ones it can actually read.

There are three places that each state, in their own words, which files are
trajectories: the loader that decodes them, the caller that decides whether to
*skip* the structure reader for them, and the file dialog that offers them. They
drifted once already -- the loader was moved from an HDF5-based library onto
ChiSurf's own DCD codec and the other two went on naming the old formats.
Nothing failed. The dialog offered a format that could no longer be opened, and
the skip-the-structure-reader rule fired for exactly the files it should not
have and not for the ones it should, which put a warning and a full traceback in
the log for every DCD that opened perfectly.

That is the failure mode these tests are for: a claim about formats that no
longer matches the code behind it, and no symptom beyond noise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chimol.io import structure as chimol_structure
from chimol.io.structure import (
    TRAJECTORY_SUFFIXES,
    TrajectoryFormatError,
    load_trajectory_frames,
)


def test_loader_accepts_exactly_the_declared_suffixes() -> None:
    """Every declared suffix gets past the format check, and only those do."""
    for suffix in TRAJECTORY_SUFFIXES:
        with pytest.raises(Exception) as excinfo:
            load_trajectory_frames(Path("does-not-exist" + suffix))
        # It must fail on the *file*, not on the format: a declared format that
        # the loader rejects is the drift this test exists to catch.
        assert not isinstance(excinfo.value, TrajectoryFormatError), (
            f"'{suffix}' is declared a trajectory format but the loader "
            "rejects it as one"
        )


@pytest.mark.parametrize("suffix", [".h5", ".hdf5", ".gro", ".g96", ".pdb", ".cif"])
def test_undeclared_suffixes_raise_the_format_error(suffix: str) -> None:
    """An unreadable format says so, rather than failing as a broken read.

    The distinction is load-bearing: the caller re-raises this error and
    swallows everything else in favour of the structure reader's own complaint
    -- which, for a trajectory, is a message pointing back at this loader.
    """
    assert suffix not in TRAJECTORY_SUFFIXES
    with pytest.raises(TrajectoryFormatError):
        load_trajectory_frames(Path("x" + suffix))


def test_file_dialog_offers_every_readable_trajectory_format() -> None:
    """A format the loader reads is a format the Open dialog offers."""
    for suffix in TRAJECTORY_SUFFIXES:
        assert f"*{suffix}" in chimol_structure._DEFAULT_FILTER, (
            f"the Open dialog does not offer '{suffix}', which chimol reads"
        )


def test_file_dialog_offers_nothing_it_cannot_open() -> None:
    """And does not advertise the formats of a library that is no longer here."""
    for gone in ("*.gro", "*.g96", "*.h5", "*.hdf5"):
        assert gone not in chimol_structure._DEFAULT_FILTER, (
            f"the Open dialog still offers '{gone}', which nothing can read"
        )
