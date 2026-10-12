"""Ratchet for mypy errors: per-file counts may only go down.

``test/mypy_baseline.json`` maps each file to its current mypy error count.
The guard fails when

* a file's count rises,
* a file with errors appears that is not in the baseline, or
* an entry is stale (the count dropped or the file is clean now) -- lower it.

Refresh after fixing errors (never to absorb new ones)::

    python test/test_mypy_baseline.py --update

See ``okf/workflows/testing.md``.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "test" / "mypy_baseline.json"
_LINE = re.compile(r"^(?P<file>[^:\n]+\.pyi?):\d+(?::\d+)?: error: ")


def count_mypy_errors() -> dict[str, int]:
    """Run mypy over ``chisurf/`` and return ``{file: error_count}``."""
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "chisurf/", "--no-error-summary", "--no-color-output"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    counts: collections.Counter[str] = collections.Counter()
    for line in proc.stdout.splitlines():
        m = _LINE.match(line)
        if m:
            counts[m.group("file")] += 1
    if proc.returncode not in (0, 1) or (not counts and proc.stderr.strip()):
        raise RuntimeError(f"mypy failed to run:\n{proc.stdout}\n{proc.stderr}")
    return dict(sorted(counts.items()))


def _write(counts: dict[str, int]) -> None:
    BASELINE.write_text(
        json.dumps({"total": sum(counts.values()), "files": counts}, indent=1) + "\n"
    )


def compare(base: dict[str, int], now: dict[str, int]) -> tuple[list[str], list[str]]:
    """Return ``(regressions, stale)`` message lists."""
    regressions = [
        f"{f}: {now[f]} errors (baseline {base.get(f, 0)})"
        for f in sorted(now)
        if now[f] > base.get(f, 0)
    ]
    stale = [
        f"{f}: baseline {base[f]}, now {now.get(f, 0)}"
        for f in sorted(base)
        if now.get(f, 0) < base[f]
    ]
    return regressions, stale


@pytest.mark.slow
def test_mypy_error_counts_do_not_rise():
    """No file may gain mypy errors; lowered counts must be written back."""
    base = json.loads(BASELINE.read_text())["files"]
    regressions, stale = compare(base, count_mypy_errors())
    msg = []
    if regressions:
        msg.append(
            "mypy errors rose (fix them, do not raise the baseline):\n  " + "\n  ".join(regressions)
        )
    if stale:
        msg.append(
            "baseline is stale, shrink it with `python test/test_mypy_baseline.py --update`:\n  "
            + "\n  ".join(stale)
        )
    assert not msg, "\n".join(msg)


def test_compare_semantics():
    """The ratchet logic flags rises, new files and stale entries."""
    reg, stale = compare({"a.py": 2, "b.py": 1}, {"a.py": 3, "c.py": 1})
    assert len(reg) == 2 and len(stale) == 1 and stale[0].startswith("b.py")
    assert compare({"a.py": 2}, {"a.py": 2}) == ([], [])


if __name__ == "__main__":
    if "--update" in sys.argv:
        _write(count_mypy_errors())
        print(f"wrote {BASELINE}")
