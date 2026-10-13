"""Clear removes screen-pinned labels instead of stacking old diagnostic captions."""

import pytest

from chisurf import chiplot as cp
from chisurf.chiplot import backends


@pytest.mark.parametrize("backend", ["emtk"])
def test_clear_removes_anchored_text_across_repeated_updates(monkeypatch, backend):
    """A new diagnostic caption is the only one retained after a real clear."""
    monkeypatch.setenv("CHISURF_PLOT_BACKEND", backend)
    monkeypatch.setattr(backends, "_active", None)
    plot = cp.Panel()
    for index in range(3):
        plot.clear()
        plot.text(f"Count {index}", (8, 8), anchored=True)
        canvas = plot._canvas
        labels = [entry.state["text"] for entry in canvas._entries if entry.kind == "text"]
        assert labels == [f"Count {index}"]
