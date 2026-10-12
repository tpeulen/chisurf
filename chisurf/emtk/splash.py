"""The emtk shell's boot splash: a frameless window with the ChiSurf art while the session starts.

The art (``chisurf/gui/resources/icons/splashscreen.svg``) was designed as a splash *screen*: a
shaped picture standing on the desktop, with the start's progress written over its lower part. So,
like the Qt window's ``QSplashScreen``, it opens as its own top-level window -- undecorated,
floating above other windows, centred on the primary screen, its framebuffer transparent where the
art is (:class:`emtk.native.NativeHost` ``decorated=False, floating=True, transparent=True,
centred=True``) -- and the main window opens only once the session is ready; the splash closes as
soon as the main window has drawn its first frame (no moment without a window).

:func:`run_with_splash` is the sequence (:class:`SplashRun`):

1. the splash window opens and draws (nothing of the shell is built yet, so it appears at once);
2. after its first frame the shell is built (``make_app(splash=state)``); its session starts on a
   worker and runs the ``surface="emtk"``, ``phase="splash"`` stages declared in
   ``chisurf/startup/services.d/25_emtk_splash.json`` through
   :class:`~chisurf.startup.services.AppStartupServiceManager` -- each stage's label and progress
   land in :class:`SplashState`, which the splash draws;
3. when the session is up (or failed: the main window then says why) the main window opens;
4. after the main window's first frame the splash closes.

What it shows, where the Qt splash shows it on the art: a progress bar, the stage under way
(translated where it is drawn), the last log line (INFO and up), the copyright, version and
licence on the left, the contributors on the right.

The art is ``splash.png``, the SVG rasterised at twice its size (1065 x 542 texels) so a HiDPI
screen gets device pixels; the splash's surface gets its own 2048-texel image atlas, since emtk's
default 1024 one declines an image that wide::

    rsvg-convert -z 2 chisurf/gui/resources/icons/splashscreen.svg -o chisurf/emtk/splash.png

The stage callback and the log handler run on worker threads; they only assign plain values and
ask for a frame, and the splash's frame reads them.
"""

from __future__ import annotations

import datetime
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from emtk.i18n import tr

_log = logging.getLogger("chisurf.emtk.shell")

#: The art, twice its natural size.
ART = Path(__file__).with_name("splash.png")
#: The art's natural size in logical pixels (the SVG's ``width`` / ``height``): the splash window's.
ART_SIZE = (532, 271)
#: Who wrote ChiSurf, as the Qt splash credits it.
CONTRIBUTORS = "Thomas-Otavio Peulen, Katherina Hemmen, Jakub Kubiak"
#: The Qt splash cuts a log line at this many characters.
LOG_CHARACTERS = 75
#: The stage text before the first stage starts.
STARTING = "Starting up…"
#: Seconds between the splash's frames while it waits (its stage text changes from a worker).
POLL = 0.05

#: Where the parts sit on the art (logical pixels), as the Qt splash places them.
BAR = (130.0, 211.0, 272.0, 5.0)
STAGE_TOP = 218.0
LOG_TOP = 236.0
#: The left column (copyright, version, licence) and the right one (contributors): x, top, width.
LEFT_COLUMN = (10.0, 175.0, 220.0)
RIGHT_COLUMN = (240.0, 178.0, 284.0)
#: Small print, relative to the interface font (the Qt splash's 8 pt).
SMALL = 0.7

BAR_TRACK = (255, 255, 255, 40)
BAR_FILL = (0, 255, 0, 255)
TEXT = (235, 235, 235, 255)
MUTED = (175, 175, 175, 255)


class _LastLine(logging.Handler):
    """Keep the last INFO-or-higher log message (any thread) and ask for a frame."""

    def __init__(self, state: SplashState) -> None:
        super().__init__(logging.INFO)
        self.state = state
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            lines = self.format(record).splitlines()
        except Exception:  # noqa: BLE001 - a log line must never break the start
            return
        message = lines[0] if lines else ""
        if len(message) > LOG_CHARACTERS:
            message = message[: LOG_CHARACTERS - 1] + "…"
        self.state.log_line = message
        self.state.wake()


class SplashState:
    """What the splash shows: the stage under way, its progress, the last log line.

    Written from the session's worker (:meth:`stage_started`) and the log handler, read by the
    splash's frames.

    Parameters
    ----------
    wake : callable, optional
        Thread-safe frame request of the splash window.
    """

    def __init__(self, wake: Callable[[], None] | None = None) -> None:
        self._wake = wake
        #: Whether the splash is up.
        self.active = False
        #: The label of the stage that started last (untranslated; drawn through ``tr``).
        self.stage = STARTING
        #: That stage's declared progress, 0..100.
        self.progress = 0
        #: The stages seen, in order (their ``id``).
        self.stages: list[str] = []
        #: The last log line.
        self.log_line = ""
        self._handler: _LastLine | None = None
        self._level: int | None = None
        self._lock = threading.Lock()

    def wake(self) -> None:
        if self._wake is not None:
            self._wake()

    def start(self) -> None:
        """The splash is up: listen to the log until :meth:`finish`."""
        self.active = True
        if self._handler is None:
            self._handler = _LastLine(self)
            logging.getLogger().addHandler(self._handler)
            # ChiSurf's INFO lines (the stages' timings, the server's start) are what the line
            # shows, as the Qt splash shows them; the shell keeps WARNING otherwise.
            chisurf_log = logging.getLogger("chisurf")
            if chisurf_log.getEffectiveLevel() > logging.INFO:
                self._level = chisurf_log.level
                chisurf_log.setLevel(logging.INFO)

    def stage_started(self, payload: dict) -> None:
        """A startup stage began (the manager's ``on_stage_start``; any thread)."""
        with self._lock:
            self.stage = str(payload.get("label") or payload.get("id") or "")
            self.progress = max(self.progress, int(payload.get("progress") or 0))
            self.stages.append(str(payload.get("id") or ""))
        self.wake()

    def finish(self) -> None:
        """The splash is gone: stop listening to the log."""
        self.active = False
        self.progress = 100
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None
        if self._level is not None:
            logging.getLogger("chisurf").setLevel(self._level)
            self._level = None

    def lines(self) -> dict[str, str]:
        """The splash's text, translated."""
        from chisurf.core.info import __license__, __version__

        year = datetime.date.today().year
        return {
            "stage": tr("Starting up…") if self.stage == STARTING else tr(self.stage),
            "log": self.log_line,
            "copyright": tr("(c) 2014-{year} ChiSurf Team").format(year=year),
            "version": tr("Version: {version}").format(version=__version__),
            "license": tr("Licensed under {license}").format(license=__license__),
            "contributors_title": tr("Developers & Contributors:"),
            "contributors": CONTRIBUTORS,
        }


class SplashApp:
    """The splash window's control: the art filling the window, the text on it.

    Parameters
    ----------
    state : SplashState
    on_frame : callable, optional
        Called after every frame (the splash's step of :func:`run_with_splash`).
    """

    #: The window opens at the art's natural size.
    window_size = ART_SIZE

    def __init__(self, state: SplashState, on_frame: Callable[[], None] | None = None) -> None:
        self.state = state
        self.on_frame = on_frame
        self.frames = 0
        self._texture: Any = None
        self._frame_request: Callable[[], None] | None = None
        #: The parts drawn last frame: ``key -> (box, text drawn)`` (``art``, ``bar``, ``stage``,
        #: ``log``, ``copyright``, ``version``, ``license``, ``contributors_title``, ``contributors.N``).
        self.drawn: dict[str, tuple[tuple[float, float, float, float], str]] = {}

    # -- the control contract ----------------------------------------------------------- #
    def set_frame_request_callback(self, callback) -> None:
        self._frame_request = callback

    def request_frame(self) -> None:
        if self._frame_request is not None:
            self._frame_request()

    def animating(self) -> bool:
        return False

    def next_frame_in(self) -> float | None:
        return POLL if self.state.active else None

    def texture(self) -> Any:
        """The art as a texture (read once), ``None`` when it cannot be read."""
        if self._texture is None and ART.is_file():
            from emtk.texture import Texture

            try:
                self._texture = Texture.from_file(ART)
            except Exception:  # noqa: BLE001 - the splash still shows its text
                _log.exception("reading the splash art failed")
                self._texture = False
        return self._texture or None

    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        from emtk import painter as paint

        self.drawn = {}
        sx, sy = w / ART_SIZE[0], h / ART_SIZE[1]

        def box(bx, by, bw, bh):
            return (x + bx * sx, y + by * sy, bw * sx, bh * sy)

        texture = self.texture()
        if texture is not None:
            paint.image(painter, x, y, w, h, texture)
        self.drawn["art"] = ((x, y, w, h), "")
        lines = self.state.lines()

        bx, by, bw, bh = box(*BAR)
        painter.fill_rect(bx, by, bw, bh, BAR_TRACK)
        fraction = max(0.0, min(1.0, self.state.progress / 100.0))
        if fraction > 0.0:
            painter.fill_rect(bx, by, bw * fraction, bh, BAR_FILL)
        self.drawn["bar"] = ((bx, by, bw, bh), f"{self.state.progress}")

        line = float(painter.line_height())
        self._text(
            painter,
            "stage",
            lines["stage"],
            box(10, STAGE_TOP, 512, 0)[:3],
            line,
            paint.ALIGN_CENTER,
            TEXT,
            bold=True,
        )
        paint.set_font_scale(painter, SMALL)
        try:
            small = float(painter.line_height())
            self._text(
                painter,
                "log",
                lines["log"],
                box(10, LOG_TOP, 512, 0)[:3],
                small,
                paint.ALIGN_CENTER,
                MUTED,
            )
            lx, ly, lw = box(*LEFT_COLUMN, 0.0)[:3]
            for key in ("copyright", "version", "license"):
                self._text(
                    painter,
                    key,
                    lines[key],
                    (lx, ly, lw),
                    small,
                    paint.ALIGN_LEFT | paint.ALIGN_VCENTER,
                    TEXT,
                )
                ly += small
            rx, ry, rw = box(*RIGHT_COLUMN, 0.0)[:3]
            rows = [lines["contributors_title"], *self._wrap(painter, lines["contributors"], rw)]
            for index, row in enumerate(rows[:4]):
                key = "contributors_title" if index == 0 else f"contributors.{index}"
                self._text(
                    painter,
                    key,
                    row,
                    (rx, ry, rw),
                    small,
                    paint.ALIGN_LEFT | paint.ALIGN_VCENTER,
                    TEXT,
                )
                ry += small
        finally:
            paint.set_font_scale(painter, 1.0)
        self.frames += 1
        if self.on_frame is not None:
            self.on_frame()

    def _text(self, painter, key, string, column, height, align, colour, bold=False) -> None:
        x, y, width = column
        string = self._elide(painter, string, width)
        if string:
            painter.text(x, y, width, height, align, string, colour, bold)
        self.drawn[key] = ((x, y, width, height), string)

    @staticmethod
    def _elide(painter, string: str, width: float) -> str:
        if not string or painter.text_width(string) <= width:
            return string
        while string and painter.text_width(string + "…") > width:
            string = string[:-1]
        return string + "…"

    @staticmethod
    def _wrap(painter, string: str, width: float) -> list[str]:
        """*string* broken after its commas into rows no wider than *width*."""
        rows: list[str] = []
        for part in [p.strip() for p in string.split(",") if p.strip()]:
            if rows and painter.text_width(rows[-1] + ", " + part + ",") <= width:
                rows[-1] = rows[-1] + ", " + part
            else:
                if rows:
                    rows[-1] += ","
                rows.append(part)
        return rows


class SplashRun:
    """The steps of :func:`run_with_splash`, driven by the splash's frames (testable without a window).

    Parameters
    ----------
    state : SplashState
    make_app : callable
        ``make_app(splash=state) -> shell``; the shell's session reports its stages to *state*.
    open_main : callable
        ``open_main(shell) -> host``: open the main window on the shell.
    close_splash : callable
        Close the splash window.
    later : callable
        ``later(callback)``: run *callback* after the current frame (the loop's ``call_soon``):
        nothing is built or opened inside a frame.
    """

    def __init__(
        self,
        state: SplashState,
        make_app: Callable[..., Any],
        open_main: Callable[[Any], Any],
        close_splash: Callable[[], None],
        later: Callable[[Callable[[], None]], None],
    ) -> None:
        self.state = state
        self.make_app = make_app
        self.open_main = open_main
        self.close_splash = close_splash
        self.later = later
        self.shell: Any = None
        self.main: Any = None
        #: ``show`` → ``building`` → ``starting`` → ``opening`` → ``opened`` → ``done``.
        self.step = "show"
        self.error: BaseException | None = None

    def frame(self) -> None:
        """After each splash frame: take the next step once its condition holds."""
        if self.step == "show":
            self.step = "building"
            self.later(self._build)
        elif self.step == "starting" and self.shell.data.session_settled:
            self.step = "opening"
            self.later(self._open)
        elif self.step == "opened" and getattr(self.shell, "frames_drawn", 0) > 0:
            self.step = "done"
            self.later(self._close)

    def _build(self) -> None:
        try:
            self.shell = self.make_app(splash=self.state)
        except BaseException as error:  # the splash must not stay up over a failed start
            self.error = error
            self.step = "done"
            _log.exception("building the ChiSurf window failed")
            self._close()
            return
        self.step = "starting"
        self.state.wake()

    def _open(self) -> None:
        try:
            self.main = self.open_main(self.shell)
        except (
            BaseException
        ) as error:  # a main window that cannot open must not leave the splash up
            self.error = error
            self.step = "done"
            _log.exception("opening the ChiSurf window failed")
            self._close()
            return
        self.step = "opened"
        self.state.wake()

    def _close(self) -> None:
        self.state.finish()
        self.close_splash()


def run_with_splash(
    make_app: Callable[..., Any], title: str = "ChiSurf", size: tuple[int, int] | None = None
) -> int:
    """Show the splash window, build the shell behind it, open the main window when ready.

    Returns when the main window closes.
    """
    from emtk.app import ControlSurface
    from emtk.gpu_atlas import ImageAtlas
    from emtk.native import NativeHost

    state = SplashState()
    app = SplashApp(state)
    surface = ControlSurface(app, background=(0, 0, 0, 0), images=ImageAtlas(2048, 2048))
    splash = NativeHost(
        surface,
        size=ART_SIZE,
        title=title,
        decorated=False,
        floating=True,
        transparent=True,
        centred=True,
    )
    state._wake = app.request_frame
    state.start()
    loop = splash._loop

    run = SplashRun(
        state,
        make_app,
        open_main=lambda shell: NativeHost(shell, size=size, title=title),
        close_splash=splash.close,
        later=loop.call_soon,
    )
    app.on_frame = run.frame
    splash.run()
    if run.main is not None:
        run.main.close()
    elif run.error is not None:
        raise run.error
    return 0


__all__ = [
    "ART",
    "ART_SIZE",
    "CONTRIBUTORS",
    "SplashApp",
    "SplashRun",
    "SplashState",
    "run_with_splash",
]
