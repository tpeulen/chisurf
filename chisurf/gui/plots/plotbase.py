"""The base of every fit-window page: Qt-free, drawn by emtk.

A page is what the fit window's emtk surface draws for one tab, plus the
settings the main window's *Plot settings* dock shows while that tab is current.
Neither is a widget. The page says what to draw in one of three ways (see
:func:`chisurf.gui.plots.emtk_page.page_body`):

* :meth:`Plot.add_panel` -- chiplot panels stacked top to bottom;
* ``emtk_body()`` -- one retained emtk control;
* ``emtk_draw(box)`` -- immediate-mode drawing into the page's box.

Its settings are an AutoForm ``view.json`` (:attr:`Plot.settings_view`) over a
plain model object (:meth:`Plot.settings_model`), drawn in place by
:func:`emtk.view_form.draw_form`; a page whose settings a spec cannot express
draws them itself in :meth:`Plot.draw_settings`.
"""

from __future__ import annotations

import json
import pathlib
import typing

import chisurf.core.fitting


class Hook:
    """A callback list with the ``connect``/``emit`` spelling of a Qt signal."""

    def __init__(self) -> None:
        self._callbacks: list[typing.Callable] = []

    def connect(self, callback: typing.Callable) -> None:
        """Call *callback* with the arguments of every :meth:`emit`."""
        self._callbacks.append(callback)

    def disconnect(self, callback: typing.Callable | None = None) -> None:
        """Forget *callback*, or every callback."""
        if callback is None:
            self._callbacks.clear()
        elif callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(self, *args: typing.Any) -> None:
        """Call every connected callback with *args*."""
        for callback in list(self._callbacks):
            callback(*args)


class Plot:
    """A fit-window page.

    Parameters
    ----------
    fit : Fit
        The fit the page shows.
    parent : object, optional
        Kept for the pages that address their owner.
    """

    #: The tab title.
    name = "Plot"
    #: The page's settings: a ``view.json`` file name beside the page's module,
    #: or the parsed spec. ``None``: the page has no settings.
    settings_view: str | dict | None = None

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, parent=None, **kwargs):
        self.parent = parent
        self.fit = fit
        self.widgets: list = []
        #: ``(chiplot.Panel, stretch)`` in order: what the fit window's emtk
        #: surface draws for this page, stacked top to bottom (see add_panel).
        self.emtk_panels: list = []
        self._settings_form = None
        self._settings_spec = None
        self._refresh: typing.Callable[[], None] | None = None
        self._settings_refresh: typing.Callable[[], None] | None = None

    # -- page body -----------------------------------------------------------

    def add_panel(self, panel=None, stretch: float = 1.0):
        """Declare a chiplot panel of this page, below the ones before it.

        A :class:`chisurf.gui.chiplot.Panel` is not a widget: the fit window
        draws its canvas on its emtk surface, sharing the height by *stretch*.
        Called without a panel, a new one is made. Returns the panel.
        """
        if panel is None:
            from chisurf.gui import chiplot as cp

            panel = cp.Panel()
        self.emtk_panels.append((panel, float(stretch)))
        return panel

    def update(self, *args, **kwargs) -> None:
        """Redraw from the current fit (pages override)."""

    def set_refresh_target(self, callback: typing.Callable[[], None] | None) -> None:
        """Install what :meth:`request_redraw` calls (the surface's frame request)."""
        self._refresh = callback

    def request_redraw(self) -> None:
        """Ask whatever shows this page for a new frame."""
        if self._refresh is not None:
            self._refresh()

    def close(self) -> None:
        """Release what the page holds (pages override)."""

    # -- settings ------------------------------------------------------------

    def settings_spec(self) -> dict | None:
        """The parsed settings spec, or ``None`` for a page without settings."""
        if self._settings_spec is None and self.settings_view is not None:
            view = self.settings_view
            if isinstance(view, dict):
                self._settings_spec = view
            else:
                module = __import__(type(self).__module__, fromlist=["__file__"])
                path = pathlib.Path(module.__file__).with_name(view)
                self._settings_spec = json.loads(path.read_text(encoding="utf-8"))
        return self._settings_spec

    def settings_model(self) -> typing.Any:
        """The object the settings spec reads and writes (the page itself)."""
        return self

    @property
    def settings_form(self):
        """The :class:`emtk.view_form.FormState` of the settings, kept between frames."""
        if self._settings_form is None:
            from emtk.view_form import FormState

            self._settings_form = FormState()
            self.register_settings_sections(self._settings_form)
        return self._settings_form

    def set_settings_refresh(self, callback: typing.Callable[[], None] | None) -> None:
        """Install what :meth:`request_settings_redraw` calls (the settings dock's)."""
        self._settings_refresh = callback

    def request_settings_redraw(self) -> None:
        """Ask the *Plot settings* dock for a new frame (a value changed underneath it)."""
        if self._settings_refresh is not None:
            self._settings_refresh()

    def register_settings_sections(self, form) -> None:
        """Register the page's ``custom`` settings sections in ``form.custom``."""

    def has_settings(self) -> bool:
        """Whether the page shows anything in the *Plot settings* dock."""
        return self.settings_spec() is not None or type(self).draw_settings is not Plot.draw_settings

    def draw_settings(self) -> None:
        """Draw the page's settings into the current emtk window."""
        spec = self.settings_spec()
        if spec is None:
            return
        from emtk.view_form import draw_form

        draw_form(spec, self.settings_model(), self.settings_form)

    def get_settings_state(self) -> dict:
        """The settings, for the project file (pages override)."""
        return {}

    def set_settings_state(self, state: dict) -> None:
        """Restore :meth:`get_settings_state` (pages override)."""
