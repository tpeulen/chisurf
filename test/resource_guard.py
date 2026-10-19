"""Keep a test run from taking the machine down: measure every test, stop the run at a cap.

One pytest process runs tens of thousands of tests. Memory a test keeps (a cache filled
at module level, a window never closed, a thread never joined) is carried by every test
after it, so a run that is fine at 10 % can push a 16 GB laptop into swap at 60 %, and
leaked threads that keep polling drive the load average into the hundreds. Nothing in a
green-or-red test result shows any of that.

This plugin, loaded by the root ``conftest.py``:

* records resident memory, thread count and child processes after every test, and
  prints the tests that grew memory or left threads/processes behind (terminal summary);
* writes the per-test record as CSV when ``CHISURF_TEST_RESOURCE_LOG`` names a file;
* runs a watchdog thread that ends the run *before* the machine suffers: when the
  process exceeds ``CHISURF_TEST_MAX_RSS_MB`` (default 4096) or the system has less than
  ``CHISURF_TEST_MIN_FREE_MB`` available (default 1024), or the temp volume has less
  than ``CHISURF_TEST_MIN_DISK_MB`` free (default 4096), it prints which test was running
  and the biggest growers so far, deletes this run's tmp_path tree, kills the run's
  child processes and exits with 3.
  ``CHISURF_TEST_MAX_RSS_MB=0`` disables the cap.

Only ``psutil`` is needed; without it the plugin does nothing.
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
import threading
import time

import pytest

try:
    import psutil
except ImportError:  # pragma: no cover - psutil ships in every pixi env
    psutil = None

_MB = 1024 * 1024
_PROC = psutil.Process() if psutil is not None else None
_STATE = {"current": "<collection>", "rows": [], "last_rss": 0, "start_rss": 0}


def _env_mb(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _rss() -> int:
    return _PROC.memory_info().rss


def _children():
    try:
        return _PROC.children(recursive=True)
    except psutil.Error:
        return []


def _top(rows, key, n=15):
    return sorted((r for r in rows if r[key] > 0), key=lambda r: r[key], reverse=True)[:n]


def _report(write, rows) -> None:
    grow = _top(rows, "delta_mb")
    if grow:
        write(f"tests that grew resident memory the most (of {len(rows)}):")
        for r in grow:
            write(f"  +{r['delta_mb']:7.1f} MB  -> {r['rss_mb']:7.1f} MB  {r['nodeid']}")
    threads = _top(rows, "thread_delta", 10)
    if threads:
        write("tests that left threads running:")
        for r in threads:
            write(f"  +{r['thread_delta']:3d} threads (now {r['threads']})  {r['nodeid']}")
    disk = _top(rows, "disk_mb", 10)
    if disk:
        write("tests that used the most disk:")
        for r in disk:
            write(f"  +{r['disk_mb']:7.1f} MB  {r['nodeid']}")
    procs = _top(rows, "child_delta", 10)
    if procs:
        write("tests that left child processes running:")
        for r in procs:
            write(f"  +{r['child_delta']:3d} children (now {r['children']})  {r['nodeid']}")


def _disk_free() -> int:
    return shutil.disk_usage(_STATE.get("disk_path", tempfile.gettempdir())).free


def _watchdog(max_rss: int, min_free: int, min_disk: int, interval: float) -> None:
    while True:
        time.sleep(interval)
        try:
            rss = _rss()
            free = psutil.virtual_memory().available
            disk = _disk_free()
        except (psutil.Error, OSError):
            continue
        reason = None
        if max_rss and rss > max_rss:
            reason = f"resident memory {rss / _MB:.0f} MB > cap {max_rss / _MB:.0f} MB"
        elif min_free and free < min_free:
            reason = (
                f"system has {free / _MB:.0f} MB available < floor {min_free / _MB:.0f} MB "
                f"(this process: {rss / _MB:.0f} MB)"
            )
        elif min_disk and disk < min_disk:
            reason = f"disk has {disk / _MB:.0f} MB free < floor {min_disk / _MB:.0f} MB"
        if reason is None:
            continue
        # pytest redirects fd 2 into a capture file while a test runs: write through the
        # descriptor duplicated before capturing started, or the report is lost.
        err = os.fdopen(os.dup(_STATE["stderr_fd"]), "w") if "stderr_fd" in _STATE else sys.__stderr__
        _write_csv(list(_STATE["rows"]))
        err.write(f"\n\nresource_guard: STOPPING THE TEST RUN: {reason}\n")
        err.write(f"resource_guard: running test: {_STATE['current']}\n")
        _report(lambda line: err.write("resource_guard: " + line + "\n"), list(_STATE["rows"]))
        err.write(
            "resource_guard: raise CHISURF_TEST_MAX_RSS_MB / lower CHISURF_TEST_MIN_FREE_MB "
            "only after fixing the growth above.\n"
        )
        err.flush()
        # os._exit skips pytest's own tmp_path cleanup: drop this run's directories here,
        # or every stopped run leaves gigabytes behind.
        if _STATE.get("basetemp"):
            shutil.rmtree(_STATE["basetemp"], ignore_errors=True)
        for child in _children():
            try:
                child.kill()
            except psutil.Error:
                pass
        os._exit(3)


def _write_csv(rows) -> None:
    path = os.environ.get("CHISURF_TEST_RESOURCE_LOG")
    if not path or not rows:
        return
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def pytest_configure(config):
    if psutil is None:
        return
    if "stderr_fd" not in _STATE:
        capman = config.pluginmanager.getplugin("capturemanager")
        fd = None
        cap = getattr(getattr(capman, "_global_capturing", None), "err", None)
        fd = getattr(cap, "targetfd_save", None)
        _STATE["stderr_fd"] = os.dup(fd if fd is not None else 2)
    _STATE["start_rss"] = _STATE["last_rss"] = _rss()
    _STATE["last_threads"] = threading.active_count()
    _STATE["last_children"] = len(_children())
    max_rss = _env_mb("CHISURF_TEST_MAX_RSS_MB", 4096) * _MB
    min_free = _env_mb("CHISURF_TEST_MIN_FREE_MB", 1024) * _MB
    min_disk = _env_mb("CHISURF_TEST_MIN_DISK_MB", 4096) * _MB
    _STATE["last_disk"] = _disk_free()
    # One watchdog per process: pytester sessions run in-process and configure again.
    if (max_rss or min_free or min_disk) and not getattr(sys, "_chisurf_resource_guard", False):
        sys._chisurf_resource_guard = True
        threading.Thread(
            target=_watchdog, args=(max_rss, min_free, min_disk, 0.5), name="resource_guard", daemon=True
        ).start()


def pytest_sessionstart(session):
    factory = getattr(session.config, "_tmp_path_factory", None)
    if factory is not None:
        try:
            _STATE["basetemp"] = str(factory.getbasetemp())
            _STATE["disk_path"] = _STATE["basetemp"]
        except OSError:
            pass


def pytest_runtest_logstart(nodeid, location):
    _STATE["current"] = nodeid


def pytest_runtest_logfinish(nodeid, location):
    if psutil is None:
        return
    rss = _rss()
    threads = threading.active_count()
    children = len(_children())
    disk = _disk_free()
    _STATE["rows"].append(
        {
            "nodeid": nodeid,
            "rss_mb": rss / _MB,
            "delta_mb": (rss - _STATE["last_rss"]) / _MB,
            "threads": threads,
            "thread_delta": threads - _STATE["last_threads"],
            "children": children,
            "child_delta": children - _STATE["last_children"],
            "disk_mb": (_STATE.get("last_disk", disk) - disk) / _MB,
        }
    )
    _STATE["last_rss"], _STATE["last_threads"], _STATE["last_children"] = rss, threads, children
    _STATE["last_disk"] = disk


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    rows = _STATE["rows"]
    if psutil is None or not rows:
        return
    _write_csv(rows)
    if len(rows) < 50:
        return
    tr = terminalreporter
    tr.section("resources")
    tr.write_line(
        f"resident memory {_STATE['start_rss'] / _MB:.0f} MB -> {_rss() / _MB:.0f} MB, "
        f"threads {threading.active_count()}, child processes {len(_children())}"
    )
    _report(tr.write_line, rows)
