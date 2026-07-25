"""A measurement file must stay renamable after it has been read.

ChiSurf opens a photon file, and the user then renames, moves or deletes it —
from the staging cache, on a project save, or by hand. If the reader keeps an
operating-system handle on the file that fails: on Windows with a hard error, on
POSIX by leaving a deleted-but-open file quietly consuming space. The non-ASCII
name is part of the question, because that is where path handling is most likely
to keep a stray handle open.

This file used to be a Windows debugging script that ran at import time and
copied a file from a hard-coded ``e:\\dev\\chisurf`` path, so it failed at
*collection* and took the whole ``test/core`` directory down with it.
"""

from __future__ import annotations

import os
import pathlib
import shutil

import pytest

tttrlib = pytest.importorskip("tttrlib")

#: A real photon file from the repository's own test data.
SOURCE = pathlib.Path(__file__).resolve().parents[1] / "data" / "clsm" / "Leica_SP8.ptu"


@pytest.fixture()
def measurement(tmp_path):
    """Return a copy of a real PTU file under a non-ASCII name."""
    if not SOURCE.is_file():
        pytest.skip(f"test data not available: {SOURCE}")
    target = tmp_path / "measurement_µ_file.ptu"
    shutil.copy(SOURCE, target)
    return target


def test_file_can_be_renamed_after_reading(measurement):
    """Reading a file must not leave a handle that blocks renaming it."""
    ascii_name = measurement.with_name("measurement_m_file.ptu")
    os.rename(measurement, ascii_name)

    data = tttrlib.TTTR(str(ascii_name))
    assert len(data.macro_times) > 0

    # The rename is the assertion: it is what fails when a handle is still open.
    os.rename(ascii_name, measurement)
    assert measurement.is_file()


def test_file_can_be_deleted_after_reading(measurement):
    """The same for deletion — a project cleaning its staging cache depends on it."""
    data = tttrlib.TTTR(str(measurement))
    assert len(data.macro_times) > 0
    del data

    measurement.unlink()
    assert not measurement.exists()


def test_non_ascii_name_is_read_as_such(measurement):
    """A non-ASCII path opens without being mangled on the way in."""
    data = tttrlib.TTTR(str(measurement))
    assert len(data.macro_times) > 0
    assert "µ" in measurement.name
