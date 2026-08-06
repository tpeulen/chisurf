"""Regenerate ``elements.py`` from PyMOL's own atomic-mass table.

PyMOL keeps the masses in ``modules/chempy/__init__.py`` as ``atomic_mass``, a
dict from element symbol to mass in daltons, with **every symbol listed twice**
-- once cased (``He``) and once upper (``HE``) -- because a PDB writes element
symbols in either. That duplication is the useful part rather than noise: it is
how PyMOL's own reader survives ``FE`` in a HETATM record, so the transcription
keeps a case-insensitive lookup rather than assuming clean input.

Run it against a PyMOL source checkout::

    python make_elements.py junk/pymol-open-source > elements.py

The output is checked in so chimol needs no PyMOL at runtime, and this script
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

__all__ = ["ATOMIC_MASS", "mass_of", "masses_for"]

'''

FOOTER = '''

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


def render(masses: dict[str, float]) -> str:
    lines = [HEADER, "ATOMIC_MASS: dict[str, float] = {"]
    for symbol in sorted(masses, key=lambda s: (len(s), s)):
        lines.append(f'    "{symbol}": {masses[symbol]!r},')
    lines.append("}")
    lines.append(FOOTER)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.splitlines()[0], file=sys.stderr)
        print("usage: make_elements.py <pymol-source-root>", file=sys.stderr)
        return 2
    print(render(extract(pathlib.Path(argv[1]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
