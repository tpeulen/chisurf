"""Regenerate ``elements.py`` from PyMOL's own periodic table.

Two tables, from two places, because PyMOL keeps them in two:

* ``modules/chempy/__init__.py::atomic_mass`` -- symbol to mass in daltons, with
  **every symbol listed twice**, cased (``He``) and upper (``HE``), because a
  PDB writes element symbols in either. That duplication is the useful part
  rather than noise: it is how PyMOL's own reader survives ``FE`` in a HETATM
  record, so the transcription keeps a case-insensitive lookup;
* ``layer2/AtomInfo.cpp::ElementTable`` -- the periodic table proper, carrying
  the **van der Waals radius** beside the weight. That is the radius PyMOL draws
  a sphere with and measures a surface with, so it is the one a viewer wants;
  its own comment records the fallback, "Default VDW radius is 1.80".

Run it against a PyMOL source checkout::

    python make_elements.py junk/pymol-open-source \\
        > ../../../../core/fio/structure/elements.py

The output is checked in under ``chisurf/core/fio/structure/`` -- the reader
needs it, and one table serves everyone -- so nothing needs PyMOL at runtime, and this script
exists so the transcription can be **redone and diffed** rather than trusted --
the same arrangement as ``make_space_groups.py``. ``test_elements.py`` verifies
the result's own properties, which is what catches a truncated extraction: a
partial table is self-consistent and passes every spot check that happens to
fall inside it, so the count is asserted alongside the values.
"""

from __future__ import annotations

import ast
import pathlib
import sys

HEADER = '''"""Atomic masses in daltons. **Generated -- do not edit by hand.**

Transcribed from PyMOL's ``modules/chempy/__init__.py::atomic_mass`` by
``analysis/make_elements.py``. PyMOL's values are the IUPAC standard atomic
weights, and taking them rather than an independent list is deliberate: a
molecular weight that disagrees with PyMOL's by a rounding convention is a
support question nobody can answer.

Lookup is **case-insensitive**, because a PDB element column is written both
``Fe`` and ``FE`` and a table that knows only one of them silently drops every
metal in half the files in the world.
"""

from __future__ import annotations

__all__ = ["ATOMIC_MASS", "VDW_RADIUS", "DEFAULT_VDW_RADIUS", "mass_of",
           "masses_for", "radius_of", "radii_for"]

'''

FOOTER = '''

def radius_of(symbol: str) -> float:
    """Van der Waals radius of one element in Angstrom.

    Unlike :func:`mass_of` this never returns ``None``: PyMOL's own table
    documents 1.80 as the fallback for an element it does not list, and a sphere
    has to be drawn at *some* size. A mass may be absent from a sum; a radius
    cannot be absent from a picture.
    """
    return VDW_RADIUS.get(str(symbol).strip().upper(), DEFAULT_VDW_RADIUS)


def mass_of(symbol: str) -> float | None:
    """Mass of one element in daltons, or ``None`` when it is not a symbol.

    Parameters
    ----------
    symbol : str
        Element symbol in any case, with or without surrounding blanks.

    Returns
    -------
    float or None
        ``None`` rather than a guess: an unknown symbol in a molecular weight
        has to be *reported*, not quietly counted as zero or as carbon.
    """
    return ATOMIC_MASS.get(str(symbol).strip().upper())


def radii_for(symbols) -> "numpy.ndarray":  # noqa: F821
    """Van der Waals radii for a sequence of symbols, vectorised over a cache."""
    import numpy as np

    cache: dict = {}
    values = np.empty(len(symbols), dtype=float)
    for index, symbol in enumerate(symbols):
        key = str(symbol).strip().upper()
        radius = cache.get(key)
        if radius is None:
            radius = cache[key] = VDW_RADIUS.get(key, DEFAULT_VDW_RADIUS)
        values[index] = radius
    return values


def masses_for(symbols) -> tuple["numpy.ndarray", int]:  # noqa: F821
    """Masses for a sequence of symbols, and how many were not recognised.

    Returns
    -------
    tuple
        ``(masses, unknown)``. Unknown symbols get ``0.0`` so array arithmetic
        still works, and the count is returned so the caller can say so --
        which is the whole point of not defaulting them to something plausible.
    """
    import numpy as np

    values = np.zeros(len(symbols), dtype=float)
    unknown = 0
    for index, symbol in enumerate(symbols):
        mass = mass_of(symbol)
        if mass is None:
            unknown += 1
        else:
            values[index] = mass
    return values, unknown
'''


def extract(root: pathlib.Path) -> dict[str, float]:
    """Read ``atomic_mass`` out of a PyMOL checkout.

    Parsed with :mod:`ast` rather than imported: ``chempy`` pulls in the rest of
    PyMOL, and a transcription that needs the reference *installed* is not a
    transcription.
    """
    source = (root / "modules" / "chempy" / "__init__.py").read_text(
        encoding="utf-8", errors="replace"
    )
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "atomic_mass" not in targets:
            continue
        table = ast.literal_eval(node.value)
        return {str(k).upper(): float(v) for k, v in table.items()}
    raise SystemExit("no `atomic_mass` in modules/chempy/__init__.py")


def extract_vdw(root: pathlib.Path) -> dict[str, float]:
    """Read ``ElementTable`` out of ``layer2/AtomInfo.cpp``.

    Parsed with a regular expression rather than a C parser: the table is a flat
    list of brace-delimited rows and anything cleverer would be more code than
    the data. A malformed row simply does not match, and the count assertion in
    the test is what catches that -- a partial table is otherwise
    indistinguishable from a complete one.
    """
    import re

    source = (root / "layer2" / "AtomInfo.cpp").read_text(
        encoding="utf-8", errors="replace"
    )
    body = source.split("const ElementTableItemType ElementTable[] = {", 1)
    if len(body) != 2:
        raise SystemExit("no `ElementTable` in layer2/AtomInfo.cpp")
    rows = re.findall(
        r'\{\s*"[^"]*"\s*,\s*"([A-Za-z]+)"\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\}',
        body[1].split("};", 1)[0],
    )
    return {symbol.upper(): float(vdw) for symbol, vdw, _weight in rows}


def render(masses: dict[str, float], vdw: dict[str, float]) -> str:
    lines = [HEADER, "ATOMIC_MASS: dict[str, float] = {"]
    for symbol in sorted(masses, key=lambda s: (len(s), s)):
        lines.append(f'    "{symbol}": {masses[symbol]!r},')
    lines.append("}")
    lines.append("")
    lines.append("#: Van der Waals radii in Angstrom, from PyMOL's ElementTable.")
    lines.append("#: 1.80 is its own documented fallback for an element not listed.")
    lines.append("DEFAULT_VDW_RADIUS: float = 1.80")
    lines.append("")
    lines.append("VDW_RADIUS: dict[str, float] = {")
    for symbol in sorted(vdw, key=lambda s: (len(s), s)):
        lines.append(f'    "{symbol}": {vdw[symbol]!r},')
    lines.append("}")
    lines.append(FOOTER)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.splitlines()[0], file=sys.stderr)
        print("usage: make_elements.py <pymol-source-root>", file=sys.stderr)
        return 2
    root = pathlib.Path(argv[1])
    print(render(extract(root), extract_vdw(root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
