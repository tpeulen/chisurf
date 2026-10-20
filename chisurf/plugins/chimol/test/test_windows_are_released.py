"""A window nobody holds is collected -- nothing process-wide keeps it.

A gate run of this suite was stopped by the resource guard with every window
it had ever built still alive (26 after ``test_lighting.py`` alone, closed or
not), each with its scene, packed GPU buffers and chrome. Three process-wide
holders did it, and each is pinned here by what it held rather than by name:

* the canvas loop's queue of pending timer ticks -- the loop cannot cancel a
  callback, and where nothing pumps it (headless, a test) it holds one forever;
* the display configuration's update-listener list, which no dropped window
  ever left;
* the compute dispatcher's status line, a module attribute closing over the
  last gui.
"""

from __future__ import annotations

import gc
import weakref

import pytest

from native_window import PDB_148L, NativeWindow


def _weak_refs(window) -> list[weakref.ref]:
    refs = [weakref.ref(window.app), weakref.ref(window.viewer), weakref.ref(window.renderer)]
    return refs


def test_a_closed_window_is_collected():
    if not PDB_148L.is_file():
        pytest.skip("missing 148l fixture")
    win = NativeWindow(size=(320, 240))
    win.load_structure_from_path(PDB_148L)
    win.pump(3)  # arms the idle-settle timer and installs the compute status line
    refs = _weak_refs(win)
    win.close()
    del win
    gc.collect()
    alive = [type(r()).__name__ for r in refs if r() is not None]
    assert not alive, f"still alive after close: {alive}"


def test_a_window_dropped_without_close_is_collected():
    win = NativeWindow(size=(320, 240))
    win.pump(3)
    refs = _weak_refs(win)
    del win
    gc.collect()
    alive = [type(r()).__name__ for r in refs if r() is not None]
    assert not alive, f"still alive with no owner: {alive}"


def test_a_queued_tick_does_not_hold_its_timer():
    from chimol.core.toolkit import _Timer

    fired: list[int] = []
    timer = _Timer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: fired.append(1))
    timer.start(10_000)  # queued on the canvas loop, which nothing here pumps
    ref = weakref.ref(timer)
    del timer
    gc.collect()
    assert ref() is None, "the canvas loop's pending tick keeps the timer alive"


def test_a_config_listener_does_not_hold_its_owner():
    from chimol.core.settings import config

    class Owner:
        calls = 0

        def changed(self):
            Owner.calls += 1

    owner = Owner()
    config.register_update_listener(owner.changed)
    config.notify_config_updated()
    assert Owner.calls == 1
    ref = weakref.ref(owner)
    del owner
    gc.collect()
    assert ref() is None, "the update-listener list keeps its owner alive"
    config.notify_config_updated()  # a dead entry is dropped, not called
    assert Owner.calls == 1
