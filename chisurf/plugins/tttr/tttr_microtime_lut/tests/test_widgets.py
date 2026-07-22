"""Tests for the tttr_microtime_lut file-list migration.

The ``TACLinearizationWidget`` cannot be constructed under pytest (a pre-existing
incompatibility — the heavy pyqtgraph/tttrlib setup aborts the interpreter under
the headless harness, which is why it has never had widget tests). The unified
file-list behaviour it relies on is covered by ``test/gui/test_path_list_section.py``;
here we cover the pure ``_FileListModel`` adapter that bridges the list to the tool.
"""

from __future__ import annotations

from chisurf.plugins.tttr.tttr_microtime_lut import _FileListModel


class _FakeTool:
    def __init__(self):
        self.files = []
        self.changed = 0

    def _on_files_changed(self):
        self.changed += 1


def test_file_list_model_delegates_and_notifies():
    tool = _FakeTool()
    model = _FileListModel(tool)

    assert model.files == []
    model.files = ["a.ptu", "b.ht3"]
    assert tool.files == ["a.ptu", "b.ht3"]
    assert model.files == ["a.ptu", "b.ht3"]

    model.update()
    assert tool.changed == 1


def test_file_list_model_tolerates_missing_attr():
    class Bare:
        def _on_files_changed(self):
            pass

    # getter must not raise if the tool has not initialised ``files`` yet
    assert _FileListModel(Bare()).files == []
