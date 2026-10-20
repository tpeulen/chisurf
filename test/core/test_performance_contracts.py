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


def test_table_plot_refreshes_only_when_visible_and_shares_curves_contract():
    """The data-table plot must not copy the fit's arrays nor refresh unseen.

    A plot that is not visible records that it needs a refresh instead of
    performing one, so a hidden tab costs nothing while a fit iterates; and it
    reads the fit's curves without duplicating them. (The Qt table half of this
    contract -- no O(rows) ``ResizeToContents`` header -- went with the Qt table.)
    """
    plot = (ROOT / "chisurf" / "emtk" / "fit_pages" / "pages" / "table_plot_emtk.py").read_text(
        encoding="utf-8"
    )

    assert "copy_curves=False" in plot  # do not duplicate the fit's arrays
    assert "if self._stale:" in plot  # hidden plots do not refresh
    assert "self._stale = True" in plot
