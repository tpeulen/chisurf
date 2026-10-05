"""Lifetime regressions for the standalone actual-Main GUI child probe."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from test.gui import scientific_document_gui_probe as probe


def test_probe_shutdown_runs_pyqtgraph_cleanup_before_python_teardown(monkeypatch):
    """Standalone GUI children must not defer pyqtgraph cleanup to pytest exit."""
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "pyqtgraph",
        SimpleNamespace(cleanup=lambda: calls.append("cleanup")),
    )

    report = {}
    probe._shutdown_qt_process(report)

    assert calls == ["cleanup"]
    assert report["shutdown"]["pyqtgraph_cleanup"] is True


def test_reported_complete_children_exit_without_native_teardown(monkeypatch):
    """A completed GUI child must not die in interpreter exit after its report lands.

    ParseFCS actual-Main children repeatedly finished every lifecycle phase,
    wrote ``phase: complete`` and shutdown markers, and were then killed with
    SIGBUS while Python unloaded native extensions. The parent consumes the
    exit code as a verdict, so once the report is flushed the only safe exit
    is to skip native teardown entirely.
    """
    exited = {}
    monkeypatch.setattr(
        probe.os, "_exit", lambda code: exited.setdefault("code", code), raising=False
    )

    # Simulate everything after main(): report written, cleanup ran, then the
    # module-level exit contract must fire instead of returning into teardown.
    report = {"phase": "complete", "shutdown": {"pyqtgraph_cleanup": True}}
    probe._exit_after_report(report)

    assert exited == {"code": 0}
