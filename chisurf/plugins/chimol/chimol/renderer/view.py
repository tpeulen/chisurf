from __future__ import annotations

import copy
import logging
import time
from collections import OrderedDict
from collections.abc import Sequence
from contextlib import contextmanager
from importlib import import_module
from typing import Any, Optional, Union

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from ..analysis.ss import assign_ss_c3_from_atoms
from ..colors import (
    _build_chain_color_array,
    _build_element_color_array,
    _build_residue_color_array,
    _build_sequence_gradient_colors,
    _build_ss_color_array,
    _three_to_one_array,
)
from ..config import _DISPLAY_CONFIG, register_update_listener, unregister_update_listener
from ..io.structure import parse_pdb_secondary_structure
from ..geometry import (
    bond_line_segments,
    _build_bond_pairs,
    build_bond_pairs_by_element,
    _build_sphere_mesh,
    _build_stick_mesh,
    _build_trace_ups,
    backbone_index_map,
    _compute_center_radius,
    _estimate_ambient_occlusion,
    directional_occlusion,
    occlusion_from_spheres,
    _extract_ca_trace,
    _generate_cartoon_tube_arrays,
    _generate_nucleic_cartoon_arrays,
    _generate_surface_mesh_from_density,
    _generate_surface_mesh_edt,
    _generate_surface_mesh_from_gaussians,
    _generate_surface_mesh_from_points,
    _generate_trace_arrays,
    _get_surface_atom_mask,
    nonbonded_crosses,
    shade_from_atoms,
    unbonded_mask,
)
from .base import Renderer
from .chimol_state import (
    _MolViewObjectEntry,
    _MolViewObjectState,
    _StateField,
    copy_state,
)
from .qtgl import QtGLRenderer
from .scene import Geometry, Scene, SceneObject
from .undo import UndoRing
from .view_state import framing_centre, framing_radius

logger = logging.getLogger(__name__)

# Default per-atom van-der-Waals radius (Angstrom) used for raw-coordinate
# objects that carry no radii of their own. Sized to sit just below the real
# vdW radii the structure reader assigns (~1.5-2.0 A) so the fallback's balls
# and its surface/metaball density sigmas match the structured path once the
# coordinates are scaled by ``_scale_factor``.
_DEFAULT_ATOM_RADIUS_A = 1.5


def _get_picking_module():
    try:
        return import_module("..app.picking", __package__)
    except Exception:
        return None


def _copy_array(value):
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


def _coerce_rotation_translation(rotation, translation):
    rot = np.asarray(rotation, dtype=float)
    if rot.shape != (3, 3):
        raise ValueError("Rotation matrix must have shape (3, 3)")
    trans = np.asarray(translation, dtype=float).reshape(3)
    return rot, trans


def _apply_rigid_transform(data, rotation, translation):
    if data is None:
        return None

    arr = np.asarray(data)
    # A structured atom array keeps its coordinates in an `xyz` field, so
    # transform that. Skipping it -- as this used to -- left the atom array
    # holding pre-transform coordinates while the render arrays moved, and the
    # two are read by different commands: `rms` reported 69 A of displacement
    # over render coordinates while `align` read the atom array, saw nothing to
    # do, and announced an RMSD of 0.000.
    if getattr(arr.dtype, "fields", None):
        if "xyz" not in (arr.dtype.names or ()):
            return data
        moved = arr.copy()
        xyz = np.asarray(moved["xyz"], dtype=float)
        moved["xyz"] = (xyz @ rotation.T) + translation
        return moved

    arr = arr.astype(float, copy=False)

    if arr.ndim == 2 and arr.shape[1] == 3:
        return (arr @ rotation.T) + translation

    if arr.ndim >= 3 and arr.shape[-1] == 3:
        flat = arr.reshape(-1, 3)
        flat = (flat @ rotation.T) + translation
        return flat.reshape(arr.shape)

    if arr.ndim == 1 and arr.shape[0] == 3:
        return (arr @ rotation.T) + translation

    return arr




def _frame_blend(position, n_frames: int) -> tuple[int, float, int]:
    """Split a possibly fractional frame position into a pair and a weight.

    Returns ``(index, blend, next_index)`` where ``blend`` is 0 on a stored
    frame and the interpolation weight toward ``next_index`` otherwise. The last
    frame never blends past the end, and a non-numeric position falls back to
    the first frame rather than raising -- callers pass whatever a spinner or a
    script gave them.
    """
    if n_frames <= 0:
        return 0, 0.0, 0
    try:
        pos = float(position)
    except (TypeError, ValueError):
        return 0, 0.0, 0
    if not np.isfinite(pos):
        return 0, 0.0, 0
    pos = min(max(pos, 0.0), float(n_frames - 1))
    index = int(np.floor(pos))
    blend = float(pos - index)
    if index >= n_frames - 1:
        return n_frames - 1, 0.0, n_frames - 1
    if blend <= 1e-9:
        return index, 0.0, index
    return index, blend, index + 1


class MolView(QtWidgets.QWidget):

    # Emitted when residues are selected via picking in the 3D view. The
    # payload is a list of integer residue indices along the CA trace.
    residueSelectionChanged = QtCore.Signal(object)
    objectResidueSelectionChanged = QtCore.Signal(object, object)
    # Emitted when atoms are selected via picking in the 3D view. The
    # payload is a list of integer atom indices.
    atomSelectionChanged = QtCore.Signal(object)
    """Minimal 3D protein viewer widget (Chimol).

    This widget embeds a :class:`QtWidgets.QOpenGLWidget`-based renderer and
    draws a simple backbone trace (through CA atoms where possible). It is
    designed to be embedded in existing Qt layouts and does not manage its own
    QApplication.

    Public methods
    --------------
    - :meth:`set_structure(structure)`: accept a ChiSurf ``Structure``-like
      object with ``atoms``/``xyz`` attributes.
    - :meth:`set_coordinates(xyz)`: accept an ``(N, 3)`` coordinate array.
    """

    _coords = _StateField("coords")
    _center = _StateField("center")
    _raw_center = _StateField("raw_center")
    _radius = _StateField("radius")
    _atoms = _StateField("atoms")
    _all_atom_coords = _StateField("all_atom_coords")
    _all_atom_res_ids = _StateField("all_atom_res_ids")
    _all_atom_radii = _StateField("all_atom_radii")
    _atom_features = _StateField("atom_features")
    _atom_feature_meta = _StateField("atom_feature_meta")
    _residue_ids = _StateField("residue_ids")
    _residue_names = _StateField("residue_names")
    _residue_oneletter = _StateField("residue_oneletter")
    _residue_chain_ids = _StateField("residue_chain_ids")
    _selected_residues = _StateField("selected_residues")
    _color_mode = _StateField("color_mode")
    _colors_per_ca = _StateField("colors_per_ca")
    _colors_per_residue_override = _StateField("colors_per_residue_override")
    _colors_per_atom_override = _StateField("colors_per_atom_override")
    _secondary_structure = _StateField("secondary_structure")
    _representation_mode = _StateField("representation_mode")
    _trace_ups = _StateField("trace_ups")
    _backbone_map = _StateField("backbone_map")
    _show_cartoon = _StateField("show_cartoon")
    _show_trace = _StateField("show_trace")
    _show_atoms = _StateField("show_atoms")
    _show_dots = _StateField("show_dots")
    _show_sticks = _StateField("show_sticks")
    _show_lines = _StateField("show_lines")
    _show_nonbonded = _StateField("show_nonbonded")
    _labels = _StateField("labels")
    _show_labels = _StateField("show_labels")
    _sidechains_visible = _StateField("sidechains_visible")
    _show_atom_gaussians = _StateField("show_atom_gaussians")
    _cartoon_mask = _StateField("cartoon_mask")
    _ball_mask = _StateField("ball_mask")
    _sticks_mask = _StateField("sticks_mask")
    _bond_pairs = _StateField("bond_pairs")
    _bond_edits = _StateField("bond_edits")
    _protected_mask = _StateField("protected_mask")
    _masked_mask = _StateField("masked_mask")
    _surface_visible = _StateField("surface_visible")
    _metaballs_visible = _StateField("metaballs_visible")
    _point_overlays = _StateField("point_overlays")
    _ca_indices = _StateField("_ca_indices")
    _measurements = _StateField("measurements")
    _bead_radii = _StateField("bead_radii")
    _rmf_hierarchy = _StateField("rmf_hierarchy")
    _restraints = _StateField("restraints")
    _rmf_provenance = _StateField("rmf_provenance")

    def set_rmf_data(
        self,
        hierarchy: object,
        frames: np.ndarray,
        radii: np.ndarray,
        restraints: list[dict] = None,
        rmf_provenance: list[dict] = None,
        rmf_frame_series: dict[str, object] | None = None,
        rmf_frame_metadata: dict[str, object] | None = None,
        rmf_resolutions: set[object] | None = None,
        bond_pairs: np.ndarray | None = None,
        *,
        object_id: str | None = None
    ) -> None:
        """Load full RMF data (hierarchy, trajectory, radii) into an object.

        RMF coordinates are stored and returned in Angstroms by IMP.  Chimol's
        internal scene uses the same scaled units as :meth:`set_frames` and
        :meth:`add_structure` (coordinates are centered and multiplied by
        ``_scale_factor``), so we apply that scaling here to keep bond,
        cartoon, and bead sizes consistent with structure-loaded objects.
        """
        with self._activate_object(object_id):
            state = self._get_active_state()
            state.rmf_hierarchy = hierarchy

            if frames is not None and len(frames) > 0:
                arr = np.asarray(frames, dtype=float)
                flat = arr.reshape(-1, 3)
                center, radius = _compute_center_radius(flat)
                scale = float(self._scale_factor)
                state.frames = (arr - center) * scale
                state.frames_raw = arr
                self._center = np.zeros(3, dtype=float)
                self._radius = float(radius * scale)
            else:
                state.frames = frames
                state.frames_raw = frames

            if radii is not None:
                state.bead_radii = np.asarray(radii, dtype=float) * float(self._scale_factor)
            else:
                state.bead_radii = radii

            if restraints:
                state.restraints = restraints
            if rmf_provenance:
                state.rmf_provenance = rmf_provenance
            if rmf_frame_series is not None:
                state.rmf_frame_series = rmf_frame_series
            if rmf_frame_metadata is not None:
                state.rmf_frame_metadata = rmf_frame_metadata
            if rmf_resolutions is not None:
                state.rmf_resolutions = rmf_resolutions
            if bond_pairs is not None:
                state.bond_pairs = bond_pairs
                state.show_sticks = True
            # If we have frames, set the first one as active
            if frames is not None and len(frames) > 0:
                self._select_state_frame(state, 0)
                self._total_frames = max(self._total_frames, len(frames))
                n_points = int(np.asarray(state.frames).shape[1])
                state.cartoon_mask = np.zeros(n_points, dtype=bool)
                state.ball_mask = np.ones(n_points, dtype=bool)
                state.sticks_mask = np.ones(n_points, dtype=bool)

            # If we have radii, we likely want to show beads (mode 'spheres')
            if radii is not None and np.any(radii > 0):
                state.show_atoms = True  # We use the atoms/spheres path for beads
                state.show_cartoon = False
                state.show_trace = False

        self._update_view()

    def _prune_placeholders(self) -> None:
        """Drop any placeholder-only entries."""
        removed_any = False
        for oid in list(self._objects.keys()):
            entry = self._objects.get(oid)
            if entry is not None and entry.placeholder:
                self._objects.pop(oid, None)
                removed_any = True
        if removed_any and self._active_object_id not in self._objects:
            self._active_object_id = next(iter(self._objects), None)
        if not self._objects:
            self._auto_create_enabled = False

    def _create_object(
        self,
        name: str | None = None,
        source_path: str | None = None,
        *,
        placeholder: bool = False,
    ) -> _MolViewObjectEntry:
        if not placeholder:
            self._prune_placeholders()
        self._object_counter += 1
        object_id = f"obj{self._object_counter}"
        entry = _MolViewObjectEntry(
            object_id=object_id,
            name=name or f"Object {self._object_counter}",
            source_path=source_path,
            placeholder=placeholder,
        )
        defaults = _DISPLAY_CONFIG.get("defaults", {})
        try:
            entry.state.color_mode = str(defaults.get("color_mode", "single"))
        except Exception:
            entry.state.color_mode = "single"
        self._objects[object_id] = entry
        self._active_object_id = object_id
        self._auto_create_enabled = True
        return entry

    def _ensure_active_entry(self, create_if_missing: bool = True) -> _MolViewObjectEntry | None:
        if self._active_object_id in self._objects:
            return self._objects[self._active_object_id]
        if self._objects:
            # Prefer a non-placeholder entry
            for oid, entry in self._objects.items():
                if not entry.placeholder:
                    self._active_object_id = oid
                    return entry
            # Fallback to first placeholder if that's all we have
            oid, entry = next(iter(self._objects.items()))
            self._active_object_id = oid
            return entry
        if create_if_missing and self._auto_create_enabled:
            return self._create_object(placeholder=True)
        return None

    def _get_active_state(self) -> _MolViewObjectState:
        entry = self._ensure_active_entry()
        if entry is None:
            raise RuntimeError("No active object available")
        return entry.state

    def get_active_object_id(self) -> str | None:
        return self._active_object_id

    def set_active_object(self, object_id: str) -> bool:
        if object_id not in self._objects:
            return False
        if self._active_object_id == object_id:
            return True
        self._active_object_id = object_id
        self._update_view()
        return True

    def clear_color_overrides(self) -> None:
        self._colors_per_residue_override = None
        self._colors_per_atom_override = None
        if self._coords is not None:
            self._update_view()

    def set_atom_features(
        self,
        features: dict[str, object] | None,
        *,
        meta: dict[str, dict] | None = None,
        object_id: str | None = None,
    ) -> None:
        """Attach arbitrary per-atom feature payloads to the active object."""

        def _sanitize_dict(data: dict[str, object] | None) -> dict[str, object]:
            if not data:
                return {}
            cleaned: dict[str, object] = {}
            for key, value in data.items():
                cleaned[str(key)] = _copy_array(value)
            return cleaned

        with self._activate_object(object_id):
            state = self._get_active_state()
            state.atom_features = _sanitize_dict(features)
            if meta is None:
                state.atom_feature_meta = {}
            else:
                cleaned_meta: dict[str, dict] = {}
                for key, info in meta.items():
                    if not isinstance(info, dict):
                        continue
                    cleaned_meta[str(key)] = {
                        str(sub_key): _copy_array(sub_val)
                        for sub_key, sub_val in info.items()
                    }
                state.atom_feature_meta = cleaned_meta

        if self._coords is not None:
            self._update_view()

    def clear_atom_features(self, *, object_id: str | None = None) -> None:
        self.set_atom_features(None, object_id=object_id)

    def set_atom_colors(self, colors: np.ndarray | None) -> None:
        if colors is None:
            self._colors_per_atom_override = None
        else:
            arr = np.asarray(colors, dtype=float)
            if arr.ndim != 2 or arr.shape[1] < 3:
                return
            if self._all_atom_coords is None:
                return
            n_atoms = int(np.asarray(self._all_atom_coords).shape[0])
            if arr.shape[0] != n_atoms:
                return
            if arr.shape[1] == 3:
                alpha = np.ones((arr.shape[0], 1), dtype=float)
                arr = np.concatenate([arr, alpha], axis=1)
            self._colors_per_atom_override = arr
        if self._coords is not None:
            self._update_view()

    def set_atom_color_override(
        self,
        indices: np.ndarray,
        colors: np.ndarray,
        *,
        object_id: str | None = None,
    ) -> bool:
        """Colour some atoms without disturbing the rest.

        :meth:`set_atom_colors` replaces the whole array, so it cannot express
        "colour this selection": everything outside it would have to be supplied
        too, and would be lost if it were not. Commands that colour a selection --
        ``spectrum``, ``color`` -- need this instead.

        Parameters
        ----------
        indices : numpy.ndarray
            Atom indices to set.
        colors : numpy.ndarray
            ``(len(indices), 3)`` or ``(len(indices), 4)`` colours.
        object_id : str, optional
            Object to colour; defaults to the active one.

        Returns
        -------
        bool
            False when the object carries no per-atom coordinates to colour.
        """
        with self._activate_object(object_id):
            coords = self._all_atom_coords
            if coords is None:
                return False
            n_atoms = int(np.asarray(coords).shape[0])

            current = self._colors_per_atom_override
            if current is None or np.asarray(current).shape[0] != n_atoms:
                # Start from whatever the object is currently drawn with, so
                # colouring a selection does not blank everything else.
                base = self._atom_rgba_array(n_atoms)
            else:
                base = np.asarray(current, dtype=float).copy()

            arr = np.asarray(colors, dtype=float)
            if arr.ndim != 2 or arr.shape[1] < 3:
                return False
            if arr.shape[1] == 3:
                arr = np.column_stack([arr, np.ones(arr.shape[0])])

            picked = np.asarray(indices, dtype=int)
            base[picked] = arr[:, :4]
            self._colors_per_atom_override = base

        self._update_view()
        return True

    def _atom_rgba_array(self, n_atoms: int) -> np.ndarray:
        """Per-atom colours as currently drawn, as an ``(n, 4)`` array."""
        try:
            rgba = self._atom_rgba(self._colors_per_ca)
            arr = np.asarray(rgba, dtype=float)
            if arr.ndim == 2 and arr.shape[0] == n_atoms:
                if arr.shape[1] == 3:
                    return np.column_stack([arr, np.ones(n_atoms)])
                return arr[:, :4].copy()
        except Exception:
            pass
        return np.ones((n_atoms, 4), dtype=float)

    def set_residue_colors(self, colors: np.ndarray | None) -> None:
        if colors is None:
            self._colors_per_residue_override = None
        else:
            arr = np.asarray(colors, dtype=float)
            if arr.ndim != 2 or arr.shape[1] < 3:
                return
            if self._residue_ids is None:
                return
            n_res = int(np.asarray(self._residue_ids).shape[0])
            if arr.shape[0] != n_res:
                return
            if arr.shape[1] == 3:
                alpha = np.ones((arr.shape[0], 1), dtype=float)
                arr = np.concatenate([arr, alpha], axis=1)
            self._colors_per_residue_override = arr
        if self._coords is not None:
            self._update_view()

    def set_object_visible(self, object_id: str, visible: bool) -> None:
        entry = self._objects.get(object_id)
        if entry is None:
            return
        entry.visible = bool(visible)
        self._update_view()

    def get_residue_positions(self, indices, *, object_id: str | None = None) -> np.ndarray:
        with self._activate_object(object_id):
            coords = self._coords
            if coords is None:
                return np.zeros((0, 3), dtype=float)
            arr = np.asarray(coords, dtype=float)
            if arr.ndim != 2 or arr.shape[1] != 3:
                return np.zeros((0, 3), dtype=float)
            if indices is None:
                idx = np.arange(arr.shape[0], dtype=int)
            else:
                try:
                    idx = np.asarray(list(indices), dtype=int)
                except Exception:
                    idx = np.zeros(0, dtype=int)
            if idx.size:
                idx = idx[(idx >= 0) & (idx < arr.shape[0])]
            if idx.size == 0:
                return np.zeros((0, 3), dtype=float)
            return arr[idx].copy()

    @staticmethod
    def _transform_pivot(state) -> np.ndarray | None:
        """Return the atom-space point the render arrays rotate about.

        The renderer stores ``(xyz - raw_center) * scale``, so every render-space
        rotation happens about ``raw_center`` expressed in Angstrom.

        Parameters
        ----------
        state : object
            The per-object state whose ``raw_center`` is read.

        Returns
        -------
        numpy.ndarray or None
            The ``(3,)`` pivot, or ``None`` when the object carries no centering
            metadata (then the render arrays are the raw coordinates and the
            origin is the pivot).
        """
        raw_center = getattr(state, "raw_center", None)
        if raw_center is None:
            return None
        try:
            return np.asarray(raw_center, dtype=float).reshape(3)
        except Exception:
            return None

    def object_raw_center(self, object_id: str | None = None) -> np.ndarray | None:
        """Return the Angstrom point an object's scene coordinates are centred on.

        Callers that compute a transform in Angstrom (``align``, ``pair_fit``)
        need this to express it in the scene units
        :meth:`apply_transform_to_object` takes.

        Parameters
        ----------
        object_id : str, optional
            Object to query; the active one by default.

        Returns
        -------
        numpy.ndarray or None
            The ``(3,)`` centre, or ``None`` for an unknown object or one
            without centering metadata.
        """
        entry = self._objects.get(object_id or self._active_object_id)
        if entry is None:
            return None
        return self._transform_pivot(entry.state)

    def apply_transform_to_object(
        self,
        rotation: np.ndarray,
        translation: np.ndarray,
        *,
        object_id: str | None = None,
    ) -> None:
        """Move one object rigidly, in **scene** units.

        The atom array follows in Angstrom, about the same pivot, so the two
        copies keep describing one geometry. A caller holding an Angstrom-space
        transform converts it with :meth:`object_raw_center` first.

        Parameters
        ----------
        rotation : (3, 3) ndarray
            Rotation applied to the scene coordinates.
        translation : (3,) ndarray
            Translation in scene units, applied after the rotation.
        object_id : str, optional
            Object to move; the active one by default.
        """
        rot, trans = _coerce_rotation_translation(rotation, translation)
        target_id = object_id if object_id is not None else self._active_object_id

        # PyMOL's editor snapshots coordinates before it moves them, which is what
        # makes `undo` mean anything: the ring is filled by the operations, not by
        # the undo command.
        self.push_undo(object_id=target_id)

        with self._activate_object(object_id):
            state = self._get_active_state()
            state.coords = _apply_rigid_transform(state.coords, rot, trans)
            state.center = _apply_rigid_transform(state.center, rot, trans)
            state.all_atom_coords = _apply_rigid_transform(state.all_atom_coords, rot, trans)
            state.frames = _apply_rigid_transform(state.frames, rot, trans)

            # The atom array is in Angstrom while everything above is in scene
            # units, so the translation has to come back through the scale. The
            # rotation is scale-free. Leaving the atom array untransformed --
            # which is what happened before -- desynchronised the two, and
            # `align`, `get_area`, `alter_state` and the distance selections all
            # read the stale one.
            #
            # The scene arrays are `(xyz - raw_center) * scale`, so a scene
            # transform (R, t) rotates the molecule about its *own centre*: in
            # atom space it reads `x' = R (x - c) + c + t / s`. Rotating the atom
            # array about the PDB origin instead leaves the two arrays describing
            # geometries that differ by `(I - R) c` -- tens of Angstrom for any
            # structure deposited away from the origin.
            scale = float(getattr(self, "_scale_factor", 1.0) or 1.0)
            atom_trans = trans / scale if scale else trans
            pivot = self._transform_pivot(state)
            if pivot is not None:
                atom_trans = atom_trans + pivot - rot @ pivot
            state.atoms = _apply_rigid_transform(state.atoms, rot, atom_trans)

            if state.coords is not None:
                center, radius = _compute_center_radius(state.coords)
                state.center = center
                state.radius = float(radius)

            # Keep global mirrors in sync when transforming the active object.
            if target_id == self._active_object_id:
                self._coords = state.coords
                self._center = state.center
                self._radius = state.radius

        self._update_view()

    def add_point_overlay(
        self,
        key: str,
        coords: np.ndarray,
        color: np.ndarray | Sequence[float] = (0.0, 1.0, 0.5, 0.6),
        size_scale: float = 0.03,
        min_size: float = 2.5,
        alpha: float = 0.6,
        transform_to_scene: bool = True,
        max_points: int | None = None,
    ) -> None:
        """Add or replace a named point-cloud overlay in the 3D view.

        The overlay is rendered as transparent spheres on top of the structure.
        Suitable for displaying AV point clouds, dye density distributions, or
        any set of 3D positions.

        Parameters
        ----------
        key : str
            Unique identifier for this overlay. Calling again with the same key
            replaces the existing overlay.
        coords : (N, 3) ndarray
            3D coordinates of the overlay points.
        color : (4,) array-like or (N, 4) array-like
            RGBA colour in [0, 1]. Broadcast scalar or per-point.
        size_scale : float
            Point size relative to the scene radius.
        min_size : float
            Minimum point size in world units.
        alpha : float
            Global alpha multiplier applied on top of the per-point alpha.
        transform_to_scene : bool, optional
            Whether to convert raw molecular coordinates into Chimol scene
            coordinates.
        max_points : int, optional
            Cap on the number of rendered points. A dense accessible-volume cloud
            is thousands of *transparent* sphere sprites, and the cost is fragment
            overdraw — proportional to the point count — not the CPU build. When
            the cloud exceeds the cap it is uniformly random-subsampled; the alpha
            is left untouched so the cloud stays see-through (a thinned cloud reads
            as slightly lighter, not opaque). Raise the cap for more density.
            Defaults to the ``overlay.max_points`` config value.
        """
        if self._point_overlays is None:
            self._point_overlays = {}
        scene_scale = self._world_to_scene_scale()
        if transform_to_scene:
            coords = self._transform_world_coords_to_scene(coords)

        coords = np.asarray(coords, dtype=float)
        color_arr = np.asarray(color, dtype=float)
        per_point_color = (
            color_arr.ndim == 2
            and color_arr.shape[0] == coords.shape[0]
        )

        if max_points is None:
            overlay_cfg = _DISPLAY_CONFIG.get("overlay", {})
            try:
                max_points = int(overlay_cfg.get("max_points", 30000))
            except Exception:
                max_points = 30000

        n = coords.shape[0]
        if max_points and n > max_points and coords.ndim == 2:
            rng = np.random.default_rng(0)
            idx = np.sort(rng.choice(n, int(max_points), replace=False))
            coords = coords[idx]
            if per_point_color:
                color = color_arr[idx]

        self._point_overlays[key] = {
            "coords": coords,
            "color": color,
            "size_scale": size_scale,
            "min_size": min_size * scene_scale,
            "alpha": alpha,
        }
        self._update_view()

    def add_surface_overlay(
        self,
        key: str,
        coords: np.ndarray,
        color: np.ndarray | Sequence[float] = (0.0, 1.0, 0.0, 0.35),
        alpha: float = 0.35,
        grid_spacing: float = 1.0,
        padding: float = 1.5,
        smoothing_sigma: float = 0.75,
        dilation_iterations: int = 1,
        max_dim: int = 96,
        fallback_size_scale: float = 0.025,
        fallback_min_size: float = 2.0,
    ) -> None:
        """Add or replace a named point-cloud surface overlay.

        Parameters
        ----------
        key : str
            Unique identifier for this overlay. Calling again with the same key
            replaces the existing overlay.
        coords : (N, 3) ndarray
            3D point cloud used to build the surface.
        color : (4,) array-like
            RGBA surface colour in [0, 1].
        alpha : float, optional
            Global alpha multiplier applied to the surface colour.
        grid_spacing : float, optional
            Target voxel spacing for point-cloud meshing.
        padding : float, optional
            Empty border around the point cloud before meshing.
        smoothing_sigma : float, optional
            Gaussian smoothing sigma in voxel units.
        dilation_iterations : int, optional
            Number of binary dilation passes before smoothing.
        max_dim : int, optional
            Maximum mesh grid dimension.
        fallback_size_scale : float, optional
            Point size scale if a mesh cannot be generated.
        fallback_min_size : float, optional
            Minimum point size if a mesh cannot be generated.
        """
        if self._point_overlays is None:
            self._point_overlays = {}
        scene_scale = self._world_to_scene_scale()
        coords = self._transform_world_coords_to_scene(coords)
        self._point_overlays[key] = {
            "coords": coords,
            "color": color,
            "alpha": alpha,
            "overlay_kind": "surface",
            "grid_spacing": grid_spacing * scene_scale,
            "padding": padding * scene_scale,
            "smoothing_sigma": smoothing_sigma,
            "dilation_iterations": dilation_iterations,
            "max_dim": max_dim,
            "size_scale": fallback_size_scale,
            "min_size": fallback_min_size * scene_scale,
        }
        self._update_view()

    def _transform_world_coords_to_scene(self, coords: np.ndarray) -> np.ndarray:
        """Transform raw molecular coordinates into Chimol scene coordinates.

        Parameters
        ----------
        coords : numpy.ndarray
            Raw world coordinates in the same units as the loaded structure.

        Returns
        -------
        numpy.ndarray
            Centered and scaled scene coordinates.
        """
        arr = np.asarray(coords, dtype=float)
        raw_center = getattr(self, "_raw_center", None)
        if raw_center is None:
            return arr
        try:
            center = np.asarray(raw_center, dtype=float).reshape(3)
        except Exception:
            return arr
        return (arr - center) * float(self._scale_factor)

    def _world_to_scene_scale(self) -> float:
        """Return the coordinate scale used for raw-to-scene overlays.

        Returns
        -------
        float
            The active structure scale if raw centering metadata is available,
            otherwise ``1.0``.
        """
        if getattr(self, "_raw_center", None) is None:
            return 1.0
        return float(self._scale_factor)

    def update_point_overlay(
        self,
        key: str,
        coords: np.ndarray,
        **kwargs,
    ) -> None:
        """Update the coordinates (and optionally style) of an existing overlay.

        If no overlay with *key* exists, behaves identically to
        :meth:`add_point_overlay`.
        """
        if self._point_overlays is None:
            self._point_overlays = {}
        if key not in self._point_overlays:
            self.add_point_overlay(key, coords, **kwargs)
        else:
            self._point_overlays[key]["coords"] = coords
            for k, v in kwargs.items():
                self._point_overlays[key][k] = v
            self._update_view()

    def remove_point_overlay(self, key: str) -> bool:
        """Remove a named point-cloud overlay.

        Returns True if the overlay existed and was removed.
        """
        if self._point_overlays is not None and key in self._point_overlays:
            del self._point_overlays[key]
            self._update_view()
            return True
        return False

    def clear_point_overlays(self) -> None:
        """Remove all point-cloud overlays from the view."""
        self._point_overlays = {}
        self._update_view()

    def add_sphere(
        self,
        center: np.ndarray,
        radius: float = 1.5,
        color: Sequence[float] = (1.0, 0.8, 0.2, 0.9),
        label: str | None = None,
        key: str | None = None,
        transform_to_scene: bool = True,
    ) -> str:
        """Place a single sphere at *center* (e.g. an AV mean position or attachment point).

        Parameters
        ----------
        center : (3,) array-like
            Sphere centre in Å.
        radius : float
            Sphere radius in Å (default 1.5 — about a Cβ).
        color : (4,) array-like
            RGBA colour in [0, 1].
        label : str, optional
            Text label placed next to the sphere.
        key : str, optional
            Overlay key; auto-generated as ``'sphere_<n>'`` if not provided.
        transform_to_scene : bool, optional
            Whether to convert raw molecular coordinates into Chimol scene
            coordinates.

        Returns
        -------
        key : str
            The overlay key used, for subsequent removal.
        """
        if self._point_overlays is None:
            self._point_overlays = {}
        if key is None:
            n = len([k for k in self._point_overlays if k.startswith("sphere_")])
            key = f"sphere_{n}"

        coords = np.asarray(center, dtype=float).reshape(1, 3)
        scene_scale = self._world_to_scene_scale()
        if transform_to_scene:
            coords = self._transform_world_coords_to_scene(coords)
        self._point_overlays[key] = {
            "coords": coords,
            "color": color,
            "size_scale": 0.0,
            "min_size": 2 * radius * scene_scale,
            "alpha": color[3] if len(color) > 3 else 1.0,
            "glyph": "sphere",
        }
        if label is not None:
            self._point_overlays[key]["label"] = label
        self._update_view()
        return key

    def remove_object(self, object_id: str) -> bool:
        if object_id not in self._objects:
            return False
        self._objects.pop(object_id, None)
        # Deleting the last member of a group must take the group with it, or
        # the panel keeps an empty row nothing can be dragged out of.
        self._prune_group_state()
        if self._active_object_id == object_id:
            self._active_object_id = None
        if self._objects:
            # Promote the first remaining non-placeholder object to active.
            for oid, entry in self._objects.items():
                if not entry.placeholder:
                    self._active_object_id = oid
                    break
            else:
                self._active_object_id = next(iter(self._objects))
        else:
            # Disable auto-creation when all objects are gone to avoid ghost entries.
            self._auto_create_enabled = False
        # If only placeholders remain, drop them.
        if self._objects and all(entry.placeholder for entry in self._objects.values()):
            self._objects.clear()
            self._active_object_id = None
            self._auto_create_enabled = False
        self._update_view()
        return True

    # ------------------------------------------------------------------
    # Groups (PyMOL ``group`` / ``ungroup`` / ``order``)
    # ------------------------------------------------------------------
    def group_names(self) -> list[str]:
        """Every group that currently has at least one member, in panel order.

        Derived from membership rather than kept as a list, so a group cannot
        outlive its last member as a phantom row -- which is what PyMOL's
        ``ExecutiveGroupPurge`` exists to clean up after.
        """
        seen: list[str] = []
        for entry in self._objects.values():
            if entry.group and entry.group not in seen:
                seen.append(entry.group)
        return seen

    def group_members(self, group: str) -> list[str]:
        """Object ids belonging to ``group``, in panel order."""
        name = str(group).strip()
        return [
            oid for oid, entry in self._objects.items()
            if entry.group == name and not entry.placeholder
        ]

    def set_object_group(self, object_id: str, group: str | None) -> bool:
        """Put an object in a group, or take it out with ``None``."""
        entry = self._objects.get(object_id)
        if entry is None:
            return False
        name = str(group).strip() if group else None
        if name and name == entry.name:
            # A group cannot contain itself; PyMOL rejects this too, and the
            # alternative is a row that is its own parent.
            return False
        entry.group = name or None
        if name:
            self._group_open.setdefault(name, True)
        self._prune_group_state()
        return True

    def is_group_open(self, group: str) -> bool:
        """Whether a group's members are shown in the panel."""
        return bool(self._group_open.get(str(group).strip(), True))

    def set_group_open(self, group: str, open_: bool) -> bool:
        """Expand or collapse a group row. False when no such group exists."""
        name = str(group).strip()
        if name not in self.group_names():
            return False
        self._group_open[name] = bool(open_)
        return True

    def _prune_group_state(self) -> None:
        """Forget the open/closed flag of groups that no longer have members."""
        live = set(self.group_names())
        for name in [n for n in self._group_open if n not in live]:
            self._group_open.pop(name, None)

    def reorder_objects(self, object_ids: list[str]) -> None:
        """Move the named objects into the given relative order.

        Objects not mentioned keep their positions relative to each other, and
        the named ones are placed at the first position any of them occupied --
        which is what PyMOL's ``order`` with the default ``location=current``
        does. Passing ids that do not exist is ignored rather than an error, so
        a script naming an object that failed to load still orders the rest.
        """
        wanted = [oid for oid in object_ids if oid in self._objects]
        if not wanted:
            return
        current = list(self._objects.keys())
        anchor = min(current.index(oid) for oid in wanted)
        rest = [oid for oid in current if oid not in wanted]
        # The anchor counts positions in the original list, so translate it to
        # an index into the remaining ones.
        before = [oid for oid in current[:anchor] if oid not in wanted]
        new_order = before + wanted + rest[len(before):]
        self._objects = OrderedDict((oid, self._objects[oid]) for oid in new_order)

    def move_objects_to_edge(self, object_ids: list[str], *, top: bool) -> None:
        """Move the named objects to the top or bottom of the panel."""
        wanted = [oid for oid in object_ids if oid in self._objects]
        if not wanted:
            return
        rest = [oid for oid in self._objects if oid not in wanted]
        new_order = wanted + rest if top else rest + wanted
        self._objects = OrderedDict((oid, self._objects[oid]) for oid in new_order)

    def copy_object(self, object_id: str, *, name: str | None = None) -> str | None:
        """Create a deep copy of an existing loaded object."""
        entry = self._objects.get(object_id)
        if entry is None:
            return None
        copied = self._create_object(
            name=name or f"{entry.name}_copy",
            source_path=entry.source_path,
            placeholder=entry.placeholder,
        )
        copied.state = copy_state(entry.state)
        copied.visible = bool(entry.visible)
        # `object_id`, not `id`: the entry has no `id`, so this raised
        # AttributeError, which the `copy` command caught as "no such method" and
        # answered with a fallback that left a second, broken object behind.
        self._active_object_id = copied.object_id
        self._update_view()
        return copied.object_id

    # ------------------------------------------------------------------
    # Animation API
    # ------------------------------------------------------------------
    def get_total_frames(self) -> int:
        return self._total_frames

    def set_total_frames(self, count: int) -> None:
        self._total_frames = max(1, int(count))
        if self._current_frame >= self._total_frames:
            self._current_frame = self._total_frames - 1
        self._update_view()

    def get_current_frame(self) -> int:
        return self._current_frame

    #: Trajectory frames advanced per displayed playback step (``mplay 5``).
    movie_step: float = 1.0

    #: Positions drawn between successive frames (``minterpolate``); 1 is off.
    movie_interpolate: int = 1

    def get_frame_position(self) -> float:
        """Where playback actually is, which may be between two frames."""
        return float(getattr(self, "_frame_position", self._current_frame))

    def set_frame_position(self, position: float) -> None:
        """Show a possibly fractional point on the timeline.

        A whole number is a stored frame; anything between two is interpolated.
        This is what lets playback advance by less than a frame at a time, so a
        trajectory whose frames are far apart still moves smoothly.
        """
        self._sync_timeline_length()
        limit = max(self._total_frames - 1, 0)
        try:
            pos = float(position)
        except (TypeError, ValueError):
            return
        if not np.isfinite(pos):
            return
        pos = min(max(pos, 0.0), float(limit))
        if abs(pos - self.get_frame_position()) < 1e-9:
            return
        self._frame_position = pos
        self._current_frame = int(np.floor(pos))
        self._apply_frame_states()
        self._note_frame_change()
        self._update_view(fit_camera=False)

    def _sync_timeline_length(self) -> None:
        """Grow the timeline to fit frames attached outside it."""
        try:
            active_state = self._get_active_state()
            state_frames = getattr(active_state, "frames", None)
        except Exception:
            return
        if state_frames is None or getattr(state_frames, "ndim", 0) != 3:
            return
        try:
            n_states = int(state_frames.shape[0])
        except Exception:
            return
        if n_states > self._total_frames:
            self._total_frames = n_states

    def set_current_frame(self, frame_idx: int) -> None:
        """Jump the timeline to a whole frame.

        Delegates, rather than keeping its own idea of where playback is: a
        second copy of the position is exactly the thing that drifts, and the
        symptom would be a spinbox and a picture disagreeing about which frame
        is on screen.
        """
        try:
            self.set_frame_position(int(frame_idx))
        except (TypeError, ValueError):
            return

    def _select_state_frame(
        self,
        state: _MolViewObjectState,
        index: int,
    ) -> int:
        """Select one trajectory frame and expose it as render geometry.

        Chimol stores trajectories in ``state.frames`` but all render paths
        consume ``state.coords`` / ``state.all_atom_coords``. Keeping that
        derived state in one place prevents accidental rendering of the whole
        ``(T, N, 3)`` trajectory array.
        """
        frames = getattr(state, "frames", None)
        if frames is None:
            return 0
        try:
            arr = np.asarray(frames, dtype=float)
        except Exception:
            return 0
        if arr.ndim != 3 or arr.shape[2] != 3 or arr.shape[0] == 0:
            return 0

        n_frames = int(arr.shape[0])
        idx, blend, next_idx = _frame_blend(index, n_frames)
        if blend > 0.0:
            # Between two stored frames: straight-line interpolation of every
            # atom. Motion between saved frames is not linear in truth, but over
            # one frame's worth of it the error is far smaller than the jump the
            # eye sees without it -- and it lets playback be smooth without
            # storing, or recomputing, more frames than there are.
            frame = (1.0 - blend) * arr[idx] + blend * arr[next_idx]
        else:
            frame = np.asarray(arr[idx], dtype=float)

        state.active_frame = idx
        state.frame_position = float(idx) + blend
        # Coordinate-only trajectories should not leave stale all-atom data in
        # atom rendering paths. Reuse all-atom coords only when dimensions match.
        all_atom_coords = getattr(state, "all_atom_coords", None)
        frame_matches_all_atoms = False
        if all_atom_coords is None:
            state.all_atom_coords = frame
        else:
            try:
                all_atom_arr = np.asarray(all_atom_coords)
                if all_atom_arr.ndim == 2 and all_atom_arr.shape == frame.shape:
                    state.all_atom_coords = frame
                    frame_matches_all_atoms = True
                elif all_atom_arr.ndim == 3 and all_atom_arr.shape[1:] == frame.shape:
                    state.all_atom_coords = np.asarray(all_atom_arr[idx], dtype=float)
                    frame_matches_all_atoms = True
                else:
                    state.all_atom_coords = frame
            except Exception:
                state.all_atom_coords = frame

        if state.atoms is not None and not frame_matches_all_atoms:
            try:
                atoms_xyz = np.asarray(state.atoms["xyz"], dtype=float)
                if atoms_xyz.shape != frame.shape:
                    state.atoms = None
                    state.all_atom_res_ids = None
                    state.all_atom_radii = None
                    state.bond_pairs = None
                    if state.residue_ids is not None and len(state.residue_ids) != frame.shape[0]:
                        state.residue_ids = None
                        state.residue_names = None
                        state.residue_oneletter = None
                        state.residue_chain_ids = None
                        state.secondary_structure = None
                        state.trace_ups = None
            except Exception:
                state.atoms = None
                state.all_atom_res_ids = None
                state.all_atom_radii = None
                state.bond_pairs = None
                if state.residue_ids is not None and len(state.residue_ids) != frame.shape[0]:
                    state.residue_ids = None
                    state.residue_names = None
                    state.residue_oneletter = None
                    state.residue_chain_ids = None
                    state.secondary_structure = None
                    state.trace_ups = None

        # All-atom frames: set_frames already re-centered and scaled them.
        # Extract the CA trace so residue-level rendering (cartoon, trace,
        # labels) stays intact. Always replace state.coords; frames usually
        # have the same shape, so a shape-change guard would keep rendering
        # the first conformation while only all-atom overlays move.
        selected_coords = None
        if frame_matches_all_atoms and state.residue_ids is not None:
            try:
                ca_idx = getattr(state, "_ca_indices", None)
                if ca_idx is not None and len(ca_idx) > 0 and ca_idx.max() < frame.shape[0]:
                    ca_coords = frame[ca_idx]
                    if ca_coords.shape[0] == len(state.residue_ids):
                        selected_coords = ca_coords
            except Exception:
                pass
        if selected_coords is None:
            selected_coords = frame
        state.coords = selected_coords

        # Sync atoms["xyz"] to the raw (unscaled) frame coordinates so that
        # _build_trace_ups uses the current backbone geometry rather than the
        # stale coordinates from the initial add_structure call.  Without this,
        # the ribbon normals (C→O vectors) are frozen at the starting
        # conformation and the cartoon appears twisted/tangled as the MC moves
        # the backbone.
        if (
            frame_matches_all_atoms
            and state.atoms is not None
            and state.residue_ids is not None
        ):
            try:
                frames_raw = getattr(state, "frames_raw", None)
                if frames_raw is not None:
                    raw_arr = np.asarray(frames_raw, dtype=float)
                    if raw_arr.ndim == 3 and raw_arr.shape[0] > idx and raw_arr.shape[1:] == frame.shape:
                        # Interpolated exactly like the render coordinates were.
                        # Taking the floor frame here instead would orient the
                        # ribbon from one frame while drawing it at another.
                        raw_blend = float(getattr(state, "frame_position", idx)) - idx
                        if raw_blend > 0.0 and raw_arr.shape[0] > idx + 1:
                            raw_frame = (
                                (1.0 - raw_blend) * raw_arr[idx]
                                + raw_blend * raw_arr[idx + 1]
                            )
                        else:
                            raw_frame = raw_arr[idx]
                    else:
                        raw_frame = None
                else:
                    raw_frame = None
                if raw_frame is not None and raw_frame.shape == state.atoms["xyz"].shape:
                    state.atoms = state.atoms.copy()
                    state.atoms["xyz"] = raw_frame
                    # Only ``xyz`` changed, so which atom is which residue's
                    # backbone N/C/O is still true. Rebuilding that map was the
                    # single most expensive part of a frame change -- it costs
                    # ``n_res * n_atoms`` comparisons and a full string
                    # conversion of every atom name.
                    if state.backbone_map is None:
                        state.backbone_map = backbone_index_map(
                            state.atoms,
                            state.residue_ids,
                            state.residue_chain_ids,
                        )
                    state.trace_ups = _build_trace_ups(
                        state.atoms,
                        state.residue_ids,
                        selected_coords,
                        state.residue_chain_ids,
                        index_map=state.backbone_map,
                    )
            except Exception:
                pass

        try:
            center, radius = _compute_center_radius(
                state.all_atom_coords
                if frame_matches_all_atoms and state.all_atom_coords is not None
                else state.coords
            )
            state.center = center
            state.radius = float(radius)
        except Exception:
            pass

        coords_len = state.coords.shape[0] if state.coords is not None else frame.shape[0]
        all_atom_len = (
            np.asarray(state.all_atom_coords).shape[0]
            if state.all_atom_coords is not None
            else coords_len
        )

        if state.cartoon_mask is None or len(state.cartoon_mask) != coords_len:
            state.cartoon_mask = np.ones(coords_len, dtype=bool)
        if state.ball_mask is None or len(state.ball_mask) not in (coords_len, all_atom_len):
            state.ball_mask = np.zeros(coords_len, dtype=bool)
        return idx

    def _apply_frame_states(self) -> None:
        """Update scene objects based on the current frame position."""
        # For objects with 'frames' coordinate sets, update their active_frame
        position = float(getattr(self, "_frame_position", self._current_frame))
        for entry in self._objects.values():
            state = entry.state
            if state.frames is not None and state.frames.ndim == 3:
                # If the object has frames, map the global timeline to its states.
                # Simplest mapping: state_idx = global_idx % n_states
                n_states = state.frames.shape[0]
                # Modulo on the *fractional* position, so interpolation survives
                # the wrap instead of snapping to a whole frame at the seam.
                self._select_state_frame(state, position % n_states)
                # Also update center/radius if needed, but maybe defer for performance?
                # PyMOL usually doesn't re-center automatically during movie playback.

    def list_objects(self) -> list[dict]:
        objects: list[dict] = []
        for entry in self._objects.values():
            if entry.placeholder:
                continue
            state = entry.state
            has_geometry = state.coords is not None and state.coords.size > 0 if state.coords is not None else False
            objects.append(
                {
                    "id": entry.object_id,
                    "name": entry.name,
                    "visible": entry.visible,
                    "source_path": entry.source_path,
                    "has_geometry": bool(has_geometry),
                    "group": entry.group,
                    "group_open": (
                        self.is_group_open(entry.group) if entry.group else True
                    ),
                }
            )
        return objects

    # ------------------------------------------------------------------
    # Chain utilities
    # ------------------------------------------------------------------
    def get_chain_ids(self, object_id: str | None = None) -> list[str]:
        """Return sorted chain identifiers for the given object (or active)."""
        with self._activate_object(object_id):
            state = self._get_active_state()
            chains = state.residue_chain_ids
            if chains is None:
                return []
            try:
                arr = np.asarray(chains)
                uniq = np.unique(arr)
                uniq = uniq[uniq != ""]
                return [str(x) for x in uniq]
            except Exception:
                return []


    def create_from_selection(
        self,
        mask: np.ndarray,
        *,
        name: str,
        source_id: str | None = None,
        extract: bool = False,
    ) -> str | None:
        """Make a new object from a selection (PyMOL ``create`` / ``extract``).

        ``extract`` additionally removes the atoms from the source, which is the
        only difference between the two commands in PyMOL.

        The new object is placed **in the same frame as its parent**. Every object
        is otherwise centred on its own centroid for rendering, so a subset would
        be drawn at the scene origin and appear to jump away from the structure it
        came from. The fix is applied to the *render-space* arrays only: the stored
        ``atoms["xyz"]`` keeps its true coordinates, so ``save`` on the new object
        writes where the atoms really are rather than where they are drawn. An
        earlier approach (still visible in ``split_chains``) shifted the stored
        coordinates instead, which looks identical on screen and writes a wrong
        file.

        Parameters
        ----------
        mask : numpy.ndarray
            Boolean per-atom selection into the source object.
        name : str
            Name for the new object.
        source_id : str, optional
            Object to take atoms from; defaults to the active one.
        extract : bool, optional
            Remove the atoms from the source as well.

        Returns
        -------
        str or None
            The new object's id, or ``None`` when the selection was empty or the
            source has no atoms.
        """
        source = source_id or self._active_object_id
        entry = self._objects.get(source) if source else None
        if entry is None:
            return None

        atoms = getattr(entry.state, "atoms", None)
        if atoms is None or getattr(atoms.dtype, "fields", None) is None:
            return None

        keep = np.asarray(mask, dtype=bool)
        if keep.shape[0] != len(atoms) or not keep.any():
            return None

        parent_centre = np.asarray(entry.state.raw_center, dtype=float) \
            if entry.state.raw_center is not None else None

        class _Subset:
            """The minimal shape :meth:`add_structure` needs."""

        subset = _Subset()
        subset.atoms = atoms[keep].copy()
        subset.xyz = np.asarray(subset.atoms["xyz"], dtype=float)
        subset.n_atoms = int(len(subset.atoms))

        new_id = self.add_structure(
            subset, name=name, source_path=entry.source_path
        )
        if new_id is None:
            return None

        if parent_centre is not None:
            self._reframe_to(new_id, parent_centre)

        if extract:
            self._remove_atoms(source, keep)

        # Adding an object makes it active, which would silently re-scope the next
        # command: `create sugars, resn NAG` followed by `extract stem, resn DAL`
        # would look for DAL inside `sugars` and report that nothing matched. The
        # source stays active, as it does in PyMOL, where creating an object does
        # not change what an unqualified selection means.
        if self._objects.get(source) is not None:
            self._active_object_id = source

        self._update_view()
        return new_id

    def _reframe_to(self, object_id: str, centre: np.ndarray) -> None:
        """Redraw an object about ``centre`` instead of its own centroid.

        Only the render-space arrays move; the stored coordinates are the truth
        and must not be touched (see :meth:`create_from_selection`).
        """
        with self._activate_object(object_id):
            own = self._raw_center
            if own is None:
                return
            shift = (np.asarray(own, dtype=float) - np.asarray(centre, dtype=float))
            shift = shift * float(self._scale_factor)
            for attr in ("_coords", "_all_atom_coords"):
                arr = getattr(self, attr, None)
                if arr is not None:
                    setattr(self, attr, np.asarray(arr, dtype=float) + shift)
            self._raw_center = np.asarray(centre, dtype=float)

    def _remove_atoms(self, object_id: str, mask: np.ndarray) -> None:
        """Drop the masked atoms from an object (the ``extract`` half).

        Rebuilt through :meth:`add_structure`'s own path rather than by editing
        the arrays in place, because a dozen derived arrays -- the trace, the
        secondary structure, the bond list, every per-atom mask -- would otherwise
        be left describing atoms that are no longer there.
        """
        entry = self._objects.get(object_id)
        if entry is None:
            return
        atoms = getattr(entry.state, "atoms", None)
        if atoms is None:
            return

        keep = ~np.asarray(mask, dtype=bool)
        centre = entry.state.raw_center
        if not keep.any():
            self.remove_object(object_id)
            return

        class _Remaining:
            """The minimal shape :meth:`set_structure` needs."""

        remaining = _Remaining()
        remaining.atoms = atoms[keep].copy()
        remaining.xyz = np.asarray(remaining.atoms["xyz"], dtype=float)
        remaining.n_atoms = int(len(remaining.atoms))

        with self._activate_object(object_id):
            self.set_structure(remaining)
        if centre is not None:
            self._reframe_to(object_id, np.asarray(centre, dtype=float))

    def split_chains(self, *, prefix: str | None = None, object_ids: list[str] | None = None) -> int:
        """Create a new object for each chain in the specified objects.

        Returns the number of new objects created. Original objects are
        hidden (disabled) after splitting, similar to PyMOL.
        """
        target_ids = object_ids or list(self._objects.keys())
        created = 0

        for obj_id in target_ids:
            entry = self._objects.get(obj_id)
            if entry is None:
                continue
            atoms = entry.state.atoms
            if atoms is None or getattr(atoms.dtype, "fields", None) is None:
                continue
            fields = set(atoms.dtype.fields or {})
            if "chain" not in fields:
                continue

            try:
                chains = np.char.strip(atoms["chain"].astype(str))
            except Exception:
                chains = np.array([str(c).strip() for c in atoms["chain"]])

            # Compute the original object's center so each chain sub-object
            # can be positioned relative to the same origin.
            all_xyz = np.asarray(atoms["xyz"], dtype=float)
            orig_center, _ = _compute_center_radius(all_xyz)

            unique_chains = np.unique(chains)
            for chain_id in unique_chains:
                chain_str = str(chain_id)
                mask = chains == chain_id
                if not mask.any():
                    continue
                sub_atoms = atoms[mask].copy()
                # Shift the chain's raw coordinates so its center matches
                # the original object's center. This ensures the chain
                # stays in the same position after splitting.
                sub_xyz = sub_atoms["xyz"]
                chain_center = np.asarray(sub_xyz, dtype=float).mean(axis=0)
                sub_xyz[:] = np.asarray(sub_xyz, dtype=float) + (orig_center - chain_center)
                # Build a simple structure-like container
                class _Struct:
                    pass
                struct = _Struct()
                struct.atoms = sub_atoms

                created += 1
                if prefix:
                    name = f"{prefix}{created:04d}"
                else:
                    base = entry.name or obj_id
                    name = f"{base}_{chain_str or ''}"

                self.add_structure(struct, name=name, source_path=entry.source_path)

            # Hide original object after splitting
            entry.visible = False

        if created > 0:
            self._update_view()
        return created

    def add_structure(
        self,
        structure: object,
        *,
        name: str | None = None,
        source_path: str | None = None,
    ) -> str:
        entry = self._create_object(name=name, source_path=source_path)
        self.set_structure(structure)
        self._apply_deposited_secondary_structure(source_path)
        return entry.object_id

    def _apply_deposited_secondary_structure(self, source_path: str | None) -> None:
        """Prefer a PDB file's own HELIX/SHEET records over the computed codes.

        The depositor's annotation is the authority for a deposited structure,
        and it is also what PyMOL displays — PyMOL only recomputes when asked
        with ``dss``, or when the file carries no records. Files without them
        keep the computed assignment.

        Parameters
        ----------
        source_path : str or None
            Path the object was loaded from; anything that is not a readable PDB
            simply leaves the computed codes in place.
        """
        if not source_path or self._residue_ids is None:
            return
        # parse_pdb_secondary_structure logs and returns None on any failure, so
        # a malformed header degrades to the computed assignment.
        records = parse_pdb_secondary_structure(source_path)
        if not records:
            return

        res_ids = np.asarray(self._residue_ids)
        chain_ids = getattr(self, "_residue_chain_ids", None)
        codes = []
        matched = 0
        for i in range(res_ids.shape[0]):
            chain = ""
            if chain_ids is not None and i < len(chain_ids):
                chain = str(chain_ids[i]).strip()
            code = records.get((chain, int(res_ids[i])))
            if code is None:
                codes.append("C")
            else:
                codes.append(code)
                matched += 1
        if matched:
            self.set_secondary_structure_codes(codes)

    # ------------------------------------------------------------------
    # Info overlay API
    # ------------------------------------------------------------------

    def set_system_info_visible(self, visible: bool) -> None:
        self._info_visible = bool(visible)
        if self._info_overlay is not None:
            self._info_overlay.setVisible(self._info_visible)

    def set_system_info_text(self, text: str) -> None:
        self._info_text = str(text)
        if self._info_overlay is not None:
            self._info_overlay.setPlainText(self._info_text)
            self._info_overlay.setVisible(self._info_visible)

    def add_coordinates(
        self,
        coords: np.ndarray,
        *,
        name: str | None = None,
        source_path: str | None = None,
        trace_coords: np.ndarray | None = None,
        res_ids: np.ndarray | None = None,
        res_names: np.ndarray | None = None,
        chain_ids: np.ndarray | None = None,
        atoms: np.ndarray | None = None,
    ) -> str:
        entry = self._create_object(name=name, source_path=source_path)
        self.set_coordinates(
            coords,
            trace_coords=trace_coords,
            res_ids=res_ids,
            res_names=res_names,
            chain_ids=chain_ids,
            atoms=atoms,
        )
        self._apply_deposited_secondary_structure(source_path)
        return entry.object_id

    @contextmanager
    def _activate_object(self, object_id: str | None):
        prev = self._active_object_id
        if object_id is not None and object_id in self._objects:
            self._active_object_id = object_id
        self._ensure_active_entry(create_if_missing=False)
        try:
            yield
        finally:
            self._active_object_id = prev

    @staticmethod
    def _normalize_mouse_mode(mode: Any) -> str:
        """Return a valid mouse rotation mode string.

        Parameters
        ----------
        mode : Any
            Candidate mode value (typically ``"pymol"`` or ``"chimol"``).

        Returns
        -------
        str
            ``"pymol"`` or ``"chimol"``. Unrecognised values fall back to
            ``"pymol"``.
        """
        mode_str = str(mode).lower().strip()
        if mode_str == "chimol":
            return "chimol"
        return "pymol"

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        background: str | None = None,
        *,
        representation_mode: str | None = None,
        show_cartoon: bool | None = None,
        show_trace: bool | None = None,
        show_atoms: bool | None = None,
        show_sticks: bool | None = None,
        sidechains_visible: bool | None = None,
        grid_visible: bool | None = None,
        surface_visible: bool | None = None,
        scale_factor: float | None = None,
    ) -> None:
        super().__init__(parent)

        self._objects: OrderedDict[str, _MolViewObjectEntry] = OrderedDict()
        self._active_object_id: str | None = None
        self._object_counter: int = 0
        # Groups hold only what is *not* derivable from their members: whether
        # the row is expanded. Membership lives on the member entry, so a group
        # cannot disagree with its objects about who belongs to it.
        self._group_open: dict[str, bool] = {}
        # Coordinate undo is per object, as PyMOL's is; see renderer/undo.py.
        self._undo_rings: dict[str, UndoRing] = {}
        # Allow creating an initial entry during startup; turned off when last object is deleted.
        self._auto_create_enabled: bool = True

        # Animation / Timeline state
        self._total_frames: int = 1
        self._current_frame: int = 0  # 0-indexed internally
        self._keyframes: dict[int, dict] = {}
        self._animation_running: bool = False
        self._animation_timer: QtCore.QTimer | None = None
        self.selection_mode: str = "Residues"

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view: QtWidgets.QWidget | None = None
        self._disabled_label: QtWidgets.QLabel | None = None
        self._container: QtWidgets.QWidget | None = None
        self._ray_overlay: QtWidgets.QLabel | None = None

        # Stored geometry
        self._coords: np.ndarray | None = None
        self._center: np.ndarray | None = None
        self._radius: float = 1.0

        self._atoms = None
        self._all_atom_coords = None
        self._all_atom_res_ids = None
        self._all_atom_radii = None
        self._atom_features = {}
        self._atom_feature_meta = {}

        # Residue / sequence metadata (valid when a Structure is set)
        self._residue_ids = None
        self._residue_names = None
        self._residue_oneletter = None
        self._residue_chain_ids = None
        self._selected_residues = []

        display_defaults = _DISPLAY_CONFIG.get("defaults", {})
        scaling_cfg = _DISPLAY_CONFIG.get("scaling", {})
        camera_cfg = _DISPLAY_CONFIG.get("camera", {})

        # Coloring state
        # "single", "by_residue" (AA type), "by_secondary_structure" (H/E/C)
        # or "by_sequence" (gradient along the CA index)
        self._color_mode = str(
            display_defaults.get("color_mode", "single")
        )
        colors_cfg = _DISPLAY_CONFIG.get("colors", {})
        base_col = np.asarray(colors_cfg.get("base", [0.8, 0.8, 1.0, 1.0]), dtype=float)
        if base_col.shape[0] != 4:
            base_col = np.array([0.8, 0.8, 1.0, 1.0], dtype=float)
        self._base_color_single = tuple(float(x) for x in base_col)
        self._colors_per_ca = None
        self._colors_per_residue_override = None
        self._colors_per_atom_override = None
        self._secondary_structure = None

        rep_mode_default = str(display_defaults.get("representation_mode", "cartoon")).lower()
        self._representation_mode = str(
            representation_mode or rep_mode_default
        ).lower()
        self._trace_ups = None

        # Global representation flags to allow independent toggling from the
        # plugin UI (cartoon / trace / atoms / sticks).
        self._show_cartoon = bool(
            show_cartoon if show_cartoon is not None else display_defaults.get("show_cartoon", True)
        )
        self._show_trace = bool(
            show_trace if show_trace is not None else display_defaults.get("show_trace", False)
        )
        self._show_atoms = bool(
            show_atoms if show_atoms is not None else display_defaults.get("show_atoms", False)
        )
        self._show_dots = bool(display_defaults.get("show_dots", False))
        self._show_sticks = bool(
            show_sticks if show_sticks is not None else display_defaults.get("show_sticks", False)
        )

        # Side-chain visibility flag for atom / ball view.
        self._sidechains_visible = bool(
            sidechains_visible if sidechains_visible is not None else display_defaults.get("sidechains_visible", True)
        )

        # Per-residue representation masks (per CA index)
        self._cartoon_mask = None
        self._ball_mask = None

        # Cached bond list for sticks representation: array of shape (M, 2)
        # with integer indices into the all-atom coordinate array.
        self._bond_pairs = None

        self._info_text: str = ""
        self._info_visible: bool = False
        self._info_overlay: QtWidgets.QPlainTextEdit | None = None

        # Render backend
        self._renderer: Renderer | None = None
        self._point_overlays = {}

        # Reference plane (grid) is hidden by default; the toolbar button
        # can toggle it on when needed.
        self._grid_visible: bool = bool(
            grid_visible if grid_visible is not None else display_defaults.get("grid_visible", False)
        )

        self._surface_visible: bool = bool(
            surface_visible if surface_visible is not None else display_defaults.get("surface_visible", False)
        )

        self._scale_factor = float(
            scale_factor if scale_factor is not None else scaling_cfg.get("structure", 10.0)
        )

        def _camera_val(key: str, default: float) -> float:
            try:
                return float(camera_cfg.get(key, default))
            except Exception:
                return float(default)

        self._camera_min_near_clip = max(_camera_val("min_near_clip", 0.005), 1e-4)
        self._camera_max_near_clip = max(
            _camera_val("max_near_clip", 5.0), self._camera_min_near_clip * 1.01
        )
        self._camera_near_clip = min(
            max(_camera_val("near_clip", 0.1), self._camera_min_near_clip), self._camera_max_near_clip
        )
        far_default = _camera_val("far_clip", 1000.0)
        self._camera_far_clip = far_default if far_default > self._camera_near_clip else self._camera_near_clip * 200.0
        clip_wheel_scale = _camera_val("clip_wheel_scale", 0.85)
        if not (0.0 < clip_wheel_scale < 1.0):
            clip_wheel_scale = 0.85
        self._camera_clip_wheel_scale = clip_wheel_scale

        self._mouse_mode = self._normalize_mouse_mode(
            camera_cfg.get("mouse_mode", "pymol")
        )

        # Camera defaults
        self._default_elevation = 20
        self._default_azimuth = 45
        self._scene: Scene | None = None

        info_cfg = _DISPLAY_CONFIG.get("info_overlay", {})

        try:
            renderer = QtGLRenderer(controller=self, parent=self)
        except Exception:
            renderer = None

        if renderer is not None:
            container = QtWidgets.QWidget(self)
            container_layout = QtWidgets.QGridLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)
            container_layout.setRowStretch(0, 1)
            container_layout.setColumnStretch(0, 1)

            self._info_overlay = QtWidgets.QPlainTextEdit(container)
            self._info_overlay.setReadOnly(True)
            max_width = int(info_cfg.get("max_width", 260))
            min_width = int(info_cfg.get("min_width", 180))
            self._info_overlay.setMaximumWidth(max_width)
            self._info_overlay.setMinimumWidth(min_width)
            self._info_overlay.setSizePolicy(
                QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.MinimumExpanding
            )
            full_height = bool(info_cfg.get("full_height", True))
            self._info_overlay.setPlainText(self._info_text or "(no system loaded)")
            style = info_cfg.get(
                "stylesheet",
                "background-color: rgba(0, 0, 0, 180);"
                "color: white;"
                "border: 1px solid rgba(255, 255, 255, 80);",
            )
            self._info_overlay.setStyleSheet(style)
            self._info_overlay.setFrameStyle(QtWidgets.QFrame.NoFrame)
            self._info_overlay.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            self._info_overlay.viewport().setAutoFillBackground(False)
            self._info_overlay.setVisible(self._info_visible)

            self._renderer = renderer
            self.view = self._renderer.widget()
            self._container = container
            bg = background if background is not None else _DISPLAY_CONFIG.get(
                "background", "k"
            )
            self._renderer.set_background_color(bg)
            grid_cfg = _DISPLAY_CONFIG.get("grid", {})
            g_size = float(grid_cfg.get("size", 20.0))
            g_spacing = float(grid_cfg.get("spacing", 1.0))
            self._renderer.configure_grid(g_size, g_spacing)
            self._renderer.set_grid_visible(self._grid_visible)
            configure_camera = getattr(self._renderer, "configure_camera", None)
            if callable(configure_camera):
                configure_camera(
                    near_clip=self._camera_near_clip,
                    far_clip=self._camera_far_clip,
                    min_near_clip=self._camera_min_near_clip,
                    max_near_clip=self._camera_max_near_clip,
                    clip_wheel_scale=self._camera_clip_wheel_scale,
                )
            set_mouse_mode = getattr(self._renderer, "set_mouse_mode", None)
            if callable(set_mouse_mode):
                set_mouse_mode(self._mouse_mode)
            renderer_widget = self._renderer.widget()
            renderer_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )
            container_layout.addWidget(renderer_widget, 0, 0)
            container_layout.addWidget(
                self._info_overlay,
                0,
                0,
                2 if full_height else 1,
                1,
                alignment=QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop,
            )
            self._info_overlay.raise_()
            layout.addWidget(container, 1)
        else:
            self._renderer = None

        if self._renderer is None:
            self._show_disabled_label()

        # Register to recompute representations when display config changes.
        self._config_listener = self._on_display_config_changed
        register_update_listener(self._config_listener)
        self.destroyed.connect(self._unregister_config_listener)

    # ------------------------------------------------------------------
    # Public properties for accessing CA trace data
    # ------------------------------------------------------------------
    @property
    def ca_indices(self):
        """NumPy array of indices into the atoms array for CA atoms, or None."""
        return self._ca_indices

    @property
    def residue_ids_for_ca_trace(self):
        """NumPy array of residue ids for the CA trace, or None."""
        return self._residue_ids

    def _unregister_config_listener(self) -> None:
        """Remove the config-change listener on widget destruction."""
        try:
            unregister_update_listener(self._config_listener)
        except Exception:
            pass

    def _on_display_config_changed(self) -> None:
        """Recompute scene objects when display config is reloaded."""
        try:
            camera_cfg = _DISPLAY_CONFIG.get("camera", {})
            self.set_mouse_mode(camera_cfg.get("mouse_mode", "pymol"))
        except Exception:
            pass
        if getattr(self, "_coords", None) is not None:
            try:
                self._update_view()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_structure(self, structure: object) -> None:
        """Set structure from a ChiSurf ``Structure``-like object.

        The object is expected to provide either:
        - ``atoms``: NumPy structured array with fields ``'xyz'`` and
          ``'atom_name'`` (as in :mod:`chisurf.core.structure`), or
        - ``xyz``: array-like of shape ``(N, 3)``.
        """
        self._atoms = None
        self._all_atom_coords = None
        self._all_atom_res_ids = None
        self._all_atom_radii = None
        self._atom_features = {}
        self._atom_feature_meta = {}
        self._show_atom_gaussians = False
        self._bond_pairs = None
        self._bond_pairs = None
        self._secondary_structure = None

        # Case 1: explicit atoms array with xyz/atom_name fields (preferred)
        atoms = getattr(structure, "atoms", None)
        if isinstance(atoms, np.ndarray) and {"xyz", "atom_name"}.issubset(
            set(atoms.dtype.fields or {})
        ):
            self._atoms = atoms
            fields_atoms = set(atoms.dtype.fields or {})

            coords_all_raw: np.ndarray | None
            try:
                coords_all_raw = np.asarray(atoms["xyz"], dtype=float)
            except Exception:
                coords_all_raw = None
            self._all_atom_coords = None if coords_all_raw is None else coords_all_raw.copy()
            if "res_id" in fields_atoms:
                try:
                    self._all_atom_res_ids = np.asarray(atoms["res_id"])
                except Exception:
                    self._all_atom_res_ids = None
            else:
                self._all_atom_res_ids = None
            if "radius" in fields_atoms:
                try:
                    self._all_atom_radii = np.asarray(atoms["radius"], dtype=float)
                except Exception:
                    self._all_atom_radii = None
            else:
                self._all_atom_radii = None

            # Pre-compute simple covalent bonds for sticks representation
            # using a distance cutoff in *raw* (unscaled) coordinates so the
            # list is independent of the global scaling we apply for viewing.
            self._bond_pairs = self._apply_bond_edits(
                self._infer_bonds(coords_all_raw, atoms)
            )

            coords, res_ids, res_names, chain_ids = _extract_ca_trace(atoms)
            if coords is None:
                coords = np.asarray(atoms["xyz"], dtype=float)
                res_ids = None
                res_names = None
                chain_ids = None

            self._residue_ids = res_ids
            self._residue_names = res_names
            self._residue_oneletter = _three_to_one_array(res_names)
            self._residue_chain_ids = chain_ids

            coords_arr = np.asarray(coords, dtype=float)

            # Determine a common center/radius from all atoms if available,
            # otherwise from the CA trace, then center and scale geometry.
            if self._all_atom_coords is not None:
                center, radius = _compute_center_radius(self._all_atom_coords)
            else:
                center, radius = _compute_center_radius(coords_arr)

            scale = float(self._scale_factor)
            coords_arr = (coords_arr - center) * scale
            self._coords = coords_arr

            if self._all_atom_coords is not None:
                self._all_atom_coords = (self._all_atom_coords - center) * scale
            if self._all_atom_radii is not None:
                try:
                    self._all_atom_radii = (
                        np.asarray(self._all_atom_radii, dtype=float) * scale
                    )
                except Exception:
                    self._all_atom_radii = None

            self._center = np.zeros(3, dtype=float)
            self._raw_center = np.asarray(center, dtype=float)
            self._radius = float(radius * scale)
            if getattr(self, "_ca_indices", None) is None:
                try:
                    _atom_names = np.asarray(atoms["atom_name"], dtype=str)
                    self._ca_indices = np.where(
                        np.char.strip(_atom_names) == "CA"
                    )[0]
                except Exception:
                    self._ca_indices = None
            self._backbone_map = None  # topology replaced; the map must be rebuilt
            self._trace_ups = _build_trace_ups(atoms, self._residue_ids, self._coords, chain_ids)

            try:
                n_res = int(self._coords.shape[0])
            except Exception:
                n_res = 0
            if atoms is not None and n_res > 0:
                try:
                    ss_codes = assign_ss_c3_from_atoms(atoms, n_res, verbose=False)
                except Exception:
                    ss_codes = None
                if ss_codes:
                    try:
                        self._secondary_structure = np.asarray(ss_codes, dtype="U1")
                    except Exception:
                        self._secondary_structure = None

            n_res = self._coords.shape[0]
            n_atoms = self._all_atom_coords.shape[0] if self._all_atom_coords is not None else 0

            # As in set_coordinates: keep per-atom state that still fits, and
            # only fall back to the defaults when it does not. `remove` trims
            # these arrays itself and then rebuilds, so re-deriving here undid
            # the trim and re-applied the hetero-ball default -- which is how
            # deleting the waters put a sphere on the zinc.
            keep_reps = (
                self._ball_mask is not None
                and len(self._ball_mask) == n_atoms
                and self._sticks_mask is not None
                and len(self._sticks_mask) == n_atoms
            )
            if self._cartoon_mask is None or len(self._cartoon_mask) != n_res:
                self._cartoon_mask = np.ones(n_res, dtype=bool)
            if not keep_reps:
                self._ball_mask = self._hetero_atom_mask(atoms, n_atoms)
                self._sticks_mask = np.zeros(n_atoms, dtype=bool)
            if not keep_reps and self._ball_mask.any():
                # Waters and ligands are not part of any cartoon, so leaving them
                # off means a deposited entry silently loses content the file
                # carries. PyMOL shows them too (as nonbonded dots) until hidden.
                self._show_atoms = True

            self._update_view()
            return

        # Case 2: fallback to ``structure.xyz`` attribute
        xyz_attr = getattr(structure, "xyz", None)
        if xyz_attr is not None:
            self.set_coordinates(np.asarray(xyz_attr, dtype=float))
            return

        raise TypeError(
            "Unsupported structure type for Chimol: " f"{type(structure)!r}"
        )

    def set_coordinates(
        self,
        xyz: np.ndarray,
        *,
        trace_coords: np.ndarray | None = None,
        res_ids: np.ndarray | None = None,
        res_names: np.ndarray | None = None,
        chain_ids: np.ndarray | None = None,
        atoms: np.ndarray | None = None,
    ) -> None:
        """Set raw coordinates for visualization.

        Parameters
        ----------
        xyz:
            Array of shape ``(N, 3)`` with Cartesian coordinates.
        trace_coords:
            Optional CA trace of shape ``(M, 3)``. When given it drives the
            cartoon/trace geometry instead of ``xyz``, mirroring what
            :meth:`set_structure` does.
        res_ids, res_names, chain_ids:
            Optional per-CA residue metadata of length ``M``. Supplying these
            is what lets the trace break at chain and residue gaps; without
            them the viewer draws one polyline through every point in ``xyz``.
        atoms:
            Optional structured per-atom array aligned with ``xyz``, carrying at
            least ``atom_name``, ``xyz``, ``res_id`` and ``chain``. This is what
            separates a *cartoon* from a bare spring: secondary structure is
            assigned from N/CA/C/O, and the ribbon takes its up-vector from the
            backbone carbonyl. Without it the viewer can only tube the CA trace.
        """
        arr = np.asarray(xyz, dtype=float)
        if arr.ndim != 2 or arr.shape[1] != 3:
            raise ValueError("xyz must have shape (N, 3)")

        self._atoms = atoms if isinstance(atoms, np.ndarray) else None
        self._all_atom_res_ids = None
        self._atom_features = {}
        self._atom_feature_meta = {}
        self._show_atom_gaussians = False

        # Bonds for the sticks representation are computed from *raw* (unscaled)
        # coordinates so the distance cutoff is independent of the view scaling,
        # exactly as in :meth:`set_structure`. Without this a raw-coordinate
        # object (the PDB fallback) has no bonds and sticks never render.
        raw_all = arr.copy()

        center, radius = _compute_center_radius(arr)
        scale = float(self._scale_factor)
        arr = (arr - center) * scale

        self._all_atom_coords = arr

        # A raw-coordinate object has no per-atom radii, but the surface and
        # metaball density renderers derive their Gaussian sigmas from
        # ``_all_atom_radii`` in the *scaled* coordinate frame. Leaving it None
        # makes them fall back to a constant sigma sized for *unscaled* Angstrom,
        # which is ~``scale``x too small once the coordinates are scaled -- the
        # density barely overlaps between atoms and the surface breaks up. Seed a
        # uniform atomic radius scaled the same way ``set_structure`` scales the
        # real ``radius`` field so every density path stays in the right units.
        self._all_atom_radii = np.full(
            arr.shape[0], _DEFAULT_ATOM_RADIUS_A * scale, dtype=float
        )

        # Replay any manual bond/unbond over the fresh inference: a hand-made
        # bond stored only in bond_pairs vanishes the moment coordinates change.
        self._bond_pairs = self._apply_bond_edits(
            self._infer_bonds(raw_all, self._atoms)
        )

        trace_arr = None
        if trace_coords is not None:
            trace_arr = np.asarray(trace_coords, dtype=float)
            if trace_arr.ndim != 2 or trace_arr.shape[1] != 3 or trace_arr.shape[0] < 2:
                trace_arr = None

        if trace_arr is not None:
            self._coords = (trace_arr - center) * scale
            self._residue_ids = res_ids
            self._residue_names = res_names
            self._residue_oneletter = _three_to_one_array(res_names)
            self._residue_chain_ids = chain_ids
        else:
            self._coords = arr
            self._residue_ids = None
            self._residue_names = None
            self._residue_oneletter = None
            self._residue_chain_ids = None

        self._center = np.zeros(3, dtype=float)
        self._raw_center = np.asarray(center, dtype=float)
        self._radius = float(radius * scale)

        # With a real atom array the fallback is not a second-class citizen: it
        # can orient the ribbon and assign secondary structure exactly as
        # set_structure does, so a missing core reader costs metadata rather
        # than the picture.
        self._secondary_structure = None
        self._trace_ups = None
        self._backbone_map = None  # topology replaced; the map must be rebuilt
        if self._atoms is not None and self._coords is not None:
            self._trace_ups = _build_trace_ups(
                self._atoms, self._residue_ids, self._coords, self._residue_chain_ids
            )
            try:
                n_res = int(self._coords.shape[0])
                ss_codes = assign_ss_c3_from_atoms(self._atoms, n_res, verbose=False)
            except Exception:
                logger.warning("Secondary-structure assignment failed for raw "
                               "coordinates", exc_info=True)
                ss_codes = None
            if ss_codes:
                try:
                    self._secondary_structure = np.asarray(ss_codes, dtype="U1")
                except Exception:
                    self._secondary_structure = None

        self._update_view()

        # No sequence information when only raw coordinates are provided
        if self._residue_ids is None and self._residue_names is None:
            self._colors_per_ca = None
        self._colors_per_residue_override = None
        # Per-atom state is *kept* when it still fits the atoms, and only
        # re-derived when it does not.
        #
        # Clobbering it unconditionally meant every coordinate change threw away
        # what the user had set: `remove solvent` turned `show spheres, solvent`
        # into a sphere on the zinc -- an atom nobody had selected -- because the
        # hetero-ball default was re-applied over the top, and a `spectrum`
        # colouring vanished the next time anything moved. The default belongs on
        # a *fresh* structure, not on every rebuild of one.
        n_atoms = arr.shape[0]

        def _fits(value) -> bool:
            return value is not None and len(np.asarray(value)) == n_atoms

        if not _fits(self._colors_per_atom_override):
            self._colors_per_atom_override = None
        n_residues = len(self._residue_ids) if self._residue_ids is not None else 0
        if self._cartoon_mask is None or len(self._cartoon_mask) != n_residues:
            self._cartoon_mask = None

        if not _fits(self._ball_mask):
            self._ball_mask = self._hetero_atom_mask(self._atoms, n_atoms)
            if self._ball_mask.any():
                self._show_atoms = True
        if not _fits(self._sticks_mask):
            self._sticks_mask = np.zeros(n_atoms, dtype=bool)

    def set_frames(
        self,
        frames: np.ndarray,
        *,
        object_id: str | None = None,
        active_frame: int | None = None,
    ) -> None:
        arr = np.asarray(frames, dtype=float)
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise ValueError("frames must have shape (T, N, 3)")
        if arr.shape[0] == 0 or arr.shape[1] == 0:
            raise ValueError("frames must contain at least one frame and one point")

        flat = arr.reshape(-1, 3)
        center, radius = _compute_center_radius(flat)
        scale = float(self._scale_factor)
        arr_scaled = (arr - center) * scale

        with self._activate_object(object_id):
            state = self._get_active_state()
            state.frames = arr_scaled
            state.frames_raw = arr
            idx = 0 if active_frame is None else int(active_frame)
            idx = self._select_state_frame(state, idx)
            self._center = np.zeros(3, dtype=float)
            self._radius = float(radius * scale)
            self._selected_residues = []
            # Keep the global timeline in sync with the new trajectory so
            # ``set_current_frame`` / ``get_total_frames`` reflect reality.
            self._total_frames = max(self._total_frames, int(arr.shape[0]))
            self._current_frame = idx
            if self._current_frame >= self._total_frames:
                self._current_frame = self._total_frames - 1
            try:
                self._update_view()
            except Exception:
                pass

    def append_frame(self, frame: np.ndarray, *, object_id: str | None = None) -> int:
        """Append one raw coordinate frame to an object's trajectory.

        Parameters
        ----------
        frame : np.ndarray
            Coordinate array with shape ``(N, 3)`` in Angstrom.
        object_id : str, optional
            Object to update. The active object is used by default.

        Returns
        -------
        int
            Number of frames after appending.
        """
        arr = np.asarray(frame, dtype=float)
        if arr.ndim != 2 or arr.shape[1] != 3:
            raise ValueError("frame must have shape (N, 3)")
        with self._activate_object(object_id):
            state = self._get_active_state()
            raw = getattr(state, "frames_raw", None)
            if raw is None:
                frames = arr[np.newaxis, :, :]
            else:
                raw_arr = np.asarray(raw, dtype=float)
                if raw_arr.ndim != 3 or raw_arr.shape[1:] != arr.shape:
                    raise ValueError("frame shape does not match existing trajectory")
                frames = np.concatenate([raw_arr, arr[np.newaxis, :, :]], axis=0)
        self.set_frames(frames, object_id=object_id)
        self.set_active_frame(frames.shape[0] - 1, object_id=object_id)
        return int(frames.shape[0])

    def set_active_frame(self, index: int, *, object_id: str | None = None) -> None:
        with self._activate_object(object_id):
            state = self._get_active_state()
            frames = getattr(state, "frames", None)
            if frames is None:
                return
            try:
                arr = np.asarray(frames, dtype=float)
            except Exception:
                return
            if arr.ndim != 3 or arr.shape[2] != 3 or arr.shape[0] == 0:
                return
            n_frames = arr.shape[0]
            # A fractional position is legitimate: it means "between these two
            # frames", and `_select_state_frame` interpolates there.
            idx, _blend, _next = _frame_blend(index, n_frames)
            self._note_frame_change()
            self._select_state_frame(state, index)
            # Keep ``_total_frames`` consistent with the trajectory length
            # so the public ``get_total_frames`` / ``set_current_frame`` API
            # behaves correctly for externally attached frames.
            self._total_frames = max(self._total_frames, n_frames)
            self._current_frame = idx
            if self._current_frame >= self._total_frames:
                self._current_frame = self._total_frames - 1
            try:
                self._update_view(fit_camera=False)
            except Exception:
                pass

    def get_frame_count(self, object_id: str | None = None) -> int:
        with self._activate_object(object_id):
            state = self._get_active_state()
            frames = getattr(state, "frames", None)
            if frames is None:
                return 0
            try:
                arr = np.asarray(frames, dtype=float)
            except Exception:
                return 0
            if arr.ndim != 3 or arr.shape[2] != 3:
                return 0
            return int(arr.shape[0])

    def get_active_frame_index(self, object_id: str | None = None) -> int:
        with self._activate_object(object_id):
            state = self._get_active_state()
            try:
                idx = int(getattr(state, "active_frame", 0))
            except Exception:
                idx = 0
            frames = getattr(state, "frames", None)
            if frames is None:
                return 0
            try:
                n = int(np.asarray(frames).shape[0])
            except Exception:
                return max(idx, 0)
            if n <= 0:
                return 0
            if idx < 0:
                idx = 0
            if idx >= n:
                idx = n - 1
            return idx

    def set_background_color(self, color) -> bool:
        """Set the viewer background color. False when it could not be applied.

        This is a thin wrapper around the renderer's ``set_background_color``
        method and accepts the same Qt-compatible color values (strings like
        "black" or RGB(A) tuples).
        """
        renderer = self._renderer
        if renderer is None:
            return False
        try:
            renderer.set_background_color(color)
        except Exception as exc:
            # Not swallowed: a bare `except: pass` here is why `bg_color` failed
            # silently for so long -- the colour arrived as a numpy array, the
            # renderer raised, and the command reported success anyway.
            import logging

            logging.getLogger(__name__).warning(
                "chimol: could not set the background to %r (%s)", color, exc
            )
            return False
        return True

    def set_field_of_view(self, fov: float) -> None:
        """Set the camera's vertical field of view in degrees.

        Delegates to the renderer, which re-frames the scene so the molecule
        keeps its on-screen size (see
        :meth:`~.qtgl.QtGLRenderer.set_field_of_view`).
        """
        renderer = self._renderer
        if renderer is None:
            return
        setter = getattr(renderer, "set_field_of_view", None)
        if callable(setter):
            setter(fov)

    def set_mouse_mode(self, mode: str) -> None:
        """Set the mouse interaction style.

        Parameters
        ----------
        mode : str
            ``"pymol"`` rotates and pans the object (protein) in the camera
            view so it appears to follow the cursor (PyMOL-style).
            ``"chimol"`` rotates and pans the camera / plane, so the object
            moves opposite to the cursor (legacy Chimol style).
        """
        self._mouse_mode = self._normalize_mouse_mode(mode)
        renderer = self._renderer
        if renderer is None:
            return
        try:
            renderer.set_mouse_mode(self._mouse_mode)
        except Exception:
            pass

    def get_mouse_mode(self) -> str:
        """Return the current left-drag rotation style."""
        return self._mouse_mode

    def _framing_radius(self, complete: bool = False) -> float:
        """Radius the camera should fit, over whichever coordinates we have.

        Prefers the all-atom coordinates, since that is what PyMOL measures;
        falls back to the CA trace and finally to the scene's bounding-sphere
        radius when neither is available.
        """
        for attr in ("_all_atom_coords", "_coords"):
            pts = getattr(self, attr, None)
            if pts is None:
                continue
            try:
                radius = framing_radius(
                    pts, complete=complete,
                    scale=float(getattr(self, '_scale_factor', 1.0) or 1.0),
                )
            except Exception:
                continue
            if radius > 0.0:
                return radius

        scene = self._scene
        if scene is not None:
            try:
                return float(getattr(scene, "radius", 0.0))
            except Exception:
                pass
        return 0.0

    def reset_view(self) -> None:
        """Reset the camera to show all visible objects at default orientation."""
        if self._renderer is None:
            return

        radius = 0.0
        try:
            radius = self._framing_radius()
        except Exception:
            pass

        if radius <= 0.0:
            radius = float(getattr(self, "_radius", 10.0))

        # The distance is recomputed from the field of view by fit_to_radius
        # immediately afterwards; this only establishes the orientation.
        self._renderer.reset_view(
            distance=max(radius * 3.0, 5.0),
            elevation=float(self._default_elevation),
            azimuth=float(self._default_azimuth)
        )
        self._renderer.fit_to_radius(radius)

    def turn(self, axis: str, angle: float) -> None:
        """Rotate the camera about a screen axis (PyMOL ``turn``)."""
        r = self._renderer
        if r is not None and hasattr(r, "turn"):
            r.turn(axis, angle)

    def move(self, axis: str, dist: float) -> None:
        """Translate the camera along a screen axis (PyMOL ``move``)."""
        r = self._renderer
        if r is not None and hasattr(r, "move"):
            r.move(axis, dist)

    def clip(self, mode: str, dist: float) -> None:
        """Move the clipping planes (PyMOL ``clip``)."""
        r = self._renderer
        if r is not None and hasattr(r, "adjust_clip"):
            r.adjust_clip(mode, dist)

    def get_view_state(self) -> list[float]:
        """Return an 18-float view tuple for PyMOL-style ``get_view``."""
        renderer = self._renderer
        if renderer is not None and hasattr(renderer, "get_view_state"):
            return list(renderer.get_view_state())
        return [
            1.0, 0.0, 0.0,
            0.0, 1.0, 0.0,
            0.0, 0.0, 1.0,
            float(self._radius * 3.0), 20.0, 45.0,
            0.0, 0.0, 0.0,
            float(self._camera_near_clip), float(self._camera_far_clip), 45.0,
        ]

    def set_view_state(self, view) -> None:
        """Restore an 18-float view tuple from PyMOL-style ``set_view``."""
        vals = [float(v) for v in view]
        if len(vals) != 18:
            raise ValueError("view must contain 18 floats")
        renderer = self._renderer
        if renderer is not None and hasattr(renderer, "set_view_state"):
            renderer.set_view_state(vals)

    def push_undo(self, *, object_id: str | None = None) -> bool:
        """Snapshot an object's coordinates onto its undo ring (PyMOL ``push_undo``).

        Parameters
        ----------
        object_id : str, optional
            Object to snapshot; defaults to the active one.

        Returns
        -------
        bool
            False when there is no such object, or it carries no coordinates.

        See Also
        --------
        chimol.renderer.undo.UndoRing : the ring, and why it is not a stack pair.
        """
        target = object_id or self._active_object_id
        entry = self._objects.get(target) if target else None
        state = getattr(entry, "state", None)
        if state is None:
            return False
        return self._undo_ring(target).push(state)

    def undo(self, *, direction: int = -1, object_id: str | None = None) -> str:
        """Undo or redo an object's last coordinate change (PyMOL ``undo``/``redo``).

        Parameters
        ----------
        direction : int, optional
            ``-1`` to undo, ``+1`` to redo. One routine serves both, as
            ``ObjectMoleculeUndo`` does: it leaves the present state in the ring
            before stepping, so the walk is reversible.
        object_id : str, optional
            Object to act on; defaults to the active one.

        Returns
        -------
        str
            ``"restored"``, ``"empty"`` when the history holds nothing in that
            direction, ``"resized"`` when the atom count has changed since the
            snapshot -- PyMOL refuses that too, since old coordinates cannot be
            poured into a differently sized object -- or ``"no object"``.
        """
        target = object_id or self._active_object_id
        entry = self._objects.get(target) if target else None
        state = getattr(entry, "state", None)
        if state is None:
            return "no object"

        outcome = self._undo_ring(target).step(state, direction)
        if outcome != "restored":
            return outcome

        if target == self._active_object_id:
            # The globals mirror the active object's arrays.
            self._coords = state.coords
            self._center = state.center
            self._radius = state.radius
        self._update_view()
        return "restored"

    def undo_depth(self, *, object_id: str | None = None) -> int:
        """Number of coordinate snapshots stored for an object."""
        target = object_id or self._active_object_id
        ring = self._undo_rings.get(target) if target else None
        return ring.depth() if ring is not None else 0

    def _undo_ring(self, object_id: str) -> UndoRing:
        """The undo ring for an object, created on first use."""
        ring = self._undo_rings.get(object_id)
        if ring is None:
            ring = UndoRing()
            self._undo_rings[object_id] = ring
        return ring

    def set_rotation_origin(self, point: Sequence[float]) -> bool:
        """Move the point the camera rotates about (PyMOL ``origin``).

        The picture does not move: PyMOL's ``origin`` always preserves the current
        view, so nothing appears to happen until the next rotation, which then
        pivots about the chosen point.

        Parameters
        ----------
        point : sequence of float
            The new pivot, in **Angstrom** in the structure's own frame. Converted
            to the renderer's scene units here, which is the seam every command
            taking a length has to respect.

        Returns
        -------
        bool
            False when there is no renderer to tell.
        """
        renderer = self._renderer
        if renderer is None or not hasattr(renderer, "set_origin"):
            return False
        scene = self._transform_world_coords_to_scene(
            np.asarray(point, dtype=float).reshape(1, 3)
        )
        renderer.set_origin(np.asarray(scene, dtype=float).reshape(3))
        return True

    def get_rotation_origin(self) -> np.ndarray | None:
        """Return the current pivot in Angstrom, or ``None`` without a renderer."""
        renderer = self._renderer
        if renderer is None or not hasattr(renderer, "get_origin"):
            return None
        scene = np.asarray(renderer.get_origin(), dtype=float)
        centre = self._raw_center
        scale = float(getattr(self, "_scale_factor", 1.0) or 1.0)
        out = scene / scale if scale else scene
        return out + np.asarray(centre, dtype=float) if centre is not None else out

    def center(
        self,
        indices: Sequence[int] | None = None,
        *,
        object_id: str | None = None,
        atom_mask: np.ndarray | None = None,
    ) -> bool:
        """Centre the camera on a selection's centre (PyMOL ``center``).

        Returns
        -------
        bool
            False when the selection yielded no coordinates, so a caller can
            report that rather than a success.

        See Also
        --------
        _selection_coords : why this takes atoms rather than residue positions.
        """
        coords = self._selection_coords(
            indices, object_id=object_id, atom_mask=atom_mask
        )
        if coords.size == 0 or self._renderer is None:
            return False
        self._renderer.look_at(coords.mean(axis=0))
        return True

    def _selection_coords(
        self,
        indices=None,
        *,
        object_id: str | None = None,
        atom_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        """Coordinates a camera command should measure, in render space.

        Prefers the selection's **atoms**. Residue positions are one CA-trace
        point per residue, so any residue without a CA -- a ligand, an ion, a
        water -- reduced to nothing, and `zoom resn NAG`, `center resn NAG` and
        `orient resn NAG` all silently did nothing while reporting success. A
        ligand is exactly what those commands are usually pointed at.
        """
        if atom_mask is not None:
            with self._activate_object(object_id):
                all_atoms = getattr(self, "_all_atom_coords", None)
            if all_atoms is not None:
                array = np.asarray(all_atoms, dtype=float)
                mask = np.asarray(atom_mask, dtype=bool)
                if mask.shape[0] == array.shape[0] and mask.any():
                    return array[mask]
        if indices is None and object_id is None:
            all_atoms = getattr(self, "_all_atom_coords", None)
            if all_atoms is not None and np.asarray(all_atoms).size:
                return np.asarray(all_atoms, dtype=float)
        return np.asarray(
            self.get_residue_positions(indices, object_id=object_id), dtype=float
        )

    def zoom(
        self,
        indices: Sequence[int] | None = None,
        *,
        buffer: float = 0.0,
        complete: bool = False,
        object_id: str | None = None,
        atom_mask: np.ndarray | None = None,
    ) -> None:
        """Zoom the camera to fit target residues (PyMOL ``zoom``).

        Parameters
        ----------
        indices : sequence of int or None
            Residue indices to fit; ``None`` fits everything.
        buffer : float, optional
            Extra room around the fitted radius, in scene units. PyMOL's default
            is 0, which frames tightly and may clip a corner.
        complete : bool, optional
            Fit the bounding sphere rather than the bounding box, so that no atom
            centre can be clipped at any orientation.
        object_id : str or None
            Object to take the residues from.

        See Also
        --------
        chimol.renderer.view_state.framing_radius : the two fitting rules.
        """
        # With no selection, fit every atom rather than the CA trace: PyMOL
        # measures the whole molecule, and a trace-only fit reads ~20% small
        # because the side chains reaching furthest out are exactly the ones
        # left out of it.
        coords = self._selection_coords(
            indices, object_id=object_id, atom_mask=atom_mask
        )
        if coords.size == 0:
            self.reset_view()
            return

        # The centroid, not the box centre: PyMOL asks for a *weighted* extent
        # and re-centres the box on the average of the atom coordinates. See
        # view_state.framing_centre.
        center = framing_centre(coords)
        radius = framing_radius(
            coords, complete=complete,
            scale=float(getattr(self, '_scale_factor', 1.0) or 1.0),
        )

        if self._renderer is not None:
            self._renderer.look_at(center)
            self._renderer.fit_to_radius(radius + float(buffer))

    def orient(
        self,
        indices: Sequence[int] | None = None,
        *,
        object_id: str | None = None,
        atom_mask: np.ndarray | None = None,
    ) -> bool:
        """Align the selection's principal axes with the screen (PyMOL ``orient``).

        Follows ``ExecutiveOrient``: build the **inertia tensor** of the selection
        about its own centre, eigensolve it, use the eigenvectors as the camera
        basis, force the result right-handed, then frame it.

        The sign convention matters and is easy to invert. For an inertia tensor
        the **smallest** eigenvalue belongs to the **longest** axis -- a rod has
        almost no moment about its own length -- so the longest extent goes on
        screen x, the next on y, the shortest into the screen. Sorting the other
        way puts the molecule end-on, which looks like a failure to orient at all.

        Returns
        -------
        bool
            False when there is nothing to orient, so a caller can say so rather
            than report success.

        Notes
        -----
        This was a stub for a long time -- it called :meth:`zoom` and returned,
        behind a TODO saying the renderer could not take an arbitrary rotation. It
        can (``set_view_state`` takes the full 3x3), so the note outlived the
        limitation. It reported no error either way, which is why running the
        command proved nothing.

        PyMOL reaches the same place by loading the eigenvector matrix and then
        applying a sequence of 90-degree rotations chosen from the eigenvalue
        ordering -- with a comment in its own source that there must be a more
        elegant way. Sorting the eigenvectors *is* that permutation, so it is done
        directly here and the observable contract is asserted instead: the
        extents, measured in the camera frame, come out descending.
        """
        coords = self._selection_coords(
            indices, object_id=object_id, atom_mask=atom_mask
        )
        if coords.size == 0 or coords.shape[0] < 2:
            # One point has no orientation; framing is all that is meaningful.
            self.zoom(indices, object_id=object_id)
            return False

        centred = coords - coords.mean(axis=0)
        # The inertia tensor, exactly as OMOP_CSetMoment accumulates it:
        # sum over atoms of |r|^2 * I - r (outer) r.
        squared = float(np.sum(centred * centred))
        tensor = np.eye(3) * squared - centred.T @ centred

        try:
            eigenvalues, eigenvectors = np.linalg.eigh(tensor)
        except np.linalg.LinAlgError:
            self.zoom(indices, object_id=object_id)
            return False

        # Ascending eigenvalue: smallest moment first, which is the longest axis.
        order = np.argsort(eigenvalues)
        basis = eigenvectors[:, order]

        # Right-handed, or the view is mirrored: PyMOL negates the third column
        # when the cross product of the first two points the other way.
        if float(np.dot(np.cross(basis[:, 0], basis[:, 1]), basis[:, 2])) < 0.0:
            basis[:, 2] = -basis[:, 2]

        # Of the equivalent orientations, take the one closest to where the camera
        # already is, so `orient` does not spin the molecule through half a turn
        # for no reason. PyMOL does this with a 180-degree flip chosen from the
        # signs of the per-axis dot products; flipping two columns at once is the
        # same thing and keeps the matrix right-handed.
        try:
            current = np.asarray(self.get_view_state(), dtype=float)[:9].reshape(3, 3)
        except Exception:
            current = None
        if current is not None:
            best, best_score = basis, -np.inf
            for flip in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)):
                candidate = basis * np.asarray(flip, dtype=float)
                score = float(np.sum(candidate * current))
                if score > best_score:
                    best, best_score = candidate, score
            basis = best

        view = list(self.get_view_state())
        # Slots 0-8 hold the camera basis in columns, which is what `basis` is.
        view[:9] = [float(v) for v in basis.flatten()]
        try:
            self.set_view_state(view)
        except Exception:
            return False
        # Frame it afterwards: the rotation changes which extent faces the camera,
        # so a zoom computed before it would fit the wrong silhouette.
        self.zoom(indices, object_id=object_id, atom_mask=atom_mask)
        return True

    # ------------------------------------------------------------------
    # Representation / interaction helpers
    # ------------------------------------------------------------------
    def set_residue_representation(
        self,
        indices,
        cartoon: bool | None = None,
        ball: bool | None = None,
        *,
        object_id: str | None = None,
    ) -> None:
        """Enable/disable cartoon and ball view for selected residues.

        Parameters
        ----------
        indices:
            Iterable of integer residue indices (0-based along the CA trace).
        cartoon:
            If True, enable cartoon for these residues; if False, disable;
            if None, leave unchanged.
        ball:
            If True, enable ball view for these residues; if False, disable;
            if None, leave unchanged.
        """
        changed = False
        with self._activate_object(object_id):
            coords = self._coords
            if coords is None:
                return
            n = coords.shape[0]
            if n == 0:
                return

            if self._cartoon_mask is None or len(self._cartoon_mask) != n:
                self._cartoon_mask = np.ones(n, dtype=bool)
            if self._ball_mask is None or len(self._ball_mask) != n:
                self._ball_mask = np.zeros(n, dtype=bool)

            if indices is None:
                idx_list = np.arange(n, dtype=int)
            else:
                try:
                    idx_arr = np.asarray(list(indices), dtype=int)
                except Exception:
                    idx_list = np.arange(n, dtype=int)
                else:
                    if idx_arr.size == 0:
                        idx_list = np.arange(n, dtype=int)
                    else:
                        idx_arr = idx_arr[(idx_arr >= 0) & (idx_arr < n)]
                        idx_list = idx_arr if idx_arr.size else np.arange(n, dtype=int)

            if cartoon is not None:
                self._cartoon_mask[idx_list] = bool(cartoon)
                try:
                    self._show_cartoon = bool(self._cartoon_mask.any())
                except Exception:
                    self._show_cartoon = True
                changed = True
            if ball is not None:
                self._ball_mask[idx_list] = bool(ball)
                try:
                    self._show_atoms = bool(self._ball_mask.any())
                except Exception:
                    self._show_atoms = True
                changed = True

        if changed:
            self._update_view()

    def _hetero_atom_mask(self, atoms, n_atoms: int) -> np.ndarray:
        """Mark the atoms that no cartoon or trace will draw.

        An atom is "hetero" here if its residue never appears in the backbone
        trace — waters, ions, ligands and sugars. Defining it by absence from the
        trace rather than by a residue-name table means modified residues that do
        get traced are correctly treated as polymer.

        Parameters
        ----------
        atoms : numpy.ndarray or None
            The structured atom array, needing ``res_id`` and (ideally) ``chain``.
        n_atoms : int
            Length of the returned mask.

        Returns
        -------
        numpy.ndarray
            Boolean mask of length ``n_atoms``; all-False when the residues
            cannot be matched up.
        """
        mask = np.zeros(max(int(n_atoms), 0), dtype=bool)
        if atoms is None or mask.size == 0 or self._residue_ids is None:
            return mask
        names = getattr(atoms, "dtype", None)
        names = set(names.names or ()) if names is not None else set()
        if "res_id" not in names or len(atoms) != mask.size:
            return mask

        def _keys(res_ids, chain_ids):
            res = np.asarray(res_ids).astype(int, copy=False)
            if chain_ids is None:
                return [(None, int(r)) for r in res]
            chains = np.asarray(chain_ids).astype(str, copy=False)
            return [(str(c).strip(), int(r)) for c, r in zip(chains, res)]

        try:
            traced = set(_keys(
                self._residue_ids,
                getattr(self, "_residue_chain_ids", None) if "chain" in names else None,
            ))
            atom_keys = _keys(
                atoms["res_id"],
                atoms["chain"] if "chain" in names else None,
            )
        except Exception:
            return mask

        for i, key in enumerate(atom_keys):
            if key not in traced:
                mask[i] = True
        return mask

    def recompute_secondary_structure(self) -> int:
        """Recompute the secondary structure from the coordinates (PyMOL ``dss``).

        Discards whatever the object is currently annotated with — including a
        depositor's ``HELIX``/``SHEET`` records — and derives H/E/C from the
        backbone geometry instead. This is the escape hatch for structures whose
        records are absent, stale, or disagree with the model, and for
        trajectory frames where the conformation has moved on.

        Returns
        -------
        int
            Number of residues assigned, or 0 when there is nothing to work on.
        """
        atoms = getattr(self, "_atoms", None)
        coords = getattr(self, "_coords", None)
        if atoms is None or coords is None:
            return 0
        try:
            n_res = int(coords.shape[0])
        except Exception:
            return 0
        if n_res <= 0:
            return 0

        try:
            codes = assign_ss_c3_from_atoms(atoms, n_res, verbose=False)
        except Exception:
            logger.warning("Secondary-structure assignment failed", exc_info=True)
            return 0
        if not codes:
            return 0

        self.set_secondary_structure_codes(codes)
        return len(codes)

    def set_secondary_structure_codes(self, codes) -> None:
        """Set per-residue secondary-structure codes for coloring.

        Parameters
        ----------
        codes:
            Iterable of single-character secondary-structure labels (e.g.
            'H', 'E', 'C') aligned to the CA trace.
        """
        try:
            arr = np.asarray(list(codes), dtype="U1")
        except Exception:
            return
        if arr.size == 0:
            self._secondary_structure = None
            return
        self._secondary_structure = arr
        if self._coords is not None and self._coords.shape[0] > 0:
            self._update_view()

    def set_plane_visible(self, visible: bool) -> None:
        """Show or hide the reference plane (grid)."""
        self._grid_visible = bool(visible)
        if self._renderer is not None:
            try:
                self._renderer.set_grid_visible(self._grid_visible)
            except Exception:
                pass

    def toggle_plane(self) -> None:
        self.set_plane_visible(not self._grid_visible)

    def set_surface_visible(self, visible: bool) -> None:
        self._surface_visible = bool(visible)
        if self._renderer is not None and self._coords is not None:
            self._update_view()

    def set_metaballs_visible(self, visible: bool) -> None:
        self._metaballs_visible = bool(visible)
        if self._renderer is not None and self._coords is not None:
            self._update_view()

    def set_color_mode(self, mode: str) -> None:
        """Set coloring mode.

        Parameters
        ----------
        mode:
            "single" for uniform coloring, "by_residue" to color amino
            acids differently, or "by_secondary_structure" to color by
            secondary-structure state.
        """
        if mode not in (
            "single",
            "by_residue",
            "by_secondary_structure",
            "by_sequence",
            "by_element",
            "by_chain",
            "spectrum",
        ):
            return
        self._color_mode = mode
        if self._coords is not None:
            self._update_view(fit_camera=False)

    def set_representation(self, mode: str, *, object_id: str | None = None) -> None:
        """Legacy mode-style API (cartoon / ca_trace / atoms).

        This is primarily used by keyboard shortcuts and :class:`MolViewPlot`.
        Internally it configures the independent representation toggles
        (``_show_cartoon``, ``_show_trace``, ``_show_atoms``) and the
        per-residue ball mask, then refreshes the view.
        """
        mode_l = str(mode).lower()
        if mode_l not in ("cartoon", "ca_trace", "atoms", "lines"):
            return
        with self._activate_object(object_id):
            self._representation_mode = mode_l

            if self._coords is None:
                return
            n = self._coords.shape[0]
            if n <= 0:
                return

            # `lines` is exclusive like the others: PyMOL's `as` replaces the
            # representation rather than adding to it. It brings the nonbonded
            # crosses with it, as PyMOL pairs the two.
            if mode_l == "lines":
                self._show_cartoon = False
                self._show_trace = False
                self._show_atoms = False
                self._show_sticks = False
                self._show_lines = True
                self._show_nonbonded = True
                self._update_view()
                return

            self._show_lines = False
            self._show_nonbonded = False

            if mode_l == "cartoon":
                self._show_cartoon = True
                self._show_trace = False
                self._show_atoms = False
            elif mode_l == "ca_trace":
                self._show_cartoon = False
                self._show_trace = True
                self._show_atoms = False
            else:  # "atoms"
                self._show_cartoon = False
                self._show_trace = False
                self._show_atoms = True

            # For atoms mode, default to showing balls on all residues.
            if mode_l == "atoms":
                self._cartoon_mask = np.ones(n, dtype=bool)
                self._ball_mask = np.ones(n, dtype=bool)
            else:
                if self._cartoon_mask is None or len(self._cartoon_mask) != n:
                    self._cartoon_mask = np.ones(n, dtype=bool)
                else:
                    self._cartoon_mask[:] = True
                if self._ball_mask is None or len(self._ball_mask) != n:
                    self._ball_mask = np.zeros(n, dtype=bool)
                else:
                    self._ball_mask[:] = False

        self._update_view()

    def set_cartoon_visible(self, visible: bool) -> None:
        """Enable or disable the cartoon tube globally."""
        self._show_cartoon = bool(visible)
        if self._coords is not None:
            self._update_view()

    def set_trace_visible(self, visible: bool) -> None:
        """Enable or disable the CA trace line globally."""
        self._show_trace = bool(visible)
        if self._coords is not None:
            self._update_view()

    def set_atoms_visible(self, visible: bool) -> None:
        """Enable or disable the atom/ball representation globally."""
        state = self._get_active_state()
        self._set_state_atoms_visible(state, bool(visible))
        self._update_view(fit_camera=False)

    def set_atom_gaussians_visible(self, visible: bool) -> None:
        self._show_atom_gaussians = bool(visible)
        if self._coords is not None:
            self._update_view()

    def set_dots_visible(self, visible: bool) -> None:
        self._show_dots = bool(visible)
        if self._coords is not None:
            self._update_view()

    def toggle_dots(self) -> None:
        self.set_dots_visible(not self._show_dots)

    def set_atoms_visible_all(self, visible: bool) -> None:
        """Toggle atoms representation for every loaded object."""
        changed = False
        vis = bool(visible)
        for entry in self._objects.values():
            prev_mask = entry.state.ball_mask
            self._set_state_atoms_visible(entry.state, vis)
            if entry.state.ball_mask is not prev_mask or entry.state.show_atoms != vis:
                changed = True
        if changed:
            self._update_view()

    def _set_state_atoms_visible(self, state: _MolViewObjectState, visible: bool) -> None:
        state.show_atoms = bool(visible)

        coords = state.coords
        if isinstance(coords, np.ndarray) and coords.ndim == 2 and coords.shape[0] > 0:
            n = coords.shape[0]
            mask = np.ones(n, dtype=bool) if visible else np.zeros(n, dtype=bool)
            state.ball_mask = mask
        else:
            if not visible:
                state.ball_mask = None

    def set_lines_visible(self, visible: bool) -> None:
        """Show or hide the per-bond wireframe (PyMOL ``lines``)."""
        self._show_lines = bool(visible)
        self._update_view()

    def set_nonbonded_visible(self, visible: bool) -> None:
        """Show or hide crosses on the atoms that draw no bond."""
        self._show_nonbonded = bool(visible)
        self._update_view()

    def set_sticks_visible(self, visible: bool) -> None:
        """Enable or disable the sticks (bond) representation globally."""
        self._show_sticks = bool(visible)
        if visible and self._all_atom_coords is not None:
            n_atoms = int(np.asarray(self._all_atom_coords).shape[0])
            if (
                self._sticks_mask is None
                or len(self._sticks_mask) != n_atoms
                or not np.asarray(self._sticks_mask, dtype=bool).any()
            ):
                self._sticks_mask = np.ones(n_atoms, dtype=bool)
        if self._coords is not None:
            self._update_view()

    def handle_key_event(self, ev: QtGui.QKeyEvent) -> bool:  # type: ignore[name-defined]
        """Handle keyboard shortcuts for basic viewer controls.

        r - cartoon/ribbon mode
        c - CA trace mode
        b - atoms/ball mode
        s - toggle sidechains on/off (atoms view)
        q - close the containing window
        """
        try:
            ch = ev.text().lower()
        except Exception:
            return False

        if ch == "r":
            self.set_representation("cartoon")
            return True
        if ch == "c":
            self.set_representation("ca_trace")
            return True
        if ch == "b":
            self.set_representation("atoms")
            return True
        if ch == "d":
            self.toggle_dots()
            return True
        if ch == "s":
            self.toggle_sidechains()
            return True
        if ch == "q":
            w = self.window()
            if w is not None:
                try:
                    w.close()
                except Exception:
                    pass
            return True
        return False

    # ------------------------------------------------------------------
    # Picking / mouse interaction
    # ------------------------------------------------------------------

    def handle_mouse_click(self, ev: QtGui.QMouseEvent) -> None:  # type: ignore[name-defined]
        """Handle a mouse-click in the GL view for atom picking.

        A left-click near an atom selects the nearest atom;
        clicking in empty space clears the selection.
        Updates both atom and residue selection states.
        """
        atom_indices = []
        residue_indices = []
        mods = None
        if self._coords is not None and getattr(self, "_gl_enabled", False) and self.view is not None:
            picking_mod = _get_picking_module()
            try:
                sel_cfg = _DISPLAY_CONFIG.get("selection", {})
            except Exception:
                sel_cfg = {}
            try:
                radius_px = float(sel_cfg.get("click_radius_px", 8.0))
            except Exception:
                radius_px = 8.0
            if not np.isfinite(radius_px) or radius_px <= 0.0:
                radius_px = 8.0

            try:
                mods = ev.modifiers()
            except Exception:
                mods = None

            picked_atom_idx = None
            if picking_mod is not None and self._all_atom_coords is not None:
                try:
                    picked_atom_idx = picking_mod.pick_atom_from_click(
                        self._all_atom_coords,
                        self.view,
                        ev,
                        radius_px,
                        # PyMOL's `mask`: these atoms are not selectable, which
                        # is how a click stops reaching the molecule behind.
                        unpickable=self._masked_mask,
                    )
                except Exception:
                    picked_atom_idx = None

            if picked_atom_idx is not None:
                atom_indices = [picked_atom_idx]
                if self._all_atom_res_ids is not None and self._residue_ids is not None:
                    try:
                        residue_id = int(self._all_atom_res_ids[picked_atom_idx])
                        matches = np.where(self._residue_ids == residue_id)[0]
                        if len(matches) > 0:
                            residue_indices = [int(matches[0])]
                    except Exception:
                        residue_indices = []
            elif picking_mod is not None:
                try:
                    picked_idx = picking_mod.pick_residue_from_click(
                        self._coords,
                        self.view,
                        ev,
                        radius_px,
                    )
                    if picked_idx is not None:
                        residue_indices = [picked_idx]
                except Exception:
                    residue_indices = []

        try:
            self.atomSelectionChanged.emit(atom_indices)
        except Exception:
            pass

        try:
            self._apply_selection_indices(residue_indices, mods)
        except Exception:
            pass

        if self._coords is not None and getattr(self, "_gl_enabled", False):
            try:
                self._update_view()
            except Exception:
                pass

    def _apply_selection_indices(self, indices, modifiers=None) -> None:
        try:
            mods = modifiers
            ctrl = bool(mods & QtCore.Qt.ControlModifier) if mods is not None else False
        except Exception:
            ctrl = False

        try:
            idx_list = [int(i) for i in list(indices)]
        except Exception:
            idx_list = []

        if idx_list:
            if ctrl:
                try:
                    current = set(
                        int(i)
                        for i in getattr(self, "_selected_residues", [])
                        if int(i) >= 0
                    )
                except Exception:
                    current = set()
                region = set(i for i in idx_list if i >= 0)
                new_sel = sorted(current.symmetric_difference(region))
                self._selected_residues = new_sel
            else:
                self._selected_residues = idx_list
            selection = list(self._selected_residues)
            try:
                self.residueSelectionChanged.emit(selection)
            except Exception:
                pass
            try:
                self.objectResidueSelectionChanged.emit(self.get_active_object_id(), selection)
            except Exception:
                pass
        else:
            self._selected_residues = []
            try:
                self.residueSelectionChanged.emit([])
            except Exception:
                pass
            try:
                self.objectResidueSelectionChanged.emit(self.get_active_object_id(), [])
            except Exception:
                pass


    def handle_rect_selection(self, rect, modifiers=None) -> None:
        if self._coords is None or not getattr(self, "_gl_enabled", False) or self.view is None:
            return

        picking_mod = _get_picking_module()
        if picking_mod is not None:
            try:
                idx_arr = picking_mod.pick_residues_in_rect(self._coords, self.view, rect)
            except Exception:
                idx_arr = np.zeros(0, dtype=int)
        else:
            idx_arr = np.zeros(0, dtype=int)

        try:
            indices = [int(i) for i in np.asarray(idx_arr, dtype=int) if int(i) >= 0]
        except Exception:
            indices = []
        try:
            self._apply_selection_indices(indices, modifiers)
        except Exception:
            pass

    def _show_disabled_label(self, reason: str | None = None) -> None:
        message = (
            "Chimol OpenGL viewer is disabled.\n"
            "Enable OpenGL support to use this tool."
        )
        if reason:
            message = f"{message}\n\n{reason}"

        if self._disabled_label is None:
            label = QtWidgets.QLabel(self)
            label.setAlignment(QtCore.Qt.AlignCenter)
            label.setWordWrap(True)
            self._disabled_label = label
            self.layout().addWidget(label)

        self._disabled_label.setText(message)
        self._disabled_label.show()

    def on_renderer_error(self, message: str) -> None:
        self._renderer = None
        self._show_disabled_label(message)

        try:
            self._update_view()
        except Exception:
            pass

    def set_selected_residues(self, indices, *, object_id: str | None = None) -> None:
        """Update selection from external widgets (e.g. sequence view)."""
        try:
            idx_iter = list(indices)
        except Exception:
            idx_iter = []

        with self._activate_object(object_id):
            if self._coords is None:
                self._selected_residues = []
                return

            n = self._coords.shape[0]
            if n <= 0:
                self._selected_residues = []
                return

            idx_list: list[int] = []
            for idx in idx_iter:
                try:
                    i = int(idx)
                except Exception:
                    continue
                if 0 <= i < n:
                    idx_list.append(i)

            self._selected_residues = idx_list

        try:
            self._update_view()
        except Exception:
            pass

    def get_sequence_arrays(
        self, object_id: str | None = None
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        with self._activate_object(object_id):
            seq = _copy_array(self._residue_oneletter)
            res = _copy_array(self._residue_names)
        return seq, res

    def get_residue_numbers(self, object_id: str | None = None) -> np.ndarray | None:
        with self._activate_object(object_id):
            ids = _copy_array(self._residue_ids)
        return ids

    def get_residue_colors(
        self, object_id: str | None = None
    ) -> np.ndarray | None:
        """Return per-residue RGBA colors for an object.

        The result matches the colors used for the CA trace and other
        residue-based representations, including the current ``color_mode``
        and any explicit per-residue overrides.
        """
        with self._activate_object(object_id):
            coords = self._coords
            if coords is None or getattr(coords, "size", 0) <= 0:
                return None
            try:
                n_points = int(np.asarray(coords, dtype=float).shape[0])
            except Exception:
                return None
            if n_points <= 0:
                return None

            # Reuse the same color computation path used for rendering.
            try:
                self._build_scene_for_current_object(object_prefix=None)
            except Exception:
                pass

            cols = getattr(self, "_colors_per_ca", None)
            if cols is None:
                return None
            try:
                arr = np.asarray(cols, dtype=float)
            except Exception:
                return None
            if arr.ndim != 2 or arr.shape[0] != n_points:
                return None
            return arr.copy()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _has_nucleic_acids(self, residue_names: np.ndarray | None = None) -> bool:
        """Check if the current structure contains nucleic acid residues."""
        if residue_names is None:
            residue_names = getattr(self, "_residue_names", None)
        if residue_names is None:
            return False
        try:
            names_arr = np.asarray(residue_names, dtype=str)
            names_upper = np.char.upper(names_arr)
            # Check for common nucleic acid residue names
            nucleic_names = {"DA", "DC", "DG", "DT", "A", "C", "G", "T", "U"}
            return bool(nucleic_names.intersection(set(names_upper)))
        except Exception:
            return False

    def _clear_items(self) -> None:
        if self._renderer is not None:
            try:
                self._renderer.clear()
            except Exception:
                pass

    #: How a cartoon is coarsened while a trajectory is being scrubbed.
    #:
    #: All but the last are **tessellation**: how finely the ribbon is sampled
    #: along the chain and around its cross-section. They change how many
    #: triangles the same ribbon is drawn with, not where it goes, so the draft
    #: does not slide around and then settle somewhere else. Everything
    #: downstream scales with them, down to the vertices uploaded to the GPU.
    #:
    #: ``round_helices`` is the one exception and is here deliberately: it lifts
    #: the spline back onto the helix cylinder, and switching it off leaves a
    #: helix about 13% narrower through the middle of each turn (2.17 A against
    #: 1.88 A on 148L). That is a real difference, and it is included because it
    #: buys the per-residue helix-axis fit -- which tessellation cannot reduce,
    #: since it runs per residue rather than per sampled point. Rendered side by
    #: side against the settled frame the fold, the helices and the strands are
    #: indistinguishable, which is why it is an acceptable trade *while moving*.
    #: Anything that flipped the ribbon's face -- ``refine_normals``,
    #: ``flat_sheets`` -- is deliberately **not** here: a ribbon that twists
    #: differently mid-scrub and then snaps is worse than a coarser one.
    _DRAFT_CARTOON = {
        "cartoon_sampling": 3,
        "subdivisions": 3,
        "segments_circle": 8,
        "loop_quality": 7,
        "oval_quality": 8,
        "tube_quality": 8,
        "profile_segments": 8,
        "round_helices": False,
    }

    def _cartoon_config(self, config: dict) -> dict:
        """The cartoon settings to draw with, coarsened while scrubbing."""
        if not getattr(self, "_draft_quality", False):
            return config
        coarse = dict(config)
        coarse.update(self._DRAFT_CARTOON)
        return coarse

    #: A frame change arriving sooner than this after the previous one counts as
    #: a scrub rather than a look. Comfortably longer than a bake, so a
    #: trajectory played at any watchable rate stays in the cheap path.
    _SCRUB_INTERVAL_S = 0.35

    #: How long the frame has to hold still before the full-quality bake runs.
    _SETTLE_MS = 220

    def _note_frame_change(self) -> None:
        """Record a frame change and decide whether to bake occlusion for it.

        Baking ambient occlusion and cast shadows into the vertex colours costs
        more than everything else in a cartoon rebuild put together, and during
        playback it is wasted: the result is replaced before anyone can look at
        it. Skipping it while frames are arriving quickly is the same trade
        every viewer makes when you drag the mouse.

        The decision is made on **rate**, not on a mode flag, so that a single
        frame change -- a headless render, one click of a frame spinner -- is
        never quietly downgraded. Only a frame that follows hard on the heels of
        another skips the bake, and a settle timer restores full quality once
        the scrubbing stops, so what you end up looking at is always the good
        version.
        """
        now = time.perf_counter()
        previous = getattr(self, "_last_frame_change", None)
        self._last_frame_change = now
        self._draft_quality = (
            previous is not None and (now - previous) < self._SCRUB_INTERVAL_S
        )
        if not self._draft_quality:
            return
        try:
            timer = getattr(self, "_settle_timer", None)
            if timer is None:
                timer = QtCore.QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._bake_after_settling)
                self._settle_timer = timer
            timer.start(self._SETTLE_MS)
        except Exception:
            # No event loop to settle into (headless stepping). Leave the flag
            # to the rate test alone -- the next unhurried frame bakes anyway.
            logger.debug("chimol: no settle timer available", exc_info=True)

    def _bake_after_settling(self) -> None:
        """Redraw at full quality once the frame has stopped changing."""
        if not getattr(self, "_draft_quality", False):
            return
        self._draft_quality = False
        self._last_frame_change = None
        try:
            self._update_view(fit_camera=False)
        except Exception:
            logger.warning("chimol: full-quality redraw failed", exc_info=True)

    def _occlusion_occluders(
        self, override: str | None = None
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Return what casts the ambient occlusion, with radii, in scene units.

        By default this is the **residue trace**, not the atoms. A cartoon
        ribbon threads straight through its own side chains, so occluding it
        with every atom buries the whole molecule in shadow — the ribbon is
        surrounded by geometry that is not being drawn. Coarse residue-sized
        occluders stand for the bulk of the fold instead, which is what should
        darken a groove between two helices.

        Set ``occlusion.occluders`` to ``"atoms"`` for the all-atom set, which
        suits space-filling representations where the atoms *are* the picture.

        Parameters
        ----------
        override : str or None
            ``"atoms"`` or ``"residues"``, taking precedence over the config.
            Representations that know which is right for them pass it.

        Returns
        -------
        tuple or None
            ``(centres, radii)``, or ``None`` when there is nothing to occlude
            with.
        """
        cfg = _DISPLAY_CONFIG.get("occlusion") or {}
        scale = float(getattr(self, "_scale_factor", 1.0) or 1.0)
        choice = override or str(cfg.get("occluders", "residues"))
        use_atoms = choice.lower() == "atoms"

        centres = radii = None
        if use_atoms:
            centres = getattr(self, "_all_atom_coords", None)
            radii = getattr(self, "_all_atom_radii", None)
        if centres is None:
            centres = getattr(self, "_coords", None)
            radii = None
        if centres is None:
            return None

        pts = np.asarray(centres, dtype=float)
        if pts.ndim != 2 or pts.shape[0] == 0 or pts.shape[1] != 3:
            return None

        if radii is not None:
            rad = np.asarray(radii, dtype=float).reshape(-1)
            if rad.shape[0] != pts.shape[0]:
                rad = None
        else:
            rad = None
        if rad is None:
            # One sphere standing in for a whole residue, so it is sized like a
            # residue rather than like an atom.
            rad = np.full(
                pts.shape[0], float(cfg.get("residue_radius", 3.2)) * scale
            )
        return pts, rad

    def _shade_by_occlusion(
        self,
        verts: np.ndarray,
        norms: np.ndarray,
        cols: np.ndarray | None,
        *,
        occluders: str | None = None,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Darken mesh vertex colours by their ambient occlusion.

        Baked here rather than computed per frame: the occlusion of a rigid
        molecule does not depend on the camera, so paying for it once per rebuild
        costs nothing while the view moves and cannot shimmer the way a
        screen-space estimate does.

        Parameters
        ----------
        verts, norms : numpy.ndarray
            ``(N, 3)`` mesh vertices and their normals, in scene units.
        cols : numpy.ndarray or None
            ``(N, 4)`` RGBA vertex colours to modulate.
        occluders : str or None
            ``"atoms"`` or ``"residues"``; see :meth:`_occlusion_occluders`.

        Returns
        -------
        tuple
            ``(colours, occlusion)``. The occlusion is handed on to the backend
            as well, so it can damp the light that does not come from the surface
            colour; it is ``None`` when occlusion is off or could not be
            computed.
        """
        if cols is None:
            return cols, None
        if getattr(self, "_draft_quality", False):
            # Mid-scrub: this frame is about to be replaced. `_note_frame_change`
            # schedules the full-quality redraw for when it stops.
            return cols, None
        cfg = _DISPLAY_CONFIG.get("occlusion") or {}
        if not bool(cfg.get("enabled", True)):
            return cols, None

        darkness = float(cfg.get("darkness", 0.7))
        if darkness <= 0.0:
            return cols, None

        casters = self._occlusion_occluders(occluders)
        if casters is None:
            return cols, None
        centres, radii = casters

        scale = float(getattr(self, "_scale_factor", 1.0) or 1.0)
        try:
            occ = occlusion_from_spheres(
                verts,
                norms,
                centres,
                radii,
                max_distance=float(cfg.get("max_distance", 10.0)) * scale,
                strength=float(cfg.get("strength", 1.4)),
            )
        except Exception:
            logger.warning("Ambient occlusion failed; drawing unshaded",
                           exc_info=True)
            return cols, None
        if occ is None or occ.shape[0] != cols.shape[0]:
            return cols, None

        shaded = np.array(cols, dtype=float, copy=True)
        shaded[:, :3] *= (1.0 - darkness * occ)[:, None]

        # Ambient occlusion says how *enclosed* a point is; a cast shadow says
        # whether anything stands between it and the light. They are different
        # cues and the second is what PyMOL's interactive view has no equivalent
        # of at all -- it casts shadows only when raytracing.
        shadow = self._directional_shadow(verts, norms, centres, radii, cfg, scale)
        if shadow is not None:
            shadow_darkness = float(cfg.get("shadow_darkness", 0.45))
            shaded[:, :3] *= (1.0 - shadow_darkness * shadow)[:, None]
            # Fold the shadow into the occlusion channel the backend damps its
            # non-surface lighting by, so a shadowed crevice does not get its
            # ambient and rim light back.
            occ = np.clip(occ + (1.0 - occ) * shadow, 0.0, 1.0)

        return np.clip(shaded, 0.0, 1.0), occ

    def _directional_shadow(
        self,
        verts: np.ndarray,
        norms: np.ndarray,
        centres: np.ndarray,
        radii: np.ndarray,
        cfg: dict,
        scale: float,
    ) -> np.ndarray | None:
        """Per-vertex shadowing of the key light, or ``None`` when disabled."""
        if not bool(cfg.get("shadows", True)):
            return None
        # PyMOL's `light` default is (-0.4, -0.4, -1): the direction the light
        # *travels*, so the shadow ray runs the other way, toward the source. A
        # pure headlight casts almost nothing the camera can see, which is why
        # this is off-axis rather than reusing the viewport's light direction.
        light = cfg.get("shadow_direction", [0.4, 0.4, 1.0])
        try:
            shadow = directional_occlusion(
                verts,
                norms,
                centres,
                radii,
                np.asarray(light, dtype=float),
                max_distance=float(cfg.get("shadow_distance", 20.0)) * scale,
                softness=float(cfg.get("shadow_softness", 1.6)),
                strength=float(cfg.get("shadow_strength", 1.0)),
            )
        except Exception:
            logger.warning("Directional shadowing failed", exc_info=True)
            return None
        if shadow is None or shadow.shape[0] != verts.shape[0]:
            return None
        return shadow

    def _update_cartoon(
        self, coords: np.ndarray, n_points: int, config: dict, colors: np.ndarray | None
    ) -> list[SceneObject]:
        scene_objects: list[SceneObject] = []
        if not self._show_cartoon:
            return scene_objects

        ao_radius = float(config.get("ao_radius", 4.0))
        ao_max = int(config.get("ao_max_neighbors", 16))
        ao_strength = float(config.get("ao_strength", 0.45))

        # Check for nucleic acid residues to exclude them from the regular cartoon path
        nucleic_names = {
            "DA", "DC", "DG", "DT", "A", "C", "G", "T", "U",
            "2DA", "2DC", "2DG", "2DT",
            "RA", "RC", "RG", "RU", "I",
            "5MC", "5HC", "OMC", "H2U", "PSU", "M2G", "1MA", "7MG",
            "D2A", "D2C", "D2G", "D2T", "R2A", "R2C", "R2G", "R2U",
        }
        is_nuc_residue = np.zeros(n_points, dtype=bool)
        if self._residue_names is not None and len(self._residue_names) == n_points:
            for i, rname in enumerate(self._residue_names):
                try:
                    rname_str = str(rname).strip().upper()
                except Exception:
                    rname_str = ""
                if rname_str in nucleic_names:
                    is_nuc_residue[i] = True

        non_nuc_mask = ~is_nuc_residue

        coords_cartoon = coords
        colors_for_tube = colors
        idx_all = np.arange(n_points, dtype=int)
        idx_cartoon = idx_all

        # Apply per-residue cartoon mask by subselecting the CA points
        # used to build the tube, and exclude nucleic residues.
        if self._cartoon_mask is not None and len(self._cartoon_mask) == n_points:
            mask = self._cartoon_mask.astype(bool) & non_nuc_mask
        else:
            mask = non_nuc_mask

        coords_cartoon = coords[mask]
        idx_cartoon = idx_all[mask]
        if colors_for_tube is not None:
            colors_for_tube = colors_for_tube[mask]

        # The per-residue neighbour count below is superseded by the per-vertex
        # occlusion applied to the finished mesh, which is normal-aware and an
        # order of magnitude finer. Running both would darken the cartoon twice.
        occ_ca = None
        if not bool((_DISPLAY_CONFIG.get("occlusion") or {}).get("enabled", True)):
            try:
                occ_ca = _estimate_ambient_occlusion(
                    coords_cartoon,
                    radius=ao_radius,
                    max_neighbors=ao_max,
                )
            except Exception:
                occ_ca = None

        if (
            occ_ca is not None
            and np.asarray(occ_ca).shape[0] == coords_cartoon.shape[0]
            and colors_for_tube is not None
        ):
            colors_for_tube = colors_for_tube.copy()
            occ_ca_arr = np.asarray(occ_ca, dtype=float)
            shade = (1.0 - ao_strength) + ao_strength * (1.0 - occ_ca_arr)
            colors_for_tube[:, :3] *= shade.reshape(-1, 1)
            colors_for_tube = np.clip(colors_for_tube, 0.0, 1.0)

        if coords_cartoon is not None and coords_cartoon.shape[0] >= 2:
            n_cartoon = coords_cartoon.shape[0]
            idx_cartoon_arr = np.asarray(idx_cartoon, dtype=int)
            if idx_cartoon_arr.shape[0] != n_cartoon:
                idx_cartoon_arr = np.arange(n_cartoon, dtype=int)

            res_ids_full = getattr(self, "_residue_ids", None)
            chain_ids_full = getattr(self, "_residue_chain_ids", None)
            ss_full = getattr(self, "_secondary_structure", None)
            trace_ups_full = getattr(self, "_trace_ups", None)

            res_ids_cartoon = None
            if res_ids_full is not None:
                try:
                    res_full_arr = np.asarray(res_ids_full)
                    if res_full_arr.shape[0] == n_points:
                        res_ids_cartoon = res_full_arr[idx_cartoon_arr]
                except Exception:
                    res_ids_cartoon = None

            chain_ids_cartoon = None
            if chain_ids_full is not None:
                try:
                    chain_full_arr = np.asarray(chain_ids_full)
                    if chain_full_arr.shape[0] == n_points:
                        chain_ids_cartoon = chain_full_arr[idx_cartoon_arr]
                except Exception:
                    chain_ids_cartoon = None

            seg_bounds = [(0, n_cartoon)]
            if res_ids_cartoon is not None or chain_ids_cartoon is not None:
                seg_bounds = []
                start = 0
                for i in range(n_cartoon - 1):
                    gap = False
                    if chain_ids_cartoon is not None:
                        try:
                            ch0 = str(chain_ids_cartoon[i]).strip()
                            ch1 = str(chain_ids_cartoon[i + 1]).strip()
                        except Exception:
                            ch0 = ch1 = ""
                        if ch0 != ch1:
                            gap = True
                    if not gap and res_ids_cartoon is not None:
                        try:
                            r0 = int(res_ids_cartoon[i])
                            r1 = int(res_ids_cartoon[i + 1])
                            if (r1 - r0) != 1:
                                gap = True
                        except Exception:
                            pass
                    if gap:
                        if i + 1 - start >= 2:
                            seg_bounds.append((start, i + 1))
                        start = i + 1
                if n_cartoon - start >= 2:
                    seg_bounds.append((start, n_cartoon))
                if not seg_bounds and n_cartoon >= 2:
                    seg_bounds = [(0, n_cartoon)]

            ss_full_arr = None
            if ss_full is not None:
                try:
                    ss_full_arr = np.asarray(ss_full)
                except Exception:
                    ss_full_arr = None

            trace_ups_cartoon = None
            if trace_ups_full is not None:
                try:
                    ups_full_arr = np.asarray(trace_ups_full, dtype=float)
                    if ups_full_arr.shape[0] == n_points:
                        trace_ups_cartoon = ups_full_arr[idx_cartoon_arr]
                except Exception:
                    trace_ups_cartoon = None

            for start, end in seg_bounds:
                seg_coords = coords_cartoon[start:end]
                if seg_coords.shape[0] < 2:
                    continue

                if colors_for_tube is not None:
                    seg_colors = colors_for_tube[start:end]
                else:
                    seg_colors = None

                if trace_ups_cartoon is not None and trace_ups_cartoon.shape[0] == n_cartoon:
                    seg_trace_ups = trace_ups_cartoon[start:end]
                else:
                    seg_trace_ups = None

                seg_ss = None
                if ss_full_arr is not None and ss_full_arr.shape[0] == n_points:
                    seg_indices = idx_cartoon_arr[start:end]
                    seg_ss = ss_full_arr[seg_indices]

                seg_putty = None
                if str(config.get("style", "tube")).lower() == "putty":
                    seg_putty = self._trace_bfactors(idx_cartoon_arr[start:end])

                arrays = _generate_cartoon_tube_arrays(
                    seg_coords,
                    seg_colors,
                    seg_trace_ups,
                    base_radius=float(config.get("tube_radius", 0.5)),
                    style=str(config.get("style", "tube")),
                    ss_codes=seg_ss,
                    config={**config, "coordinate_scale": float(self._scale_factor)},
                    putty_values=seg_putty,
                )

                if arrays is not None:
                    verts, norms, faces_arr, cols = arrays
                    cols, occ = self._shade_by_occlusion(verts, norms, cols)
                    geom = Geometry(
                        kind="mesh",
                        positions=verts,
                        indices=faces_arr,
                        normals=norms,
                        colors=cols,
                        occlusion=occ,
                    )
                    scene_objects.append(
                        SceneObject(id="cartoon", geometry=geom, render_mode="opaque")
                    )

        # Generate nucleic cartoon for DNA/RNA structures
        if self._has_nucleic_acids() and self._atoms is not None and self._all_atom_coords is not None:
            nuc_arrays = _generate_nucleic_cartoon_arrays(
                self._atoms,
                self._all_atom_coords,
                getattr(self, "_residue_ids", None),
                getattr(self, "_residue_chain_ids", None),
                colors,
                config={**config, "coordinate_scale": float(self._scale_factor)},
            )
            if nuc_arrays is not None:
                nuc_verts, nuc_norms, nuc_faces, nuc_cols = nuc_arrays
                nuc_cols, nuc_occ = self._shade_by_occlusion(
                    nuc_verts, nuc_norms, nuc_cols
                )
                nuc_geom = Geometry(
                    kind="mesh",
                    positions=nuc_verts,
                    indices=nuc_faces,
                    normals=nuc_norms,
                    colors=nuc_cols,
                    occlusion=nuc_occ,
                    # Flat base-ring plates need two-sided lighting so they are
                    # not dark from the anti-light face.
                    meta={"two_sided": True},
                )
                scene_objects.append(
                    SceneObject(id="cartoon_nucleic", geometry=nuc_geom, render_mode="opaque")
                )

        return scene_objects

    def _update_trace(self, coords: np.ndarray, colors: np.ndarray | None) -> list[SceneObject]:
        scene_objects: list[SceneObject] = []
        if not self._show_trace:
            return scene_objects

        res_ids = getattr(self, "_residue_ids", None)
        chain_ids = getattr(self, "_residue_chain_ids", None)

        # Build segment boundaries at chain/residue-number breaks
        n = coords.shape[0]
        seg_bounds = [(0, n)]
        if n >= 2 and (res_ids is not None or chain_ids is not None):
            seg_bounds = []
            start = 0
            for i in range(n - 1):
                gap = False
                if chain_ids is not None and i < len(chain_ids) and (i + 1) < len(chain_ids):
                    ch0 = str(chain_ids[i]).strip()
                    ch1 = str(chain_ids[i + 1]).strip()
                    if ch0 != ch1:
                        gap = True
                if not gap and res_ids is not None and i < len(res_ids) and (i + 1) < len(res_ids):
                    try:
                        r0 = int(res_ids[i])
                        r1 = int(res_ids[i + 1])
                        if (r1 - r0) != 1:
                            gap = True
                    except Exception:
                        pass
                if gap:
                    if i + 1 - start >= 2:
                        seg_bounds.append((start, i + 1))
                    start = i + 1
            if n - start >= 2:
                seg_bounds.append((start, n))
            if not seg_bounds and n >= 2:
                seg_bounds = [(0, n)]

        for s, e in seg_bounds:
            seg_coords = coords[s:e]
            seg_colors = colors[s:e] if colors is not None and s < len(colors) else None
            coords_line, colors_line = _generate_trace_arrays(seg_coords, seg_colors)
            if colors_line is None:
                colors_line = seg_colors
            geom = Geometry(kind="line", positions=coords_line, colors=colors_line)
            scene_objects.append(SceneObject(id="trace", geometry=geom, render_mode="opaque"))

        return scene_objects

    @staticmethod
    def _balls_sphere_segments() -> tuple[int, int]:
        """Return the (lat, lon) tessellation for atom-ball glyphs.

        Atom balls are drawn thousands at a time and small on screen, so they use
        a much coarser sphere than the 16x32 default; the resolution is
        config-tunable via the ``balls`` section.
        """
        balls_cfg = _DISPLAY_CONFIG.get("balls", {})
        lat = int(balls_cfg.get("sphere_lat", 10))
        lon = int(balls_cfg.get("sphere_lon", 16))
        return max(3, lat), max(3, lon)

    @staticmethod
    def _build_balls_mesh(
        pts: np.ndarray,
        colors_rgb: np.ndarray,
        radii: np.ndarray,
    ) -> SceneObject | None:
        """Merge per-atom spheres into a single ``atoms_mesh`` scene object.

        Parameters
        ----------
        pts : numpy.ndarray
            Atom centres of shape ``(N, 3)``, already centred and scaled.
        colors_rgb : numpy.ndarray
            Per-atom RGB colours of shape ``(N, 3)``.
        radii : numpy.ndarray
            Per-atom sphere radii of shape ``(N,)``.

        Returns
        -------
        SceneObject or None
            The merged mesh, or ``None`` when no geometry could be built.
        """
        n_atoms = int(pts.shape[0])
        if n_atoms == 0:
            return None
        lat, lon = MolView._balls_sphere_segments()
        sphere_mesh = _build_sphere_mesh(1.0, lat, lon)
        if sphere_mesh is None:
            return None
        base_verts = sphere_mesh.get("vertices")
        base_norms = sphere_mesh.get("normals")
        base_faces = sphere_mesh.get("faces")
        if (
            base_verts is None
            or base_faces is None
            or base_norms is None
            or not base_verts.size
            or not base_faces.size
            or not base_norms.size
        ):
            return None
        n_verts = base_verts.shape[0]
        verts = base_verts[np.newaxis, :, :] * np.asarray(radii, dtype=float)[
            :, np.newaxis, np.newaxis
        ]
        verts += np.asarray(pts, dtype=float)[:, np.newaxis, :]
        verts = verts.reshape(-1, 3)
        # Broadcasting avoids the intermediate copies that np.repeat allocates.
        offsets = (np.arange(n_atoms, dtype=base_faces.dtype) * n_verts)[
            :, np.newaxis, np.newaxis
        ]
        faces = (base_faces[np.newaxis, :, :] + offsets).reshape(-1, 3)
        norms = np.broadcast_to(
            base_norms[np.newaxis, :, :], (n_atoms, n_verts, 3)
        ).reshape(-1, 3)
        rgba = np.ones((n_atoms, 4), dtype=float)
        rgba[:, :3] = np.clip(np.asarray(colors_rgb, dtype=float)[:, :3], 0.0, 1.0)
        vcols = np.broadcast_to(
            rgba[:, np.newaxis, :], (n_atoms, n_verts, 4)
        ).reshape(-1, 4)
        geom = Geometry(
            kind="mesh", positions=verts, indices=faces, normals=norms, colors=vcols
        )
        return SceneObject(id="atoms_mesh", geometry=geom, render_mode="opaque")

    def _update_atoms(
        self,
        coords: np.ndarray,
        n_points: int,
        balls_cfg: dict,
        colors_per_ca: np.ndarray | None
    ) -> list[SceneObject] | None:
        scene_objects: list[SceneObject] = []
        if not self._show_atoms:
            return scene_objects

        balls_size_scale = float(balls_cfg.get("size_scale", 0.04))
        balls_min_size = float(balls_cfg.get("min_size", 3.0))
        balls_radius_multiplier = float(balls_cfg.get("radius_multiplier", 1.0))
        balls_ao_radius = float(balls_cfg.get("ao_radius", 4.0))
        balls_ao_max = int(balls_cfg.get("max_neighbors", 24))
        balls_ao_strength = float(balls_cfg.get("ao_strength", 0.5))
        balls_max_atoms = int(balls_cfg.get("max_atoms", 8000))
        base_global_radius = max(self._radius * balls_size_scale, balls_min_size)

        # Raw-coordinate objects (the PDB fallback) have no structured ``_atoms``
        # array, so the per-residue ball path below is skipped and only a sparse
        # CA sampling of the trace would be drawn. Render every atom straight
        # from the all-atom coordinates instead, mirroring get_atom_sphere_data.
        if self._atoms is None and self._all_atom_coords is not None:
            pts, colors_rgb, radii = self.get_atom_sphere_data()
            if pts.shape[0] == 0:
                return scene_objects
            # Honour an explicit per-atom selection mask when one is present and
            # matches the atom count; otherwise show the whole molecule.
            if (
                self._ball_mask is not None
                and len(self._ball_mask) == pts.shape[0]
                and self._ball_mask.any()
            ):
                sel = np.asarray(self._ball_mask, dtype=bool)
                pts = pts[sel]
                colors_rgb = colors_rgb[sel]
                radii = radii[sel]
            if pts.shape[0] and balls_max_atoms > 0 and pts.shape[0] > balls_max_atoms:
                step = max(1, pts.shape[0] // balls_max_atoms)
                pts = pts[::step]
                colors_rgb = colors_rgb[::step]
                radii = radii[::step]
            obj = self._build_balls_mesh(pts, colors_rgb, radii)
            if obj is not None:
                scene_objects.append(obj)
            return scene_objects

        used_all_atoms_for_balls = False
        # The body below handles both a per-atom and a per-residue mask; this
        # guard used to admit only the per-residue length, so a per-atom
        # selection (which is what `show spheres, <sel>` and the hetero-atom
        # default produce) fell through to the coarse per-CA sampling instead.
        n_all_atoms = (
            self._all_atom_coords.shape[0]
            if self._all_atom_coords is not None
            else -1
        )
        if (
            self._ball_mask is not None
            and len(self._ball_mask) in (n_points, n_all_atoms)
            and self._ball_mask.any()
            and self._atoms is not None
            and self._residue_ids is not None
        ):
            atoms = self._atoms
            fields_atoms = set(atoms.dtype.fields or {})
            atom_names = None
            if "res_id" in fields_atoms:
                try:
                    atom_res_id = np.asarray(atoms["res_id"])
                except Exception:
                    atom_res_id = None
            else:
                atom_res_id = None

            # Prefer the already-centered and scaled all-atom coordinates so
            # atoms and cartoon/surface share the exact same frame.
            if self._all_atom_coords is not None:
                atom_xyz = np.asarray(self._all_atom_coords, dtype=float)
            elif "xyz" in fields_atoms:
                try:
                    atom_xyz = np.asarray(atoms["xyz"], dtype=float)
                except Exception:
                    atom_xyz = None
            else:
                atom_xyz = None

            if "atom_name" in fields_atoms:
                try:
                    atom_names = np.char.strip(atoms["atom_name"].astype(str))
                except Exception:
                    atom_names = None

            if atom_xyz is not None and atom_res_id is not None:
                n_atoms_total = atom_xyz.shape[0]

                if self._ball_mask is not None and len(self._ball_mask) == n_atoms_total:
                    # Per-atom mask
                    atom_mask = self._ball_mask.astype(bool)
                elif self._ball_mask is not None and len(self._ball_mask) == n_points:
                    # Legacy: residue-level mask
                    sel_idx = np.nonzero(self._ball_mask)[0]
                    sel_res_ids = np.unique(self._residue_ids[sel_idx])
                    atom_mask = np.isin(atom_res_id, sel_res_ids)
                else:
                    atom_mask = np.zeros(n_atoms_total, dtype=bool)

                # Optionally hide sidechains and keep only backbone atoms
                if not getattr(self, "_sidechains_visible", True) and atom_names is not None:
                    backbone_names = np.array(["N", "CA", "C", "O", "CB"], dtype=atom_names.dtype)
                    backbone_mask = np.isin(atom_names, backbone_names)
                    atom_mask = atom_mask & backbone_mask

                pts = atom_xyz[atom_mask]
                if pts.size:
                    pts = np.asarray(pts, dtype=float)
                    radii_sel: np.ndarray | None
                    if (
                        self._all_atom_radii is not None
                        and len(self._all_atom_radii) == atom_xyz.shape[0]
                    ):
                        try:
                            radii_sel = np.asarray(self._all_atom_radii, dtype=float)[atom_mask]
                        except Exception:
                            radii_sel = None
                    else:
                        radii_sel = None

                    colors = np.zeros((pts.shape[0], 4), dtype=float)
                    colors[:] = np.asarray(self._base_color_single, dtype=float)

                    # Start from per-residue colors_per_ca if present.
                    if (
                        colors_per_ca is not None
                        and len(colors_per_ca) == len(self._residue_ids)
                    ):
                        color_map = {rid: colors_per_ca[i_res] for i_res, rid in enumerate(self._residue_ids)}
                    else:
                        color_map = {}

                    # Atoms the cartoon never colours -- waters, ions, ligands --
                    # get their element's CPK colour instead of the flat base
                    # colour, so a water oxygen reads as red the way it does in
                    # every other viewer rather than as an anonymous grey ball.
                    sel_atom_res = atom_res_id[atom_mask]
                    element_colors = None
                    if "element" in fields_atoms:
                        try:
                            element_colors = _build_element_color_array(
                                np.asarray(atoms["element"])[atom_mask], pts.shape[0]
                            )
                        except Exception:
                            element_colors = None
                    for i_atom, rid in enumerate(sel_atom_res):
                        base_col = color_map.get(rid)
                        if base_col is None:
                            base_col = (
                                element_colors[i_atom]
                                if element_colors is not None
                                else self._base_color_single
                            )
                        colors[i_atom, :] = base_col

                    # Apply per-atom override if present.
                    if (
                        getattr(self, "_colors_per_atom_override", None) is not None
                        and len(self._colors_per_atom_override) == atom_res_id.shape[0]
                    ):
                        ov = np.asarray(self._colors_per_atom_override, dtype=float)
                        ov_sel = ov[atom_mask]
                        for i_atom in range(pts.shape[0]):
                            col_ov = ov_sel[i_atom]
                            if np.isfinite(col_ov).all():
                                colors[i_atom, :] = col_ov

                    # Make balls fully opaque
                    colors[:, 3] = 1.0

                    # Lightweight ambient-occlusion style darkening to
                    # improve depth perception in ball view.
                    try:
                        occ_balls = _estimate_ambient_occlusion(
                            pts,
                            radius=balls_ao_radius,
                            max_neighbors=balls_ao_max,
                        )
                    except Exception:
                        occ_balls = None
                    if (
                        occ_balls is not None
                        and np.asarray(occ_balls).shape[0] == pts.shape[0]
                    ):
                        occ_b = np.asarray(occ_balls, dtype=float)
                        shade_balls = (1.0 - balls_ao_strength) + (
                            balls_ao_strength * (1.0 - occ_b)
                        )
                        colors[:, :3] *= shade_balls.reshape(-1, 1)
                        colors = np.clip(colors, 0.0, 1.0)

                    max_atoms = max(1, balls_max_atoms)
                    if pts.shape[0] > max_atoms:
                        step = max(1, pts.shape[0] // max_atoms)
                        pts = pts[::step]
                        colors = colors[::step]
                        if radii_sel is not None and radii_sel.shape[0] >= pts.shape[0]:
                            radii_sel = radii_sel[::step]

                    if radii_sel is not None and radii_sel.shape[0] == pts.shape[0]:
                        radii_for_mesh = radii_sel * balls_radius_multiplier
                    else:
                        radii_for_mesh = np.full(
                            pts.shape[0], base_global_radius, dtype=float
                        )

                    invalid_r = (~np.isfinite(radii_for_mesh)) | (radii_for_mesh <= 0.0)
                    if invalid_r.any():
                        radii_for_mesh[invalid_r] = base_global_radius
                    radii_for_mesh = np.maximum(radii_for_mesh, balls_min_size)

                    # PyMOL's nonbonded_size applies to atoms that have no bonds
                    # -- waters and free ions -- so a shell of full-size solvent
                    # spheres does not bury the molecule it surrounds. It is
                    # *not* a non-polymer rule: a bonded ligand is drawn at full
                    # van-der-Waals radius, exactly as the protein is. Testing
                    # "not in the polymer colour map" instead shrank every
                    # ligand to a quarter of its size, which is why `show
                    # spheres, organic` came out as a scatter of dots.
                    nonbonded_scale = float(balls_cfg.get("nonbonded_size", 0.25))
                    if 0.0 < nonbonded_scale < 1.0:
                        unbonded = self._unbonded_atom_mask()
                        if unbonded is not None and atom_mask is not None:
                            try:
                                sel_unbonded = unbonded[atom_mask]
                            except Exception:
                                sel_unbonded = None
                            if (
                                sel_unbonded is not None
                                and sel_unbonded.shape[0] == radii_for_mesh.shape[0]
                                and sel_unbonded.any()
                            ):
                                radii_for_mesh[sel_unbonded] *= nonbonded_scale

                    # Render all balls for the current selection as a
                    # single merged mesh. This is much faster than
                    # creating one GLMeshItem per atom while still
                    # providing proper shaded spheres, similar to pyball.
                    _lat, _lon = self._balls_sphere_segments()
                    sphere_mesh = _build_sphere_mesh(1.0, _lat, _lon)
                    if sphere_mesh is not None and pts.shape[0] > 0:
                        base_verts = sphere_mesh.get("vertices")
                        base_norms = sphere_mesh.get("normals")
                        base_faces = sphere_mesh.get("faces")
                        if (
                            base_verts is not None
                            and base_faces is not None
                            and base_norms is not None
                            and base_verts.size
                            and base_faces.size
                            and base_norms.size
                        ):
                            if (
                                base_verts is not None
                                and base_faces is not None
                                and base_norms is not None
                                and base_verts.size
                                and base_faces.size
                                and base_norms.size
                            ):
                                n_atoms = pts.shape[0]
                                n_verts = base_verts.shape[0]

                                # Duplicate and translate sphere vertices for
                                # each atom center: (N_atoms, N_verts, 3)
                                verts = base_verts[np.newaxis, :, :] * (
                                    radii_for_mesh[:, np.newaxis, np.newaxis]
                                )
                                verts += pts[:, np.newaxis, :]
                                verts = verts.reshape(-1, 3)

                                # Duplicate faces with index offsets
                                faces = np.repeat(
                                    base_faces[np.newaxis, :, :], n_atoms, axis=0
                                )
                                offsets = (
                                    np.arange(n_atoms, dtype=base_faces.dtype)
                                    * n_verts
                                )
                                faces += offsets[:, np.newaxis, np.newaxis]
                                faces = faces.reshape(-1, 3)

                                norms = np.repeat(
                                    base_norms[np.newaxis, :, :], n_atoms, axis=0
                                ).reshape(-1, 3)

                                vcols = None
                                try:
                                    col_arr = np.asarray(colors, dtype=float)
                                    if col_arr.shape[0] == n_atoms:
                                        vcols = np.repeat(
                                            col_arr[:, np.newaxis, :],
                                            n_verts,
                                            axis=1,
                                        ).reshape(-1, 4)
                                except Exception:
                                    vcols = None

                                # Space-filling spheres are shaded against the
                                # atoms themselves: here the atoms are the
                                # picture, not hidden bulk.
                                ball_cols, ball_occ = self._shade_by_occlusion(
                                    verts, norms, vcols, occluders="atoms"
                                )
                                geom = Geometry(
                                    kind="mesh",
                                    positions=verts,
                                    indices=faces,
                                    normals=norms,
                                    colors=ball_cols,
                                    occlusion=ball_occ,
                                )
                                scene_objects.append(
                                    SceneObject(id="atoms_mesh", geometry=geom, render_mode="opaque")
                                )

                                used_all_atoms_for_balls = True

        if self._show_atoms and not used_all_atoms_for_balls:
            sphere_radius = max(self._radius * balls_size_scale * 0.5, balls_min_size * 0.1)
            sphere = _build_sphere_mesh(radius=sphere_radius)
            if (
                self._ball_mask is not None
                and len(self._ball_mask) == n_points
                and self._ball_mask.any()
            ):
                indices = np.nonzero(self._ball_mask)[0]
            else:
                # Default: sparse sampling along the chain
                step = max(1, n_points // 50)
                indices = np.arange(0, n_points, step, dtype=int)

            point_positions: list[np.ndarray] = []
            point_colors: list[np.ndarray] = []

            for i in indices:
                center = coords[i]
                color = (
                    colors_per_ca[i]
                    if colors_per_ca is not None
                    else self._base_color_single
                )
                color_local = np.array(color, dtype=float)
                color_local[3] = 1.0
                point_positions.append(center)
                point_colors.append(color_local)

            if point_positions:
                radii_vals = None
                beads = getattr(self, "_bead_radii", None)
                if beads is not None and len(beads) == len(indices):
                    radii_vals = np.asarray(beads[indices], dtype=float)

                geom = Geometry(
                    kind="points",
                    positions=np.asarray(point_positions, dtype=float),
                    colors=np.asarray(point_colors, dtype=float),
                    radii=radii_vals,
                    meta={"glyph": "sphere", "radius": sphere_radius},
                )
                scene_objects.append(
                    SceneObject(id="atoms_points", geometry=geom, render_mode="opaque")
                )

        return scene_objects if scene_objects else None

    def get_atom_sphere_data(
        self, *, visible_only: bool = False
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Extract atom positions, colors (RGB), and radii for ray tracing.

        By default returns ALL atoms of the active object regardless of
        representation, which is what the atom-gaussian overlay wants. Pass
        ``visible_only`` for what is actually *drawn* as spheres -- ``ray`` needs
        that, or it traces a hidden molecule.  Radii are
        estimated from the ``radius`` field or the bounding sphere when per-atom
        radii are unavailable.

        Returns three arrays suitable for building a list of :class:`Sphere`:
        (positions, colors, radii) where positions is (N, 3), colors (N, 3),
        and radii (N,) — all in world / model coordinates.  If no atom data
        is available, returns empty arrays.
        """
        positions = np.zeros((0, 3), dtype=float)
        colors_rgb = np.zeros((0, 3), dtype=float)
        radii_arr = np.zeros((0,), dtype=float)

        balls_cfg = _DISPLAY_CONFIG.get("balls", {})
        balls_size_scale = float(balls_cfg.get("size_scale", 0.04))
        balls_min_size = float(balls_cfg.get("min_size", 3.0))
        balls_radius_multiplier = float(balls_cfg.get("radius_multiplier", 1.0))
        base_global_radius = max(self._radius * balls_size_scale, balls_min_size)

        atoms = self._atoms
        atom_xyz = self._all_atom_coords
        if atom_xyz is None and atoms is not None and "xyz" in (atoms.dtype.fields or {}):
            atom_xyz = np.asarray(atoms["xyz"], dtype=float)
        if atom_xyz is None:
            return positions, colors_rgb, radii_arr
        pts = np.asarray(atom_xyz, dtype=float)

        n_atoms_total = pts.shape[0]

        # --- Radii ---
        if (
            self._all_atom_radii is not None
            and len(self._all_atom_radii) == n_atoms_total
        ):
            radii_arr = np.asarray(self._all_atom_radii, dtype=float)
            radii_arr = radii_arr * balls_radius_multiplier
        else:
            radii_arr = np.full(n_atoms_total, base_global_radius, dtype=float)
        radii_arr[np.isnan(radii_arr) | (radii_arr <= 0.0)] = base_global_radius

        # --- Colors ---
        colors_4 = np.zeros((n_atoms_total, 4), dtype=float)
        colors_4[:] = np.asarray(self._base_color_single, dtype=float)

        if atoms is not None:
            n_points = len(self._residue_ids) if self._residue_ids is not None else 0
            if (
                self._colors_per_ca is not None
                and len(self._colors_per_ca) == n_points
            ):
                atom_res_id = None
                if "res_id" in (atoms.dtype.fields or {}):
                    try:
                        atom_res_id = np.asarray(atoms["res_id"])
                    except Exception:
                        atom_res_id = None
                if atom_res_id is not None:
                    for i_atom in range(n_atoms_total):
                        rid = atom_res_id[i_atom]
                        idx_in_res = np.where(self._residue_ids == rid)[0]
                        if len(idx_in_res) > 0:
                            colors_4[i_atom, :3] = self._colors_per_ca[idx_in_res[0], :3]
                        else:
                            colors_4[i_atom, :3] = self._base_color_single[:3]

            # Per-atom overrides
            ov = getattr(self, "_colors_per_atom_override", None)
            if ov is not None and len(ov) == n_atoms_total:
                ov_arr = np.asarray(ov, dtype=float)
                for i_atom in range(n_atoms_total):
                    if np.isfinite(ov_arr[i_atom]).all():
                        colors_4[i_atom, :3] = ov_arr[i_atom, :3]

        colors_rgb = np.clip(colors_4[:, :3], 0.0, 1.0)

        if visible_only:
            shown = self.sphere_visible_mask()
            if shown is not None and shown.shape[0] == n_atoms_total:
                return pts[shown], colors_rgb[shown], radii_arr[shown]

        return pts, colors_rgb, radii_arr

    def _trace_bfactors(self, residue_indices) -> np.ndarray | None:
        """The b-factor of each traced residue, for a putty cartoon.

        A putty tube's thickness is a *per-residue* number, so the per-atom
        b-factors are reduced to one value per residue — the guide atom's, since
        that is the atom the cartoon path runs through.

        Parameters
        ----------
        residue_indices : sequence of int
            Indices into the residue arrays for this cartoon segment.

        Returns
        -------
        numpy.ndarray or None
            One value per residue, or ``None`` when the structure carries no
            b-factors, which draws a uniform tube rather than failing.
        """
        atoms = self._atoms
        if atoms is None or "bfactor" not in (atoms.dtype.names or ()):
            return None
        res_ids = self._all_atom_res_ids
        residue_ids = self._residue_ids
        if res_ids is None or residue_ids is None:
            return None

        try:
            wanted = np.asarray(residue_ids)[np.asarray(residue_indices, dtype=int)]
        except Exception:
            return None

        bfactor = np.asarray(atoms["bfactor"], dtype=float)
        per_atom_res = np.asarray(res_ids)
        # Mean over the residue's atoms: the guide atom alone would be noisier,
        # and for a property written in by `alter` it is usually constant across
        # the residue anyway.
        out = np.zeros(len(wanted), dtype=float)
        for position, residue in enumerate(wanted):
            chosen = per_atom_res == residue
            if np.any(chosen):
                out[position] = float(bfactor[chosen].mean())
        return out

    def _infer_bonds(self, coords, atoms) -> np.ndarray | None:
        """Infer covalent bonds from radii, as PyMOL does.

        A single global distance cutoff has to be wide enough for the longest real
        bond, which makes it wide enough for a mere *contact* between two heavier
        atoms -- and every bond-based selection inherits the false bonds that
        follow. Per-element radii fix that at the source.

        Falls back to the old global cutoff when the structure carries no radii,
        since some coordinate-only objects do not.
        """
        if coords is None:
            return None
        raw = np.asarray(coords, dtype=float)

        names = (atoms.dtype.names or ()) if atoms is not None else ()
        if atoms is not None and "radius" in names and len(atoms) == raw.shape[0]:
            radii = np.asarray(atoms["radius"], dtype=float)
            if np.any(radii > 0):
                elements = (
                    atoms["element"] if "element" in names
                    else np.full(len(atoms), "C")
                )
                sticks_cfg = _DISPLAY_CONFIG.get("sticks", {})
                return build_bond_pairs_by_element(
                    raw, radii, elements,
                    cutoff=float(sticks_cfg.get("connect_cutoff", 0.35)),
                )

        sticks_cfg = _DISPLAY_CONFIG.get("sticks", {})
        max_bond_len = float(sticks_cfg.get("bond_max_length", 1.9))
        if np.isfinite(max_bond_len) and max_bond_len > 0.0:
            return _build_bond_pairs(raw, max_bond_len)
        return None

    def sphere_visible_mask(self) -> np.ndarray | None:
        """Which atoms are currently drawn as something the ray tracer can trace.

        The tracer knows spheres, so this covers the representations built out of
        them -- spheres/atoms, sticks and nonbonded -- and deliberately not the
        cartoon, whose ribbon geometry the tracer has no primitive for.

        Returns
        -------
        numpy.ndarray or None
            Boolean per-atom mask, or ``None`` when the object has no atoms.

        Notes
        -----
        Without this, ``ray`` traced every atom in every state: ``hide
        everything`` and ``show spheres, resn NAG`` produced the identical
        picture of the whole molecule.
        """
        coords = self._all_atom_coords
        if coords is None:
            return None
        n_atoms = int(np.asarray(coords).shape[0])
        mask = np.zeros(n_atoms, dtype=bool)

        # The per-atom mask is the authority where one exists, and the boolean
        # flag is the whole-object fallback. `show spheres, resn NAG` sets the
        # mask and leaves the flag alone, so reading only the flag sees nothing.
        for flag, mask_attr in (
            ("_show_atoms", "_ball_mask"),
            ("_show_sticks", "_sticks_mask"),
            ("_show_nonbonded", None),
        ):
            selected = getattr(self, mask_attr, None) if mask_attr else None
            if selected is not None:
                selected = np.asarray(selected)
                if selected.shape[0] == n_atoms:
                    mask |= selected.astype(bool)
                    continue
            if bool(getattr(self, flag, False)):
                mask[:] = True
                break
        return mask

    def get_ray_view_state(self) -> list[float]:
        """Return the current 18-float view tuple for ray-traced camera setup."""
        renderer = getattr(self, "_renderer", None)
        if renderer is not None and hasattr(renderer, "get_view_state"):
            return renderer.get_view_state()
        return [1.0, 0.0, 0.0,
                0.0, 1.0, 0.0,
                0.0, 0.0, 1.0,
                50.0, 20.0, 45.0,
                0.0, 0.0, 0.0,
                0.1, 100.0, 45.0]

    def get_current_scene(self) -> Scene | None:
        """Return the currently visible scene description.

        Returns
        -------
        Scene or None
            Current backend-neutral scene object used by the OpenGL renderer.
        """
        return self._scene

    def grab_current_view_image(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> QtGui.QImage | None:
        """Grab the currently visible OpenGL view as a QImage.

        Parameters
        ----------
        width, height:
            Optional output dimensions. When both are provided, the grabbed
            image is scaled to that exact size.

        Returns
        -------
        QtGui.QImage or None
            Snapshot of the current viewport, or ``None`` if unavailable.
        """
        renderer = getattr(self, "_renderer", None)
        widget = renderer.widget() if renderer is not None and hasattr(renderer, "widget") else None
        grab = getattr(widget, "grabFramebuffer", None)
        if not callable(grab):
            return None
        try:
            image = grab()
        except Exception:
            return None
        if image is None or image.isNull():
            return None
        if width and height and width > 0 and height > 0 and (image.width() != width or image.height() != height):
            image = image.scaled(
                int(width),
                int(height),
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        return image

    def show_ray_overlay(self, image: QtGui.QImage) -> bool:
        """Show a rendered image over the OpenGL viewport until interaction.

        Parameters
        ----------
        image:
            Rendered image to display.

        Returns
        -------
        bool
            ``True`` when the overlay was shown.
        """
        container = getattr(self, "_container", None)
        if container is None or image is None or image.isNull():
            return False
        overlay = self._ray_overlay
        if overlay is None:
            overlay = QtWidgets.QLabel(container)
            overlay.setAlignment(QtCore.Qt.AlignCenter)
            overlay.setScaledContents(True)
            overlay.setStyleSheet("background-color: black;")
            overlay.installEventFilter(self)
            self._ray_overlay = overlay
            layout = container.layout()
            if layout is not None:
                layout.addWidget(overlay, 0, 0)
        overlay.setPixmap(QtGui.QPixmap.fromImage(image))
        overlay.show()
        overlay.raise_()
        return True

    def hide_ray_overlay(self) -> None:
        """Hide the ray-rendered overlay if visible."""
        overlay = self._ray_overlay
        if overlay is not None:
            overlay.hide()

    def eventFilter(self, obj, event):  # type: ignore[override]
        """Dismiss ray overlay on user interaction."""
        if obj is self._ray_overlay and event is not None:
            if event.type() in (
                QtCore.QEvent.MouseButtonPress,
                QtCore.QEvent.MouseButtonDblClick,
                QtCore.QEvent.Wheel,
                QtCore.QEvent.KeyPress,
            ):
                self.hide_ray_overlay()
                return True
        return super().eventFilter(obj, event)

    def _update_atom_gaussians(self, config: dict) -> list[SceneObject] | None:
        if not self._show_atom_gaussians:
            return None

        features = getattr(self, "_atom_features", None) or {}
        covariances = features.get("gaussian_covariances")
        if covariances is None:
            return None

        coords = self._all_atom_coords
        if coords is None:
            coords = self._coords
        if coords is None:
            return None
        coords = np.asarray(coords, dtype=float)
        cov_arr = _coerce_covariance_array(covariances)
        if cov_arr is None:
            return None

        n_atoms = coords.shape[0]
        if n_atoms == 0:
            return None
        if cov_arr.shape[0] != n_atoms:
            count = min(n_atoms, cov_arr.shape[0])
            coords = coords[:count]
            cov_arr = cov_arr[:count]
            n_atoms = count

        valid = np.isfinite(coords).all(axis=1) & np.isfinite(cov_arr.reshape(n_atoms, -1)).all(axis=1)
        if not valid.any():
            return None

        meta_map = getattr(self, "_atom_feature_meta", None) or {}
        feature_meta = meta_map.get("gaussian_covariances", {}) or {}

        idx_override = feature_meta.get("indices") if isinstance(feature_meta, dict) else None
        if idx_override is not None:
            try:
                idx_override = np.asarray(idx_override, dtype=int)
                idx_override = idx_override[(idx_override >= 0) & (idx_override < n_atoms)]
            except Exception:
                idx_override = None

        indices = np.nonzero(valid)[0]
        if idx_override is not None and idx_override.size:
            indices = np.intersect1d(indices, idx_override, assume_unique=False)
        if indices.size == 0:
            return None

        def _resolve_float(key: str, default: float) -> float:
            value = default
            if isinstance(feature_meta, dict) and key in feature_meta:
                value = feature_meta[key]
            elif key in config:
                value = config[key]
            try:
                return float(value)
            except Exception:
                return float(default)

        scale = _resolve_float("scale", float(config.get("scale", 1.0)))
        min_axis = _resolve_float("min_axis", float(config.get("min_axis", 0.15)))
        max_axis = _resolve_float("max_axis", float(config.get("max_axis", 5.0)))
        max_atoms = int(_resolve_float("max_atoms", float(config.get("max_atoms", 256))))

        if max_atoms > 0 and indices.size > max_atoms:
            indices = indices[:max_atoms]

        color_default = config.get("color", [1.0, 0.5, 0.2, 0.35])
        if isinstance(feature_meta, dict) and "color" in feature_meta:
            color_default = feature_meta["color"]
        base_color = np.asarray(color_default, dtype=float)
        if base_color.shape[0] != 4:
            base_color = np.array([1.0, 0.5, 0.2, 0.35], dtype=float)

        per_atom_colors = None
        if isinstance(feature_meta, dict) and "colors" in feature_meta:
            try:
                per_atom_colors = np.asarray(feature_meta["colors"], dtype=float)
            except Exception:
                per_atom_colors = None

        sphere_mesh = _build_sphere_mesh(radius=1.0)
        if sphere_mesh is None:
            return None
        base_verts = np.asarray(sphere_mesh.get("vertices"))
        base_normals = np.asarray(sphere_mesh.get("normals"))
        base_faces = np.asarray(sphere_mesh.get("faces"), dtype=int)
        if base_verts.size == 0 or base_faces.size == 0:
            return None

        n_sel = indices.size
        n_verts = base_verts.shape[0]
        positions = np.zeros((n_sel * n_verts, 3), dtype=float)
        normals = np.zeros_like(positions)
        colors = np.zeros((n_sel * n_verts, 4), dtype=float)

        def _color_for_atom(idx_atom: int) -> np.ndarray:
            if per_atom_colors is not None and 0 <= idx_atom < per_atom_colors.shape[0]:
                col = np.asarray(per_atom_colors[idx_atom], dtype=float)
                if col.shape[0] == 3:
                    col = np.concatenate([col, np.array([base_color[3]])])
                return col
            return base_color

        for i, atom_idx in enumerate(indices):
            center = coords[atom_idx]
            cov_local = cov_arr[atom_idx]
            cov_local = 0.5 * (cov_local + cov_local.T)
            try:
                evals, evecs = np.linalg.eigh(cov_local)
            except np.linalg.LinAlgError:
                continue
            evals = np.clip(evals, 0.0, None)
            axes = np.sqrt(evals) * scale
            axes = np.clip(axes, min_axis, None)
            axes = np.clip(axes, None, max_axis)
            axes[axes <= 0.0] = min_axis

            transform = evecs @ np.diag(axes)
            verts_local = base_verts @ transform.T + center

            try:
                inv_t = np.linalg.pinv(transform).T
            except np.linalg.LinAlgError:
                inv_t = np.linalg.pinv(transform + np.eye(3) * 1e-6).T
            normals_local = base_normals @ inv_t
            norms = np.linalg.norm(normals_local, axis=1, keepdims=True)
            normals_local = normals_local / np.clip(norms, 1e-6, None)

            start = i * n_verts
            end = start + n_verts
            positions[start:end] = verts_local
            normals[start:end] = normals_local
            colors[start:end] = np.clip(_color_for_atom(atom_idx), 0.0, 1.0)

        if positions.size == 0:
            return None

        faces = np.repeat(base_faces[np.newaxis, :, :], n_sel, axis=0)
        offsets = (np.arange(n_sel, dtype=base_faces.dtype) * n_verts)[:, np.newaxis, np.newaxis]
        faces = (faces + offsets).reshape(-1, 3)

        geom = Geometry(
            kind="mesh",
            positions=positions,
            indices=faces,
            normals=normals,
            colors=colors,
        )
        render_mode = "transparent" if np.any(colors[:, 3] < 0.999) else "opaque"
        return [SceneObject(id="atom_gaussians", geometry=geom, render_mode=render_mode)]


    def set_labels(self, indices, texts, *, object_id: str | None = None) -> int:
        """Attach label text to atoms (PyMOL ``label``).

        Passing no indices clears every label, which is what
        ``cmd.label(sel, "")`` does.

        Parameters
        ----------
        indices : sequence of int
            Atom indices to label.
        texts : sequence of str
            Text per index; an empty string removes that atom's label.
        object_id : str, optional
            Object to label; defaults to the active one.

        Returns
        -------
        int
            Number of labels now attached to the object.
        """
        with self._activate_object(object_id):
            current = dict(self._labels or {})
            for index, text in zip(indices, texts):
                key = int(index)
                if text:
                    current[key] = str(text)
                else:
                    current.pop(key, None)
            self._labels = current
            self._update_view()
            return len(current)

    def clear_labels(self, *, object_id: str | None = None) -> None:
        """Remove every label from an object."""
        with self._activate_object(object_id):
            self._labels = {}
            self._update_view()

    def set_labels_visible(self, visible: bool) -> None:
        """Show or hide the label representation without discarding the text."""
        self._show_labels = bool(visible)
        self._update_view()

    def _update_labels(self) -> list[SceneObject]:
        """Text at the labelled atoms, drawn as an overlay.

        One SceneObject per label rather than one for all of them: the backends
        render ``kind="text"`` a label at a time anyway, and keeping them separate
        means a label can be removed without rebuilding the rest.
        """
        labels = self._labels or {}
        if not labels or not self._show_labels:
            return []
        if self._all_atom_coords is None:
            return []

        cfg = _DISPLAY_CONFIG.get("label", {})
        colour = np.asarray(
            cfg.get("color", [1.0, 1.0, 1.0, 1.0]), dtype=float
        ).reshape(1, 4)
        n_atoms = self._all_atom_coords.shape[0]

        out: list[SceneObject] = []
        for index, text in sorted(labels.items()):
            if not (0 <= int(index) < n_atoms):
                continue
            out.append(
                SceneObject(
                    id=f"label:{int(index)}",
                    geometry=Geometry(
                        kind="text",
                        positions=self._all_atom_coords[int(index)].reshape(1, 3),
                        colors=colour,
                        meta={"labels": [str(text)]},
                    ),
                    render_mode="overlay",
                )
            )
        return out

    def _update_lines(self, colors: np.ndarray | None) -> list[SceneObject]:
        """Draw PyMOL's ``lines``: one segment per bond, split at the midpoint.

        Each half takes its own atom's colour, which is how element identity is
        read off a wireframe. This is what PyMOL shows by default, and it is deliberately *not* the
        alpha-carbon trace chimol used to draw under the same name.
        """
        if not self._show_lines:
            return []
        if self._bond_pairs is None or self._all_atom_coords is None:
            return []

        sticks_cfg = _DISPLAY_CONFIG.get("sticks", {})
        bonds = np.asarray(self._bond_pairs, dtype=int)
        if self._sticks_mask is not None and bonds.size:
            n_atoms = self._all_atom_coords.shape[0]
            if len(self._sticks_mask) == n_atoms and self._sticks_mask.any():
                keep = (
                    self._sticks_mask[bonds[:, 0]] & self._sticks_mask[bonds[:, 1]]
                )
                bonds = bonds[keep]

        verts, cols = bond_line_segments(
            self._all_atom_coords, bonds, self._atom_rgba(colors)
        )
        if verts.shape[0] == 0:
            return []
        return [
            SceneObject(
                id="lines",
                geometry=Geometry(
                    kind="line",
                    positions=verts,
                    colors=cols,
                    meta={"width": float(sticks_cfg.get("width", 2.0))},
                ),
                render_mode="opaque",
            )
        ]

    def _update_nonbonded(self, colors: np.ndarray | None) -> list[SceneObject]:
        """PyMOL's ``nonbonded``: crosses on atoms that draw no bond line.

        Without it, waters and ions disappear from a wireframe view, which is why
        PyMOL enables it alongside ``lines``.
        """
        if not self._show_nonbonded or self._all_atom_coords is None:
            return []

        mask = unbonded_mask(self._all_atom_coords.shape[0], self._bond_pairs)
        if not mask.any():
            return []

        rgba = self._atom_rgba(colors)
        balls_cfg = _DISPLAY_CONFIG.get("balls", {})
        scale = float(getattr(self, "_scale_factor", 1.0) or 1.0)
        verts, cols = nonbonded_crosses(
            self._all_atom_coords[mask],
            None if rgba is None else rgba[mask],
            size=float(balls_cfg.get("nonbonded_size", 0.25)) * scale,
        )
        if verts.shape[0] == 0:
            return []
        return [
            SceneObject(
                id="nonbonded",
                geometry=Geometry(
                    kind="line", positions=verts, colors=cols,
                    meta={"width": 1.5},
                ),
                render_mode="opaque",
            )
        ]

    def _atom_rgba(self, colors_per_ca: np.ndarray | None) -> np.ndarray | None:
        """Per-atom RGBA, expanded from the per-residue colours when needed."""
        if self._all_atom_coords is None:
            return None
        n_atoms = self._all_atom_coords.shape[0]

        override = getattr(self, "_colors_per_atom_override", None)
        if override is not None:
            arr = np.asarray(override, dtype=float)
            if arr.ndim == 2 and arr.shape[0] == n_atoms:
                return arr

        atoms = self._atoms
        if (
            colors_per_ca is not None
            and atoms is not None
            and self._residue_ids is not None
            and "res_id" in (atoms.dtype.names or ())
        ):
            try:
                lookup = {
                    int(rid): colors_per_ca[i]
                    for i, rid in enumerate(np.asarray(self._residue_ids))
                    if i < len(colors_per_ca)
                }
                base = np.asarray(self._base_color_single, dtype=float)
                return np.array(
                    [lookup.get(int(r), base) for r in np.asarray(atoms["res_id"])],
                    dtype=float,
                )
            except Exception:
                pass

        # Element colours are the useful fallback for a wireframe: it is how you
        # read atom identity when there is no shading to go on.
        if atoms is not None and "element" in (atoms.dtype.names or ()):
            try:
                return _build_element_color_array(
                    np.asarray(atoms["element"]), n_atoms
                )
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # Bonds (PyMOL ``bond`` / ``unbond`` / ``get_bonds``)
    # ------------------------------------------------------------------
    @staticmethod
    def _bond_key(i: int, j: int) -> tuple[int, int]:
        """Canonical key for a bond: sorted, so i-j and j-i are one bond."""
        a, b = int(i), int(j)
        return (a, b) if a <= b else (b, a)

    def _apply_bond_edits(self, pairs: np.ndarray | None) -> np.ndarray | None:
        """Replay the manual bond edits over a freshly inferred bond list.

        Called wherever ``_infer_bonds`` result is stored, which is the only way
        a hand-made bond survives a coordinate change.

        Parameters
        ----------
        pairs : numpy.ndarray or None
            Inferred ``(N, 2)`` bond list.

        Returns
        -------
        numpy.ndarray or None
            The list with manual additions merged in and removals taken out.
        """
        edits = self._bond_edits or {}
        added = edits.get("added") or {}
        removed = edits.get("removed") or set()
        if not added and not removed:
            return pairs

        keys: list[tuple[int, int]] = []
        if pairs is not None:
            arr = np.asarray(pairs, dtype=int)
            if arr.ndim == 2 and arr.shape[1] >= 2:
                keys = [self._bond_key(a, b) for a, b in arr[:, :2]]
        live = [k for k in keys if k not in removed]
        seen = set(live)
        for key in added:
            if key not in seen and key not in removed:
                live.append(key)
                seen.add(key)
        if not live:
            return np.zeros((0, 2), dtype=int)
        return np.asarray(live, dtype=int)

    def bond_list(self) -> np.ndarray:
        """Current bonds as an ``(N, 2)`` array of atom indices."""
        pairs = self._bond_pairs
        if pairs is None:
            return np.zeros((0, 2), dtype=int)
        arr = np.asarray(pairs, dtype=int)
        if arr.ndim != 2 or arr.shape[1] < 2:
            return np.zeros((0, 2), dtype=int)
        return arr[:, :2]

    def bond_order(self, i: int, j: int) -> int:
        """Order of one bond. Inferred bonds are single unless said otherwise."""
        edits = self._bond_edits or {}
        return int((edits.get("added") or {}).get(self._bond_key(i, j), 1))

    def add_bond(self, i: int, j: int, order: int = 1) -> bool:
        """Bond two atoms. False when they are already bonded or i == j.

        Parameters
        ----------
        i, j : int
            Atom indices within the active object.
        order : int, optional
            Bond order; 1 unless given.
        """
        if int(i) == int(j):
            return False
        coords = self._all_atom_coords
        if coords is None:
            return False
        n_atoms = int(np.asarray(coords).shape[0])
        if not (0 <= int(i) < n_atoms and 0 <= int(j) < n_atoms):
            return False

        key = self._bond_key(i, j)
        existing = {self._bond_key(a, b) for a, b in self.bond_list()}
        edits = self._bond_edits or {"added": {}, "removed": set()}
        # An explicit `bond` outranks an earlier `unbond` of the same pair.
        edits.setdefault("removed", set()).discard(key)
        if key in existing:
            # Already bonded: record the order anyway, since `bond a, b, 2` on an
            # existing single bond is how its order is changed.
            edits.setdefault("added", {})[key] = int(order)
            self._bond_edits = edits
            return False
        edits.setdefault("added", {})[key] = int(order)
        self._bond_edits = edits
        self._bond_pairs = self._apply_bond_edits(self._bond_pairs)
        self._update_view()
        return True

    def remove_bonds(self, pairs: list[tuple[int, int]]) -> int:
        """Remove bonds between the given index pairs. Returns how many went.

        Pairs that are not bonded are skipped rather than reported: ``unbond``
        takes two *selections* and removes every bond between them, so most
        candidate pairs in a real call are legitimately not bonded.
        """
        if not pairs:
            return 0
        existing = {self._bond_key(a, b) for a, b in self.bond_list()}
        edits = self._bond_edits or {"added": {}, "removed": set()}
        removed = edits.setdefault("removed", set())
        added = edits.setdefault("added", {})
        gone = 0
        for i, j in pairs:
            key = self._bond_key(i, j)
            if key not in existing:
                continue
            removed.add(key)
            added.pop(key, None)
            gone += 1
        if gone:
            self._bond_edits = edits
            self._bond_pairs = self._apply_bond_edits(self._bond_pairs)
            self._update_view()
        return gone

    def _unbonded_atom_mask(self) -> np.ndarray | None:
        """Atoms that take part in no bond at all.

        These are what PyMOL calls nonbonded -- ordered waters, free ions -- and
        the only atoms its ``nonbonded_size`` shrinks. Derived from the inferred
        bond list so it agrees with the ``nonbonded`` selection keyword rather
        than being a second, drifting opinion about what counts as solvent.

        Returns
        -------
        numpy.ndarray or None
            Boolean mask over all atoms, or None when no bonds are known -- in
            which case no atom should be treated as nonbonded, since every atom
            would otherwise qualify.
        """
        pairs = self._bond_pairs
        coords = self._all_atom_coords
        if pairs is None or coords is None:
            return None
        pairs = np.asarray(pairs, dtype=int)
        if pairs.ndim != 2 or pairs.size == 0:
            return None
        n_atoms = int(np.asarray(coords).shape[0])
        bonded = np.zeros(n_atoms, dtype=bool)
        flat = pairs.reshape(-1)
        flat = flat[(flat >= 0) & (flat < n_atoms)]
        bonded[flat] = True
        return ~bonded

    def _ca_rgba(self, n_points: int) -> np.ndarray | None:
        """Per-residue RGBA projected down from the per-atom override.

        The mirror image of :meth:`_atom_rgba`, and it exists for the same
        reason: there are two colour arrays -- one per atom, one per residue --
        and a command that writes only one of them silently fails to colour
        whatever reads the other. ``spectrum`` writes per-atom colours, the
        cartoon and the trace read per-residue ones, so ``spectrum count,
        rainbow`` left the cartoon showing the load-time gradient. Nothing
        errored; the picture was simply the wrong colours.

        A residue takes its CA atom's colour where there is one -- that is the
        atom the cartoon spline is drawn through -- and the mean of its atoms
        otherwise, which is what a ligand or a nucleic acid residue gets.

        Parameters
        ----------
        n_points : int
            Number of residues, i.e. the length of the per-residue arrays.

        Returns
        -------
        numpy.ndarray or None
            ``(n_points, 4)`` colours, or None when there is no per-atom
            override to project or the arrays do not line up. A residue no
            overridden atom belongs to is NaN, i.e. it abstains -- the caller
            blends on the finite mask so that a partial override leaves the
            rest of the colouring alone.
        """
        override = getattr(self, "_colors_per_atom_override", None)
        if override is None:
            return None
        atoms = self._atoms
        res_ids = self._residue_ids
        if atoms is None or res_ids is None:
            return None
        names = atoms.dtype.names or ()
        if "res_id" not in names:
            return None

        ov = np.asarray(override, dtype=float)
        atom_res = np.asarray(atoms["res_id"])
        if ov.ndim != 2 or ov.shape[0] != atom_res.shape[0]:
            return None

        res_ids = np.asarray(res_ids)
        if res_ids.shape[0] != n_points:
            return None

        is_ca = (
            np.asarray([str(v).strip().upper() == "CA" for v in atoms["atom_name"]])
            if "atom_name" in names
            else np.zeros(atom_res.shape[0], dtype=bool)
        )

        out = np.empty((n_points, 4), dtype=float)
        # One pass over the atoms rather than one selection per residue: on a
        # ribosome the per-residue version is the whole frame budget.
        order = {int(rid): i for i, rid in enumerate(res_ids)}
        sums = np.zeros((n_points, 4), dtype=float)
        counts = np.zeros(n_points, dtype=int)
        ca_seen = np.zeros(n_points, dtype=bool)
        ca_cols = np.zeros((n_points, 4), dtype=float)
        for i_atom, rid in enumerate(atom_res):
            i_res = order.get(int(rid))
            if i_res is None:
                continue
            col = ov[i_atom]
            if not np.isfinite(col).all():
                continue
            sums[i_res] += col
            counts[i_res] += 1
            if is_ca[i_atom] and not ca_seen[i_res]:
                ca_seen[i_res] = True
                ca_cols[i_res] = col

        empty = counts == 0
        with np.errstate(invalid="ignore"):
            out[:] = sums / np.maximum(counts, 1)[:, None]
        out[ca_seen] = ca_cols[ca_seen]
        out[:, 3] = 1.0
        # A residue no overridden atom belongs to abstains -- it must not be
        # given the base colour here. The override is normally partial (``color
        # red, resi 4`` touches one residue), and the caller assigns this array
        # wholesale, so a fallback colour would flatten the colour mode and the
        # per-residue override for every residue the user did not name.
        out[empty] = np.nan
        return out

    def _update_sticks(self, sticks_cfg: dict, colors_per_ca: np.ndarray | None) -> list[SceneObject] | None:
        if not self._show_sticks:
            return None
        if self._bond_pairs is None or self._all_atom_coords is None:
            return None

        sticks_width = float(sticks_cfg.get("width", 2.0))
        sticks_max_bonds = int(sticks_cfg.get("max_bonds", 20000))

        bonds = np.asarray(self._bond_pairs, dtype=int)
        if bonds.ndim == 2 and bonds.shape[1] == 2 and bonds.size:
            n_atoms_all = self._all_atom_coords.shape[0]
            # Clamp indices to valid range just in case.
            mask_valid = (
                (bonds[:, 0] >= 0)
                & (bonds[:, 0] < n_atoms_all)
                & (bonds[:, 1] >= 0)
                & (bonds[:, 1] < n_atoms_all)
                & (bonds[:, 0] != bonds[:, 1])
            )
            bonds = bonds[mask_valid]

            if self._sticks_mask is not None and len(self._sticks_mask) == n_atoms_all:
                 mask_bonds = self._sticks_mask[bonds[:, 0]] & self._sticks_mask[bonds[:, 1]]
                 bonds = bonds[mask_bonds]

            if bonds.size:
                # Optional bond downsampling for performance.
                if sticks_max_bonds > 0 and bonds.shape[0] > sticks_max_bonds:
                    step = max(1, bonds.shape[0] // sticks_max_bonds)
                    bonds = bonds[::step]

                pts_all = np.asarray(self._all_atom_coords, dtype=float)

                # Build per-atom colors from residue colors and/or explicit overrides.
                atom_res = None
                if self._all_atom_res_ids is not None:
                    atom_res = np.asarray(self._all_atom_res_ids)
                atom_colors = np.tile(
                    np.asarray(self._base_color_single, dtype=float),
                    (pts_all.shape[0], 1),
                )

                if (
                    atom_res is not None
                    and self._residue_ids is not None
                    and colors_per_ca is not None
                    and len(colors_per_ca) == len(self._residue_ids)
                ):
                    color_map = {rid: colors_per_ca[i_res] for i_res, rid in enumerate(self._residue_ids)}
                    for i_atom, rid in enumerate(atom_res):
                        atom_colors[i_atom, :] = color_map.get(
                            rid, self._base_color_single
                        )

                if (
                    atom_res is not None
                    and getattr(self, "_colors_per_atom_override", None) is not None
                    and len(self._colors_per_atom_override) == atom_res.shape[0]
                ):
                    ov = np.asarray(self._colors_per_atom_override, dtype=float)
                    for i_atom in range(atom_res.shape[0]):
                        col_ov = ov[i_atom]
                        if np.isfinite(col_ov).all():
                            atom_colors[i_atom, :] = col_ov

                # Use cylinder mesh for sticks (replaces GL_LINES)
                sticks_radius = float(sticks_cfg.get("radius", 0.15)) * float(self._scale_factor)
                sticks_segments = int(sticks_cfg.get("segments_circle", 12))
                mesh = _build_stick_mesh(
                    bonds, pts_all, atom_colors,
                    radius=sticks_radius, segments_circle=sticks_segments,
                )
                if mesh is not None:
                    verts, norms, faces, cols = mesh
                    geom = Geometry(
                        kind="mesh", positions=verts, indices=faces,
                        normals=norms, colors=cols,
                    )
                    return [SceneObject(id="sticks", geometry=geom, render_mode="opaque")]

        return None

    def _update_restraints(self, state: _MolViewObjectState) -> list[SceneObject] | None:
        """Build geometry for RMF restraint pseudobonds."""
        if not state.restraints or state.all_atom_coords is None:
            return None

        pts = state.all_atom_coords
        n_restraints = len(state.restraints)
        seg_pos = np.empty((n_restraints * 2, 3), dtype=np.float32)

        for i, r in enumerate(state.restraints):
            idx1, idx2 = r["indices"]
            if idx1 < pts.shape[0] and idx2 < pts.shape[0]:
                seg_pos[i*2] = pts[idx1]
                seg_pos[i*2 + 1] = pts[idx2]
            else:
                seg_pos[i*2] = [0, 0, 0]
                seg_pos[i*2 + 1] = [0, 0, 0]

        geom = Geometry(kind="line", positions=seg_pos)
        # Warm orange/yellow for restraints
        geom.colors = np.tile([1.0, 0.6, 0.2, 1.0], (n_restraints * 2, 1)).astype(np.float32)

        return [SceneObject(id="restraints", geometry=geom, render_mode="opaque")]

    def _update_metaballs(
        self,
        coords: np.ndarray,
        cfg: dict,
        colors_per_ca: np.ndarray | None,
    ) -> list[SceneObject] | None:
        if not getattr(self, "_metaballs_visible", False):
            return None

        iso_value = float(cfg.get("iso_value", 0.15))
        grid_spacing = float(cfg.get("grid_spacing", 0.6))
        padding = float(cfg.get("padding", 4.0))
        max_dim = int(cfg.get("max_dim", 128))
        alpha = float(cfg.get("alpha", 0.6))

        ao_strength = float(cfg.get("ao_strength", 0.5))
        ao_radius = float(cfg.get("ao_radius", 4.5))

        surface_only = bool(cfg.get("surface_only", True))
        surface_radius = float(cfg.get("surface_radius", 5.0))
        surface_max_neighbors = int(cfg.get("surface_max_neighbors", 20))

        lighting_cfg = _DISPLAY_CONFIG.get("lighting", {})
        material = {
            "shininess": float(cfg.get("shininess", lighting_cfg.get("shininess", 38.0))),
            "specular_strength": float(cfg.get("specular_strength", lighting_cfg.get("specular_strength", 0.18))),
            "rim_strength": float(cfg.get("rim_strength", lighting_cfg.get("rim_strength", 0.18))),
            "rim_power": float(cfg.get("rim_power", lighting_cfg.get("rim_power", 2.4))),
        }

        if self._all_atom_coords is not None:
            pts_all = np.asarray(self._all_atom_coords, dtype=float)
        else:
            pts_all = coords.copy()

        if pts_all.size == 0:
            return None

        n_all = pts_all.shape[0]

        # Larger sigmas fuse neighbouring atoms into rounder blobs; the factor is
        # config-tunable so the "blobbiness" can be dialled without touching the
        # per-atom radii (which the balls/surface representations also use).
        sigma_factor = float(cfg.get("sigma_factor", 1.5))
        if self._all_atom_radii is not None and self._all_atom_radii.shape[0] == n_all:
            sigmas_all = np.asarray(self._all_atom_radii, dtype=float) * sigma_factor
        else:
            sigmas_all = np.ones(n_all, dtype=float) * sigma_factor

        if surface_only and n_all > surface_max_neighbors:
            surf_mask = _get_surface_atom_mask(
                pts_all, radius=surface_radius, max_neighbors=surface_max_neighbors
            )
            if surf_mask.any():
                pts_surface = pts_all[surf_mask]
                sigmas = sigmas_all[surf_mask]
            else:
                pts_surface = pts_all
                sigmas = sigmas_all
        else:
            pts_surface = pts_all
            sigmas = sigmas_all

        n_pts = pts_surface.shape[0]

        field_function = cfg.get("field_function", "wyvill")
        mesh_data = _generate_surface_mesh_from_density(
            pts_surface,
            sigmas,
            grid_spacing=grid_spacing,
            padding=padding,
            iso_value=iso_value,
            max_dim=max_dim,
            field_function=field_function,
        )

        if mesh_data is None:
            return None

        verts, faces, norms = mesh_data

        base_color = np.asarray(self._base_color_single, dtype=float)
        if base_color.shape[0] != 4:
            base_color = np.array([1.0, 1.0, 1.0, 1.0], dtype=float)

        atom_colors = np.tile(base_color, (n_pts, 1))

        if surface_only and n_all > surface_max_neighbors:
            surf_mask_full = _get_surface_atom_mask(
                pts_all, radius=surface_radius, max_neighbors=surface_max_neighbors
            )
            surf_indices = np.where(surf_mask_full)[0]
        else:
            surf_indices = np.arange(n_all)

        if (
            self._all_atom_res_ids is not None
            and self._residue_ids is not None
            and colors_per_ca is not None
            and len(colors_per_ca) == len(self._residue_ids)
        ):
            res_id_to_color = {}
            for i_res, rid in enumerate(self._residue_ids):
                res_id_to_color[rid] = colors_per_ca[i_res]

            for i_local, i_global in enumerate(surf_indices):
                if i_global < len(self._all_atom_res_ids):
                    rid = self._all_atom_res_ids[i_global]
                    if rid in res_id_to_color:
                        atom_colors[i_local] = res_id_to_color[rid]

        if getattr(self, "_colors_per_atom_override", None) is not None:
            ov = np.asarray(self._colors_per_atom_override, dtype=float)
            for i_local, i_global in enumerate(surf_indices):
                if i_global < ov.shape[0] and np.isfinite(ov[i_global]).all():
                    atom_colors[i_local] = ov[i_global]

        try:
            max_sigma = float(np.max(sigmas))
            cutoff = max_sigma * 2.5

            # Gaussian-weighted colour + gradient normal per vertex via a numba
            # cell list (no scipy). ``col_sum``/``wsum`` give the weighted colour;
            # ``grad_sum`` the density gradient; ``nearest`` the closest atom for
            # vertices with no atom inside the cutoff.
            col_sum, wsum, grad_sum, nearest = shade_from_atoms(
                verts, pts_surface, atom_colors, sigmas, cutoff
            )
            w_safe = np.where(wsum > 0.0, wsum, 1.0)
            mesh_colors = col_sum / w_safe[:, np.newaxis]
            no_neighbors = wsum <= 0.0
            if no_neighbors.any():
                mesh_colors[no_neighbors] = atom_colors[nearest[no_neighbors]]

            mag = np.linalg.norm(grad_sum, axis=1, keepdims=True)
            good = mag[:, 0] > 1e-6
            new_norms = norms.copy()
            new_norms[good] = -grad_sum[good] / mag[good]
            norms = new_norms

            if ao_strength > 0:
                occ = _estimate_ambient_occlusion(verts, radius=ao_radius, max_neighbors=32)
                if occ is not None:
                    darken = 1.0 - (occ * ao_strength)
                    mesh_colors[:, :3] *= darken[:, np.newaxis]

        except Exception:
            mesh_colors = np.tile(base_color, (verts.shape[0], 1))

        render_mode = "opaque"
        if alpha < 1.0:
            mesh_colors[:, 3] = alpha
            render_mode = "transparent"

        geom = Geometry(
            kind="mesh",
            positions=verts,
            indices=faces,
            normals=norms,
            colors=mesh_colors,
        )
        return [SceneObject(
            id="metaballs",
            geometry=geom,
            render_mode=render_mode,
            material=material
        )]

    def _update_surface(
        self,
        coords: np.ndarray,
        surface_cfg: dict,
        colors_per_ca: np.ndarray | None
    ) -> list[SceneObject] | None:
        if not self._surface_visible:
            return None

        surface_alpha = float(surface_cfg.get("alpha", 0.85))
        surface_ao_radius = float(surface_cfg.get("ao_radius", 4.5))
        surface_ao_strength = float(surface_cfg.get("ao_strength", 0.6))
        surface_base_color = np.asarray(
            surface_cfg.get("base_color", self._base_color_single), dtype=float
        )
        if surface_base_color.shape[0] != 4:
            surface_base_color = np.asarray(self._base_color_single, dtype=float)

        if self._all_atom_coords is not None:
            pts_surface = np.asarray(self._all_atom_coords, dtype=float)
        elif coords is not None:
            pts_surface = np.asarray(coords, dtype=float)
        else:
            return None

        if pts_surface.size == 0:
            return None

        n_pts = pts_surface.shape[0]

        # --- Try mesh surface via Gaussian density + marching cubes ---
        grid_spacing = float(surface_cfg.get("grid_spacing", 0.8))
        iso_value = float(surface_cfg.get("iso_value", 0.5))
        padding = float(surface_cfg.get("padding", 3.0))
        max_dim = int(surface_cfg.get("max_dim", 96))
        mesh_sigma_factor = float(surface_cfg.get("mesh_sigma_factor", 1.0))
        mesh_sigma_default = float(surface_cfg.get("mesh_sigma_default", 1.8))

        method = str(surface_cfg.get("method", "gaussian")).lower()
        probe_radius = float(surface_cfg.get("probe_radius", 1.4))

        if method in ("sas", "ses"):
            if self._all_atom_radii is not None and self._all_atom_radii.shape[0] == n_pts:
                atom_radii = np.asarray(self._all_atom_radii, dtype=float)
            else:
                atom_radii = np.full(n_pts, mesh_sigma_default, dtype=float)

            mesh_data = _generate_surface_mesh_edt(
                pts_surface,
                atom_radii,
                method=method,
                probe_radius=probe_radius,
                grid_spacing=grid_spacing,
                padding=padding,
                max_dim=max_dim,
            )
            mesh_sigmas = atom_radii
        else:
            if self._all_atom_radii is not None and self._all_atom_radii.shape[0] == n_pts:
                sigmas = np.asarray(self._all_atom_radii, dtype=float) * mesh_sigma_factor
            else:
                sigmas = np.full(n_pts, mesh_sigma_default, dtype=float)

            mesh_data = _generate_surface_mesh_from_gaussians(
                pts_surface,
                sigmas,
                grid_spacing=grid_spacing,
                padding=padding,
                iso_value=iso_value,
                max_dim=max_dim,
            )
            mesh_sigmas = sigmas

        if mesh_data is not None:
            verts, faces, norms = mesh_data
            return self._build_surface_mesh_scene(
                verts, faces, norms, pts_surface, mesh_sigmas,
                surface_cfg, colors_per_ca, surface_base_color, surface_alpha,
            )

        # --- Fallback: point-cloud surface ---
        surface_size_scale = float(surface_cfg.get("size_scale", 0.03))
        surface_min_size = float(surface_cfg.get("min_size", 2.5))
        surface_ao_max = int(surface_cfg.get("max_neighbors", 24))
        surface_max_points = int(surface_cfg.get("max_points", 10000))
        surface_color_mode = str(surface_cfg.get("color_mode", "ao_gray")).lower()

        colors_surface = self._build_surface_atom_colors(
            pts_surface, surface_cfg, colors_per_ca, surface_base_color,
        )
        if colors_surface is None:
            colors_surface = np.tile(surface_base_color, (pts_surface.shape[0], 1))

        max_pts = max(1, surface_max_points)
        if pts_surface.shape[0] > max_pts:
            step = max(1, pts_surface.shape[0] // max_pts)
            pts_surface = pts_surface[::step]
            colors_surface = colors_surface[::step]

        colors_surface = colors_surface.copy()

        try:
            occ_surf = _estimate_ambient_occlusion(
                pts_surface,
                radius=surface_ao_radius,
                max_neighbors=surface_ao_max,
            )
        except Exception:
            occ_surf = None
        if (
            occ_surf is not None
            and np.asarray(occ_surf).shape[0] == pts_surface.shape[0]
        ):
            occ_s = np.asarray(occ_surf, dtype=float)
            shade_surf = (1.0 - surface_ao_strength) + (
                surface_ao_strength * (1.0 - occ_s)
            )
            colors_surface[:, :3] *= shade_surf.reshape(-1, 1)

        colors_surface = np.clip(colors_surface, 0.0, 1.0)
        colors_surface[:, 3] *= surface_alpha

        size_world = max(self._radius * surface_size_scale, surface_min_size)
        meta = {"size": float(size_world), "glyph": "sphere"}

        geom = Geometry(
            kind="points",
            positions=pts_surface,
            colors=colors_surface,
            meta=meta,
        )
        return [SceneObject(id="surface", geometry=geom, render_mode="transparent")]

    def _build_surface_atom_colors(
        self,
        pts_surface: np.ndarray,
        surface_cfg: dict,
        colors_per_ca: np.ndarray | None,
        surface_base_color: np.ndarray,
    ) -> np.ndarray | None:
        """Build per-atom/point colors for the surface representation."""
        surface_color_mode = str(surface_cfg.get("color_mode", "ao_gray")).lower()
        n_pts = pts_surface.shape[0]

        if (
            surface_color_mode == "by_residue"
            and self._all_atom_res_ids is not None
            and self._residue_ids is not None
            and colors_per_ca is not None
            and len(colors_per_ca) == len(self._residue_ids)
        ):
            color_map = {rid: colors_per_ca[i_res] for i_res, rid in enumerate(self._residue_ids)}
            colors = np.zeros((n_pts, 4), dtype=float)
            for i_atom, rid in enumerate(self._all_atom_res_ids):
                colors[i_atom, :] = color_map.get(rid, self._base_color_single)
        else:
            colors = np.tile(surface_base_color, (n_pts, 1))

        if (
            getattr(self, "_colors_per_atom_override", None) is not None
            and self._all_atom_res_ids is not None
            and len(self._colors_per_atom_override) == self._all_atom_res_ids.shape[0]
        ):
            ov = np.asarray(self._colors_per_atom_override, dtype=float)
            for i_atom in range(min(colors.shape[0], ov.shape[0])):
                col_ov = ov[i_atom]
                if np.isfinite(col_ov).all():
                    colors[i_atom, :] = col_ov

        return colors

    def _build_surface_mesh_scene(
        self,
        verts: np.ndarray,
        faces: np.ndarray,
        norms: np.ndarray,
        pts_surface: np.ndarray,
        sigmas: np.ndarray,
        surface_cfg: dict,
        colors_per_ca: np.ndarray | None,
        surface_base_color: np.ndarray,
        surface_alpha: float,
    ) -> list[SceneObject] | None:
        """Build a colored mesh SceneObject for the Gaussian surface."""
        surface_ao_radius = float(surface_cfg.get("ao_radius", 4.5))
        surface_ao_strength = float(surface_cfg.get("ao_strength", 0.6))

        base_color = np.asarray(self._base_color_single, dtype=float)
        if base_color.shape[0] != 4:
            base_color = np.array([1.0, 1.0, 1.0, 1.0], dtype=float)

        n_pts = pts_surface.shape[0]
        mesh_colors = np.zeros((verts.shape[0], 4), dtype=float)

        atom_colors = self._build_surface_atom_colors(
            pts_surface, surface_cfg, colors_per_ca, surface_base_color,
        )
        if atom_colors is None:
            atom_colors = np.tile(base_color, (n_pts, 1))

        try:
            max_sigma = float(np.max(sigmas))
            cutoff = max_sigma * 2.5

            # Gaussian-weighted colour + analytical normal per vertex via a numba
            # cell list (no scipy); atoms beyond the cutoff contribute ~0.
            col_sum, wsum, grad_sum, nearest = shade_from_atoms(
                verts, pts_surface, atom_colors, sigmas, cutoff
            )
            w_safe = np.where(wsum > 0.0, wsum, 1.0)
            mesh_colors = col_sum / w_safe[:, np.newaxis]
            no_nb = wsum <= 0.0
            if no_nb.any():
                mesh_colors[no_nb] = atom_colors[nearest[no_nb]]

            # Analytical normals from the Gaussian gradient (density methods only).
            method = str(surface_cfg.get("method", "gaussian")).lower()
            if method not in ("sas", "ses"):
                mag = np.linalg.norm(grad_sum, axis=1, keepdims=True)
                good = mag[:, 0] > 1e-6
                new_norms = norms.copy()
                new_norms[good] = grad_sum[good] / mag[good]
                norms = new_norms

            if surface_ao_strength > 0:
                occ = _estimate_ambient_occlusion(verts, radius=surface_ao_radius, max_neighbors=32)
                if occ is not None:
                    darken = 1.0 - (occ * surface_ao_strength)
                    mesh_colors[:, :3] *= darken[:, np.newaxis]

        except Exception:
            mesh_colors[:, :] = base_color

        render_mode = "opaque"
        if surface_alpha < 1.0:
            mesh_colors[:, 3] = surface_alpha
            render_mode = "transparent"

        geom = Geometry(
            kind="mesh",
            positions=verts,
            indices=faces,
            normals=norms,
            colors=mesh_colors,
        )
        return [SceneObject(id="surface", geometry=geom, render_mode=render_mode)]

    def _update_dots(
        self,
        coords: np.ndarray,
        colors_per_ca: np.ndarray | None,
    ) -> list[SceneObject] | None:
        if not self._show_dots:
            return None

        dots_cfg = _DISPLAY_CONFIG.get("dots", {})
        try:
            max_points = int(dots_cfg.get("max_points", 250_000))
        except Exception:
            max_points = 250_000
        try:
            size_px = float(dots_cfg.get("size_px", 8.0))
        except Exception:
            size_px = 8.0
        try:
            alpha = float(dots_cfg.get("alpha", 1.0))
        except Exception:
            alpha = 1.0
        try:
            px_mode = bool(dots_cfg.get("px_mode", True))
        except Exception:
            px_mode = True
        try:
            size_scale = float(dots_cfg.get("size_scale", 0.04))
        except Exception:
            size_scale = 0.04
        try:
            min_size = float(dots_cfg.get("min_size", 3.0))
        except Exception:
            min_size = 3.0

        positions: np.ndarray | None
        colors_local: np.ndarray | None

        if self._all_atom_coords is not None and self._all_atom_coords.size:
            positions = np.asarray(self._all_atom_coords, dtype=float)
            base_col = np.asarray(self._base_color_single, dtype=float)
            colors_local = np.tile(base_col, (positions.shape[0], 1))

            # Per-atom residue colouring needs a per-atom res-id array, which
            # only the structured loader supplies. The raw-coordinate fallback
            # has none (its res ids are per-CA), so it keeps the base colour
            # rather than iterating a 0-d ``asarray(None)``.
            atom_res = (
                np.asarray(self._all_atom_res_ids)
                if self._all_atom_res_ids is not None
                else None
            )

            if (
                atom_res is not None
                and self._residue_ids is not None
                and colors_per_ca is not None
                and len(colors_per_ca) == len(self._residue_ids)
            ):
                color_map = {rid: colors_per_ca[i_res] for i_res, rid in enumerate(self._residue_ids)}
                for i_atom, rid in enumerate(atom_res):
                    colors_local[i_atom, :] = color_map.get(rid, self._base_color_single)

            if (
                atom_res is not None
                and getattr(self, "_colors_per_atom_override", None) is not None
                and len(self._colors_per_atom_override) == atom_res.shape[0]
            ):
                ov = np.asarray(self._colors_per_atom_override, dtype=float)
                for i_atom in range(atom_res.shape[0]):
                    col_ov = ov[i_atom]
                    if np.isfinite(col_ov).all():
                        colors_local[i_atom, :] = col_ov
        else:
            positions = np.asarray(coords, dtype=float) if coords is not None else None
            colors_local = None if colors_per_ca is None else np.asarray(colors_per_ca, dtype=float)

        if positions is None or positions.size == 0:
            return None

        if max_points > 0 and positions.shape[0] > max_points:
            step = max(1, positions.shape[0] // max_points)
            positions = positions[::step]
            if colors_local is not None and colors_local.shape[0] >= positions.shape[0]:
                colors_local = colors_local[::step]

        if colors_local is None:
            base = np.asarray(dots_cfg.get("base_color", self._base_color_single), dtype=float)
            if base.shape[0] != 4:
                base = np.asarray(self._base_color_single, dtype=float)
            colors_local = np.tile(base, (positions.shape[0], 1))
        else:
            colors_local = np.asarray(colors_local, dtype=float)

        if colors_local.shape[0] != positions.shape[0]:
            colors_local = np.resize(colors_local, (positions.shape[0], colors_local.shape[1]))

        colors_local = colors_local.copy()
        colors_local[:, 3] = np.clip(colors_local[:, 3] * alpha, 0.0, 1.0)

        if px_mode:
            size_value = size_px
            meta = {"size": size_value, "px_mode": True, "glyph": "sphere"}
        else:
            size_world = max(self._radius * size_scale, min_size)
            size_world = max(size_world, 0.5)
            meta = {"size": size_world, "glyph": "sphere"}

        geom = Geometry(
            kind="points",
            positions=positions,
            colors=colors_local,
            meta=meta,
        )
        return [SceneObject(id="dots", geometry=geom, render_mode="opaque")]

    def _update_custom_overlays(self, surface_cfg: dict) -> list[SceneObject] | None:
        overlays = getattr(self, "_point_overlays", None)
        if not overlays:
            return None

        surface_size_scale = float(surface_cfg.get("size_scale", 0.03))
        surface_min_size = float(surface_cfg.get("min_size", 2.5))

        scene_objects = []
        for key, overlay in list(overlays.items()):
            try:
                pts_ov = np.asarray(overlay.get("coords"), dtype=float)
            except Exception:
                continue
            if pts_ov.ndim != 2 or pts_ov.shape[0] == 0 or pts_ov.shape[1] != 3:
                continue

            if overlay.get("overlay_kind") == "surface":
                surface_objects = self._build_surface_overlay_scene(key, overlay, pts_ov)
                if surface_objects:
                    scene_objects += surface_objects
                    continue

            try:
                col = overlay.get("color", None)
                if col is None:
                    base_col = np.asarray(self._base_color_single, dtype=float)
                    colors_ov = np.tile(base_col, (pts_ov.shape[0], 1))
                else:
                    arr_col = np.asarray(col, dtype=float)
                    if arr_col.ndim == 1 and arr_col.shape[0] == 4:
                        colors_ov = np.tile(arr_col, (pts_ov.shape[0], 1))
                    elif (
                        arr_col.ndim == 2
                        and arr_col.shape[1] == 4
                        and arr_col.shape[0] == pts_ov.shape[0]
                    ):
                        colors_ov = arr_col
                    else:
                        base_col = np.asarray(self._base_color_single, dtype=float)
                        colors_ov = np.tile(base_col, (pts_ov.shape[0], 1))
            except Exception:
                base_col = np.asarray(self._base_color_single, dtype=float)
                colors_ov = np.tile(base_col, (pts_ov.shape[0], 1))

            try:
                size_scale_ov = float(overlay.get("size_scale", surface_size_scale))
            except Exception:
                size_scale_ov = surface_size_scale
            try:
                min_size_ov = float(overlay.get("min_size", surface_min_size))
            except Exception:
                min_size_ov = surface_min_size
            try:
                alpha_ov = float(overlay.get("alpha", 1.0))
            except Exception:
                alpha_ov = 1.0
            try:
                px_mode_ov = bool(overlay.get("px_mode", False))
            except Exception:
                px_mode_ov = False

            size_ov = max(self._radius * size_scale_ov, min_size_ov)
            colors_ov = np.asarray(colors_ov, dtype=float).copy()
            if colors_ov.shape[1] >= 4:
                colors_ov[:, 3] *= alpha_ov

            geom = Geometry(
                kind="points",
                positions=pts_ov,
                colors=colors_ov,
                meta={"size": size_ov, "glyph": overlay.get("glyph", "sphere")},
            )
            scene_objects.append(SceneObject(id=f"overlay:{key}", geometry=geom, render_mode="transparent"))

            if overlay.get("label"):
                label_geom = Geometry(
                    kind="text",
                    positions=pts_ov[0].reshape(1, 3),
                    colors=colors_ov[0].reshape(1, 4),
                    meta={"labels": [overlay["label"]]},
                )
                scene_objects.append(SceneObject(id=f"overlay_label:{key}", geometry=label_geom, render_mode="overlay"))

        return scene_objects

    def _build_surface_overlay_scene(
        self,
        key: str,
        overlay: dict,
        points: np.ndarray,
    ) -> list[SceneObject] | None:
        """Build mesh or point fallback objects for a surface overlay.

        Parameters
        ----------
        key : str
            Overlay identifier.
        overlay : dict
            Overlay style and meshing parameters.
        points : numpy.ndarray
            Surface point cloud with shape ``(N, 3)``.

        Returns
        -------
        list of SceneObject or None
            Scene objects representing the surface overlay.
        """
        try:
            grid_spacing = float(overlay.get("grid_spacing", 1.0))
        except Exception:
            grid_spacing = 1.0
        try:
            padding = float(overlay.get("padding", 1.5))
        except Exception:
            padding = 1.5
        try:
            smoothing_sigma = float(overlay.get("smoothing_sigma", 0.75))
        except Exception:
            smoothing_sigma = 0.75
        try:
            dilation_iterations = int(overlay.get("dilation_iterations", 1))
        except Exception:
            dilation_iterations = 1
        try:
            max_dim = int(overlay.get("max_dim", 96))
        except Exception:
            max_dim = 96
        try:
            alpha = float(overlay.get("alpha", 1.0))
        except Exception:
            alpha = 1.0

        mesh_data = _generate_surface_mesh_from_points(
            points,
            grid_spacing=grid_spacing,
            padding=padding,
            smoothing_sigma=smoothing_sigma,
            dilation_iterations=dilation_iterations,
            max_dim=max_dim,
        )

        color = overlay.get("color", (0.0, 1.0, 0.0, 0.62))
        try:
            base_color = np.asarray(color, dtype=float).reshape(-1)
            if base_color.shape[0] < 4:
                base_color = np.array(
                    [base_color[0], base_color[1], base_color[2], 1.0],
                    dtype=float,
                )
            else:
                base_color = base_color[:4]
        except Exception:
            base_color = np.array([0.0, 1.0, 0.0, 0.62], dtype=float)
        base_color = np.clip(base_color, 0.0, 1.0)
        base_color[3] = np.clip(base_color[3] * alpha, 0.0, 1.0)

        if mesh_data is None:
            try:
                size_scale = float(overlay.get("size_scale", 0.025))
            except Exception:
                size_scale = 0.025
            try:
                min_size = float(overlay.get("min_size", 2.0))
            except Exception:
                min_size = 2.0
            size = max(self._radius * size_scale, min_size)
            colors = np.tile(base_color, (points.shape[0], 1))
            geom = Geometry(
                kind="points",
                positions=points,
                colors=colors,
                meta={"size": size, "glyph": "sphere"},
            )
            return [
                SceneObject(
                    id=f"overlay_surface_points:{key}",
                    geometry=geom,
                    render_mode="transparent",
                )
            ]

        verts, faces, norms = mesh_data
        colors = np.tile(base_color, (verts.shape[0], 1))
        geom = Geometry(
            kind="mesh",
            positions=verts,
            indices=faces,
            normals=norms,
            colors=colors,
        )
        return [
            SceneObject(
                id=f"overlay_surface:{key}",
                geometry=geom,
                render_mode="transparent",
            )
        ]

    def _update_measurements(self) -> list[SceneObject]:
        measurements = getattr(self, "_measurements", None)
        if not measurements:
            return []

        scene_objects = []
        for mid, mdata in measurements.items():
            kind = mdata.get("kind", "distance")
            coords = np.asarray(mdata.get("positions", []), dtype=float)
            if coords.size == 0: continue

            if mdata.get("transform_to_scene", True):
                coords = self._transform_world_coords_to_scene(coords)

            color = np.asarray(mdata.get("color", [1.0, 1.0, 1.0, 1.0]), dtype=float)
            label = str(mdata.get("label", ""))

            if kind == "distance" and coords.shape[0] >= 2:
                 # Line between two points
                 line_geom = Geometry(kind="line", positions=coords[:2], colors=np.tile(color, (2, 1)))
                 scene_objects.append(SceneObject(id=f"meas_line_{mid}", geometry=line_geom, render_mode="overlay"))

                 # Label at midpoint
                 midpoint = np.mean(coords[:2], axis=0)
                 label_geom = Geometry(kind="text", positions=midpoint.reshape(1, 3), colors=color.reshape(1, 4), meta={"labels": [label]})
                 scene_objects.append(SceneObject(id=f"meas_text_{mid}", geometry=label_geom, render_mode="overlay"))

            elif kind == "angle" and coords.shape[0] >= 3:
                 # Lines 0-1, 1-2
                 line_coords = np.array([coords[0], coords[1], coords[1], coords[2]])
                 line_geom = Geometry(kind="line", positions=line_coords, colors=np.tile(color, (4, 1)))
                 scene_objects.append(SceneObject(id=f"meas_line_{mid}", geometry=line_geom, render_mode="overlay"))

                 # Label at center point (1)
                 label_geom = Geometry(kind="text", positions=coords[1].reshape(1, 3), colors=color.reshape(1, 4), meta={"labels": [label]})
                 scene_objects.append(SceneObject(id=f"meas_text_{mid}", geometry=label_geom, render_mode="overlay"))

            elif kind == "dihedral" and coords.shape[0] >= 4:
                 # Lines 0-1, 1-2, 2-3
                 line_coords = np.array([coords[0], coords[1], coords[1], coords[2], coords[2], coords[3]])
                 line_geom = Geometry(kind="line", positions=line_coords, colors=np.tile(color, (6, 1)))
                 scene_objects.append(SceneObject(id=f"meas_line_{mid}", geometry=line_geom, render_mode="overlay"))

                 # Label at midpoint of central bond (1-2)
                 midpoint = np.mean(coords[1:3], axis=0)
                 label_geom = Geometry(kind="text", positions=midpoint.reshape(1, 3), colors=color.reshape(1, 4), meta={"labels": [label]})
                 scene_objects.append(SceneObject(id=f"meas_text_{mid}", geometry=label_geom, render_mode="overlay"))

        return scene_objects

    def _update_selection_highlight(self, coords: np.ndarray) -> list[SceneObject] | None:
        sel = getattr(self, "_selected_residues", None)
        if not sel or self._coords is None:
            return None

        try:
            idx_sel = np.asarray(list(sel), dtype=int)
        except Exception:
            idx_sel = np.zeros(0, dtype=int)
        n = self._coords.shape[0]
        if idx_sel.size and n > 0:
            idx_sel = idx_sel[(idx_sel >= 0) & (idx_sel < n)]
        if idx_sel.size:
            try:
                centers = coords[idx_sel]
            except Exception:
                centers = None
            if centers is not None and centers.size:
                try:
                    sel_cfg = _DISPLAY_CONFIG.get("selection", {})
                except Exception:
                    sel_cfg = {}
                try:
                    col = np.asarray(
                        sel_cfg.get("color", [1.0, 1.0, 0.0, 1.0]),
                        dtype=float,
                    )
                except Exception:
                    col = np.array([1.0, 1.0, 0.0, 1.0], dtype=float)
                if col.shape[0] != 4:
                    col = np.array([1.0, 1.0, 0.0, 1.0], dtype=float)
                size_scale = float(sel_cfg.get("size_scale", 0.08))
                min_size = float(sel_cfg.get("min_size", 6.0))
                px_mode = bool(sel_cfg.get("px_mode", False))
                size = max(self._radius * size_scale, min_size)
                color_arr = np.tile(col, (centers.shape[0], 1))

                if px_mode:
                    geom = Geometry(
                        kind="points",
                        positions=centers,
                        colors=color_arr,
                        meta={
                            "glyph": "sphere",
                            "radius": size * 0.1,
                            "size": size,
                            "px_mode": True,
                        },
                    )
                    scene_objects = [SceneObject(id="selection", geometry=geom, render_mode="overlay")]
                else:
                    template = _build_sphere_mesh(radius=1.0)
                    verts = template.get("vertices") if template else None
                    norms = template.get("normals") if template else None
                    faces = template.get("faces") if template else None
                    if (
                        verts is not None
                        and norms is not None
                        and faces is not None
                        and verts.size
                        and faces.size
                    ):
                        n_sel = centers.shape[0]
                        n_verts = verts.shape[0]
                        radius_ws = max(size * 0.5, 1e-3)
                        verts_scaled = verts[np.newaxis, :, :] * radius_ws
                        verts_translated = verts_scaled + centers[:, np.newaxis, :]
                        positions = verts_translated.reshape(-1, 3)

                        faces_rep = np.repeat(faces[np.newaxis, :, :], n_sel, axis=0)
                        idx_offsets = (
                            np.arange(n_sel, dtype=faces.dtype) * n_verts
                        )[:, np.newaxis, np.newaxis]
                        faces_rep = (faces_rep + idx_offsets).reshape(-1, 3)

                        normals = np.repeat(
                            norms[np.newaxis, :, :], n_sel, axis=0
                        ).reshape(-1, 3)
                        colors = np.repeat(
                            color_arr[:, np.newaxis, :], n_verts, axis=1
                        ).reshape(-1, 4)

                        geom = Geometry(
                            kind="mesh",
                            positions=positions,
                            indices=faces_rep,
                            normals=normals,
                            colors=colors,
                        )
                        scene_objects = [
                            SceneObject(id="selection", geometry=geom, render_mode="overlay")
                        ]

                return scene_objects

        return None

    def _update_view(self, fit_camera: bool = True) -> None:
        if self._renderer is None:
            return

        visible_entries = [
            entry
            for entry in self._objects.values()
            if entry.visible
            and entry.state.coords is not None
            and getattr(entry.state.coords, "size", 0) > 0
        ]

        if not visible_entries:
            self._clear_items()
            self._scene = None
            return

        self._clear_items()

        scene_objects: list[SceneObject] = []
        centers: list[np.ndarray] = []
        radii: list[float] = []

        for entry in visible_entries:
            with self._activate_object(entry.object_id):
                objects = self._build_scene_for_current_object(object_prefix=entry.object_id)
                if objects:
                    scene_objects.extend(objects)
                center = (
                    np.asarray(self._center, dtype=float)
                    if isinstance(self._center, np.ndarray)
                    else np.zeros(3, dtype=float)
                )
                centers.append(center)
                try:
                    radii.append(float(self._radius))
                except Exception:
                    radii.append(1.0)

        if not radii:
            self._scene = None
            return

        radius = max(radii)
        try:
            centers_arr = np.vstack(centers)
            center = centers_arr.mean(axis=0)
        except Exception:
            center = np.zeros(3, dtype=float)

        if fit_camera:
            self._fit_camera_to_radius(radius)

        self._scene = Scene(objects=scene_objects, center=center, radius=radius)
        try:
            self._renderer.set_scene(self._scene)
        except Exception:
            pass

    def _build_scene_for_current_object(self, object_prefix: str | None = None) -> list[SceneObject]:
        if self._coords is None or self._coords.size == 0:
            return []

        coords = np.asarray(self._coords, dtype=float)
        if coords.ndim == 3:
            state = self._get_active_state()
            idx = self._select_state_frame(state, getattr(state, "active_frame", 0))
            coords = np.asarray(state.coords, dtype=float)
            state.active_frame = idx
        if coords.ndim != 2 or coords.shape[1] != 3:
            return []
        coords = coords.copy()
        n_points = coords.shape[0]

        cartoon_cfg = self._cartoon_config(_DISPLAY_CONFIG.get("cartoon", {}))
        balls_cfg = _DISPLAY_CONFIG.get("balls", {})
        sticks_cfg = _DISPLAY_CONFIG.get("sticks", {})
        surface_cfg = _DISPLAY_CONFIG.get("surface", {})

        if (
            self._color_mode == "by_secondary_structure"
            and self._secondary_structure is not None
        ):
            self._colors_per_ca = _build_ss_color_array(
                self._secondary_structure, n_points
            )
        elif self._color_mode == "by_residue" and self._residue_names is not None:
            self._colors_per_ca = _build_residue_color_array(
                self._residue_names, n_points
            )
        elif self._color_mode == "by_sequence":
            self._colors_per_ca = _build_sequence_gradient_colors(n_points)
        elif self._color_mode == "by_element":
            elements = None
            if self._atoms is not None and "element" in self._atoms.dtype.names:
                elements = self._atoms["element"]
            self._colors_per_ca = _build_element_color_array(elements, n_points)
        elif self._color_mode == "by_chain":
            self._colors_per_ca = _build_chain_color_array(self._residue_chain_ids, n_points)
        elif self._color_mode == "spectrum":
            # PyMOL 'spectrum' usually defaults to b-factor or sequence.
            # For now, let's use sequence gradient if no values provided.
            # In a fuller impl, we'd check for B-factor data.
            self._colors_per_ca = _build_sequence_gradient_colors(n_points)
        else:
            base = np.asarray(self._base_color_single, dtype=float)
            self._colors_per_ca = np.tile(base, (n_points, 1))

        # Apply optional per-residue color overrides on top of the base colors.
        try:
            ov = getattr(self, "_colors_per_residue_override", None)
        except Exception:
            ov = None
        if ov is not None:
            try:
                ov_arr = np.asarray(ov, dtype=float)
            except Exception:
                ov_arr = None
            if (
                ov_arr is not None
                and ov_arr.ndim == 2
                and ov_arr.shape[0] == n_points
            ):
                base_cols = self._colors_per_ca
                if base_cols is None or base_cols.shape != ov_arr.shape:
                    base = np.asarray(self._base_color_single, dtype=float)
                    base_cols = np.tile(base, (n_points, 1))
                base_cols = np.asarray(base_cols, dtype=float)
                mask = np.all(np.isfinite(ov_arr), axis=1)
                if mask.any():
                    base_cols[mask] = ov_arr[mask]
                self._colors_per_ca = base_cols

        # And the per-*atom* override on top of that. It has to be folded in
        # here, at the one place the per-residue array is finalised, because the
        # cartoon and the trace read only that array -- see _ca_rgba.
        projected = self._ca_rgba(n_points)
        if projected is not None:
            base_cols = self._colors_per_ca
            base_cols = (
                np.asarray(base_cols, dtype=float)
                if base_cols is not None and np.shape(base_cols) == projected.shape
                else np.tile(np.asarray(self._base_color_single, dtype=float), (n_points, 1))
            )
            mask = np.all(np.isfinite(projected), axis=1)
            base_cols[mask] = projected[mask]
            self._colors_per_ca = base_cols

        scene_objects: list[SceneObject] = []
        scene_objects += self._update_cartoon(coords, n_points, cartoon_cfg, self._colors_per_ca)
        scene_objects += self._update_trace(coords, self._colors_per_ca)
        scene_objects += self._update_atoms(coords, n_points, balls_cfg, self._colors_per_ca) or []
        if self._show_atom_gaussians:
            feature_cfg = _DISPLAY_CONFIG.get("atom_features", {})
            gaussian_cfg = feature_cfg.get("gaussian_covariances", {})
            if not isinstance(gaussian_cfg, dict):
                gaussian_cfg = {}
            scene_objects += self._update_atom_gaussians(gaussian_cfg) or []
        scene_objects += self._update_sticks(sticks_cfg, self._colors_per_ca) or []
        scene_objects += self._update_lines(self._colors_per_ca)
        scene_objects += self._update_nonbonded(self._colors_per_ca)
        scene_objects += self._update_labels()
        scene_objects += self._update_surface(coords, surface_cfg, self._colors_per_ca) or []

        metaball_cfg = _DISPLAY_CONFIG.get("metaball", {})
        scene_objects += self._update_metaballs(coords, metaball_cfg, self._colors_per_ca) or []

        scene_objects += self._update_dots(coords, self._colors_per_ca) or []
        scene_objects += self._update_custom_overlays(surface_cfg) or []
        scene_objects += self._update_measurements() or []
        scene_objects += self._update_restraints(self._get_active_state()) or []
        scene_objects += self._update_selection_highlight(coords) or []

        if object_prefix:
            for obj in scene_objects:
                obj.id = f"{object_prefix}:{obj.id}"

        return scene_objects

    def _fit_camera_to_radius(self, radius: float) -> None:
        if self._renderer is None:
            return
        self._renderer.fit_to_radius(radius)
