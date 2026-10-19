"""Out-of-process watchdog for a pytest run (started by ``test/resource_guard.py``).

A thread inside the test process cannot be trusted to stop a run: a C extension that
allocates while holding the GIL starves it, and the memory of child processes (worker
pools, servers) is not the test process's RSS. This process polls from outside:

* resident memory of the whole process tree (the pytest process and every descendant),
* memory the system still has available, and swap growth since the run started,
* free space on the volume holding the run's tmp_path tree,

and when a limit is crossed it prints the running test and the biggest growers (read
from the per-test CSV the plugin appends to after every test), deletes the run's
tmp_path tree and SIGKILLs the tree. It exits on its own when the pytest process ends.

Usage: ``python resource_watchdog.py <pid> <state_dir> <max_tree_mb> <min_free_mb>
<max_swap_growth_mb> <min_disk_mb>`` (0 disables a limit).
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import time

import psutil

_MB = 1024 * 1024


def _read(path: str) -> str:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _tree(proc: psutil.Process) -> list[psutil.Process]:
    try:
        return [proc, *proc.children(recursive=True)]
    except psutil.Error:
        return [proc]


def _tree_rss(procs) -> int:
    total = 0
    for p in procs:
        try:
            total += p.memory_info().rss
        except psutil.Error:
            pass
    return total


def _report(state_dir: str, write) -> None:
    log = _read(os.path.join(state_dir, "log_path"))
    rows = []
    if log:
        try:
            with open(log, newline="") as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            pass
    write(f"per-test record: {log or '<none>'} ({len(rows)} tests finished)")

    def top(key, n):
        def val(r):
            try:
                return float(r[key])
            except (KeyError, ValueError):
                return 0.0

        return sorted((r for r in rows if val(r) > 0), key=val, reverse=True)[:n]

    for r in top("delta_mb", 15):
        write(f"  +{float(r['delta_mb']):7.1f} MB -> {float(r['tree_mb']):7.1f} MB  {r['nodeid']}")
    for r in top("thread_delta", 5):
        write(f"  +{r['thread_delta']} threads (now {r['threads']})  {r['nodeid']}")
    for r in top("child_delta", 5):
        write(f"  +{r['child_delta']} child processes (now {r['children']})  {r['nodeid']}")


def main(argv) -> int:
    pid = int(argv[1])
    state_dir = argv[2]
    max_tree, min_free, max_swap, min_disk = (int(a) * _MB for a in argv[3:7])
    try:
        root = psutil.Process(pid)
    except psutil.Error:
        return 0
    swap0 = psutil.swap_memory().used
    me = os.getpid()
    while True:
        time.sleep(0.25)
        if not root.is_running() or root.status() == psutil.STATUS_ZOMBIE:
            return 0
        procs = [p for p in _tree(root) if p.pid != me]
        reason = None
        try:
            rss = _tree_rss(procs)
            free = psutil.virtual_memory().available
            swap = psutil.swap_memory().used - swap0
            basetemp = _read(os.path.join(state_dir, "basetemp"))
            disk = shutil.disk_usage(basetemp or state_dir).free
        except (psutil.Error, OSError):
            continue
        if max_tree and rss > max_tree:
            reason = f"test process tree uses {rss / _MB:.0f} MB > cap {max_tree / _MB:.0f} MB"
        elif min_free and free < min_free:
            reason = f"system has {free / _MB:.0f} MB available < floor {min_free / _MB:.0f} MB"
        # Swap grows for reasons that are not this run (other suites, a just-booted
        # machine): count it only once the run itself is a large share of the memory.
        elif max_swap and swap > max_swap and rss > min(max_tree or 1024 * _MB, 1024 * _MB):
            reason = f"swap grew by {swap / _MB:.0f} MB since the run started > {max_swap / _MB:.0f} MB"
        elif min_disk and disk < min_disk:
            reason = f"disk has {disk / _MB:.0f} MB free < floor {min_disk / _MB:.0f} MB"
        if reason is None:
            continue
        # Kill first: every quarter second spent writing the report is memory the machine
        # does not have.
        for p in reversed(procs):
            try:
                p.kill()
            except psutil.Error:
                pass
        err = sys.stderr

        def write(line):
            err.write("resource_guard: " + line + "\n")

        write("")
        write(f"STOPPED THE TEST RUN: {reason} (tree {rss / _MB:.0f} MB, {len(procs)} processes)")
        write(f"running test: {_read(os.path.join(state_dir, 'current')) or '<collection>'}")
        _report(state_dir, write)
        write("raise the CHISURF_TEST_* limits only after fixing the growth above.")
        err.flush()
        if basetemp:
            shutil.rmtree(basetemp, ignore_errors=True)
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
