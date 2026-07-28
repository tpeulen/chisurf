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

import pathlib

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
