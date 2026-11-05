"""``kill -USR1 <pid>`` dumps every thread's Python stack into the crash log, ChiSurf running on.

A hang where every thread idles (a result nobody collects) is invisible to a native sample; reading
the Python stacks from outside needs root on macOS. The signal is how a user hands them over.
"""

from __future__ import annotations

import faulthandler
import os
import signal
import threading
import time

import pytest

from chisurf.__main__ import _register_stack_dump, _unregister_stack_dump


@pytest.mark.skipif(not hasattr(signal, "SIGUSR1"), reason="no SIGUSR1 on this platform")
def test_sigusr1_writes_every_threads_stack_and_the_process_goes_on(tmp_path):
    release = threading.Event()

    def waiting_for_a_result_nobody_collects():
        release.wait()

    worker = threading.Thread(target=waiting_for_a_result_nobody_collects, daemon=True)
    worker.start()
    with (tmp_path / "crash.log").open("w+") as crash_file:
        _register_stack_dump(faulthandler, crash_file)
        try:
            os.kill(os.getpid(), signal.SIGUSR1)
            time.sleep(0.2)
        finally:
            _unregister_stack_dump(faulthandler)
        crash_file.seek(0)
        dump = crash_file.read()
    release.set()
    assert "waiting_for_a_result_nobody_collects" in dump
    assert "test_sigusr1_writes_every_threads_stack" in dump


def test_dock_side_is_a_declared_manifest_field():
    from chisurf.core.plugin.manifest import PluginManifest, validate_manifest

    data = {"id": "x", "name": "x", "version": "1.0.0", "plugin_type": "tool",
            "dock_side": "right"}
    assert not [e for e in validate_manifest(data) if "dock_side" in e]
    assert PluginManifest.from_dict(data).dock_side == "right"
    data["dock_side"] = "left"
    assert any("dock_side" in e for e in validate_manifest(data))
