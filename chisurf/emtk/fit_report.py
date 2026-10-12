"""The pictures of a fit report, drawn by emtk: each member's plot pages and its model editor.

The Qt shell grabbed its widgets (``QWidget.grab()``) for the Word report; these are the same two views, drawn
on emtk's CPU rasteriser (:func:`emtk.export.png_bytes`), so the report needs no window, no GPU and no Qt
widget: the fit window's pages (:class:`chisurf.emtk.fit_window.FitWindow`, the surface both shells show) and
the model's ``view.json`` editor (:class:`chisurf.emtk.model_editor.ModelEditor` over the editor the server
resolves, :func:`chisurf.server.services.model_svc.model_editor`).

Drawing takes emtk's frame lock, so it may run on the server's thread while the shell draws on its own.
:func:`chisurf.core.fitting.fit_export.write_report` puts the pictures into the report.
"""

from __future__ import annotations

import logging
from typing import Any

from emtk import im

_log = logging.getLogger("chisurf.emtk.fit_report")

#: Size of a plot page's picture and of the model editor's.
PLOT_SIZE = (960, 640)
EDITOR_SIZE = (720, 480)


class _ReadOnlyDocks:
    """What the model editor asks of its docks, for a picture: nothing is busy, no change is sent."""

    busy = False
    status = ""

    def __getattr__(self, name: str) -> Any:
        return lambda *args, **kwargs: None


class _EditorPicture:
    """An ImApp-shaped drawer of one resolved model editor, full window."""

    def __init__(self, uid: str, editor: dict) -> None:
        from emtk.app import ImApp

        from chisurf.emtk.model_editor import ModelEditor

        self.editor = ModelEditor(_ReadOnlyDocks())
        self.editor.set_editor(uid, editor)

        outer = self

        class _App(ImApp):
            def __init__(self) -> None:
                super().__init__(self.gui)

            def gui(self) -> None:
                im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
                im.set_next_window_size(im.get_main_viewport().size, im.Cond.ALWAYS)
                flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
                if im.begin("model editor picture", flags=flags):
                    outer.editor.draw()
                im.end()

        self.app = _App()


def resolved_editor(fit: Any, member: int = 0) -> dict | None:
    """The model editor of member *member* of *fit*, resolved as the server does (plain data)."""
    from chisurf.server.services.model_svc import model_editor
    from chisurf.server.session import SessionState

    group = list(getattr(fit, "grouped_fits", None) or [fit])
    result = model_editor(SessionState(fits=[group[member]]), fit_index=0)
    return result.get("editor") if result.get("ok") else None


def render_fit_images(
    fit: Any, *, editor: bool = True, pages: int | None = 1
) -> list[tuple[str, bytes]]:
    """``[(caption, png)]``: each member's fit window and its model editor, as the Qt report had them.

    *pages* is how many of the window's pages are drawn, from the first (the fit and its residuals;
    the Qt report grabbed the window as shown, which opens on it); ``None`` draws them all.

    The fit group's selected member is moved through each member while drawing and put back.
    """
    from emtk.export import png_bytes

    from chisurf.emtk.fit_window import FitWindow

    group = list(getattr(fit, "grouped_fits", None) or [fit])
    selected = getattr(fit, "selected_fit_index", 0) if len(group) > 1 else None
    uid = str(getattr(fit, "unique_identifier", "") or "fit")
    images: list[tuple[str, bytes]] = []
    try:
        for index, member in enumerate(group):
            if selected is not None:
                fit.selected_fit = index
            prefix = f"Fit #{index + 1}"
            window = FitWindow(uid, fit, str(getattr(fit, "name", "") or uid))
            try:
                count = len(window.specs) if pages is None else min(int(pages), len(window.specs))
                for page in range(count):
                    window.surface.set_current(page, notify=False)
                    if window.page(page) is None:
                        continue
                    window.poll()
                    png = png_bytes(window.surface, PLOT_SIZE, painter="pil")
                    images.append((f"{prefix} · {window.names[page]}", png))
            finally:
                window.close()
            if editor:
                resolved = resolved_editor(fit, index)
                if resolved is not None:
                    picture = _EditorPicture(
                        str(getattr(member, "unique_identifier", "") or uid), resolved
                    )
                    images.append(
                        (f"{prefix} · Model", png_bytes(picture.app, EDITOR_SIZE, painter="pil"))
                    )
    finally:
        if selected is not None:
            fit.selected_fit = selected
    return images


__all__ = ["EDITOR_SIZE", "PLOT_SIZE", "render_fit_images", "resolved_editor"]
