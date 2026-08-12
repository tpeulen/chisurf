"""Run chimol as a desktop application, with no GUI toolkit.

What this is
------------
:func:`run` is chimol's **default** entry point. It builds the real viewer on a
``rendercanvas`` surface, wires the real command layer to the in-viewport
command line, loads whatever was named on the command line, and pumps the
canvas' loop. Nothing in this path imports Qt, and
``test_engine_is_portable.py`` runs it in a process where Qt cannot be imported
to keep that true.

There is no second viewer and no second command set here. The window that opens
is the same :class:`~chimol.renderer.view.MolView` the Qt plugin embeds and the
same ``Cmd`` the browser page runs; what differs is a canvas and five event
handlers, which is the whole point of :mod:`chimol.renderer.canvas_base`.

Where the pixels go
-------------------
An OS window when this machine can open one without a toolkit, which today means
the ``glfw`` backend and therefore the ``glfw`` package. Where that is missing
the offscreen canvas is used instead: every frame is still rendered, and
:func:`run` says so and draws one frame rather than blocking on a loop that can
show nothing. That distinction is reported rather than hidden, because "chimol
opened and I saw no window" is a much harder question than "chimol said it had
no windowing backend".
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Sequence

__all__ = ["ChimolApp", "main", "run"]

logger = logging.getLogger(__name__)


def _plain(text: str | None) -> str:
    """A docstring's first meaning, without its markup.

    The docs are reStructuredText, so a tooltip that shows them verbatim reads
    ``Change atom properties (PyMOL ``alter``)`` -- the backticks are for a
    documentation build, not for someone hovering a name in a listing.

    Parameters
    ----------
    text : str or None
        A docstring, or ``None``.

    Returns
    -------
    str
        The text with inline literal and emphasis markers removed, collapsed
        onto one line.
    """
    if not text:
        return ""
    # The *first* line, taken before the markup is stripped: stripping first
    # collapses the whole docstring onto one line, and the "summary" then runs
    # to several sentences -- which is a paragraph in a tooltip.
    for line in str(text).splitlines():
        if line.strip():
            plain = line.replace("``", "").replace("**", "").replace("*", "")
            return " ".join(plain.split())
    return ""


class ChimolApp:
    """A viewer, a command layer and a window, assembled.

    Parameters
    ----------
    size : tuple of int, optional
        Window size in logical pixels.
    backend : str, optional
        A ``rendercanvas`` backend name; see
        :func:`chimol.renderer.canvas_view.canvas_module`.
    title : str, optional
        Window title.

    Attributes
    ----------
    viewer : chimol.renderer.view.MolView
        The viewer.
    renderer : chimol.renderer.canvas_view.CanvasView
        The renderer drawing it, and the owner of the canvas.
    cmd : chimol.cmd.Cmd
        The command layer, wired to the in-viewport prompt.
    """

    def __init__(
        self,
        size: tuple[int, int] = (1280, 860),
        backend: str | None = None,
        title: str = "chimol",
    ) -> None:
        from ..cmd import Cmd
        from ..renderer.canvas_view import renderer_factory
        from ..renderer.view import MolView
        from .app import ViewerHost, sync_panel

        self.viewer = MolView(
            renderer_factory=renderer_factory(backend=backend, size=size, title=title)
        )
        self.renderer = self.viewer._renderer
        if self.renderer is None:
            raise RuntimeError(
                "chimol could not create a renderer: no WebGPU adapter, or no "
                "windowing backend. Install `glfw` for a window, or set "
                "CHIMOL_CANVAS=offscreen to render without one."
            )

        self.host = ViewerHost(self.viewer)
        self.cmd = Cmd(self.host)
        # The host replays scripts and demos through the same command layer a
        # typed line takes; without this `demo` reports that the host cannot
        # run scripts, which is what it did before `run_demo` existed here.
        self.host.cmd = self.cmd
        self._sync_panel = sync_panel
        self.host.on_objects_changed = self.sync_panel

        gui = self.renderer._internal_gui
        gui.visible = True
        gui.sequence_visible = True
        gui.set_run_command(self.cmd.do)
        gui.command_line.completions = self._completions
        self.cmd.set_message_callback(gui.command_line.append_message)
        self.cmd.set_error_callback(gui.command_line.append_error)
        self.host.on_error = gui.command_line.append_error
        gui.on_select = self._on_select
        gui.info_describe = self._describe
        gui.on_info_close = lambda: self.viewer.set_system_info_visible(False)
        gui.on_info_text = self.viewer.set_system_info_text
        gui.on_info_activate = self._type_at_prompt
        self._install_menus(gui)
        # Remember where the user put the windows. `enable_persistence` both
        # loads the saved layout and starts saving changes (a drag or a resize
        # calls `persist_windows` on its own), and it is deliberately opt-in so
        # that a bare panel built by a test never reads -- or on the first drag
        # rewrites -- the preferences of whoever runs the suite. Only the Qt
        # window opted in, so the toolkit-free run forgot its layout every time.
        self._apply_display_scale(gui)
        gui.enable_persistence()
        self.sync_panel()

    def _apply_display_scale(self, gui) -> None:
        """Pick a chrome scale for this display, unless the user set one.

        The chrome is drawn at the device pixel ratio, so on a HiDPI screen the
        effective magnification is ``ratio * ui_scale``; text is crisp only when
        that lands on a whole number. On an ordinary display and on a clean 2x
        one the answer is 1.0 -- the size the glyph atlas was baked at -- and
        only a fractional ratio needs a correction.

        Deliberately skipped when the configuration already differs from the
        default: guessing over a value somebody chose is worse than not
        guessing at all.

        Parameters
        ----------
        gui : chimol.renderer.internal_gui.InternalGui
            The chrome to scale.
        """
        from ..config import _DISPLAY_CONFIG  # noqa: PLC0415

        section = _DISPLAY_CONFIG.get("layout")
        current = section.get("ui_scale") if isinstance(section, dict) else None
        if current is not None and abs(float(current) - gui.DEFAULT_UI_SCALE) > 1e-6:
            return          # the user has an opinion; leave it alone

        ratio = 1.0
        for source in (self.renderer, getattr(self.renderer, "_canvas", None)):
            getter = getattr(source, "get_pixel_ratio", None) or getattr(source, "_ratio", None)
            if callable(getter):
                try:
                    ratio = float(getter()) or 1.0
                    break
                except Exception:  # noqa: BLE001 - a guess is not worth a frame
                    continue
        wanted = gui.suggest_ui_scale(ratio)
        if abs(wanted - float(gui.ui_scale)) > 1e-6:
            logger.info(
                "chimol: display pixel ratio %.3g, chrome scale %.3g", ratio, wanted
            )
            gui.set_ui_scale(wanted)

    # -- the chrome ----------------------------------------------------------

    def _install_menus(self, gui) -> None:
        """Put the menu bar and the toolbar into the viewport.

        Both are plain tables (``app.menu_bar``), and every entry is a command
        line, so the same bar works here, in the Qt window and in a browser --
        and a press is echoed at the prompt exactly like a typed one.

        Parameters
        ----------
        gui : chimol.renderer.internal_gui.InternalGui
            The in-viewport chrome to install them into.
        """
        from ..app.menu_bar import MENU_BAR, TOOLBAR

        gui.menubar = [(title, entries) for title, entries in MENU_BAR if entries]
        gui.toolbar = list(TOOLBAR)

    def sync_panel(self) -> None:
        """Re-read the object list into the in-viewport panel."""
        gui = self.renderer._internal_gui
        self._sync_panel(self.viewer, gui)
        # And the info panel's text, which nothing else in this host produced.
        self.host.update_system_info()
        try:
            gui.selecting = str(self.viewer.selection_mode)
        except Exception:
            pass
        self.renderer.update()

    def _completions(self, line: str, cursor: int):
        """Complete a command name or an argument, as the console does.

        Parameters
        ----------
        line : str
            The whole prompt line.
        cursor : int
            Caret position within it.

        Returns
        -------
        list of str
        """
        from ..cmd import completion

        head = line[:cursor].lstrip()
        parts = [p for p in head.replace(",", " ").split() if p]
        if not parts or (len(parts) == 1 and not head.endswith((" ", ","))):
            prefix = (parts[0] if parts else "").lower()
            return [n for n in completion.command_names(self.cmd) if n.startswith(prefix)]
        prefix = "" if head.endswith((" ", ",")) else parts[-1].lower()
        pool = completion.argument_pool(parts[0], self.cmd)
        return [item for item in pool if item.lower().startswith(prefix)]

    def _describe(self, token: str) -> str | None:
        """One line on what ``token`` is: a command, or a setting.

        Parameters
        ----------
        token : str
            A word clicked or hovered in the info panel.

        Returns
        -------
        str or None
            A short description, or ``None`` when the word names neither.
        """
        spec = self.cmd._registry.resolve(str(token).lower())
        if spec is not None:
            doc = _plain(spec.doc)
            first = doc.splitlines()[0].strip() if doc else ""
            return f"{spec.name} -- {first}" if first else f"{spec.name}: a command"

        # Settings come from the registry rather than from `_DISPLAY_CONFIG`:
        # the registry is what carries the one-line `doc`, and a setting's name
        # is not always its config key (`depth_cue` lives at
        # `depth_cue.enabled`), so walking the config finds neither the text nor
        # reliably the setting.
        from .. import settings as _settings

        try:
            spec = _settings.resolve(str(token))
        except Exception:  # noqa: BLE001 - not a setting either
            return None
        doc = _plain(spec.doc)
        return f"{spec.name} -- {doc}" if doc else f"{spec.name}: a {spec.kind} setting"

    def _type_at_prompt(self, token: str) -> None:
        """Put ``token`` at the command line rather than running it.

        A listing is something you browse: a click that *ran* the name under it
        would eventually run `delete`. So the name is typed, the prompt takes
        focus, and the reader decides.

        Parameters
        ----------
        token : str
            The word that was clicked.
        """
        gui = self.renderer._internal_gui
        line = gui.command_line
        spec = self.cmd._registry.resolve(str(token).lower())
        # A setting is edited with `set`; a command is typed as itself.
        text = f"{token} " if spec is not None else f"set {token}, "
        line.text = text
        line.cursor = len(text)
        gui.focus_command(True)
        self.renderer.update()

    def _on_select(self, name: str, indices, additive: bool) -> None:
        """Turn a sequence-strip selection into the viewer's own selection.

        Parameters
        ----------
        name : str
            The object the strip row belongs to.
        indices : iterable of int
            Residue columns.
        additive : bool
            Whether the selection adds to what is there.
        """
        columns = [int(i) for i in (indices or [])]
        for entry in self.viewer.list_objects():
            if str(entry.get("name")) == str(name):
                self.viewer.set_selected_residues(columns, object_id=entry.get("id"))
                return

    # -- running -------------------------------------------------------------

    def load(self, paths: str | Iterable[str]) -> int:
        """Load structures, through the same command a user would type.

        Parameters
        ----------
        paths : str or iterable of str
            One path, or several. A bare string is treated as a single path --
            a string *is* an iterable of characters, so without this
            ``load("x.pdb")`` quietly tries to load ``"x"``, then ``"."``, then
            ``"p"``, and reports six failures for one file. It logs rather than
            raises, so the mistake looks like a broken file instead of a
            misused signature.

        Returns
        -------
        int
            How many loaded.
        """
        if isinstance(paths, (str, os.PathLike)):
            paths = [paths]
        loaded = 0
        for path in paths:
            try:
                self.cmd.do(f"load {path}")
            except Exception as exc:  # noqa: BLE001 - one bad file, not the session
                logger.error("chimol could not load %s: %s", path, exc)
                continue
            loaded += 1
        return loaded

    def is_interactive(self) -> bool:
        """Whether this window can actually be looked at and driven.

        Returns
        -------
        bool
            ``False`` on the offscreen canvas, which renders every frame and
            shows none.
        """
        return bool(self.renderer.is_interactive())

    def draw_frame(self):
        """Render one frame now.

        Returns
        -------
        object
            The offscreen canvas returns the image; a window returns ``None``.
        """
        return self.renderer.draw_frame()

    def run(self) -> None:
        """Show the window and pump its loop until it closes."""
        self.renderer.run()

    def close(self) -> None:
        """Close the window."""
        self.renderer.close()


def run(
    paths: Sequence[str] = (),
    size: tuple[int, int] = (1280, 860),
    backend: str | None = None,
    once: bool = False,
) -> int:
    """Open chimol's Qt-free window and run it.

    Parameters
    ----------
    paths : sequence of str, optional
        Structures to load at start-up.
    size : tuple of int, optional
        Window size in logical pixels.
    backend : str, optional
        A ``rendercanvas`` backend name. ``None`` picks a windowing backend if
        one is installed and the offscreen canvas otherwise.
    once : bool, optional
        Build everything, render **one** frame and return, instead of entering
        the event loop. This is what ``--check`` runs: it exercises the whole
        default path -- the viewer, the command layer, the panel, the shaders --
        in a process that then exits, which is the only way a guard test can
        assert that the default entry point never imports a toolkit.

    Returns
    -------
    int
        A process exit code: ``0`` when the window ran, ``1`` when chimol could
        not build a renderer at all.
    """
    try:
        app = ChimolApp(size=size, backend=backend)
    except Exception as exc:  # noqa: BLE001 - report, do not traceback at a user
        logger.error("chimol could not start: %s", exc)
        return 1

    app.load(paths)

    if once:
        app.draw_frame()
        logger.info("chimol rendered one frame and is exiting (--check)")
        app.close()
        return 0

    if not app.is_interactive():
        # Starting chimol means opening a window. Falling back to the offscreen
        # canvas here would "succeed" by rendering one frame into a buffer
        # nobody can see and exiting 0 -- which is indistinguishable, from the
        # outside, from a window that opened and closed instantly. So this is
        # an error, and it names the one thing that fixes it.
        #
        # The offscreen canvas is still reachable, deliberately and only when
        # asked for: `--backend offscreen`, `CHIMOL_CANVAS=offscreen`, or
        # `--check`. Those are the paths the tests use.
        app.close()
        logger.error(
            "chimol has no toolkit-free windowing backend, so there is no "
            "window to open. Install `glfw` (it is declared in pixi.toml and "
            "pyproject.toml), or use `--qt` for the Qt window, or "
            "`--backend offscreen` if you meant to render without one."
        )
        return 1

    app.run()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse a command line and :func:`run`.

    Parameters
    ----------
    argv : sequence of str, optional
        Arguments after the program name; ``sys.argv[1:]`` by default.

    Returns
    -------
    int
        A process exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="chimol",
        description="chimol's molecular viewer, without a GUI toolkit.",
    )
    parser.add_argument("paths", nargs="*", help="structure files to load")
    parser.add_argument(
        "--backend",
        default=None,
        help=(
            "rendercanvas backend to draw on (glfw, offscreen, ...); a "
            "windowing one is used when installed, offscreen otherwise"
        ),
    )
    parser.add_argument(
        "--size",
        default=None,
        help="window size as WIDTHxHEIGHT, e.g. 1280x860",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="build everything, render one frame and exit; opens no loop",
    )
    parser.add_argument(
        "--qt",
        action="store_true",
        help="open the Qt window instead (handled by the module entry point)",
    )
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    size = (1280, 860)
    if args.size:
        try:
            width, height = (int(part) for part in str(args.size).lower().split("x"))
            size = (width, height)
        except ValueError:
            parser.error(f"--size must look like 1280x860, not {args.size!r}")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    return run(
        paths=args.paths, size=size, backend=args.backend, once=bool(args.check)
    )
