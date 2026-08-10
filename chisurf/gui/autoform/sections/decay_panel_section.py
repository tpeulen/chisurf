"""The ``decay_panel`` view-spec section: a VV/VH fit, residuals and all.

Any tool that fits a single lifetime to a VV|VH stack can now show the whole
picture from its ``view.json`` — the same two-panel view the burst-wise tool
uses, for a burst, a region, or anything else that produces a stack and a model.

The section is deliberately thin. It owns *when* to redraw; what to draw comes
from the model as a
:class:`~chisurf.core.fluorescence.mle.display.DecayCurves`, and how to draw it
belongs to :class:`~chisurf.gui.widgets.decay_panel.DecayPanel`. That split is
why the awkward half — clipping a diverged model, area-matching the overlays,
pinning a log range that a runaway fit would otherwise take with it — is
testable without a screen.

View spec::

    {"type": "custom", "key": "decay_panel", "target": "current_region_curves",
     "title": "Decay",
     "options": {"refresh_on": ["results", "done"], "x_label": "micro-time channel"}}

``target`` names a zero-argument model method returning ``DecayCurves`` (or
``None`` for "nothing selected", which clears the panel rather than leaving the
previous selection's decay on screen — a stale decay beside a fresh table is a
number and a picture that disagree).
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.widgets.decay_panel import DecayPanel

from .registry import register_section

logger = logging.getLogger(__name__)


@register_section("decay_panel")
class DecayPanelSection(QtWidgets.QWidget):
    """A :class:`DecayPanel` bound to a model method returning ``DecayCurves``."""

    def __init__(self, model=None, target: str = "", parent=None, **options):
        """Build the section.

        Parameters
        ----------
        model : optional
            The view-model.
        target : str
            Name of a zero-argument method returning ``DecayCurves`` or ``None``.
        parent : optional
            Qt parent.
        **options
            ``title`` (group-box caption), ``x_label``, and ``refresh_on`` — the
            model events that trigger a redraw. Without the last one the panel
            draws once and then quietly shows the first fit forever.
        """
        super().__init__(parent)
        self._model = model
        self._target = target or options.get("target", "")

        self.panel = DecayPanel(
            title=str(options.get("title", "")),
            x_label=str(options.get("x_label", "Time (ch.)")),
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.panel)

        events = options.get("refresh_on") or ("results", "done", "preview")
        self._events = tuple(str(e) for e in events)
        observe = getattr(model, "add_observer", None)
        if callable(observe):
            observe(self._on_event)
        self.refresh()

    def _on_event(self, event: str) -> None:
        """Redraw when the model says something the panel depends on changed."""
        if event in self._events:
            self.refresh()

    def refresh(self) -> None:
        """Ask the model for the curves and draw them."""
        source = getattr(self._model, self._target, None) if self._target else None
        if not callable(source):
            # A missing or non-callable source is a spec mistake, and a blank
            # panel is how it would otherwise present — say it once, loudly
            # enough to find, and clear rather than show something stale.
            logger.warning("decay_panel: %r is not a callable model source", self._target)
            self.panel.set_curves(None)
            return
        try:
            self.panel.set_curves(source())
        except Exception:  # noqa: BLE001 - a bad fit must not take the panel down
            logger.debug("decay_panel: could not build the curves", exc_info=True)
            self.panel.set_curves(None)
