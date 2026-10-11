"""Per-state decays of one colour are told apart by line style.

The curve colour is the detection colour, so every state of the donor was the same solid green line
and the panel could not show which decay belonged to which state.
"""

from types import SimpleNamespace

import numpy as np

from chisurf.plugins.burst.burst_h2mm.gui import plots


def test_each_state_of_a_colour_gets_its_own_dash(monkeypatch):
    calls = []
    fake = SimpleNamespace(
        begin_plot=lambda *a, **k: True,
        end_plot=lambda *a, **k: None,
        setup_axes=lambda *a, **k: None,
        setup_axis_scale=lambda *a, **k: None,
        AXIS_Y1=1,
        SCALE_LOG10=2,
        set_next_line_style=lambda colour, weight, dash=None: calls.append(("style", dash)),
        plot_line=lambda label, x, y: calls.append(("line", label)),
    )
    monkeypatch.setattr(plots, "implot", fake)
    counts = np.ones((3, 1, 8))  # [state, colour, bin]
    decays = SimpleNamespace(
        centers_ns=lambda: np.arange(8.0), micro_time_ns=True, colours=["green"], n_states=3,
        colour_counts=counts,
    )
    owner = plots.ResultPlots()
    owner.draw_decays(decays, {"green"}, {0, 1, 2})
    dashes = [c[1] for c in calls if c[0] == "style"]
    assert [c[1] for c in calls if c[0] == "line"] == ["green S0", "green S1", "green S2"]
    assert dashes[0] is None  # S0 solid
    assert len({str(d) for d in dashes}) == 3  # three states, three styles
