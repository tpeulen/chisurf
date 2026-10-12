"""The emtk shell's boot splash (:mod:`chisurf.emtk.splash`): its own frameless window, drawn first,
following the declared startup stages, gone once the main window has drawn.

The sequence is checked with stand-ins for the windows (:class:`SplashRun`); what the splash draws
on a real GPU surface (transparent around the art, the art itself, the stage text) on the offscreen
canvas; the stages against a real session start.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from chisurf.emtk import splash as splash_mod
from chisurf.emtk.splash import ART, ART_SIZE, SplashApp, SplashRun, SplashState

REPO = Path(__file__).resolve().parents[2]
STAGES = REPO / "chisurf" / "startup" / "services.d" / "25_emtk_splash.json"


class _Data:
    def __init__(self):
        self.session_settled = False
        self.starting = True


class _Shell:
    def __init__(self, splash):
        self.splash = splash
        self.data = _Data()
        self.frames_drawn = 0


def _run(make_app=None):
    state = SplashState()
    events: list[str] = []
    queued: list = []
    shells: list = []

    def make(splash):
        events.append("build")
        shell = _Shell(splash)
        shells.append(shell)
        return shell

    run = SplashRun(
        state,
        make_app or make,
        open_main=lambda shell: events.append("open") or "main-host",
        close_splash=lambda: events.append("close"),
        later=queued.append,
    )

    def settle():
        while queued:
            queued.pop(0)()

    return run, state, events, settle, shells


def test_the_splash_is_drawn_before_anything_of_the_shell_is_built():
    run, _state, events, settle, _shells = _run()
    assert events == []  # the splash window exists; nothing else yet
    run.frame()  # the splash's first frame
    assert events == []  # the shell is built after that frame, never inside it
    settle()
    assert events == ["build"]


def test_the_main_window_opens_only_once_the_session_has_settled():
    run, _state, events, settle, shells = _run()
    run.frame()
    settle()
    for _ in range(3):
        run.frame()
        settle()
    assert events == ["build"], "the main window must wait for the session"
    shells[0].data.session_settled = True
    run.frame()
    settle()
    assert events == ["build", "open"]
    assert run.main == "main-host"


def test_the_splash_closes_after_the_main_window_has_drawn_not_before():
    run, state, events, settle, shells = _run()
    state.start()
    run.frame()
    settle()
    shells[0].data.session_settled = True
    run.frame()
    settle()
    run.frame()
    settle()
    assert events == ["build", "open"], "no frame of the main window yet: the splash stays"
    assert state.active
    shells[0].frames_drawn = 1
    run.frame()
    settle()
    assert events == ["build", "open", "close"]
    assert not state.active and run.step == "done"


def test_a_failed_build_closes_the_splash_and_keeps_the_error():
    def broken(splash):
        raise RuntimeError("no shell")

    run, state, events, settle, _shells = _run(make_app=broken)
    state.start()
    run.frame()
    settle()
    assert events == ["close"] and isinstance(run.error, RuntimeError)
    assert not state.active


def test_a_main_window_that_cannot_open_closes_the_splash_and_keeps_the_error():
    """A failure opening the main window is kept for the caller, not lost in the loop with the splash up."""
    state = SplashState()
    events: list[str] = []
    queued: list = []
    shells: list = []

    def make(splash):
        shells.append(_Shell(splash))
        return shells[-1]

    def cannot_open(shell):
        raise RuntimeError("no window")

    run = SplashRun(
        state,
        make,
        open_main=cannot_open,
        close_splash=lambda: events.append("close"),
        later=queued.append,
    )
    state.start()
    run.frame()
    while queued:
        queued.pop(0)()
    shells[0].data.session_settled = True
    run.frame()
    while queued:
        queued.pop(0)()
    assert events == ["close"] and isinstance(run.error, RuntimeError)
    assert run.main is None and run.step == "done" and not state.active


def test_the_state_follows_stages_and_keeps_the_last_log_line():
    import logging

    state = SplashState()
    state.start()
    try:
        state.stage_started({"id": "emtk_imports", "label": "Loading modules", "progress": 10})
        state.stage_started(
            {"id": "emtk_server", "label": "Starting the server and its plugins", "progress": 45}
        )
        logging.getLogger("chisurf.emtk.session").info("session server on 127.0.0.1:1")
        assert state.stages == ["emtk_imports", "emtk_server"]
        assert state.stage == "Starting the server and its plugins" and state.progress == 45
        assert state.log_line == "session server on 127.0.0.1:1"
    finally:
        state.finish()
    level = logging.getLogger("chisurf").getEffectiveLevel()
    logging.getLogger("chisurf.emtk.session").info("after the splash")
    assert state.log_line == "session server on 127.0.0.1:1", "the handler leaves with the splash"
    assert level == logging.getLogger("chisurf").getEffectiveLevel()


def test_the_stage_labels_are_translated(monkeypatch):
    from chisurf.emtk.i18n import install, set_locale

    install(None)
    state = SplashState()
    try:
        set_locale("de")
        state.stage_started({"id": "emtk_imports", "label": "Loading modules", "progress": 10})
        lines = state.lines()
        assert lines["stage"] == "Module werden geladen"
        assert lines["contributors_title"] == "Entwickler & Mitwirkende:"
        state.stage = splash_mod.STARTING
        assert state.lines()["stage"] == "Wird gestartet…"
        set_locale("fr")
        assert state.lines()["stage"] == "Démarrage…"
    finally:
        set_locale("en")


def test_the_art_is_the_svg_at_twice_its_size():
    from PIL import Image

    with Image.open(ART) as image:
        width, height = image.size
        assert image.mode == "RGBA", "the art's shape needs its alpha"
    assert (width, height) == (2 * ART_SIZE[0] + 1, 2 * ART_SIZE[1]), (
        "regenerate: rsvg-convert -z 2 chisurf/gui/resources/icons/splashscreen.svg "
        "-o chisurf/emtk/splash.png"
    )


@pytest.fixture(scope="module")
def device():
    pytest.importorskip("rendercanvas")
    pytest.importorskip("wgpu")
    from emtk.wgpu_host import default_device

    try:
        return default_device()
    except Exception as exc:  # noqa: BLE001 - no adapter here
        pytest.skip(f"no wgpu adapter: {exc}")


@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_the_splash_draws_the_art_transparent_around_it_with_the_stage(device, scale):
    import numpy as np
    from emtk.app import ControlSurface
    from emtk.gpu_atlas import ImageAtlas
    from emtk.native import NativeHost
    from rendercanvas.offscreen import RenderCanvas

    state = SplashState()
    app = SplashApp(state)
    state.stage_started(
        {"id": "emtk_server", "label": "Starting the server and its plugins", "progress": 45}
    )
    surface = ControlSurface(app, background=(0, 0, 0, 0), images=ImageAtlas(2048, 2048))
    canvas = RenderCanvas(size=ART_SIZE, pixel_ratio=scale)
    host = NativeHost(surface, canvas=canvas, device=device)
    image = np.asarray(host.draw_frame())
    assert image.shape[:2] == (int(ART_SIZE[1] * scale), int(ART_SIZE[0] * scale))
    assert image[1, 1, 3] == 0, "the art's transparent corner shows the desktop"
    # The left panel of the art (grey) is drawn, not a blank rectangle the atlas declined.
    panel = image[int(140 * scale), int(60 * scale)]
    assert panel[3] == 255 and 60 < int(panel[0]) < 140 and abs(int(panel[0]) - int(panel[2])) < 8
    # The bar is filled to the stage's progress: green inside, the track after it.
    bar_y = int((211 + 2) * scale)
    assert image[bar_y, int(140 * scale), 1] > 200 and image[bar_y, int(140 * scale), 0] < 60
    assert image[bar_y, int(390 * scale), 1] < 200
    assert app.drawn["stage"][1] == "Starting the server and its plugins"
    assert app.frames == 1


def test_the_session_reports_the_declared_stages_in_order():
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState
    from chisurf.startup.services import AppStartupServiceManager

    declared = [
        s.id for s in AppStartupServiceManager().ordered_specs(surface="emtk", phase="splash")
    ]
    assert declared == [s["id"] for s in json.loads(STAGES.read_text())["services"]]
    state = SplashState()
    session = start_session(state=SessionState(), on_stage=state.stage_started)
    try:
        assert state.stages == declared
        assert state.progress == max(
            s["progress"] for s in json.loads(STAGES.read_text())["services"]
        )
        datasets = session.api.list_datasets() or []
        assert [d["name"] for d in datasets] == ["Global Dataset"], "the last stage adds it, once"
        assert session.ensure_global_dataset() is False, (
            "a second call (the shell's adopt) adds none"
        )
        assert len(session.api.list_datasets()) == 1
    finally:
        session.close()


def test_the_shell_reports_its_session_stages_to_the_splash_and_settles():
    from emtk.testing import Driver

    from chisurf.emtk.main_app import make_app

    state = SplashState()
    shell = make_app(persist=False, splash=state)
    try:
        assert shell.data.starting and not shell.data.session_settled
        end = time.monotonic() + 120
        while not shell.data.session_settled and time.monotonic() < end:
            time.sleep(0.05)
        assert shell.data.session_settled, "the splash opens the main window on this"
        assert state.stages and state.stages[-1] == "emtk_session"
        driver = Driver(shell, (1200, 800))
        driver.frame(1)
        assert not shell.data.starting and shell.data.session is not None
        assert shell.frames_drawn == 1, "the splash closes on the main window's first frame"
    finally:
        shell.close()


class _Classic:
    """A tool written to the classic control contract (press / drag / hover / release / scroll)."""

    def __init__(self):
        self.calls = []

    def draw(self, painter, x, y, w, h):
        self.calls.append(("draw", w, h))

    def press(self, x, y, *box_and_more):
        self.calls.append(("press", x, y, box_and_more))

    def hover(self, x, y, *box):
        self.calls.append(("hover", x, y))

    def drag(self, x, y, *box):
        self.calls.append(("drag", x, y))

    def release(self, *_):
        self.calls.append(("release",))

    def scroll(self, rows):
        self.calls.append(("scroll", rows))


def test_a_classic_contract_tool_works_inside_the_shell():
    """ebFRET's app speaks the classic contract; hosted in the shell it raised on every frame."""
    from chisurf.emtk.child_contract import ClassicChild, as_child

    tool = _Classic()
    child = as_child(tool)
    assert isinstance(child, ClassicChild) and as_child(child) is child
    child.draw(None, 0, 0, 300, 200)
    assert child.animating() is False and child.next_frame_in() is None
    child.pointer_move(5, 6, 0, 0)
    child.pointer_press(10, 20, 1, 0, 1)
    child.pointer_move(11, 21, 1, 0)
    child.pointer_release(11, 21, 1, 0)
    child.wheel(0, 0, -2, 0)
    assert tool.calls[1:] == [
        ("hover", 5.0, 6.0),
        ("press", 10.0, 20.0, (0.0, 0.0, 300.0, 200.0, 0, 1)),
        ("drag", 11.0, 21.0),
        ("release",),
        ("scroll", -2),
    ]


def test_ebfret_opens_in_the_shell_without_errors():
    from emtk.testing import Driver

    from chisurf.emtk.background_build import join_all
    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.plugins import manifests

    catalog = {k: v for k, v in manifests().items() if k == "burst_ebfret"}
    shell = EmtkShellApp(catalog)
    try:
        driver = Driver(shell, (1200, 800))
        shell.open_plugin("burst_ebfret")
        join_all()
        driver.frame(3)
        hosted = shell.hosted["burst_ebfret"]
        assert hosted.app is not None and not hosted.error
        assert shell.animating() in (True, False)
        x, y, w, h = hosted.box
        shell.pointer_move(x + w / 2, y + h / 2, 0, 0)
        shell.pointer_press(x + w / 2, y + h / 2, 1, 0, 1)
        shell.pointer_release(x + w / 2, y + h / 2, 1, 0)
        driver.frame(2)
    finally:
        shell.close()
