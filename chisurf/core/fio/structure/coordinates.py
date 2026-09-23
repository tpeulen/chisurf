"""Read PDB files.

PDB files contain atomic coordinates.

`PDB <http://www.wwpdb.org/documentation/file-format>`_

:Author:
  `Thomas-Otavio Peulen <http://tpeulen.github.io>`_

Requirements
------------


Revisions
---------

Notes
-----
The API is not stable yet and might change between revisions.

References
----------

Examples
--------

"""

from __future__ import annotations

import logging
import os
import urllib.request

import numpy as np

import chisurf as cs
import chisurf.core.fio as io
import chisurf.core.support.common

from . import elements

logger = logging.getLogger(__name__)

# No `import IMP` here, and none anywhere in chisurf. Reading a structure well
# means IMP's readers -- its selectors, its element table, the CHARMM topology
# that decides how big an atom is -- but chisurf reaches them through
# ``IMP.bff.read_structure_table``, which is a **flat table of columns** and
# names no IMP type. imp.bff links IMP as a private C++ library, so the door
# works in a Python where ``import IMP.atom`` fails; and the walk out of the
# hierarchy happens in C++ rather than costing ~100 us per atom of SWIG
# traffic on this side. See ``okf/references/imp-ecosystem.md``.


def _bff():
    """Return ``IMP.bff``, imported on first use.

    Returns
    -------
    module
        The ``IMP.bff`` module.

    Raises
    ------
    ImportError
        With the reason, when the installed build has no structure door --
        the IMP-free wheel is one, and it says so rather than failing later
        on a missing attribute.

    Notes
    -----
    Lazy because ``import chisurf.core.fio.structure`` must stay cheap:
    ``IMP.bff`` pulls a large native stack in, and most of what imports this
    module never reads a structure.
    """
    import IMP.bff as bff

    if not hasattr(bff, "read_structure_table"):
        build = getattr(bff, "get_build", lambda: "?")()
        raise ImportError(
            f"this IMP.bff (build {build!r}) has no read_structure_table. "
            "Either it predates the function and needs rebuilding, or it is "
            "a build with no IMP linked, where CHARMM radii and mmCIF are "
            "not available at all. For a PDB, radii='vdw' reads it here and "
            "needs nothing from IMP.bff."
        )
    return bff


def write_pdb(
    filename: str,
    atoms=None,
    append_model: bool = False,
    append_coordinates: bool = False,
    verbose: bool = False,
    model_serial: int | None = None,
):
    """Writes a structured numpy array containing the PDB-info to a PDB-file

    If append_model and append_coordinates are False the file is overwritten. Otherwise the atomic-coordinates
    are appended to the existing file.


    :param filename: target-filename
    :param atoms: structured numpy array
    :param append_model: bool
        If True the atoms are appended as a new models
    :param append_coordinates:
        If True the coordinates are appended to the file
    :param model_serial:
        Wrap the atoms in ``MODEL <serial>`` / ``ENDMDL`` records. Needed for
        every frame of a multi-model file, the first included; the file is
        still overwritten unless an append flag is set.

    """
    mode = "a+" if append_model or append_coordinates else "w"
    if verbose:
        print("Writing to file: ", filename)

    # A PDB file has exactly one column for the chain, and `%1s` is a *minimum*
    # width in Python -- it does not truncate. A two-character chain id written
    # through it shifts every column after it, which turns the whole file into
    # something no reader parses correctly. The format simply cannot represent
    # these ids, so say so rather than emitting a corrupt file or dropping the
    # distinction in silence; mmCIF is the format that can.
    if atoms is not None and len(atoms):
        try:
            long_chains = sorted({c for c in np.asarray(atoms["chain"]).astype(str) if len(c) > 1})
        except Exception:
            long_chains = []
        if long_chains:
            logger.warning(
                "%s: %d chain identifier(s) are longer than the single column a "
                "PDB file has and are truncated to their first character (%s%s). "
                "Chains that differ only after the first character become "
                "indistinguishable -- write mmCIF to keep them.",
                filename,
                len(long_chains),
                ", ".join(long_chains[:5]),
                ", ..." if len(long_chains) > 5 else "",
            )

    with io.zipped.open_maybe_zipped(filename=filename, mode=mode) as fp:
        # http://cupnet.net/pdb_format/
        # `%1.1s` for the chain, not `%1s`: the precision is what truncates, and
        # without it a wider chain id silently shifts every following column.
        al = [
            "%-6s%5d %4s%1s%3s %1.1s%4d%1s   %8.3f%8.3f%8.3f%6.2f%6.2f          %2s%2s\n"
            % (
                "ATOM ",
                at["atom_id"],
                at["atom_name"],
                " ",
                at["res_name"],
                at["chain"],
                at["res_id"],
                " ",
                at["xyz"][0],
                at["xyz"][1],
                at["xyz"][2],
                0.0,
                at["bfactor"],
                at["element"],
                "  ",
            )
            for at in atoms
        ]
        # MODEL/ENDMDL are records of their own: without the newlines and the
        # serial they fused with the neighbouring ATOM lines and no reader
        # could split the models again.
        wrap = model_serial is not None or append_model
        if wrap:
            fp.write("MODEL     %4d\n" % (model_serial if model_serial is not None else 0))
        fp.write("".join(al))
        if wrap:
            fp.write("ENDMDL\n")


#: The atom row every reader produces. **chimol owns it** (`chimol.io.atoms.ATOM_DTYPE`)
#: and this module re-exports it: chimol has to parse a PDB without chisurf on
#: the path, and two transcriptions of the same twelve fields is how the copies
#: drift -- a structured array does not complain when a field is too narrow, it
#: truncates, silently, and the loss looks like the file. The chimol test suite
#: asserts the two names are the *same object* (`test_engine_is_portable.py`).
from chimol.io.atoms import ATOM_DTYPE as atom_dtype  # noqa: E402

keys = tuple(atom_dtype.names)


def _format_of(name: str) -> str:
    """The dtype spelling ``np.dtype({'names':..,'formats':..})`` accepts."""
    dt = atom_dtype.fields[name][0]
    if dt.subdtype is not None:
        base, shape = dt.subdtype
        return f"{shape[0]}{base.str[1:]}"  # ('<f8', (3,)) -> '3f8'
    return dt.str.lstrip("<>|=")  # '<U4' -> 'U4', '<i4' -> 'i4'


formats = tuple(_format_of(name) for name in keys)
keys_formats = list(zip(keys, formats))


_STANDARD_RESIDUES = {
    "ALA",
    "ARG",
    "ASN",
    "ASP",
    "CYS",
    "GLN",
    "GLU",
    "GLY",
    "HIS",
    "ILE",
    "LEU",
    "LYS",
    "MET",
    "PHE",
    "PRO",
    "SER",
    "THR",
    "TRP",
    "TYR",
    "VAL",
    "SEC",
    "PYL",
    # Nucleic acid residues (DNA/RNA)
    "DA",
    "DC",
    "DG",
    "DT",  # Deoxyribonucleotides
    "A",
    "C",
    "G",
    "T",
    "U",  # Ribonucleotides
    # Modified nucleic acid residues
    "2DA",
    "2DC",
    "2DG",
    "2DT",  # Modified deoxyribonucleotides
    "1MA",
    "1MG",
    "1MC",
    "1MT",  # Other modified nucleotides
    "M2G",
    "OMG",
    "OMC",
    "H2U",  # Common RNA modifications
    "PSU",
    "5MC",
    "7MG",
    "I",  # More modifications
}


def find_atom_index(
    atoms: np.array,
    chain_identifier: str,
    residue_seq_number: int,
    atom_name: str,
    residue_name: str,
    verbose: bool = False,
    ignore_multiple_selections: bool = True,
):
    """
    Find the index of an atom by a set of identifiers

    :param atoms:
    :param chain_identifier:
    :param residue_seq_number:
    :param atom_name:
    :param residue_name:
    :param ignore_multiple_selections:
    :param verbose:
    :return:
    """
    # Determine Labeling position
    if residue_seq_number is None or atom_name is None:
        raise ValueError(
            "Either attachment_atom number or residue number and atom_name need to be provided."
        )
    if verbose:
        print("find_atom_index:")
        print(f"-- Chain ID: {chain_identifier}")
        print(f"-- Residue seq. number: {residue_seq_number}")
        print(f"-- Residue name: {residue_name}")
        print(f"-- Atom name: {atom_name}")
    if chain_identifier is None or chain_identifier == "":
        attachment_atom_index = np.where(
            (atoms["res_id"] == residue_seq_number) & (atoms["atom_name"] == atom_name)
        )[0]
        if verbose:
            print(
                f"-- WARNING no chain specified. Possible attachment atoms: {attachment_atom_index: }"
            )
    else:
        attachment_atom_index = np.where(
            (atoms["res_id"] == residue_seq_number)
            & (atoms["atom_name"] == atom_name)
            & (atoms["chain"] == chain_identifier)
        )[0]
    if len(attachment_atom_index) != 1 and not ignore_multiple_selections:
        print("Search atom index:")
        print(f"-- Chain ID: {chain_identifier}")
        print(f"-- Residue seq. number: {residue_seq_number}")
        print(f"-- Residue name: {residue_name}")
        print(f"-- Atom name: {atom_name}")
        raise ValueError("Invalid selection of attachment atom")
    else:
        attachment_atom_index = attachment_atom_index[0]
    if verbose:
        print(f"Atom index: {attachment_atom_index}")
    return attachment_atom_index


get_atom_index = find_atom_index


def fetch_pdb_string(pdb_id: str) -> str:
    """Downloads from the RCSB a PDB file with the specified PDB-ID

    :param pdb_id: The PDB-ID that is downloaded
    :param get_binary: If get_binary is True a binary string is returned.
    :return:
    """
    url = f"http://www.rcsb.org/pdb/files/{pdb_id[:4]}.pdb"
    binary = urllib.request.urlopen(url).read()
    return binary.decode("utf-8")


def fetch_pdb(pdb_id: str, **kwargs):
    """Download a PDB file from RCSB and parse it.

    Parameters
    ----------
    pdb_id : str
        Four-character PDB identifier.
    **kwargs
        Passed to parse_string_pdb.

    Returns
    -------
    np.ndarray
        Structured array with atom information.
    """
    st = fetch_pdb_string(pdb_id)
    return parse_string_pdb(st, **kwargs)


def assign_element_to_atom_name(atom_name: str):
    """Tries to guess element from atom name if not recognised.

    :param atom_name: string

    Examples
    --------

    >>> assign_element_to_atom_name('CA')
    'C'
    """
    element = atom_name
    if atom_name.upper() not in chisurf.core.support.common.atom_weights:
        # Inorganic elements have their name shifted left by one position
        #  (is a convention in PDB, but not part of the standard).
        # isdigit() check on last two characters to avoid mis-assignment of
        # hydrogens atoms (GLN HE21 for example)
        # Hs may have digit in [0]
        putative_element = atom_name[1] if atom_name[0].isdigit() else atom_name[0]
        if putative_element.capitalize() in chisurf.core.support.common.atom_weights.keys():
            element = putative_element
    return element


def parse_string_pdb(
    string: str,
    assign_charge: bool = False,
    verbose: bool = cs.core.settings.cs_settings["verbose"],
):
    """

    :param string:
    :param assign_charge:
    :param verbose:
    :return:
    """
    rows = string.splitlines()
    atoms = np.zeros(len(rows), dtype={"names": keys, "formats": formats})
    ni = 0
    for line in rows:
        if verbose:
            print(line)
        if line.startswith("ATOM"):
            atom_name = line[12:16].strip().upper()
            atoms["i"][ni] = ni
            atoms["chain"][ni] = line[21]
            atoms["res_name"][ni] = line[17:20].strip().upper()
            atoms["atom_name"][ni] = atom_name
            atoms["res_id"][ni] = line[22:26]
            atoms["atom_id"][ni] = line[6:11]
            atoms["xyz"][ni][0] = line[30:38]
            atoms["xyz"][ni][1] = line[38:46]
            atoms["xyz"][ni][2] = line[46:54]
            atoms["bfactor"][ni] = line[60:65]
            atoms["element"][ni] = assign_element_to_atom_name(atom_name)
            try:
                if assign_charge:
                    if atoms["res_name"][ni] in chisurf.core.support.common.CHARGE_DICT:
                        if (
                            atoms["atom_name"][ni]
                            == chisurf.core.support.common.TITR_ATOM_COARSE[atoms["res_name"][ni]]
                        ):
                            atoms["charge"][ni] = chisurf.core.support.common.CHARGE_DICT[
                                atoms["res_name"][ni]
                            ]
                atoms["mass"][ni] = chisurf.core.support.common.atom_weights[atoms["element"][ni]]
                atoms["radius"][ni] = chisurf.core.support.common.VDW_DICT[atoms["element"][ni]]
            except KeyError:
                print(f"Cloud not assign parameters to: {line}")
            ni += 1
    atoms = atoms[:ni]
    if verbose:
        print("Number of atoms: %s" % (ni + 1))
    return atoms


def parse_string_pqr(string: str, verbose: bool = cs.core.settings.cs_settings["verbose"]):
    """Parse a PQR format string into a structured atom array.

    Parameters
    ----------
    string : str
        PQR file content as a single string.
    verbose : bool
        If True, print progress.

    Returns
    -------
    np.ndarray
        Structured array with atom information including charges and radii.
    """
    rows = string.splitlines()
    atoms = np.zeros(len(rows), dtype={"names": keys, "formats": formats})
    ni = 0
    for line in rows:
        if line.startswith("ATOM"):
            atom_name = line[12:16].strip().upper()
            atoms["i"][ni] = ni
            atoms["chain"][ni] = line[21]
            atoms["atom_name"][ni] = atom_name.upper()
            atoms["res_name"][ni] = line[17:20].strip().upper()
            atoms["res_id"][ni] = line[21:27]
            atoms["atom_id"][ni] = line[6:11]
            atoms["xyz"][ni][0] = float(line[30:38].strip())
            atoms["xyz"][ni][1] = float(line[38:46].strip())
            atoms["xyz"][ni][2] = float(line[46:54].strip())
            atoms["radius"][ni] = float(line[63:70].strip())
            atoms["element"][ni] = assign_element_to_atom_name(atom_name)
            atoms["charge"][ni] = float(line[55:62].strip())
            atoms["element"][ni] = assign_element_to_atom_name(atom_name)
            try:
                atoms["mass"][ni] = chisurf.core.support.common.atom_weights[atoms["element"][ni]]
            except KeyError:
                print(f"Cloud not assign parameters to: {line}")
            ni += 1
    atoms = atoms[:ni]
    if verbose:
        print("Number of atoms: %s" % (ni + 1))
    return atoms


def _table_to_atoms(table) -> np.ndarray:
    """Build the atom record array from an ``IMP.bff.StructureTable``.

    Parameters
    ----------
    table : IMP.bff.StructureTable
        The columns ``read_structure_table`` filled.

    Returns
    -------
    numpy.ndarray
        The structured array :func:`read_coordinates` returns.

    Notes
    -----
    Column by column, never atom by atom. The record array is the only place
    the two representations meet, and every field is assigned as a whole
    slice, so nothing here scales with a per-atom Python call.
    """
    n = int(table.n_atoms)
    atoms = np.zeros(n, dtype=atom_dtype)
    if n == 0:
        return atoms
    atoms["i"] = np.arange(n, dtype=np.int32)
    atoms["xyz"] = table.xyz
    atoms["radius"] = table.radius
    atoms["mass"] = table.mass
    atoms["bfactor"] = table.bfactor
    atoms["atom_id"] = table.atom_id
    atoms["res_id"] = table.res_id
    atoms["chain"] = table.chain
    atoms["res_name"] = table.res_name
    atoms["atom_name"] = table.atom_name
    atoms["element"] = table.element
    # IMP's readers assign no charge, and neither did the reader this
    # replaced; the field stays zero rather than carrying a guess.
    atoms["charge"] = 0.0
    return atoms


#: PDB column slices, from the format specification. Fixed columns rather than
#: whitespace splitting because a PDB is a **fixed-column** format: residue
#: names run into chain ids, atom names are padded on the left by their element,
#: and a file with a blank chain (which is most of them) has no whitespace there
#: to split on at all.
_PDB_COLUMNS = {
    "atom_id": (6, 11),
    "atom_name": (12, 16),
    "alt_loc": (16, 17),
    "res_name": (17, 20),
    "chain": (21, 22),
    "res_id": (22, 26),
    "x": (30, 38),
    "y": (38, 46),
    "z": (46, 54),
    "bfactor": (60, 66),
    "element": (76, 78),
}


def parse_pdb_native(
    filename: str,
    *,
    keep_water: bool = False,
    only_standard_residues: bool = True,
    keep_altloc: bool = True,
) -> np.ndarray:
    """Read a PDB into the atom array without IMP, by slicing columns.

    Parameters
    ----------
    filename : str
        Path to a ``.pdb``/``.ent`` file, optionally compressed.
    keep_water, only_standard_residues : bool
        As :func:`read_coordinates`.
    keep_altloc : bool
        Keep only the first alternate location of an atom, which is what PyMOL
        does. ``False`` keeps every one.

    Returns
    -------
    numpy.ndarray
        The same structured array :func:`read_coordinates` returns.

    Notes
    -----
    Written because the IMP path costs **~100 us per atom** and this costs
    ~0.7 us: on a 9315-atom structure, 0.96 s against 0.007 s. The profile said
    the parsing was never the expensive part -- ``IMP.atom.read_pdb`` is 0.079 s
    of that second -- so what this really removes is the per-atom SWIG traffic
    of walking IMP's hierarchy back out again.

    **The radii are not the same numbers.** IMP assigns a CHARMM ``Rmin``, which
    depends on the *atom type* (a carbon has seven distinct values in one
    structure); this assigns the element's van der Waals radius from PyMOL's own
    table. For a viewer that is the more correct quantity -- it is what PyMOL
    draws a sphere with and measures a surface with -- but it is a different
    quantity, so the modelling code that wants CHARMM radii must keep asking for
    the IMP path. That is why this is not silently the default everywhere.
    """
    with io.zipped.open_maybe_zipped(filename=filename, mode="r") as handle:
        raw = handle.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8", errors="replace")

    lines = [
        line
        for line in raw.split(b"\n")
        if line.startswith(b"ATOM  ") or line.startswith(b"HETATM")
    ]
    if not lines:
        return np.zeros(0, dtype=atom_dtype)

    width = max(len(line) for line in lines)
    block = np.frombuffer(b"".join(line.ljust(width) for line in lines), dtype="S1").reshape(
        len(lines), width
    )

    def column(name: str) -> np.ndarray:
        start, stop = _PDB_COLUMNS[name]
        stop = min(stop, width)
        if start >= width:
            return np.full(len(lines), b"", dtype="S1")
        return np.frombuffer(
            np.ascontiguousarray(block[:, start:stop]).tobytes(),
            dtype=f"S{stop - start}",
        )

    res_name = np.char.strip(column("res_name")).astype("U5")
    keep = np.ones(len(lines), dtype=bool)
    if not keep_water:
        keep &= ~np.isin(res_name, ["HOH", "WAT", "DOD", "TIP3", "SOL"])
    if only_standard_residues:
        keep &= np.isin(res_name, list(_STANDARD_RESIDUES))
    if keep_altloc:
        # PyMOL keeps the first alternate location and drops the rest; a blank
        # or "A" is the first. Keeping them all doubles those atoms and every
        # distance, area and bond inferred from them.
        alt = np.char.strip(column("alt_loc")).astype("U1")
        keep &= (alt == "") | (alt == "A") | (alt == "1")

    if not keep.any():
        return np.zeros(0, dtype=atom_dtype)
    index = np.nonzero(keep)[0]

    atoms = np.zeros(len(index), dtype=atom_dtype)
    atoms["i"] = np.arange(len(index))
    atoms["res_name"] = res_name[index]
    # Not stripped: a PDB's chain field is one character and a blank chain is a
    # real chain id -- IMP reports it as `" "`, and a selection written against
    # that must keep working. Stripping turned `" "` into `""` and every
    # `chain " "` matched nothing.
    atoms["chain"] = column("chain")[index].astype("U4")
    atoms["atom_name"] = np.char.strip(column("atom_name")[index]).astype("U5")
    atoms["xyz"] = np.column_stack(
        [
            column("x")[index].astype(float),
            column("y")[index].astype(float),
            column("z")[index].astype(float),
        ]
    )

    def integers(name: str) -> np.ndarray:
        text = np.char.strip(column(name)[index])
        blank = text == b""
        text = np.where(blank, b"0", text)
        try:
            return text.astype(np.int64)
        except ValueError:
            # A hybrid-36 serial past 99999, or a hexadecimal one: both appear
            # in files from real programs. Anything unreadable becomes 0 rather
            # than failing the whole read for a field nothing indexes on.
            out = np.zeros(len(text), dtype=np.int64)
            for position, value in enumerate(text):
                try:
                    out[position] = int(value)
                except ValueError:
                    out[position] = 0
            return out

    atoms["atom_id"] = integers("atom_id")
    atoms["res_id"] = integers("res_id")

    bfactor = np.char.strip(column("bfactor")[index])
    bfactor = np.where(bfactor == b"", b"0", bfactor)
    try:
        atoms["bfactor"] = bfactor.astype(float)
    except ValueError:
        atoms["bfactor"] = 0.0

    element = np.char.strip(column("element")[index]).astype("U2")
    # A file with no element column -- older entries, and anything written by a
    # program that skipped it -- leaves it blank, and PyMOL falls back to the
    # atom name. Guessing from the name is why `CA` is ambiguous (alpha carbon
    # or calcium), so the fallback takes the *first alphabetic character* only,
    # which is right for the organic elements that make up a protein and
    # deliberately does not try to be clever about metals.
    blank = element == ""
    if blank.any():
        names = atoms["atom_name"][blank]
        atoms["element"] = element
        derived = np.array(
            [next((c for c in str(n) if c.isalpha()), "") for n in names], dtype="U2"
        )
        element = element.copy()
        element[blank] = derived
    atoms["element"] = np.char.upper(element)

    masses, _unknown = elements.masses_for(atoms["element"])
    atoms["mass"] = masses
    atoms["radius"] = elements.radii_for(atoms["element"])
    atoms["charge"] = 0.0
    return atoms


def read_coordinates(
    filename: str,
    *,
    keep_water: bool = False,
    only_standard_residues: bool = True,
    radii: str = "charmm",
) -> np.ndarray:
    """Read atomic coordinates from a PDB or mmCIF file.

    Parameters
    ----------
    filename : str
        Path to the coordinate file.
    keep_water : bool
        Keep water molecules. The default drops them, which is what the
        modelling code wants; a viewer showing the deposited model wants them.
    only_standard_residues : bool
        Drop residues that are not standard amino acids or nucleotides
        (ligands, sugars, modified residues).
    radii : {"charmm", "vdw"}
        Which radius the ``radius`` field carries -- and with it **which reader
        runs**. ``"charmm"`` is IMP's per-atom-type ``Rmin``, which is what the
        modelling code wants (the accessible-volume simulation sizes its probes
        with it, and the clash term of a docking score measures overlap against
        the same numbers), so it stays the default and nothing existing
        changes; it comes from ``IMP.bff.read_structure_table``. ``"vdw"`` is
        the element's van der Waals radius, which is what a *viewer* wants --
        it is what PyMOL draws a sphere with and measures a surface with --
        and takes the in-tree parser: ~20x faster, because it never builds a
        hierarchy in order to walk back out of it.

    Returns
    -------
    np.ndarray
        Structured array with atom information.

    Raises
    ------
    FileNotFoundError
        When ``filename`` does not exist.
    ValueError
        For a format this reader does not handle. It does **not** answer with
        zero atoms: a trajectory handed to a coordinate reader used to produce
        an empty structure, and whatever was built from it was simply blank.

    Examples
    --------
    >>> import cs as cs  # doctest: +SKIP
    >>> import cs.core.fio  # doctest: +SKIP
    >>> atoms = cs.fio.structure.read_coordinates('./test/data/1fat.cif')  # doctest: +SKIP
    """
    # The fast path, and the reason it is a *policy* rather than a default: the
    # in-tree parser gives the element's van der Waals radius, IMP gives a
    # CHARMM Rmin per atom type. A viewer wants the first; the
    # accessible-volume simulation wants the second. Everything else the two
    # produce is identical, asserted field by field in
    # `test/fio/test_pdb_native.py`.
    if str(radii).lower() == "vdw" and str(filename).lower().endswith(
        (".pdb", ".ent", ".pdb.gz", ".ent.gz")
    ):
        return parse_pdb_native(
            filename,
            keep_water=keep_water,
            only_standard_residues=only_standard_residues,
        )

    if not os.path.isfile(filename):
        raise FileNotFoundError(f"The file {filename} could not be found.")

    lower = str(filename).lower()
    if not lower.endswith((".pdb", ".ent", ".cif", ".mmcif")):
        raise ValueError(
            f"cannot read coordinates from '{filename}': this reader handles "
            "PDB, ENT, mmCIF and PQR. Trajectories (.dcd) are read by "
            "their own loader."
        )
    if lower.endswith((".gz", ".bz2", ".xz", ".zip")):
        # IMP's readers do not decompress, and a compressed stream read as
        # text comes back as an *empty* structure rather than an error. The
        # in-tree parser handles gzip, so say which road takes it.
        raise ValueError(
            f"cannot read coordinates from '{filename}': the CHARMM-radius "
            "reader does not decompress. Pass radii='vdw' for a compressed "
            "PDB, or decompress the file."
        )

    # Whether non-standard residues are dropped is a *setting*, and the
    # argument is its default: `structure.json` -> `IMP.filter_non_standard_residues`.
    # It used to be consulted per residue inside the conversion loop, which is
    # why it read as a property of the reader rather than of the request.
    try:
        cfg = getattr(cs.core.settings, "structure_data", {})
        if not bool(cfg.get("IMP", {}).get("filter_non_standard_residues", True)):
            only_standard_residues = False
    except Exception:
        pass

    try:
        table = _bff().read_structure_table(
            filename,
            keep_water=keep_water,
            only_standard_residues=only_standard_residues,
            radius_no_interaction=True,
        )
        return _table_to_atoms(table)
    except ImportError:
        if str(filename).lower().endswith((".pdb", ".ent", ".pdb.gz", ".ent.gz")):
            return parse_pdb_native(
                filename,
                keep_water=keep_water,
                only_standard_residues=only_standard_residues,
            )
        raise


def read(
    filename: str,
    assign_charge: bool = False,
    verbose: bool = None,
    keep_water: bool = False,
    only_standard_residues: bool = True,
    radii: str = "charmm",
    **kwargs,
) -> np.ndarray:
    """Read atomic coordinates from a PDB/PQR/mmCIF file.

    Parameters
    ----------
    filename : str
        Path to the coordinate file.
    assign_charge : bool
        If True, assign charges based on residue type.
    verbose : bool, optional
        If True, print progress.
    keep_water : bool
        Keep water molecules (PDB/mmCIF only). Off by default.
    only_standard_residues : bool
        Drop ligands, sugars and modified residues (PDB/mmCIF only). On by
        default.
    **kwargs
        Forwarded to the PQR parser; ignored for PDB and mmCIF.

    Returns
    -------
    np.ndarray
        Structured array with atom information.

    Examples
    --------
    >>> import cs.core.fio
    >>> pdb_file = './test/data/atomic_coordinates/pdb_files/hGBP1_closed.pdb'
    >>> pdb = cs.core.fio.structure.coordinates.read(pdb_file, verbose=True)
    >>> pdb[:5]
    array([ (0, ' ', 7, 'MET', 1, 'N', 'N', [72.739, -17.501, 8.879], 0.0, 1.65, 0.0, 14.0067),
           (1, ' ', 7, 'MET', 2, 'CA', 'C', [73.841, -17.042, 9.747], 0.0, 1.76, 0.0, 12.0107),
           ...
    """
    if verbose is None:
        verbose = cs.core.settings.cs_settings["verbose"]
    if os.path.isfile(filename):
        if verbose:
            path, baseName = os.path.split(filename)
            print("======================================")
            print(f"Filename: {filename}")
            print(f"Path: {path}")
        fn1, ext1 = os.path.splitext(filename.upper())
        _, ext2 = os.path.splitext(fn1)
        # The file is slurped **only** for PQR, which is the one format parsed
        # from a string here. It used to be read unconditionally, before the
        # dispatch, and the text was then thrown away for every PDB and mmCIF --
        # and for anything binary it did not merely waste the read, it raised:
        # an HDF5 trajectory died on its own magic byte (`0x89` at position 0)
        # with a UnicodeDecodeError, from a function that had no intention of
        # looking at the bytes.
        if ".PQR" in [ext1, ext2]:
            with io.zipped.open_maybe_zipped(filename=filename, mode="r") as f:
                return parse_string_pqr(f.read(), **kwargs)
        return read_coordinates(
            filename=filename,
            keep_water=keep_water,
            only_standard_residues=only_standard_residues,
            radii=radii,
        )
    else:
        return np.zeros(0, dtype={"names": keys, "formats": formats})
