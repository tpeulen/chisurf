"""The model-editor sections a FRET line depends on, drawn on the tool's own live models.

The emtk shell's fit editor draws a model's ``custom`` sections with
:class:`chisurf.emtk.model_sections.SectionViews` and sends every write through the
server (``model.section.call``). The FRET-line generator holds its components as
live models of its own, with no fit and no session, so it gives the same drawer a
local host: the section is resolved and its operations run on the selected
component with :func:`chisurf.server.services.model_sections.call_model_section`,
the same declared-section check and operation table the server uses.

Only the sections that change the lifetime spectrum a line reads are drawn
(:data:`LINE_SECTIONS`): the κ² regime (``kappa2_controls``) -- a static κ²
average gives a different E(τ_F) than the dynamic one. The decay-only sections
(IRF, anisotropy diagnostics, …) have no effect on a FRET line.
"""

from __future__ import annotations

from typing import Any, Callable

#: The ``custom`` section keys of a component's ``view.json`` that move a FRET line.
LINE_SECTIONS: tuple[str, ...] = ("kappa2_controls",)


class _LocalDocks:
    """What :class:`SectionViews` asks of the shell's docks, answered on a local model."""

    busy = False

    def __init__(
        self,
        model_of: Callable[[], Any],
        on_error: Callable[[str], None],
        on_called: Callable[[str, str, dict], None] | None = None,
    ) -> None:
        self._model_of = model_of
        self._on_error = on_error
        self._on_called = on_called
        self.status = ""

    def section_call(
        self,
        section: str,
        op: str,
        args: dict,
        label: str,
        after: Callable[[Any], None] | None = None,
        update: bool = True,
        failed: Callable[[str], None] | None = None,
    ) -> bool:
        """Run *op* of *section* on the selected component now; *after* gets the service result."""
        from chisurf.server.services.model_sections import call_model_section

        result = call_model_section(self._model_of(), section, op, args)
        if not result.get("ok"):
            error = str(result.get("error") or op)
            (failed or self._on_error)(error)
            return False
        self._on_error("")
        if self._on_called is not None:
            self._on_called(str(section), str(op), dict(args or {}))
        if after is not None:
            after(result)
        return True

    def request_frame(self) -> None:
        """The tool redraws every frame; nothing to request."""


class _Host:
    """The editor :class:`SectionViews` belongs to: its docks, form and table sources."""

    def __init__(self, docks: _LocalDocks, form: Any) -> None:
        self.docks = docks
        self.form = form
        self._sources: dict[str, Any] = {}

    @staticmethod
    def label_markup(text: str) -> str:
        return str(text)


class LineSections:
    """Resolve and draw :data:`LINE_SECTIONS` of a live component model.

    Parameters
    ----------
    model_of : callable
        Returns the selected component's live model.
    form : emtk.view_form.FormState
        The form the tool draws its spec sections with; the section drawers are
        installed on it and record their rectangles in it (``kappa2.static`` …).
    on_error : callable
        Receives a failed operation's message ("" clears it).
    on_called : callable, optional
        ``(section, op, args)`` after an operation succeeded (the guided tour listens).
    """

    def __init__(
        self,
        model_of: Callable[[], Any],
        form: Any,
        on_error: Callable[[str], None],
        on_called: Callable[[str, str, dict], None] | None = None,
    ):
        from chisurf.emtk.model_sections import SectionViews

        self._model_of = model_of
        self._state: Any = None
        self.views = SectionViews(_Host(_LocalDocks(model_of, on_error, on_called), form))
        self.views.install(form)

    def specs(self, model: Any | None = None) -> list[dict]:
        """The emtk spec sections drawing the model's line-relevant custom sections, resolved now."""
        from chisurf.server.services.model_sections import declared_sections, resolve_custom

        model = model if model is not None else self._model_of()
        self.views.reset()
        out: list[dict] = []
        try:
            customs = declared_sections(model)[1]
        except Exception:  # noqa: BLE001 - a model without a view has no sections to draw
            return out
        for n, section in enumerate(customs.values()):
            if str(getattr(section, "key", "")) not in LINE_SECTIONS:
                continue
            if self._state is None:
                from chisurf.server.session import SessionState

                self._state = SessionState()
            resolved = resolve_custom(section, model, None, self._state)
            common = {"description": str(getattr(section, "description", "") or "")}
            made = self.views.convert(resolved, common, n)
            out.extend(made if isinstance(made, list) else [made] if made else [])
        return out

    def draw_dialogs(self, box: Any) -> None:
        """The windows a section opened (*show κ²*, *compute κ²*, *calc R0*)."""
        self.views.draw_dialogs(box)
