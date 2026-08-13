"""How fast the canvas draws, and how it behaves when nothing asks it to.

Two mechanisms live here, both about *cadence* rather than what gets drawn:

``CanvasRenderer.set_max_fps`` re-throttles an already-open window's
frame-rate ceiling by calling straight into ``rendercanvas``'s own
``set_update_mode`` -- the real live-reconfigure API the library exposes for
exactly this, found by reading ``rendercanvas/base.py`` rather than assumed.
Nothing here opens a real GPU window: the renderer's ``_surface()`` is the
seam (it answers ``self`` for a host that *is* a canvas and the held canvas
for one that merely owns one), so a fake surface is enough to prove the right
call happens with the right arguments.

The idle-settle timer is the fix for a distinct, previously-unnoticed bug: an
"ondemand" canvas (both hosts use that update mode) draws nothing once nobody
is interacting, so the fps readout -- computed only from inside a real draw --
freezes at its last value forever rather than reporting the still viewport
honestly. ``_arm_idle_settle`` schedules one follow-up draw past the idle gap
using the codebase's existing host-independent timer
(:class:`chimol.host.widget.Timer`, the same clock movie playback and the
cartoon settle-then-bake pass already use), and ``_note_frame_drawn`` makes
sure that one follow-up draw does not rearm itself and free-run forever.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chisurf.plugins.chimol.chimol.renderer.canvas_base import CanvasRenderer, _IDLE_GAP


# --------------------------------------------------------------------------- #
# set_max_fps
# --------------------------------------------------------------------------- #
class _FakeSurface:
    """Stands in for the ``rendercanvas`` object `_surface()` would return."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def set_update_mode(self, update_mode, *, min_fps=None, max_fps=None):
        self.calls.append((update_mode, min_fps, max_fps))


class _FakeHost:
    """The minimum `set_max_fps` needs from `self`: a `_surface()`."""

    def __init__(self, surface) -> None:
        self._surface_obj = surface

    def _surface(self):
        return self._surface_obj


def test_set_max_fps_calls_rendercanvas_set_update_mode():
    """The real live-reconfigure API, not a home-grown throttle beside it."""
    surface = _FakeSurface()
    host = _FakeHost(surface)

    CanvasRenderer.set_max_fps(host, 30)

    assert surface.calls == [("ondemand", None, 30.0)]


def test_set_max_fps_leaves_the_update_mode_alone():
    """Only the ceiling changes; the mode stays the "ondemand" the window was
    built with, so this cannot turn a viewport into `continuous`."""
    surface = _FakeSurface()
    host = _FakeHost(surface)

    CanvasRenderer.set_max_fps(host, 144)

    mode, min_fps, _max_fps = surface.calls[0]
    assert mode == "ondemand"
    assert min_fps is None


def test_set_max_fps_clamps_below_one():
    """``rendercanvas`` raises for anything under 1; a bad value must not
    crash a draw."""
    surface = _FakeSurface()
    host = _FakeHost(surface)

    CanvasRenderer.set_max_fps(host, 0)

    assert surface.calls == [("ondemand", None, 1.0)]


def test_set_max_fps_does_nothing_without_a_settable_surface():
    """A surface with no `set_update_mode` (or none at all) must not raise."""
    host = _FakeHost(object())
    CanvasRenderer.set_max_fps(host, 30)  # no exception


def test_set_max_fps_swallows_a_surface_that_raises():
    class _Angry:
        def set_update_mode(self, *a, **k):
            raise RuntimeError("no scheduler")

    CanvasRenderer.set_max_fps(_FakeHost(_Angry()), 30)  # no exception


# --------------------------------------------------------------------------- #
# The idle-settle timer
# --------------------------------------------------------------------------- #
class _FakeTimer:
    """Stands in for `chimol.host.widget.Timer`, recording what was asked."""

    def __init__(self) -> None:
        self.single_shot = None
        self.started_ms = None
        self._callback = None
        self.timeout = SimpleNamespace(connect=self._connect)

    def _connect(self, fn) -> None:
        self._callback = fn

    def setSingleShot(self, value) -> None:  # noqa: N802 - mirrors Qt naming
        self.single_shot = value

    def start(self, msec) -> None:
        self.started_ms = msec

    def fire(self) -> None:
        """Simulate the timer elapsing."""
        self._callback()


def _fake_host(*, nerd: bool = False, debug: bool = False) -> SimpleNamespace:
    """A double carrying real bound versions of the methods
    `_arm_idle_settle` itself calls: `timeout.connect` needs a callable, and
    `update` is what the settle draw asks for.

    ``nerd``/``debug`` set what :meth:`CanvasRenderer._readout_is_live` reads,
    which is what decides the timer's cadence.
    """
    gui = SimpleNamespace(nerd=nerd, debug_overlays=debug)
    host = SimpleNamespace(
        _idle_settle_timer=None, _idle_settling=False, updated=0, _internal_gui=gui,
    )
    host.update = lambda: setattr(host, "updated", host.updated + 1)
    host._on_idle_settle_timeout = lambda: CanvasRenderer._on_idle_settle_timeout(host)
    host._readout_is_live = lambda: CanvasRenderer._readout_is_live(host)
    return host


def test_arm_idle_settle_starts_a_singleshot_timer_past_the_idle_gap(monkeypatch):
    """With no readout on screen the timer is the one-shot settle."""
    monkeypatch.setattr(
        "chisurf.plugins.chimol.chimol.host.widget.Timer", _FakeTimer, raising=True
    )
    host = _fake_host()

    CanvasRenderer._arm_idle_settle(host)

    timer = host._idle_settle_timer
    assert isinstance(timer, _FakeTimer)
    assert timer.single_shot is True
    assert timer.started_ms >= int(_IDLE_GAP * 1000)


def test_a_live_readout_ticks_at_the_idle_tick_interval(monkeypatch):
    """The counter has to *run*, so it redraws on its own cadence.

    Past the idle gap it would only ever redraw after the rate had already
    been cleared to zero, which is a settle, not a counter.
    """
    monkeypatch.setattr(
        "chisurf.plugins.chimol.chimol.host.widget.Timer", _FakeTimer, raising=True
    )
    from chisurf.plugins.chimol.chimol.renderer.frame_stats import (
        nerd_idle_tick_interval,
    )

    host = _fake_host(nerd=True)
    CanvasRenderer._arm_idle_settle(host)

    assert host._idle_settle_timer.started_ms == max(
        int(nerd_idle_tick_interval() * 1000), 16
    )


def test_the_idle_tick_is_slower_than_the_publish_tick():
    """It costs a whole frame, not a re-read, so it must not run at the
    publish rate -- an instrument that redraws the scene to report the rate
    is an instrument that changes the rate."""
    from chisurf.plugins.chimol.chimol.renderer.frame_stats import (
        nerd_idle_tick_interval,
        nerd_report_interval,
    )

    assert nerd_idle_tick_interval() > nerd_report_interval()


def test_the_idle_tick_can_be_switched_off_entirely(monkeypatch):
    """0 is a real value: no redraws at all, the rate settles to zero and
    stays there. That is the setting to use while measuring."""
    monkeypatch.setattr(
        "chisurf.plugins.chimol.chimol.host.widget.Timer", _FakeTimer, raising=True
    )
    monkeypatch.setattr(
        "chisurf.plugins.chimol.chimol.renderer.frame_stats.nerd_idle_tick_interval",
        lambda: 0.0,
        raising=True,
    )
    host = _fake_host(nerd=True)

    CanvasRenderer._arm_idle_settle(host)

    assert host._idle_settle_timer is None, "a disabled tick must arm nothing"


def test_the_settle_timer_asks_for_another_draw(monkeypatch):
    monkeypatch.setattr(
        "chisurf.plugins.chimol.chimol.host.widget.Timer", _FakeTimer, raising=True
    )
    host = _fake_host()

    CanvasRenderer._arm_idle_settle(host)
    host._idle_settle_timer.fire()

    assert host._idle_settling is True
    assert host.updated == 1


def test_a_real_draw_arms_the_idle_settle_timer():
    """Every draw that is not itself the settle draw rearms the debounce."""
    calls = []
    host = _fake_host()
    host._arm_idle_settle = lambda: calls.append(1)

    CanvasRenderer._note_frame_drawn(host)

    assert calls == [1]
    assert host._idle_settling is False


def test_the_settle_draw_does_not_rearm_when_no_readout_is_shown():
    """With nothing to keep live, the follow-up draw settles the rate to zero
    once and stops -- an idle viewport nobody is measuring goes fully quiet."""
    calls = []
    host = _fake_host()
    host._idle_settling = True
    host._arm_idle_settle = lambda: calls.append(1)

    CanvasRenderer._note_frame_drawn(host)

    assert calls == []
    assert host._idle_settling is False


def test_a_live_readout_keeps_rearming_so_the_counter_runs():
    """The reported bug: the counter only advanced when something *else*
    repainted the chrome (a hover crossing a control), because the settle draw
    deliberately did not rearm. With a readout on screen it must rearm --
    including after its own draw -- or the number freezes between hovers."""
    calls = []
    host = _fake_host(nerd=True)
    host._idle_settling = True          # this draw *is* the timer's own
    host._arm_idle_settle = lambda: calls.append(1)

    CanvasRenderer._note_frame_drawn(host)

    assert calls == [1], "a live readout must keep the timer going"
    assert host._idle_settling is False


def test_the_status_band_rate_also_counts_as_a_live_readout():
    """`debug_overlays` draws the plain rate without nerd mode's graphs; it is
    just as frozen if the tick stops."""
    host = _fake_host(debug=True)
    assert CanvasRenderer._readout_is_live(host) is True


def test_no_readout_means_no_repeating_tick():
    """Neither instrument on screen: nothing to keep live, nothing to pay."""
    host = _fake_host()
    assert CanvasRenderer._readout_is_live(host) is False
