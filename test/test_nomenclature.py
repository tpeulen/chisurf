"""Guard: retired nomenclature does not come back.

**The rule:** detectors are named ``<emission>|<excitation>`` (``G|G``, ``R|G``,
``R|R``); a background rate is ``Bg_<detector>`` in kHz; polarisation channels
are ``VV`` / ``VH``; a detector's lifetime / anisotropy is named after it
(``Tau (G|G)``, ``r (R|R)``); ranges are written ``a:b``; the G factor is per
detection colour (``G (G|G)``); there is no HDF5. The retired spellings -- the
``green``/``red`` detector names, ``Bg``/``Br``/``By``/``B_<det>``/``n_bg``,
``par``/``perp`` and the parallel / perpendicular signs, ``a-b`` ranges,
HDF5 -- are what :mod:`build_tools.dev_utils.nomenclature_audit` finds, by
area: ``chisurf/``, ndX's ``ndxplorer/``, view specs, settings, shipped help,
``docs/`` and ``okf/``. Tests are not scanned: they document the old names they
migrate.

``test/nomenclature_allowlist.txt`` is a **shrinking** record, ``rule path
count  # reason``, of what was not fixed when the rule came in. It is never
somewhere to add yourself: a new hit fails, and so does a file whose count went
down without its line being lowered (or struck). A line that is a deliberate
exception (a read-side rename of old data, a third-party format) says so.
A single line that has to name a retired spelling can carry ``nomenclature: ok``.
"""

from __future__ import annotations

import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ALLOWLIST = _ROOT / "test" / "nomenclature_allowlist.txt"


def _load_allowlist() -> dict:
    """``{(rule, path): count}`` from the allow-list."""
    out = {}
    for line in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
        body = line.split("#", 1)[0].strip()
        if not body:
            continue
        rule, path, count = body.split()
        out[(rule, path)] = int(count)
    return out


@pytest.fixture(scope="module")
def current() -> dict:
    """``{(rule, path): count}`` of the tree as it is."""
    from build_tools.dev_utils import nomenclature_audit as audit

    if not audit.NDX.exists():
        pytest.skip("modules/ndxplorer is not checked out")
    return {(rule, path): n for (path, rule), n in audit.per_file(audit.scan()).items()}


def test_no_new_retired_names(current):
    """No file has a retired term the allow-list does not hold, nor more of them."""
    allowed = _load_allowlist()
    new = sorted(f"{rule:<19} {path}  {n} (allowed {allowed.get((rule, path), 0)})"
                 for (rule, path), n in current.items() if n > allowed.get((rule, path), 0))
    assert not new, (
        "Retired nomenclature (G|G detector names, Bg_<detector>, VV/VH, Tau (G|G), a:b ranges, "
        "no HDF5) -- see `python -m build_tools.dev_utils.nomenclature_audit --hits`:\n  "
        + "\n  ".join(new))


def test_nomenclature_allowlist_shrinks(current):
    """Every allow-listed count is still reached: a cleaned file is lowered or struck."""
    stale = sorted(f"{rule:<19} {path}  now {current.get((rule, path), 0)} (listed {n})"
                   for (rule, path), n in _load_allowlist().items()
                   if current.get((rule, path), 0) < n)
    assert not stale, ("Lower or strike these lines of test/nomenclature_allowlist.txt:\n  "
                       + "\n  ".join(stale))
