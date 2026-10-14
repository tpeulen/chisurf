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
