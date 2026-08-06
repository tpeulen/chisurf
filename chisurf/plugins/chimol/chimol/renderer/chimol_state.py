from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


def _copy_array(value):
    """Return a defensive copy of arbitrary array-like payloads."""

    if value is None:
        return None
    try:
        return np.array(value, copy=True)
    except Exception:
        try:
            return copy.deepcopy(value)
        except Exception:
            return value


def _coerce_covariance_array(value):
    """Normalize covariance payloads into ``(N, 3, 3)`` arrays."""

    if value is None:
        return None
    try:
        arr = np.asarray(value, dtype=float)
    except Exception:
        return None
    if arr.ndim == 3 and arr.shape[1:] == (3, 3):
        return arr
    if arr.ndim == 2 and arr.shape[1] == 9:
        return arr.reshape(-1, 3, 3)
    if arr.ndim == 2 and arr.shape[1] == 6:
        out = np.zeros((arr.shape[0], 3, 3), dtype=float)
        out[:, 0, 0] = arr[:, 0]
        out[:, 1, 1] = arr[:, 1]
        out[:, 2, 2] = arr[:, 2]
        out[:, 0, 1] = out[:, 1, 0] = arr[:, 3]
        out[:, 0, 2] = out[:, 2, 0] = arr[:, 4]
        out[:, 1, 2] = out[:, 2, 1] = arr[:, 5]
        return out
    return None


@dataclass
class _MolViewObjectState:
    coords: Optional[np.ndarray] = None
    center: Optional[np.ndarray] = None
    raw_center: Optional[np.ndarray] = None
    radius: float = 1.0
    atoms: Optional[np.ndarray] = None
    all_atom_coords: Optional[np.ndarray] = None
    all_atom_res_ids: Optional[np.ndarray] = None
    all_atom_radii: Optional[np.ndarray] = None
    atom_features: dict[str, object] = field(default_factory=dict)
    atom_feature_meta: dict[str, dict] = field(default_factory=dict)
    residue_ids: Optional[np.ndarray] = None
    residue_names: Optional[np.ndarray] = None
    residue_oneletter: Optional[np.ndarray] = None
    residue_chain_ids: Optional[np.ndarray] = None
    selected_residues: list[int] = field(default_factory=list)
    color_mode: str = "single"
    colors_per_ca: Optional[np.ndarray] = None
    colors_per_residue_override: Optional[np.ndarray] = None
    colors_per_atom_override: Optional[np.ndarray] = None
    secondary_structure: Optional[np.ndarray] = None
    #: ``(n_res, 3)`` atom indices of each residue's N, C and O -- see
    #: :func:`~chimol.geometry.cartoon.backbone_index_map`. Pure topology, so it
    #: survives a trajectory frame change, where only ``atoms["xyz"]`` is
    #: replaced. Consulted *only* on that path and cleared wherever the topology
    #: is genuinely rebuilt, so it cannot drift from the atom array.
    backbone_map: Optional[np.ndarray] = None
    #: Frame position actually shown, which may sit between two stored frames.
    frame_position: float = 0.0
    #: A voxel map, when this object is one -- see :mod:`chimol.volume`. A map
    #: object has no ``coords``, so every path that assumes coordinates has to
    #: ask about this too rather than skipping the object silently.
    volume: Optional[object] = None
    #: Contours to draw on ``volume``: ``[{"level": float, "color": (r,g,b,a),
    #: "style": "surface"|"mesh"}]``. A list because reading a density means
    #: seeing more than one level at once -- a dense core inside a diffuse shell.
    volume_levels: list = field(default_factory=list)
    representation_mode: str = "cartoon"
    trace_ups: Optional[np.ndarray] = None
    show_cartoon: bool = True
    show_trace: bool = False
    show_atoms: bool = False
    show_dots: bool = False
    show_sticks: bool = False
    # PyMOL's default pair: per-bond wireframe plus crosses on the
    # atoms that draw no bond (auto_show_lines / auto_show_nonbonded).
    show_lines: bool = False
    show_nonbonded: bool = False
    #: {atom index: text} for the label representation.
    labels: dict = field(default_factory=dict)
    show_labels: bool = True
    sidechains_visible: bool = True
    show_atom_gaussians: bool = False
    cartoon_mask: Optional[np.ndarray] = None
    ball_mask: Optional[np.ndarray] = None
    sticks_mask: Optional[np.ndarray] = None
    #: Per-atom/per-residue scoping masks for the remaining representations,
    #: ``None`` meaning *all atoms/residues* (no scoping). Set only by a scoped
    #: ``show``/``hide``/``as`` with a selection, so ``as X, sele`` changes
    #: exactly the selection and nothing outside it.
    trace_mask: Optional[np.ndarray] = None
    lines_mask: Optional[np.ndarray] = None
    nonbonded_mask: Optional[np.ndarray] = None
    label_mask: Optional[np.ndarray] = None
    dots_mask: Optional[np.ndarray] = None
    surface_mask: Optional[np.ndarray] = None
    metaball_mask: Optional[np.ndarray] = None
    bond_pairs: Optional[np.ndarray] = None
    bond_edits: dict = field(default_factory=lambda: {"added": {}, "removed": set()})
    """Manual ``bond``/``unbond`` edits, kept as *deltas* over the inferred list.

    Bonds are re-inferred from the coordinates whenever a structure is loaded or
    its coordinates change, so a hand-made bond stored only in ``bond_pairs``
    would silently disappear the next time anything moved an atom. Recording the
    edits instead and replaying them over each fresh inference is what makes
    ``bond`` stick, and it is one-directional -- the edits are the source of
    truth for the deltas, ``bond_pairs`` is derived -- so the two cannot drift.

    ``added`` maps a sorted ``(i, j)`` index pair to its bond order; ``removed``
    holds pairs to take out. Orders live here rather than as a third column of
    ``bond_pairs`` because several consumers flatten that array to ask "which
    atoms have a bond", and an order column would read as an atom index.
    """
    symmetry: Optional[dict] = None
    """Crystal cell, space group and operators, when set or read from the file.

    ``{"cell": UnitCell, "space_group": str, "operators": [str, ...]}``. Kept on
    the object rather than globally because two loaded structures can come from
    different crystals, and a single global cell would silently expand one of them
    with the other's lattice.
    """
    masked_mask: Optional[np.ndarray] = None
    """Atoms made unpickable by ``mask``, as a boolean over all atoms.

    PyMOL's ``mask`` stops the mouse selecting an atom, which is what makes a
    molecule in front workable when another sits behind it. Kept separate from
    ``protected_mask``: one is about the mouse, the other about transforms, and
    conflating them would mean hiding an atom from selection also froze it.
    """
    protected_mask: Optional[np.ndarray] = None
    """Atoms held in place by ``protect``, as a boolean over all atoms.

    PyMOL's ``protect`` shields atoms from the editing transforms, which is how
    part of a structure is moved while the rest stays put. Stored as a mask
    rather than a list of indices so it survives an atom-count change no worse
    than the other per-atom arrays do -- and so the check at the transform seam
    is one array operation rather than a membership test per atom.
    """
    surface_visible: bool = False
    metaballs_visible: bool = False
    point_overlays: dict[str, dict] = field(default_factory=dict)
    frames: Optional[np.ndarray] = None
    frames_raw: Optional[np.ndarray] = None
    #: ``(n_frames, n_rows)`` radii, when the file gives a radius per frame. A
    #: simulation whose particles grow, or that has not created one yet, says so
    #: here; ``None`` means the one radius in ``all_atom_radii`` holds for the
    #: whole trajectory.
    frame_radii: Optional[np.ndarray] = None
    #: ``(n_frames, n_rows, 3)`` colours, when the file gives a colour per
    #: frame. This is how a particle's *state* over time reaches the picture --
    #: a cell that changes what it is doing changes colour without moving.
    frame_colors: Optional[np.ndarray] = None
    #: Rows with no size in the current frame: a bead the file has not created
    #: yet, or one that has gone. Kept apart from ``hidden_mask`` for the reason
    #: ``representation_mask`` is: they answer different questions, and one mask
    #: serving both means stepping the movie silently un-hides what you switched
    #: off. Composed in :meth:`MolView.visible_row_mask`.
    absent_mask: Optional[np.ndarray] = None
    active_frame: int = 0
    measurements: dict[str, dict] = field(default_factory=dict)
    rmf_hierarchy: Optional[object] = None  # HierarchyNode, whoever built it
    #: Rows of the coordinate array to leave undrawn, one flag each. This is
    #: *visibility*, not representation: the hierarchy panel switches whole
    #: molecules and chains off with it, and every representation honours it.
    hidden_mask: Optional[np.ndarray] = None
    #: Per row, the resolution of the representation it belongs to; ``None``
    #: when the file states a single one. "Resolution" is residues per bead, so
    #: a larger number is a coarser depiction.
    resolutions: Optional[np.ndarray] = None
    #: Rows of the representation currently *chosen*, one flag each. Kept apart
    #: from ``hidden_mask`` deliberately: the two answer different questions --
    #: "which depiction of this model" and "which parts of it did I switch off"
    #: -- and one mask serving both means picking a resolution silently
    #: un-hides whatever you had hidden. They are combined at draw time.
    representation_mask: Optional[np.ndarray] = None
    restraints: list[dict] = field(default_factory=list)
    rmf_provenance: list[dict] = field(default_factory=list)
    rmf_frame_series: dict[str, object] = field(default_factory=dict)
    rmf_frame_metadata: dict[str, object] = field(default_factory=dict)
    rmf_resolutions: list[float] = field(default_factory=list)
    _ca_indices: Optional[np.ndarray] = None


def copy_state(state: "_MolViewObjectState") -> "_MolViewObjectState":
    """Return an independent copy of an object's render state.

    Every array is copied rather than shared, which is the whole point: a copied
    object that aliased its source's coordinates would move when the original was
    transformed, and the two would be indistinguishable until someone edited one.

    Parameters
    ----------
    state : _MolViewObjectState
        The state to duplicate.

    Returns
    -------
    _MolViewObjectState
        A new state sharing nothing mutable with the original.
    """
    duplicate = _MolViewObjectState()
    for name in state.__dataclass_fields__:
        value = getattr(state, name, None)
        if isinstance(value, np.ndarray):
            setattr(duplicate, name, value.copy())
        elif isinstance(value, (list, dict, set)):
            setattr(duplicate, name, copy.deepcopy(value))
        else:
            setattr(duplicate, name, value)
    return duplicate


@dataclass
class _MolViewObjectEntry:
    object_id: str
    name: str
    state: _MolViewObjectState = field(default_factory=_MolViewObjectState)
    visible: bool = True
    placeholder: bool = False
    source_path: Optional[str] = None
    group: Optional[str] = None
    """Name of the group this object belongs to, or None for a top-level object.

    Membership is stored on the member rather than as a list on the group, so
    there is exactly one place that says where an object sits. A list on the
    group plus a back-pointer here would be two, and the two would drift the
    first time an object was deleted -- which is the failure this codebase keeps
    finding in its own colour, keyword and representation state.
    """


class _StateField:
    """Descriptor that proxies attribute access to the active object state."""

    def __init__(self, attr_name: str):
        self.attr_name = attr_name

    def __get__(self, instance, owner):  # type: ignore[override]
        if instance is None:
            return self
        # Reading from an empty viewer answers "nothing", not an exception.
        # `_get_active_state` raises when the last object has been deleted, and
        # every reader of these fields already handles ``None`` -- so raising
        # turned `delete` of the final object into a crash in whatever touched
        # `viewer._atoms` next, which in a GUI is the following repaint.
        try:
            state = instance._get_active_state()
        except RuntimeError:
            return None
        return getattr(state, self.attr_name)

    def __set__(self, instance, value):  # type: ignore[override]
        state = instance._get_active_state()
        setattr(state, self.attr_name, value)


__all__ = [
    "_copy_array",
    "_coerce_covariance_array",
    "_MolViewObjectState",
    "_MolViewObjectEntry",
    "_StateField",
]
