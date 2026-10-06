"""Cancellable execution for the editor's optional Ruff subprocess."""

from __future__ import annotations

import subprocess
import threading

from chisurf.plugins.core.code_editor.ruff_runner import RuffRunner


class CancellableRuffRunner(RuffRunner):
    def __init__(self) -> None:
        super().__init__()
        self.cancelled = threading.Event()
        self.process: subprocess.Popen | None = None

    def cancel(self) -> None:
        self.cancelled.set()
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                return

            def ensure_stopped() -> None:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass

            threading.Thread(target=ensure_stopped, daemon=True).start()

    def _run(self, args, content, timeout_ms):
        if self.cancelled.is_set():
            raise RuntimeError("Ruff check cancelled")
        process = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        self.process = process
        if self.cancelled.is_set():
            self.cancel()
        try:
            stdout, stderr = process.communicate(
                content, timeout=None if timeout_ms is None else max(0.001, timeout_ms / 1000)
            )
            if self.cancelled.is_set():
                raise RuntimeError("Ruff check cancelled")
            return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
        finally:
            self.process = None
