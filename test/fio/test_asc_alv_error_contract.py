"""An unreadable ALV file must fail like every other IO failure.

`LoadALVError` used to derive from `BaseException`, which put a malformed-file
condition in the same category as `KeyboardInterrupt`: it passed straight
through every `except Exception` in the import path, and through
`pytest.raises(Exception)`. The reader raises it five times for ordinary
malformed-file conditions, right next to a `NotImplementedError` that *is* an
`Exception` — so two failures of the same kind behaved differently for callers.
"""

from __future__ import annotations

import pathlib

import pytest

FCS_ASC = pathlib.Path(__file__).parent.parent / "data" / "fcs" / "asc"


@pytest.fixture()
def alv_without_mode(tmp_path):
    """Write a copy of a real ALV-7004 file with its ``Mode`` header removed.

    Dropping that one line is what the reader reports as "Undetermined ALV
    file mode" — the cheapest genuine `LoadALVError` the parser can reach,
    reached only after the correlation and trace blocks have parsed.
    """
    source = FCS_ASC / "ALV-7004USB_ac3.ASC"
    lines = source.read_text(encoding="iso8859_15").splitlines(keepends=True)
    kept = [line for line in lines if not line.startswith("Mode")]
    assert len(kept) == len(lines) - 1, "expected exactly one Mode header"

    target = tmp_path / "no_mode.ASC"
    target.write_text("".join(kept), encoding="iso8859_15")
    return target


def test_load_alv_error_is_an_exception():
    """The reader's error type is catchable by generic handlers."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import LoadALVError

    assert issubclass(LoadALVError, Exception)


def test_malformed_alv_file_raises_a_catchable_error(alv_without_mode):
    """A file the parser cannot interpret raises `LoadALVError`, not a `BaseException`."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import LoadALVError, openASC

    with pytest.raises(LoadALVError):
        openASC(alv_without_mode)

    # The point of the contract: a caller guarding with the generic handler
    # sees the failure instead of having it tear down the import path.
    try:
        openASC(alv_without_mode)
    except Exception as exc:  # noqa: BLE001 - that generic catch *is* the contract
        assert isinstance(exc, LoadALVError)
    else:
        pytest.fail("openASC accepted a file with no Mode header")


def test_alv_writer_stub_is_gone():
    """ALV is a read-only format; no `write_asc` stub pretends otherwise.

    The removed function carried a full docstring describing eight parameters
    and an output file over a body of `pass`, so a caller that found it would
    have written nothing and been told it succeeded.
    """
    from chisurf.core.fio.fluorescence.fcs import asc_alv

    assert not hasattr(asc_alv, "write_asc")
