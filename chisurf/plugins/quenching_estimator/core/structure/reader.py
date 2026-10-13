import locale
import os
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
#: `residue_index` is assigned here, one per distinct
#: ``(chain, res_id, insertion_code)`` in the order the reader returns atoms. Group on it; report
#: `chain`/`res_id`/`insertion_code` to a human.
keys = [
    "i",
    "chain",
    "res_id",
    "insertion_code",
    "residue_index",
    "res_name",
    "atom_id",
    "atom_name",
    "element",
    "coord",
    "charge",
    "radius",
    "bfactor",
    "mass",
]

formats = ["i4", "|U1", "i4", "|U1", "i4", "|U5", "i4", "|U5", "|U1", "3f8", "f8", "f8", "f8", "f8"]


def sequence(structure, use_atoms=False):
    """
    ParseModel the SEQRES entries in a pdb file.  If this fails, use the ATOM
    entries.  Return dictionary of sequences keyed to chain and type of
    sequence used.
    :param structure: a `Structure` object
    :param use_atoms: boolean
    """
    # Try using SEQRES
    pdb = open(structure.filename).readlines()
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
            pdb = pdb[models[0] : models[1]]
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
    mode = "a+" if append else "w+"
    if atoms is not None:
        fp = open(filename, mode)
        # http://cupnet.net/pdb_format/
        al = [
            "%-6s%5d %4s%1s%3s %1s%4d%1s   %8.3f%8.3f%8.3f%6.2f%6.2f          %2s%2s\n"
            % (
                "ATOM ",
                at["atom_id"],
                at["atom_name"],
                " ",
                at["res_name"],
                at["chain"],
                at["res_id"],
                " ",
                at["coord"][0],
                at["coord"][1],
                at["coord"][2],
                0.0,
                at["bfactor"],
                at["element"],
                "  ",
            )
            for at in atoms
        ]
        if mode == "a+":
            fp.write("MODEL")
        fp.write("".join(al))
        if mode == "a+":
            fp.write("ENDMDL")
        fp.close()


#: One lock around the parse, and a cache so a scan running sites in a pool
#: parses each structure once instead of once per site.
_PARSE_LOCK = threading.Lock()
_PARSE_CACHE: dict[tuple, np.ndarray] = {}
_PARSE_CACHE_LIMIT = 8


def _cache_key(path: str):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (os.path.abspath(path), stat.st_mtime_ns, stat.st_size)


def read(filename, **kwargs):
    """Read a structure into QuEst's atom array, through IMP.bff's reader.

    Returns a NumPy structured array with the fields in :data:`keys`. PDB and
    mmCIF are both read by :func:`IMP.bff.parse_structure_table`, the IMP-free
    core's restatement of ``IMP::atom::read_pdb`` / ``read_mmcif`` with their
    default selector: the same atoms, in the same order (residues sorted by
    number within a chain), with IMP's element, mass and radius. QuEst carries
    no parser of its own for either format, and needs no IMP kernel.

    **The atom set is IMP's default**: everything except waters and alternate
    locations other than blank/``A``; only the first model. Ligands, cofactors
    and modified residues are steric obstacles like any other atom, because
    they physically are -- a dye cannot diffuse through a bound sugar. QuEst
    used to strip every HETATM record, which on 148L discarded 41 atoms of
    ``FGA``, ``API``, ``DAL``, ``MUB``, ``NAG`` and ``BME`` (1322 against 1363).

    Waters are deliberately *not* obstacles. Adding them costs **17 % of every
    accessible volume** on the 148l chain-E sites, and crystallographic solvent
    is mobile on the timescale a tethered dye explores -- treating it as a
    rigid wall is a stronger claim than the physics supports.

    As a defensive guarantee, :func:`_strip_waters` runs after the parse and
    removes every atom whose residue name identifies it as water (``HOH``,
    ``WAT``, ``TIP3``, ``SOL``, ...). The reader drops only ``HOH``/``DOD``;
    the explicit filter keeps QuEst correct for the other spellings.

    Raises
    ------
    ImportError
        If the installed IMP.bff predates :func:`IMP.bff.parse_structure_table`.
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
        atoms = _read_with_imp_bff(path)

    if key is not None:
        if len(_PARSE_CACHE) >= _PARSE_CACHE_LIMIT:
            _PARSE_CACHE.clear()
        _PARSE_CACHE[key] = atoms
    return atoms.copy()


#: Residue names that identify water molecules. Every common force field and
#: crystallographic convention is covered, so the filter does not depend on a
#: single parser's notion of "water".
_WATER_RESIDUE_NAMES = frozenset(
    {
        "HOH",
        "WAT",
        "TIP3",
        "TIP4",
        "TIP4P",
        "TIP",
        "SPC",
        "SPCM",
        "SOL",
        "DOD",
        "H2O",
        "OH2",
        "D2O",
    }
)


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

    The reader already drops ``HOH`` and ``DOD``, but relying on that alone
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


def _read_with_imp_bff(path):
    """Parse *path* into QuEst's atom array. Call under :data:`_PARSE_LOCK`."""
    import IMP.bff

    parse = getattr(IMP.bff, "parse_structure_table", None)
    if parse is None:
        raise ImportError(
            "QuEst reads structures with IMP.bff.parse_structure_table, which this "
            "IMP.bff does not have; update imp-bff (pixi install) to a build that does."
        )
    # Every atom IMP's default selector keeps, every residue (ligands too),
    # and the radius as IMP gives the particle -- R_min, not the zero-crossing.
    table = parse(
        path, keep_water=False, only_standard_residues=False, radius_no_interaction=False
    )
    n = int(table.n_atoms)
    atoms = np.zeros(n, dtype={"names": keys, "formats": formats})
    if n == 0:
        return atoms

    chain = np.asarray(table.chain, dtype=str)
    res_id = np.asarray(table.res_id, dtype=np.int64)
    insertion_code = np.asarray(table.insertion_code, dtype=str)

    # Distinct residues, in reader order. The reader reports chain, number and
    # insertion code; grouping on `res_id` alone is what merged chains.
    residue_indices: dict[tuple, int] = {}
    atoms["residue_index"] = [
        residue_indices.setdefault((c, int(r), i), len(residue_indices))
        for c, r, i in zip(chain.tolist(), res_id.tolist(), insertion_code.tolist())
    ]
    atoms["insertion_code"] = insertion_code
    atoms["i"] = np.arange(n)
    atoms["chain"] = chain
    atoms["res_id"] = res_id
    atoms["res_name"] = np.asarray(table.res_name, dtype=str)
    atoms["atom_id"] = np.arange(n)
    atoms["atom_name"] = np.asarray(table.atom_name, dtype=str)
    atoms["element"] = np.asarray(table.element, dtype=str)
    atoms["coord"] = np.asarray(table.xyz, dtype=np.float64).reshape(n, 3)
    atoms["bfactor"] = np.asarray(table.bfactor, dtype=np.float64)
    atoms["radius"] = np.asarray(table.radius, dtype=np.float64)
    atoms["mass"] = np.asarray(table.mass, dtype=np.float64)

    return _strip_waters(atoms)
