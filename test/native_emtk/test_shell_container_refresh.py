"""A container written on a worker thread refreshes the Datasets dock in the window's next frame.

The listener used to rebuild the dock on the writer's thread -- under a frame that was drawing it,
and without asking for one: flicker, and new runs that only appeared once the mouse moved.
"""

from __future__ import annotations

import threading

from chisurf.emtk.main_app import _refresh_stale_datasets, _watch_containers


class _Docks:
    def __init__(self):
        self.refreshed_on: list[int] = []

    def refresh(self):
        self.refreshed_on.append(threading.get_ident())


class _App:
    def __init__(self):
        self.frames = 0

    def request_frame(self):
        self.frames += 1


def test_a_worker_write_marks_the_list_and_wakes_the_window(monkeypatch):
    from chisurf.core.project import analysis

    monkeypatch.setattr(analysis, "_LISTENERS", list(getattr(analysis, "_LISTENERS", [])))
    monkeypatch.setattr(analysis, "sync_runs", lambda: [])
    docks, app = _Docks(), _App()
    _watch_containers(docks, app)
    writer = threading.Thread(target=analysis.container_changed, args=("m.pto",))
    writer.start()
    writer.join()
    assert docks.refreshed_on == [] and app.frames == 1  # nothing rebuilt on the writer's thread
    _refresh_stale_datasets(docks)  # the window's next frame
    assert docks.refreshed_on == [threading.get_ident()]
    _refresh_stale_datasets(docks)
    assert len(docks.refreshed_on) == 1  # once per write
