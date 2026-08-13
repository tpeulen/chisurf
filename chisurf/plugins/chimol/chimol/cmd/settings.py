"""The ``set`` / ``get`` / ``unset`` / ``toggle`` commands.

These resolve names through :mod:`chimol.settings`, which owns the mapping from
PyMOL's flat setting namespace onto chimol's nested display config. The commands
themselves only parse, apply, and push the change to the live viewer.
"""

from __future__ import annotations

import pathlib

from typing import Any

from .. import settings as _settings
from ..settings import SettingSpec, SettingValueError, UnknownSettingError
from .base import BaseCmd
from .registry import command

# Setting paths whose section tells us which part of the viewer has to be
# poked after a change. Anything not listed here is picked up by the generic
# scene rebuild.
_CAMERA_SECTION = "camera"


class SettingsMixin(BaseCmd):
    """PyMOL-compatible access to the display settings."""

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #
    @command("set")
    def set(self, name: str = "", value: str = "") -> None:
        """Set a display setting (PyMOL ``set <name>, <value>``).

        Accepts any registered PyMOL setting name, an unambiguous prefix of one,
        or a dotted path into the display config such as ``metaball.alpha``.
        Boolean settings take ``on``/``off``.
        """
        name = str(name).strip().rstrip(",")
        value = str(value).strip()
        if not name:
            self._emit_error("Usage: set <name>, <value>")
            return

        # Representation toggles are commands in PyMOL (`show cartoon`), but
        # chimol has long accepted `set cartoon, on` and scripts rely on it.
        if self._apply_representation_toggle(name, value):
            return

        if not value:
            self._emit_error("Usage: set <name>, <value>")
            return

        try:
            spec, coerced = _settings.set_setting(name, value)
        except (UnknownSettingError, SettingValueError) as exc:
            self._emit_error(str(exc))
            return

        self._apply_setting(spec, coerced)
        self._emit_message(f"{spec.name} set to {_format(coerced)}")

    @command("get")
    def get(self, name: str = "") -> None:
        """Print the value of a display setting (PyMOL ``get <name>``)."""
        name = str(name).strip().rstrip(",")
        if not name:
            self._emit_error("Usage: get <name>")
            return
        try:
            spec = _settings.resolve(name)
            value = _settings.get_setting(name)
        except UnknownSettingError as exc:
            self._emit_error(str(exc))
            return
        self._emit_message(f"{spec.name} = {_format(value)}")

    @command("unset")
    def unset(self, name: str = "") -> None:
        """Restore a display setting to its default (PyMOL ``unset <name>``)."""
        name = str(name).strip().rstrip(",")
        if not name:
            self._emit_error("Usage: unset <name>")
            return
        try:
            spec, value = _settings.unset_setting(name)
        except UnknownSettingError as exc:
            self._emit_error(str(exc))
            return
        self._apply_setting(spec, value)
        self._emit_message(f"{spec.name} reset to {_format(value)}")

    @command("config")
    def config(self) -> None:
        """Open the settings editor **in the viewport**.

        This used to raise a modal Qt dialog with the display configuration in
        it as raw JSON. Two things were wrong with that and only one of them
        was the JSON: a dialog outside the 3-D view cannot be seen by the
        browser build, and it covers the very picture the settings change. It
        is an alias for `settings_panel` now, so the toolbar's *Cfg*, the menu
        bar's *Edit All...* and a typed `config` all land in the same panel.
        """
        self.settings_panel("on")

    @command("settings_panel")
    def settings_panel(self, action: str = "toggle") -> None:
        """Show, hide or toggle the settings editor **inside the viewport**.

        Every entry of the display configuration, grouped by section, edited
        with the same controls the rest of the chrome is drawn from. The Qt
        settings table shows the registered subset in a dock; this shows all of
        it in the view it changes, which is where the effect of a change is.

        Parameters
        ----------
        action : str, optional
            ``toggle`` (the default), ``on``/``show``, or ``off``/``hide``.
        """
        _window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
        if gui is None:
            self._emit_error("settings_panel: this renderer draws no chrome")
            return

        from ..renderer.settings_window import SettingsWindow

        wanted = str(action).strip().lower() or "toggle"
        existing = gui.window(SettingsWindow.KEY)
        if wanted in ("off", "hide", "0", "false"):
            if existing is not None:
                existing.visible = False
            viewer._update_view()
            return

        if existing is None:
            panel = SettingsWindow(viewer)
            panel.attach(gui)
            # Kept on the viewer so it outlives this call: the window holds
            # bound methods and nothing else keeps the panel alive.
            viewer._settings_controls = panel
            existing = gui.add_window(panel.window())
        elif wanted == "toggle" and existing.visible:
            existing.visible = False
            viewer._update_view()
            return
        else:
            # Values move under the panel -- a command, a preset, a script --
            # so the rows are rebuilt whenever it is asked for again.
            controls = getattr(viewer, "_settings_controls", None)
            if controls is not None:
                controls.refresh()

        existing.visible = True
        gui.raise_window(SettingsWindow.KEY)
        gui.layout(gui._width, gui._height)
        viewer._update_view()

    @command("fov", aliases=("field_of_view",))
    def fov(self, angle: str = "") -> None:
        """Read or set the vertical field of view, in degrees.

        The lens, not the zoom: the camera moves to keep the molecule the same
        size on screen, so a wider angle exaggerates perspective and a narrower
        one flattens it towards an orthographic view.

        A command as well as a setting because ``fov`` is what it is called
        everywhere else, and ``set field_of_view, 60`` is the only spelling
        that worked -- ``fov 60`` was "not implemented" and ``set fov, 60``
        "unknown setting", which between them read as the feature being
        missing.

        Parameters
        ----------
        angle : str, optional
            Degrees. Omitted, the current value is reported.
        """
        _window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        text = str(angle).strip()
        if not text:
            self._emit_message(
                f"field_of_view = {_settings.get_setting('field_of_view'):g} deg"
            )
            return
        try:
            value = float(text)
        except ValueError:
            self._emit_error(f"fov: '{angle}' is not an angle in degrees")
            return
        if not 1.0 <= value <= 175.0:
            self._emit_error(
                f"fov: {value:g} is outside 1-175 degrees; a lens outside that "
                "shows nothing"
            )
            return
        self.do(f"set field_of_view, {value:g}")

    @command("form")
    def form(self, path: str = "", title: str = "") -> None:
        """Open a ChiSurf ``view.json`` as a painted form in the viewport.

        ChiSurf tools declare their interface as data -- nested sections, each
        naming the model attribute it edits, its label, its range and its
        one-line description -- and AutoForm builds Qt widgets from it. Chimol
        has no Qt, so the same file is read here and drawn with the chrome's own
        controls, which means it also works in the browser.

        The model is the viewer, so a spec written against it edits the scene
        live. Anything the spec asks for that a painted panel cannot draw -- a
        plot, a parameter table, an attribute the model does not have -- is
        **reported** rather than dropped in silence.

        Parameters
        ----------
        path : str
            The ``*.view.json`` to read.
        title : str, optional
            Window title; the spec's own, or the model's class, by default.
        """
        _window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
        if gui is None:
            self._emit_error("form: this renderer draws no chrome")
            return
        if not str(path).strip():
            self._emit_error("Usage: form <file.view.json> [, title]")
            return

        from ..renderer.form_window import FormWindow, model_for
        from ..renderer.ui.view_spec import load_view_spec

        redraw = lambda _key, _value: viewer._update_view()  # noqa: E731
        try:
            spec = load_view_spec(self._unquote_name(path))
            panel = FormWindow(
                spec, model_for(spec, viewer, redraw),
                title=self._unquote_name(title),
                key=f"form:{pathlib.Path(str(path)).stem}",
                on_change=redraw,
            )
        except (FileNotFoundError, ValueError) as exc:
            self._emit_error(f"form: {exc}")
            return

        panel.attach(gui)
        # Kept on the viewer so it outlives this call: the window holds bound
        # methods and nothing else keeps the panel alive.
        forms = getattr(viewer, "_form_controls", None)
        if forms is None:
            forms = {}
            viewer._form_controls = forms
        forms[panel.key] = panel

        existing = gui.window(panel.key)
        if existing is None:
            existing = gui.add_window(panel.window())
        existing.visible = True
        gui.raise_window(panel.key)
        gui.layout(gui._width, gui._height)
        viewer._update_view()

        rows = len(panel.model.settings)
        message = f"form: {panel.title} -- {rows} control(s)"
        if panel.missing:
            message += f"; {len(panel.missing)} section(s) not drawn: " + \
                "; ".join(panel.missing[:3])
        self._emit_message(message)

    @command("debug_mode", aliases=("debug",))
    def debug_mode(self, state: str = "") -> None:
        """Show or hide the developer instruments (``debug [on|off]``).

        The instruments are the frame-rate readout and the chrome-size slider,
        bottom-right. They are hidden by default: a permanent number and a
        permanent slider in the corner of a figure are chrome that earns its
        space only while somebody is measuring.

        With no argument this **toggles**, which is what a menu entry needs.

        Parameters
        ----------
        state : str, optional
            ``on``/``1``/``true`` or ``off``/``0``/``false``. Empty toggles.
        """
        from ..config import _DISPLAY_CONFIG, save_user_display_config  # noqa: PLC0415

        layout = _DISPLAY_CONFIG.setdefault("layout", {})
        current = bool(layout.get("debug", False))
        text = str(state or "").strip().lower()
        if not text:
            wanted = not current
        elif text in ("on", "1", "true", "yes"):
            wanted = True
        elif text in ("off", "0", "false", "no"):
            wanted = False
        else:
            self._emit_error("Usage: debug [on|off]")
            return

        layout["debug"] = wanted
        # Persisted, like every other setting: a mode that has to be switched
        # on again every launch is one nobody leaves on while working.
        try:
            save_user_display_config()
        except Exception:  # noqa: BLE001 - an unwritable settings dir
            pass
        _window, viewer = self._require_window_and_viewer()
        if viewer is not None:
            try:
                viewer._update_view()
            except Exception:  # noqa: BLE001
                pass
        self._emit_message(
            "debug: developer instruments on (frame rate, chrome-size slider)"
            if wanted else "debug: developer instruments off"
        )

    @command("window_reset", aliases=("reset_windows",))
    def window_reset(self) -> None:
        """Put every in-viewport window back to its default place and size.

        And forget the saved layout, so the next run starts from the defaults
        too -- restoring only this session would let a bad layout return on the
        next start, which is the case this exists for.
        """
        _window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
        if gui is None:
            self._emit_error("window_reset: this renderer draws no chrome")
            return
        count = gui.reset_windows()
        viewer._update_view()
        self._emit_message(
            f"window_reset: {count} window(s) restored, saved layout cleared"
        )

    @command("toggle")
    def toggle(self, name: str = "") -> None:
        """Flip a boolean display setting (PyMOL ``toggle <name>``)."""
        name = str(name).strip().rstrip(",")
        if not name:
            self._emit_error("Usage: toggle <name>")
            return
        try:
            spec, value = _settings.toggle_setting(name)
        except (UnknownSettingError, SettingValueError) as exc:
            self._emit_error(str(exc))
            return
        self._apply_setting(spec, value)
        self._emit_message(f"{spec.name} set to {_format(value)}")

    @command("help_setting", aliases=("help_settings",))
    def help_setting(self, name: str = "") -> str:
        """Describe a setting, or list every setting when given no name.

        Into the **info panel**, for the same reason `help` goes there: there
        are 85 settings and the prompt's feedback line shows one at a time, so
        the answer scrolled straight past. The text is still returned, so a
        script or the console sees it too.
        """
        name = str(name).strip().rstrip(",")
        if not name:
            names = _settings.setting_names()
            text = f"Settings ({len(names)}):\n\n" + "\n".join(
                "  " + line for line in self._columns(names)
            )
        else:
            try:
                spec = _settings.resolve(name)
            except UnknownSettingError as exc:
                text = str(exc)
            else:
                text = (
                    f"{spec.name} ({spec.kind}, default {_format(spec.default)})\n"
                    f"  {spec.doc}\n"
                    f"  stored at {'.'.join(spec.path)}"
                )
        self._show_in_info_panel(text)
        return text

    # ------------------------------------------------------------------ #
    # Applying a change to the live viewer
    # ------------------------------------------------------------------ #
    def _apply_setting(self, spec: SettingSpec, value: Any) -> None:
        """Push a changed setting to the attached viewer, and remember it.

        Autosaved: a setting the user changed is a preference, and one that is
        forgotten when the window closes is not a preference at all. The write
        is best-effort -- a read-only home stops settings persisting rather
        than stopping the session.
        """
        from ..config import save_user_display_config  # noqa: PLC0415

        try:
            save_user_display_config()
        except Exception:  # noqa: BLE001 - never fail a `set` over a file
            pass

        viewer = getattr(self.window, "viewer", None)
        if viewer is None:
            return

        if spec.path == ("background",):
            _call(viewer, "set_background_color", value)
        elif spec.path[0] == _CAMERA_SECTION:
            if spec.path[-1] == "field_of_view":
                _call(viewer, "set_field_of_view", value)
        elif spec.path == ("selection", "mouse_selection_mode"):
            _call(viewer, "set_selection_level", value)
            # The word is drawn in the viewport block, which reads it back from
            # the viewer -- so the block has to be re-synced or the row keeps
            # showing the level that was replaced.
            sync = getattr(self.window, "sync_internal_gui", None)
            if callable(sync):
                try:
                    sync()
                except Exception:
                    pass
        elif spec.path[0] == "info_overlay":
            # The panel is chrome now, and the chrome re-reads its palette every
            # frame -- all this needs is a repaint.
            _call(viewer, "_request_chrome_redraw")

        # Everything else is read out of the display config during the rebuild.
        _call(viewer, "_update_view")

    def _apply_representation_toggle(self, name: str, value: str) -> bool:
        """Handle the legacy ``set <representation>, on|off`` spelling.

        Returns ``True`` when ``name`` was a representation and the toggle was
        applied (or rejected), so the caller stops.
        """
        key = name.lower()
        if key in ("bg_color", "bg_colour"):
            self.bg_color(value)
            return True
        if key in ("color_mode",):
            self.color(value)
            return True
        if key not in (
            "cartoon", "trace", "ca_trace", "atoms",
            "sticks", "surface", "dots", "plane", "grid",
        ):
            return False

        try:
            visible = _settings.coerce(value, "bool")
        except SettingValueError:
            self._emit_error(f"Value for set {key} must be one of: on, off, true, false, 1, 0")
            return True
        (self.show if visible else self.hide)(key)
        return True


def _call(target: object, method: str, *args: Any) -> None:
    """Best-effort call of an optional viewer method."""
    fn = getattr(target, method, None)
    if not callable(fn):
        return
    try:
        fn(*args)
    except Exception:
        pass


def _format(value: Any) -> str:
    """Render a setting value the way PyMOL echoes it."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format(v) for v in value) + "]"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


__all__ = ["SettingsMixin"]
