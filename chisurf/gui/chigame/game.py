"""The game base class, the frame loop, and the headless capture path.

A game subclasses :class:`Game` and implements ``update`` and ``draw``. The host
owns everything else: the device, the batch, the font, input and audio. The same
:class:`GameHost` drives a docked widget and a windowless capture, so a
screenshot test exercises the game's real update and draw code rather than a
stand-in.
"""

from __future__ import annotations

import time

import numpy as np
import wgpu

from .assets import AssetPack, ProceduralPack
from .audio import Audio
from .input import InputMap
from .render import Camera, SpriteBatch
from .scene import Scene
from .text import FontAtlas


def _srgb_to_linear(c: float) -> float:
    """Convert one sRGB channel to linear.

    The colour attachment is an sRGB format, so a clear colour given in sRGB
    must be linearised or the background renders too bright.

    Parameters
    ----------
    c : float
        Channel value in 0..1.

    Returns
    -------
    float
        Linear value.
    """
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


class Game:
    """Base class for anything chigame runs.

    Attributes
    ----------
    title : str
        Shown by hosts that have somewhere to show it.
    background : tuple of float
        sRGB RGBA clear colour.
    music_context : str or None
        Set by a game to drive the soundtrack; the host applies it each frame.
    """

    title: str = "chigame"
    background: tuple[float, float, float, float] = (0.06, 0.07, 0.10, 1.0)
    music_context: str | None = None

    def setup(self, host: "GameHost") -> None:
        """Called once, after the host and its resources exist.

        Parameters
        ----------
        host : GameHost
            The host running this game.
        """

    def update(self, dt: float, keys: InputMap) -> None:
        """Advance the simulation by one frame.

        Parameters
        ----------
        dt : float
            Seconds since the previous frame, clamped by the host so a stalled
            window cannot teleport everything on resume.
        keys : InputMap
            Input state for this frame.
        """
        raise NotImplementedError

    def draw(self, scene: Scene) -> None:
        """Queue this frame's drawing.

        Parameters
        ----------
        scene : Scene
            The frame under construction.
        """
        raise NotImplementedError


class GameHost:
    """Owns the GPU resources and drives a game's frames.

    Parameters
    ----------
    game : Game
        The game to run.
    context : chisurf.gui.chigame.gpu.GpuContext
        A configured canvas.
    pack : chisurf.gui.chigame.assets.AssetPack, optional
        Look and sound. Defaults to the procedural pack.
    with_text : bool, optional
        Build a font atlas. Costs one Qt rasterisation at startup.
    with_audio : bool, optional
        Enable the mixer.
    """

    #: Longest frame step handed to a game. A window that was hidden for a
    #: minute must not resume with a 60-second update.
    MAX_DT = 0.1

    def __init__(
        self,
        game: Game,
        context,
        pack: AssetPack | None = None,
        with_text: bool = True,
        with_audio: bool = True,
    ) -> None:
        self.game = game
        self.ctx = context
        self.pack = pack if pack is not None else ProceduralPack()
        self.batch = SpriteBatch(context)
        self.keys = InputMap()
        self.camera = Camera()
        self.font: FontAtlas | None = None
        if with_text:
            self.font = FontAtlas(context.device)
            self.batch.set_atlas(self.font.texture)
        # The decoder shares the renderer's device rather than asking the
        # driver for a second one purely to decompress audio.
        try:
            from .adpcm import use_device

            use_device(context.device)
        except Exception:
            pass
        self.audio = Audio(self.pack, enabled=with_audio)
        self.scene = Scene(self.batch, self.pack, self.camera, self.font)
        self._extra_players: list[InputMap] = []
        self._last = time.perf_counter()
        try:
            self.keys.attach(context.canvas)
        except Exception:
            # The offscreen canvas emits no key events; scripted input still works.
            pass
        self.game.setup(self)

    def add_player(self, bindings: dict) -> InputMap:
        """Create a second (or third) controller on the same canvas.

        The abstract controller describes *one* player, so local multiplayer
        needs one map per player rather than more actions. Each map is attached
        to the same canvas with its own binding table.

        Parameters
        ----------
        bindings : dict
            Key name to :class:`~chisurf.gui.chigame.input.Action`.

        Returns
        -------
        InputMap
            The new controller. The host advances it with the others.
        """
        extra = InputMap(bindings)
        try:
            extra.attach(self.ctx.canvas)
        except Exception:
            pass
        self._extra_players.append(extra)
        return extra

    def frame(self, dt: float | None = None) -> int:
        """Advance and render exactly one frame.

        Parameters
        ----------
        dt : float, optional
            Step to use. Omitted measures wall-clock time since the last frame,
            which is what an interactive host wants; a test passes a fixed step
            so its output is deterministic.

        Returns
        -------
        int
            Number of instances drawn.
        """
        if dt is None:
            now = time.perf_counter()
            dt = min(now - self._last, self.MAX_DT)
            self._last = now

        self.game.update(dt, self.keys)
        self.keys.end_frame()
        for player in self._extra_players:
            player.end_frame()
        self.sync_audio()
        if self.game.music_context is not None:
            self.audio.set_context(self.game.music_context)

        self.batch.clear()
        self.game.draw(self.scene)

        r, g, b, a = self.game.background
        target = self.ctx.context.get_current_texture().create_view()
        encoder = self.ctx.device.create_command_encoder()
        render_pass = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": target,
                    "resolve_target": None,
                    "clear_value": (
                        _srgb_to_linear(r),
                        _srgb_to_linear(g),
                        _srgb_to_linear(b),
                        a,
                    ),
                    "load_op": wgpu.LoadOp.clear,
                    "store_op": wgpu.StoreOp.store,
                }
            ]
        )
        drawn = self.batch.flush(render_pass, self.scene.camera)
        render_pass.end()
        self.ctx.device.queue.submit([encoder.finish()])
        return drawn

    def attend(self) -> bool:
        """Whether this game's window is the one the user is actually looking at.

        Returns
        -------
        bool
            False when the widget is hidden, or its window is not the active
            one. An offscreen canvas has no widget at all and counts as
            attended, because a headless capture is nobody's foreground.
        """
        canvas = getattr(self.ctx, "canvas", None)
        if canvas is None or not hasattr(canvas, "isVisible"):
            return True
        try:
            if not canvas.isVisible():
                return False
            window = canvas.window()
            return bool(window is None or window.isActiveWindow())
        except Exception:
            # A widget being torn down answers nothing useful; silence is the
            # safe reading of that.
            return False

    def sync_audio(self) -> None:
        """Suspend or resume the mixer to match the window.

        A game in a window nobody is looking at must not still be audible.
        Frames may stop entirely when a widget is hidden, so this is called
        both per frame *and* from the event filter installed by
        :func:`create_widget`.
        """
        if not self.audio.enabled:
            return
        if self.attend():
            self.audio.resume()
        else:
            self.audio.suspend()

    def close(self) -> None:
        """Stop the game's audio for good."""
        self.audio.stop()

    def start(self) -> None:
        """Drive frames continuously from the canvas' own draw scheduling."""
        self.ctx.canvas.request_draw(self._on_draw)

    def _on_draw(self) -> None:
        """Render one frame and ask for the next."""
        self.frame()
        self.ctx.canvas.request_draw(self._on_draw)


def create_widget(game: Game, parent=None, pack: AssetPack | None = None, **kwargs):
    """Run a game inside a Qt widget suitable for a ChiSurf dock.

    Parameters
    ----------
    game : Game
        The game to run.
    parent : QWidget, optional
        Parent widget.
    pack : chisurf.gui.chigame.assets.AssetPack, optional
        Look and sound.
    **kwargs
        Forwarded to :class:`GameHost`.

    Returns
    -------
    tuple
        ``(widget, host)``. The widget is a real ``QWidget``; keep a reference
        to the host or the game stops when it is collected.
    """
    from .gpu import create_widget as create_gpu_widget

    context = create_gpu_widget(parent=parent)
    host = GameHost(game, context, pack=pack, **kwargs)
    host.start()
    _watch_focus(host, context.canvas)
    return context.canvas, host


def _watch_focus(host: GameHost, widget) -> None:
    """Make a game go quiet the moment its window stops being the front one.

    Polling inside ``frame`` is not enough on its own: a hidden widget may stop
    being asked to draw at all, and a game whose frames have stopped with its
    music still playing is the worst version of this bug. So the window's own
    show/hide/activate events are watched too, and both routes call the same
    :meth:`GameHost.sync_audio`.

    Parameters
    ----------
    host : GameHost
        The running game.
    widget : QWidget
        The canvas.
    """
    try:
        from qtpy.QtCore import QEvent, QObject
    except Exception:  # pragma: no cover - no Qt in this build
        return

    watched = frozenset({
        QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.Close,
        QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate,
        QEvent.Type.WindowStateChange, QEvent.Type.ApplicationStateChange,
    })

    class _Watcher(QObject):
        """Keeps the mixer in step with the window."""

        def eventFilter(self, obj, event):  # noqa: N802 - Qt's spelling
            """Sync audio on anything that changes whether we are in front.

            Parameters
            ----------
            obj : QObject
                The watched object.
            event : QEvent
                What happened.

            Returns
            -------
            bool
                Always False: this observes, it never consumes.
            """
            if event.type() in watched:
                try:
                    host.sync_audio()
                except Exception:
                    pass
            return False

    watcher = _Watcher(widget)
    widget.installEventFilter(watcher)
    window = widget.window()
    if window is not None and window is not widget:
        window.installEventFilter(watcher)
    try:
        from qtpy.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(watcher)
    except Exception:
        pass
    # Keep it alive for as long as the host does; a filter that is collected
    # stops filtering and the bug comes back silently.
    host._focus_watcher = watcher


def capture(
    game: Game,
    size: tuple[int, int] = (960, 540),
    frames: int = 1,
    dt: float = 1.0 / 60.0,
    script=None,
    pack: AssetPack | None = None,
    **kwargs,
) -> np.ndarray:
    """Render a game headlessly and return the final frame.

    This is the path the project's rule about never implementing a GUI blind
    depends on. It runs the game's real ``update`` and ``draw``.

    Parameters
    ----------
    game : Game
        The game to run.
    size : tuple of int, optional
        Pixel size.
    frames : int, optional
        Frames to advance before capturing. More than one lets a game settle,
        or lets a script play out.
    dt : float, optional
        Fixed step per frame, so output does not depend on machine speed.
    script : callable, optional
        Called as ``script(frame_index, host)`` before each frame — the hook for
        pushing actions into :class:`~chisurf.gui.chigame.input.InputMap`.
    pack : chisurf.gui.chigame.assets.AssetPack, optional
        Look and sound.
    **kwargs
        Forwarded to :class:`GameHost`. Audio defaults off here.

    Returns
    -------
    numpy.ndarray
        The frame as ``(height, width, 4)`` uint8 RGBA.
    """
    from .gpu import create_offscreen

    kwargs.setdefault("with_audio", False)
    context = create_offscreen(size=size)
    host = GameHost(game, context, pack=pack, **kwargs)

    # The offscreen canvas composes the frame during its own draw call, so the
    # host's frame() has to be registered as that callback rather than invoked
    # beside it — calling draw() with the function is a TypeError.
    context.canvas.request_draw(lambda: host.frame(dt))

    errors: list[BaseException] = []
    original_frame = host.frame

    def _frame_recording_errors(step: float) -> int:
        """Run one frame, keeping any exception for the caller.

        The canvas catches whatever its draw callback raises and merely logs it,
        then hands back an empty frame. That turns a plain error in a game's
        ``draw`` into a confusing failure much later, somewhere else -- so the
        exception is captured here and re-raised below.

        Parameters
        ----------
        step : float
            Seconds to advance.

        Returns
        -------
        int
            Instances drawn, or ``0`` when the frame raised.
        """
        try:
            return original_frame(step)
        except BaseException as error:  # noqa: BLE001 - re-raised below
            errors.append(error)
            return 0

    context.canvas.request_draw(lambda: _frame_recording_errors(dt))

    result = None
    for index in range(max(frames, 1)):
        if script is not None:
            script(index, host)
        result = context.canvas.draw()
        if errors:
            raise errors[0]

    frame = np.asarray(result)
    if frame.ndim != 3:
        raise RuntimeError(
            "the canvas returned no frame; the game's draw callback probably "
            f"failed silently (got an array of shape {frame.shape})"
        )
    return frame


def save_png(image: np.ndarray, path) -> None:
    """Write a captured frame to a PNG.

    Parameters
    ----------
    image : numpy.ndarray
        ``(height, width, 4)`` uint8 RGBA.
    path : str or pathlib.Path
        Destination.
    """
    from qtpy import QtGui

    array = np.ascontiguousarray(image[..., :4].astype(np.uint8))
    height, width = array.shape[:2]
    qimage = QtGui.QImage(array.data, width, height, width * 4, QtGui.QImage.Format_RGBA8888)
    if not qimage.copy().save(str(path)):
        raise OSError(f"could not write {path}")
