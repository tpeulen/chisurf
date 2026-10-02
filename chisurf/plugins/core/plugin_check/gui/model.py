"""Native startup sweep with subprocess isolation, cancellation and progress."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from chisurf.emtk.plugins import manifests


class PluginCheckModel:
    def __init__(self, catalog=None):
        self.catalog = catalog if catalog is not None else manifests()
        self.results = {}
        self.blacklisted = set()
        self.failures = {}
        self.skip_blacklisted = True
        self.delay = 0.5
        self.timeout = 30.0
        self.current = 0
        self.total = 0
        self.running = False
        self.message = "Ready"
        self._events = queue.Queue()
        self._stop = threading.Event()
        self._process = None
        self._thread = None

    def refresh(self):
        if self.running:
            return
        self.catalog = manifests()
        self.results.clear()

    def start(self, safe=False):
        if self.running:
            return False
        self.running = True
        self._stop.clear()
        ids = sorted(self.catalog)
        if safe:
            ids = ids[:10]
        self.current, self.total = 0, len(ids)
        snapshot = [(key, dict(self.catalog[key])) for key in ids]
        self._thread = threading.Thread(target=self._run, args=(snapshot, safe), daemon=True)
        self._thread.start()
        return True

    def _run(self, rows, safe):
        try:
            for key, manifest in rows:
                if self._stop.is_set():
                    break
                if self.skip_blacklisted and key in self.blacklisted:
                    result = {"status": "skipped", "error": "Blacklisted after repeated failures"}
                else:
                    factory = manifest.get("entrypoints", {}).get("emtk")
                    if not factory:
                        result = {"status": "pending" if manifest.get("entrypoints", {}).get("gui") or
                                  manifest.get("entrypoints", {}).get("script") else "non_gui",
                                  "error": "No native factory declared"}
                    else:
                        result = self._check(factory, min(self.timeout, 5) if safe else self.timeout)
                self._events.put((key, result))
                if self._stop.wait(max(0.0, self.delay)):
                    break
        finally:
            self._events.put((None, {"status": "cancelled" if self._stop.is_set() else "complete"}))

    def _check(self, factory, timeout):
        with tempfile.TemporaryDirectory(prefix="chisurf-plugin-check-") as directory:
            env = dict(os.environ, CHISURF_SETTINGS_DIR=directory, MMFDB_SETTINGS_DIR=directory,
                       MMFDB_OBJECT_STORE_ROOT=str(Path(directory) / "objects"),
                       NDXPLORER_SETTINGS_DIR=str(Path(directory) / "ndxplorer"))
            process = subprocess.Popen([sys.executable, "-m", "chisurf.emtk.validation", "--factory", factory],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            self._process = process
            started = time.monotonic()
            try:
                while True:
                    if self._stop.is_set():
                        return {"status": "cancelled"}
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        return {"status": "fail", "error": f"Startup timed out after {timeout:g}s"}
                    try:
                        stdout, stderr = process.communicate(timeout=min(0.1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                try:
                    result = json.loads(stdout.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    result = {"status": "fail", "error": stderr or f"Child exited {process.returncode}"}
                return result
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()
                self._process = None

    def poll(self):
        while True:
            try:
                key, result = self._events.get_nowait()
            except queue.Empty:
                break
            if key is None:
                self.running = False
                self.message = "Cancelled" if result["status"] == "cancelled" else "Startup checks complete"
            else:
                self.results[key] = result
                self.current += 1
                if result["status"] == "fail":
                    self.failures[key] = self.failures.get(key, 0) + 1
                    if self.failures[key] >= 5:
                        self.blacklisted.add(key)
                elif result["status"] == "pass":
                    self.failures.pop(key, None)
                    self.blacklisted.discard(key)
                self.message = f"Checked {self.current}/{self.total}: {key}"

    def stop(self):
        self._stop.set()

    def close(self):
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout=3)
