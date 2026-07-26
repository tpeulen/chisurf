from __future__ import annotations

from shlex import split as shlex_split

import numpy as np

from ..analysis.metrics import compute_kabsch, compute_rmsd
from .base import BaseCmd
from .registry import command


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
    def distance(self, *seles: str) -> None:
        """Measure distance between two selections (PyMOL ``distance [name,] s1, s2``)."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        args = list(seles)
        if not args:
            self._emit_error("Usage: distance sele1, sele2")
            return

        try:
            meas_name, sele_parts = self._parse_measurement_selections(
                args, expected_count=2, cmd="distance"
            )
        except ValueError as exc:
            self._emit_error(str(exc))
            return

        sele1, sele2 = sele_parts

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
