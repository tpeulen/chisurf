"""After the source-tree move, nothing names the old modules.

``tools/moves.toml`` in the chimol repo is the move table. Every *old*
dotted name in it must be gone from the chimol package, from this test
directory, and from the ChiSurf call sites the table lists -- code, strings,
prose alike. Before the move (the table exists, the moves have not been
applied) the test is a no-op that only checks the table parses.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

_REPO = pathlib.Path(__import__("chimol").__file__).resolve().parents[1]
_MOVES = _REPO / "tools" / "moves.toml"


def _load():
    tomllib = pytest.importorskip("tomllib")
    with _MOVES.open("rb") as fh:
        return tomllib.load(fh)


def _moved(cfg) -> bool:
    """Whether the move has been applied (the first new module exists)."""
    new = next(iter(cfg["modules"].values()))
    return (_REPO / pathlib.Path(*new.split("."))).with_suffix(".py").exists() or (
        _REPO / pathlib.Path(*new.split(".")) / "__init__.py"
    ).exists()


@pytest.mark.skipif(not _MOVES.exists(), reason="no move table beside the package")
def test_no_old_dotted_name_survives():
    cfg = _load()
    if not _moved(cfg):
        pytest.skip("the move has not been applied yet")
    olds = sorted(cfg["modules"], key=len, reverse=True)
    pattern = re.compile(r"(?<![\w.])(" + "|".join(re.escape(o) for o in olds) + r")(?![\w])")
    roots = [str(_REPO / "chimol"), str(pathlib.Path(__file__).parent)]
    roots += [p for p in cfg["chisurf_files"]["python"] if pathlib.Path(p).exists()]
    hits = []
    for root in roots:
        proc = subprocess.run(
            [
                "grep",
                "-rnE",
                "--include=*.py",
                "--include=*.js",
                "--include=*.json",
                "--include=*.md",
                "--include=*.toml",
                "--include=*.txt",
                "--include=*.html",
                pattern.pattern,
                root,
            ],
            capture_output=True,
            text=True,
        )
        for line in proc.stdout.splitlines():
            if "/tools/moves.toml" in line or "/__pycache__/" in line:
                continue
            hits.append(line)
    assert not hits, "old module names still referenced:\n" + "\n".join(hits[:60])
