"""Regenerate ``space_groups.py`` from PyMOL's own table.

PyMOL keeps the space-group operators in ``modules/pymol/xray.py`` as ``sym_base``
-- a dict from a *tuple of operator strings* to the list of names that share those
operators -- plus ``space_group_map``, an alias table for alternative spellings.
That is the authoritative source: it encodes the International Tables settings
PyMOL actually uses, so transcribing it is what makes chimol agree with PyMOL
rather than approximately agree.

Run it against a PyMOL source checkout::

    python make_space_groups.py junk/pymol-open-source > space_groups.py

The output is checked into the tree so chimol needs no PyMOL at runtime, and this
script exists so the transcription can be redone and diffed rather than trusted.
The generated table is verified mathematically by ``test_symmetry.py`` -- closure,
proper rotations, one identity -- which is what catches a bad extraction.
"""

from __future__ import annotations

import pathlib
import sys

HEADER = '''"""Space-group symmetry operators. **Generated -- do not edit by hand.**

Transcribed from PyMOL's ``modules/pymol/xray.py`` (``sym_base`` and
``space_group_map``) by ``make_space_groups.py``, which is checked in beside this
file. PyMOL's table is the authoritative one: it encodes the International Tables
settings PyMOL uses, so sharing it is what makes chimol's symmetry mates agree
with PyMOL's rather than approximately agree.

No crystallography library is a dependency here -- neither ``gemmi`` nor
``spglib`` nor ``cctbx`` -- which is why the data is carried rather than computed.
Every entry is checked mathematically by ``test_symmetry.py``: the operators of
each group must be closed under composition modulo lattice translations, every
rotation must be a proper rotation, and there must be exactly one identity. A bad
extraction fails those tests rather than producing plausible mates in the wrong
place.

{counts}
"""

from __future__ import annotations

__all__ = ["SPACE_GROUP_ALIASES", "SPACE_GROUP_OPERATORS", "lookup_operators"]


def _normalise(name: str) -> str:
    """Collapse the spellings of a space-group name to one key.

    PyMOL's ``sg_canonicalize`` upper-cases, collapses runs of whitespace, and
    then consults its alias map. Keys here have whitespace removed entirely, so
    ``P 21 21 21`` and ``P212121`` are the same key without needing both spellings
    in the table -- though PyMOL's own table lists many of them anyway.
    """
    return "".join(str(name).upper().split())


def lookup_operators(name: str) -> tuple[str, ...] | None:
    """Operators for a space group, or None when the name is not known.

    Aliases are followed first, then the name itself, so both a conventional
    symbol and PyMOL's alternative spelling resolve.
    """
    key = _normalise(name)
    alias = SPACE_GROUP_ALIASES.get(key)
    if alias is not None:
        resolved = SPACE_GROUP_OPERATORS.get(_normalise(alias))
        if resolved is not None:
            return resolved
    return SPACE_GROUP_OPERATORS.get(key)

'''


def main(pymol_root: str) -> int:
    """Write the generated module to stdout."""
    source = (
        pathlib.Path(pymol_root) / "modules" / "pymol" / "xray.py"
    ).read_text()
    namespace: dict = {}
    exec(compile(source, "xray.py", "exec"), namespace)  # noqa: S102
    sym_dict = namespace["sym_dict"]
    alias_map = namespace["space_group_map"]

    def normalise(name: str) -> str:
        return "".join(str(name).upper().split())

    operators: dict[str, tuple[str, ...]] = {}
    for name, ops in sym_dict.items():
        key = normalise(name)
        if not key:
            continue
        operators[key] = tuple(op.replace(" ", "") for op in ops)

    aliases = {
        normalise(k): v for k, v in alias_map.items() if normalise(k)
    }

    counts = (
        f"{len(operators)} space-group names over "
        f"{len({v for v in operators.values()})} distinct operator sets, "
        f"plus {len(aliases)} aliases."
    )
    out = [HEADER.format(counts=counts)]

    out.append("#: Alternative spellings PyMOL maps to a canonical name.")
    out.append("SPACE_GROUP_ALIASES: dict[str, str] = {")
    for key in sorted(aliases):
        out.append(f"    {key!r}: {aliases[key]!r},")
    out.append("}")
    out.append("")
    out.append("#: Normalised space-group name -> its symmetry operators.")
    out.append("SPACE_GROUP_OPERATORS: dict[str, tuple[str, ...]] = {")
    for key in sorted(operators):
        ops = operators[key]
        if len(ops) == 1:
            out.append(f"    {key!r}: ({ops[0]!r},),")
        else:
            out.append(f"    {key!r}: (")
            for op in ops:
                out.append(f"        {op!r},")
            out.append("    ),")
    out.append("}")
    out.append("")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
