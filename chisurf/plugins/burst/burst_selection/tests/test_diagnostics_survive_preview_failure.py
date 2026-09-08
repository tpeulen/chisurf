"""A failure in the preview table must not blank the whole window.

``_load_tttr_for_plots`` wraps everything it does in one broad ``except``, and
that handler *clears the diagnostics* — so any exception raised anywhere inside
it leaves the tool with no data and every plot empty.

That is not hypothetical. One logging call written printf-style
(``_LOG.warning("burst search: %s", text)``) against a logger whose signature is
``warning(message, **extra)`` raised ``TypeError``, the handler swallowed it,
and the burst-selection GUI stopped updating entirely. The failure was in a
cosmetic step; the cost was the whole window.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_selection.gui.tool import BurstSelectionTool


class _Header:
    macro_time_resolution = 1e-6


class _Tttr:
    def __init__(self, n=1000):
        self.macro_times = np.arange(n, dtype=np.int64)
        self.micro_times = np.zeros(n, dtype=np.int64)
        self.header = _Header()


def _tool(preview_raises: bool):
    """A tool with only the pieces ``_load_tttr_for_plots`` touches."""
    tool = BurstSelectionTool.__new__(BurstSelectionTool)
    diag = {
        "path": "/data/a.ptu",
        "tttr": _Tttr(),
        "selected": np.ones(1000, dtype=bool),
        "start_stop": np.array([[0, 100]], dtype=np.int64),
    }

    class _Client:
        def load_diagnostics(self, *_a, **_k):
            return dict(diag)

    class _Bar:
        def showMessage(self, *_a):
            pass

    class _Summary:
        text = ""

        def setPlainText(self, t):
            type(self).text = t

        def append(self, t):
            type(self).text += t

    tool._client = _Client()
    tool._status_bar = _Bar()
    tool.summary = _Summary()
    tool._last_diagnostics = []
    tool._open_tttr = {}
    tool._display_view_model = None
    tool.plot_min_spin = None
    tool.plot_max_spin = None
    tool._diagnostic_photon_total = None

    calls = {"plots": 0}
    tool.update_burst_plots = lambda: calls.__setitem__("plots", calls["plots"] + 1)
    tool._sync_plot_range_controls = lambda *_a, **_k: None
    tool._diagnostic_window = lambda: (None, 0.0)

    def preview(_diagnostics):
        if preview_raises:
            raise TypeError("warning() takes 2 positional arguments but 3 were given")

    tool._show_preview_frames = preview
    return tool, calls


@pytest.mark.parametrize("preview_raises", [False, True])
def test_the_plots_still_draw_when_the_preview_fails(preview_raises, monkeypatch):
    from pathlib import Path

    from chisurf.plugins.burst.burst_selection.gui import tool as tool_module

    # The status task walks real Qt parents; this stand-in has none.
    monkeypatch.setattr(tool_module, "find_status_reporter", lambda _w: None)
    tool, calls = _tool(preview_raises)
    BurstSelectionTool._load_tttr_for_plots(tool, [Path("/data/a.ptu")], None)

    assert len(tool._last_diagnostics) == 1, (
        "the diagnostics were cleared, so every plot would be empty"
    )
    assert calls["plots"] == 1, "update_burst_plots never ran"


def test_the_status_logger_takes_no_positional_arguments():
    """The signature the module must be written against.

    ``RpcLogWriter.warning(message, **extra)`` — a printf-style call raises, and
    in this module raising is what blanks the window.
    """
    import inspect

    from chisurf.plugins.burst.burst_selection.gui import tool as tool_module

    log = tool_module._LOG
    for level in ("debug", "info", "warning", "error"):
        method = getattr(log, level, None)
        if method is None:
            continue
        params = list(inspect.signature(method).parameters.values())
        positional = [
            p for p in params
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        assert len(positional) == 1, (
            f"{level}() takes {len(positional)} positional arguments; "
            "the module assumes exactly one (the message)"
        )
