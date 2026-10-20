"""Run the test suite one directory at a time, each in a pytest process of its own.

One pytest process over ~33k tests carries every module's leftovers into the next, and
when the resource guard (``test/resource_guard.py``) stops it -- correctly, the machine
was running out of memory -- the whole run is lost. Here every top-level directory of the
suite is a chunk: a stop costs one chunk, ``--resume`` skips the chunks already done, and
memory starts from zero for each.

Before a chunk starts, the runner waits until the machine has memory to spare, so a gate
run yields to other work instead of being stopped half way.

Usage::

    python -m build_tools.dev_utils.run_tests_chunked [--resume] [--only test/fio ...]
        [-- extra pytest args]

Results land in ``~/.cache/chisurf/test-resources/gate/``: ``<chunk>.log`` per chunk and
``summary.json`` (chunk -> exit code, counts, seconds). The exit code is 0 only when every
chunk passed.

``seconds`` is the time the machine was *awake* running the chunk (the monotonic clock,
which stops while the machine sleeps); ``wall_seconds`` and ``slept_seconds`` appear when
the two differ by more than a minute. A gate left running over a closed lid once reported
the calculator chunk at 4.4 h when pytest itself took 278 s: the machine slept from 23:40
to 06:39 and the chunk only crept forward in 45-second maintenance wakes. On macOS the
runner holds a ``caffeinate -i -s`` assertion for its lifetime, which stops idle sleep
(and system sleep on AC); closing the lid on battery still sleeps the machine.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "chisurf" / "test-resources" / "gate"
MARKERS = "not slow and not e2e and not gui and not widget"
#: The environment the gate runs with: offscreen, one thread per numeric library, the
#: resource guard's limits (see okf/workflows/testing.md).
ENV = {
    "QT_QPA_PLATFORM": "offscreen",
    "PYTHONUNBUFFERED": "1",
    "PYTHONUTF8": "1",
    "LC_NUMERIC": "C",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMBA_NUM_THREADS": "1",
    "CHISURF_TEST_MAX_RSS_MB": "3000",
    "CHISURF_TEST_MIN_FREE_MB": "1500",
    "CHISURF_TEST_MAX_SWAP_GROWTH_MB": "1500",
    "CHISURF_TEST_MIN_DISK_MB": "6000",
}
#: Memory the machine must have available before a chunk starts.
START_FREE_MB = 3000


#: Plugin directories that hold no real tests: the plugin template's ``test_*.py`` are
#: cookiecutter sources (pytest exits 2 on them).
SKIP_FAMILIES = {"cookiecutter-chisurf-plugin"}
#: A plugin family with more test files than this runs as ``<family>[i/n]`` batches of
#: about this many files: chimol (241 files) keeps scene/GPU caches per module, and as one
#: process it was stopped by the resource guard at RSS > 3 GB.
BATCH_FILES = 40

#: The name of the chunk that holds the test files directly under test/.
LOOSE = "test/*.py"


def chunks() -> list[str]:
    """Every top-level test directory, the loose test files as one chunk, every plugin family
    and the tests under ``chisurf/`` outside the plugins, in a stable order."""
    found: list[str] = []
    test = ROOT / "test"
    for path in sorted(test.iterdir()):
        if path.name.startswith((".", "_")) or path.name in ("data", "fixtures", "benchmarks", "e2e"):
            continue
        if path.is_dir() and any(path.rglob("test_*.py")):
            found.append(str(path.relative_to(ROOT)))
    if any(test.glob("test_*.py")):
        found.append(LOOSE)
    plugins = ROOT / "chisurf" / "plugins"
    for family in sorted(p for p in plugins.iterdir() if p.is_dir()):
        if family.name in SKIP_FAMILIES or not any(family.rglob("test_*.py")):
            continue
        name = str(family.relative_to(ROOT))
        n = len(_family_files(name))
        if n > BATCH_FILES:
            parts = -(-n // BATCH_FILES)
            found.extend(f"{name}[{i}/{parts}]" for i in range(1, parts + 1))
        else:
            found.append(name)
    for path in sorted((ROOT / "chisurf").iterdir()):
        if path.is_dir() and path.name != "plugins" and any(path.rglob("test_*.py")):
            found.append(str(path.relative_to(ROOT)))
    return found


def _family_files(family: str) -> list[str]:
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / family).rglob("test_*.py"))


def _targets(chunk: str) -> list[str]:
    if chunk == LOOSE:
        return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "test").glob("test_*.py"))
    batch = re.fullmatch(r"(.+)\[(\d+)/(\d+)\]", chunk)
    if batch:
        family, index, parts = batch.group(1), int(batch.group(2)), int(batch.group(3))
        files = _family_files(family)
        size = -(-len(files) // parts)
        return files[(index - 1) * size:index * size]
    return [chunk]


def _available_mb() -> float:
    try:
        import psutil
    except ImportError:
        return float("inf")
    return psutil.virtual_memory().available / 2**20


def _wait_for_memory() -> None:
    waited = False
    while _available_mb() < START_FREE_MB:
        if not waited:
            print(f"  waiting for {START_FREE_MB} MB available ({_available_mb():.0f} now)", flush=True)
            waited = True
        time.sleep(15)


def _hold_awake() -> subprocess.Popen | None:
    """Keep macOS from idle-sleeping while the gate runs; ``None`` elsewhere.

    ``-w`` ties the assertion to this process, so it ends with the runner even when the
    runner is killed.
    """
    if sys.platform != "darwin" or shutil.which("caffeinate") is None:
        return None
    return subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())])


def _counts(text: str) -> dict:
    tail = text.strip().splitlines()[-3:] if text.strip() else []
    counts = {}
    for line in tail:
        for number, word in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)", line):
            counts[word.rstrip("s") if word.startswith("error") else word] = int(number)
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--resume", action="store_true", help="skip chunks with a recorded result")
    parser.add_argument("--only", nargs="*", default=None, help="run only these chunks")
    parser.add_argument("pytest_args", nargs="*", help="extra pytest arguments (after --)")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    summary_path = OUT / "summary.json"
    summary = json.loads(summary_path.read_text()) if args.resume and summary_path.is_file() else {}
    todo = args.only or chunks()
    env = {**os.environ, **ENV}
    awake = _hold_awake()
    for chunk in todo:
        if args.resume and chunk in summary and summary[chunk]["exit"] in (0, 1, 5):
            continue
        _wait_for_memory()
        log = OUT / (re.sub(r"[\[\]]", "_", chunk).replace("/", "__").replace("*", "loose") + ".log")
        started, started_wall = time.monotonic(), time.time()
        print(f"{chunk} ...", flush=True)
        with open(log, "w") as fh:
            code = subprocess.call(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", MARKERS,
                 "--timeout=120", "-rfE", *_targets(chunk), *args.pytest_args],
                cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT,
            )
        counts = _counts(log.read_text(errors="replace"))
        seconds, wall = time.monotonic() - started, time.time() - started_wall
        summary[chunk] = {"exit": code, **counts, "seconds": round(seconds, 1)}
        slept = ""
        if wall - seconds > 60:
            summary[chunk].update(wall_seconds=round(wall, 1), slept_seconds=round(wall - seconds, 1))
            slept = f" (machine slept {wall - seconds:.0f}s; wall {wall:.0f}s)"
        summary_path.write_text(json.dumps(summary, indent=1))
        print(f"  exit {code} {counts} {summary[chunk]['seconds']}s{slept}", flush=True)
    if awake is not None:
        awake.terminate()
    bad = {c: r for c, r in summary.items() if c in todo and r["exit"] not in (0, 5)}
    print(f"{len(todo) - len(bad)}/{len(todo)} chunks green; failing: {sorted(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
