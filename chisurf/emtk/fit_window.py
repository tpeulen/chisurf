"""One fit's window in the emtk shell: the fit window's emtk surface, its pages built on demand.

The Qt shell puts a fit in a ``FitSubWindow`` whose content is already one emtk
surface (:func:`chisurf.emtk.fit_pages.surface.make_surface`); this
is the same surface without the Qt sub-window around it, hosted as a dock window
of the shell. The pages are the model's declared plots
(:func:`chisurf.emtk.fit_pages.plots.model_plot_specs`), each built
the first time its tab is drawn and re-read from the fit when the server says
the fit changed (:meth:`FitWindow.refresh`).

The surface, the page registry and the Code face are Qt-free
(:mod:`chisurf.emtk.fit_pages`). The page classes themselves still live under
``chisurf.gui.plots`` and draw through ``chisurf.gui.chiplot``; importing either runs the
``chisurf.gui`` package ``__init__``, which imports Qt (no ``QApplication`` is made and
nothing is drawn by Qt). The shell therefore imports this module only when the first fit
window opens; the remaining move is in ``okf/subsystems/qt-retirement.md``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

_log = logging.getLogger("chisurf.emtk.fit_window")

#: Prefix of a fit window's dock key.
FIT_KEY = "fit."


class FitWindow:
    """The emtk surface of one fit, with its pages.

    Parameters
    ----------
    uid : str
        The fit's unique identifier (the dock key is ``"fit." + uid``).
    fit : object
        The fit to draw (read only; edits go through the API).
    title : str
        The window title.
    request_frame : callable, optional
        The shell's frame request, for a page that changed between frames.
    """

    def __init__(
        self,
        uid: str,
        fit: Any,
        title: str,
        request_frame: Callable[[], None] | None = None,
    ) -> None:
        from chisurf.emtk.fit_pages.surface import make_surface
        from chisurf.emtk.fit_pages.plots import model_plot_specs

        self.uid = str(uid)
        self.fit = fit
        self.title = str(title)
        self.request_frame = request_frame
        self.surface = make_surface(on_current_changed=self._page_changed)
        self.specs = list(model_plot_specs(fit.model))
        self.plots: list[Any] = [None] * len(self.specs)
        self.names: list[str] = []
        #: The content box drawn into on the last frame (canvas coordinates).
        self.box: tuple[float, float, float, float] | None = None
        #: The Code face (the model's source and ``view.json``), made when first shown.
        self.code_face: Any = None
        self._stale: set[int] = set()
        for index, (plot_class, _options) in enumerate(self.specs):
            name = getattr(plot_class, "name", None)
            name = name if isinstance(name, str) else plot_class.__name__
            self.names.append(name)
            self.surface.add_page(f"{index}:{name}", name, lambda i=index: self.page(i))

    @property
    def key(self) -> str:
        """The dock window key."""
        return FIT_KEY + self.uid

    @property
    def app(self) -> Any:
        """The emtk app the shell draws and routes input to."""
        return self.surface

    # -- pages ----------------------------------------------------------------- #
    def page(self, index: int) -> Any:
        """The plot of page *index*, built on first use (its curves are read on the next frame)."""
        if not 0 <= index < len(self.specs):
            return None
        if self.plots[index] is None:
            plot_class, options = self.specs[index]
            try:
                self.plots[index] = plot_class(self.fit, **options)
            except Exception:  # noqa: BLE001 - one broken page must not take the window down
                _log.exception("building the %s page failed", self.names[index])
                return None
            self._stale.add(index)
            if self.request_frame is not None:
                self.request_frame()
        return self.plots[index]

    def current_page(self) -> Any:
        """The plot of the page whose tab is current."""
        return self.page(self.surface.current)

    def visible_indices(self) -> list[int]:
        """The pages in view: the current one and the front tab of every region."""
        surface = self.surface
        shown = {surface.index_of_key(key) for key in surface.docks.selected.values() if key}
        shown.update(
            surface.index_of_key(key)
            for key in surface.docks.floating()
            if surface.docks.is_visible(key)
        )
        if surface.current >= 0:
            shown.add(surface.current)
        return sorted(i for i in shown if i >= 0)

    def refresh(self) -> None:
        """Re-read every built page from the fit on the next :meth:`poll` (the fit changed)."""
        self._stale.update(i for i, plot in enumerate(self.plots) if plot is not None)
        if self.request_frame is not None:
            self.request_frame()

    def poll(self) -> None:
        """Update the stale pages that are in view (before the frame draws them)."""
        visible = set(self.visible_indices())
        for index in sorted(self._stale & visible):
            plot = self.plots[index]
            self._stale.discard(index)
            if plot is None:
                continue
            update = getattr(plot, "update_all", None) or getattr(plot, "update", None)
            if callable(update):
                try:
                    update()
                except Exception:  # noqa: BLE001 - a page that fails to read keeps its last curves
                    _log.exception("updating the %s page failed", self.names[index])
        self.surface.request_frame()

    # -- the Code face ------------------------------------------------------------ #
    def code_shown(self) -> bool:
        """Whether the window shows the model's code instead of its plots."""
        return bool(getattr(self.surface, "show_code", False))

    def show_code(
        self,
        shown: bool,
        files: dict | None = None,
        on_apply: Callable[[str, str], Any] | None = None,
    ) -> None:
        """Turn the window over: the model's code (*files* from ``model.code.files``) or the plots.

        *on_apply(path, text)* saves and applies an edit; the Qt fit window's
        ``FitCodeFace`` is drawn on the same surface.
        """
        if shown and self.code_face is None:
            from chisurf.emtk.fit_pages.code_face import FitCodeFace

            self.code_face = FitCodeFace(on_apply=on_apply)
            self.surface.code_face = self.code_face
            self.code_face.request_frame = self.surface.request_frame
        if shown and files:
            face = self.code_face
            face.set_files(list(files.get("files") or []))
            view_spec = files.get("view_spec")
            if view_spec and face.find_document(str(view_spec)) < 0:
                face.open_file(str(view_spec), record=False)
            if files.get("source"):
                face.open_file(str(files["source"]))
        self.surface.show_code = bool(shown)
        self.surface.request_frame()
        if self.request_frame is not None:
            self.request_frame()

    def _page_changed(self, index: int) -> None:
        self.page(index)
        if self.request_frame is not None:
            self.request_frame()

    def close(self) -> None:
        """Drop the pages."""
        self.plots = [None] * len(self.specs)
        self._stale.clear()


__all__ = ["FIT_KEY", "FitWindow"]
