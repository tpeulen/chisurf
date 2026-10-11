"""The Förster radius calculator over the emtk shell: *calc R0* of a FRET model's κ² row.

The form is ``forster_calculator.view.json`` beside this file, drawn by
:func:`emtk.view_form.draw_form` over
:class:`chisurf.core.fluorescence.fret.forster_calculator.ForsterCalculatorModel`
-- the same model the Qt ``ForsterCalculatorWidget`` draws. Picking a donor or
an acceptor fills its quantum yield or extinction coefficient from MMFDB and
recomputes R0; every edit of an input recomputes it too. *Apply R₀ to model*
hands the R0 (Å) to ``on_close`` and closes; *Close*, × and Escape hand over
``None``. The caller writes the value to the model's Förster radius.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

VIEW_JSON = Path(__file__).with_name("forster_calculator.view.json")


class ForsterCalculatorDialog:
    """*calc R0*: R0 of a dye pair from MMFDB spectra, over the shell.

    Parameters
    ----------
    on_close : callable
        ``on_close(r0)`` once the dialog closes: R0 in Å after *Apply R₀ to
        model*, ``None`` after *Close*, × or Escape.
    model : ForsterCalculatorModel, optional
        The form's model; a fresh one reads the probes from MMFDB (read-only).
    open_database : callable, optional
        ``open_database() -> MFDatabase`` for the fresh model; ignored when
        *model* is given.

    Attributes
    ----------
    rects : dict
        The drawn controls' rectangles by name (``donor``, ``acceptor``,
        ``donor_qy``, ``acceptor_emax``, ``refractive_index``, ``r0``,
        ``apply``, ``close``), for tests and guided tours.
    """

    TITLE = "Förster Radius Calculator"

    def __init__(
        self,
        on_close: Callable[[float | None], None],
        model: Any = None,
        open_database: Callable[[], Any] | None = None,
    ) -> None:
        from emtk.dialog_window import DialogWindow

        if model is None:
            from chisurf.core.fluorescence.fret.forster_calculator import ForsterCalculatorModel

            model = ForsterCalculatorModel(open_database=open_database)
        self.model = model
        self.on_close = on_close
        self.spec = json.loads(VIEW_JSON.read_text(encoding="utf-8"))
        self.form = FormState(on_used=self._used)
        self.rects: dict[str, tuple] = {}
        self.window = DialogWindow(tr(self.TITLE), size=(620, 420), fit_height=True)
        self.window.show()
        self._answer: tuple[bool, float | None] | None = None

    def _used(self, name: str) -> None:
        # The form's button row reports its presses here; the model has no
        # ``apply``/``close`` of its own -- closing is the dialog's business.
        if name == "apply" and self.model.r0 is not None:
            self._answer = (True, float(self.model.r0))
        elif name == "close":
            self._answer = (True, None)

    def apply(self) -> None:
        """*Apply R₀ to model*: hand the R0 to ``on_close`` and close (no-op without one)."""
        if self.model.r0 is not None:
            self._finish(float(self.model.r0))

    def reject(self) -> None:
        """*Close*: nothing is applied."""
        self._finish(None)

    def _finish(self, r0: float | None) -> None:
        self.window.hide()
        self.on_close(r0)

    def draw(self, box) -> None:
        """Draw the dialog over *box* (the whole shell)."""
        if not self.window.open:
            return
        pressed = self.window.begin(box)
        draw_form(self.spec, self.model, self.form, titles=True)
        self.rects.update(self.form.rects)
        self.window.end()
        answer, self._answer = self._answer, None
        if answer is not None:
            self._finish(answer[1])
        elif pressed == "close":
            self.reject()


__all__ = ["ForsterCalculatorDialog", "VIEW_JSON"]
