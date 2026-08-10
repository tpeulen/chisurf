from __future__ import annotations

import copy
import logging
import math
import time
from collections import OrderedDict
from collections.abc import Sequence
from contextlib import contextmanager
from importlib import import_module
from typing import Any, Optional, Union

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from ..analysis.atom_classes import classify_atoms
from ..analysis.side_chain_helper import hidden_backbone_bonds
from ..analysis.ss import assign_ss_c3_from_atoms
from ..colors import (
    as_rgba,
    _build_chain_color_array,
    _build_element_color_array,
    _build_residue_color_array,
    _build_sequence_gradient_colors,
    _build_ss_color_array,
    _three_to_one_array,
)
from ..config import _DISPLAY_CONFIG, register_update_listener, unregister_update_listener
from ..io.atoms import bead_mask
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
    _estimate_ambient_occlusion as _estimate_ambient_occlusion_raw,
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


def _estimate_ambient_occlusion(*args, **kwargs):
    """Per-point ambient occlusion, honouring the global switch.

    Six representations bake occlusion through this name and only one of them
    consulted ``occlusion.enabled`` -- so turning occlusion off left sticks,
    balls, beads and both surface paths shading exactly as before. Gating here
    rather than at each call site means the switch governs all of them and a new
    representation cannot forget to ask.

    Returns
    -------
    numpy.ndarray or None
        The occlusion array, or ``None`` when occlusion is switched off. Callers
        already treat ``None`` as "no occlusion available".
    """
    if not _occlusion_enabled():
        return None
    return _estimate_ambient_occlusion_raw(*args, **kwargs)


def _occlusion_enabled() -> bool:
    """Whether ambient occlusion is switched on.

    One reader for one key. Every representation that bakes occlusion asks this
    rather than reaching into the config itself: the three that did not were
    applying occlusion whatever the setting said, and the one that did read it
    read it backwards, so the switch did the opposite of what it promised.

    Returns
    -------
    bool
        The ``occlusion.enabled`` flag, defaulting to ``True``.
    """
    return bool((_DISPLAY_CONFIG.get("occlusion") or {}).get("enabled", True))


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




def _smooth_frame(
    frames: np.ndarray,
    index: int,
    frame: np.ndarray,
    window: int,
) -> np.ndarray:
    """Average *frame* over the smoothing window centred on *index*.

    Parameters
    ----------
    frames : numpy.ndarray
        ``(T, N, 3)`` trajectory.
    index : int
        The frame being shown.
    frame : numpy.ndarray
        The coordinates that would be shown without smoothing.
    window : int
        Width in frames; 0 or 1 means no smoothing.

    Returns
    -------
    numpy.ndarray
        Averaged coordinates, or ``frame`` unchanged when the window would not
        cover more than one frame.
    """
    window = int(window or 0)
    if window <= 1:
        return frame
    n_frames = int(frames.shape[0])
    if n_frames < 2:
        return frame
    half = window // 2
    # Clipped at the ends rather than wrapped: a trajectory's last frame is not
    # next to its first, and averaging across that seam invents motion that
    # never happened.
    lo = max(0, index - half)
    hi = min(n_frames, index + half + 1)
    if hi - lo < 2:
        return frame
    return np.asarray(frames[lo:hi], dtype=float).mean(axis=0)


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


def _rgba(colors) -> np.ndarray:
    """An ``(n, 3)`` or ``(n, 4)`` colour array as ``(n, 4)``, opaque by default.

    Parameters
    ----------
    colors : array_like
        Per-row RGB or RGBA in ``0..1``.

    Returns
    -------
    numpy.ndarray
        ``(n, 4)``.
    """
    arr = np.asarray(colors, dtype=float)
    if arr.ndim == 2 and arr.shape[1] == 3:
        return np.column_stack([arr, np.ones(arr.shape[0])])
    return arr


def _apply_frame_appearance(
    state: _MolViewObjectState, idx: int, blend: float, next_idx: int
) -> None:
    """Take this frame's radii and colours, when the file gives them per frame.

    A trajectory is usually only motion, and every path here assumed that. A
    simulation is not: its particles can grow, change what they are doing, or
    not exist yet, and a reader that plays only the coordinates shows a colony
    of full-grown cells sliding into place. Radius and colour are interpolated
    between stored frames exactly as the coordinates are, so a bead that appears
    grows into view rather than popping.

    Parameters
    ----------
    state : _MolViewObjectState
        The object being stepped; updated in place.
    idx : int
        The stored frame at or below the position shown.
    blend : float
        Weight toward ``next_idx``; ``0`` on a stored frame.
    next_idx : int
        The frame after ``idx``.
    """

    def _at(series):
        if series is None:
            return None
        arr = np.asarray(series)
        if arr.ndim < 2 or idx >= arr.shape[0]:
            return None
        if blend <= 0.0 or next_idx >= arr.shape[0]:
            return arr[idx]
        return (1.0 - blend) * arr[idx] + blend * arr[next_idx]

    radii = _at(state.frame_radii)
    if radii is not None:
        state.all_atom_radii = np.asarray(radii, dtype=float)
        # A bead with no size is one the file has not created yet. Saying that
        # with a mask rather than a zero radius matters because the renderers
        # substitute a default for a non-positive radius -- which would draw
        # every unborn cell at full size, all of them, from the first frame.
        state.absent_mask = np.asarray(radii, dtype=float) <= 0.0

    colors = _at(state.frame_colors)
    if colors is not None:
        state.colors_per_atom_override = _rgba(colors)


def _triangle_edges(faces: np.ndarray) -> np.ndarray:
    """Unique undirected edges of a triangle list, as ``(M, 2)`` indices.

    Every interior edge is shared by two triangles, so drawing all three edges of
    each would send twice the lines needed -- on a contour with tens of thousands
    of triangles that is worth removing rather than leaving to the GPU.
    """
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if faces.size == 0:
        return np.zeros((0, 2), dtype=np.int32)
    edges = np.concatenate(
        [faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=0
    )
    edges = np.sort(edges, axis=1)
    edges = np.unique(edges, axis=0)
    return edges.astype(np.int32)


def _dash_segments(
    pairs: np.ndarray, dash_length: float, gap: float
) -> np.ndarray:
    """Chop line segments into dashes.

    A measurement is dashed in PyMOL, and the line primitive here has no
    stipple, so the dashes are geometry: each ``(start, end)`` pair becomes a
    run of short segments spaced ``dash_length + gap`` apart, the last one
    clipped to the end so the dash pattern never overshoots the atom it points
    at.

    Parameters
    ----------
    pairs : (K, 2, 3) numpy.ndarray
        Segment endpoints.
    dash_length, gap : float
        Dash and gap size, in the same units as ``pairs``. A non-positive dash
        length means "solid", and the segments come back unchanged.

    Returns
    -------
    numpy.ndarray
        ``(2M, 3)`` dash endpoints, ready for a ``GL_LINES`` draw.
    """
    pairs = np.asarray(pairs, dtype=float).reshape(-1, 2, 3)
    if pairs.shape[0] == 0:
        return np.zeros((0, 3), dtype=float)
    period = float(dash_length) + max(float(gap), 0.0)
    if dash_length <= 0.0 or period <= 0.0:
        return pairs.reshape(-1, 3)

    out: list[np.ndarray] = []
    for start, end in pairs:
        direction = end - start
        total = float(np.linalg.norm(direction))
        if total <= 1e-9:
            continue
        unit = direction / total
        # A contact shorter than one period still has to be visible, so it
        # keeps a single dash rather than disappearing between two gaps.
        offsets = np.arange(0.0, total, period)
        for offset in offsets:
            stop = min(offset + dash_length, total)
            out.append(start + unit * offset)
            out.append(start + unit * stop)
    if not out:
        return np.zeros((0, 3), dtype=float)
    return np.asarray(out, dtype=float)


#: Samples per axis the surface grid will never exceed, however fine a spacing
#: is asked for. Measured on 148L (37x41x48 A, 1300 atoms): 320 samples/axis is
#: 172k vertices in 0.66 s, which is a fair price for a level PyMOL itself calls
#: "nearly perfect". The next level up is 4x that again for no visible gain.
_SURFACE_GRID_CEILING = 320


def _surface_grid_cap(
    points: np.ndarray, spacing: float, padding: float, configured: int
) -> int:
    """Samples per axis to allow, so a finer spacing is actually delivered.

    ``max_dim`` is a hard cap inside the mesh builder, which **rescales the
    spacing to fit it** -- so on anything larger than a fragment every fine
    setting collapsed to the same grid. Measured on 148L before this: asking for
    0.5 A and 0.25 A gave 27 648 and 29 152 vertices, a 5 % difference across a
    2x request, because both were pinned at 96 samples. Raising the cap to what
    the request needs gives 42 502 and 171 810 -- which is what "finer" is
    supposed to mean.

    The configured value stays the floor, so nothing gets *coarser* than before,
    and :data:`_SURFACE_GRID_CEILING` stops an extreme level from asking for a
    grid that cannot be built.

    Parameters
    ----------
    points : (N, 3) numpy.ndarray
        The atoms the surface is built over.
    spacing : float
        Requested grid spacing in Angstrom.
    padding : float
        Margin the mesh builder adds around the extent.
    configured : int
        ``surface.max_dim`` -- the floor, and what was previously the cap.

    Returns
    -------
    int
        Samples per axis to permit.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[0] == 0 or spacing <= 0.0:
        return max(int(configured), 16)
    extent = float(np.max(pts.max(axis=0) - pts.min(axis=0))) + 2.0 * float(padding)
    needed = int(np.ceil(extent / float(spacing))) + 1
    return int(min(max(int(configured), needed), _SURFACE_GRID_CEILING))


#: Colour a map opens in when nothing else is asked for.
_DEFAULT_MAP_COLOR = (0.5, 0.7, 1.0, 1.0)


def _negative_lobe_color(rgba):
    """The complement of a map's colour, for its negative lobe.

    Transcribed from the reference tool's ``_negative_color``: invert the
    channels, then brighten the result if inverting left it dark, so the two
    lobes of a difference map stay distinguishable whatever the positive colour
    is. A colour that inverts to black becomes red rather than invisible.
    """
    inverted = [1.0 - c for c in rgba[:3]]
    brightest = max(inverted)
    if brightest == 0:
        return (1.0, 0.0, 0.0, rgba[3])
    if brightest < 0.7:
        inverted = [c / brightest for c in inverted]
    return (inverted[0], inverted[1], inverted[2], rgba[3])


def _default_volume_levels(grid) -> list[dict]:
    """The contours a map opens with, following the reference tool.

    One level enclosing the densest one per cent, except that a binary map --
    which an accessible volume is -- opens at 0.5, and a map signed both ways
    opens with a symmetric pair so its negative lobe is not hidden.
    """
    try:
        values = grid.default_levels()
    except Exception:
        values = [grid.default_level()]
    if not values:
        return []
    negative = _negative_lobe_color(_DEFAULT_MAP_COLOR)
    return [
        {
            "level": level,
            "color": negative if level < 0 else _DEFAULT_MAP_COLOR,
            "style": "surface",
        }
        for level in values
    ]


def _bead_mask(atoms) -> np.ndarray | None:
    """Which rows are beads rather than atoms, one entry per row.

    Per row, and over the *whole* array, because an integrative entry is
    routinely a mixture: the mmCIF reader writes every atomic row before every
    sphere row, so a model with one resolved subunit and 200,000 beads opens
    with an atom at the head of the array. Judging the array by a sample of its
    first rows classified that model as a protein and put the whole
    cartoon-through-beads pathology back; judging a bead-first array the same
    way stripped a resolved subunit of its cartoon. Neither is a rare shape --
    it is what depositing both `atom_site` and `ihm_sphere_obj_site` records
    produces, which is the normal shape of an integrative model.

    Parameters
    ----------
    atoms : numpy.ndarray or None
        Structured per-atom array carrying ``res_name``.

    Returns
    -------
    numpy.ndarray or None
        Boolean mask of length ``len(atoms)``, or ``None`` when there is no
        usable atom array.
    """
    if atoms is None:
        return None
    try:
        names = np.asarray(atoms["res_name"])
    except Exception:
        return None
    return bead_mask(names)


def _is_bead_model(atoms) -> bool:
    """Whether these "atoms" are *entirely* the beads of a coarse-grained model.

    A bead stands for a range of residues and has no backbone, so every
    backbone-derived analysis is not merely wasted on it but meaningless.
    Secondary-structure assignment was 4 of the 10 seconds it took to open one
    spoke of the nuclear pore -- computed over 29,273 beads that have no
    hydrogen bonds to find.

    For a model that mixes beads with resolved atoms, ask :func:`_bead_mask`
    instead and treat each part as what it is.
    """
    mask = _bead_mask(atoms)
    return bool(mask is not None and mask.all())


def _expand_occlusion(
    values: np.ndarray, sample: np.ndarray, n: int
) -> np.ndarray:
    """Spread a per-sampled-vertex occlusion field back over every vertex.

    ``values`` holds the occlusion of the ``sample`` vertices of a larger mesh.
    Its index ``j`` corresponds to mesh vertex ``sample[j]``. The full ``n``-long
    array is reconstructed by linear interpolation over the sampled indices: a
    vertex between two samples gets the value on the straight line joining them.
    The occlusion field is smooth over a surface and the sampling is regular, so
    the interpolation error stays far below the occlusion contrast itself.
    """
    values = np.asarray(values, dtype=float)
    return np.interp(np.arange(n), sample.astype(float), values)


class MolView(QtWidgets.QWidget):

    # Emitted when residues are selected via picking in the 3D view. The
    # payload is a list of integer residue indices along the CA trace.
    residueSelectionChanged = QtCore.Signal(object)
    objectResidueSelectionChanged = QtCore.Signal(object, object)
    # Emitted when atoms are selected via picking in the 3D view. The
    # payload is a list of integer atom indices.
    atomSelectionChanged = QtCore.Signal(object)
    # A short line for the status bar, for things the view does that have no
    # other trace. A mouse gesture that changes a mode silently -- clipping,
    # say -- is undiagnosable when it is triggered by accident, and clipping
    # was: a slab cut into a closed surface reads as broken transparency.
    statusMessage = QtCore.Signal(str)
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
    _volume = _StateField("volume")
    _volume_levels = _StateField("volume_levels")
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
    _trace_mask = _StateField("trace_mask")
    _lines_mask = _StateField("lines_mask")
    _nonbonded_mask = _StateField("nonbonded_mask")
    _label_mask = _StateField("label_mask")
    _dots_mask = _StateField("dots_mask")
    _surface_mask = _StateField("surface_mask")
    _metaball_mask = _StateField("metaball_mask")
    _bond_pairs = _StateField("bond_pairs")
    _bond_edits = _StateField("bond_edits")
    _protected_mask = _StateField("protected_mask")
    _masked_mask = _StateField("masked_mask")
    _surface_visible = _StateField("surface_visible")
    _metaballs_visible = _StateField("metaballs_visible")
    _point_overlays = _StateField("point_overlays")
    _ca_indices = _StateField("_ca_indices")
    _measurements = _StateField("measurements")
    _rmf_hierarchy = _StateField("rmf_hierarchy")
    _hidden_mask = _StateField("hidden_mask")
    _resolutions = _StateField("resolutions")
    _representation_mask = _StateField("representation_mask")
    _absent_mask = _StateField("absent_mask")
    _frame_radii = _StateField("frame_radii")
    _frame_colors = _StateField("frame_colors")
    _rmf_resolutions = _StateField("rmf_resolutions")
    _restraints = _StateField("restraints")
    _rmf_provenance = _StateField("rmf_provenance")

    def apply_payload(
        self, payload, *, object_id: str | None = None, fit_camera: bool = True
    ) -> None:
        """Load everything a reader recovered from a file into one object.

        The single route from a file into the viewer. RMF used to have its own
        -- ``set_rmf_data``, which filled a parallel set of state fields -- and
        the consequence was not that RMF looked slightly different but that it
        received nothing the common path knew: beads drawn at one default radius
        instead of their own, decimated to a fraction of themselves rather than
        drawn as impostors, and a hierarchy whose check boxes moved nothing at
        all.

        Parameters
        ----------
        payload : StructurePayload
            What the reader produced.
        object_id : str, optional
            Which object to load into; the active one by default.
        fit_camera : bool, optional
            Frame the result -- PyMOL's ``auto_zoom``, which its own wizard
            turns **off** before building a preview (`cmd.set('auto_zoom', 0)`
            in `do_library`). An object created beside the one you are looking
            at must not throw your framing away.
        """
        with self._activate_object(object_id):
            self.set_coordinates(
                payload.coords,
                fit_camera=fit_camera,
                trace_coords=payload.trace_coords,
                res_ids=payload.res_ids,
                res_names=payload.res_names,
                chain_ids=payload.chain_ids,
                atoms=payload.atoms,
                atom_radii=payload.atom_radii,
                bonds=payload.bonds,
                hierarchy=payload.hierarchy,
                resolutions=payload.resolutions,
                resolution_default_mask=payload.resolution_default_mask,
            )

            extras = getattr(payload, "extras", None) or {}
            state = self._get_active_state()
            if extras.get("restraints"):
                state.restraints = extras["restraints"]
            if extras.get("rmf_provenance"):
                state.rmf_provenance = extras["rmf_provenance"]
            if extras.get("rmf_frame_series") is not None:
                state.rmf_frame_series = extras["rmf_frame_series"]
            if extras.get("rmf_frame_metadata") is not None:
                state.rmf_frame_metadata = extras["rmf_frame_metadata"]
            if extras.get("frame_radii") is not None:
                # Scaled here, once, into the units ``all_atom_radii`` is kept
                # in -- the frame seam that reads it has no view to ask.
                state.frame_radii = (
                    np.asarray(extras["frame_radii"], dtype=float)
                    * float(self._scale_factor)
                )
            if extras.get("frame_colors") is not None:
                state.frame_colors = np.asarray(extras["frame_colors"], dtype=float)
            if extras.get("bead_colors") is not None:
                # The file's own colours, so a model that states them is drawn
                # as it says rather than in the viewer's default. `color` still
                # overrides, as it does for a structure read from a PDB.
                state.colors_per_atom_override = _rgba(extras["bead_colors"])

            # Frames last. `set_frames` centres and scales over the *whole*
            # trajectory, which is what stops the model jumping about as it
            # plays; doing it before `set_coordinates` would leave the object
            # centred on one frame instead.
            if payload.frames is not None and len(payload.frames) > 0:
                self.set_frames(np.asarray(payload.frames, dtype=float))

    def add_payload(
        self,
        payload,
        *,
        name: str | None = None,
        source_path: str | None = None,
        fit_camera: bool = True,
    ) -> str:
        """Create an object from a reader payload and return its id.

        Parameters
        ----------
        payload : StructurePayload
            What the reader produced.
        name : str, optional
            Display name for the object list.
        source_path : str, optional
            Where it came from, for the info panel and for deposited
            secondary-structure lookup.

        Returns
        -------
        str
            The new object's id.
        """
        entry = self._create_object(name=name, source_path=source_path)
        self.apply_payload(
            payload, object_id=entry.object_id, fit_camera=fit_camera
        )
        self._apply_deposited_secondary_structure(source_path)
        return entry.object_id

    @staticmethod
    def _residue_bead_mask(res_names) -> np.ndarray | None:
        """Which *traced residues* are beads, one entry per trace point.

        The atom-level mask says which rows are beads; the cartoon is built per
        residue, so it needs the same question asked of the trace. In an
        integrative entry one bead contributes exactly one trace point, which is
        what makes the two masks line up with each other.

        Parameters
        ----------
        res_names : sequence or None
            Per-trace-point residue names, as handed to ``set_coordinates``.

        Returns
        -------
        numpy.ndarray or None
            Boolean mask over trace points, or ``None`` when there are no names.
        """
        return bead_mask(res_names)

    def is_empty(self) -> bool:
        """Whether the viewer holds nothing a command could act on.

        A fresh viewer -- and one just emptied by ``delete all`` -- keeps a
        **placeholder** entry so that settings made before anything is loaded
        survive the first load. It is not a molecule. Answering commands about
        it as though it were is how an empty viewer came to report ``zoom all``
        as "matched no atoms" and ``spectrum`` as "that object has no atoms to
        colour": both describe a broken molecule, where in fact there is none.

        Returns
        -------
        bool
            True when every entry is a placeholder, or there are no entries.
        """
        return not any(
            not entry.placeholder for entry in self._objects.values()
        )

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

    def _representation_color(self, name: str) -> np.ndarray | None:
        """PyMOL's per-representation colour override, as RGBA, or ``None``.

        ``stick_color``, ``cartoon_color`` and ``surface_color`` each say "draw
        this representation in *this* colour, whatever the atoms are". PyMOL
        stores the absence of an override as the sentinel ``cColorDefault``
        (-1) and every representation applies the same one-line rule --
        ``c != cColorDefault ? c : ai->color`` (`RepCylBond.cpp`,
        `RepSurface.cpp`, `RepRibbon.cpp`) -- so there is one rule here too,
        read by each representation as it assembles its colours.

        Parameters
        ----------
        name : str
            ``"stick"``, ``"cartoon"`` or ``"surface"``.

        Returns
        -------
        numpy.ndarray or None
            ``(4,)`` RGBA, or ``None`` for "no override" -- which is the whole
            point: the caller then leaves the per-atom colours it already built
            exactly as they are.

        Notes
        -----
        Read from the configuration **here, where it is used**, so a live
        ``set stick_color, red`` reaches the next redraw. Caching it on the
        object at load time is what made three other settings inert.
        """
        spec = (_DISPLAY_CONFIG.get("colors") or {}).get(f"{name}_color")
        if spec is None:
            return None
        parsed = as_rgba(spec)
        if parsed is None:
            return None
        rgba = np.asarray(parsed, dtype=float)
        return rgba if np.isfinite(rgba).all() else None

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
        self._update_view()

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

    def set_trajectory_smoothing(self, frames: int) -> None:
        """Average each frame with its neighbours over a window of *frames*.

        A trajectory sampled often enough to be smooth in time is rarely smooth
        to *look* at: thermal motion moves every atom a little in every frame,
        so the picture jitters even when nothing is happening. A running mean
        over a few frames removes that without touching the slower motion, which
        is what anyone is watching for.

        The average is over the **stored** frames around the one shown, centred,
        and it never changes which frame is current -- only what is drawn -- so
        measurements, exports and the frame number all continue to mean what
        they say.

        Parameters
        ----------
        frames : int
            Window width in frames. ``0`` or ``1`` shows the trajectory as
            recorded; larger values average more and lag more.
        """
        self._trajectory_smoothing = max(0, int(frames))
        try:
            state = self._get_active_state()
            self._select_state_frame(state, getattr(state, "active_frame", 0))
            self._update_view()
        except Exception:
            logger.debug("chimol: could not re-apply smoothing", exc_info=True)

    def get_trajectory_smoothing(self) -> int:
        """The smoothing window in frames; 0 or 1 means none."""
        return int(getattr(self, "_trajectory_smoothing", 0))

    def set_frame_step(self, step: int) -> None:
        """How many frames playback advances per step.

        This is the same setting the ``mset`` command drives, so the control
        beside the slider and the command line cannot disagree about it. It
        *skips* frames rather than averaging them -- the two knobs answer
        different questions, and a long trajectory usually wants both: step to
        cover it in reasonable time, smoothing to stop it shimmering.

        Parameters
        ----------
        step : int
            Frames per step; at least 1.
        """
        self.movie_step = max(1, int(step))

    def get_frame_step(self) -> int:
        """Frames advanced per playback step."""
        return max(1, int(getattr(self, "movie_step", 1) or 1))

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

        # `getattr` rather than `self.`: `_select_state_frame` is also driven
        # unbound (`MolView._select_state_frame(None, state, i)`) by tests that
        # exercise the frame maths without building a widget.
        frame = _smooth_frame(
            arr, idx, frame, getattr(self, "_trajectory_smoothing", 0)
        )

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
        # Residue ids are *not* required here. They were, because this started
        # life as a fix for cartoon ribbon normals -- but `atoms["xyz"]` is what
        # `zoom`, `distance` and `select ... within` read, so an object with
        # atoms and no residues had every measurement silently frozen at the
        # first frame while the picture moved. Only the backbone map, below,
        # genuinely needs residues.
        if frame_matches_all_atoms and state.atoms is not None:
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
                    if state.residue_ids is not None:
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

        # Whether the camera follows the frame. For a molecule that wanders
        # across a box, following its centroid is what keeps it in view; for
        # anything that *grows*, or that is attached to something, it slides the
        # scene out from under it -- playing the biofilm demo swung the scene
        # centre from 0 to -21 to +52 scene units and the radius from 174 to 88
        # to 137, so the substratum drifted about beneath a film that was
        # supposed to be growing off it. PyMOL never re-centres; this is
        # ChiMOL's, on by default because the molecular case is the common one.
        #
        # Read from the configuration *here*, where it is used, so that `set
        # movie_recenter, off` reaches an open viewer and there is no second
        # copy to leave stale.
        if bool((_DISPLAY_CONFIG.get("camera") or {}).get("recenter_on_frame", True)):
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

        _apply_frame_appearance(state, idx, blend, next_idx)

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
        atom_radii: np.ndarray | None = None,
        hierarchy: object | None = None,
    ) -> str:
        entry = self._create_object(name=name, source_path=source_path)
        self.set_coordinates(
            coords,
            trace_coords=trace_coords,
            res_ids=res_ids,
            res_names=res_names,
            chain_ids=chain_ids,
            atoms=atoms,
            atom_radii=atom_radii,
            hierarchy=hierarchy,
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
                # Bottom left, not top left: the top left of the viewport is
                # where the sequence strip and the object panel already put
                # text, and the molecule is framed centre-high, so an info block
                # anchored to the top competes with both. The bottom left is the
                # emptiest corner of a framed structure.
                alignment=QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom,
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
    def set_structure(self, structure: object, *, fit_camera: bool = True) -> None:
        """Set structure from a ChiSurf ``Structure``-like object.

        The object is expected to provide either:
        - ``atoms``: NumPy structured array with fields ``'xyz'`` and
          ``'atom_name'`` (as in :mod:`chisurf.core.structure`), or
        - ``xyz``: array-like of shape ``(N, 3)``.

        Parameters
        ----------
        structure : object
            The structure to show.
        fit_camera : bool, optional
            Frame the result -- PyMOL's ``auto_zoom``, which applies to a
            *newly created* object. This is also the one path that re-derives
            everything after an edit (see
            ``EditingMixin._rebuild_after_coordinate_change``), and re-deriving
            is not loading: ``h_add`` on a residue you have zoomed into must
            not throw the framing away.
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
                    ss_codes = (
                        None if _is_bead_model(atoms)
                        else assign_ss_c3_from_atoms(atoms, n_res, verbose=False)
                    )
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

            self._update_view(fit_camera=fit_camera)
            return

        # Case 2: fallback to ``structure.xyz`` attribute
        xyz_attr = getattr(structure, "xyz", None)
        if xyz_attr is not None:
            self.set_coordinates(
                np.asarray(xyz_attr, dtype=float), fit_camera=fit_camera
            )
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
        atom_radii: np.ndarray | None = None,
        bonds: np.ndarray | None = None,
        hierarchy: object | None = None,
        resolutions: np.ndarray | None = None,
        resolution_default_mask: np.ndarray | None = None,
        fit_camera: bool = True,
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
        atom_radii:
            Optional per-atom radii in the same (unscaled) units as ``xyz``.
            An integrative model's beads differ in size by an order of
            magnitude and the sizes *are* the shape of the thing, so a single
            default radius does not describe it. Scaled here with the
            coordinates so every downstream renderer stays in one frame.
        bonds:
            Optional ``(K, 2)`` connectivity the *file states*. When given it is
            used verbatim: it outranks both the distance-cutoff inference and
            the rule that a bead model has no bonds, because a reader that knows
            the topology is a better source than either.
        hierarchy:
            The tree the file describes -- molecules, and the copies of them
            this model places -- as a
            :class:`~chisurf.plugins.chimol.chimol.io.hierarchy.HierarchyNode`.
            An integrative mmCIF carries one, in the same shape the RMF reader
            builds, and it feeds the same panel.
        resolutions:
            Optional per-row resolution of the representation each row belongs
            to, for a file that offers more than one. ``None`` means there is
            nothing to choose between.
        resolution_default_mask:
            Optional per-row mask of the representation to show on opening --
            the one that lives in the file's own tree. Rows outside it are
            present but not drawn until asked for, so a file opens looking as it
            always did.
        """
        arr = np.asarray(xyz, dtype=float)
        if arr.ndim != 2 or arr.shape[1] != 3:
            raise ValueError("xyz must have shape (N, 3)")

        self._atoms = atoms if isinstance(atoms, np.ndarray) else None
        # The same field the RMF reader fills: one hierarchy per object, however
        # it was read, so the panel does not have to know which reader ran.
        self._rmf_hierarchy = hierarchy
        self._set_representations(arr.shape[0], resolutions, resolution_default_mask)
        # Which residue each atom belongs to. `set_structure` fills this from
        # the same field and this method only cleared it, so **every object
        # loaded through a payload** -- which is every reader except the PDB
        # structure path: RMF, mmCIF, bead models -- had no atom-to-residue map
        # at all. Clicking one picked the atom and then found no residue to
        # select, which looks exactly like picking being broken.
        self._all_atom_res_ids = None
        if isinstance(atoms, np.ndarray) and "res_id" in set(atoms.dtype.fields or {}):
            try:
                self._all_atom_res_ids = np.asarray(atoms["res_id"])
            except Exception:
                self._all_atom_res_ids = None
        elif res_ids is not None:
            # No atom table, so the coordinates *are* the residues -- one row
            # each, which is what a coarse bead model gives.
            candidate = np.asarray(res_ids)
            if candidate.shape[0] == arr.shape[0]:
                self._all_atom_res_ids = candidate
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
        if atom_radii is not None:
            radii_arr = np.asarray(atom_radii, dtype=float).ravel()
            if radii_arr.shape[0] == arr.shape[0]:
                good = np.isfinite(radii_arr) & (radii_arr > 0.0)
                self._all_atom_radii[good] = radii_arr[good] * scale
            else:
                logger.warning(
                    "atom_radii has %d entries for %d coordinates; ignoring them.",
                    radii_arr.shape[0],
                    arr.shape[0],
                )

        # Named apart from the imported `bead_mask` helper: a local of the same
        # name shadows it for the whole function body, which is a trap for the
        # next edit rather than a bug today.
        beads = _bead_mask(self._atoms)
        has_beads = beads is not None and bool(beads.any())
        all_beads = beads is not None and bool(beads.all())

        # Replay any manual bond/unbond over the fresh inference: a hand-made
        # bond stored only in bond_pairs vanishes the moment coordinates change.
        #
        # A bead has no bonds to infer. It stands for a *range* of residues, so
        # no interatomic distance cutoff means anything on it, and the search is
        # not free: it is 0.7 s of the 4.3 s one nuclear-pore spoke takes to
        # open, for pairs that would be wrong if it found any. A model that
        # mixes beads with resolved atoms is bonded over the atoms alone, with
        # the pair indices mapped back to the full array.
        #
        # Bonds the *file states* are not inferred and not guessed away: a
        # reader that knows the connectivity outranks both the distance cutoff
        # and the rule that a bead model has none. An RMF names its bonds, and
        # they are often the restraint topology someone opened the file to see.
        if bonds is not None:
            stated = np.asarray(bonds, dtype=int).reshape(-1, 2)
            self._bond_pairs = self._apply_bond_edits(stated)
        elif all_beads:
            self._bond_pairs = self._apply_bond_edits(np.zeros((0, 2), dtype=int))
        elif has_beads:
            atomic = np.nonzero(~beads)[0]
            pairs = self._infer_bonds(raw_all[atomic], self._atoms[atomic])
            pairs = np.asarray(pairs, dtype=int).reshape(-1, 2)
            self._bond_pairs = self._apply_bond_edits(
                atomic[pairs] if pairs.size else pairs
            )
        else:
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
                if all_beads:
                    # Nothing to find: no bead has a backbone.
                    ss_codes = None
                elif has_beads:
                    # Search the resolved atoms only, then scatter the answer
                    # back over the full residue list. Running it over the
                    # beads as well is the 4-seconds-a-spoke cost, spent on
                    # rows that cannot contribute a hydrogen bond.
                    atomic = np.nonzero(~beads)[0]
                    res_beads = self._residue_bead_mask(self._residue_names)
                    # Only when the residue-level mask really describes this
                    # trace: without one there is no way to say which code
                    # belongs to which residue, and a mis-scattered assignment
                    # is worse than none.
                    if res_beads is not None and res_beads.shape[0] == n_res:
                        n_atomic_res = int((~res_beads).sum())
                        codes = assign_ss_c3_from_atoms(
                            self._atoms[atomic], n_atomic_res, verbose=False
                        )
                        if codes:
                            full = np.full(n_res, "C", dtype="U1")
                            full[~res_beads] = np.asarray(codes, dtype="U1")[
                                :n_atomic_res
                            ]
                            ss_codes = full.tolist()
                        else:
                            ss_codes = None
                    else:
                        ss_codes = None
                else:
                    ss_codes = assign_ss_c3_from_atoms(
                        self._atoms, n_res, verbose=False
                    )
            except Exception:
                logger.warning("Secondary-structure assignment failed for raw "
                               "coordinates", exc_info=True)
                ss_codes = None
            if ss_codes:
                try:
                    self._secondary_structure = np.asarray(ss_codes, dtype="U1")
                except Exception:
                    self._secondary_structure = None

        # A bead is drawn as a bead, and an atom is not. The rule lives here,
        # in the viewer, rather than in each reader -- or the readers of the same
        # kind of model disagree about how to draw it: an
        # integrative mmCIF came out as a cartoon splined through beads that
        # have no backbone -- meaningless as a depiction, and the reason the
        # eight-spoke nuclear pore took seven minutes to open.
        #
        # The two depictions coexist in one object, because an integrative entry
        # routinely holds both: the beads take the ball mask, the resolved
        # residues keep their cartoon. The masks are set *before* the first
        # `_update_view` so no cartoon is ever built through a bead, and they
        # survive the `_fits` defaults below because they fit.
        if has_beads:
            # `self._residue_names`, not the argument: with no usable trace the
            # viewer clears them, and the mask has to describe the trace the
            # cartoon is actually built from.
            res_beads = self._residue_bead_mask(self._residue_names)
            n_res_total = (
                len(self._residue_ids) if self._residue_ids is not None else 0
            )
            # Beads, plus whatever the atomic part would have shown as balls on
            # its own -- a hybrid entry's waters and ligands are not forfeited
            # because the entry also contains beads.
            self._ball_mask = beads.copy()
            if not all_beads:
                hetero = self._hetero_atom_mask(self._atoms, arr.shape[0])
                if hetero is not None and len(hetero) == arr.shape[0]:
                    self._ball_mask |= np.asarray(hetero, dtype=bool)
            self._sticks_mask = np.zeros(arr.shape[0], dtype=bool)
            if res_beads is not None and res_beads.shape[0] == n_res_total:
                self._cartoon_mask = ~res_beads
                atomic_residues = bool((~res_beads).any())
            else:
                self._cartoon_mask = np.zeros(n_res_total, dtype=bool)
                atomic_residues = False
            self._show_atoms = True
            self._show_cartoon = atomic_residues
            self._show_trace = False

        self._update_view(fit_camera=fit_camera)

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
        if not _fits(self._absent_mask):
            self._absent_mask = None
        # The per-frame series are indexed by *row*, so a structure whose atom
        # count changed under them describes a different model and they go.
        for _series in ("_frame_radii", "_frame_colors"):
            value = getattr(self, _series)
            if value is not None and np.asarray(value).shape[1] != n_atoms:
                setattr(self, _series, None)
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
        share_frame_with: str | None = None,
    ) -> None:
        """Attach a trajectory to an object.

        Parameters
        ----------
        frames : numpy.ndarray
            ``(T, N, 3)`` raw coordinates.
        object_id : str, optional
            Which object. The active one by default.
        active_frame : int, optional
            Which frame to show.
        share_frame_with : str, optional
            Put the frames in **another object's** render frame instead of
            centring them on themselves. An object built beside an existing one
            -- a mutation preview, a docked copy -- has to be drawn where it
            belongs relative to that one, and centring it on its own centroid
            puts a fourteen-atom residue at the middle of the scene. The
            stored raw coordinates are untouched, as in :meth:`_reframe_to`;
            only the render arrays move.
        """
        arr = np.asarray(frames, dtype=float)
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise ValueError("frames must have shape (T, N, 3)")
        if arr.shape[0] == 0 or arr.shape[1] == 0:
            raise ValueError("frames must contain at least one frame and one point")

        flat = arr.reshape(-1, 3)
        center, radius = _compute_center_radius(flat)
        if share_frame_with:
            borrowed = self.object_raw_center(share_frame_with)
            if borrowed is not None:
                center = np.asarray(borrowed, dtype=float).reshape(3)
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
            if share_frame_with:
                # The object now lives in the other's frame, so its own record
                # of where the origin is has to say the same -- everything that
                # converts world coordinates for this object reads it.
                self._raw_center = np.asarray(center, dtype=float)
                # And its *scene* centre and radius are the parent's, not its
                # own. `_update_view` averages the objects' centres to aim the
                # camera and takes the largest radius to frame it, so a
                # fourteen-atom object claiming the origin as its centre drags
                # the camera target halfway there and the clip slab with it --
                # the molecule goes dark and half of it is clipped away.
                parent = self._objects.get(share_frame_with)
                parent_state = getattr(parent, "state", None)
                if parent_state is not None:
                    if getattr(parent_state, "center", None) is not None:
                        self._center = np.asarray(parent_state.center, dtype=float)
                    if getattr(parent_state, "radius", None) is not None:
                        self._radius = float(parent_state.radius)
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
                self._update_view()
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

    def get_background_color(self):
        """The background now in force, as RGBA in ``0..1``, or ``None``.

        ``bg_color`` writes to the renderer, so the renderer is the only place
        that knows the answer. Anything that draws the scene by another route --
        the ray tracer above all -- has to ask here rather than read the
        configuration, which holds the value the session *started* with: that
        gap is why a traced figure came out on black however the viewport was
        set.
        """
        renderer = self._renderer
        getter = getattr(renderer, "get_background_color", None) if renderer else None
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception:  # pragma: no cover - a renderer without a colour yet
            return None

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

    def report_status(self, text: str) -> None:
        """Show *text* in the host's status bar, if it is listening."""
        try:
            self.statusMessage.emit(str(text))
        except Exception:
            pass

    def reset_clipping(self) -> None:
        """Put the clip planes back where framing left them."""
        r = self._renderer
        if r is not None and hasattr(r, "reset_clipping"):
            r.reset_clipping()

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
        selections: Sequence[tuple[str, np.ndarray]] | None = None,
    ) -> bool:
        """Centre the camera on a selection's centre (PyMOL ``center``).

        Returns
        -------
        bool
            False when the selection yielded no coordinates, so a caller can
            report that rather than a success.

        See Also
        --------
        _selection_coords : why this takes atoms rather than residue positions,
            and what ``selections`` is for.
        """
        coords = self._selection_coords(
            indices, object_id=object_id, atom_mask=atom_mask,
            selections=selections,
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
        selections: Sequence[tuple[str, np.ndarray]] | None = None,
    ) -> np.ndarray:
        """Coordinates a camera command should measure, in render space.

        Prefers the selection's **atoms**. Residue positions are one CA-trace
        point per residue, so any residue without a CA -- a ligand, an ion, a
        water -- reduced to nothing, and `zoom resn NAG`, `center resn NAG` and
        `orient resn NAG` all silently did nothing while reporting success. A
        ligand is exactly what those commands are usually pointed at.

        Parameters
        ----------
        selections : sequence of (str, ndarray), optional
            ``(object_id, atom_mask)`` for every object the selection reached.
            A selection is not confined to one object -- a group name covers
            several -- and framing must measure all of them, or ``zoom
            <group>`` frames whichever member happened to come first.
        """
        if selections:
            parts = []
            for oid, mask in selections:
                with self._activate_object(oid):
                    all_atoms = getattr(self, "_all_atom_coords", None)
                if all_atoms is None:
                    continue
                array = np.asarray(all_atoms, dtype=float)
                mask = np.asarray(mask, dtype=bool)
                if mask.shape[0] == array.shape[0] and mask.any():
                    parts.append(array[mask])
            if parts:
                return np.concatenate(parts, axis=0)
            return np.zeros((0, 3), dtype=float)

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
        selections: Sequence[tuple[str, np.ndarray]] | None = None,
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
        selections : sequence of (str, ndarray), optional
            Every object the selection reached; see :meth:`_selection_coords`.

        See Also
        --------
        chimol.renderer.view_state.framing_radius : the two fitting rules.
        """
        # With no selection, fit every atom rather than the CA trace: PyMOL
        # measures the whole molecule, and a trace-only fit reads ~20% small
        # because the side chains reaching furthest out are exactly the ones
        # left out of it.
        coords = self._selection_coords(
            indices, object_id=object_id, atom_mask=atom_mask,
            selections=selections,
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
        selections: Sequence[tuple[str, np.ndarray]] | None = None,
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
            indices, object_id=object_id, atom_mask=atom_mask,
            selections=selections,
        )
        if coords.size == 0 or coords.shape[0] < 2:
            # One point has no orientation; framing is all that is meaningful.
            self.zoom(indices, object_id=object_id, selections=selections)
            return False

        centred = coords - coords.mean(axis=0)
        # The inertia tensor, exactly as OMOP_CSetMoment accumulates it:
        # sum over atoms of |r|^2 * I - r (outer) r.
        squared = float(np.sum(centred * centred))
        tensor = np.eye(3) * squared - centred.T @ centred

        try:
            eigenvalues, eigenvectors = np.linalg.eigh(tensor)
        except np.linalg.LinAlgError:
            self.zoom(indices, object_id=object_id, selections=selections)
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
        self.zoom(
            indices, object_id=object_id, atom_mask=atom_mask,
            selections=selections,
        )
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
            self._update_view()

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

    def set_rows_hidden(
        self,
        indices,
        hidden: bool,
        *,
        object_id: str | None = None,
    ) -> None:
        """Hide or show rows of the coordinate array.

        This is *visibility*, not representation: a row switched off here is not
        drawn by anything. It is what the hierarchy panel's check boxes act on,
        so that switching off ``Nup84`` removes its 10,560 beads from the picture
        without changing how anything else is depicted.

        Parameters
        ----------
        indices : iterable of int
            Rows to act on. Out-of-range entries are ignored rather than
            raising, because a tree built by one reader can outlive the
            coordinates set by another.
        hidden : bool
            True to hide them, False to show them again.
        object_id : str, optional
            Which object; the active one by default.
        """
        with self._activate_object(object_id):
            coords = self._all_atom_coords
            if coords is None:
                return
            n = int(np.asarray(coords).shape[0])
            if n == 0:
                return
            mask = self._hidden_mask
            if mask is None or len(mask) != n:
                mask = np.zeros(n, dtype=bool)
            else:
                mask = np.asarray(mask, dtype=bool).copy()
            idx = np.asarray(list(indices), dtype=int)
            idx = idx[(idx >= 0) & (idx < n)]
            if idx.size == 0:
                return
            mask[idx] = bool(hidden)
            self._hidden_mask = mask
        self._update_view()

    def _set_representations(
        self,
        n_rows: int,
        resolutions: np.ndarray | None,
        default_mask: np.ndarray | None,
    ) -> None:
        """Record which resolutions this object holds, and show the default one.

        Parameters
        ----------
        n_rows : int
            Rows of the coordinate array the masks must match.
        resolutions : numpy.ndarray or None
            Per-row resolution, or ``None`` for a single-representation file.
        default_mask : numpy.ndarray or None
            Per-row mask of the representation to show. Everything is shown when
            it is missing, which is the right answer for a file that offers one.
        """
        if resolutions is None:
            self._resolutions = None
            self._representation_mask = None
            self._rmf_resolutions = []
            return

        values = np.asarray(resolutions, dtype=float).ravel()
        if values.shape[0] != n_rows:
            logger.warning(
                "resolutions has %d entries for %d coordinates; ignoring them.",
                values.shape[0],
                n_rows,
            )
            self._resolutions = None
            self._representation_mask = None
            self._rmf_resolutions = []
            return

        self._resolutions = values
        # NaN is "the file did not say", and it is not a resolution anyone can
        # choose, so it must not appear in the chooser.
        self._rmf_resolutions = sorted(
            {float(v) for v in np.unique(values) if np.isfinite(v)}
        )

        if default_mask is not None and len(default_mask) == n_rows:
            self._representation_mask = np.asarray(default_mask, dtype=bool).copy()
        else:
            self._representation_mask = np.ones(n_rows, dtype=bool)

    def hierarchy_labels(
        self,
        node_type: str = "MOLECULE",
        *,
        object_id: str | None = None,
    ) -> np.ndarray | None:
        """One label per coordinate row, naming the node of *node_type* it is under.

        The tree already knows which rows belong to each node -- that is what
        makes it useful rather than decorative -- so this is the same knowledge
        the panel's check boxes use, read out per row. It is what lets colour be
        assigned by **molecule** rather than by chain: every copy of a
        nucleoporin then shares a colour, and the eight-fold symmetry of a pore
        appears as a repeating pattern instead of a mosaic of 544 unrelated
        hues.

        Parameters
        ----------
        node_type : str
            Which level to label by; one of
            :data:`~chisurf.plugins.chimol.chimol.io.hierarchy.NODE_TYPES`.
        object_id : str, optional
            Which object; the active one by default.

        Returns
        -------
        numpy.ndarray or None
            Labels of length ``n_rows``, or ``None`` when the object has no
            hierarchy or no node of that type. Rows under no such node get an
            empty string rather than being dropped, so the array always lines up
            with the coordinates.
        """
        with self._activate_object(object_id):
            root = self._rmf_hierarchy
            coords = self._all_atom_coords
            if root is None or coords is None:
                return None
            n_rows = int(np.asarray(coords).shape[0])
            if n_rows == 0:
                return None

            labels = np.full(n_rows, "", dtype=object)
            wanted = str(node_type).upper()
            found = False
            for node in [root, *root.descendants()]:
                if str(getattr(node, "node_type", "")).upper() != wanted:
                    continue
                rows = np.asarray(getattr(node, "atom_indices", ()), dtype=int)
                rows = rows[(rows >= 0) & (rows < n_rows)]
                if rows.size == 0:
                    continue
                found = True
                labels[rows] = str(getattr(node, "name", "") or "")
            return labels if found else None

    def available_resolutions(self, *, object_id: str | None = None) -> list[float]:
        """The resolutions this object holds, coarsest last.

        Parameters
        ----------
        object_id : str, optional
            Which object; the active one by default.

        Returns
        -------
        list of float
            Empty when the file states a single representation -- which is the
            signal to offer no choice at all rather than a choice of one.
        """
        with self._activate_object(object_id):
            return list(self._rmf_resolutions or [])

    def set_visible_resolutions(
        self,
        resolutions,
        *,
        object_id: str | None = None,
    ) -> int:
        """Choose which resolution(s) of a multi-resolution model are drawn.

        This is the *depiction*, not visibility: it never touches what the
        hierarchy panel switched off, and the two are combined when drawing. So
        switching from a coarse depiction to a fine one leaves a molecule you
        hid still hidden.

        Parameters
        ----------
        resolutions : iterable of float or None
            The resolutions to show. ``None`` shows every row the file holds,
            which superimposes the representations -- occasionally wanted for
            comparison, never a sensible default.
        object_id : str, optional
            Which object; the active one by default.

        Returns
        -------
        int
            How many rows the chosen representation covers. Zero means the
            request matched nothing and the previous choice was kept, rather
            than the model being silently emptied.
        """
        with self._activate_object(object_id):
            values = self._resolutions
            if values is None:
                return 0
            n_rows = int(np.asarray(values).shape[0])

            if resolutions is None:
                self._representation_mask = np.ones(n_rows, dtype=bool)
                self._update_view()
                return n_rows

            wanted = [float(v) for v in resolutions]
            mask = np.zeros(n_rows, dtype=bool)
            for value in wanted:
                mask |= np.isclose(values, value, rtol=0.0, atol=1e-9)
            if not mask.any():
                return 0

            self._representation_mask = mask
            self._update_view()
            return int(mask.sum())

    def visible_row_mask(self, n_rows: int) -> np.ndarray | None:
        """Which rows may be drawn: everything not hidden, in the chosen depiction.

        Three independent questions are answered here, and they have to be
        answered together. ``hidden_mask`` is what the hierarchy panel's check
        boxes set -- the parts of the model you switched off.
        ``representation_mask`` is which depiction of it is selected, when the
        file offers several resolutions. ``absent_mask`` is what does not exist
        in the frame being shown, which a simulation states by giving a particle
        no radius. Compose them in one place, or picking a resolution quietly
        un-hides what you had hidden, stepping the movie does the same, and
        every drawing path has to remember to consult all three.

        Parameters
        ----------
        n_rows : int
            Length the masks must have to apply to this array.

        Returns
        -------
        numpy.ndarray or None
            A boolean mask of rows that may be drawn, or ``None`` when
            everything is visible -- which lets callers skip the work entirely.
        """
        visible = None

        hidden = self._hidden_mask
        if hidden is not None and len(hidden) == n_rows:
            hidden_arr = np.asarray(hidden, dtype=bool)
            if hidden_arr.any():
                visible = ~hidden_arr

        chosen = self._representation_mask
        if chosen is not None and len(chosen) == n_rows:
            chosen_arr = np.asarray(chosen, dtype=bool)
            if not chosen_arr.all():
                visible = chosen_arr if visible is None else (visible & chosen_arr)

        absent = self._absent_mask
        if absent is not None and len(absent) == n_rows:
            absent_arr = np.asarray(absent, dtype=bool)
            if absent_arr.any():
                present = ~absent_arr
                visible = present if visible is None else (visible & present)

        return visible

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
        self._update_view()

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

    def handle_mouse_click(self, ev: QtGui.QMouseEvent, action: str | None = None) -> None:  # type: ignore[name-defined]
        """Handle a mouse-click in the GL view for atom picking.

        A left-click near an atom picks it and toggles its residue in and out
        of the selection -- PyMOL's ``+/-``, the single-left action of both the
        viewing and selecting modes. Clicking in empty space deactivates the
        selection, as PyMOL does ("left-clicking away from any atom should
        deactivate the selection" -- ``mouse:selecting``): with nothing picked
        there is nothing to toggle, so ``+/-`` and ``sele`` clear instead.
        Updates both atom and residue selection states.
        """
        atom_indices = []
        residue_indices = []
        mods = None
        # `_gl_enabled` was the gate here and **no code has ever set it**: the
        # `getattr` default made every click skip the whole picking block, on
        # top of the projection below raising. Two independent reasons the
        # viewport could not select anything. What actually has to hold is that
        # there is a widget able to project.
        if self._coords is not None and self.view is not None:
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
            # No atom picked. PyMOL's default left click is `+/-`, which toggles
            # the *picked* residue -- with nothing picked there is nothing to
            # toggle, and PyMOL deactivates the selection instead ("left-clicking
            # away from any atom should deactivate the selection"). `sele` (set)
            # on nothing is the same empty set. `pkat` is an editing pick that
            # highlights but never owns the selection, so it leaves it alone.
            if not residue_indices and not atom_indices:
                if action in ("+/-", "sele"):
                    try:
                        self._apply_selection_indices([], mods, mode="set")
                    except Exception:
                        pass
                try:
                    self.atomSelectionChanged.emit([])
                except Exception:
                    pass
                if action in ("+/-", "sele") and self._coords is not None:
                    try:
                        self._update_view()
                    except Exception:
                        pass
                return

        try:
            self.atomSelectionChanged.emit(atom_indices)
        except Exception:
            pass

        # `Orig` is not a selection at all: it moves the point the camera turns
        # about to the atom under the cursor, which is how PyMOL re-centres a
        # rotation without typing anything. The cell was in the block on screen
        # and wired to nothing, so ctrl-shift-middle silently did nothing.
        if action == "orig" and atom_indices:
            try:
                raw = self._atoms["xyz"][atom_indices[0]]
            except Exception:
                raw = None
            if raw is not None:
                try:
                    self.set_rotation_origin(np.asarray(raw, dtype=float))
                except Exception:
                    pass
            return

        # The action, not the modifier, carries the meaning -- PyMOL's cells:
        #   +/-   -- the clicked residue toggles in/out of the selection
        #   Sele  -- the clicked residue becomes the selection
        #   PkAt  -- editing pick: highlight only, the selection is untouched
        mode = {
            "sele": "set",
            "+/-": "toggle",
            "pkat": "pick",
            # A box action that was clicked rather than dragged is the same
            # operation on one atom -- see the release handler in `qtgl`.
            "+box": "add",
            "-box": "subtract",
        }.get(action, "toggle")
        try:
            # Redraws itself when the selection actually changed.
            self._apply_selection_indices(residue_indices, mods, mode=mode)
        except Exception:
            pass

    def _apply_selection_indices(self, indices, modifiers=None, mode=None) -> None:
        """Merge ``indices`` into the selection the way PyMOL's mouse does.

        PyMOL's selection mouse has four operations, named by the action codes
        in its mode matrix, and the whole point of matching it is that the
        modifier does not carry the meaning -- the *action* does:

        * ``+/-``      -- ``toggle``: the clicked atoms switch state.
        * ``+Box``     -- ``add``: the rectangle joins the selection.
        * ``-Box``     -- ``subtract``: the rectangle leaves the selection.
        * ``Sele``     -- ``set``: the rectangle becomes the selection.
        * ``PkAt``     -- ``pick``: like ``set``; editing-mode pick highlights.

        ``mode=None`` keeps the old single-click behaviour (a plain click
        replaces, ctrl toggles) for callers that predate the action wiring.
        """
        try:
            mods = modifiers
            ctrl = bool(mods & QtCore.Qt.ControlModifier) if mods is not None else False
        except Exception:
            ctrl = False

        try:
            idx_list = [int(i) for i in list(indices)]
        except Exception:
            idx_list = []

        current = set(
            int(i) for i in getattr(self, "_selected_residues", []) if int(i) >= 0
        )
        region = set(i for i in idx_list if i >= 0)

        if mode == "toggle":
            new_sel = sorted(current.symmetric_difference(region))
        elif mode == "add":
            new_sel = sorted(current | region)
        elif mode == "subtract":
            new_sel = sorted(current - region)
        elif idx_list:
            # mode is None (legacy) or "set"
            if ctrl:
                new_sel = sorted(current.symmetric_difference(region))
            else:
                new_sel = sorted(region)
        else:
            # An explicit "set" with nothing to select clears; a legacy call
            # with no indices clears too.
            new_sel = []

        previous = sorted(current)
        self._selected_residues = new_sel
        selection = list(self._selected_residues)
        try:
            self.residueSelectionChanged.emit(selection)
        except Exception:
            pass
        try:
            self.objectResidueSelectionChanged.emit(self.get_active_object_id(), selection)
        except Exception:
            pass
        # Redraw here, in the one place the selection changes, rather than at
        # each caller. `handle_mouse_click` did it and `handle_rect_selection`
        # did not, so a box select updated the sequence strip -- which is
        # repainted every frame -- while the molecule showed no markers at all
        # until something unrelated rebuilt the scene. A box that appears to
        # select nothing reads as a box select that does not work.
        #
        # The marker-only path, not `_update_view`: the same swap the sequence
        # strip has always used, 0.01 ms against 88 ms, and a box drag is as
        # much a per-mouse-move gesture as dragging over a sequence is.
        if new_sel != previous and self._coords is not None:
            try:
                self.refresh_selection_highlight()
            except Exception:
                pass


    def handle_rect_selection(self, rect, modifiers=None, action: str | None = None) -> None:
        """Select residues inside a screen rectangle, PyMOL-box style.

        The meaning is carried by the mouse *action*, not the modifier, exactly
        as in PyMOL's mode matrix:

        * ``Sele``/``set``  -- the rectangle becomes the selection.
        * ``+Box``/``add``  -- the rectangle joins the selection.
        * ``-Box``/``sub``  -- the rectangle leaves the selection.
        * ``+/-``/``toggle`` -- residues in the rectangle switch state.

        ``action=None`` keeps the legacy behaviour: the rectangle replaces.
        """
        if self._coords is None or self.view is None:
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

        mode = {
            "add": "add",
            "+box": "add",
            "subtract": "subtract",
            "-box": "subtract",
            "toggle": "toggle",
            "+/-": "toggle",
        }.get(str(action).lower() if action else None, "set")
        try:
            self._apply_selection_indices(indices, modifiers, mode=mode)
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
        """Set one object's selection from outside -- a sequence view, a script.

        Goes through the same merge as a click or a box does, because there is
        one selection and every view of it has to agree. This used to assign
        `_selected_residues` directly and refresh the marker, emitting nothing:
        a residue picked in the *sequence strip* therefore never reached the
        docked sequence list (or anything else listening), and the two
        sequence views showed different selections of the same molecule.
        """
        try:
            idx_iter = list(indices)
        except Exception:
            idx_iter = []

        with self._activate_object(object_id):
            coords = self._coords
            n = int(coords.shape[0]) if coords is not None else 0
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

            self._apply_selection_indices(idx_list, None, mode="set")

    @staticmethod
    def _is_selection_object(object_id: str) -> bool:
        """Whether a scene-object id is a selection marker, prefixed or not."""
        name = str(object_id)
        return name == "selection" or name.endswith(":selection")

    def refresh_selection_highlight(self) -> None:
        """Redraw the selection markers, not the whole scene.

        Selecting used to go through `_update_view`, which rebuilds every
        representation: 88 ms on a small protein, against 0.01 ms for the marker
        itself. Dragging a range over a sequence fires one of those per mouse
        move, so the selection lagged the cursor by a rebuild each step, and the
        cost had nothing to do with what changed.

        **Every object's marker, and matched by the same id the full rebuild
        gives it.** `_build_scene_for_current_object` prefixes every scene
        object with its object id, so the old `id != "selection"` filter matched
        nothing: the stale marker was never dropped and a fresh, *unprefixed*
        one was appended beside it. Deselecting therefore left the markers on
        screen, and a selection in a second molecule was drawn while the first
        one's ghost stayed -- the sequence and the view disagreeing, which is
        the one thing they may never do.
        """
        scene = getattr(self, "_scene", None)
        renderer = getattr(self, "_renderer", None)
        if scene is None or renderer is None:
            self._update_view()
            return

        fresh: list[SceneObject] = []
        for entry in self._objects.values():
            if not entry.visible:
                continue
            with self._activate_object(entry.object_id):
                coords = self._coords
                if coords is None:
                    continue
                marks = self._update_selection_highlight(
                    np.asarray(coords, dtype=float)
                ) or []
            for obj in marks:
                obj.id = f"{entry.object_id}:{obj.id}"
            fresh.extend(marks)

        objects = [
            obj for obj in scene.objects
            if not self._is_selection_object(getattr(obj, "id", ""))
        ]
        objects.extend(fresh)
        scene.objects = objects
        try:
            renderer.set_scene(scene)
        except Exception:
            self._update_view()
            return
        try:
            renderer.update()
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
            try:
                coords = self._ca_coords_2d()
            except Exception:
                return None
            if coords is None:
                return None
            n_points = int(coords.shape[0])
            if n_points <= 0:
                return None

            # The same colour computation the scene builder uses, and *only*
            # that. This used to call `_build_scene_for_current_object`, which
            # rebuilds every representation to recover one array -- and the
            # sequence strip asks for these colours once per object on every
            # frame, from inside `paintGL`. With a surface shown that meant a
            # density grid, marching cubes, gradients and ambient occlusion
            # sixty times a second.
            try:
                self._recompute_colors_per_ca(n_points)
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

    #: Metaball settings while scrubbing. The isosurface is sampled on a grid,
    #: so the cost falls with the **cube** of the resolution: 128 -> 96 is 42% of
    #: the voxels. The blob's shape survives -- an isosurface of fused Gaussians
    #: is smooth by construction and has no fine detail to lose at this step --
    #: while the shading skipped in draft is what actually dominated the build.
    _DRAFT_METABALL = {
        # 96 was chosen when the field was wide enough that the mesh cost little;
        # a tighter sigma follows the molecule, which is the point of it, and
        # costs more triangles to do so. At the shipped width 96 builds 148L at
        # 18.8 fps -- under the 20 the scrub path exists to hold -- and 80 builds
        # it at 29. The elongated trajectory molecule is cheaper either way (46
        # and 64 fps), so this is sized by the worst case, not the average.
        "max_dim": 80,
    }

    def _metaball_config(self, config: dict) -> dict:
        """The metaball settings to draw with, coarsened while scrubbing."""
        if not getattr(self, "_draft_quality", False):
            return config
        coarse = dict(config)
        coarse.update(self._DRAFT_METABALL)
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

    @contextmanager
    def suspend_updates(self):
        """Collapse every redraw inside the block into one at the end.

        A command that touches several things -- a frame, an overlay and a
        panel -- otherwise pays for a full scene rebuild per touch, and the
        first two are never seen. Counted, so nesting is safe, and the redraw
        still happens if the block raises: a half-drawn scene left behind
        because something failed is worse than the failure.
        """
        self._update_depth = getattr(self, "_update_depth", 0) + 1
        try:
            yield
        finally:
            self._update_depth -= 1
            if self._update_depth <= 0:
                self._update_depth = 0
                self._update_view()

    def begin_scrub(self) -> None:
        """Declare that redraws are about to arrive faster than anyone can look.

        :meth:`_note_frame_change` decides this from the *rate* of frame
        changes, which cannot help a caller whose own updates are slow because
        the bake is what makes them slow -- stepping a rotamer took a second,
        so no two steps ever arrived close enough together to count as
        scrubbing, and every one of them paid for an ambient-occlusion bake of
        a molecule that had not moved. A caller that knows it is scrubbing says
        so, and the same settle timer restores full quality when it stops.
        """
        self._draft_quality = True
        self._last_frame_change = time.perf_counter()
        try:
            timer = getattr(self, "_settle_timer", None)
            if timer is None:
                timer = QtCore.QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._bake_after_settling)
                self._settle_timer = timer
            timer.start(self._SETTLE_MS)
        except Exception:
            logger.debug("chimol: no settle timer available", exc_info=True)

    def _bake_after_settling(self) -> None:
        """Redraw at full quality once the frame has stopped changing."""
        if not getattr(self, "_draft_quality", False):
            return
        self._draft_quality = False
        self._last_frame_change = None
        try:
            self._update_view()
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

    def _per_vertex_occlusion_available(self) -> bool:
        """Whether the fine per-vertex bake will actually shade a mesh.

        Mirrors :meth:`_shade_by_occlusion`'s preconditions so a caller can ask,
        *before* a mesh exists, whether that mesh will come back shaded. The
        coarse per-residue estimate is the fallback for precisely this question
        and must not run alongside the fine bake, or the geometry darkens twice.

        Keeping the two in one place is the point: they were separate conditions
        that disagreed, which is how switching occlusion off became the only way
        to see any.

        Returns
        -------
        bool
            ``True`` when a call to :meth:`_shade_by_occlusion` would return a
            non-``None`` occlusion array.
        """
        if getattr(self, "_draft_quality", False):
            return False
        cfg = _DISPLAY_CONFIG.get("occlusion") or {}
        if not bool(cfg.get("enabled", True)):
            return False
        if float(cfg.get("darkness", 0.7)) <= 0.0:
            return False
        try:
            return self._occlusion_occluders() is not None
        except Exception:
            return False

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

        A mesh above :attr:`_OCCLUSION_SAMPLE_FLOOR` vertices is not baked in
        full. Every *stride*-th vertex is shaded and the rest are filled by
        nearest-sampled interpolation, because the occlusion field varies
        smoothly over a surface and a sphere mesh has far more vertices than
        smoothness demands. The bake's cost then follows the sampled count,
        which is also what is charged against
        :attr:`_OCCLUSION_VERTEX_BUDGET`.

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

        # The bake costs vertices times occluder neighbourhood, so a sphere mesh
        # for a protein of a few thousand atoms is over a million vertices and
        # tens of seconds of bake. The occlusion field varies smoothly along a
        # surface, so sampling every *stride*-th vertex and interpolating the
        # gaps loses almost nothing while cutting the cost by the stride.
        # ``None`` means the mesh is small enough to shade in full.
        n_verts = int(verts.shape[0])
        sample = None
        floor = int(self._OCCLUSION_SAMPLE_FLOOR)
        if n_verts > floor:
            stride = max(1, int(np.ceil(n_verts / float(floor))))
            sample = np.arange(0, n_verts, stride, dtype=int)
            verts_use = verts[sample]
            norms_use = norms[sample]
        else:
            verts_use = verts
            norms_use = norms

        if not self._occlusion_within_budget(verts_use.shape[0]):
            return cols, None

        scale = float(getattr(self, "_scale_factor", 1.0) or 1.0)
        try:
            occ = occlusion_from_spheres(
                verts_use,
                norms_use,
                centres,
                radii,
                max_distance=float(cfg.get("max_distance", 10.0)) * scale,
                strength=float(cfg.get("strength", 1.4)),
            )
        except Exception:
            logger.warning("Ambient occlusion failed; drawing unshaded",
                           exc_info=True)
            return cols, None
        if occ is None:
            return cols, None

        shadow = self._directional_shadow(
            verts_use, norms_use, centres, radii, cfg, scale
        )
        if sample is not None:
            occ = _expand_occlusion(occ, sample, n_verts)
            if shadow is not None:
                shadow = _expand_occlusion(shadow, sample, n_verts)

        if occ.shape[0] != cols.shape[0]:
            return cols, None

        shaded = np.array(cols, dtype=float, copy=True)
        shaded[:, :3] *= (1.0 - darkness * occ)[:, None]

        # Ambient occlusion says how *enclosed* a point is; a cast shadow says
        # whether anything stands between it and the light. They are different
        # cues and the second is what PyMOL's interactive view has no equivalent
        # of at all -- it casts shadows only when raytracing.
        if shadow is not None:
            shadow_darkness = float(cfg.get("shadow_darkness", 0.45))
            shaded[:, :3] *= (1.0 - shadow_darkness * shadow)[:, None]
            # Fold the shadow into the occlusion channel the backend damps its
            # non-surface lighting by, so a shadowed crevice does not get its
            # ambient and rim light back.
            occ = np.clip(occ + (1.0 - occ) * shadow, 0.0, 1.0)

        return np.clip(shaded, 0.0, 1.0), occ

    #: Vertices that may be shaded per object before baking is dropped. Baking
    #: is per *segment*, and cost grows with segments times occluders -- so on a
    #: model built of thousands of short chains it stops being the finishing
    #: touch and becomes the load time. Measured on one NPC spoke: 1608 segments,
    #: 24 seconds of a 33-second load, for shading nobody can see at that scale.
    #: Counts *sampled* vertices (see ``_shade_by_occlusion``), so a single large
    #: sphere mesh stays eligible while thousands of short segments still trip it.
    _OCCLUSION_VERTEX_BUDGET = 400_000

    #: Vertices above which the bake is sampled -- every *stride*-th vertex is
    #: shaded and the rest interpolated. A smooth occlusion field needs far fewer
    #: samples than a sphere mesh has vertices; this keeps a large mesh both
    #: within ``_OCCLUSION_VERTEX_BUDGET`` and quick to bake.
    _OCCLUSION_SAMPLE_FLOOR = 120_000

    def _occlusion_within_budget(self, vertex_count: int) -> bool:
        """Whether this object is small enough to be worth shading.

        Bounded by a setting rather than by the file, as the map voxel budget is.
        Reported once per object, because silently dropping a visual is how a
        renderer ends up with a look nobody can account for. ``vertex_count`` is
        the number of vertices that would actually be baked -- already sampled,
        for a mesh above ``_OCCLUSION_SAMPLE_FLOOR``.
        """
        try:
            per_segment = int(vertex_count)
        except Exception:
            return True
        total = int(getattr(self, "_occlusion_vertices_this_build", 0)) + per_segment
        self._occlusion_vertices_this_build = total
        if total <= self._OCCLUSION_VERTEX_BUDGET:
            return True
        if not getattr(self, "_occlusion_budget_reported", False):
            self._occlusion_budget_reported = True
            logger.info(
                "chimol: past %d shaded vertices; drawing without baked "
                "occlusion. It costs more than it shows on a model this large.",
                self._OCCLUSION_VERTEX_BUDGET,
            )
        return False

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
        # Which residues are nucleic is a fact about the residue *names*, so it
        # is the same in every frame of a trajectory -- but this walked all 570
        # of them in Python, with a str/strip/upper each, on every redraw.
        is_nuc_residue = np.zeros(n_points, dtype=bool)
        if self._residue_names is not None and len(self._residue_names) == n_points:
            try:
                names = np.asarray(self._residue_names)
                upper = np.char.upper(np.char.strip(names.astype(str)))
                is_nuc_residue = np.isin(upper, tuple(nucleic_names))
            except Exception:
                # A name array NumPy cannot coerce; fall back per residue rather
                # than treating everything as protein.
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
        # `cartoon_color` applies to the cartoon and to nothing else, so it is
        # read here rather than folded into `_colors_per_ca` -- that array is
        # shared with the trace, which PyMOL colours through `ribbon_color`.
        cartoon_override = self._representation_color("cartoon")
        if cartoon_override is not None:
            colors_for_tube = np.tile(cartoon_override, (n_points, 1))
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

        # The per-residue neighbour count here is superseded by the per-vertex
        # occlusion applied to the finished mesh, which is normal-aware and an
        # order of magnitude finer. Running both would darken the cartoon twice,
        # so this is a *fallback* -- it runs only when the fine bake will not.
        #
        # It was gated on `not enabled`, which made switching occlusion **off**
        # the only way to see any: the fine bake contributes nothing to a tube
        # cartoon, so the fallback was the sole source of shading and appeared
        # exactly when the user asked for none. Asking "is occlusion on, and is
        # the fine bake going to run?" gets both directions right, and keeps the
        # mutual exclusion the comment above is about.
        occ_ca = None
        if _occlusion_enabled() and not self._per_vertex_occlusion_available():
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

        # A scoped trace (``as trace, sele``) runs through only the selected
        # residues. The mask is residue-length, the same alignment as `coords`,
        # so the segment builder below sees a coherent subset.
        trace_mask = self._trace_mask
        if trace_mask is not None and len(trace_mask) == coords.shape[0]:
            keep = np.asarray(trace_mask, dtype=bool)
            if not keep.any():
                return scene_objects
            coords = coords[keep]
            if colors is not None and len(colors) == keep.shape[0]:
                colors = colors[keep]
            if res_ids is not None and len(res_ids) == keep.shape[0]:
                res_ids = res_ids[keep]
            if chain_ids is not None and len(chain_ids) == keep.shape[0]:
                chain_ids = chain_ids[keep]

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
    def scene_radius_for(points: np.ndarray, configured: float, fraction: float = 0.02) -> float:
        """Turn a radius written in Angstrom into one that means something here.

        Every neighbourhood radius in the display configuration -- the ambient
        occlusion radii, the surface-only cull, the shadow reach -- is written
        in Angstrom, and every one of them is then applied to **scaled scene
        coordinates**. On one spoke of the nuclear pore that is a 5 A
        neighbourhood inside a 6,000-unit model, and it fails twice over:

        * it selects nothing, so the work it guards is not skipped. The
          "surface only" cull kept **100%** of 29,273 beads -- it had never
          culled anything;
        * it is *slow*, because a cell list built at 5 units across a 6,000-unit
          model is millions of near-empty cells. That mask cost **2.0 s**; at a
          radius the model's own size it costs 0.03 s and keeps 3%.

        So the radius is the larger of what was configured and a fraction of the
        model's own extent. Configured values still win on a model small enough
        for them to mean what they say -- a protein a few tens of Angstrom
        across -- which is the case they were chosen for.

        Parameters
        ----------
        points : numpy.ndarray
            ``(N, 3)`` positions the neighbourhood will be searched over.
        configured : float
            The radius from the display configuration, in Angstrom.
        fraction : float
            Share of the model's spread to use as the floor.

        Returns
        -------
        float
            A radius in the same units as ``points``.
        """
        radius = float(configured)
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2 or pts.shape[0] < 2:
            return radius
        try:
            spread = float(
                np.percentile(np.linalg.norm(pts - pts.mean(axis=0), axis=1), 95)
            )
        except Exception:
            return radius
        if spread <= 0.0:
            return radius
        return max(radius, spread * float(fraction))

    @staticmethod
    def _shade_beads_by_crowding(
        pts: np.ndarray,
        rgb: np.ndarray,
        balls_cfg: dict,
    ) -> np.ndarray:
        """Darken crowded spheres, leaving exposed ones bright.

        The estimate counts neighbours within a radius rather than sampling a
        hemisphere: for a cloud of spheres that *is* the question, since a bead
        surrounded on all sides is buried whichever way its surface faces. It is
        also O(n) through a cell list, which matters at 234,184 beads.

        Baked into the colours rather than sent as a separate attribute, so it
        reaches every backend that draws the result -- the mesh path, the
        impostor path, and the ray tracer, which reads the same colours.

        Parameters
        ----------
        pts : numpy.ndarray
            ``(N, 3)`` sphere centres, in scene coordinates.
        rgb : numpy.ndarray
            ``(N, 3)`` colours to shade.
        balls_cfg : dict
            The ``balls`` section: ``ao_strength`` (0 disables), ``ao_radius``
            and ``ao_max_neighbors``.

        Returns
        -------
        numpy.ndarray
            The shaded colours, or ``rgb`` unchanged when occlusion is off or
            could not be computed.
        """
        strength = float(balls_cfg.get("ao_strength", 0.5))
        if strength <= 0.0 or pts.shape[0] < 2:
            return rgb

        # The scene is scaled, so a radius written in Angstrom has to be scaled
        # with it or the neighbourhood is the wrong size -- too small and every
        # bead reads as exposed, too large and the whole model darkens evenly.
        # Both failures look like "the occlusion does nothing".
        radius = float(balls_cfg.get("ao_radius", 4.0))
        try:
            spread = float(np.percentile(np.linalg.norm(pts - pts.mean(axis=0), axis=1), 95))
        except Exception:
            spread = 0.0
        if spread > 0.0:
            radius = max(radius, spread * float(balls_cfg.get("ao_radius_fraction", 0.02)))

        try:
            occ = _estimate_ambient_occlusion(
                pts,
                radius=radius,
                # The config key is `ao_max_neighbors`; reading `max_neighbors`
                # here found nothing and silently used the default forever.
                max_neighbors=int(balls_cfg.get("ao_max_neighbors", 24)),
            )
        except Exception:
            return rgb
        if occ is None:
            # Occlusion is switched off, or the estimate declined. Unshaded is
            # the right answer; `np.asarray(None)` is 0-d and the shape check
            # below would raise on it.
            return rgb
        occ = np.asarray(occ, dtype=float)
        if occ.shape[0] != pts.shape[0]:
            return rgb

        shade = (1.0 - strength) + strength * (1.0 - occ)
        return np.clip(rgb * shade.reshape(-1, 1), 0.0, 1.0)

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

    def _build_balls_mesh(
        self,
        pts: np.ndarray,
        colors_rgb: np.ndarray,
        radii: np.ndarray,
        *,
        occluders: str | None = None,
    ) -> SceneObject | None:
        """Merge per-atom spheres into a single ``atoms_mesh`` scene object.

        This was written twice -- once here and once inline in the scene builder,
        sixty lines of the same tessellation with its own duplicated guard. The
        copies had already diverged (only one baked occlusion), and a duplicated
        builder does not merely drift: it cannot *receive* what the other learns,
        so the sphere-centre record added for the ray tracer reached the copy
        nobody was calling. One builder now, with the bake as an argument.

        Parameters
        ----------
        pts : numpy.ndarray
            Atom centres of shape ``(N, 3)``, already centred and scaled.
        colors_rgb : numpy.ndarray
            Per-atom RGB colours of shape ``(N, 3)``.
        radii : numpy.ndarray
            Per-atom sphere radii of shape ``(N,)``.
        occluders : str, optional
            Bake ambient occlusion into the vertex colours against this occluder
            set (:meth:`_shade_by_occlusion`); ``None`` leaves them unshaded.
            Space-filling spheres shade against ``"atoms"``, because there the
            atoms *are* the picture rather than hidden bulk.

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
        occlusion = None
        if occluders is not None:
            vcols, occlusion = self._shade_by_occlusion(
                verts, norms, vcols, occluders=occluders
            )
        geom = Geometry(
            kind="mesh",
            positions=verts,
            indices=faces,
            normals=norms,
            colors=vcols,
            occlusion=occlusion,
            # The spheres this mesh *is*, carried alongside it. A rasteriser needs
            # the triangles; a ray tracer has an exact sphere primitive and is
            # far better off with the centres -- 1363 atoms of 148L take 0.3 s as
            # spheres against 114 s as their 210 240 triangles, for the same
            # picture, and the tessellation's facets besides. Recorded here rather
            # than rebuilt by the tracer from `get_atom_sphere_data`, because a
            # second source for "which atoms are drawn" is a second answer.
            meta={
                "spheres": {
                    "centers": np.asarray(pts, dtype=float),
                    "radii": np.asarray(radii, dtype=float),
                    "colors": rgba[:, :3],
                }
            },
        )
        return SceneObject(id="atoms_mesh", geometry=geom, render_mode="opaque")

    def _bead_scene_object(
        self,
        balls_cfg: dict,
        colors_per_ca: np.ndarray | None,
    ) -> SceneObject | None:
        """Draw an integrative model's beads, or return ``None`` if it is not one.

        Two depictions, chosen by count. Up to ``impostor_min_atoms`` beads the
        merged sphere mesh is used, which is what every other sphere in chimol
        is. Past it the beads are drawn as **sphere impostors**: one vertex each,
        shaded in the fragment shader as a sphere. That is not a degraded
        picture -- an impostor is a mathematically exact sphere where a
        tessellation is a polyhedron -- but it costs one vertex instead of the
        ~160 a mesh sphere costs. At 234,184 beads the difference is 234k
        vertices against 37 million, which is the difference between opening the
        eight-spoke nuclear pore and running the machine out of memory.

        Parameters
        ----------
        balls_cfg : dict
            The ``balls`` section of the display config.
        colors_per_ca : numpy.ndarray or None
            Per-residue RGBA colours. For a bead model one bead is one residue,
            so these are per-bead and need no residue lookup.

        Returns
        -------
        SceneObject or None
            The bead rows, or ``None`` when the object holds no beads (or none
            of them are selected).
        """
        atoms = self._atoms
        beads = _bead_mask(atoms)
        if beads is None or not beads.any():
            return None
        pts_all = self._all_atom_coords
        if pts_all is None:
            return None
        pts_all = np.asarray(pts_all, dtype=float)
        n_beads = pts_all.shape[0]
        if n_beads == 0 or beads.shape[0] != n_beads:
            return None

        # Only the bead rows, and only the selected ones. An entry that also
        # holds resolved atoms keeps them out of here: they are drawn by the
        # generic ball path, which knows about elements, waters and ligands.
        sel = beads.copy()
        mask = self._ball_mask
        if mask is not None and len(mask) == n_beads:
            sel &= np.asarray(mask, dtype=bool)
        visible = self.visible_row_mask(n_beads)
        if visible is not None:
            sel &= visible
        if not sel.any():
            return None

        pts = pts_all[sel]
        radii = self._all_atom_radii
        if radii is not None and len(radii) == n_beads:
            radii_sel = np.asarray(radii, dtype=float)[sel]
        else:
            radii_sel = np.full(
                pts.shape[0],
                max(self._radius * float(balls_cfg.get("size_scale", 0.04)),
                    float(balls_cfg.get("min_size", 3.0))),
                dtype=float,
            )
        radii_sel = radii_sel * float(balls_cfg.get("radius_multiplier", 1.0))
        bad = (~np.isfinite(radii_sel)) | (radii_sel <= 0.0)
        if bad.any():
            radii_sel[bad] = float(np.median(radii_sel[~bad])) if (~bad).any() else 1.0

        # One bead is one residue, so the per-residue colours are already
        # per-bead: no residue-id lookup, and no Python loop over 234k rows.
        rgb = np.tile(
            np.asarray(self._base_color_single, dtype=float)[:3], (pts.shape[0], 1)
        )
        if colors_per_ca is not None and len(colors_per_ca) == n_beads:
            rgb = np.asarray(colors_per_ca, dtype=float)[sel][:, :3]
        elif colors_per_ca is not None:
            # A model that also holds resolved atoms has more rows than trace
            # points, so the identity above does not hold. Each bead is still
            # exactly one trace point: take them in order.
            res_beads = self._residue_bead_mask(self._residue_names)
            if res_beads is not None and len(colors_per_ca) == res_beads.shape[0]:
                bead_res = np.nonzero(res_beads)[0]
                if bead_res.shape[0] == int(beads.sum()):
                    per_row = np.zeros(n_beads, dtype=int)
                    per_row[beads] = bead_res
                    rgb = np.asarray(colors_per_ca, dtype=float)[per_row[sel]][:, :3]
        override = getattr(self, "_colors_per_atom_override", None)
        if override is not None and len(override) == n_beads:
            ov = np.asarray(override, dtype=float)[sel]
            good = np.isfinite(ov).all(axis=1)
            rgb = rgb.copy()
            rgb[good] = ov[good, :3]
        rgb = np.clip(rgb, 0.0, 1.0)

        # Ambient occlusion, baked into the colours. Every other sphere path in
        # the viewer does this and the bead path did not, which is why an
        # integrative model came out as a flat sheet of coloured dots: with no
        # shadow, no specular separation between neighbours and no perspective
        # cue at this scale, *nothing* in the picture said which beads were in
        # front. A crowding estimate is the right one here -- a bead deep inside
        # the assembly has neighbours in every direction and darkens, one on the
        # outside stays bright -- and it costs one scalar per bead, so it works
        # for impostors exactly as it does for a mesh.
        rgb = self._shade_beads_by_crowding(pts, rgb, balls_cfg)

        impostor_min = int(balls_cfg.get("impostor_min_atoms", 20000))
        if impostor_min > 0 and pts.shape[0] >= impostor_min:
            rgba = np.ones((pts.shape[0], 4), dtype=float)
            rgba[:, :3] = rgb
            geom = Geometry(
                kind="points",
                positions=pts,
                colors=rgba,
                radii=radii_sel,
                meta={"glyph": "sphere", "world_radius": True},
            )
            return SceneObject(id="atoms_points", geometry=geom, render_mode="opaque")

        return self._build_balls_mesh(pts, rgb, radii_sel)

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

        # Beads get their own path: one row each, their own radius, and no atoms
        # underneath to fall back on. The generic path below would subsample
        # them to `max_atoms` -- for the nuclear pore, 8,000 of 234,184 beads
        # presented as the model. It draws only the bead rows, so an entry that
        # also holds resolved atoms falls through and has them drawn too.
        ball_mask = self._ball_mask
        # Rows switched off in the hierarchy panel are not drawn by anything.
        visible_rows = (
            self.visible_row_mask(len(ball_mask)) if ball_mask is not None else None
        )
        if visible_rows is not None:
            ball_mask = np.asarray(ball_mask, dtype=bool) & visible_rows
        beads = self._bead_scene_object(balls_cfg, colors_per_ca)
        if beads is not None:
            scene_objects.append(beads)
            if _is_bead_model(self._atoms):
                return scene_objects
            # A hybrid entry continues into the generic path for its resolved
            # atoms -- with the beads taken out of the mask, or they would be
            # drawn a second time as a merged mesh on top of their own
            # impostors.
            bead_rows = _bead_mask(self._atoms)
            if (
                bead_rows is not None
                and ball_mask is not None
                and len(ball_mask) == bead_rows.shape[0]
            ):
                ball_mask = np.asarray(ball_mask, dtype=bool) & ~bead_rows
                if not ball_mask.any():
                    return scene_objects

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
                ball_mask is not None
                and len(ball_mask) == pts.shape[0]
                and ball_mask.any()
            ):
                sel = np.asarray(ball_mask, dtype=bool)
                pts = pts[sel]
                colors_rgb = colors_rgb[sel]
                radii = radii[sel]
            # Hiding is not a property of the bead path: a raw-coordinate object
            # has a hierarchy too whenever its reader built one, and its check
            # boxes have to move something here as well.
            visible = self.visible_row_mask(pts.shape[0])
            if visible is not None:
                pts = pts[visible]
                colors_rgb = colors_rgb[visible]
                radii = radii[visible]
                if pts.shape[0] == 0:
                    return scene_objects
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
            ball_mask is not None
            and len(ball_mask) in (n_points, n_all_atoms)
            and ball_mask.any()
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

                if ball_mask is not None and len(ball_mask) == n_atoms_total:
                    # Per-atom mask
                    atom_mask = ball_mask.astype(bool)
                elif ball_mask is not None and len(ball_mask) == n_points:
                    # Legacy: residue-level mask
                    sel_idx = np.nonzero(ball_mask)[0]
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

                    # One merged mesh for every ball in the selection: far
                    # cheaper than a mesh item per atom, and shaded like a real
                    # sphere. Built by the shared helper -- this was a second,
                    # inline copy of it.
                    colors_rgb_balls = np.asarray(colors, dtype=float)[:, :3] \
                        if colors is not None else None
                    if colors_rgb_balls is None or colors_rgb_balls.shape[0] != pts.shape[0]:
                        colors_rgb_balls = np.tile(self._base_color_single, (pts.shape[0], 1))
                    ball_obj = self._build_balls_mesh(
                        pts, colors_rgb_balls, radii_for_mesh, occluders="atoms",
                    )
                    if ball_obj is not None:
                        scene_objects.append(ball_obj)
                        used_all_atoms_for_balls = True

        if self._show_atoms and not used_all_atoms_for_balls:
            sphere_radius = max(self._radius * balls_size_scale * 0.5, balls_min_size * 0.1)
            sphere = _build_sphere_mesh(radius=sphere_radius)
            if (
                ball_mask is not None
                and len(ball_mask) == n_points
                and ball_mask.any()
            ):
                indices = np.nonzero(ball_mask)[0]
            else:
                # Default: sparse sampling along the chain
                step = max(1, n_points // 50)
                indices = np.arange(0, n_points, step, dtype=int)

            point_positions: list[np.ndarray] = []
            point_colors: list[np.ndarray] = []

            # `color` writes a per-atom override, and this path drew from
            # `colors_per_ca` alone -- so every object that lands here (anything
            # `create` copied out, which has no residue table and therefore
            # cannot take the merged-mesh branch above) ignored `color`
            # completely and stayed its default colour. It reported success, so
            # the only symptom was a molecule that would not change.
            override = getattr(self, "_colors_per_atom_override", None)
            if override is not None:
                override = np.asarray(override, dtype=float)
                if override.ndim != 2 or override.shape[0] != len(coords):
                    override = None

            for i in indices:
                center = coords[i]
                color = (
                    colors_per_ca[i]
                    if colors_per_ca is not None
                    else self._base_color_single
                )
                if override is not None and np.isfinite(override[i]).all():
                    color = override[i]
                color_local = np.array(color, dtype=float)
                color_local[3] = 1.0
                point_positions.append(center)
                point_colors.append(color_local)

            if point_positions:
                radii_vals = None
                sizes = self._all_atom_radii
                # The radii cover the *coordinates*, and `indices` selects into
                # them. Comparing the array against the length of the selection
                # only held when everything was selected, so any narrower
                # selection silently lost the per-bead sizes and drew one size
                # for all of them.
                if sizes is not None and len(sizes) == n_points:
                    radii_vals = np.asarray(sizes, dtype=float)[indices]

                geom = Geometry(
                    kind="points",
                    positions=np.asarray(point_positions, dtype=float),
                    colors=np.asarray(point_colors, dtype=float),
                    radii=radii_vals,
                    # `set_coordinates` has already multiplied these by
                    # `_scale_factor`, so they are distances in the scene, not
                    # pixel counts. Without saying so a 20 A bead was drawn as a
                    # 200-pixel dot that did not change when you zoomed.
                    meta={
                        "glyph": "sphere",
                        "radius": sphere_radius,
                        "world_radius": radii_vals is not None,
                    },
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

        # ...and then only the rows that are visible at all. A representation
        # mask says *how* a row would be drawn; this says whether it is drawn.
        # Without it `ray` traced molecules switched off in the hierarchy panel
        # and every resolution of a multi-resolution model at once, so the
        # traced image disagreed with the picture on screen -- silently, since
        # both are pictures of the same thing.
        visible = self.visible_row_mask(n_atoms)
        if visible is not None:
            mask &= visible
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
        """Show a traced image in place of the live scene.

        Parameters
        ----------
        image:
            Rendered image to display.

        Returns
        -------
        bool
            ``True`` when the image was shown.

        Notes
        -----
        The renderer draws it *inside* its paint pass, under the chrome. This
        was a ``QLabel`` laid over the viewport, and that is what took PyMOL's
        object panel off the screen after every `ray`: the panel is drawn in
        the viewport, not beside it, so a widget over the scene covers the
        A/S/H/L/C menus, the mouse-mode block and the sequence strip -- and the
        panel is the only way to switch a representation back on. The chrome
        should be missing from the *file*, which it is, and never from the
        window.
        """
        renderer = getattr(self, "_renderer", None)
        show = getattr(renderer, "show_ray_image", None)
        if not callable(show):
            return False
        return bool(show(image))

    def hide_ray_overlay(self) -> None:
        """Go back to the live scene if a traced image is showing."""
        renderer = getattr(self, "_renderer", None)
        clear = getattr(renderer, "clear_ray_image", None)
        if callable(clear):
            clear()

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

        n_atoms = self._all_atom_coords.shape[0]
        # A scoped ``labels`` (``show labels, sele``) draws only the labels of
        # the masked atoms. ``None`` means no scoping -- every label.
        label_mask = self._label_mask
        if label_mask is not None:
            lm = np.asarray(label_mask, dtype=bool)
            if len(lm) == n_atoms:
                labels = {
                    idx: text for idx, text in labels.items() if lm[int(idx)]
                }
        if not labels:
            return []

        cfg = _DISPLAY_CONFIG.get("label", {})
        colour = np.asarray(
            cfg.get("color", [1.0, 1.0, 1.0, 1.0]), dtype=float
        ).reshape(1, 4)

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
        # A scoped ``lines`` (``show lines, sele``) draws only the bonds of the
        # masked atoms. ``None`` means no scoping -- every bond. This used to
        # read ``sticks_mask``, which coupled the two representations: hiding
        # lines in a selection also hid sticks there, and ``hide everything,
        # sele`` through the lines slot could light the sticks flag up.
        lines_mask = self._lines_mask
        if bonds.size and lines_mask is not None:
            n_atoms = self._all_atom_coords.shape[0]
            lm = np.asarray(lines_mask, dtype=bool)
            if len(lm) == n_atoms and lm.any():
                keep = lm[bonds[:, 0]] & lm[bonds[:, 1]]
                bonds = bonds[keep]

        bonds = self._apply_side_chain_helper(bonds)

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
        # A scoped ``nonbonded`` (``show nonbonded, sele``) draws crosses only
        # on the masked atoms. ``None`` means no scoping -- every unbonded atom.
        nonbonded_mask = self._nonbonded_mask
        if nonbonded_mask is not None:
            nm = np.asarray(nonbonded_mask, dtype=bool)
            if len(nm) == mask.shape[0]:
                mask = mask & nm
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

    def _cartoon_atom_mask(self) -> np.ndarray | None:
        """Whether a cartoon is drawn over each atom.

        chimol's cartoon visibility is a flag plus a *per-residue* mask, so it
        has to be expanded through the atoms' residue ids before it can be asked
        about an atom -- which is the domain PyMOL's ``visRep`` answers in.
        """
        coords = self._all_atom_coords
        if coords is None:
            return None
        n_atoms = int(np.asarray(coords).shape[0])
        if not self._show_cartoon:
            return np.zeros(n_atoms, dtype=bool)

        mask = getattr(self, "_cartoon_mask", None)
        res_ids = self._residue_ids
        atom_res = self._all_atom_res_ids
        if mask is None or res_ids is None or atom_res is None:
            return np.ones(n_atoms, dtype=bool)
        mask = np.asarray(mask, dtype=bool)
        res_ids = np.asarray(res_ids)
        atom_res = np.asarray(atom_res)
        if mask.shape[0] != res_ids.shape[0] or atom_res.shape[0] != n_atoms:
            return np.ones(n_atoms, dtype=bool)
        return np.isin(atom_res, res_ids[mask])

    def _apply_side_chain_helper(self, bonds: np.ndarray) -> np.ndarray:
        """Drop the backbone bonds ``cartoon_side_chain_helper`` hides.

        A no-op when the setting is off, which is PyMOL's default. See
        :mod:`chimol.analysis.side_chain_helper` for the rule and why it is a
        bond filter rather than an atom filter.
        """
        if bonds.size == 0:
            return bonds
        cartoon_cfg = _DISPLAY_CONFIG.get("cartoon", {})
        if not bool(cartoon_cfg.get("side_chain_helper", False)):
            return bonds
        atoms = self._atoms
        if atoms is None:
            return bonds
        cartoon = self._cartoon_atom_mask()
        if cartoon is None or not cartoon.any():
            return bonds
        try:
            classes = classify_atoms(atoms)
            polymer = np.asarray(classes.polymer, dtype=bool)
        except Exception:
            return bonds
        if polymer.shape[0] != cartoon.shape[0]:
            return bonds
        hidden = hidden_backbone_bonds(atoms, bonds, cartoon, polymer)
        return bonds[~hidden]

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

            bonds = self._apply_side_chain_helper(bonds)

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

                # `stick_color` wins over all of it, which is what a
                # per-representation override means: PyMOL takes the atom's
                # colour only when the setting is its "default" sentinel.
                stick_override = self._representation_color("stick")
                if stick_override is not None:
                    atom_colors[:, :] = stick_override

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

    def _update_cell(self, state: _MolViewObjectState) -> list[SceneObject] | None:
        """The unit cell as a wireframe box, when the object has one and it is on.

        PyMOL draws the cell as its twelve edges, which is what makes a
        crystallographic view legible: the mates `symexp` generates are
        meaningless without the box they tile. The geometry is not transcribed
        from anywhere -- a cell is fully determined by its six parameters, and
        `UnitCell.frac_to_real` already turns fractional coordinates into
        Cartesian ones, so the box is that matrix applied to the eight corners
        of the unit cube.

        Parameters
        ----------
        state : _MolViewObjectState
            The object; drawn only when it carries ``symmetry`` and
            ``show_cell``.

        Returns
        -------
        list of SceneObject or None
            One line object, or ``None`` when there is no cell to draw.

        Notes
        -----
        Placed in the object's own render frame: everything is drawn centred on
        the object's centroid and scaled, so a box built in Angstrom around the
        origin would sit somewhere else entirely. The corners go through the
        same transform the coordinates did.
        """
        if not getattr(state, "show_cell", False):
            return None
        symmetry = getattr(state, "symmetry", None) or {}
        cell = symmetry.get("cell")
        if cell is None:
            return None
        try:
            basis = np.asarray(cell.frac_to_real(), dtype=float)
        except Exception:
            return None
        if basis.shape != (3, 3) or not np.isfinite(basis).all():
            return None

        corners = np.array(
            [[x, y, z] for x in (0.0, 1.0) for y in (0.0, 1.0) for z in (0.0, 1.0)],
            dtype=float,
        ) @ basis.T
        # The twelve edges of a parallelepiped: every pair of corners differing
        # in exactly one fractional coordinate.
        keys = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
        edges = [
            (i, j)
            for i, a in enumerate(keys)
            for j, b in enumerate(keys)
            if i < j and sum(int(p != q) for p, q in zip(a, b)) == 1
        ]
        segments = np.empty((len(edges) * 2, 3), dtype=float)
        for n, (i, j) in enumerate(edges):
            segments[2 * n] = corners[i]
            segments[2 * n + 1] = corners[j]

        centre = getattr(state, "raw_center", None)
        if centre is not None:
            segments = segments - np.asarray(centre, dtype=float)
        segments = segments * float(self._scale_factor)

        colour = self._representation_color("cell")
        if colour is None:
            colour = np.array([0.6, 0.6, 0.6, 1.0], dtype=float)
        geom = Geometry(
            kind="line",
            positions=segments.astype(np.float32),
            colors=np.tile(colour, (segments.shape[0], 1)).astype(np.float32),
        )
        return [SceneObject(id="cell", geometry=geom, render_mode="opaque")]

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

        # Computed once. This was evaluated twice with identical arguments --
        # here, and again below to index the colours -- and it was the single
        # most expensive thing in the whole representation: 2.7 s of a 4.0 s
        # build, for a result that was already in hand.
        surf_mask = None
        if surface_only and n_all > surface_max_neighbors:
            surf_mask = _get_surface_atom_mask(
                pts_all,
                radius=self.scene_radius_for(pts_all, surface_radius),
                max_neighbors=surface_max_neighbors,
            )
            if not surf_mask.any():
                surf_mask = None

        # A scoped ``metaball`` (``show metaball, sele``) builds the blob from
        # the masked atoms only, so the iso field is *driven by* the selection.
        # ``None`` means no scoping -- every atom. Combined with the surface
        # mask (when ``surface_only``) so the two keep the same indexing into
        # the per-atom colours below.
        metaball_mask = self._metaball_mask
        if metaball_mask is not None:
            mm = np.asarray(metaball_mask, dtype=bool)
            if len(mm) == n_all:
                surf_mask = mm if surf_mask is None else (surf_mask & mm)
                if not surf_mask.any():
                    return None

        if surf_mask is not None:
            pts_surface = pts_all[surf_mask]
            sigmas = sigmas_all[surf_mask]
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

        # The same mask as above, not a second computation of it.
        if surf_mask is not None:
            surf_indices = np.where(surf_mask)[0]
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

        # While the frame is being scrubbed, the per-vertex transfer from atoms
        # is the whole cost of a rebuild -- and it is spent on a picture that is
        # replaced before anyone can look at it. Draft keeps the geometry, which
        # is what actually moves, and takes its colour and normals from the
        # isosurface itself. The settle timer bakes the good version as soon as
        # the frame stops changing, so what you end up *looking* at is never the
        # draft. This is the same trade the cartoon makes; see
        # `_note_frame_change`.
        # Draft is only available when one flat colour is the *truth*. Averaging
        # the atom colours was the first attempt and it is wrong for anything
        # coloured per atom: the mean of a spectrum is **grey**, so a rainbow
        # trajectory went grey the moment it started playing and came back on
        # settle. A uniformly coloured model loses nothing to a flat colour, so
        # it keeps the fast path; a spectrum-coloured one pays for the transfer
        # that spreads its colours over the surface, because that transfer *is*
        # the picture.
        draft = getattr(self, "_draft_quality", False)
        if draft and len(atom_colors):
            colours = np.asarray(atom_colors, dtype=float)
            spread = float(np.abs(colours[:, :3] - colours[0, :3]).max())
            draft = spread <= 1e-6
        if draft:
            draft_color = (
                np.asarray(atom_colors, dtype=float)[0]
                if len(atom_colors)
                else base_color
            )
            mesh_colors = np.tile(draft_color, (verts.shape[0], 1))
            mesh_colors[:, 3] = alpha if alpha < 1.0 else 1.0
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
                render_mode="transparent" if alpha < 1.0 else "opaque",
                material=material,
            )]

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

            # `shade_from_atoms` accumulates ``(vertex - atom) * w``, which is
            # **minus** the density gradient -- so it already points away from
            # the matter, i.e. outward. Negating it turned two thirds of the
            # normals inward (measured: 35% outward, mean dot -0.22 against the
            # outward direction), and a surface lit from inside its own volume
            # renders nearly black. The surface builder, which uses the same
            # helper, had the sign right; these two disagreed.
            # The isosurface's own normals are sampled from the density field
            # at the vertex; these are a Gaussian-weighted average over a cutoff
            # of several bead radii, which is far smoother. Smoother is not
            # better here: it airbrushes the surface into a soft glow and no
            # specular highlight survives it, which is why a metaball never
            # looked wet. `metaball.normals` chooses; the isosurface wins by
            # default.
            if str(cfg.get("normals", "isosurface")).lower() != "isosurface":
                mag = np.linalg.norm(grad_sum, axis=1, keepdims=True)
                good = mag[:, 0] > 1e-6
                new_norms = norms.copy()
                new_norms[good] = grad_sum[good] / mag[good]
                norms = new_norms

            if ao_strength > 0:
                occ = _estimate_ambient_occlusion(
                    verts,
                    radius=self.scene_radius_for(verts, ao_radius),
                    max_neighbors=32,
                )
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

        # A scoped ``surface`` (``show surface, sele``) builds the surface from
        # the masked atoms only. ``None`` means no scoping -- all atoms. The
        # per-atom colour/radius inputs are filtered to match, so the positions
        # stay aligned with their res ids and overrides downstream.
        surface_mask = self._surface_mask
        res_ids_surface = self._all_atom_res_ids
        radii_surface = self._all_atom_radii
        override_surface = getattr(self, "_colors_per_atom_override", None)
        if surface_mask is not None:
            sm = np.asarray(surface_mask, dtype=bool)
            if len(sm) == n_pts:
                pts_surface = pts_surface[sm]
                if res_ids_surface is not None and len(res_ids_surface) == len(sm):
                    res_ids_surface = res_ids_surface[sm]
                if radii_surface is not None and len(radii_surface) == len(sm):
                    radii_surface = radii_surface[sm]
                if override_surface is not None and len(override_surface) == len(sm):
                    override_surface = np.asarray(override_surface)[sm]
                if pts_surface.size == 0:
                    return None
                n_pts = pts_surface.shape[0]

        # --- Try mesh surface via Gaussian density + marching cubes ---
        # The spacing is an *Angstrom* quantity and `pts_surface` is in scene
        # units, which are Angstrom times `_scale_factor` (10). Passing the
        # configured number straight through asked for a grid ten times finer
        # than it says -- 0.08 A rather than 0.8 -- and `max_dim` then clamped it
        # back, which is why the spacing had no measurable effect at all and the
        # cap was doing the whole job. The volume path already converts
        # (`add_volume`); this one did not.
        scene_scale = float(getattr(self, "_scale_factor", 1.0) or 1.0)
        grid_spacing = float(surface_cfg.get("grid_spacing", 0.8)) * scene_scale
        iso_value = float(surface_cfg.get("iso_value", 0.5))
        padding = float(surface_cfg.get("padding", 3.0))
        max_dim = _surface_grid_cap(
            pts_surface, grid_spacing, padding,
            int(surface_cfg.get("max_dim", 96)),
        )
        mesh_sigma_factor = float(surface_cfg.get("mesh_sigma_factor", 1.0))
        # Scene units, like the coordinates and the per-atom radii it stands in
        # for. Written as an Angstrom vdW radius (1.8) and used unscaled, this
        # fallback made a blob a tenth the size it should be -- reachable by any
        # object whose atom array carries no `radius` field, where the surface
        # would come out as spikes rather than an envelope. The real radii are
        # already scaled (measured: 15-20 for a protein, i.e. 1.5-2.0 A x 10),
        # so the stand-in has to be too.
        mesh_sigma_default = (
            float(surface_cfg.get("mesh_sigma_default", 1.8)) * scene_scale
        )
        # `probe_radius` is an Angstrom quantity for the same reason.
        probe_radius_scene = (
            float(surface_cfg.get("probe_radius", 1.4)) * scene_scale
        )

        method = str(surface_cfg.get("method", "gaussian")).lower()

        if method in ("sas", "ses"):
            if radii_surface is not None and radii_surface.shape[0] == n_pts:
                atom_radii = np.asarray(radii_surface, dtype=float)
            else:
                atom_radii = np.full(n_pts, mesh_sigma_default, dtype=float)

            mesh_data = _generate_surface_mesh_edt(
                pts_surface,
                atom_radii,
                method=method,
                probe_radius=probe_radius_scene,
                grid_spacing=grid_spacing,
                padding=padding,
                max_dim=max_dim,
            )
            mesh_sigmas = atom_radii
        else:
            if radii_surface is not None and radii_surface.shape[0] == n_pts:
                sigmas = np.asarray(radii_surface, dtype=float) * mesh_sigma_factor
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
                res_ids=res_ids_surface, override=override_surface,
            )

        # --- Fallback: point-cloud surface ---
        surface_size_scale = float(surface_cfg.get("size_scale", 0.03))
        surface_min_size = float(surface_cfg.get("min_size", 2.5))
        surface_ao_max = int(surface_cfg.get("max_neighbors", 24))
        surface_max_points = int(surface_cfg.get("max_points", 10000))
        surface_color_mode = str(surface_cfg.get("color_mode", "ao_gray")).lower()

        colors_surface = self._build_surface_atom_colors(
            pts_surface, surface_cfg, colors_per_ca, surface_base_color,
            res_ids=res_ids_surface, override=override_surface,
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
        res_ids: np.ndarray | None = None,
        override: np.ndarray | None = None,
    ) -> np.ndarray | None:
        """Build per-atom/point colors for the surface representation.

        ``res_ids``/``override`` default to the object's own arrays and are
        threaded in by ``_update_surface`` so a scoped surface (``show surface,
        sele``) colours the filtered atom set correctly.
        """
        surface_color_mode = str(surface_cfg.get("color_mode", "ao_gray")).lower()
        n_pts = pts_surface.shape[0]
        res_ids = self._all_atom_res_ids if res_ids is None else res_ids
        if override is None:
            override = getattr(self, "_colors_per_atom_override", None)

        if (
            surface_color_mode == "by_residue"
            and res_ids is not None
            and self._residue_ids is not None
            and colors_per_ca is not None
            and len(colors_per_ca) == len(self._residue_ids)
        ):
            color_map = {rid: colors_per_ca[i_res] for i_res, rid in enumerate(self._residue_ids)}
            colors = np.zeros((n_pts, 4), dtype=float)
            for i_atom, rid in enumerate(res_ids[:n_pts]):
                colors[i_atom, :] = color_map.get(rid, self._base_color_single)
        else:
            colors = np.tile(surface_base_color, (n_pts, 1))

        if (
            override is not None
            and res_ids is not None
            and len(override) == res_ids.shape[0]
        ):
            ov = np.asarray(override, dtype=float)
            for i_atom in range(min(colors.shape[0], ov.shape[0])):
                col_ov = ov[i_atom]
                if np.isfinite(col_ov).all():
                    colors[i_atom, :] = col_ov

        surface_override = self._representation_color("surface")
        if surface_override is not None:
            colors[:, :] = surface_override

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
        res_ids: np.ndarray | None = None,
        override: np.ndarray | None = None,
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
            res_ids=res_ids, override=override,
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
                occ = _estimate_ambient_occlusion(
                    verts,
                    radius=self.scene_radius_for(verts, surface_ao_radius),
                    max_neighbors=32,
                )
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
            # PyMOL's `two_sided_lighting`, and it only matters once you can see
            # through the surface: a back face has its normal pointing away, so
            # the inside of the shell comes out unlit black without it. That is
            # why PyMOL's own ligand-site preset turns it on in the same breath
            # as the transparency.
            meta={"two_sided": bool(surface_cfg.get("two_sided", False))},
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

        # A scoped ``dots`` (``show dots, sele``) draws dots on the masked
        # atoms only. ``None`` means no scoping -- all atoms.
        dots_mask = self._dots_mask
        if dots_mask is not None:
            dm = np.asarray(dots_mask, dtype=bool)
            if len(dm) == positions.shape[0]:
                positions = positions[dm]
                if colors_local is not None and len(colors_local) == len(dm):
                    colors_local = colors_local[dm]
                if positions.size == 0:
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

    def _scene_dash_length(self) -> float:
        """``dash_length`` in scene units.

        The setting is in Angstrom and the scene is the molecule scaled about
        its centre, so the dash has to be scaled with it or a large structure
        gets a solid line and a small one gets dust.
        """
        cfg = _DISPLAY_CONFIG.get("dash", {}) or {}
        return float(cfg.get("length", 0.15)) * float(
            getattr(self, "_scale_factor", 1.0) or 1.0
        )

    def _scene_dash_gap(self) -> float:
        """``dash_gap`` in scene units; see :meth:`_scene_dash_length`."""
        cfg = _DISPLAY_CONFIG.get("dash", {}) or {}
        return float(cfg.get("gap", 0.45)) * float(
            getattr(self, "_scale_factor", 1.0) or 1.0
        )

    def _dash_width(self) -> float:
        """``dash_width`` in pixels.

        Unlike the dash *length*, this is not scaled: a line width is a screen
        property, not a molecular one.
        """
        cfg = _DISPLAY_CONFIG.get("dash", {}) or {}
        return float(cfg.get("width", 2.5))

    def _update_measurements(self) -> list[SceneObject]:
        measurements = getattr(self, "_measurements", None)
        if not measurements:
            return []

        scene_objects = []
        for mid, mdata in measurements.items():
            kind = mdata.get("kind", "distance")
            coords = np.asarray(mdata.get("positions", []), dtype=float)
            if coords.size == 0:
                continue

            if mdata.get("transform_to_scene", True):
                coords = self._transform_world_coords_to_scene(coords)

            color = np.asarray(mdata.get("color", [1.0, 1.0, 1.0, 1.0]), dtype=float)
            label = str(mdata.get("label", ""))

            if kind == "contacts" and coords.shape[0] >= 2:
                # A bump check: solid segments, one colour *per segment*, from
                # green where the contact is comfortable to red where the two
                # atoms are inside each other. Not dashed -- PyMOL's
                # `sculpt_vdw_vis` draws a solid line (mode 2) or a cylinder
                # (mode 1), and a dashed one would read as a measurement.
                pairs = coords[: (coords.shape[0] // 2) * 2]
                per_vertex = mdata.get("colors")
                if per_vertex is None:
                    colours = np.tile(color, (pairs.shape[0], 1))
                else:
                    colours = np.asarray(per_vertex, dtype=float)[: pairs.shape[0]]
                line_geom = Geometry(
                    kind="line", positions=pairs, colors=colours,
                    meta={"width": float(mdata.get("width", 2.0))},
                )
                scene_objects.append(SceneObject(
                    id=f"meas_line_{mid}", geometry=line_geom, render_mode="overlay"
                ))
                continue

            if kind in ("distance", "dashes") and coords.shape[0] >= 2:
                 # PyMOL draws a measurement dashed, and a polar-contact object
                 # holds many segments at once, so both go through the same
                 # path: an even number of points read as consecutive pairs.
                 pairs = coords[: (coords.shape[0] // 2) * 2].reshape(-1, 2, 3)
                 dashes = _dash_segments(pairs, self._scene_dash_length(),
                                         self._scene_dash_gap())
                 if dashes.size:
                     line_geom = Geometry(kind="line", positions=dashes,
                                          colors=np.tile(color, (dashes.shape[0], 1)),
                                          meta={"width": self._dash_width()})
                     scene_objects.append(SceneObject(id=f"meas_line_{mid}", geometry=line_geom, render_mode="overlay"))

                 # One label per segment, at its midpoint. `label=0` on the
                 # command leaves the list empty, which is how PyMOL's presets
                 # draw a hundred contacts without a hundred numbers over them.
                 labels = mdata.get("labels")
                 if labels is None:
                     labels = [label] if label else []
                 if labels:
                     mids = pairs.mean(axis=1)[: len(labels)]
                     label_geom = Geometry(
                         kind="text", positions=mids,
                         colors=np.tile(color, (mids.shape[0], 1)),
                         meta={"labels": [str(t) for t in labels[: mids.shape[0]]]},
                     )
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

    def _selection_atom_positions(self, coords: np.ndarray) -> np.ndarray | None:
        """Where the selection indicators go: every atom of every selected residue.

        PyMOL marks **atoms** (``ObjectMoleculeRenderSele`` walks the object's
        atom table), not one point per residue. The difference is what makes a
        selection read as a region of the molecule rather than a sprinkle of
        dots along the backbone -- a selected residue is a dozen markers
        clustered on it, which is visible against a cartoon at a glance.

        Falls back to the per-residue positions when the object carries no atom
        table (a bead model, a trajectory read as coordinates only).
        """
        sel = getattr(self, "_selected_residues", None)
        if not sel or coords is None or not len(coords):
            return None
        try:
            idx_sel = np.asarray(list(sel), dtype=int)
        except Exception:
            return None
        n = len(coords)
        idx_sel = idx_sel[(idx_sel >= 0) & (idx_sel < n)]
        if not idx_sel.size:
            return None

        atom_xyz = getattr(self, "_all_atom_coords", None)
        atom_res = getattr(self, "_all_atom_res_ids", None)
        res_ids = getattr(self, "_residue_ids", None)
        if atom_xyz is not None and atom_res is not None and res_ids is not None:
            try:
                wanted = np.asarray(res_ids, dtype=int)[idx_sel]
                mask = np.isin(np.asarray(atom_res, dtype=int), wanted)
                if mask.any():
                    return np.asarray(atom_xyz, dtype=float)[mask]
            except Exception:
                pass
        try:
            return np.asarray(coords, dtype=float)[idx_sel]
        except Exception:
            return None

    def _selection_marker_width(self) -> float:
        """Indicator size in pixels, by PyMOL's rule.

        ``ExecutiveGetAdjustedSelectionWidth``:
        ``selection_width_scale * |stick_radius| / vScale``, clamped between
        ``selection_width`` and ``selection_width_max`` -- so the marker grows
        as you zoom in and stops at ten pixels. ``vScale`` is
        ``SceneGetScreenVertexScale``: the scene units one pixel covers at the
        origin's depth.

        PyMOL recomputes this every frame and chimol computes it when the
        selection changes; between the two, the clamp band is three to ten
        pixels, so the drift a zoom introduces is at most that.
        """
        cfg = _DISPLAY_CONFIG.get("selection", {}) or {}
        try:
            low = float(cfg.get("width", 3.0))
            high = float(cfg.get("width_max", 10.0))
            scale = float(cfg.get("width_scale", 2.0))
            radius = float(cfg.get("width_reference_radius", 0.25))
        except Exception:
            low, high, scale, radius = 3.0, 10.0, 2.0, 0.25

        renderer = getattr(self, "_renderer", None)
        try:
            height = max(int(renderer.scene_height()), 1)
            fov = math.radians(float(renderer._fov))
            distance = float(renderer._distance)
            v_scale = 2.0 * distance * math.tan(fov / 2.0) / height
        except Exception:
            v_scale = 0.0
        if v_scale <= 0.0:
            return high
        return float(min(max(scale * abs(radius) / v_scale, low), high))

    def _update_selection_highlight(self, coords: np.ndarray) -> list[SceneObject] | None:
        """Mark the selected atoms, the way PyMOL marks a selection.

        PyMOL's indicator (``ExecutiveSetupIndicatorPassMultipassImmediate``) is
        three concentric filled squares at each selected atom: pink
        ``(1.0, 0.2, 0.6)`` at the full width, black at about half of it, and
        white in the middle. It is loud on purpose -- a selection you have to
        hunt for is one you act on by mistake.

        What stood here was a thin green ring at each *residue*, argued for as
        Chimera's outline. It is the better idea and it was not what it drew:
        the middle of a ring is only covered when the marker is depth-tested
        against the geometry it hugs, this one is an overlay, and at one point
        per residue there was nothing to hug. Reported as "the rect select does
        not show the selection", which is what a scatter of thin rings over a
        cartoon looks like. A real silhouette needs the selected geometry's
        depth rendered to a texture and the existing outline shader
        (``postprocess._OUTLINE_FRAGMENT``) run over it; until that second depth
        target exists, PyMOL's marker is the honest option.
        """
        centers = self._selection_atom_positions(coords)
        if centers is None or not len(centers):
            return None

        try:
            sel_cfg = _DISPLAY_CONFIG.get("selection", {})
        except Exception:
            sel_cfg = {}
        # PyMOL's selection pink, from its own indicator pass.
        default_color = [1.0, 0.2, 0.6, 1.0]
        try:
            col = np.asarray(sel_cfg.get("color", default_color), dtype=float)
        except Exception:
            col = np.array(default_color, dtype=float)
        if col.shape[0] != 4:
            col = np.array(default_color, dtype=float)

        geom = Geometry(
            kind="points",
            positions=centers,
            colors=np.tile(col, (centers.shape[0], 1)),
            meta={
                "glyph": "selection",
                "size": self._selection_marker_width(),
                "px_mode": True,
            },
        )
        # An overlay, as PyMOL's is: `selection_overlay` defaults to on, so the
        # marker is drawn over the representation rather than hidden by it. A
        # marker you can only see when nothing is in front of it does not tell
        # you what is selected on the far side of the molecule -- which is
        # exactly where a box select reaches.
        return [SceneObject(id="selection", geometry=geom, render_mode="overlay")]

    def _update_view(self, fit_camera: bool = False) -> None:
        """Rebuild the scene, leaving the camera where the user put it.

        A rebuild is what colouring, a representation change, a label, a bond
        edit and **every** ``set`` all trigger. While this defaulted to ``True``
        each of those refitted the camera to the whole molecule, so framing a
        binding site and then adjusting a stick radius threw the framing away --
        measured at 12 of 12 ordinary commands, `zoom resi 20-26` at distance
        357 and the next command back at 1730. PyMOL moves the camera only for a
        camera command or a load, and so does this now.

        The three load paths (:meth:`set_structure`, :meth:`set_coordinates`,
        :meth:`add_volume`) pass ``True`` explicitly, which is the whole of
        PyMOL's ``auto_zoom``.

        **Why this could not be flipped before.** The attempt is recorded as
        reverted because `ray` then traced an empty image for every
        representation -- the load-time fit looked as though it had nothing to
        measure. It measured fine; the *aspect* was wrong. A window that is
        never shown has no viewport, and `_aspect` read 1/30 off the one-pixel
        column that left, putting the camera thirty times too far away. Refitting
        on every rebuild hid that, because the last rebuild landed after the
        widget had a size. With :meth:`QtGLRenderer._aspect` fixed there is
        nothing left to hide.

        Parameters
        ----------
        fit_camera : bool, optional
            Refit the camera distance to the scene radius afterwards. Only a
            load path or a camera command should ask for this.
        """
        if self._renderer is None:
            return
        if getattr(self, "_update_depth", 0) > 0:
            # Inside `suspend_updates`: the caller will ask once at the end.
            return

        self._occlusion_vertices_this_build = 0
        visible_entries = [
            entry
            for entry in self._objects.values()
            if entry.visible
            and (
                (
                    entry.state.coords is not None
                    and getattr(entry.state.coords, "size", 0) > 0
                )
                # A voxel map has no coordinates at all. Testing only for those
                # would drop it from the scene without a word.
                or getattr(entry.state, "volume", None) is not None
            )
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
        volume_objects = self._update_volume(object_prefix)
        if self._coords is None or self._coords.size == 0:
            # A map on its own is a complete object; it does not need atoms.
            # Its ids still have to be qualified -- the prefix loop below is not
            # reached on this path, and two maps would both be "volume_0".
            if object_prefix:
                for obj in volume_objects:
                    obj.id = f"{object_prefix}:{obj.id}"
            return volume_objects

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

        self._recompute_colors_per_ca(n_points)

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

        metaball_cfg = self._metaball_config(_DISPLAY_CONFIG.get("metaball", {}))
        scene_objects += self._update_metaballs(coords, metaball_cfg, self._colors_per_ca) or []

        scene_objects += self._update_dots(coords, self._colors_per_ca) or []
        scene_objects += self._update_custom_overlays(surface_cfg) or []
        scene_objects += self._update_measurements() or []
        scene_objects += self._update_restraints(self._get_active_state()) or []
        scene_objects += self._update_cell(self._get_active_state()) or []
        scene_objects += self._update_selection_highlight(coords) or []
        scene_objects += volume_objects

        if object_prefix:
            for obj in scene_objects:
                obj.id = f"{object_prefix}:{obj.id}"

        return scene_objects

    def _ca_coords_2d(self) -> np.ndarray | None:
        """Return the per-residue coordinates as ``(n_residues, 3)``, or None.

        ``_coords`` is ``(n_frames, n_residues, 3)`` for a trajectory, and the
        residue count is what every per-residue array is sized by -- so reading
        ``shape[0]`` off the raw attribute gives the *frame* count on exactly
        the objects where getting it wrong matters. One definition, because two
        readings of this drifted once already.

        Read-only: unlike the scene builder's own resolution, this does not move
        the state's active frame, so a colour query cannot advance a trajectory.
        """
        coords = getattr(self, "_coords", None)
        if coords is None or getattr(coords, "size", 0) <= 0:
            return None
        arr = np.asarray(coords, dtype=float)
        if arr.ndim == 3:
            state = self._get_active_state()
            frame = getattr(state, "coords", None)
            if frame is None:
                return None
            arr = np.asarray(frame, dtype=float)
        if arr.ndim != 2 or arr.shape[1] != 3:
            return None
        return arr

    def _recompute_colors_per_ca(self, n_points: int) -> np.ndarray | None:
        """Recompute ``_colors_per_ca`` from the colour mode and the overrides.

        Split out of :meth:`_build_scene_for_current_object` because
        :meth:`get_residue_colors` needs *only this*. It used to get it by
        calling the scene builder, which rebuilds every representation to
        recover one array -- and the sequence strip asks for those colours
        **once per object, every frame**, from inside ``paintGL``. On a surface
        that meant re-running the density grid, marching cubes, the gradients
        and the ambient occlusion sixty times a second: 86 ms of the 82 ms
        frame, and the reason frame time did not move when the window was
        resized. The comment at the call site said reading them back "is a
        cached array copy, which costs nothing".

        Parameters
        ----------
        n_points : int
            Number of residues the array must cover.

        Returns
        -------
        numpy.ndarray or None
            The finalised ``(n_points, 4)`` colours, also stored on the viewer.
        """
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

        return self._colors_per_ca

    def add_volume(self, grid, *, name: str | None = None,
                   levels=None, object_id: str | None = None) -> str:
        """Put a voxel map into the scene as an object of its own.

        Parameters
        ----------
        grid : chimol.volume.VolumeGrid
            The map. It carries its own placement, so nothing here has to know
            whether it came from a file, from atoms, or from an array a plugin
            handed over.
        name : str, optional
            Object name; the grid's own name by default.
        levels : list of dict, optional
            Contours to draw. One derived from the data when omitted, because an
            accessible volume, a cryo-EM map and a photon-count stack share no
            scale and a fixed number would land off at least two of them.
        object_id : str, optional
            Reuse an existing object instead of creating one.

        Returns
        -------
        str
            The object id.
        """
        display_name = name or getattr(grid, "name", "map")
        if object_id is None:
            entry = self._create_object(name=display_name)
            object_id = entry.object_id
        self.set_active_object(object_id)

        state = self._get_active_state()
        state.volume = grid
        # Materialise the opening contours rather than deriving them at draw
        # time. Leaving the list empty meant the map was *drawn* with levels the
        # object did not *have*, so the panel and every `get_volume_levels`
        # caller saw none -- two answers to one question.
        state.volume_levels = (
            list(levels) if levels else _default_volume_levels(grid)
        )

        # Scene coordinates are `(world - raw_center) * scale`, per object. A map
        # that centred on *itself* would therefore be drawn at the middle of the
        # scene whatever its true position -- which is how the first version of
        # this put a density that wraps a structure inside it as a small blob.
        # Adopt an existing object's frame so the two land together; only define
        # the frame when this map is the first thing in the scene.
        low, high = grid.extent()
        centre_world = (np.asarray(low, dtype=float) + np.asarray(high, dtype=float)) * 0.5
        shared_centre = None
        for other_id, other in self._objects.items():
            if other_id == object_id:
                continue
            other_centre = getattr(other.state, "raw_center", None)
            if other_centre is not None:
                shared_centre = np.asarray(other_centre, dtype=float).reshape(3)
                break
        state.raw_center = centre_world if shared_centre is None else shared_centre

        scale = float(getattr(self, "_scale_factor", 1.0) or 1.0)
        state.center = (centre_world - state.raw_center) * scale
        radius = float(np.linalg.norm(np.asarray(high, dtype=float) - centre_world))
        state.radius = max(radius * scale, 1e-3)

        self._update_view(fit_camera=True)
        return object_id

    def set_volume_levels(self, levels, object_id: str | None = None) -> bool:
        """Replace the contours drawn on this object's map.

        Returns ``False`` when the object has no map, rather than quietly doing
        nothing -- a level set on the wrong object is otherwise invisible.
        """
        with self._activate_object(object_id):
            state = self._get_active_state()
            if getattr(state, "volume", None) is None:
                return False
            state.volume_levels = list(levels)
            self._update_view()
            return True

    def get_volume_levels(self, object_id: str | None = None) -> list:
        """The contours drawn on this object's map; empty when it has none."""
        with self._activate_object(object_id):
            return list(getattr(self._get_active_state(), "volume_levels", []) or [])

    def get_volume(self, object_id: str | None = None):
        """This object's voxel map, or ``None`` when it is not a map."""
        with self._activate_object(object_id):
            return getattr(self._get_active_state(), "volume", None)

    def _update_volume(self, object_prefix: str | None = None) -> list[SceneObject]:
        """Contour this object's voxel map, if it has one.

        One scene object per level, so a dense core can be drawn inside a diffuse
        shell in different colours -- which is how an accessible volume or an
        occupancy density is actually read.
        """
        grid = getattr(self._get_active_state(), "volume", None) \
            if self._objects else None
        if grid is None:
            return []
        levels = list(getattr(self._get_active_state(), "volume_levels", []) or [])
        if not levels:
            levels = _default_volume_levels(grid)

        objects: list[SceneObject] = []
        for index, entry in enumerate(levels):
            try:
                level = float(entry.get("level"))
            except (TypeError, ValueError):
                continue
            try:
                surface = grid.isosurface(level)
            except Exception:
                logger.warning(
                    "chimol: could not contour %s at %g", grid.name, level,
                    exc_info=True,
                )
                continue
            if surface is None:
                # The level sits outside the data; that is an answer, not a
                # failure, and drawing nothing is the honest result.
                continue
            verts, faces, normals = surface
            # Into the same scene frame the structure is drawn in. A uniform
            # scale and a translation leave the normals alone.
            verts = self._transform_world_coords_to_scene(
                np.asarray(verts, dtype=float)
            ).astype(np.float32)
            color = np.asarray(entry.get("color", (0.5, 0.7, 1.0, 1.0)), dtype=float)
            if color.size < 4:
                color = np.concatenate([color.reshape(-1), np.ones(4)])[:4]
            colors = np.tile(color.astype(np.float32), (verts.shape[0], 1))
            style = str(entry.get("style", "surface")).lower()
            if style == "mesh":
                # A real wireframe, drawn as lines. Setting a "wireframe" flag on
                # a triangle mesh looked right and drew a solid surface, because
                # nothing downstream reads such a flag -- the contour has to
                # become line geometry to be one.
                geometry = Geometry(
                    kind="line",
                    positions=verts,
                    indices=_triangle_edges(faces),
                    normals=normals,
                    colors=colors,
                    meta={"mode": "lines", "width": 1.0, "map_level": level},
                )
            else:
                geometry = Geometry(
                    kind="mesh",
                    positions=verts,
                    indices=faces,
                    normals=normals,
                    colors=colors,
                    meta={"map_level": level},
                )
            objects.append(
                SceneObject(
                    id=f"volume_{index}",
                    geometry=geometry,
                    render_mode="transparent" if color[3] < 1.0 else "opaque",
                )
            )
        return objects

    def _fit_camera_to_radius(self, radius: float) -> None:
        if self._renderer is None:
            return
        self._renderer.fit_to_radius(radius)
