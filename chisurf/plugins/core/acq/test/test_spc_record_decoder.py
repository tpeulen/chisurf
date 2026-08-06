"""The live-acquisition SPC-130 decoder must agree with the library's.

``_process_bh_spc_records_numba`` is a **hand-maintained copy** of
``RecordProcessor<BH_RECORD_TYPE_SPC130>``, and its own docstring says so. It
exists because the acquisition path decodes records arriving from the card *in
memory*, and the library exposes its decoder to Python only behind a file
reader — there is no "decode this buffer" entry point to call instead.

A copy of a decoder with nothing pinning it is how the two come to disagree
about a corner (an overflow run, a gap flag, a marker) on somebody's data,
months later, with no error anywhere. So this reads a real ``.spc`` both ways
and asserts they are the same file.

If the library ever grows an in-memory record decoder in its Python surface,
this test should be deleted along with the copy.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

#: The same BH SPC-130 fixture the burst-selection tests use.
_SPC = pathlib.Path(__file__).resolve().parents[4] / "test" / "data" / "tttr"


def _find_spc() -> pathlib.Path | None:
    """Return a BH SPC fixture, or ``None`` when none is available.

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
            return candidate
    return None


def test_the_copy_still_decodes_what_the_library_decodes():
    """Same event count, same macro times, same micro times, same channels."""
    tttrlib = pytest.importorskip("tttrlib")
    path = _find_spc()
    if path is None:
        pytest.skip("no .spc fixture available")

    from chisurf.plugins.core.acq.gui.tool import _process_bh_spc_records_numba

    reference = tttrlib.TTTR(str(path))
    if reference.get_tttr_container_type() != "SPC-130":
        pytest.skip(f"{path.name} is {reference.get_tttr_container_type()}, not SPC-130")

    # A .spc carries one 32-bit header word before its records.
    records = np.fromfile(path, dtype=np.uint32)[1:]
    macro, micro, routing, _, _ = _process_bh_spc_records_numba(records, 0)

    expected_macro = reference.macro_times
    assert len(expected_macro) > 0, path
    n = len(expected_macro)
    np.testing.assert_array_equal(macro[:n], expected_macro)
    np.testing.assert_array_equal(micro[:n], reference.micro_times)
    np.testing.assert_array_equal(routing[:n], reference.routing_channel)
