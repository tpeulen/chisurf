"""AutoForm ``setup_selector`` section: pick a saved detector setup.

Tools that read photon streams work in terms of the **detector windows** defined
once in the Detector Def tool (green / red / yellow …, each a channel set plus
optional micro-time gates), not raw routing-channel numbers. Historically every
such tool embedded its own ``SetupSelector`` widget in hand-written Qt; this
section makes the picker available to any declarative view::

    {"type": "custom", "key": "setup_selector", "title": "Detector setup",
     "options": {"attr": "setup_name", "call": "apply_setup_settings"}}

Options:

* ``attr`` (str) — model attribute receiving the selected setup **name**.
* ``call`` (str) — model method invoked with the setup **payload**
  ``{"name": …, "detectors": {…}}`` on every change; the established convention
  is ``apply_setup_settings`` (the same hook the imaging pipeline steps use), so
  a view-model needs no extra glue.
* ``label`` (str, default ``"Setup"``) — caption left of the combo (``""`` hides it).
* ``show_summary`` (bool, default ``True``) — muted one-line detector summary.
* ``show_reload`` (bool, default ``True``) — the ``🔄`` re-read button.
* ``placeholder`` (str) — label of the empty entry (e.g. ``"— none —"``).
"""

from __future__ import annotations

import logging
from typing import Any

from qtpy import QtWidgets

from .registry import register_section

logger = logging.getLogger(__name__)


@register_section("setup_selector")
class SetupSelectorSection(QtWidgets.QWidget):
    """Detector-setup picker bound to a model attribute and/or a model method."""

    #: marker so :meth:`AutoForm.refresh_plots` / ``sync_fields`` re-read it.
    AUTOFORM_REFRESH = True
    is_form_field = False

    def __init__(self, model=None, target: str | None = None, **options: Any):
        super().__init__()
        self._model = model
        self._attr = options.get("attr") or target or ""
        self._call = options.get("call") or ""

        from chisurf.gui.widgets.setup_selector import SetupSelector

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = str(options.get("label", "Setup"))
        if label:
            caption = QtWidgets.QLabel(label)
            caption.setToolTip(
                "Named detector windows to use as image channels (edited in the Detector Def tool)."
            )
            layout.addWidget(caption)
        self.selector = SetupSelector(
            show_summary=bool(options.get("show_summary", True)),
            show_reload=bool(options.get("show_reload", True)),
            placeholder=str(options.get("placeholder", "")),
        )
        self.selector.combo.setToolTip(
            "Detector setup: the named detector windows (green / red / …) this tool "
            "offers as image channels. Setups are created and edited in the Detector "
            "Def tool; here you only pick one. Leave empty to use the raw detector "
            "channels found in the file."
        )
        layout.addWidget(self.selector, 1)
        self.selector.setupChanged.connect(self._on_changed)
        # Adopt whatever the selector restored (last-used setup) right away.
        self._on_changed(self.selector.current_setup())

    def _on_changed(self, name: str) -> None:
        """Write the picked setup to the model and notify it."""
        if self._model is None:
            return
        if self._attr:
            try:
                setattr(self._model, self._attr, name)
            except Exception:
                logger.debug("setup_selector: cannot set %r", self._attr, exc_info=True)
        if self._call:
            fn = getattr(self._model, self._call, None)
            if callable(fn):
                try:
                    fn({"name": name, "detectors": dict(self.selector.current_detectors())})
                except Exception:
                    logger.debug("setup_selector: %r failed", self._call, exc_info=True)

    def sync(self) -> None:
        """Re-select the model's setup name without re-notifying the model."""
        if self._model is None or not self._attr:
            return
        name = str(getattr(self._model, self._attr, "") or "")
        if name and name != self.selector.current_setup():
            self.selector.blockSignals(True)
            self.selector.set_current(name)
            self.selector.blockSignals(False)

    def refresh(self) -> None:
        """Alias of :meth:`sync` (AutoForm refreshes plots and widgets alike)."""
        self.sync()


__all__ = ["SetupSelectorSection"]
