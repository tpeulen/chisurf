"""Performance contracts that are cheap to break and expensive to notice.

Each of these guards a property that shows up only as sluggishness on large
data, never as a failure, so nothing else in the suite would catch a regression.
They are asserted against the source because the alternative — building the real
widgets and timing them — is slow and flaky.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_add_fit_batches_ui_updates_for_multi_dataset_adds_contract():
    """Adding many datasets must batch the UI updates instead of one per fit."""
    src = (ROOT / "chisurf" / "macros" / "core_fit.py").read_text(encoding="utf-8")

    assert "_defer_cs_update" in src
    assert "_ui_updates_frozen" in src
    assert "dataset_indices=[idx]" in src
    assert "_defer_cs_update=True" in src
    assert "_ui_updates_frozen=True" in src


def test_table_plot_avoids_resize_to_contents_and_hidden_refresh_contract():
    """The data table must not size columns to contents, nor refresh unseen.

    ``ResizeToContents`` measures every row of every column on each update —
    O(rows) per repaint, unusable on a decay with 4096 channels. The plot used to
    fight a third-party editor that set it; since the table became
    :mod:`chisurf.gui.widgets.chitable` the policy is simply never set, leaving
    Qt's interactive default. So the contract is now that the mode appears
    nowhere in the table stack, rather than that one file overrides it.

    The second half is unchanged: a plot that is not visible records that it
    needs a refresh instead of performing one, so a hidden tab costs nothing
    while a fit iterates.
    """
    plot = (ROOT / "chisurf" / "gui" / "plots" / "table_plot.py").read_text(encoding="utf-8")
    view = (ROOT / "chisurf" / "gui" / "widgets" / "chitable" / "view.py").read_text(
        encoding="utf-8"
    )

    for name, src in (("table_plot.py", plot), ("chitable/view.py", view)):
        assert "ResizeToContents" not in src, (
            f"{name} sets an O(rows) header resize policy; keep the interactive default"
        )

    assert "copy_curves=False" in plot          # do not duplicate the fit's arrays
    assert "if not self.isVisible():" in plot   # hidden plots do not refresh
    assert "self._refresh_pending = True" in plot
