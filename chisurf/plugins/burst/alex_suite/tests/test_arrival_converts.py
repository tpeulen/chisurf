"""Arriving at the alternation step must leave converted data behind.

The step is declared ``optional``, and the workflow shell never runs an optional
step for you — ``process_current_step`` returns early on one, by design, so that
walking past a step cannot silently change the analysis. For µs-ALEX that made
**Next skip the conversion**: the burst search then ran on files whose
alternation was still in the macro time, gating on a micro-time of zeros, and
wrote a container per file full of zero per-detector counts.

So the step converts itself on arrival. These pin the two conditions that make
that safe.
"""

from __future__ import annotations

import numpy as np

from chisurf.plugins.burst.alex_suite.gui.alternation import AlexAlternationPanel


class _Tttr:
    def __init__(self, micro):
        self.micro_times = np.asarray(micro)


def _panel(monkeypatch, micro, path="/data/a.sm"):
    from pathlib import Path

    import chisurf.core.fio.staging as staging

    panel = AlexAlternationPanel.__new__(AlexAlternationPanel)
    panel._files = [Path(path)]
    monkeypatch.setattr(staging, "open_tttr", lambda *_a, **_k: _Tttr(micro))
    return panel


def test_a_macro_time_alternation_is_converted(monkeypatch):
    """An empty micro-time is what an unfolded µs-ALEX file looks like."""
    panel = _panel(monkeypatch, np.zeros(1000, dtype=int))
    assert panel._needs_conversion() is True


def test_data_that_already_has_a_micro_time_is_left_alone(monkeypatch):
    """PIE data, or a container this step produced earlier.

    Folding it again would overwrite a real micro-time with a phase — the one
    way this step can destroy information, so it is checked before, not after.
    """
    panel = _panel(monkeypatch, np.arange(1000))
    assert panel._needs_conversion() is False


def test_an_unreadable_file_is_not_converted(monkeypatch):
    """Unknown is not "needs folding": refuse rather than rewrite blindly."""
    from pathlib import Path

    import chisurf.core.fio.staging as staging

    panel = AlexAlternationPanel.__new__(AlexAlternationPanel)
    panel._files = [Path("/data/missing.sm")]

    def _raise(*_a, **_k):
        raise OSError("no such file")

    monkeypatch.setattr(staging, "open_tttr", _raise)
    assert panel._needs_conversion() is False


def test_the_step_is_still_optional_but_self_running():
    """Optional in the shell's sense, yet it must not need Next to act.

    If this ever stops being optional, Next will run it on PIE data too; if the
    auto-run is ever removed while it stays optional, the conversion is skipped
    again. Both halves are load-bearing together.
    """
    from chisurf.plugins.burst.alex_suite.gui.tool import ALEX_PANELS

    step = next(p for p in ALEX_PANELS if p["role"] == "alternation")
    assert step.get("optional") is True
    assert hasattr(AlexAlternationPanel, "_autorun")
    assert hasattr(AlexAlternationPanel, "_needs_conversion")
