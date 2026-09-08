"""What the burst-selection diagnostics show, as a form rather than a toolbar.

The photon-range and layer toggles used to sit in the main toolbar, beside the
buttons that *do* things. They are neither: they select what the diagnostic
plots draw and over which slice of the file — settings, which belong in a form.
The toolbar was also simply full, so a wide "Show: … Photon Range: … to …" run
pushed the actions themselves off to the left.

This is a thin view-model: it holds nothing of its own and proxies straight to
the tool's existing widgets, so the two cannot drift apart and every existing
call site (``plot_min_spin``, ``show_all_photons_check``, the tests that use
them) keeps working while the *placement* moves.
"""

from __future__ import annotations

import logging
import pathlib

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "burst_display.view.json"


class BurstDisplayViewModel:
    """The display settings of the burst-selection diagnostics.

    Parameters
    ----------
    tool : BurstSelectionTool
        The tool whose controls this reflects. Held weakly by attribute access
        only — every property reads and writes the tool's own widgets, so the
        form is a *view* of them and never a second copy of the state.
    """

    def __init__(self, tool) -> None:
        self._tool = tool
        self._view_json = _VIEW_JSON
        self._display_observers: list = []

    def view_spec(self):
        """Resolve the AutoForm view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── which diagnostic layers are drawn ──────────────────────────────

    @property
    def show_all_photons(self) -> bool:
        """Draw the layers computed from every photon in the range."""
        box = getattr(self._tool, "show_all_photons_check", None)
        return bool(box.isChecked()) if box is not None else True

    @show_all_photons.setter
    def show_all_photons(self, value: bool) -> None:
        box = getattr(self._tool, "show_all_photons_check", None)
        if box is not None:
            box.setChecked(bool(value))

    @property
    def show_selected_photons(self) -> bool:
        """Draw the layers computed from the photons the burst search kept."""
        box = getattr(self._tool, "show_selected_photons_check", None)
        return bool(box.isChecked()) if box is not None else True

    @show_selected_photons.setter
    def show_selected_photons(self, value: bool) -> None:
        box = getattr(self._tool, "show_selected_photons_check", None)
        if box is not None:
            box.setChecked(bool(value))

    # ── which slice of the file is processed ───────────────────────────

    @property
    def photon_first(self) -> int:
        """First photon index to process (0 = the start of the file)."""
        spin = getattr(self._tool, "plot_min_spin", None)
        return int(spin.value()) if spin is not None else 0

    @photon_first.setter
    def photon_first(self, value: int) -> None:
        spin = getattr(self._tool, "plot_min_spin", None)
        if spin is not None:
            spin.setValue(int(value))

    @property
    def photon_last(self) -> int:
        """Last photon index to process (the default is the end of the file)."""
        spin = getattr(self._tool, "plot_max_spin", None)
        return int(spin.value()) if spin is not None else 0

    @photon_last.setter
    def photon_last(self, value: int) -> None:
        spin = getattr(self._tool, "plot_max_spin", None)
        if spin is not None:
            spin.setValue(int(value))

    # ── the visible slice, as time rather than photon indices ──────────

    def add_display_observer(self, callback) -> None:
        """Register a callback fired when a new search changes the timeline.

        The viewport widget has to re-read the span and the file list after a
        search: a window placed on a six-file selection means nothing on the
        one-file selection that replaced it.
        """
        if callback not in self._display_observers:
            self._display_observers.append(callback)

    def notify_display(self) -> None:
        """Tell the viewport widget the timeline changed."""
        for callback in list(self._display_observers):
            try:
                callback()
            except Exception:
                logger.warning("burst display: observer failed", exc_info=True)

    def _segments(self):
        """The concatenated timeline of the last search, as segments."""
        from . import timeline as _timeline

        diagnostics = getattr(self._tool, "_last_diagnostics", None) or []
        if not diagnostics:
            return []
        try:
            offsets = self._tool._macro_time_offsets_ms(diagnostics)
        except Exception:
            logger.warning("burst display: timeline offsets failed", exc_info=True)
            return []
        return _timeline.build_timeline(diagnostics, offsets)

    def timeline_span(self) -> float:
        """Length of the whole measurement in seconds (0 when nothing is loaded)."""
        from . import timeline as _timeline

        return _timeline.span(self._segments())

    def timeline_file_count(self) -> int:
        """How many files carry photons in the current selection."""
        return len(self._segments())

    def timeline_file_at(self, start_s: float):
        """``(name, position, total)`` of the file visible at ``start_s``."""
        from . import timeline as _timeline

        segments = self._segments()
        segment = _timeline.locate(segments, float(start_s))
        if segment is None:
            return "", 0, 0
        position = segments.index(segment) + 1
        return segment.name, position, len(segments)

    def show_time_window(self, start_s: float, length_s: float) -> None:
        """Draw only ``[start_s, start_s + length_s]``.

        Written as a photon-index range, because that is what the plots already
        take — so this adds a way of asking, not a second thing to keep in step.
        """
        from . import timeline as _timeline

        segments = self._segments()
        if not segments:
            return
        first, last = _timeline.photon_range(
            segments, float(start_s), float(start_s) + float(length_s))
        self._set_range(first, last)

    def show_whole_timeline(self) -> None:
        """Draw every photon of every file (what the plots did before)."""
        segments = self._segments()
        if not segments:
            return
        last = segments[-1].first_photon + segments[-1].n_photons - 1
        self._set_range(0, last)

    def _set_range(self, first: int, last: int) -> None:
        """Write the photon range, replotting once rather than twice.

        Setting the two spin boxes separately fires two replots, and the first
        of them is over a range where the new minimum is above the old maximum
        -- an empty plot, drawn and thrown away on every drag of the slider.
        """
        low = getattr(self._tool, "plot_min_spin", None)
        high = getattr(self._tool, "plot_max_spin", None)
        if low is None or high is None:
            return
        low.blockSignals(True)
        try:
            low.setValue(int(first))
        finally:
            low.blockSignals(False)
        high.setValue(int(last))
