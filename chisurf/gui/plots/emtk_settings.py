"""The *Plot settings* dock: the current fit-window page's settings, drawn by emtk.

Every fit-window page used to bring its own Qt controller widget, and the main
window stacked them in its options dock and showed the current one. Now one emtk
surface is in that dock and draws whatever page is current: its AutoForm
settings spec (:meth:`chisurf.gui.plots.plotbase.Plot.draw_settings`), or a
line saying it has none. Qt only *hosts* the surface (:class:`PlotSettingsHost`).
"""

from __future__ import annotations

import logging
from typing import Any

from qtpy import QtCore, QtWidgets

logger = logging.getLogger(__name__)

#: The dock's background, the dark chrome every emtk tool shares.
BACKGROUND = (30, 32, 38)


def _surface_class():
    from emtk import im
    from emtk.app import ImApp

    class _PlotSettingsSurface(ImApp):
        """Draws :attr:`page`'s settings filling the whole surface."""

        def __init__(self) -> None:
            self.page: Any = None
            #: The exception the last frame's settings raised, ``None`` if they drew.
            self.last_error: Exception | None = None
            super().__init__(gui=self._render, continuous=False)

        def on_files_dropped(self, paths) -> bool:
            """Files dropped on the dock go to the page, if it takes them."""
            take = getattr(self.page, "on_paths_dropped", None)
            if not callable(take):
                return False
            take(list(paths))
            self.wants_frame = True
            return True

        def _render(self) -> None:
            vp = im.get_main_viewport()
            width, height = float(vp.size[0]), float(vp.size[1])
            flags = (im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
                     | im.WindowFlags.NO_MOVE | im.WindowFlags.NO_COLLAPSE)
            pad = 6.0  # the form's inset from the dock's edges
            im.begin("##plot-settings", (pad, pad, width - 2 * pad, height - 2 * pad), flags=flags)
            page = self.page
            self.last_error = None
            if page is None:
                im.text_disabled("No plot selected.")
            elif not page.has_settings():
                im.text_disabled(f"{page.name}: this page has no settings.")
            else:
                try:
                    page.draw_settings()
                except Exception as exc:  # a broken form must not take the dock down
                    self.last_error = exc
                    logger.exception("drawing the settings of %s failed", page.name)
                    im.text_colored((220, 90, 90), f"{page.name}: settings failed ({exc}).")
            im.end()

    return _PlotSettingsSurface


class PlotSettingsHost(QtWidgets.QWidget):
    """The Qt host of the settings surface: the one widget in the options dock.

    ``show_page(page)`` makes *page* the one whose settings are drawn.
    """

    #: It belongs to the main window, not to a fit window: a project load that
    #: replaces the fit windows keeps it (``chisurf.macros.core_fit``).
    outlives_fit_windows = True

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        from emtk.qt_host import ControlHost

        self.surface = _surface_class()()
        #: The window whose page is shown (``None``: none).
        self.owner: Any = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.host = ControlHost(self.surface, background=BACKGROUND, parent=self)
        layout.addWidget(self.host, 1)
        self.setMinimumHeight(220)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    @property
    def page(self) -> Any:
        """The page whose settings are shown."""
        return self.surface.page

    def owner_gone(self) -> bool:
        """Whether the window whose page is shown was closed, hidden or deleted."""
        from chisurf.gui.qt_lifetime import is_deleted

        owner = self.owner
        return owner is None or is_deleted(owner) or not owner.isVisible()

    def show_page(self, page: Any, owner: Any = None) -> None:
        """Show *page*'s settings (``None``: none), on behalf of window *owner*."""
        self.owner = owner if page is not None else None
        if page is not self.surface.page:
            self.surface.page = page
            if page is not None:
                page.set_settings_refresh(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        """Draw a new frame (the page's settings changed from elsewhere)."""
        from chisurf.gui.qt_lifetime import is_deleted

        self.surface.wants_frame = True
        if not is_deleted(self.host):
            self.host.update()

    def update(self, *args: Any) -> None:  # noqa: D401 - Qt's spelling
        """Repaint (what the main window calls on a dock becoming visible)."""
        self.refresh()


def host_in(layout: QtWidgets.QLayout) -> PlotSettingsHost | None:
    """The settings host living in *layout* (the main window's options dock), made once.

    Made again if the main window cleared the layout (its ``clear_layout``
    deletes what the dock held); ``None`` once the layout itself is gone.
    """
    from chisurf.gui.qt_lifetime import is_deleted

    if layout is None or is_deleted(layout):
        return None
    owner = layout.parentWidget() or layout
    host = getattr(owner, "_plot_settings_host", None)
    if host is None or is_deleted(host) or is_deleted(host.host):
        host = PlotSettingsHost()
        layout.addWidget(host, 1)
        # The options layout is top-aligned for Qt controllers of their own
        # height; the settings surface fills the dock.
        layout.setAlignment(host, QtCore.Qt.Alignment())
        owner._plot_settings_host = host
    return host
