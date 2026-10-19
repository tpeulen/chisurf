"""Snapshot workers: numerical work never mutates the displayed model."""

from __future__ import annotations

import copy
import queue
import threading

from chisurf.emtk import job_gate


class SnapshotJob:
    def __init__(self, model):
        self.model = model
        self.busy = False
        self.error = ""
        self.progress = ""
        self.messages = queue.SimpleQueue()
        self.thread = None

    def start(self, method, *args, **kwargs):
        if self.busy:
            return False
        snapshot = copy.copy(self.model)
        # File/selection/settings collections are mutable and belong to the job.
        for name in (
            "files",
            "picked",
            "detected_beads",
            "results",
            "run_rows",
            "curves",
            "selected_files",
            "_files",
        ):
            # A method of that name (the run picker's ``run_rows()``) is a source,
            # not a collection the job owns.
            if hasattr(snapshot, name) and not callable(getattr(snapshot, name)):
                setattr(
                    snapshot,
                    name,
                    [copy.copy(value) for value in getattr(snapshot, name)]
                    if name == "results"
                    else list(getattr(snapshot, name)),
                )
        for name in ("settings", "regions", "setup", "brush", "decay", "meta", "setup_settings"):
            if hasattr(snapshot, name):
                setattr(snapshot, name, copy.deepcopy(getattr(snapshot, name)))
        for name in ("clsm_images", "representations", "representation_sources", "_mosaic_cache"):
            if hasattr(snapshot, name):
                setattr(snapshot, name, dict(getattr(snapshot, name)))
        if getattr(snapshot, "selection_mask", None) is not None:
            snapshot.selection_mask = snapshot.selection_mask.copy()
        events = []

        def progress(event):
            events.append(event)
            self.messages.put(
                (
                    "progress",
                    getattr(snapshot, "status_text", getattr(snapshot, "results_text", "")),
                )
            )

        snapshot._observers = [progress]
        self.busy = True
        self.error = ""
        self.progress = method.replace("_", " ").capitalize() + "…"

        # A test that arms the gate keeps the job open (``busy``) until it releases it or
        # the snapshot's own Stop flag is set; in production this is free.
        ticket = job_gate.admit()

        def cancelled() -> bool:
            event = getattr(snapshot, "cancel_event", None)
            return bool(event is not None and event.is_set())

        def run():
            try:
                with job_gate.hold(ticket, cancelled) as go:
                    if go:
                        getattr(snapshot, method)(*args, **kwargs)
                if go:
                    self.messages.put(("done", snapshot, None, list(events)))
                else:  # stopped while held: nothing was computed, the model keeps its state
                    self.messages.put(("done", None, None, list(events)))
            except Exception as exc:
                self.messages.put(("done", None, str(exc), list(events)))

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return True

    def poll(self):
        changed = False
        while not self.messages.empty():
            item = self.messages.get()
            if item[0] == "progress":
                self.progress = str(item[1])
            else:
                _, snapshot, error, events = item
                self.busy = False
                # A model whose copy locks it against edits (``__copy__`` arms a guard) is told
                # the job ended -- done, failed, or stopped while held before it computed --
                # since only the first of those merges a snapshot that could reset the guard.
                release = getattr(self.model, "release_snapshot", None)
                if callable(release):
                    release()
                self.progress = ""
                self.error = error or ""
                if snapshot is not None:
                    for key, value in vars(snapshot).items():
                        if key != "_observers":
                            setattr(self.model, key, value)
                    for event in dict.fromkeys(events):
                        self.model.notify(event)
                    self.model.notify("updated")
                    changed = True
        return changed
