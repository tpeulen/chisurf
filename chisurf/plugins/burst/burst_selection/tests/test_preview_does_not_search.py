"""Arriving at the burst-search step must not run a burst search.

A full search of a converted ALEX container (20 M photons) takes ~4.5 s on the
GUI thread with no progress bar. It ran on *file selection*, which is what the
workflow shell does when it hands the step its measurements — so opening the
step froze the window, and pressing Next then ran the same search again through
the threaded path. The search belongs to the Run button and to Next.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from chisurf.plugins.burst.burst_selection.gui.tool import BurstSelectionTool


class _Recorder:
    """Stands in for the tool, recording which paths were analysed."""

    def __init__(self, cached: dict | None = None):
        self.analysed: list[Path] = []
        self.diagnostics_for: list[list[Path]] = []
        self.displayed: list[tuple] = []
        self.summary_text = ""
        self._cached = cached or {}
        self.summary = SimpleNamespace(setPlainText=self._set_summary, append=lambda *_: None)

    def _set_summary(self, text):
        self.summary_text = text

    # the pieces _update_selected_files touches
    def _frame_for_path(self, path):
        return self._cached.get(Path(path))

    def _analyze_file_frame(self, path, settings):
        self.analysed.append(Path(path))
        return f"frame:{Path(path).name}", {}

    def _file_index_for_path(self, path):
        return 0

    def _display_frame_set(self, frames, settings, indices):
        self.displayed.append((list(frames), list(indices)))

    def _load_tttr_for_plots(self, paths, settings):
        self.diagnostics_for.append([Path(p) for p in paths])


def _update(recorder, paths, *, preview):
    """Call the real method against the recorder."""
    BurstSelectionTool._update_selected_files(
        recorder, [Path(p) for p in paths], None, preview=preview)


def test_a_preview_searches_nothing():
    rec = _Recorder()
    _update(rec, ["/data/a.pto", "/data/b.pto"], preview=True)
    assert rec.analysed == []                      # the point
    assert len(rec.diagnostics_for) == 1           # but the plots still load
    assert "no burst search has run" in rec.summary_text


def test_a_preview_still_shows_a_table_it_already_has():
    rec = _Recorder(cached={Path("/data/a.pto"): "cached-frame"})
    _update(rec, ["/data/a.pto"], preview=True)
    assert rec.analysed == []
    assert rec.displayed == [(["cached-frame"], [0])]


def test_the_explicit_path_still_searches():
    rec = _Recorder()
    _update(rec, ["/data/a.pto"], preview=False)
    assert rec.analysed == [Path("/data/a.pto")]


def test_frames_stay_paired_with_their_files():
    """A cached frame in front of an uncached one must not shift the indices."""
    rec = _Recorder(cached={Path("/data/a.pto"): "cached-a"})
    seen: list[Path] = []
    rec._file_index_for_path = lambda p: (seen.append(Path(p)), len(seen) - 1)[1]
    _update(rec, ["/data/a.pto", "/data/b.pto"], preview=False)
    frames, indices = rec.displayed[0]
    assert frames == ["cached-a", "frame:b.pto"]
    assert indices == [0, 1]
    assert seen == [Path("/data/a.pto"), Path("/data/b.pto")]
