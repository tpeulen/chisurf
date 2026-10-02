"""Snapshot workers: numerical work never mutates the displayed model."""

from __future__ import annotations

import copy
import queue
import threading


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
            if hasattr(snapshot, name):
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

        def run():
            try:
                getattr(snapshot, method)(*args, **kwargs)
                self.messages.put(("done", snapshot, None, list(events)))
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
