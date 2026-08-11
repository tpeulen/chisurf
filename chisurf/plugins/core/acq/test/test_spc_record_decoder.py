"""The live-acquisition SPC-130 decoder is the library's, and must stay chunked.

There used to be a hand-maintained transcription of
``RecordProcessor<BH_RECORD_TYPE_SPC130>`` here, kept fast with numba, because
acquisition decodes records arriving from the card *in memory* and the library
exposed its decoder only behind a file reader. It now exposes
``decode_records``, so the copy is gone and this test no longer compares two
implementations of the format — that comparison would be a tautology.

What is left worth pinning is the part acquisition still owns: the **wrap
counter across chunk boundaries**. A card delivers a few thousand records at a
time, and a decoder that starts each buffer from zero produces a perfectly
plausible-looking first chunk and nonsense from the second one on. Nothing
raises. So the test below decodes a real ``.spc`` the way the acquisition
thread does — in chunks, threading the counter — and demands the result be the
file, byte for byte.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest


def _find_spc130(tttrlib) -> pathlib.Path | None:
    """Return a BH SPC-130 fixture, or ``None`` when none is available.

    Parameters
    ----------
    tttrlib : module
        Used to read each candidate's container type — the directory holds
        SPC-600 and SPC-QC files too, and those are different record formats.

    Returns
    -------
    pathlib.Path or None
    """
    roots = [
        pathlib.Path(__file__).resolve().parents[5],
        pathlib.Path.home() / "dev" / "tttr-data",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in sorted(root.rglob("*.spc")):
            try:
                if tttrlib.TTTR(str(candidate)).get_tttr_container_type() == "SPC-130":
                    return candidate
            except Exception:  # noqa: BLE001 - a bad fixture is not a failure here
                continue
    return None


@pytest.fixture(scope="module")
def spc(request):
    """A real SPC-130 file and its records, or a skip."""
    tttrlib = pytest.importorskip("tttrlib")
    path = _find_spc130(tttrlib)
    if path is None:
        pytest.skip("no SPC-130 fixture available")
    # A .spc carries one 32-bit header word before its records.
    return tttrlib.TTTR(str(path)), np.fromfile(path, dtype=np.uint32)[1:]


def test_a_single_buffer_decodes_to_the_same_file(spc):
    """One call over the whole buffer reproduces the file reader exactly."""
    from chisurf.plugins.core.acq.gui.tool import _decode_bh_spc_records

    reference, records = spc
    macro, micro, routing, wraps, final = _decode_bh_spc_records(records, 0)

    assert len(macro) > 0
    np.testing.assert_array_equal(macro, reference.macro_times)
    np.testing.assert_array_equal(micro, reference.micro_times)
    np.testing.assert_array_equal(routing, np.asarray(reference.routing_channel))
    # Starting from zero, the wraps seen *are* the counter handed on.
    assert wraps == final > 0


def test_chunking_the_buffer_changes_nothing_if_the_counter_is_threaded(spc):
    """The acquisition path's real shape: many small buffers, one counter.

    This is the assertion the module exists for. Drop the counter and the first
    chunk still looks right, which is why it needs a test rather than a glance.
    """
    from chisurf.plugins.core.acq.gui.tool import _decode_bh_spc_records

    reference, records = spc

    macro, micro, routing = [], [], []
    overflow, wraps_total = 0, 0
    for start in range(0, len(records), 4096):
        m, u, r, wraps, overflow = _decode_bh_spc_records(
            records[start:start + 4096], overflow
        )
        macro.append(m)
        micro.append(u)
        routing.append(r)
        wraps_total += wraps

    np.testing.assert_array_equal(np.concatenate(macro), reference.macro_times)
    np.testing.assert_array_equal(np.concatenate(micro), reference.micro_times)
    np.testing.assert_array_equal(
        np.concatenate(routing), np.asarray(reference.routing_channel)
    )
    # Per-chunk wrap counts are deltas, so they must sum to the final counter.
    assert wraps_total == overflow


def test_an_empty_buffer_is_not_an_error_and_keeps_the_counter(spc):
    """Idle polling hands the decoder nothing; it must not reset the clock."""
    from chisurf.plugins.core.acq.gui.tool import _decode_bh_spc_records

    macro, micro, routing, wraps, final = _decode_bh_spc_records(
        np.zeros(0, dtype=np.uint32), 12345
    )
    assert len(macro) == len(micro) == len(routing) == 0
    assert wraps == 0
    assert final == 12345


def test_the_dtypes_are_what_the_accumulator_expects(spc):
    """`_accumulate` reinterprets these arrays; a signed channel would wrap.

    The library hands back ``int8`` routing channels, so the conversion is
    load-bearing rather than decorative.
    """
    from chisurf.plugins.core.acq.gui.tool import _decode_bh_spc_records

    _, records = spc
    macro, micro, routing, _, _ = _decode_bh_spc_records(records[:4096], 0)
    assert macro.dtype == np.uint64
    assert micro.dtype == np.uint16
    assert routing.dtype == np.uint8
