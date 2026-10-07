"""Clear removes screen-pinned labels instead of stacking old diagnostic captions."""

import pytest

from chisurf.gui import chiplot as cp
from chisurf.gui.chiplot import backends


@pytest.mark.parametrize("backend", ["pyqtgraph", "emtk"])
def test_clear_removes_anchored_text_across_repeated_updates(qapp, monkeypatch, backend):
    """A new diagnostic caption is the only one retained after a real clear."""
    monkeypatch.setenv("CHISURF_PLOT_BACKEND", backend)
    monkeypatch.setattr(backends, "_active", None)
    plot = cp.Plot()
    try:
        for index in range(3):
            plot.clear()
            plot.text(f"Count {index}", (8, 8), anchored=True)
            canvas = plot._canvas
            if backend == "emtk":
                labels = [entry.state["text"] for entry in canvas._entries if entry.kind == "text"]
            else:
                labels = [
                    item.toPlainText()
                    for item in canvas._pi.childItems()
                    if type(item).__name__ == "TextItem"
                ]
            assert labels == [f"Count {index}"]
    finally:
        plot.close()
        qapp.processEvents()
