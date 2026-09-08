"""The pipeline's shape: the step order, and what a drop must not do.

Both are decisions rather than details. The order is the owner's
(2026-09-08: *"0. Must the Setup selection. 1. File drop."*), and the drop
behaviour is a bug that presented as the application crashing.
"""

from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chisurf.plugins.burst.alex_suite.gui.tool import ALEX_PANELS  # noqa: E402


def _numbered() -> list[str]:
    """Return the numbered steps, in order, without their numbers."""
    return [
        panel["name"].split(". ", 1)[1]
        for panel in ALEX_PANELS
        if panel["name"][:1].isdigit()
    ]


def test_the_setup_is_the_first_step():
    """Setup, then files — the setup is what every later step reads.

    It is also the one thing that cannot be worked out from the data: on PIE /
    ns-ALEX there is no alternation to measure, so a user who never touches the
    alternation step still has to choose one.
    """
    assert _numbered()[0] == "Setup"
    assert _numbered()[1] == "Files"


def test_the_numbered_steps_are_numbered_from_one_without_gaps():
    """A pipeline with a 3 and a 5 and no 4 is a renumbering someone missed."""
    numbers = [
        int(panel["name"].split(".", 1)[0])
        for panel in ALEX_PANELS
        if panel["name"][:1].isdigit()
    ]
    assert numbers == list(range(1, len(numbers) + 1))


def test_the_conversion_step_is_optional():
    """Walking the pipeline must not rewrite the measurements.

    Step 3 replaces every file with a converted one. *Next* and the
    fast-forward pass over an ``optional`` step without running it, which is the
    only thing stopping a Next-walk from folding a meaningless micro-time into
    data that is already PIE.
    """
    alternation = next(p for p in ALEX_PANELS if p["role"] == "alternation")
    assert alternation.get("optional") is True


def test_dropping_a_file_does_not_convert_it(qapp):
    """No `.pto` drop guard on the data step.

    Dropping a vendor file elsewhere offers to embed it in a `.pto` immediately.
    Here that is wrong twice over: a µs-ALEX measurement converted before the
    alternation step still has its alternation in the *macro* time, so the
    container's micro-time is empty and the alternation step then converts that
    container into a second file; and the embed is a synchronous whole-file copy
    on the GUI thread — about two minutes for a 45 MB `.sm` — which is
    indistinguishable from the application having hung. That is what "dropping a
    .sm crashes it" was.
    """
    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstDataSelectionWidget

    panel = BurstDataSelectionWidget(guards=())
    try:
        assert panel.file_list._guards == ()
    finally:
        panel.deleteLater()


def test_the_shared_data_panel_still_guards_by_default(qapp):
    """Turning the guard off is this workflow's choice, not a global change."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstDataSelectionWidget

    panel = BurstDataSelectionWidget()
    try:
        assert "tttr_to_pto" in panel.file_list._guards
    finally:
        panel.deleteLater()
