"""Burst-analysis shell integration of the IRF & Background tool.

Checks that the tool is wired into the ``burst_analysis`` navigation shell as a
panel and that its "Send to MLE" handoff writes the per-detector ``irf_np`` /
``bg_np`` patterns into the MLE panel and refreshes it.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool

_PATTERNS = {
    "green": {"irf": np.arange(8.0), "bg": np.ones(8)},
    "red": {"irf": np.arange(8.0), "bg": np.ones(8)},
}


class _StubMLE:
    """Minimal stand-in for the MLE wizard (``irf_np``/``bg_np`` + refresh hooks)."""

    def __init__(self) -> None:
        self.irf_np: dict = {}
        self.bg_np: dict = {}
        self._fit = "stale"
        self.refreshed: list[str] = []

    def update_scatter_count_rate_ui(self) -> None:
        self.refreshed.append("scatter")

    def update_decay_of_detector(self) -> None:
        self.refreshed.append("decay")

    def update_fit(self) -> None:
        self.refreshed.append("fit")


def test_apply_patterns_writes_and_refreshes_mle():
    """The handoff writes the arrays directly and refreshes without reloading files."""
    mle = _StubMLE()
    count = BurstAnalysisTool._apply_irf_bg_to_mle_widget(mle, _PATTERNS)
    assert count == 2
    assert set(mle.irf_np) == {"green", "red"}
    np.testing.assert_array_equal(mle.bg_np["green"], np.ones(8))
    assert mle._fit is None
    assert mle.refreshed == ["scatter", "decay", "fit"]


def test_irf_bg_panel_registered():
    """The IRF & Background tool is a panel of the burst-analysis shell."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import BURST_PANELS

    roles = [p.get("role") for p in BURST_PANELS]
    assert "irf_bg" in roles


def test_shell_stores_patterns_when_mle_absent(qapp, qtbot):
    """apply_irf_background_to_mle stores patterns on the context if MLE not loaded."""
    pytest.importorskip("tttrlib")
    tool = BurstAnalysisTool()
    qtbot.addWidget(tool)

    count = tool.apply_irf_background_to_mle(_PATTERNS)
    assert count == 2
    assert set(tool.workflow_context.irf_background_patterns) == {"green", "red"}

    # When the MLE panel later binds, the stored patterns are applied.
    mle = _StubMLE()
    tool._workflow_panels["mle"] = mle
    tool._apply_context_to_mle(mle)
    assert set(mle.irf_np) == {"green", "red"}


def test_shell_loads_irf_bg_panel(qapp, qtbot):
    """Navigating to the IRF & Background step instantiates the AutoForm tool."""
    pytest.importorskip("tttrlib")
    from chisurf.plugins.burst.burst_irf_bg.gui.tool import BurstIrfBackgroundTool

    tool = BurstAnalysisTool()
    qtbot.addWidget(tool)
    roles = [p.get("role") for p in tool.panels]
    tool._on_nav_changed(roles.index("irf_bg"))
    panel = tool._workflow_panels.get("irf_bg")
    assert isinstance(panel, BurstIrfBackgroundTool)
