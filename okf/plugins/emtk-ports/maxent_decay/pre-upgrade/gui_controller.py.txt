"""Cancellable isolated MEM jobs and their result/state handoff."""

from __future__ import annotations

import os
import pickle
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


class MEMJobs:
    def __init__(self, model):
        self.model = model
        self.process = None
        self.kind = ""
        self.snapshot = None
        self.progress = (0, 0)
        self.output = []
        self._queue = queue.Queue()
        self._workspace = None
        self._result_path = None
        self._reader = None

    def start(self, kind, folder=None):
        if self.process is not None:
            raise RuntimeError("A MEM job is already running.")
        if (
            kind in ("run", "lcurve")
            and self.model.settings.mode == "fret"
            and self.model.donor is None
        ):
            raise ValueError("Load a donor-only spectrum before running FRET MEM.")
        if kind == "sample" and self.model.result is None:
            raise ValueError("Run MEM before sampling.")
        self.snapshot = self.model.result_snapshot if kind == "sample" else self.model.snapshot()
        self.kind = kind
        self.progress = (0, 0)
        self.output = []
        self._queue = queue.Queue()
        self._workspace = tempfile.TemporaryDirectory(prefix="chisurf-mem-")
        request = Path(self._workspace.name) / "request.pkl"
        self._result_path = Path(self._workspace.name) / "result.pkl"
        job = {
            "kind": kind,
            "snapshot": self.snapshot,
            "folder": folder,
            "result": self.model.result if kind == "sample" else None,
        }
        if kind == "sample":
            job["snapshot"] = {**self.snapshot, "parameters": self.model.parameters()}
        with request.open("wb") as stream:
            pickle.dump(job, stream)
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "chisurf.plugins.fluorescence_decay.maxent_decay.gui.worker",
                str(request),
                str(self._result_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1", "MPLBACKEND": "Agg"},
        )
        process = self.process

        def read():
            try:
                for line in process.stdout:
                    self._queue.put(line.rstrip("\n"))
            finally:
                process.stdout.close()

        self._reader = threading.Thread(target=read, name="mem-output", daemon=True)
        self._reader.start()
        self.model.status = f"Running {kind}…"

    def poll(self):
        import json

        while not self._queue.empty():
            line = self._queue.get_nowait()
            self.output.append(line)
            try:
                item = json.loads(line)
                self.progress = (int(item["done"]), int(item["total"]))
            except (ValueError, KeyError, TypeError):
                pass
        if self.process is None or self.process.poll() is None:
            return False
        process, self.process = self.process, None
        if self._reader:
            self._reader.join(timeout=0.05)
        if process.returncode == 0 and self._result_path.is_file():
            with self._result_path.open("rb") as stream:
                result = pickle.load(stream)
            if self.kind == "run":
                self.model.result = result
                self.model.result_snapshot = self.snapshot
                self.model.samples = None
                self.model.settings.timeshift = float(result["timeshift"])
                self.model.settings.background = float(result["background"])
                self.model.settings.irf_background = float(result["irf_background"])
                if "x_donly" in result:
                    self.model.settings.x_donly = float(result["x_donly"])
            elif self.kind == "lcurve":
                self.model.lcurve = result
                corner = result["corner_index"]
                if corner is not None:
                    self.model.settings.nu = float(10.0 ** result["log10_nu"][corner])
            else:
                self.model.samples = result
            self.model.status = f"{self.kind} completed."
        else:
            while not self._queue.empty():
                self.output.append(self._queue.get_nowait())
            self.model.status = f"{self.kind} failed or was cancelled (exit {process.returncode})."
        self._workspace.cleanup()
        self._workspace = None
        return True

    def cancel(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.poll()

    def close(self):
        self.cancel()
