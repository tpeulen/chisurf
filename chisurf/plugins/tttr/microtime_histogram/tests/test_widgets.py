"""Tests for the microtime-histogram file-list migration.

The full ``MicrotimeHistogram`` widget cannot be constructed under pytest (a
pre-existing incompatibility — it pulls in the detector-wizard page + tttrlib and
aborts the interpreter under the headless test harness, which is why it has never
had widget tests). The unified file-list behaviour it now relies on is covered by
``test/gui/test_path_list_section.py`` (checkable, replace_on_drop, folder_expander,
path_filter, rejectedPaths); here we cover the one piece of plugin-specific logic
that is a pure function — the burstwise-folder → BUR/BST expansion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from qtpy import QtWidgets  # noqa: F401
except ImportError:
    pytest.skip("Qt bindings not available", allow_module_level=True)


def test_bid_folder_expands_to_bur_and_bst(tmp_path) -> None:
    # importing the module does not construct the widget
    from chisurf.plugins.tttr.microtime_histogram.wizard import MicrotimeHistogram

    (tmp_path / "bi4_bur").mkdir()
    (tmp_path / "bi4_bur" / "x.bur").write_bytes(b"x")
    (tmp_path / "BID").mkdir()
    (tmp_path / "BID" / "y.bst").write_bytes(b"x")

    expanded = {Path(p).name for p in MicrotimeHistogram._expand_bid_folder(tmp_path)}
    assert expanded == {"x.bur", "y.bst"}


def test_bid_folder_without_index_files_is_empty(tmp_path) -> None:
    from chisurf.plugins.tttr.microtime_histogram.wizard import MicrotimeHistogram

    (tmp_path / "unrelated.txt").write_bytes(b"x")
    assert MicrotimeHistogram._expand_bid_folder(tmp_path) == []


_SPC = (Path(__file__).resolve().parents[5]
        / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc")


@pytest.mark.skipif(not _SPC.is_file(), reason="sample SPC not available")
def test_apply_setup_lut_linearizes_histogram() -> None:
    """The histogram compute linearizes via the setup's LUT (regression: read raw)."""
    import numpy as np
    import tttrlib

    from chisurf.plugins.tttr.microtime_histogram.wizard import MicrotimeHistogram
    from chisurf.plugins.tttr.tttr_lut_tools.api import compute

    ntac = np.asarray(compute.compute_lut_from_files(
        [str(_SPC)], channel=0, linear_start=1500, linear_stop=3000)["NTAC_fract"])

    class _Page:
        _channel_luts = {0: ntac}
        _channel_shifts: dict = {}
        _apply_lut = True

    class _Self:
        detector_wizard_page = _Page()

    raw = np.asarray(tttrlib.TTTR(str(_SPC)).get_tttr_by_channel([0])
                     .get_microtime_histogram(1)[0], dtype=float)
    d = tttrlib.TTTR(str(_SPC))
    MicrotimeHistogram._apply_setup_lut(_Self(), d)
    corrected = np.asarray(d.get_tttr_by_channel([0]).get_microtime_histogram(1)[0], dtype=float)
    n = min(raw.size, corrected.size)
    assert not np.array_equal(raw[:n], corrected[:n])

    # gate off -> raw
    _Page._apply_lut = False
    d2 = tttrlib.TTTR(str(_SPC))
    MicrotimeHistogram._apply_setup_lut(_Self(), d2)
    off = np.asarray(d2.get_tttr_by_channel([0]).get_microtime_histogram(1)[0], dtype=float)
    assert np.array_equal(raw[:n], off[:n])


def test_polarization_resolved_gates_parallel_perp() -> None:
    """polarization_resolved ON = interleaved VV/VH; OFF = one unpolarized stream."""
    import types

    from chisurf.plugins.tttr.microtime_histogram.wizard import MicrotimeHistogram

    class _Page:
        _polarization_resolved = True

    class _Self:
        detector_wizard_page = _Page()

        def _get_interleaved_channels(self):
            return [8, 0, 3, 9, 1, 2]

    s = _Self()
    s._is_polarization_resolved = types.MethodType(
        MicrotimeHistogram._is_polarization_resolved, s)
    assert MicrotimeHistogram.parallel_channels.fget(s) == [8, 3, 1]
    assert MicrotimeHistogram.perpendicular_channels.fget(s) == [0, 9, 2]

    _Page._polarization_resolved = False
    assert MicrotimeHistogram.parallel_channels.fget(s) == [8, 0, 3, 9, 1, 2]
    assert MicrotimeHistogram.perpendicular_channels.fget(s) == []
