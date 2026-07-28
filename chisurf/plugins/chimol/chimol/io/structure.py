from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

import numpy as np
from qtpy import QtWidgets

from ..analysis.atom_classes import ATOMIC_NUMBER
from .atoms import ATOM_DTYPE, BEAD_RES_NAME, atom_row, bead_row, empty_atoms

logger = logging.getLogger(__name__)

StructureFactory = Optional[Callable[[str], object]]
FileDialogCallable = Optional[Callable[..., Sequence[str]]]

_DEFAULT_FILTER = "Structure files (*.pdb *.ent *.gro *.cif *.mmcif);;All files (*.*)"


class MdtrajNotAvailableError(RuntimeError):
    """Raised when a trajectory requires MDTraj but it is not installed."""

    pass


def _fallback_open_files(parent: Optional[QtWidgets.QWidget] = None) -> list[str]:
    files, _ = QtWidgets.QFileDialog.getOpenFileNames(
        parent,
        "Open structure file",
        "",
        _DEFAULT_FILTER,
    )
    return [str(f) for f in files]


def open_structure_files(
    parent: Optional[QtWidgets.QWidget] = None,
    *,
    opener: FileDialogCallable = None,
    description: str = "Open structure file",
    file_type: str = _DEFAULT_FILTER,
) -> list[str]:
    if opener is not None:
        try:
            result = opener(description=description, file_type=file_type)
            return [str(f) for f in result]
        except Exception:
            pass
    return _fallback_open_files(parent)


@dataclass
class StructurePayload:
    """Everything a reader recovered from a file, in one shape.

    Named for what it is rather than for the first reader that produced one: it
    began as a PDB fallback, then carried integrative-mmCIF hierarchies and
    beads, and now carries RMF trajectories too. While it was still called
    ``PdbBackbone`` the RMF reader had its own private route into the viewer,
    and everything the bead path learned -- real radii, sphere impostors,
    hierarchy visibility -- silently did not apply to it.

    Carrying the backbone metadata matters for more than the info panel:
    without residue and chain ids the viewer cannot find segment boundaries and
    splines a single polyline through every atom in file order.

    Attributes
    ----------
    coords : numpy.ndarray
        All coordinates, shape ``(N, 3)``. For a trajectory, the first frame.
    trace_coords : numpy.ndarray or None
        The CA trace, shape ``(M, 3)``, or ``None`` when the file has no
        recognisable protein backbone.
    res_ids, res_names, chain_ids : numpy.ndarray or None
        Per-CA residue number, residue name and chain id, each of length ``M``.
    atoms : numpy.ndarray or None
        Structured per-atom array with ``atom_name``, ``xyz``, ``res_id``,
        ``chain``, ``res_name`` and ``element``. This is what lets the fallback
        draw a *real* cartoon: secondary structure needs N/CA/C/O to assign
        H/E/C, and the ribbon needs the carbonyl to know which way is up.
        Without it the viewer can only spline a thin tube through the CA
        positions, which is the bare-spring look that says "the reader gave up".
    atom_radii : numpy.ndarray or None
        Per-row radii, in the same units as ``coords``. An integrative model's
        beads differ in size by an order of magnitude and the sizes *are* the
        shape of the thing.
    bonds : numpy.ndarray or None
        ``(K, 2)`` explicit connectivity, for a format that states it. Distinct
        from "no bonds": a bead model has none inferred, but an RMF may name
        them.
    frames : numpy.ndarray or None
        ``(T, N, 3)`` trajectory, when the file holds one.
    resolutions : numpy.ndarray or None
        Per row, the resolution of the representation it belongs to, for a file
        that states more than one. ``None`` means the file offers a single
        representation and there is nothing to choose between.
    resolution_default_mask : numpy.ndarray or None
        Per row, whether it belongs to the representation that lives in the
        file's own tree -- the one shown when the file opens.
    hierarchy : HierarchyNode or None
        The tree the file describes -- molecules, and the copies of them this
        model places -- when the format carries one. An integrative mmCIF and an
        RMF both do; a PDB file does not, beyond its chains.
    extras : dict
        Format-specific matter with no place in the common shape: an RMF's
        restraints, provenance and per-frame statistics. Kept opaque here so
        that adding one does not widen this class for every other reader.
    reader : str
        Which reader produced this. ``"mmcif"`` and ``"rmf"`` mean a dedicated
        reader read the file *on purpose* -- that is not a fallback and must not
        be reported as one. ``"pdb"`` means the built-in PDB parser stood in for
        a core reader that was missing or failed, which is worth telling the
        user about.
    """

    coords: np.ndarray
    trace_coords: np.ndarray | None = None
    res_ids: np.ndarray | None = None
    res_names: np.ndarray | None = None
    chain_ids: np.ndarray | None = None
    atoms: np.ndarray | None = None
    atom_radii: np.ndarray | None = None
    bonds: np.ndarray | None = None
    frames: np.ndarray | None = None
    resolutions: np.ndarray | None = None
    resolution_default_mask: np.ndarray | None = None
    reader: str = "pdb"
    hierarchy: object | None = None
    extras: dict = field(default_factory=dict)


def _element_symbol_from_pdb_line(line: str) -> str:
    """Return the element symbol of a PDB ATOM/HETATM record.

    Columns 77-78 carry the element in a modern PDB and are used verbatim when
    present. Older files leave them empty, and then the element has to come from
    the atom-name field -- where it is *right-justified in columns 13-14*. A
    blank or numeric column 13 therefore means a one-letter element, so ``" CA "``
    is an alpha carbon while ``"CA  "`` is calcium and ``"FE  "`` is iron. A
    two-letter reading is additionally rejected when columns 15-16 carry a digit,
    which is how a four-character hydrogen name such as ``"HE21"`` is written --
    helium would otherwise win.

    Parameters
    ----------
    line : str
        PDB ATOM or HETATM record.

    Returns
    -------
    str
        Upper-case element symbol, or an empty string when the record carries no
        atom name at all.
    """
    symbol = line[76:78].strip().upper()
    if symbol:
        return symbol

    name_field = line[12:16].ljust(4).upper()
    candidate = name_field[:2].strip()
    if (
        len(candidate) == 2
        and candidate in ATOMIC_NUMBER
        and not any(ch.isdigit() for ch in name_field[2:])
    ):
        return candidate
    letters = "".join(ch for ch in name_field if ch.isalpha())
    if letters[:1] not in ATOMIC_NUMBER and letters[:2] in ATOMIC_NUMBER:
        # Left-padding a two-letter element (" ZN ") breaks the column rule, but
        # here the strict reading is not an element at all, so take the pair.
        return letters[:2]
    return letters[:1]


def _mmcif_hierarchy(system, row_asym: list) -> "HierarchyNode | None":
    """Build the tree an integrative mmCIF describes, from the rows just read.

    The vocabularies line up with IMP's, which is what the hierarchy panel was
    written against: an ``entity`` is the **molecule** (``Nup84``), a
    ``struct_asym`` is the **copy** of it that appears in this assembly (chain
    ``A``), and each row of the coordinate array belongs to exactly one of
    those copies. The eight-spoke nuclear pore is 31 molecules in 544 copies, so
    the tree is small and the picture it gives -- which nucleoporin is which,
    and how many of each -- is the thing the flat bead cloud cannot show.

    The tree stops at the copy rather than descending to one node per bead: a
    node per bead would be 234,184 of them, and a list that long is not a
    hierarchy anyone reads. The copy carries the row indices of all its beads,
    which is what a click on it needs.

    Parameters
    ----------
    system : ihm.System
        The system just read.
    row_asym : list
        The asym unit each coordinate row came from, in row order.

    Returns
    -------
    HierarchyNode or None
        The root, or ``None`` when the file describes no asym units.
    """
    from .hierarchy import HierarchyNode

    if not row_asym:
        return None

    rows_by_asym: dict[int, list[int]] = {}
    for index, asym in enumerate(row_asym):
        rows_by_asym.setdefault(id(asym), []).append(index)

    title = str(getattr(system, "title", "") or "")
    entry_id = str(getattr(system, "id", "") or "structure")
    root = HierarchyNode(
        name=f"{entry_id} - {title}" if title else entry_id,
        node_type="ROOT",
        atom_indices=list(range(len(row_asym))),
    )

    # Group the copies under the molecule they are copies *of*, in first-seen
    # order, so the tree reads in the order the file lists things.
    by_entity: dict[int, HierarchyNode] = {}
    for asym in getattr(system, "asym_units", []) or []:
        rows = rows_by_asym.get(id(asym))
        if not rows:
            continue  # a chain this model does not place
        entity = getattr(asym, "entity", None)
        key = id(entity) if entity is not None else 0
        molecule = by_entity.get(key)
        if molecule is None:
            label = str(
                getattr(entity, "description", None)
                or getattr(entity, "id", None)
                or "unnamed"
            )
            molecule = root.add_child(
                HierarchyNode(name=label, node_type="MOLECULE")
            )
            by_entity[key] = molecule
        chain_id = str(getattr(asym, "id", "") or "?")
        details = str(getattr(asym, "details", "") or "")
        molecule.add_child(
            HierarchyNode(
                name=f"{chain_id} ({details})" if details else chain_id,
                node_type="CHAIN",
                chain_id=chain_id,
                copy_index=len(molecule.children),
                atom_indices=rows,
            )
        )
        molecule.atom_indices.extend(rows)

    if not root.children:
        return None
    return root

def _parse_mmcif_backbone(path: str) -> StructurePayload:
    """Read an mmCIF file with the format's own reference library.

    Handled by ``ihm``, which is written by the people who define the IHM
    dictionary and is what IMP itself uses. That matters more here than it might
    elsewhere: an integrative entry carries its coordinates as **beads** in
    ``_ihm_sphere_obj_site`` rather than atoms, alongside a large and evolving
    set of categories describing how the model was made. A hand-rolled loop
    parser was tried first and was a bad trade -- it read one NPC spoke in 34
    seconds where this takes 0.2, and it silently ignored everything it had not
    been taught.

    Both shapes are read:

    ``atoms``
        Ordinary atomic models, as any PDB mmCIF entry has.
    ``spheres``
        The beads of an integrative model, each standing for a residue range and
        carrying its own radius. The nuclear pore complex is published this way
        -- tens of thousands of spheres and not one atom.
    """
    import ihm.reader

    # BinaryCIF is msgpack, not text. It was routed here along with `.cif` and
    # then opened in **text** mode with `errors="ignore"` -- which cannot work
    # and, worse, cannot fail honestly: the decoder discards every byte it
    # cannot make into UTF-8, so the reader saw a truncated nonsense document
    # and reported "no coordinates" rather than "this is a binary format".
    # `ihm` reads it given a binary handle and `format="BCIF"`.
    binary = str(path).lower().endswith(".bcif")
    if binary:
        with open(path, "rb") as handle:
            systems = ihm.reader.read(handle, format="BCIF")
    else:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            systems = ihm.reader.read(handle)
    if not systems:
        raise ValueError(f"No structure found in {path!r}")
    system = systems[0]

    models = [
        model
        for state_group in system.state_groups
        for state in state_group
        for model_group in state
        for model in model_group
    ]
    if not models:
        models = [
            model for group in getattr(system, "orphan_model_groups", []) or []
            for model in group
        ]
    if not models:
        raise ValueError(f"No coordinates found in {path!r}")

    # One model, not all of them: an entry commonly deposits an ensemble, and
    # stacking every member would draw them on top of each other.
    model = models[0]

    coords: list[tuple[float, float, float]] = []
    atom_rows: list[tuple] = []
    radii: list[float] = []
    trace: list[tuple[float, float, float]] = []
    res_ids: list[int] = []
    res_names: list[str] = []
    chain_ids: list[str] = []
    seen: set[tuple[str, int]] = set()

    row_asym: list[object] = []

    for atom in model._atoms:
        xyz = (float(atom.x), float(atom.y), float(atom.z))
        chain = str(getattr(atom.asym_unit, "id", "") or "")
        row_asym.append(atom.asym_unit)
        try:
            res_id = int(atom.seq_id)
        except (TypeError, ValueError):
            res_id = -1
        res_name = ""
        try:
            comp = atom.asym_unit.sequence[atom.seq_id - 1]
            res_name = str(getattr(comp, "id", "") or "")
        except Exception:
            pass
        element = str(atom.type_symbol or atom.atom_id[:1] or "C").upper()
        coords.append(xyz)
        radii.append(0.0)
        atom_rows.append(
            atom_row(
                atom_name=str(atom.atom_id),
                res_name=res_name,
                chain=chain,
                res_id=res_id,
                element=element,
                xyz=xyz,
            )
        )
        if atom.atom_id != "CA" or getattr(atom, "het", False) or res_id < 0:
            continue
        if (chain, res_id) in seen:
            continue
        seen.add((chain, res_id))
        trace.append(xyz)
        res_ids.append(res_id)
        res_names.append(res_name)
        chain_ids.append(chain)

    for sphere in model._spheres:
        xyz = (float(sphere.x), float(sphere.y), float(sphere.z))
        chain = str(getattr(sphere.asym_unit, "id", "") or "")
        row_asym.append(sphere.asym_unit)
        try:
            res_id = int(sphere.seq_id_range[0])
        except (TypeError, ValueError, IndexError):
            res_id = len(coords) + 1
        try:
            radius = float(sphere.radius)
        except (TypeError, ValueError):
            radius = 2.0
        coords.append(xyz)
        radii.append(radius)
        # A bead is not an atom, but every per-atom path downstream wants a row.
        # What one looks like is defined once, in `io/atoms.py`, because the RMF
        # reader has to produce exactly the same thing.
        atom_rows.append(bead_row(chain, res_id, xyz))
        if (chain, res_id) in seen:
            continue
        seen.add((chain, res_id))
        trace.append(xyz)
        res_ids.append(res_id)
        res_names.append(BEAD_RES_NAME)
        chain_ids.append(chain)

    if not coords:
        raise ValueError(f"No coordinates found in {path!r}")

    has_trace = len(trace) >= 2
    backbone = StructurePayload(
        coords=np.asarray(coords, dtype=float),
        trace_coords=np.asarray(trace, dtype=float) if has_trace else None,
        res_ids=np.asarray(res_ids, dtype=int) if has_trace else None,
        res_names=np.asarray(res_names, dtype=object) if has_trace else None,
        chain_ids=np.asarray(chain_ids, dtype=object) if has_trace else None,
        atoms=np.array(atom_rows, dtype=ATOM_DTYPE) if atom_rows else None,
        reader="mmcif",
        hierarchy=_mmcif_hierarchy(system, row_asym),
    )
    if any(value > 0.0 for value in radii):
        backbone.atom_radii = np.asarray(radii, dtype=float)
    return backbone


def _parse_rmf(path: Path) -> StructurePayload:
    """Read an RMF as the same payload every other reader produces.

    An RMF is a bead model with a trajectory and a hierarchy, which is a
    superset of what an integrative mmCIF holds -- not a different kind of
    thing. Reading it into the same shape is what lets it share the bead
    depiction (real radii, sphere impostors past a budget), the hierarchy
    panel's visibility check boxes, and the selection and measurement commands,
    instead of each having to be taught about RMF separately.

    Parameters
    ----------
    path : pathlib.Path
        The ``.rmf`` / ``.rmf3`` file.

    Returns
    -------
    StructurePayload
        With ``frames`` set, and ``resolutions`` set when the file states more
        than one representation.
    """
    from .rmf import load_rmf_full

    data = load_rmf_full(path)
    frames = np.asarray(data["frames"], dtype=float)

    return StructurePayload(
        coords=frames[0],
        trace_coords=frames[0],
        res_ids=data["res_ids"],
        res_names=data["res_names"],
        chain_ids=data["chain_ids"],
        atoms=data["atoms"],
        atom_radii=np.asarray(data["radii"], dtype=float),
        bonds=data.get("bond_pairs"),
        frames=frames,
        resolutions=data.get("resolutions"),
        resolution_default_mask=data.get("resolution_default_mask"),
        reader="rmf",
        hierarchy=data["hierarchy"],
        extras={
            "restraints": data.get("restraints"),
            "rmf_provenance": data.get("rmf_provenance"),
            "rmf_frame_series": data.get("rmf_frame_series", {}),
            "rmf_frame_metadata": data.get("rmf_frame_metadata", {}),
            "rmf_resolutions": data.get("rmf_resolutions", []),
        },
    )


def _parse_pdb_backbone(path: str) -> StructurePayload:
    """Parse coordinates and the CA backbone out of a PDB file.

    Only the first model is read, and alternate locations other than the first
    are skipped, so that a multi-model or altloc-bearing file does not produce a
    trace that jumps between conformers.

    Parameters
    ----------
    path : str
        Path to the PDB file.

    Returns
    -------
    StructurePayload
        Coordinates and, when a protein backbone is present, the CA trace with
        its residue metadata.

    Raises
    ------
    ValueError
        If the file contains no usable atom coordinates.
    """
    coords: list[tuple[float, float, float]] = []
    trace: list[tuple[float, float, float]] = []
    res_ids: list[int] = []
    res_names: list[str] = []
    chain_ids: list[str] = []
    atom_rows: list[tuple] = []
    seen_residues: set[tuple[str, str]] = set()

    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("ENDMDL"):
                break
            is_atom = line.startswith("ATOM")
            if not (is_atom or line.startswith("HETATM")):
                continue
            try:
                xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            except ValueError:
                continue

            # Alternate locations are dropped here rather than further down, so
            # that ``coords`` and ``atoms`` stay index-aligned: the viewer maps
            # per-atom masks and colours between them by position.
            altloc = line[16:17]
            if altloc not in (" ", "", "A"):
                continue
            coords.append(xyz)

            chain = line[21:22].strip()
            res_name = line[17:20].strip()
            atom_name = line[12:16].strip()
            try:
                res_id = int(line[22:26])
            except ValueError:
                res_id = -1

            # Element from columns 77-78 when present, else from the atom-name
            # columns -- CPK colouring, ``elem`` selections and the metal/solvent
            # classes all read this field at face value.
            element = _element_symbol_from_pdb_line(line)

            # Columns 77-78 carry the B-factor's neighbours; the occupancy and
            # B-factor themselves are read because the canonical row has fields
            # for them and `spectrum b` is the reason anyone wants them.
            try:
                bfactor = float(line[60:66])
            except ValueError:
                bfactor = 0.0

            atom_rows.append(
                atom_row(
                    atom_name=atom_name,
                    res_name=res_name,
                    chain=chain,
                    res_id=res_id,
                    element=element,
                    xyz=xyz,
                    bfactor=bfactor,
                )
            )

            # The CA trace drives the cartoon/trace geometry, so it must come
            # from polymer records only -- ligands and waters are not backbone.
            if not is_atom:
                continue
            if atom_name != "CA":
                continue
            res_seq = line[22:27].strip()  # includes the insertion code
            key = (chain, res_seq)
            if key in seen_residues:
                continue
            seen_residues.add(key)
            if res_id < 0:
                continue
            trace.append(xyz)
            res_ids.append(res_id)
            res_names.append(res_name)
            chain_ids.append(chain)

    if not coords:
        raise ValueError(f"No atom coordinates found in {path!r}")

    atoms = np.array(atom_rows, dtype=ATOM_DTYPE) if atom_rows else None

    if len(trace) >= 2:
        return StructurePayload(
            coords=np.asarray(coords, dtype=float),
            trace_coords=np.asarray(trace, dtype=float),
            res_ids=np.asarray(res_ids, dtype=int),
            res_names=np.asarray(res_names, dtype=object),
            chain_ids=np.asarray(chain_ids, dtype=object),
            atoms=atoms,
        )
    return StructurePayload(coords=np.asarray(coords, dtype=float), atoms=atoms)


def parse_pdb_secondary_structure(path: str | Path) -> dict[tuple[str, int], str] | None:
    """Read the author-deposited ``HELIX``/``SHEET`` records from a PDB file.

    A deposited structure carries the depositor's own secondary-structure
    annotation, and that is what PyMOL shows unless the user explicitly asks it
    to recompute with ``dss``. For 148L the two agree exactly, so honouring the
    records is both closer to PyMOL and closer to the truth than any local
    estimate. Files without the records (predictions, trajectory frames, edited
    structures) simply return ``None`` and the caller falls back to computing.

    Parameters
    ----------
    path : str or pathlib.Path
        PDB file to read. Only the header records are parsed.

    Returns
    -------
    dict or None
        ``{(chain_id, residue_number): "H" | "E"}`` covering every residue the
        records span, or ``None`` when the file declares no secondary structure.

    Notes
    -----
    Column positions follow the PDB format: ``HELIX`` puts the initial chain and
    sequence number at columns 20 and 22-25 and the terminal ones at 32 and
    34-37; ``SHEET`` uses 22 and 23-26, and 33 and 34-37. Records spanning
    different start and end chains are skipped rather than guessed at.
    """
    records: dict[tuple[str, int], str] = {}

    def _span(code: str, chain0: str, res0: str, chain1: str, res1: str) -> None:
        c0, c1 = chain0.strip(), chain1.strip()
        if c0 != c1:
            return
        try:
            lo, hi = int(res0), int(res1)
        except ValueError:
            return
        if hi < lo:
            lo, hi = hi, lo
        for res in range(lo, hi + 1):
            records[(c0, res)] = code

    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.startswith("HELIX "):
                    _span("H", line[19:20], line[21:25], line[31:32], line[33:37])
                elif line.startswith("SHEET "):
                    _span("E", line[21:22], line[22:26], line[32:33], line[33:37])
                elif line.startswith(("ATOM", "HETATM", "MODEL")):
                    break  # the records all precede the coordinates
    except Exception:
        # Never let a malformed header cost the caller its structure: fall back
        # to computing the assignment, but say so rather than failing silently.
        logger.warning("Could not read secondary-structure records from %s", path,
                       exc_info=True)
        return None

    return records or None


def load_trajectory_frames(path: Path) -> np.ndarray:
    """Load a trajectory or multi-frame structure using MDTraj.

    The returned array has shape ``(T, N, 3)`` with coordinates in Angstroms.
    This helper is only used for formats that are not handled by the IMP-based
    readers in :mod:`chisurf.core.fio.structure.coordinates`.
    """

    try:  # Lazy import so Moview does not hard-depend on mdtraj
        import mdtraj as md  # type: ignore[import]
    except Exception as exc:  # pragma: no cover - environment dependent
        raise MdtrajNotAvailableError(
            "MDTraj is required to load this file type (e.g. GRO/HDF5 trajectory). "
            "Install it with 'conda install -c conda-forge mdtraj' or 'pip install mdtraj'."
        ) from exc

    suffix = path.suffix.lower()
    # For now we restrict to formats where MDTraj can infer topology from the
    # file itself without a separate topology argument.
    if suffix not in {".gro", ".g96", ".h5", ".hdf5"}:
        raise ValueError(f"File type '{suffix}' is not recognised as an MDTraj trajectory/structure")

    try:
        traj = md.load(str(path))
    except Exception as exc:
        raise RuntimeError(f"mdtraj failed to load '{path}': {exc}") from exc

    xyz = getattr(traj, "xyz", None)
    if xyz is None:
        raise RuntimeError(f"mdtraj did not return coordinates for '{path}'")

    arr = np.asarray(xyz, dtype=float)
    if arr.ndim != 3 or arr.shape[2] != 3 or arr.shape[0] == 0 or arr.shape[1] == 0:
        raise RuntimeError(f"mdtraj returned invalid xyz array for '{path}' with shape {arr.shape!r}")

    # MDTraj uses nanometers; convert to Angstrom to be consistent with IMP
    # based loaders used elsewhere in ChiSurf/Moview.
    arr *= 10.0
    return arr


#: Van-der-Waals radii, in Angstrom, for the elements a trajectory carries.
_VDW = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80}


def load_trajectory_atoms(path: Path, first_frame: np.ndarray):
    """Build an atom array from an MDTraj file's **topology**.

    Returns ``None`` when the file carries no topology.

    Why this exists
    ---------------
    :func:`load_trajectory_frames` returned coordinates and dropped
    ``traj.topology`` on the floor, so an all-atom trajectory arrived with no
    residues, no chains and no atom names. Everything keyed on that identity then
    degraded silently: the cartoon builder had no CA atoms to spline through and
    treated all 5235 atoms as trace points, drawing ~340 disconnected fragments;
    ``intra_fit polymer`` could not resolve a selection; the sequence view was
    empty.

    None of it errored, which is why it read as "cartoons do not work on
    trajectories". They do -- the identity was being discarded at load.

    Parameters
    ----------
    path : pathlib.Path
        The trajectory file.
    first_frame : numpy.ndarray
        ``(N, 3)`` coordinates in Angstrom, used to fill the ``xyz`` field.

    Returns
    -------
    numpy.ndarray or None
        A structured atom array, or None when there is no topology to read.
    """
    try:
        import mdtraj as md  # type: ignore[import]

        topology = md.load(str(path)).topology
    except Exception:
        return None
    if topology is None:
        return None

    atoms = list(topology.atoms)
    if not atoms or len(atoms) != int(np.asarray(first_frame).shape[0]):
        return None

    array = empty_atoms(len(atoms))
    for index, atom in enumerate(atoms):
        residue = atom.residue
        element = getattr(atom.element, "symbol", "") or ""
        array["i"][index] = index
        array["atom_id"][index] = index + 1
        array["atom_name"][index] = str(atom.name)[:5]
        array["element"][index] = str(element).upper()[:2]
        array["res_name"][index] = str(residue.name)[:5]
        # resSeq, not the 0-based index: it is what the file says the residue is
        # called, and what a `resi 42` selection has to match.
        array["res_id"][index] = int(getattr(residue, "resSeq", residue.index))
        chain_index = int(getattr(residue.chain, "index", 0))
        array["chain"][index] = chr(ord("A") + chain_index % 26)
        array["radius"][index] = _VDW.get(str(element).upper(), 1.70)
        array["mass"][index] = float(getattr(atom.element, "mass", 0.0) or 0.0)
    array["xyz"] = np.asarray(first_frame, dtype=float)
    return array


def _read_full_model(structure_factory: Callable[..., object], path: Path) -> object:
    """Build a structure that keeps waters, ligands and modified residues.

    The core reader is tuned for modelling and drops solvent and non-standard
    residues by default, which is wrong for a viewer: a deposited entry then
    appears without the waters and ligands that PyMOL shows, and the atom counts
    disagree with the file. Ask for the full model, and fall back to the plain
    call for factories that predate the arguments (or are not the core reader at
    all, as in standalone Chimol).

    Parameters
    ----------
    structure_factory : callable
        Factory taking a path and returning a structure object.
    path : pathlib.Path
        File to read.

    Returns
    -------
    object
        The structure the factory produced.
    """
    try:
        return structure_factory(
            str(path), keep_water=True, only_standard_residues=False
        )
    except TypeError:
        logger.debug(
            "Structure factory does not accept keep_water/only_standard_residues; "
            "loading %s without solvent and hetero residues.",
            path,
        )
        return structure_factory(str(path))


def load_structure_payload(
    path: Path,
    *,
    structure_factory: StructureFactory = None,
) -> tuple[object | None, StructurePayload | None]:
    """Load ``path`` as a ``Structure``, falling back to a parsed PDB backbone.

    Parameters
    ----------
    path : pathlib.Path
        File to load.
    structure_factory : callable or None
        Factory building the core ``Structure`` from a path. When it is missing
        or fails, the file is parsed directly for coordinates and backbone.

    Returns
    -------
    tuple
        ``(structure, None)`` when the core reader succeeded, otherwise
        ``(None, StructurePayload)``.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist. The fallback below is for a file this
        reader cannot *parse*, which is a different thing from a file that is
        not there: a mistyped path used to fall through it and arrive as a
        one-atom object at the origin, so `load` reported success, the object
        panel listed the molecule, and the viewport stayed empty.
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"no such file: {path}")

    structure = None
    # An RMF is read here rather than by a branch of its own in the window. It
    # used to have one, and so it never received anything the common path
    # learned: its beads were drawn at a single default radius, decimated to a
    # fraction of themselves, and its hierarchy's visibility check boxes moved
    # nothing.
    if str(path).lower().endswith((".rmf", ".rmf3")):
        return None, _parse_rmf(Path(path))

    # An IHM mmCIF goes straight to `ihm`. The core reader has no idea what a
    # bead model is: on one NPC spoke it ground for 34 seconds and then failed,
    # and the fallback did the work anyway. Trying it first costs that every
    # time for nothing.
    #
    # That is a *choice of reader*, not a failure of one, so it must not be
    # announced as a missing factory: every `fetch` of an mmCIF warned that it
    # had fallen back to "the built-in PDB parser" when the dedicated mmCIF
    # reader had in fact read the file, and the GUI raised a degraded-load
    # notice over the top of it.
    is_mmcif = str(path).lower().endswith((".cif", ".mmcif", ".bcif"))
    if is_mmcif:
        structure_factory = None
    elif structure_factory is None:
        logger.warning(
            "No structure factory available for %s; falling back to the "
            "built-in PDB parser (no radius of gyration).",
            path,
        )
    if structure_factory is not None:
        try:
            structure = _read_full_model(structure_factory, path)
        except Exception:
            logger.warning(
                "Structure reader failed for %s; falling back to the built-in "
                "PDB parser (no radius of gyration).",
                path,
                exc_info=True,
            )
            structure = None

    # Reject empty/invalid structures so that callers can fall back to
    # alternative loaders (e.g. MDTraj for trajectories or GRO files).
    if structure is not None:
        try:
            n_atoms = getattr(structure, "n_atoms", None)
        except Exception:
            n_atoms = None
        if isinstance(n_atoms, int) and n_atoms <= 0:
            logger.warning(
                "Structure reader returned an empty structure for %s; falling "
                "back to raw coordinates.",
                path,
            )
            structure = None

    if structure is not None:
        return structure, None

    # mmCIF needs its own reader: fed to the fixed-column PDB parser it yields
    # nothing at all, which is what every `.cif` load did before -- including
    # every `fetch_ihm`, whose files are mmCIF by definition.
    if str(path).lower().endswith((".cif", ".mmcif", ".bcif")):
        backbone = _parse_mmcif_backbone(str(path))
    else:
        backbone = _parse_pdb_backbone(str(path))
    coords = backbone.coords
    if coords.ndim != 2 or coords.shape[1] != 3 or coords.shape[0] == 0:
        raise ValueError(f"No valid coordinates in {path}")
    if backbone.trace_coords is None:
        logger.warning(
            "No protein backbone found in %s; the viewer will show bare "
            "coordinates without residues or sequence.",
            path,
        )
    return None, backbone


__all__ = [
    "StructurePayload",
    "open_structure_files",
    "load_structure_payload",
    "load_trajectory_frames",
    "parse_pdb_secondary_structure",
    "MdtrajNotAvailableError",
]
