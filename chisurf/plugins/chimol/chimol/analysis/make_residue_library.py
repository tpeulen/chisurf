r"""Generate :mod:`~chimol.analysis.residue_library` from PyMOL's own data.

PyMOL builds a mutation out of two data files: a **fragment** -- one residue in
an idealised geometry, `data/chempy/fragments/<resn>.pkl` -- and a **rotamer
library**, `data/chempy/sidechains/sc_bb_ind.pkl`, which is a list of chi-angle
sets per residue with the frequency each is observed at. Neither is code, and
neither is something to re-derive: bond lengths and angles copied out of a
textbook by hand are how a built side chain ends up subtly wrong in a way
nobody notices until it is used for a distance.

So the data is transcribed, the way the space groups were: this script reads
the reference checkout and writes a plain-Python module. Run it when the
checkout is refreshed; the generated module is what ships.

    python -m chisurf.plugins.chimol.chimol.analysis.make_residue_library \\
        --checkout junk/pymol-open-source

Two deliberate narrowings:

* only the **twenty standard amino acids** are taken. PyMOL's fragment
  directory holds 131 files -- nucleotides, caps, protonation variants,
  acetylene -- and a mutation command that offers `argn` and `hip` without
  being able to say what they are is worse than one that offers twenty;
* only the **backbone-independent** rotamer library. The backbone-dependent one
  (`sc_bb_dep.pkl`, 1.4 MB over 3569 phi/psi bins) is the better science and
  the wizard's own default; it is not embedded because a 1.4 MB generated
  module is not a reasonable thing to ship for a feature nobody has asked to be
  phi/psi-aware yet. The reader is here (`--dependent`) for when it is.
"""

from __future__ import annotations

import argparse
import pathlib
import pickle
import sys

#: The twenty. PyMOL's fragment files are lower-case.
STANDARD = (
    "ala", "arg", "asn", "asp", "cys", "gln", "glu", "gly", "his", "ile",
    "leu", "lys", "met", "phe", "pro", "ser", "thr", "trp", "tyr", "val",
)

#: PyMOL's `_rot_type_xref` in the mutagenesis wizard: which rotamer set a
#: protonation variant borrows.
ROTAMER_ALIASES = {
    "GLUH": "GLU", "ASPH": "ASP", "ARGN": "ARG", "LYSN": "LYS",
    "HIP": "HIS", "HID": "HIS", "HIE": "HIS",
}


class _Stub:
    """Stand-in for a `chempy` class, so the pickles load without PyMOL."""

    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)


class _Unpickler(pickle.Unpickler):
    """Load a chempy pickle into plain objects."""

    def find_class(self, module, name):
        if module.startswith("chempy"):
            stub = type(name, (_Stub,), {})
            return stub
        return super().find_class(module, name)


def read_fragment(path: pathlib.Path) -> dict:
    """One residue's idealised geometry: atoms, elements, coordinates, bonds."""
    molecule = _Unpickler(path.open("rb")).load()
    atoms = getattr(molecule, "atom", [])
    bonds = getattr(molecule, "bond", [])
    return {
        "names": [str(a.__dict__.get("name", "")).strip() for a in atoms],
        "elements": [str(a.__dict__.get("symbol", "")).strip() for a in atoms],
        "coords": [
            [round(float(c), 4) for c in a.__dict__.get("coord", (0.0, 0.0, 0.0))]
            for a in atoms
        ],
        "bonds": [
            [int(b.__dict__["index"][0]), int(b.__dict__["index"][1]),
             int(b.__dict__.get("order", 1))]
            for b in bonds
        ],
    }


def read_rotamers(path: pathlib.Path) -> dict:
    """Read the rotamer library as ``{resn: [(freq, {(a,b,c,d): angle})]}``.

    Sorted by frequency, most common first, which is the order a chooser should
    offer them in and the order PyMOL's own panel lists.
    """
    raw = pickle.loads(path.read_bytes())
    out: dict[str, list] = {}
    for resn, rotamers in raw.items():
        entries = []
        for rotamer in rotamers:
            freq = float(rotamer.get("FREQ", 0.0))
            chis = {
                tuple(str(name) for name in key): round(float(value), 1)
                for key, value in rotamer.items()
                if isinstance(key, tuple)
            }
            entries.append((round(freq, 6), chis))
        entries.sort(key=lambda item: -item[0])
        out[str(resn).upper()] = entries
    return out


def render(fragments: dict, rotamers: dict) -> str:
    """Render the generated module's text."""
    lines = [
        '"""Idealised residue geometry and rotamers -- **generated, do not edit**.',
        "",
        "Written by :mod:`~chimol.analysis.make_residue_library` from PyMOL's own",
        "`data/chempy/fragments/*.pkl` and `data/chempy/sidechains/sc_bb_ind.pkl`.",
        "",
        "`FRAGMENTS[resn]` is one residue in an idealised geometry: atom names,",
        "elements, coordinates and bonds. `ROTAMERS[resn]` is the chi-angle sets",
        "that residue is observed in, most frequent first, each keyed by the four",
        "atom names whose dihedral it sets.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "__all__ = [\"FRAGMENTS\", \"ROTAMERS\", \"ROTAMER_ALIASES\"]",
        "",
        "#: Which rotamer set a protonation variant borrows -- PyMOL's",
        "#: `_rot_type_xref`.",
        f"ROTAMER_ALIASES = {ROTAMER_ALIASES!r}",
        "",
        "FRAGMENTS: dict[str, dict] = {",
    ]
    for resn in sorted(fragments):
        frag = fragments[resn]
        lines.append(f"    {resn!r}: {{")
        lines.append(f"        'names': {frag['names']!r},")
        lines.append(f"        'elements': {frag['elements']!r},")
        lines.append("        'coords': [")
        for xyz in frag["coords"]:
            lines.append(f"            {xyz!r},")
        lines.append("        ],")
        lines.append(f"        'bonds': {frag['bonds']!r},")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    lines.append("ROTAMERS: dict[str, list] = {")
    for resn in sorted(rotamers):
        lines.append(f"    {resn!r}: [")
        for freq, chis in rotamers[resn]:
            lines.append(f"        ({freq!r}, {chis!r}),")
        lines.append("    ],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Read the reference data and write the generated module."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--checkout", default="junk/pymol-open-source",
        help="the PyMOL reference checkout",
    )
    parser.add_argument(
        "--out",
        default=str(pathlib.Path(__file__).with_name("residue_library.py")),
        help="where to write the generated module",
    )
    parser.add_argument(
        "--dependent", action="store_true",
        help="read the backbone-dependent library instead (not embedded by default)",
    )
    args = parser.parse_args(argv)

    root = pathlib.Path(args.checkout)
    frag_dir = root / "data" / "chempy" / "fragments"
    side_dir = root / "data" / "chempy" / "sidechains"
    if not frag_dir.is_dir() or not side_dir.is_dir():
        print(f"no chempy data under {root}", file=sys.stderr)
        return 2

    fragments = {}
    for stem in STANDARD:
        path = frag_dir / f"{stem}.pkl"
        if not path.is_file():
            print(f"missing fragment: {path}", file=sys.stderr)
            continue
        fragments[stem.upper()] = read_fragment(path)

    name = "sc_bb_dep.pkl" if args.dependent else "sc_bb_ind.pkl"
    rotamers = read_rotamers(side_dir / name)

    out = pathlib.Path(args.out)
    out.write_text(render(fragments, rotamers), encoding="utf-8")
    print(
        f"wrote {out} -- {len(fragments)} fragments, "
        f"{sum(len(v) for v in rotamers.values())} rotamers over {len(rotamers)} residues"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
