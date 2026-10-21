"""Guard: no GPL licence string or Orange provenance remains in the source.

The owner's 2026-10-17 directive (W15): the shipped distribution is MIT -- chisurf
and the ndxplorer submodule both. The GPL strings are history (chisurf
``5783d25a3``, ndxplorer ``2327ef3``), and the Orange visual-analytics toolkit's
provenance text was scrubbed from ndxplorer when VizRank was rewritten clean-room
(``0a66a36``). A GPL identifier re-entering a licence declaration, or the retired
toolkit's provenance phrases re-entering the source, undoes that.

The allow-list is empty: no file is exempt. But the scan is scoped to
*licence-identifying contexts* for identifiers, because the tree keeps sanctioned
remnants that a naive grep would flag: ndxplorer's own licence guard quotes the
retired ``"GPL-2.1"`` string in its docstring, comments may credit a GPL reference
implementation (attribution, not our licence), and the About dialogue names the
companion library IMP.bff as ``LGPL-2.1-or-later`` -- which is a different
licence, deliberately kept (see okf/subsystems/licensing.md). Identifiers are
therefore banned only where a licence is *declared* (SPDX lines, ``__license__``,
``license`` keys); the GPL licence-block boilerplate and the Orange provenance
phrases are banned outright. The word "VizRank" itself stays legal: it is now the
clean-room feature's name and cites the paper (Leban et al. 2006), not the
toolkit. Colour names ("Dark Orange") are not provenance.
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_TREES = (_ROOT / "chisurf", _ROOT / "modules" / "ndxplorer")
_SUFFIXES = {".py", ".toml", ".yaml", ".yml"}
#: Build/cache directories are not source.
_SKIP_PARTS = {
    "__pycache__",
    ".egg-info",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    ".benchmarks",
    ".cache",
    ".git",
}

#: A GPL licence identifier -- ``GPL-3.0``, ``GPLv2``, ``GPL-2.1``, ``GPL+`` -- but
#: not LGPL/AGPL (no letter may precede it).
_GPL_ID_RE = re.compile(r"(?<![A-Za-z])GPL(?:-?\d+(?:\.\d+)?|v\d+(?:\.\d+)?|\+)", re.IGNORECASE)
#: A line that *declares* a licence: SPDX headers (they live in comments),
#: ``__license__`` and ``license`` keys (TOML ``license = "..."`` /
#: ``license = { text = "..." }``, YAML ``license:``).
_LICENCE_DECL_RE = re.compile(r"^\s*#?\s*(?:SPDX-License-Identifier\s*:|__license__\s*=|license\s*[:=])")
#: The GPL licence-block boilerplate, banned outright wherever it is pasted back.
_GPL_BOILERPLATE_RE = re.compile(
    r"GNU General Public License|Free Software Foundation"
    r"|distributed in the hope that it will be useful|gnu\.org/licenses",
    re.IGNORECASE,
)
#: The retired toolkit's provenance phrases (the text removed by ndxplorer's
#: clean-room rewrite): its name with a possessive or source path, its lab, and
#: its home page. A bare ``Orange`` is not banned -- colour names are not provenance.
_ORANGE_PROVENANCE_RE = re.compile(
    r"\bOrange3\b|\bOrange(?:['\u2019/])|University of Ljubljana"
    r"|Bioinformatics Lab|orangedatamining\.com|biolab/orange",
    re.IGNORECASE,
)


def _scan_files() -> list[pathlib.Path]:
    """Return the source files of both trees the guard reads.

    Returns
    -------
    list of pathlib.Path
        Every ``.py``/``.toml``/``.yaml``/``.yml`` file under ``chisurf/`` and the
        ``modules/ndxplorer`` submodule, outside build/cache directories.
    """
    return sorted(
        path
        for tree in _TREES
        if tree.is_dir()
        for path in tree.rglob("*")
        if path.suffix in _SUFFIXES
        and path.is_file()
        and not (_SKIP_PARTS & set(path.parts))
    )


def _violations(path: pathlib.Path) -> list[str]:
    """Return the guard violations in *path* as ``"line N: what"`` strings.

    Parameters
    ----------
    path : pathlib.Path
        A source file to inspect.

    Returns
    -------
    list of str
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    found: list[str] = []
    for number, line in enumerate(lines, start=1):
        if _LICENCE_DECL_RE.search(line) and _GPL_ID_RE.search(line):
            found.append(f"line {number}: GPL identifier in a licence declaration")
        if _GPL_BOILERPLATE_RE.search(line):
            found.append(f"line {number}: GPL licence-block boilerplate")
        if _ORANGE_PROVENANCE_RE.search(line):
            found.append(f"line {number}: Orange toolkit provenance phrase")
    return found


def _offenders() -> list[str]:
    """Scan both trees and return ``file:line`` offender descriptions."""
    return [
        f"{path.relative_to(_ROOT).as_posix()}:{detail}"
        for path in _scan_files()
        for detail in _violations(path)
    ]


def _check_tree() -> list[str]:  # pragma: no cover - trivial wrapper
    """The live scan, exposed for the ``__main__`` dry run."""
    return _offenders()


def _sample_violations(directory: pathlib.Path) -> list[str]:
    """Run ``_violations`` over samples in *directory* (shared by the self-tests).

    Parameters
    ----------
    directory : pathlib.Path
        Where the sample files live; the caller picks the directory (pytest's
        ``tmp_path`` or a temp dir in the dry run).

    Returns
    -------
    list of str
    """
    hits: list[str] = []
    for name, text in (
        ("spdx.py", "# SPDX-License-Identifier: GPL-3.0-only\n"),
        ("dunder.py", '__license__ = "GPL-2.1"\n'),
        ("pyproject.toml", '[project]\nlicense = "GPL-3.0-or-later"\n'),
        ("legacy.toml", 'license = { text = "GPL-2.1" }\n'),
        ("recipe.yaml", "license: GPL-2\n"),
        ("boilerplate.py", "# GNU General Public License as published by the Free Software Foundation.\n"),
        ("orange3.py", "# transcribed from Orange3's VizRankDialog.\n"),
        ("orange_path.py", "# (Orange/widgets/visualize/utils/vizrank.py, GPL-3.0)\n"),
        ("ljubljana.py", "# Bioinformatics Lab, University of Ljubljana\n"),
    ):
        (directory / name).write_text(text, encoding="utf-8")
        hits.extend(f"{name}: {detail}" for detail in _violations(directory / name))
    return hits


def _sample_clean(directory: pathlib.Path) -> list[str]:
    """Write the sanctioned remnants into *directory*; return what (wrongly) trips.

    Parameters
    ----------
    directory : pathlib.Path
        Where the sample files live.

    Returns
    -------
    list of str
    """
    hits: list[str] = []
    for name, text in (
        ("companion.py", 'COMPANION = "IMP.bff LGPL-2.1-or-later"\n'),
        ("attribution.py", '# Comments that credit a GPL reference implementation are attribution.\n'),
        ("guard_quote.py", '"""The About box kept saying "GPL-2.1" because the text was hand-written."""\n'),
        ("colour.py", 'COLORS = {"dark_orange": "Dark Orange"}\n'),
        ("citation.py", "# follows VizRank (Leban et al. 2006, doi:10.1007/s10618-005-0031-5).\n"),
        ("mit.toml", 'license = "MIT"\n'),
    ):
        (directory / name).write_text(text, encoding="utf-8")
        hits.extend(f"{name}: {detail}" for detail in _violations(directory / name))
    return hits


def test_no_gpl_strings_or_orange_provenance_in_source():
    """No GPL licence string or Orange provenance phrase in chisurf/ or the submodule."""
    offenders = _offenders()
    assert not offenders, (
        "W15: the distribution is MIT -- a GPL licence string or the retired Orange "
        "toolkit's provenance re-entered the source (see okf/subsystems/licensing.md):\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_sees_the_banned_text(tmp_path):
    """The patterns catch every banned context, spelling and phrase."""
    hits = _sample_violations(tmp_path)
    banned_files = {"spdx.py", "dunder.py", "pyproject.toml", "legacy.toml", "recipe.yaml",
                    "boilerplate.py", "orange3.py", "orange_path.py", "ljubljana.py"}
    seen_files = {hit.split(":", 1)[0] for hit in hits}
    assert seen_files == banned_files, f"missed: {sorted(banned_files - seen_files)}"


def test_sanctioned_remnants_pass(tmp_path):
    """LGPL mentions, attribution prose, colour names and the VizRank citation pass."""
    assert not _sample_clean(tmp_path), "the guard trips on sanctioned text"


if __name__ == "__main__":
    failures = 0
    tree_hits = _check_tree()
    print(f"dry run: scanned {len(_scan_files())} source files in chisurf/ and modules/ndxplorer/")
    if tree_hits:
        failures += 1
        print("FAIL live tree:")
        print("\n".join(f"  {hit}" for hit in tree_hits))
    else:
        print("PASS live tree: no GPL licence strings, no Orange provenance")
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        banned_hits = _sample_violations(pathlib.Path(tmp_a))
        clean_hits = _sample_clean(pathlib.Path(tmp_b))
    expected = {"spdx.py", "dunder.py", "pyproject.toml", "legacy.toml", "recipe.yaml",
                "boilerplate.py", "orange3.py", "orange_path.py", "ljubljana.py"}
    if {hit.split(":", 1)[0] for hit in banned_hits} != expected:
        failures += 1
        print(f"FAIL detection self-check: {banned_hits}")
    else:
        print(f"PASS detection self-check: all {len(expected)} banned contexts caught")
    if clean_hits:
        failures += 1
        print(f"FAIL sanctioned self-check: {clean_hits}")
    else:
        print("PASS sanctioned self-check: LGPL/attribution/colour/citation pass")
    sys.exit(1 if failures else 0)
