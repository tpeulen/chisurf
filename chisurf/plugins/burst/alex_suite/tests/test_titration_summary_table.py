"""The titration result's population table is drawn as a table, not as its markdown source."""

import emtk
from emtk import im
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.alex_suite.gui.app import _draw_summary

SUMMARY = (
    "**7 concentrations**, 2 shared populations (χ²ᵣ = 0.0308).\n\n"
    "| population | E | width | fraction (low → high) |\n|---|---|---|---|\n"
    "| 0 | 0.218 | 0.040 | 1.00 → 0.02 |\n| 1 ← | 0.680 | 0.044 | 0.00 → 0.98 |\n\n"
    "**K_d = 49.8 nM** (Hill n = 1.00), from population 1.\n\n_Three concentrations are needed._"
)


def test_the_summary_table_is_cells():
    io, storage, painter = emtk.IO(), {}, None
    for _ in range(3):
        painter = RecordingPainter()
        with emtk.frame(painter, (0, 0, 600, 300), io=io, storage=storage):
            im.begin("t", (0, 0, 600, 300))
            _draw_summary(SUMMARY)
            im.end()
    joined = " ".join(painter.strings)
    assert "|" not in joined and "**" not in joined and "---" not in joined
    for cell in ("population", "0.218", "0.680", "1.00 → 0.02"):
        assert any(s.strip() == cell for s in painter.strings), cell
    assert "K_d = 49.8 nM" in joined and "Three concentrations are needed." in joined
