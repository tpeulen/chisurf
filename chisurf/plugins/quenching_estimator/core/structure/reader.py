import os
import locale
import threading
from pathlib import Path

import numpy as np


#: ``residue_index`` is the residue's **identity**, and `res_id` is not.
#:
#: A PDB residue number restarts per chain and may carry an insertion code, so
#: `res_id` alone names different residues in a multi-chain structure -- on
#: `tests/data/mc4r_dimer.cif` every one of 534 ids appears in both chains.
#: Everything that groups atoms into residues used to key on `res_id`, which
#: merged them: chain B's residue 40 and chain A's residue 40 became one entry,
#: and the side chains of both folded into a single CB pseudo-atom.
#:
#: `residue_index` is assigned here, from IMP's hierarchy, one per distinct
#: ``(chain, res_id, insertion_code)`` in file order. Group on it; report
#: `chain`/`res_id`/`insertion_code` to a human.
keys = ['i', 'chain', 'res_id', 'insertion_code', 'residue_index', 'res_name',
        'atom_id', 'atom_name', 'element',
        'coord',
        'charge', 'radius', 'bfactor', 'mass']

formats = ['i4', '|U1', 'i4', '|U1', 'i4', '|U5',
           'i4', '|U5', '|U1',
           '3f8',
           'f8', 'f8', 'f8', 'f8']




def sequence(structure, use_atoms=False):
    """
    ParseModel the SEQRES entries in a pdb file.  If this fails, use the ATOM
    entries.  Return dictionary of sequences keyed to chain and type of
    sequence used.
    :param structure: a `Structure` object
    :param use_atoms: boolean
    """
    # Try using SEQRES
    pdb = open(structure.filename, 'r').readlines()
    # get residue-sequence
    seq = [l for l in pdb if l[0:6] == "SEQRES"]
    if len(seq) != 0 and not use_atoms:
        chain_dict = dict([(l[11], []) for l in seq])
        for c in list(chain_dict.keys()):
            chain_seq = [l[19:70].split() for l in seq if l[11] == c]
            for x in chain_seq:
                chain_dict[c].extend(x)
    else:
        # Check to see if there are multiple models.  If there are, only look
        # at the first model.
        models = [i for i, l in enumerate(pdb) if l.startswith("MODEL")]
        if len(models) > 1:
            pdb = pdb[models[0]:models[1]]
        atoms = [l for l in pdb if l[0:6] == "ATOM  " and l[13:16] == "CA "]
        chain_dict = dict([(l[21], []) for l in atoms])
        for c in list(chain_dict.keys()):
            chain_dict[c] = [l[17:20] for l in atoms if l[21] == c]
    return chain_dict












def write(filename, atoms=None, append=False):
    """
    Writes a structured numpy array containing the PDB-info to a
    PDB-file
    :param filename: target-filename
    :param atoms: structured numpy array
    """
    mode = 'a+' if append else 'w+'
    if atoms is not None:
        fp = open(filename, mode)
        # http://cupnet.net/pdb_format/
        al = ["%-6s%5d %4s%1s%3s %1s%4d%1s   %8.3f%8.3f%8.3f%6.2f%6.2f          %2s%2s\n" %
              ("ATOM ", at['atom_id'], at['atom_name'], " ", at['res_name'], at['chain'], at['res_id'], " ",
               at['coord'][0], at['coord'][1], at['coord'][2], 0.0, at['bfactor'], at['element'], "  ")
              for at in atoms
        ]
        if mode == 'a+':
            fp.write('MODEL')
        fp.write("".join(al))
        if mode == 'a+':
            fp.write('ENDMDL')
        fp.close()


#: IMP builds decorator objects through SWIG, which is not safe to do from
#: several threads at once — a scan running sites in a pool hit
#: "Wrong number or type of arguments for overloaded function 'new_Atom'".
#: One lock around the parse, and a cache so a scan parses each structure once
#: instead of once per site.
_PARSE_LOCK = threading.Lock()
_PARSE_CACHE: dict[tuple, np.ndarray] = {}
_PARSE_CACHE_LIMIT = 8


def _cache_key(path: str):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (os.path.abspath(path), stat.st_mtime_ns, stat.st_size)


def _atom_name(atom) -> str:
    """The atom's own name, with IMP's hetero-record prefix removed.

    IMP names atoms in HETATM records ``"HET: N  "``, ``"HET: C1 "`` and so on.
    The ``atom_name`` field is ``|U5``, so storing that verbatim truncates every
    one of them to the literal string ``"HET:"`` — every hetero atom ends up
    with the *same* name and its real one is lost. Nothing noticed while HETATM
    records were stripped at the door; admitting them
    (see :func:`read`) makes it matter, because atom names are how the quenching
    chemistry and the coarse-grain templates identify atoms.
    """
    name = atom.get_atom_type().get_string().strip()
    if name.startswith("HET:"):
        name = name[4:].strip()
    return name


def read(filename, **kwargs):
    """Read a structure into QuEst's atom array, using IMP as the parser.

    Returns a NumPy structured array with the fields in :data:`keys`. PDB and
    mmCIF are both handled by IMP (``IMP.atom.read_pdb`` / ``read_mmcif``);
    QuEst no longer carries its own parser for either.

    **No selector is passed, so IMP's default applies**: everything except
    waters and hydrogens. Ligands, cofactors and modified residues are steric
    obstacles like any other atom, because they physically are — a dye cannot
    diffuse through a bound sugar. QuEst used to strip every HETATM record,
    which on 148L discarded 41 atoms of ``FGA``, ``API``, ``DAL``, ``MUB``,
    ``NAG`` and ``BME`` (1322 against 1363).

    Waters are deliberately *not* obstacles. Adding them
    (``IMP.atom.NonHydrogenPDBSelector``, 1503 atoms) costs **17 % of every
    accessible volume** on the 148l chain-E sites, and crystallographic solvent
    is mobile on the timescale a tethered dye explores — treating it as a rigid
    wall is a stronger claim than the physics supports. Measured, not assumed:
    see [specs/structure-io.md](okf/specs/structure-io.md).

    As a defensive guarantee, :func:`_strip_waters` runs after the IMP parse and
    removes every atom whose residue name identifies it as water (``HOH``,
    ``WAT``, ``TIP3``, ``SOL``, …). IMP's selector already does this, but the
    explicit filter keeps QuEst correct regardless of which selector a caller
    or a future parser passes.

    Raises
    ------
    ImportError
        If IMP is unavailable. QuEst needs it for accessible volumes anyway.
    """
    verbose = kwargs.get("verbose", True)
    path = str(filename)
    if verbose:
        directory, base_name = os.path.split(path)
        print("======================================")
        print("Filename: %s" % path)
        print("Path: %s" % directory)

    key = _cache_key(path)
    if key is not None:
        cached = _PARSE_CACHE.get(key)
        if cached is not None:
            # A copy: callers treat the array as theirs to modify.
            return cached.copy()

    with _PARSE_LOCK:
        atoms = _read_with_imp(path)

    if key is not None:
        if len(_PARSE_CACHE) >= _PARSE_CACHE_LIMIT:
            _PARSE_CACHE.clear()
        _PARSE_CACHE[key] = atoms
    return atoms.copy()


#: Residue names that identify water molecules. Every common force field and
#: crystallographic convention is covered, so the filter does not depend on a
#: single parser's notion of "water".
_WATER_RESIDUE_NAMES = frozenset({
    "HOH", "WAT", "TIP3", "TIP4", "TIP4P", "TIP",
    "SPC", "SPCM", "SOL", "DOD", "H2O", "OH2", "D2O",
})


def strip_water_pdb_text(pdb_text: str) -> str:
    """Remove every ATOM/HETATM line whose residue name identifies it as water.

    This operates on raw PDB text, so it can clean a file *before* any viewer
    or parser sees it — the ChiMol 3D viewer deliberately keeps waters
    (``keep_water=True``), so stripping at the text level is the only point
    that covers every consumer. Column-based parsing follows the PDB spec:
    residue name is columns 18–20 (0-indexed 17:20).
    """
    kept = []
    for line in pdb_text.splitlines():
        if line.startswith(("ATOM  ", "HETATM")):
            res_name = line[17:20].strip().upper()
            if res_name in _WATER_RESIDUE_NAMES:
                continue
        kept.append(line)
    return "\n".join(kept) + "\n" if kept else ""


def water_stripped_pdb_path(source_path: str | os.PathLike) -> tuple[str, str]:
    """Return ``(temp_path, name)`` for a water-stripped copy of *source_path*.

    Reads the PDB file, removes water lines, and writes the result to a
    temporary file that is reused on repeated calls for the same source.
    The temp file is **not** deleted — it lives in the system temp directory
    and is overwritten on the next call for the same source.
    """
    import tempfile

    source = Path(source_path)
    text = source.read_text(encoding="utf-8", errors="replace")
    cleaned = strip_water_pdb_text(text)
    stem = source.stem
    fd, tmp = tempfile.mkstemp(prefix=f"{stem}_nowat_", suffix=source.suffix)
    with os.fdopen(fd, "w") as fh:
        fh.write(cleaned)
    return tmp, stem


def _strip_waters(atoms: np.ndarray) -> np.ndarray:
    """Remove every atom whose residue names it as water.

    IMP's default PDB selector already drops waters, but relying on that alone
    couples QuEst's correctness to an external library's default. This is the
    explicit, defensive guarantee that water is never a steric obstacle — a
    crystallographic solvent molecule is mobile on the timescale a tethered dye
    explores, and treating it as a rigid wall is a stronger claim than the
    physics supports.
    """
    if len(atoms) == 0:
        return atoms
    names = np.char.strip(atoms["res_name"].astype(str))
    upper = np.char.upper(names)
    mask = np.ones(len(atoms), dtype=bool)
    for water in _WATER_RESIDUE_NAMES:
        mask &= upper != water
    if mask.all():
        return atoms
    return atoms[mask].copy()


def _read_with_imp(path):
    """Parse *path* into QuEst's atom array. Call under :data:`_PARSE_LOCK`."""
    import IMP
    import IMP.atom
    import IMP.core

    model = IMP.Model()
    # No selector: IMP's default keeps everything but waters and hydrogens,
    # which is exactly the atom set QuEst wants. See :func:`read`.
    if path.lower().endswith((".cif", ".mmcif")):
        hierarchy = IMP.atom.read_mmcif(path, model)
    else:
        hierarchy = IMP.atom.read_pdb(path, model)

    leaves = IMP.atom.get_leaves(hierarchy)
    atoms = np.zeros(len(leaves), dtype={"names": keys, "formats": formats})
    element_table = IMP.atom.get_element_table()

    # Distinct residues, in file order. IMP already knows chain, number and
    # insertion code; QuEst threw that away and re-derived residues from
    # `res_id` alone, which is what merged chains.
    residue_indices: dict[tuple, int] = {}

    for index, leaf in enumerate(leaves):
        particle = leaf.get_particle()
        atom = IMP.atom.Atom(particle)
        residue = IMP.atom.Residue(IMP.atom.get_residue(atom))
        chain = IMP.atom.Chain(IMP.atom.get_chain(residue))
        element = element_table.get_name(atom.get_element())
        radius = IMP.core.XYZR(particle).get_radius()
        mass = IMP.atom.Mass(particle).get_mass()

        insertion_code = str(residue.get_insertion_code()).strip()
        residue_key = (str(chain.get_id()), int(residue.get_index()), insertion_code)
        atoms["residue_index"][index] = residue_indices.setdefault(
            residue_key, len(residue_indices)
        )
        atoms["insertion_code"][index] = insertion_code

        atoms["i"][index] = index
        atoms["chain"][index] = chain.get_id()
        atoms["res_id"][index] = residue.get_index()
        atoms["res_name"][index] = residue.get_residue_type().get_string()
        atoms["atom_id"][index] = index
        atoms["atom_name"][index] = _atom_name(atom)
        atoms["element"][index] = element
        atoms["coord"][index] = list(IMP.core.XYZ(particle).get_coordinates())
        atoms["bfactor"][index] = atom.get_temperature_factor()
        atoms["radius"][index] = radius
        atoms["mass"][index] = mass

    return _strip_waters(atoms)

