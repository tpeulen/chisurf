"""Keep a test run from taking the machine down: measure every test, stop the run at a cap.

One pytest process runs tens of thousands of tests. Memory a test keeps (a cache filled
at module level, a window never closed, a thread never joined) is carried by every test
after it, so a run that is fine at 10 % can push a 16 GB laptop into swap at 60 %, and
leaked threads that keep polling drive the load average into the hundreds. Nothing in a
green-or-red test result shows any of that.

This plugin, loaded by the root ``conftest.py``:

* records resident memory, thread count and child processes after every test, and
  prints the tests that grew memory or left threads/processes behind (terminal summary);
* appends one CSV row per test, as the test finishes, to ``CHISURF_TEST_RESOURCE_LOG``
  or else ``~/.cache/chisurf/test-resources/run-<time>-<pid>.csv`` (newest 10 kept) and
  names the running test in a state file before it starts: a run that takes the machine
  down still leaves the record of what it did, outside the tmp directory a reboot wipes;
* starts ``test/resource_watchdog.py`` as a separate process that ends the run *before*
  the machine suffers. It is out of process on purpose: a thread in here is starved by a
  C extension that allocates while holding the GIL, and cannot see child processes. It
  stops the run when the process tree exceeds ``CHISURF_TEST_MAX_RSS_MB`` (default
  4096), the system has less than ``CHISURF_TEST_MIN_FREE_MB`` available (default 1024),
  swap grew by more than ``CHISURF_TEST_MAX_SWAP_GROWTH_MB`` (default 2048), or the temp
  volume has less than ``CHISURF_TEST_MIN_DISK_MB`` free (default 4096): it prints the
  running test and the biggest growers, deletes this run's tmp_path tree and kills the
  tree. ``0`` disables a limit.

Only ``psutil`` is needed; without it the plugin does nothing.
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pytest

try:
    import psutil
except ImportError:  # pragma: no cover - psutil ships in every pixi env
    psutil = None

_MB = 1024 * 1024
_PROC = psutil.Process() if psutil is not None else None
_STATE = {"current": "<collection>", "rows": [], "last_rss": 0, "start_rss": 0}
_FIELDS = (
    "nodeid", "rss_mb", "tree_mb", "delta_mb", "threads", "thread_delta",
    "children", "child_delta", "disk_mb", "tmp_mb",
)
_KEEP_LOGS = 10


def _env_mb(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _rss() -> int:
    return _PROC.memory_info().rss


def _children():
    dog = _STATE.get("watchdog")
    try:
        return [c for c in _PROC.children(recursive=True) if dog is None or c.pid != dog.pid]
    except psutil.Error:
        return []


def _top(rows, key, n=15):
    return sorted((r for r in rows if r[key] > 0), key=lambda r: r[key], reverse=True)[:n]


def _report(write, rows) -> None:
    grow = _top(rows, "delta_mb")
    if grow:
        write(f"tests that grew resident memory the most (of {len(rows)}):")
        for r in grow:
            write(f"  +{r['delta_mb']:7.1f} MB  -> {r['tree_mb']:7.1f} MB  {r['nodeid']}")
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
    tmp = _top(rows, "tmp_mb", 10)
    if tmp:
        write("tests that wrote the most into tmp_path:")
        for r in tmp:
            write(f"  {r['tmp_mb']:7.1f} MB  {r['nodeid']}")
    procs = _top(rows, "child_delta", 10)
    if procs:
        write("tests that left child processes running:")
        for r in procs:
            write(f"  +{r['child_delta']:3d} children (now {r['children']})  {r['nodeid']}")


def _disk_free() -> int:
    return shutil.disk_usage(_STATE.get("disk_path", tempfile.gettempdir())).free


def _tree_rss(children) -> int:
    total = _rss()
    for child in children:
        try:
            total += child.memory_info().rss
        except psutil.Error:
            pass
    return total


def _log_path() -> Path:
    named = os.environ.get("CHISURF_TEST_RESOURCE_LOG")
    if named:
        return Path(named)
    folder = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "chisurf" / "test-resources"
    folder.mkdir(parents=True, exist_ok=True)
    for old in sorted(folder.glob("run-*.csv"))[: -(_KEEP_LOGS - 1)]:
        old.unlink(missing_ok=True)
    return folder / time.strftime(f"run-%Y%m%d-%H%M%S-{os.getpid()}.csv")


def _state_write(name: str, text: str) -> None:
    folder = _STATE.get("state_dir")
    if folder:
        try:
            Path(folder, name).write_text(text)
        except OSError:
            pass


def _start_watchdog(limits) -> None:
    state_dir = tempfile.mkdtemp(prefix="chisurf-resource-guard-")
    _STATE["state_dir"] = state_dir
    _state_write("log_path", str(_STATE["log_path"]))
    script = Path(__file__).with_name("resource_watchdog.py")
    # The watchdog writes its report to the terminal: give it the stderr pytest had before
    # it started capturing, or the report lands in a capture file nobody reads.
    _STATE["watchdog"] = subprocess.Popen(
        [sys.executable, "-I", str(script), str(os.getpid()), state_dir, *map(str, limits)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=_STATE["stderr_fd"],
        close_fds=True,
    )


def pytest_configure(config):
    if psutil is None:
        return
    # One guard per process: pytester sessions run in-process and configure again.
    if getattr(sys, "_chisurf_resource_guard", False):
        return
    sys._chisurf_resource_guard = True
    capman = config.pluginmanager.getplugin("capturemanager")
    cap = getattr(getattr(capman, "_global_capturing", None), "err", None)
    fd = getattr(cap, "targetfd_save", None)
    _STATE["stderr_fd"] = os.dup(fd if fd is not None else 2)
    _STATE["start_rss"] = _STATE["last_rss"] = _tree_rss(_children())
    _STATE["last_threads"] = threading.active_count()
    _STATE["last_children"] = len(_children())
    _STATE["last_disk"] = _disk_free()
    _STATE["log_path"] = _log_path()
    with open(_STATE["log_path"], "w", newline="") as fh:
        csv.writer(fh).writerow(_FIELDS)
    limits = (
        _env_mb("CHISURF_TEST_MAX_RSS_MB", 4096),
        _env_mb("CHISURF_TEST_MIN_FREE_MB", 1024),
        _env_mb("CHISURF_TEST_MAX_SWAP_GROWTH_MB", 2048),
        _env_mb("CHISURF_TEST_MIN_DISK_MB", 4096),
    )
    if any(limits):
        _start_watchdog(limits)


def pytest_unconfigure(config):
    dog = _STATE.pop("watchdog", None)
    if dog is not None:
        dog.terminate()
        try:
            dog.wait(5)
        except subprocess.TimeoutExpired:
            dog.kill()
    folder = _STATE.pop("state_dir", None)
    if folder:
        shutil.rmtree(folder, ignore_errors=True)


def pytest_sessionstart(session):
    factory = getattr(session.config, "_tmp_path_factory", None)
    if factory is not None:
        try:
            _STATE["basetemp"] = str(factory.getbasetemp())
            _STATE["disk_path"] = _STATE["basetemp"]
            _state_write("basetemp", _STATE["basetemp"])
        except OSError:
            pass


def _tree_bytes(path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # A passing test's tmp_path is deleted at teardown, before logfinish: size it here.
    if call.when == "call":
        path = getattr(item, "funcargs", {}).get("tmp_path")
        _STATE["tmp_bytes"] = _tree_bytes(path) if path is not None else 0
    yield


def pytest_runtest_logstart(nodeid, location):
    _STATE["tmp_bytes"] = 0
    _STATE["current"] = nodeid
    _state_write("current", nodeid)


def pytest_runtest_logfinish(nodeid, location):
    if psutil is None:
        return
    rss = _rss()
    threads = threading.active_count()
    kids = _children()
    children = len(kids)
    tree = _tree_rss(kids)
    disk = _disk_free()
    _STATE["rows"].append(
        {
            "nodeid": nodeid,
            "rss_mb": rss / _MB,
            "tree_mb": tree / _MB,
            "delta_mb": (tree - _STATE["last_rss"]) / _MB,
            "threads": threads,
            "thread_delta": threads - _STATE["last_threads"],
            "children": children,
            "child_delta": children - _STATE["last_children"],
            "disk_mb": (_STATE.get("last_disk", disk) - disk) / _MB,
            "tmp_mb": _STATE.get("tmp_bytes", 0) / _MB,
        }
    )
    _STATE["last_rss"], _STATE["last_threads"], _STATE["last_children"] = tree, threads, children
    _STATE["last_disk"] = disk
    row = _STATE["rows"][-1]
    if "log_path" in _STATE:
        with open(_STATE["log_path"], "a", newline="") as fh:
            csv.writer(fh).writerow(
                [row[k] if isinstance(row[k], (str, int)) else f"{row[k]:.2f}" for k in _FIELDS]
            )


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    rows = _STATE["rows"]
    if psutil is None or not rows:
        return
    if len(rows) < 50:
        return
    tr = terminalreporter
    tr.section("resources")
    tr.write_line(
        f"resident memory {_STATE['start_rss'] / _MB:.0f} MB -> {_rss() / _MB:.0f} MB, "
        f"threads {threading.active_count()}, child processes {len(_children())}; "
        f"per-test record: {_STATE.get('log_path')}"
    )
    _report(tr.write_line, rows)
