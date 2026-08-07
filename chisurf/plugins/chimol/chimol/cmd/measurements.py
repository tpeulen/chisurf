from __future__ import annotations

from collections import Counter
from shlex import split as shlex_split

import numpy as np

from ..analysis.metrics import compute_kabsch, compute_rmsd
from .base import BaseCmd
from .registry import command
from .selection_types import Selection


def _is_number(text: str) -> bool:
    """Whether a command token is a bare number.

    Used to tell PyMOL's positional ``cutoff`` and ``mode`` from a selection: no
    selection expression is a bare number, so a trailing one is never ambiguous.
    """
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def _dash_color():
    """The configured measurement colour, or ``None`` to take the default."""
    from ..config import _DISPLAY_CONFIG

    value = (_DISPLAY_CONFIG.get("dash", {}) or {}).get("color")
    if value is None:
        return None
    try:
        rgba = [float(c) for c in value]
    except (TypeError, ValueError):
        return None
    if len(rgba) == 3:
        rgba.append(1.0)
    return rgba if len(rgba) == 4 else None


def _scene_transform(viewer, object_id, rotation, translation) -> np.ndarray:
    """Express an Angstrom-space rigid transform in the renderer's scene units.

    Scene coordinates are ``(xyz - raw_center) * scale``, so the atom-space map
    ``x -> R x + t`` reads ``y -> R y + ((R - I) c + t) * scale`` on them.
    Dropping the ``(R - I) c`` term rotates the picture about the molecule's own
    centre while the fit rotated the atoms about the coordinate origin, which
    leaves the two arrays tens of Angstrom apart on any rotation.

    Parameters
    ----------
    viewer : object
        The viewer holding the object.
    object_id : str
        Object the transform will be applied to.
    rotation : (3, 3) ndarray
        Rotation acting on Angstrom column vectors.
    translation : (3,) ndarray
        Translation in Angstrom, applied after the rotation.

    Returns
    -------
    numpy.ndarray
        The ``(3,)`` translation to pass to ``apply_transform_to_object``.
    """
    scale = float(getattr(viewer, "_scale_factor", 1.0) or 1.0)
    trans = np.asarray(translation, dtype=float).reshape(3)
    centre = None
    getter = getattr(viewer, "object_raw_center", None)
    if callable(getter):
        centre = getter(object_id)
    if centre is None:
        return trans * scale
    centre = np.asarray(centre, dtype=float).reshape(3)
    return (rotation @ centre - centre + trans) * scale


class MeasurementMixin(BaseCmd):
    """Measurements, frames, and geometric helpers."""

    def _add_measurement(self, viewer, name: str, kind: str, positions: np.ndarray, label: str):
        if not name:
            name = f"{kind}_{len(viewer._measurements)}"

        mdata = {
            "kind": kind,
            "positions": positions,
            "label": label,
            "color": [1.0, 1.0, 0.0, 1.0]
        }

        cur = dict(viewer._measurements)
        cur[name] = mdata
        viewer._measurements = cur
        viewer._update_view()

    # ------------------------------------------------------------------ #
    # Frames (per-object trajectory stepping; timeline `frame` lives in
    # AnimationMixin and wins the command name via MRO)
    # ------------------------------------------------------------------ #
    @command("frame_next")
    def frame_next(self) -> None:
        """Step the active object to its next trajectory frame."""
        self._cmd_frame_step(1)

    @command("frame_prev")
    def frame_prev(self) -> None:
        """Step the active object to its previous trajectory frame."""
        self._cmd_frame_step(-1)

    def _cmd_frame_step(self, delta: int) -> None:
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        try:
            obj_id = viewer.get_active_object_id()
        except Exception:
            obj_id = None
        if obj_id is None:
            self._emit_error("No active object for frame control")
            return

        try:
            n_frames = viewer.get_frame_count(obj_id)
        except Exception:
            n_frames = 0
        if n_frames <= 0:
            self._emit_error("Active object has no frames")
            return

        try:
            current = viewer.get_active_frame_index(obj_id)
        except Exception:
            current = 0

        idx = current + int(delta)
        if idx < 0:
            idx = 0
        if idx >= n_frames:
            idx = n_frames - 1

        try:
            viewer.set_active_frame(idx, object_id=obj_id)
        except Exception:
            return

        self._emit_message(f"Frame: {idx + 1}/{n_frames}")

    # ------------------------------------------------------------------ #
    # Measurements
    # ------------------------------------------------------------------ #
    @command("distance", aliases=("dist",))
    def distance(
        self,
        *seles: str,
        cutoff: float = -1.0,
        mode: int = 0,
        label: int = 1,
        quiet: int = 0,
        reset: int = 1,
    ) -> None:
        """Measure distances between two selections.

        PyMOL's ``distance [name [, sele1 [, sele2 [, cutoff [, mode]]]]]``.

        ``mode`` decides which pairs are drawn:

        * ``0`` -- every interatomic distance inside ``cutoff``;
        * ``1`` -- only pairs that are bonded;
        * ``2`` -- **polar contacts**: donor/acceptor pairs passing the
          hydrogen-bond test in :mod:`~chimol.analysis.hbonds`;
        * ``3`` -- like ``0``, but excluding atoms within ``distance_exclusion``
          bonds of each other;
        * ``4`` -- one distance, between the two selections' centroids;
        * ``5`` / ``6`` / ``7`` -- **pi interactions**: both kinds, ring-ring
          stacking only, or cation-ring only;
        * ``9`` -- **halogen bonds**;
        * ``10`` -- **salt bridges**.

        Modes 0, 1 and 3 measure between *atoms* and can produce a great many
        lines; ``2`` is the one the presets and the **A ▸ find** menu use. The
        interaction modes have criteria of their own and ignore ``cutoff`` --
        see :mod:`~chimol.analysis.interactions`.

        With one atom on each side and no mode, this is the two-atom measurement
        it has always been -- so ``distance 14/CA, 29/CA`` is unchanged.

        Parameters
        ----------
        *seles : str
            ``[name,] sele1, sele2 [, cutoff [, mode]]``. Trailing numbers are
            read as ``cutoff`` then ``mode``, which is how PyMOL's positional
            form spells them.
        cutoff : float, optional
            Longest distance drawn. Negative means "let the mode decide": the
            hydrogen-bond criteria for mode 2, and 4 Å for the contact modes,
            where PyMOL's own default of *everything* is never what is wanted.
        mode : int, optional
            As above.
        label : int, optional
            0 draws the dashes without their numbers, which is what the presets
            do -- a hundred labelled contacts is unreadable.
        quiet : int, optional
            1 suppresses the summary line. Accepted for PyMOL compatibility.
        reset : int, optional
            Accepted for PyMOL compatibility; a named measurement is always
            replaced here, never appended to.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        args = [str(a).strip() for a in seles if str(a).strip()]
        if not args:
            self._emit_error("Usage: distance sele1, sele2")
            return

        # PyMOL takes cutoff and mode positionally, after the two selections. A
        # selection is never a bare number, so trailing numbers are unambiguous.
        trailing: list[float] = []
        while len(args) > 2 and _is_number(args[-1]) and len(trailing) < 2:
            trailing.insert(0, float(args.pop()))
        if trailing:
            cutoff = trailing[0]
            if len(trailing) > 1:
                mode = int(trailing[1])

        try:
            meas_name, sele_parts = self._parse_measurement_selections(
                args, expected_count=2, cmd="distance"
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        sele1, sele2 = sele_parts

        if int(mode) != 0 or self._selection_is_multi_atom(viewer, sele1, sele2):
            self._distance_set(
                viewer, meas_name, sele1, sele2,
                cutoff=float(cutoff), mode=int(mode),
                label=bool(label), quiet=bool(quiet),
            )
            return

        try:
            obj1_id, obj1_name, res_i, atom1, p1 = self._resolve_selection_to_atom(
                viewer, sele1
            )
            obj2_id, obj2_name, res_j, atom2, p2 = self._resolve_selection_to_atom(
                viewer, sele2
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        try:
            v1 = np.asarray(p1, dtype=float).reshape(-1)
            v2 = np.asarray(p2, dtype=float).reshape(-1)
        except Exception:
            self._emit_error("Could not compute distance (no coordinates)")
            return

        if v1.shape[0] != 3 or v2.shape[0] != 3:
            self._emit_error("Could not compute distance (invalid coordinates)")
            return

        try:
            dist = float(np.linalg.norm(v1 - v2))
        except Exception:
            self._emit_error("Could not compute distance (no coordinates)")
            return

        label1 = f"{obj1_name} res {res_i + 1}"
        if atom1:
            label1 += f" and name {atom1}"
        label2 = f"{obj2_name} res {res_j + 1}"
        if atom2:
            label2 += f" and name {atom2}"

        prefix = "distance "
        if meas_name:
            prefix += f"{meas_name} "

        dist_val = f"{dist:.3f}"
        self._emit_message(f"{prefix}{label1} - {label2}: {dist_val}")

        positions = np.array([v1, v2])
        self._add_measurement(viewer, meas_name, "distance", positions, dist_val)

    # ------------------------------------------------------------------ #
    # Distance *sets*: many pairs at once (PyMOL's `dist ... mode=N`)
    # ------------------------------------------------------------------ #
    def _combined_atom_table(self, viewer, sele1: str, sele2: str):
        """Both selections over one atom table, PyMOL-style.

        PyMOL's selector runs over a single global table spanning every loaded
        object, which is what lets ``dist`` measure between two molecules.
        chimol evaluates per object, so the tables are concatenated here and the
        bond lists offset with them. There is deliberately **no** edge between
        two objects' blocks: that is what stops the neighbour-exclusion rule
        from treating atoms in different molecules as bonded neighbours.

        Returns
        -------
        tuple
            ``(atoms, bonds, mask1, mask2, names)`` where ``names`` maps each
            row back to ``(object_name, atom_index)`` for the summary line, or
            ``None`` when neither selection reached an object with atoms.
        """
        hits1 = self._resolve_selection_to_atom_masks(viewer, sele1)
        hits2 = self._resolve_selection_to_atom_masks(viewer, sele2)
        by_object: dict[str, str] = {}
        for obj_id, obj_name, _mask in list(hits1) + list(hits2):
            by_object[obj_id] = obj_name
        if not by_object:
            return None

        masks1 = {obj_id: mask for obj_id, _n, mask in hits1}
        masks2 = {obj_id: mask for obj_id, _n, mask in hits2}

        tables, bonds, m1, m2, names = [], [], [], [], []
        offset = 0
        for obj_id, obj_name in by_object.items():
            state = getattr(viewer._objects.get(obj_id), "state", None)
            atoms = getattr(state, "atoms", None)
            if atoms is None or len(atoms) == 0:
                continue
            n = len(atoms)
            tables.append(atoms)
            pairs = getattr(state, "bond_pairs", None)
            if pairs is not None and len(pairs):
                bonds.append(np.asarray(pairs, dtype=int)[:, :2] + offset)
            m1.append(self._padded(masks1.get(obj_id), n))
            m2.append(self._padded(masks2.get(obj_id), n))
            names.append((obj_name, offset, n))
            offset += n

        if not tables:
            return None
        atoms = np.concatenate(tables) if len(tables) > 1 else tables[0]
        bond_pairs = (
            np.concatenate(bonds) if bonds else np.zeros((0, 2), dtype=int)
        )
        return (
            atoms,
            bond_pairs,
            np.concatenate(m1),
            np.concatenate(m2),
            names,
        )

    @staticmethod
    def _padded(mask, n: int) -> np.ndarray:
        """A mask of length ``n``; an absent or short one reads as all-false."""
        if mask is None:
            return np.zeros(n, dtype=bool)
        mask = np.asarray(mask, dtype=bool)
        if mask.shape[0] == n:
            return mask
        out = np.zeros(n, dtype=bool)
        out[: min(n, mask.shape[0])] = mask[: min(n, mask.shape[0])]
        return out

    def _selection_is_multi_atom(self, viewer, sele1: str, sele2: str) -> bool:
        """Whether either side names more than one atom.

        ``distance 14/CA, 29/CA`` is one measurement with a readable label;
        ``distance all, all`` is a distance *set*. The two answer differently
        and the difference is decided here rather than by the user.
        """
        try:
            for expr in (sele1, sele2):
                total = sum(
                    int(np.count_nonzero(mask))
                    for _id, _name, mask in
                    self._resolve_selection_to_atom_masks(viewer, expr)
                )
                if total > 1:
                    return True
        except ValueError:
            return False
        return False

    def _distance_set(
        self, viewer, meas_name, sele1: str, sele2: str, *,
        cutoff: float, mode: int, label: bool, quiet: bool,
    ) -> None:
        """Build a many-segment measurement for one of PyMOL's distance modes."""
        from ..analysis.hbonds import HBondCriteria, find_hydrogen_bonds
        from ..config import _DISPLAY_CONFIG

        try:
            combined = self._combined_atom_table(viewer, sele1, sele2)
        except ValueError as exc:
            self._emit_error(str(exc))
            return
        if combined is None:
            self._emit_error("distance: selection matched no atoms")
            return
        atoms, bond_pairs, mask1, mask2, _names = combined
        xyz = np.asarray(atoms["xyz"], dtype=float)

        if mode == 4:
            if not mask1.any() or not mask2.any():
                self._emit_error("distance: selection matched no atoms")
                return
            c1 = xyz[mask1].mean(axis=0)
            c2 = xyz[mask2].mean(axis=0)
            dist = float(np.linalg.norm(c1 - c2))
            self._finish_distance_set(
                viewer, meas_name, np.array([c1, c2]), [f"{dist:.3f}"],
                label=label, quiet=quiet,
                summary=f"distance {meas_name or ''}: centroids {dist:.3f}",
            )
            return

        if mode in (5, 6, 7, 9, 10):
            self._interaction_set(
                viewer, meas_name, atoms, bond_pairs, mask1, mask2,
                mode=mode, label=label, quiet=quiet,
            )
            return

        if mode == 2:
            criteria = HBondCriteria.from_config()
            bonds = find_hydrogen_bonds(
                atoms, bond_pairs, mask1, mask2, criteria=criteria,
                cutoff=cutoff if cutoff >= 0 else None,
            )
            if criteria.from_proton:
                # PyMOL draws from the proton when there is a real one; a
                # virtual hydrogen is not a place in the file, so those still
                # start at the donor.
                starts = np.array([
                    b.hydrogen_xyz if b.hydrogen is not None else xyz[b.donor]
                    for b in bonds
                ]).reshape(-1, 3)
            else:
                starts = xyz[[b.donor for b in bonds]].reshape(-1, 3)
            ends = xyz[[b.acceptor for b in bonds]].reshape(-1, 3)
            pairs = np.empty((len(bonds) * 2, 3), dtype=float)
            if len(bonds):
                pairs[0::2] = starts
                pairs[1::2] = ends
            labels = [f"{b.distance:.1f}" for b in bonds]
            self._finish_distance_set(
                viewer, meas_name, pairs, labels, label=label, quiet=quiet,
                summary=f"{len(bonds)} polar contacts",
            )
            return

        # Modes 0, 1 and 3: plain interatomic distances.
        exclusion = 0
        if mode == 3:
            exclusion = int(
                (_DISPLAY_CONFIG.get("measure", {}) or {}).get(
                    "distance_exclusion", 5
                )
            )
        # PyMOL's own default here is "no cutoff", which on `all, all` is every
        # pair in the structure. A contact radius is the useful reading and the
        # only one that finishes. Mode 1 needs none: it is already bounded by
        # the bond list, and every bond is well inside any contact radius.
        search = cutoff if cutoff >= 0 else (-1.0 if mode == 1 else 4.0)
        pairs_idx = self._contact_pairs(
            xyz, mask1, mask2, search, bond_pairs,
            bonds_only=(mode == 1), exclusion=exclusion,
        )
        flat = np.empty((len(pairs_idx) * 2, 3), dtype=float)
        labels = []
        for k, (i, j) in enumerate(pairs_idx):
            flat[2 * k] = xyz[i]
            flat[2 * k + 1] = xyz[j]
            labels.append(f"{float(np.linalg.norm(xyz[i] - xyz[j])):.1f}")
        self._finish_distance_set(
            viewer, meas_name, flat, labels, label=label, quiet=quiet,
            summary=f"{len(pairs_idx)} distances",
        )

    @staticmethod
    def _contact_pairs(
        xyz, mask1, mask2, cutoff: float, bond_pairs, *,
        bonds_only: bool, exclusion: int,
    ) -> list[tuple[int, int]]:
        """Index pairs within ``cutoff``, minus whatever the mode excludes."""
        from ..analysis.hbonds import neighbour_lists, within_n_bonds

        side1 = np.nonzero(mask1)[0]
        side2 = np.nonzero(mask2)[0]
        if not side1.size or not side2.size:
            return []
        if bonds_only:
            pairs = np.asarray(bond_pairs, dtype=int).reshape(-1, 2)
            keep = []
            for i, j in pairs:
                if (mask1[i] and mask2[j]) or (mask1[j] and mask2[i]):
                    d = float(np.linalg.norm(xyz[i] - xyz[j]))
                    if cutoff < 0 or d <= cutoff:
                        keep.append((int(min(i, j)), int(max(i, j))))
            return sorted(set(keep))

        from scipy.spatial import cKDTree

        neighbours = (
            neighbour_lists(len(xyz), bond_pairs) if exclusion else None
        )
        tree = cKDTree(xyz[side2])
        seen: set[tuple[int, int]] = set()
        for i in side1:
            for local in tree.query_ball_point(xyz[i], cutoff):
                j = int(side2[local])
                if i == j:
                    continue
                key = (int(min(i, j)), int(max(i, j)))
                if key in seen:
                    continue
                if neighbours is not None and within_n_bonds(
                    int(i), j, exclusion, neighbours
                ):
                    continue
                seen.add(key)
        return sorted(seen)

    #: PyMOL's distance modes for the three interaction finders, and what each
    #: one asks for. 5 is both pi kinds, which is what `pi_interactions` runs.
    _INTERACTION_MODES = {
        5: "pi",
        6: "pi-pi",
        7: "pi-cation",
        9: "halogen-bond",
        10: "salt-bridge",
    }

    #: What to call each in the summary line. Spelled out rather than an ``s``
    #: appended to the mode's key, which reported "0 pi-pis".
    _INTERACTION_NAMES = {
        "pi": "pi interactions",
        "pi-pi": "pi-pi interactions",
        "pi-cation": "pi-cation interactions",
        "halogen-bond": "halogen bonds",
        "salt-bridge": "salt bridges",
    }

    def _interaction_set(
        self, viewer, meas_name, atoms, bond_pairs, mask1, mask2, *,
        mode: int, label: bool, quiet: bool,
    ) -> None:
        """Draw one of the three interaction finders as a distance set.

        These are separate detectors rather than variants of the polar-contact
        test, so each has its own criteria object; see
        :mod:`~chimol.analysis.interactions`, which transcribes them. A pi
        interaction ends at a **ring centre**, which is not an atom -- the
        finder returns points for that reason and they are drawn as they come.
        """
        from ..analysis.interactions import (
            find_halogen_bonds,
            find_pi_interactions,
            find_salt_bridges,
        )

        kind = self._INTERACTION_MODES[int(mode)]
        if kind == "salt-bridge":
            hits = find_salt_bridges(atoms, mask1, mask2)
        elif kind == "halogen-bond":
            hits = find_halogen_bonds(atoms, bond_pairs, mask1, mask2)
        else:
            hits = find_pi_interactions(
                atoms, bond_pairs, mask1, mask2,
                pipi=kind in ("pi", "pi-pi"),
                pication=kind in ("pi", "pi-cation"),
            )

        positions = np.empty((len(hits) * 2, 3), dtype=float)
        for index, hit in enumerate(hits):
            positions[2 * index] = hit.start
            positions[2 * index + 1] = hit.end
        labels = [f"{hit.distance:.1f}" for hit in hits]

        if kind == "pi" and hits:
            counts = Counter(hit.kind for hit in hits)
            detail = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
            summary = f"{len(hits)} pi interactions ({detail})"
        else:
            summary = f"{len(hits)} {self._INTERACTION_NAMES[kind]}"

        self._finish_distance_set(
            viewer, meas_name, positions, labels,
            label=label, quiet=quiet, summary=summary,
        )

    def _finish_distance_set(
        self, viewer, meas_name, positions, labels, *,
        label: bool, quiet: bool, summary: str,
    ) -> None:
        """Store a distance set and report it.

        A run that finds nothing **clears** a measurement of the same name
        rather than leaving the last one on screen. That is PyMOL's ``reset=1``,
        and without it the menu lies: firing *to any atoms* on a whole object
        selects nothing on the far side, finds nothing, and the previous
        entry's dashes stay put looking like the answer.
        """
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        name = meas_name or f"dist_{len(viewer._measurements)}"

        cur = dict(viewer._measurements)
        if positions.shape[0] == 0:
            if cur.pop(name, None) is not None:
                viewer._measurements = cur
                viewer._update_view()
            if not quiet:
                self._emit_message(f"distance {name}: {summary}")
            return

        colour = _dash_color() or [1.0, 1.0, 0.0, 1.0]
        cur[name] = {
            "kind": "dashes",
            "positions": positions,
            "label": "",
            "labels": list(labels) if label else [],
            "color": list(colour),
        }
        viewer._measurements = cur
        viewer._update_view()
        if not quiet:
            self._emit_message(f"distance {name}: {summary}")

    @command("pi_interactions")
    def pi_interactions(
        self,
        *seles: str,
        label: int = 0,
        quiet: int = 0,
        reset: int = 1,
    ) -> None:
        """Find ring stacking and cation-ring contacts.

        PyMOL's ``pi_interactions name, sele1 [, sele2]``, which is what its
        **A ▸ find ▸ pi interactions ▸ all** entry calls -- the same finder as
        ``distance ..., mode=5``, under the name PyMOL gives it. With one
        selection both sides are that selection, so ``pi_interactions pi, all``
        answers "what stacks against what in this structure".

        Parameters
        ----------
        *seles : str
            ``[name,] sele1 [, sele2]``.
        label : int, optional
            1 writes the distance on each dash. Off by default: a stacking
            distance between two ring *centres* is rarely the number wanted,
            and a nucleic structure produces dozens of them.
        quiet : int, optional
            1 suppresses the summary line.
        reset : int, optional
            Accepted for PyMOL compatibility; a named measurement is always
            replaced here.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        args = [str(a).strip() for a in seles if str(a).strip()]
        if not args:
            self._emit_error("Usage: pi_interactions name, sele1 [, sele2]")
            return
        if len(args) == 1:
            args = [args[0], "all"]
        if len(args) == 2:
            # One selection means "within it", which is `same` in PyMOL's menu.
            args = [args[0], args[1], args[1]]

        try:
            meas_name, sele_parts = self._parse_measurement_selections(
                args, expected_count=2, cmd="pi_interactions"
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        self._distance_set(
            viewer, meas_name, sele_parts[0], sele_parts[1],
            cutoff=-1.0, mode=5, label=bool(label), quiet=bool(quiet),
        )

    @command("angle")
    def angle(self, *seles: str) -> None:
        """Measure the angle over three selections."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        args = list(seles)
        if not args:
            self._emit_error("Usage: angle sele1, sele2, sele3")
            return

        try:
            meas_name, sele_parts = self._parse_measurement_selections(
                args, expected_count=3, cmd="angle"
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        try:
            obj1_id, obj1_name, res_i, atom1, p1 = self._resolve_selection_to_atom(
                viewer, sele_parts[0]
            )
            obj2_id, obj2_name, res_j, atom2, p2 = self._resolve_selection_to_atom(
                viewer, sele_parts[1]
            )
            obj3_id, obj3_name, res_k, atom3, p3 = self._resolve_selection_to_atom(
                viewer, sele_parts[2]
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        try:
            v1 = np.asarray(p1, dtype=float).reshape(-1)
            v2 = np.asarray(p2, dtype=float).reshape(-1)
            v3 = np.asarray(p3, dtype=float).reshape(-1)
        except Exception:
            self._emit_error("Could not compute angle (no coordinates)")
            return

        if v1.shape[0] != 3 or v2.shape[0] != 3 or v3.shape[0] != 3:
            self._emit_error("Could not compute angle (invalid coordinates)")
            return

        try:
            a = v1 - v2
            b = v3 - v2
            n1 = float(np.linalg.norm(a))
            n2 = float(np.linalg.norm(b))
            if n1 <= 0.0 or n2 <= 0.0:
                self._emit_error("Could not compute angle (degenerate geometry)")
                return
            cos_theta = float(np.dot(a, b) / (n1 * n2))
            if cos_theta > 1.0:
                cos_theta = 1.0
            if cos_theta < -1.0:
                cos_theta = -1.0
            value = float(np.degrees(np.arccos(cos_theta)))
        except Exception:
            self._emit_error("Could not compute angle (no coordinates)")
            return

        label1 = f"{obj1_name} res {res_i + 1}"
        if atom1:
            label1 += f" and name {atom1}"
        label2 = f"{obj2_name} res {res_j + 1}"
        if atom2:
            label2 += f" and name {atom2}"
        label3 = f"{obj3_name} res {res_k + 1}"
        if atom3:
            label3 += f" and name {atom3}"

        prefix = "angle "
        if meas_name:
            prefix += f"{meas_name} "

        val_str = f"{value:.3f}"
        self._emit_message(
            f"{prefix}{label1} - {label2} - {label3}: {val_str}"
        )

        positions = np.array([v1, v2, v3])
        self._add_measurement(viewer, meas_name, "angle", positions, val_str)

    @command("dihedral")
    def dihedral(self, *seles: str) -> None:
        """Measure the dihedral over four selections."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        args = list(seles)
        if not args:
            self._emit_error("Usage: dihedral sele1, sele2, sele3, sele4")
            return

        try:
            meas_name, sele_parts = self._parse_measurement_selections(
                args, expected_count=4, cmd="dihedral"
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        try:
            obj1_id, obj1_name, res_i, atom1, p1 = self._resolve_selection_to_atom(
                viewer, sele_parts[0]
            )
            obj2_id, obj2_name, res_j, atom2, p2 = self._resolve_selection_to_atom(
                viewer, sele_parts[1]
            )
            obj3_id, obj3_name, res_k, atom3, p3 = self._resolve_selection_to_atom(
                viewer, sele_parts[2]
            )
            obj4_id, obj4_name, res_l, atom4, p4 = self._resolve_selection_to_atom(
                viewer, sele_parts[3]
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        try:
            v1 = np.asarray(p1, dtype=float).reshape(-1)
            v2 = np.asarray(p2, dtype=float).reshape(-1)
            v3 = np.asarray(p3, dtype=float).reshape(-1)
            v4 = np.asarray(p4, dtype=float).reshape(-1)
        except Exception:
            self._emit_error("Could not compute dihedral (no coordinates)")
            return

        if (
            v1.shape[0] != 3
            or v2.shape[0] != 3
            or v3.shape[0] != 3
            or v4.shape[0] != 3
        ):
            self._emit_error("Could not compute dihedral (invalid coordinates)")
            return

        try:
            b0 = v2 - v1
            b1 = v3 - v2
            b2 = v4 - v3

            n1 = np.cross(b0, b1)
            n2 = np.cross(b1, b2)
            if np.linalg.norm(n1) <= 0.0 or np.linalg.norm(n2) <= 0.0:
                self._emit_error("Could not compute dihedral (degenerate geometry)")
                return

            n1_u = n1 / np.linalg.norm(n1)
            n2_u = n2 / np.linalg.norm(n2)
            b1_u = b1 / np.linalg.norm(b1) if np.linalg.norm(b1) > 0.0 else b1

            m1 = np.cross(n1_u, b1_u)
            x = float(np.dot(n1_u, n2_u))
            y = float(np.dot(m1, n2_u))
            value = float(np.degrees(np.arctan2(y, x)))
        except Exception:
            self._emit_error("Could not compute dihedral (no coordinates)")
            return

        label1 = f"{obj1_name} res {res_i + 1}"
        if atom1:
            label1 += f" and name {atom1}"
        label2 = f"{obj2_name} res {res_j + 1}"
        if atom2:
            label2 += f" and name {atom2}"
        label3 = f"{obj3_name} res {res_k + 1}"
        if atom3:
            label3 += f" and name {atom3}"
        label4 = f"{obj4_name} res {res_l + 1}"
        if atom4:
            label4 += f" and name {atom4}"

        prefix = "dihedral "
        if meas_name:
            prefix += f"{meas_name} "

        val_str = f"{value:.3f}"
        self._emit_message(
            prefix + f"{label1} - {label2} - {label3} - {label4}: {val_str}"
        )

        positions = np.array([v1, v2, v3, v4])
        self._add_measurement(viewer, meas_name, "dihedral", positions, val_str)

    # ------------------------------------------------------------------ #
    # RMS / Align
    # ------------------------------------------------------------------ #
    @command("rms", aliases=("rms_cur",))
    def rms(self, *seles: str) -> None:
        """Report the RMSD between two selections (no superposition)."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        args = list(seles)
        if not args:
            self._emit_error("Usage: rms mobile_selection, target_selection")
            return

        try:
            _, parts = self._parse_measurement_selections(
                args, expected_count=2, cmd="rms"
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        mobile_expr, target_expr = parts

        ca_mobile = self._selection_requests_ca_only(mobile_expr)
        ca_target = self._selection_requests_ca_only(target_expr)
        use_ca = ca_mobile and ca_target

        try:
            mob_obj, mob_name, mob_indices = self._resolve_selection_to_residue_indices(
                viewer, mobile_expr
            )
            tgt_obj, tgt_name, tgt_indices = self._resolve_selection_to_residue_indices(
                viewer, target_expr
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        try:
            if use_ca:
                mob_coords = viewer.get_residue_positions(
                    mob_indices if mob_indices else None, object_id=mob_obj
                )
                tgt_coords = viewer.get_residue_positions(
                    tgt_indices if tgt_indices else None, object_id=tgt_obj
                )
            else:
                mob_coords = self._gather_atom_coords_for_residues(
                    viewer,
                    mob_obj,
                    mob_name,
                    mob_indices if mob_indices else None,
                )
                tgt_coords = self._gather_atom_coords_for_residues(
                    viewer,
                    tgt_obj,
                    tgt_name,
                    tgt_indices if tgt_indices else None,
                )
        except Exception as exc:
            self._emit_error(f"Failed to access coordinates for RMSD: {exc}")
            return

        if mob_coords.size == 0 or tgt_coords.size == 0:
            self._emit_error("Selections must contain at least one coordinate")
            return

        count = min(mob_coords.shape[0], tgt_coords.shape[0])
        if count <= 0:
            self._emit_error("Selections did not yield matching coordinate counts")
            return

        mob_coords = mob_coords[:count]
        tgt_coords = tgt_coords[:count]

        try:
            rmsd = compute_rmsd(mob_coords, tgt_coords)
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        # Those coordinates are the renderer's, in scene units. RMSD is a length
        # and scales with them, so without this the number came out ten times too
        # large -- with an Angstrom sign on it, and disagreeing with `align`,
        # which reads the atom array.
        scale = float(getattr(viewer, "_scale_factor", 1.0) or 1.0)
        if scale:
            rmsd = rmsd / scale

        if use_ca:
            msg = (
                f"RMSD between {mob_name} and {tgt_name} over {count} CA atoms: "
                f"{rmsd:.3f} Å"
            )
        else:
            msg = (
                f"RMSD between {mob_name} and {tgt_name} over {count} atoms: "
                f"{rmsd:.3f} Å"
            )
        self._emit_message(msg)

    @command("align")
    def align(
        self, mobile: str = "", target: str = "", cutoff: float = 2.0, cycles: int = 5
    ) -> None:
        """Superpose ``mobile`` onto ``target`` with iterative outlier rejection."""
        self._align_or_super(mobile, target, cutoff, cycles, cmd="align")

    @command("pair_fit")
    def pair_fit(self, *selections: str) -> None:
        """Superpose on explicitly matched atom pairs (PyMOL ``pair_fit``).

        ``pair_fit mobile_sel, target_sel [, mobile_sel, target_sel ...]`` fits the
        first selection of each pair onto the second, matching atoms **in order**
        within each pair. That is the difference from ``align``, which finds its
        own correspondence: here you state it, which is what you want when the two
        structures are not the same sequence, or when only a few atoms should
        drive the fit.

        Every selection contributes to one least-squares fit, so several pairs can
        be given to pin down a superposition that one would leave ambiguous.

        Examples
        --------
        ``pair_fit mobile and resi 10-25 and name CA, ref and resi 22-37 and name CA``
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        expressions = [str(s).strip() for s in selections if str(s).strip()]
        if len(expressions) < 2:
            self._emit_error(
                "Usage: pair_fit mobile_sel, target_sel [, mobile_sel, target_sel ...]"
            )
            return
        if len(expressions) % 2:
            self._emit_error(
                "pair_fit: selections come in pairs, so an even number is needed "
                f"(got {len(expressions)})"
            )
            return

        mobile_object: str | None = None
        mobile_points: list[np.ndarray] = []
        target_points: list[np.ndarray] = []

        for index in range(0, len(expressions), 2):
            mobile_expr, target_expr = expressions[index], expressions[index + 1]
            try:
                mob_id, mob_xyz = self._selection_coordinates(viewer, mobile_expr)
                _, tgt_xyz = self._selection_coordinates(viewer, target_expr)
            except ValueError as exc:
                self._emit_error(f"pair_fit: {exc}")
                return

            if mob_xyz.shape[0] != tgt_xyz.shape[0]:
                self._emit_error(
                    f"pair_fit: '{mobile_expr}' has {mob_xyz.shape[0]} atoms but "
                    f"'{target_expr}' has {tgt_xyz.shape[0]} -- pairs are matched "
                    "in order, so the counts must agree"
                )
                return

            if mobile_object is None:
                mobile_object = mob_id
            elif mob_id != mobile_object:
                # All the mobile selections move together, so they must name one
                # object; otherwise the fit would be applied to only one of them.
                self._emit_error(
                    "pair_fit: every mobile selection must be in the same object"
                )
                return

            mobile_points.append(mob_xyz)
            target_points.append(tgt_xyz)

        mobile = np.vstack(mobile_points)
        target = np.vstack(target_points)
        if mobile.shape[0] < 3:
            self._emit_error(
                f"pair_fit: at least three atom pairs are needed to fix an "
                f"orientation (got {mobile.shape[0]})"
            )
            return

        try:
            rot, trans, rmsd = compute_kabsch(mobile, target)
        except ValueError as exc:
            self._emit_error(f"pair_fit: {exc}")
            return

        # Those coordinates are the atom array's, in Angstrom, while
        # `apply_transform_to_object` takes its transform in scene units.
        try:
            viewer.apply_transform_to_object(
                rot.T,
                _scene_transform(viewer, mobile_object, rot.T, trans),
                object_id=mobile_object,
            )
        except Exception as exc:
            self._emit_error(f"pair_fit: could not apply the transform: {exc}")
            return

        self._emit_message(
            f"pair_fit: fitted on {mobile.shape[0]} atom pairs "
            f"(RMSD: {rmsd:.3f} Å)"
        )

    def _selection_coordinates(
        self, viewer, expression: str
    ) -> tuple[str, np.ndarray]:
        """Resolve a selection to ``(object_id, coordinates)`` in Angstrom, in order.

        Order matters here in a way it does not elsewhere: ``pair_fit`` matches
        atoms by position within the selection, so the coordinates come back in
        atom-array order rather than as an unordered set.

        Raises
        ------
        ValueError
            If the selection does not resolve, matches nothing, or the object
            carries no coordinates.
        """
        object_id, _, mask = self._resolve_selection_to_atom_mask(viewer, expression)
        entry = getattr(viewer, "_objects", {}).get(object_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None or "xyz" not in (atoms.dtype.names or ()):
            raise ValueError(f"'{expression}' is in an object with no coordinates")
        chosen = np.asarray(mask, dtype=bool)
        if not chosen.any():
            raise ValueError(f"'{expression}' matched no atoms")
        return object_id, np.asarray(atoms["xyz"], dtype=float)[chosen]

    @command("super")
    def super(
        self, mobile: str = "", target: str = "", cutoff: float = 2.0, cycles: int = 5
    ) -> None:
        """Superpose ``mobile`` onto ``target`` (sequence-independent variant)."""
        self._align_or_super(mobile, target, cutoff, cycles, cmd="super")

    def _align_or_super(
        self,
        mobile_expr: str,
        target_expr: str,
        cutoff: float = 2.0,
        cycles: int = 5,
        *,
        cmd: str = "align",
    ) -> None:
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        if not mobile_expr or not target_expr:
            self._emit_error(
                f"Usage: {cmd} mobile_selection, target_selection [, cutoff [, cycles]]"
            )
            return

        try:
            cutoff = float(cutoff)
        except (TypeError, ValueError):
            cutoff = 2.0
        try:
            cycles = int(cycles)
        except (TypeError, ValueError):
            cycles = 5

        try:
            mob_obj, mob_name, mob_indices = self._resolve_selection_to_residue_indices(
                viewer, mobile_expr
            )
            tgt_obj, tgt_name, tgt_indices = self._resolve_selection_to_residue_indices(
                viewer, target_expr
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        # For super, we might want to match by name if indices differ?
        # For now, let's assume sequence-based matching (by index in the selection)
        # but only if number of residues is compatible.

        try:
            mob_coords = viewer.get_residue_positions(
                mob_indices if mob_indices else None, object_id=mob_obj
            )
            tgt_coords = viewer.get_residue_positions(
                tgt_indices if tgt_indices else None, object_id=tgt_obj
            )
        except Exception as exc:
            self._emit_error(f"Failed to access coordinates for {cmd}: {exc}")
            return

        if mob_coords.size == 0 or tgt_coords.size == 0:
            self._emit_error("Selections must contain at least one residue (CA)")
            return

        count = min(mob_coords.shape[0], tgt_coords.shape[0])
        if count < 3:
            self._emit_error(f"{cmd} requires at least three residues in each selection")
            return

        # `get_residue_positions` returns the renderer's coordinates, which are
        # Angstrom times ``_scale_factor``. Both the cutoff the user types and the
        # RMSD reported below are lengths in Angstrom, so the fit runs in Angstrom
        # and the translation is scaled back on the way out. Dividing both sets by
        # the same scalar leaves the Kabsch rotation untouched and scales its
        # translation exactly, so nothing else in the loop has to change.
        scale = float(getattr(viewer, "_scale_factor", 1.0) or 1.0)

        # Subset to matching count
        m_coords = mob_coords[:count] / scale
        t_coords = tgt_coords[:count] / scale

        # Iterative outlier rejection
        current_mask = np.ones(count, dtype=bool)
        final_rmsd = 0.0
        final_rot = np.eye(3)
        final_trans = np.zeros(3)
        final_count = count

        for i in range(cycles + 1):
            subset_count = np.sum(current_mask)
            if subset_count < 3:
                break

            m_sub = m_coords[current_mask]
            t_sub = t_coords[current_mask]

            try:
                rot, trans, rmsd = compute_kabsch(m_sub, t_sub)
            except ValueError as exc:
                self._emit_error(f"Fit failed on cycle {i}: {exc}")
                return

            final_rmsd = rmsd
            final_rot = rot
            final_trans = trans
            final_count = int(subset_count)

            if i < cycles:
                # Calculate all distances after this fit
                m_aligned = (m_coords @ rot) + trans
                dists = np.linalg.norm(m_aligned - t_coords, axis=1)
                new_mask = dists <= cutoff

                # If no change in mask, we converged
                if np.array_equal(new_mask, current_mask):
                    break

                # Ensure we have enough points left
                if np.sum(new_mask) < 3:
                    # Maybe too aggressive? Keep top 50%?
                    sorted_indices = np.argsort(dists)
                    new_mask = np.zeros(count, dtype=bool)
                    half = max(3, count // 2)
                    new_mask[sorted_indices[:half]] = True

                current_mask = new_mask
            else:
                break

        try:
            viewer.apply_transform_to_object(final_rot.T, final_trans * scale, object_id=mob_obj)
        except Exception as exc:
            self._emit_error(f"Failed to apply {cmd} transform: {exc}")
            return

        self._emit_message(
            f"{cmd.capitalize()}: aligned {mob_name} onto {tgt_name} using {final_count}/{count} atoms "
            f"(RMSD: {final_rmsd:.3f} Å)"
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _selection_requests_ca_only(self, expr: str) -> bool:
        text = (expr or "").strip()
        if not text:
            return False

        try:
            tokens = shlex_split(text)
        except Exception:
            return False

        found_ca = False
        other_named = False
        i = 0
        n = len(tokens)
        while i < n:
            tok = tokens[i].lower()
            if tok == "name" and i + 1 < n:
                name_tok = tokens[i + 1].strip().lower()
                if name_tok == "ca":
                    found_ca = True
                else:
                    other_named = True
                i += 2
                continue
            i += 1

        return found_ca and not other_named

    def _gather_atom_coords_for_residues(
        self,
        viewer,
        obj_id: str,
        obj_name: str,
        res_indices: list[int] | None,
    ) -> np.ndarray:
        """Return per-atom coordinates for the given residue indices."""
        try:
            entry = viewer._objects.get(obj_id)  # type: ignore[attr-defined]
        except Exception:
            entry = None
        if entry is None:
            raise ValueError(f"Unknown object in selection: {obj_name}")

        state = getattr(entry, "state", None)
        all_atom_coords = getattr(state, "all_atom_coords", None)
        all_atom_res_ids = getattr(state, "all_atom_res_ids", None)
        residue_ids = getattr(state, "residue_ids", None)

        if all_atom_coords is None or all_atom_res_ids is None or residue_ids is None:
            raise ValueError(
                f"Object {obj_name} does not expose atom-level coordinates for RMSD "
                "(try using '... and name ca' to fall back to CA-based RMSD)."
            )

        try:
            atom_coords_arr = np.asarray(all_atom_coords, dtype=float)
            atom_res_ids_arr = np.asarray(all_atom_res_ids)
            res_ids_arr = np.asarray(residue_ids)
        except Exception:
            raise ValueError(f"Could not access atom/residue ids for object {obj_name}")

        if atom_coords_arr.ndim != 2 or atom_coords_arr.shape[1] != 3:
            raise ValueError(f"Invalid atom coordinate array on object {obj_name}")

        # If no residue indices were given, use all atoms.
        if not res_indices:
            return atom_coords_arr.copy()

        keep_mask = np.zeros(atom_coords_arr.shape[0], dtype=bool)
        for ri in res_indices:
            if ri < 0 or ri >= res_ids_arr.shape[0]:
                continue
            rid = res_ids_arr[ri]
            try:
                keep_mask |= atom_res_ids_arr == rid
            except Exception:
                continue

        if not np.any(keep_mask):
            return np.zeros((0, 3), dtype=float)

        return atom_coords_arr[keep_mask].copy()

    # ------------------------------------------------------------------ #
    # ChimeraX's measurement suite
    #
    # PyMOL is the reference for the GUI and the UX; ChimeraX is the reference
    # for *functionality*, and this is the largest thing it has that ChiMOL had
    # nothing of -- eight `measure_*` commands against ChiMOL's distance, angle
    # and dihedral. These three are the ones computable from what ChiMOL already
    # holds; `measure_correlation` needs a map and is not built.
    # ------------------------------------------------------------------ #
    @command("measure_buriedarea", aliases=("buried_area",))
    def measure_buriedarea(
        self, sel1: Selection = "", sel2: Selection = "", probe: str = "",
    ) -> None:
        """Solvent-accessible area buried between two sets of atoms.

        Transcribed from ChimeraX's ``measure_buriedarea``: the buried area is
        the SAS area of each set alone, minus the area of the two together,
        **halved** -- because each set carries surface at the interface, so the
        interface area is half of what is buried in total.

        The two sets must be disjoint, and each set's own area is computed with
        *only that set present*: an atom in neither set does not occlude, which
        is what makes the number an interface area rather than a difference of
        two crowded surfaces.

        Parameters
        ----------
        sel1, sel2 : str
            The two atom sets. They must not overlap.
        probe : str, optional
            Probe radius in Angstrom; the ``solvent_radius`` setting by default.

        Notes
        -----
        Always the *solvent-accessible* surface, whatever ``dot_solvent`` says.
        A buried van der Waals area is not the quantity anyone means by "buried
        area", and silently answering a different question because a global flag
        happened to be off is the failure mode this file keeps finding.
        """
        from ..analysis.surface_area import atom_surface_areas
        from ..settings import get_setting

        if not str(sel1).strip() or not str(sel2).strip():
            self._emit_error(
                "Usage: measure_buriedarea <selection 1>, <selection 2> [, probe]"
            )
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        try:
            id1, name1, mask1 = self._resolve_selection_to_atom_mask(viewer, str(sel1))
            id2, name2, mask2 = self._resolve_selection_to_atom_mask(viewer, str(sel2))
        except Exception as exc:
            self._emit_error(f"measure_buriedarea: {exc}")
            return
        if id1 != id2:
            self._emit_error(
                "measure_buriedarea: both selections must be in one object "
                f"('{name1}' and '{name2}'); the area between two objects needs "
                "them merged with `create` first"
            )
            return

        mask1 = np.asarray(mask1, dtype=bool)
        mask2 = np.asarray(mask2, dtype=bool)
        overlap = int((mask1 & mask2).sum())
        if overlap:
            self._emit_error(
                f"measure_buriedarea: the two selections share {overlap} atoms; "
                "they must be disjoint or the area is counted twice"
            )
            return
        if not mask1.any() or not mask2.any():
            self._emit_error("measure_buriedarea: a selection matched no atoms")
            return

        entry = getattr(viewer, "_objects", {}).get(id1)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None or "radius" not in (atoms.dtype.names or ()):
            self._emit_error(
                "measure_buriedarea: this structure carries no van der Waals radii"
            )
            return
        xyz = np.asarray(atoms["xyz"], dtype=float)
        radii = np.asarray(atoms["radius"], dtype=float)

        try:
            probe_radius = (
                float(str(probe).strip()) if str(probe).strip()
                else float(get_setting("solvent_radius"))
            )
        except ValueError:
            self._emit_error(f"measure_buriedarea: probe must be a number, got {probe!r}")
            return
        density = int(get_setting("dot_density"))

        def sasa(mask: np.ndarray) -> float:
            """Total SAS area of a subset, with only that subset present."""
            return float(
                atom_surface_areas(
                    xyz[mask], radii[mask],
                    solvent_radius=probe_radius,
                    dot_solvent=True,
                    dot_density=density,
                ).sum()
            )

        area1 = sasa(mask1)
        area2 = sasa(mask2)
        both = sasa(mask1 | mask2)
        buried = 0.5 * (area1 + area2 - both)

        self._emit_message(
            f"measure_buriedarea: {buried:.4g} A^2 buried between "
            f"'{sel1}' and '{sel2}' "
            f"(areas {area1:.4g} + {area2:.4g}, together {both:.4g}; "
            f"probe {probe_radius:g} A)"
        )

    def _atom_masses(self, atoms, chosen: np.ndarray):
        """Masses of the chosen atoms, and how many elements were unrecognised.

        The element column is the authority; where a structure carries none, the
        *atom name* is not guessed from -- PyMOL's own reader derives an element
        when it must, and inventing a second, worse guesser here would make two
        answers to one question.
        """
        from ..analysis.elements import masses_for

        fields = atoms.dtype.names or ()
        if "element" not in fields:
            return np.zeros(int(chosen.sum()), dtype=float), int(chosen.sum())
        symbols = [str(v) for v in np.asarray(atoms["element"])[chosen]]
        return masses_for(symbols)

    @command("measure_weight", aliases=("molecular_weight",))
    def measure_weight(self, sel: Selection = "all") -> None:
        """Molecular weight of a selection, in daltons (ChimeraX ``measure weight``).

        The masses are PyMOL's own table, transcribed by
        ``analysis/make_elements.py`` -- taken from the reference rather than
        from an independent list so that a weight reported here and a weight
        reported there cannot differ by a rounding convention.
        """
        atoms, mask, _object_id = self._selection_atoms(sel, "measure_weight")
        if atoms is None:
            return
        chosen = np.asarray(mask, dtype=bool)
        count = int(chosen.sum())
        if not count:
            self._emit_error(f"measure_weight: '{sel}' matched no atoms")
            return

        weights, unknown = self._atom_masses(atoms, chosen)
        if unknown == count:
            self._emit_error(
                "measure_weight: this structure carries no element symbols, so "
                "there is nothing to weigh"
            )
            return
        caveat = f" ({unknown} of unknown element, not counted)" if unknown else ""
        self._emit_message(
            f"measure_weight: {count} atoms weigh {weights.sum():.1f} Da{caveat}"
        )

    @command("measure_center", aliases=("centroid",))
    def measure_center(self, sel: Selection = "all") -> None:
        """Centre of a selection, in Angstrom (ChimeraX ``measure center``).

        Unweighted: the centre of the atoms, not the centre of mass. ChimeraX
        weights a *map* by density and atoms not at all, so this is the same
        quantity for the atom case, and saying "centre" rather than "centre of
        mass" is the honest name for it.
        """
        atoms, mask, _object_id = self._selection_atoms(sel, "measure_center")
        if atoms is None:
            return
        xyz = np.asarray(atoms["xyz"], dtype=float)[np.asarray(mask, dtype=bool)]
        if xyz.size == 0:
            self._emit_error(f"measure_center: '{sel}' matched no atoms")
            return
        centre = xyz.mean(axis=0)
        self._emit_message(
            f"measure_center: {len(xyz)} atoms centred at "
            f"[{centre[0]:.3f}, {centre[1]:.3f}, {centre[2]:.3f}]"
        )

    @command("measure_inertia", aliases=("inertia",))
    def measure_inertia(self, sel: Selection = "all") -> None:
        """Principal axes and moments of a selection (ChimeraX ``measure inertia``).

        Transcribed from ``measure_inertia.py::moments_of_inertia``: the
        second-moment tensor, divided by the total weight, shifted to the centre
        by the parallel-axis term, then diagonalised with eigenvalues sorted
        ascending and the third axis flipped if needed so the axes are
        right-handed.

        **Mass-weighted**, as ChimeraX is, from the transcribed element table.
        An element the table does not know contributes nothing and is *counted*:
        the message says how many, because a molecular weight quietly missing a
        metal is the kind of wrong number that gets published.
        """
        from ..analysis.elements import masses_for

        atoms, mask, _object_id = self._selection_atoms(sel, "measure_inertia")
        if atoms is None:
            return
        chosen = np.asarray(mask, dtype=bool)
        xyz = np.asarray(atoms["xyz"], dtype=float)[chosen]
        if xyz.shape[0] < 3:
            self._emit_error(
                f"measure_inertia: '{sel}' has {xyz.shape[0]} atoms; three are "
                "needed for a tensor"
            )
            return

        weights, unknown = self._atom_masses(atoms, chosen)
        total = float(weights.sum())
        if total <= 0.0:
            self._emit_error(
                "measure_inertia: no atom carried a recognised element, so the "
                "tensor would have no weight at all"
            )
            return

        # ChimeraX's moments_of_inertia: the weighted second moments, divided by
        # the total weight, then shifted to the centre by the parallel-axis term.
        weighted = weights.reshape(-1, 1) * xyz
        tensor = (xyz * weighted).sum() * np.identity(3) - xyz.T @ weighted
        tensor /= total
        centre = weighted.sum(axis=0) / total
        tensor -= float(np.dot(centre, centre)) * np.identity(3) - np.outer(centre, centre)
        centred = xyz - centre
        values, vectors = np.linalg.eigh(tensor)
        order = np.argsort(values)
        values, axes = values[order], vectors[:, order].T
        if float(np.dot(np.cross(axes[0], axes[1]), axes[2])) < 0:
            axes[2] = -axes[2]

        extents = [
            float(np.ptp(centred @ axis)) for axis in axes
        ]
        caveat = f"; {unknown} atoms of unknown element carried no weight" if unknown else ""
        self._emit_message(
            f"measure_inertia: mass-weighted ({total:.1f} Da){caveat}; "
            f"centre of mass [{centre[0]:.3f}, {centre[1]:.3f}, {centre[2]:.3f}], "
            "moments "
            + ", ".join(f"{v:.4g}" for v in values)
            + "; extents along the axes "
            + ", ".join(f"{e:.3g} A" for e in extents)
        )
