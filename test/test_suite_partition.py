"""Every test runs in exactly one pixi suite.

The ``test`` task used to filter with ``-k 'not gui and not widget and not window'`` and
``test-gui`` only looked at plugin directories, so a ``test/`` case whose node id merely
contained "gui" ran in no suite at all; ``tests/`` directories and flat ``test_*.py``
files beside the code were never on any path list. Suites are now carved out by marker
over the whole tree. This guard collects every test once and evaluates the ``-m``
expression of each suite task from ``pixi.toml``.
"""

import json
import os
import pathlib
import subprocess
import sys
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SUITES = ("test", "test-gui", "test-slow", "test-e2e")

_DUMP_PLUGIN = '''
import json, os
def pytest_collection_finish(session):
    rows = [[i.nodeid, sorted({m.name for m in i.iter_markers()})] for i in session.items]
    with open(os.environ["SUITE_DUMP"], "w") as fh:
        json.dump(rows, fh)
'''


def _task_args(name):
    """Return the shell-split ``cmd`` of a pixi task."""
    import shlex

    data = tomllib.loads((ROOT / "pixi.toml").read_text())
    for table in _walk(data):
        if name in table and isinstance(table[name], dict) and "cmd" in table[name]:
            return shlex.split(table[name]["cmd"])
    raise KeyError(name)


def _walk(node):
    """Yield every table in a nested TOML mapping."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)


def _marker_expression(name):
    args = _task_args(name)
    assert "-k" not in args, f"{name}: select by marker, never by -k substring"
    assert "-m" in args, f"{name}: needs a -m expression"
    paths = [a for a in args[1:] if (ROOT / a).exists()]
    assert not paths, f"{name}: selects by path {paths}; paths belong in pyproject testpaths"
    return args[args.index("-m") + 1]


@pytest.fixture(scope="module")
def collected(tmp_path_factory):
    """Collect the whole tree once; return ``[(nodeid, markers)]``."""
    work = tmp_path_factory.mktemp("suite_partition")
    (work / "dump_plugin.py").write_text(_DUMP_PLUGIN)
    out = work / "items.json"
    env = {**os.environ, "SUITE_DUMP": str(out), "PYTHONPATH": str(work)}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         "-p", "dump_plugin"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=900,
    )
    assert out.exists(), proc.stdout[-3000:] + proc.stderr[-3000:]
    assert proc.returncode == 0, proc.stdout[-3000:]
    return json.loads(out.read_text())


def test_every_test_belongs_to_exactly_one_suite(collected):
    """Zero or two suites for one test means it silently never runs, or runs twice."""
    from _pytest.mark.expression import Expression

    exprs = {name: Expression.compile(_marker_expression(name)) for name in SUITES}
    assert collected, "collected nothing"
    bad = {}
    for nodeid, marks in collected:
        marks = set(marks)
        hit = [n for n, e in exprs.items() if e.evaluate(lambda m, marks=marks: m in marks)]
        if len(hit) != 1:
            bad[nodeid] = hit
    assert not bad, f"{len(bad)} tests are in != 1 suite, e.g. {list(bad.items())[:5]}"


def test_coverage_task_runs_the_default_suite():
    """``test-cov`` measures exactly what ``test`` runs."""
    assert _marker_expression("test-cov") == _marker_expression("test")


def test_no_test_file_hides_outside_the_collected_roots():
    """A ``test_*.py`` outside ``test/`` and ``chisurf/`` would be in no suite."""
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]
    assert set(cfg["testpaths"]) == {"test", "chisurf"}
    skipped = set(cfg["norecursedirs"])
    stray = []
    for path in (ROOT / "chisurf").rglob("test_*.py"):
        parts = set(path.relative_to(ROOT).parts)
        if parts & skipped:
            stray.append(str(path.relative_to(ROOT)))
    # Only the cookiecutter template is allowed to be skipped: its files are not valid Python.
    assert all("cookiecutter" in s for s in stray), stray
