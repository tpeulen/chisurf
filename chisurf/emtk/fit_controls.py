"""The fit controller's dialogs in the emtk shell: ⚙ settings and the ``…`` dataset picker.

The controller itself is the Analysis dock's *Fit* panel
(``views/analysis.view.json`` over :class:`chisurf.emtk.fit_docks.AnalysisModel`).
What opens from it over the shell lives here:

* :class:`SettingsDialog` -- the sampling and fitting settings, the same form
  the Qt controller's ⚙ shows
  (:class:`chisurf.core.fitting.optimization_settings.OptimizationSettingsModel`),
  drawn natively and written to the user settings on *OK*. These are
  preferences shared by every fit, not session state, so no RPC is involved.
* :class:`DatasetPicker` -- the datasets of the session as a popup under ``…``;
  the pick is attached to the fit by the docks through ``fit.set_dataset``.
"""

from __future__ import annotations

from typing import Any, Callable

from emtk import im
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.plugins.emtk_layout import action_button


class SettingsDialog:
    """⚙: the sampling and optimiser settings over the shell.

    Parameters
    ----------
    on_close : callable
        ``on_close(written)`` once the dialog closes: ``True`` / ``False`` after
        *OK* (whether the settings file was written), ``None`` after *Cancel*.
    model : OptimizationSettingsModel, optional
        The form's model; a fresh one reads the current settings.
    """

    TITLE = "Sampling and fitting settings"

    def __init__(self, on_close: Callable[[bool | None], None], model: Any = None) -> None:
        from emtk.dialog_window import DialogWindow

        from chisurf.core.fitting.optimization_settings import OptimizationSettingsModel

        self.model = model if model is not None else OptimizationSettingsModel()
        self.form = FormState()
        self.window = DialogWindow(tr(self.TITLE), size=(560, 520), fit_height=True)
        self.window.show()
        self.on_close = on_close
        self.spec = self.model.view_dict()
        # A different sampler has different settings: the form is rebuilt from the model.
        self.model.set_rebuild_callback(self._rebuild)
        self.rects: dict[str, tuple] = {}

    def _rebuild(self) -> None:
        self.spec = self.model.view_dict()

    def accept(self) -> None:
        """*OK*: apply the settings to the session and write them to the user settings."""
        written = bool(self.model.apply())
        self.window.hide()
        self.on_close(written)

    def reject(self) -> None:
        """*Cancel*: nothing changes."""
        self.window.hide()
        self.on_close(None)

    def draw(self, box) -> None:
        """Draw the dialog over *box* (the whole shell)."""
        if not self.window.open:
            return
        pressed = self.window.begin(box)
        draw_form(self.spec, self.model, self.form, titles=True)
        im.separator()
        ok = im.button(tr("OK") + "##settings-ok")
        self.rects["ok"] = im.get_item_rect()
        im.set_item_tooltip(tr("Use these settings and save them to your settings file."))
        im.same_line()
        cancel = action_button("cancel", id="settings-cancel")
        self.rects["cancel"] = im.get_item_rect()
        self.rects.update(self.form.rects)
        self.window.end()
        if ok:
            self.accept()
        elif cancel or pressed == "close":
            self.reject()


class DatasetPicker:
    """``…``: the session's datasets as a popup; the pick goes to *on_pick*.

    Parameters
    ----------
    rows : list of dict
        The Datasets panel's rows (``uid``, ``name``, ``experiment``).
    anchor : tuple, optional
        The ``…`` button's rectangle; the popup opens below it.
    on_pick : callable
        ``on_pick(row)`` with the picked row, ``on_pick(None)`` when dismissed.
    """

    def __init__(
        self,
        rows: list[dict],
        anchor: Any,
        on_pick: Callable[[dict | None], object],
        title: str = "",
        allow_none: bool = False,
    ):
        from emtk.widgets.menus import MenuItem, Popup

        self.rows = list(rows)
        self.allow_none = allow_none
        if allow_none:
            self.rows.insert(0, {"name": tr("None (unload)"), "uid": "", "experiment": ""})
        self.on_pick = on_pick
        items = [
            MenuItem(
                row["name"] if not row.get("experiment") else f"{row['name']}  ({row['experiment']})"
            )
            for row in self.rows
        ]
        self.panel = Popup(items, title=title or tr("Attach a dataset to this fit"))
        if anchor is not None:
            x, y, _w, h = anchor
            self.panel.open_at(float(x), float(y) + float(h))
        else:
            self.panel.open_at()

    def pick(self, index: int) -> None:
        """Choose row *index* (what a click on its entry does)."""
        row = self.rows[index] if 0 <= index < len(self.rows) else None
        if row is not None and not row.get("uid"):
            row = None
        self.on_pick(row)

    def draw(self) -> None:
        from emtk import overlays

        def picked(item) -> None:
            index = next((i for i, row in enumerate(self.panel.entries) if row is item), -1)
            self.pick(index)

        overlays.popup(
            ("shell-dataset-picker", id(self)),
            self.panel,
            on_close=lambda: self.on_pick(None),
            on_pick=picked,
        )


__all__ = ["DatasetPicker", "SettingsDialog"]
