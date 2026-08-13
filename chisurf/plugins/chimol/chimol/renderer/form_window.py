"""A viewport window built from a ChiSurf ``view.json``.

:class:`~chimol.renderer.settings_window.SettingsWindow` is this same panel over
the display configuration. This one is over *any* model and *any* view spec, so
a ChiSurf tool that already declares its interface as data gets a painted form
in the 3-D view for free -- no Qt, and therefore also in the browser.

The mapping from spec to rows lives in
:mod:`~chimol.cmtk.view_spec`; this file is the window around it.
"""
from __future__ import annotations

from typing import Any, Callable

from .internal_gui import GuiWindow
from ..cmtk.settings_editor import SettingsEditor
from ..cmtk.view_spec import load_view_spec, model_from_view_spec, unsupported_sections

__all__ = ["FormWindow", "SettingsProxy", "model_for"]


class SettingsProxy:
    """chimol's registered settings, as plain attributes.

    A view spec edits *attributes of a model*, and chimol's settings are not
    attributes of anything -- they are named entries resolved through
    :mod:`chimol.settings` onto a nested configuration. This is the missing
    object: ``proxy.cartoon_loop_radius`` reads and writes the setting of that
    name, so a spec can be written against the settings exactly as one is
    written against a model.

    Deliberately narrow: only *registered* names are exposed. An unregistered
    dotted config path has no documented type, range or PyMOL name, and a form
    row over one would be a slider with a guessed track -- which is what the
    display-settings panel is for.
    """

    def __init__(self, on_change: Callable[[str, Any], None] | None = None) -> None:
        from .. import settings as settings_api

        self._api = settings_api
        self._names = set(settings_api.setting_names())
        self._on_change = on_change

    def __dir__(self):
        return sorted(self._names)

    def __getattr__(self, name: str) -> Any:
        # Only reached for names not found normally, which is every setting.
        api = self.__dict__.get("_api")
        if api is None or name not in self.__dict__.get("_names", ()):
            raise AttributeError(name)
        return api.get_setting(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        if name not in self._names:
            raise AttributeError(name)
        self._api.set_setting(name, value)
        if self._on_change is not None:
            self._on_change(name, value)

    def describe(self, name: str) -> str:
        """The setting's one-line documentation, or an empty string."""
        try:
            return str(self._api.resolve(name).doc or "")
        except Exception:  # noqa: BLE001
            return ""


def model_for(spec: dict, viewer, on_change=None):
    """The object a spec wants to edit.

    A spec says so with a top-level ``"model"``: ``"settings"`` for chimol's
    registered settings, ``"viewer"`` (the default) for the viewer itself. A
    spec shipped by a ChiSurf tool names neither and is handed whatever the
    caller passes, which is the ordinary AutoForm case.
    """
    wanted = str(spec.get("model", "") or "").strip().lower()
    if wanted in ("settings", "setting", "display"):
        return SettingsProxy(on_change)
    return viewer


class FormWindow:
    """A painted form over a model, laid out by a view spec.

    Parameters
    ----------
    spec : dict or str or pathlib.Path
        A parsed ``view.json``, or a path to one.
    model : object
        What is being edited. Its attributes are read and written directly.
    title : str, optional
        The window's title. Defaults to the spec's own, then to the model's
        class name -- a window called "Form" tells nobody anything.
    key : str, optional
        Window identity, for hit reporting and for looking the panel up.
    on_change : callable, optional
        ``on_change(attr, value)`` after each write.

    Attributes
    ----------
    missing : list of str
        What the spec asked for and this panel could not draw -- an embedded
        plot, a parameter table, an attribute the model does not have. Read it
        and say so: a form quietly lacking half its controls looks like a tool
        that has none.
    """

    def __init__(
        self,
        spec,
        model: Any,
        *,
        title: str = "",
        key: str = "form",
        on_change: Callable[[str, Any], None] | None = None,
    ) -> None:
        self.spec = spec if isinstance(spec, dict) else load_view_spec(spec)
        self.model_object = model
        self.key = str(key)
        self.title = (
            title
            or str(self.spec.get("title") or "")
            or type(model).__name__
        )
        self.on_change = on_change
        self.model = model_from_view_spec(self.spec, model, on_change)
        self.editor = SettingsEditor(self.model, visible_rows=10)
        self.missing = unsupported_sections(self.spec, model)
        self._gui = None

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """Rebuild the rows, after the model changed shape.

        A spec with ``rebuild_on_change`` means exactly this: picking a
        different equation gives the model different parameters, so the rows
        have to be built again rather than re-read.
        """
        self.model = model_from_view_spec(self.spec, self.model_object, self.on_change)
        self.editor.model = self.model
        self.missing = unsupported_sections(self.spec, self.model_object)

    def attach(self, gui) -> None:
        """Remember the chrome, so the filter box can take the keyboard."""
        self._gui = gui

    def window(self, **kwargs) -> GuiWindow:
        """A :class:`GuiWindow` wired to this panel."""
        options = dict(key=self.key, title=self.title, x=40.0, y=110.0,
                       w=420.0, h=280.0, transient=True)
        options.update(kwargs)
        return GuiWindow(body=self.draw, on_press=self.press,
                         on_drag=self.drag, on_release=self.release, **options)

    # ------------------------------------------------------------------ #
    def draw(self, p, rect) -> None:
        """Paint the editor into the window's body."""
        line = p.line_height()
        self.editor.visible_rows = max(3, int((rect.h - line * 3.0) / (line * 1.5)))
        self.editor.draw(p, rect.x + 4.0, rect.y + 4.0, rect.w - 8.0, rect.h - 8.0)

    def press(self, x: float, y: float, rect) -> bool:
        """Route a press into the editor, and take the keyboard for the filter."""
        was_filter = self.editor._inside(self.editor._filter_box, x, y)
        self.editor.press(x, y)
        if was_filter and self._gui is not None:
            focus = getattr(self._gui, "focus_field", None)
            if callable(focus):
                focus(self.editor.filter.field)
        return True

    def drag(self, x: float, y: float, rect) -> bool:
        """Continue a scrollbar drag."""
        return self.editor.drag(x, y)

    def release(self) -> None:
        """End a drag."""
        self.editor.release()
