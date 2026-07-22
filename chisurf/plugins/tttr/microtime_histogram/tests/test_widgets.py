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
