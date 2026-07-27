from __future__ import annotations

import numpy as np

from qtpy import QtCore

from .base import BaseCmd
from .registry import command


class AnimationMixin(BaseCmd):
    """Timeline control and keyframe animation commands."""

    @command("count_states", aliases=("count_frames",))
    def count_states(self, selection: str = "all") -> int:
        """How many coordinate states an object has (PyMOL ``count_states``).

        Parameters
        ----------
        selection : str, optional
            Object to ask about.

        Returns
        -------
        int
            The number of states; 1 for a static structure.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return 0
        try:
            obj_id, _name, _mask = self._resolve_selection_to_atom_mask(
                viewer, selection or "all"
            )
        except Exception:
            # A coarse-grained object has no atoms to select over; the question
            # "how many states" is still meaningful.
            obj_id = viewer.get_active_object_id()
        state = getattr(viewer._objects.get(obj_id), "state", None)
        frames = getattr(state, "frames_raw", None)
        if frames is None:
            frames = getattr(state, "frames", None)
        return 1 if frames is None else int(np.asarray(frames).shape[0])

    @command("get_state")
    def get_state(self) -> int:
        """The state currently displayed, 1-based (PyMOL ``get_state``)."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return 0
        return int(viewer.get_current_frame()) + 1

    @command("intra_fit")
    def intra_fit(self, selection: str = "all", state: str = "1") -> None:
        """Fit every state of an object onto one of them (PyMOL ``intra_fit``).

        The command that makes a trajectory watchable: without it a movie shows
        the molecule tumbling through the box, and the internal motion -- which
        is the thing being looked at -- is buried under rigid-body drift.

        Parameters
        ----------
        selection : str, optional
            Atoms to fit **on**. The whole object moves; only these decide the
            superposition, so ``intra_fit polymer and name CA`` fits on the
            backbone and lets side chains and ligands move freely.
        state : str, optional
            The state to fit onto, 1-based.
        """
        self._intra_superpose(selection, state, report_only=False)

    @command("intra_rms")
    def intra_rms(self, selection: str = "all", state: str = "1") -> list:
        """RMS of every state against one, **without** moving anything.

        PyMOL's ``intra_rms``: the measurement half of ``intra_fit``. Useful for
        finding where in a trajectory something happens.

        Returns
        -------
        list of float
            One RMS per state, in Angstrom; the reference state reads 0.
        """
        return self._intra_superpose(selection, state, report_only=True) or []

    def _intra_superpose(
        self, selection: str, state: str, *, report_only: bool
    ) -> list | None:
        """Shared body: Kabsch-fit every state onto the reference.

        Fitting and measuring differ only in whether the result is written back,
        so they share this rather than growing two implementations that drift.
        """
        verb = "intra_rms" if report_only else "intra_fit"
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return None
        try:
            reference_index = int(str(state).strip() or 1) - 1
        except ValueError:
            self._emit_error(f"{verb}: state must be a whole number")
            return None

        # A coarse-grained model -- which is what chisurf's modelling produces --
        # has coordinates and no atom array, so the selection machinery has
        # nothing to resolve against. Fall back to "every point" rather than
        # refusing: a bead trajectory is exactly the case these commands are
        # wanted for, and `intra_fit` on it is well defined.
        obj_id = obj_name = None
        mask = None
        try:
            obj_id, obj_name, mask = self._resolve_selection_to_atom_mask(
                viewer, selection or "all"
            )
        except Exception as exc:
            if str(selection or "all").strip().lower() not in ("", "all", "*"):
                self._emit_error(f"{verb}: {exc}")
                return None
        if obj_id is None:
            obj_id = viewer.get_active_object_id()
            entry_now = viewer._objects.get(obj_id)
            obj_name = getattr(entry_now, "name", str(obj_id))

        entry = viewer._objects.get(obj_id)
        state_obj = getattr(entry, "state", None)
        frames = getattr(state_obj, "frames_raw", None)
        if frames is None:
            self._emit_error(
                f"{verb}: {obj_name} has a single state; there is nothing to fit"
            )
            return None

        frames = np.asarray(frames, dtype=float)
        n_states = frames.shape[0]
        if not (0 <= reference_index < n_states):
            self._emit_error(
                f"{verb}: state {reference_index + 1} is outside 1..{n_states}"
            )
            return None

        n_points = int(frames.shape[1])
        if mask is None or np.asarray(mask).shape[0] != n_points:
            # No atom array, or a mask that does not describe these points:
            # fit on everything, which is the only well-defined choice.
            chosen = np.ones(n_points, dtype=bool)
        else:
            chosen = np.asarray(mask, dtype=bool)
        if int(chosen.sum()) < 3:
            self._emit_error(
                f"{verb}: '{selection}' matched fewer than three points of "
                f"{obj_name}; a superposition needs three"
            )
            return None

        reference = frames[reference_index][chosen]
        reference_centre = reference.mean(axis=0)
        reference_centred = reference - reference_centre

        rms_values: list[float] = []
        fitted = frames.copy()
        for index in range(n_states):
            moving = frames[index][chosen]
            centre = moving.mean(axis=0)
            rotation = _kabsch(moving - centre, reference_centred)
            aligned = (moving - centre) @ rotation.T
            difference = aligned - reference_centred
            rms_values.append(
                float(np.sqrt((difference * difference).sum() / difference.shape[0]))
            )
            if not report_only:
                fitted[index] = (frames[index] - centre) @ rotation.T + reference_centre

        if report_only:
            self._emit_message(
                f"intra_rms: {n_states} states, "
                f"max {max(rms_values):.3f} A from state {reference_index + 1}"
            )
            return rms_values

        try:
            viewer.set_frames(fitted, object_id=obj_id)
        except Exception as exc:
            self._emit_error(f"intra_fit: could not store the result: {exc}")
            return None
        self._emit_message(
            f"intra_fit: {n_states} states fitted on {int(chosen.sum())} atoms "
            f"of {obj_name}; max {max(rms_values):.3f} A"
        )
        return rms_values

    @command("mset")
    def mset(self, *tokens: str) -> None:
        """Set the movie timeline length (e.g. ``mset 1 x100``)."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        args = list(tokens)
        if not args:
            self._emit_error("Usage: mset specification")
            return

        spec = " ".join(args).strip()
        # Simple parser for "1 x100" or just "100"
        try:
            if "x" in spec.lower():
                parts = spec.lower().split("x")
                count = int(parts[1].strip())
            else:
                count = int(spec)

            viewer.set_total_frames(count)
            self._emit_message(f"Timeline set to {count} frames.")
        except Exception:
            self._emit_error(f"Invalid mset specification: {spec}")

    @command("frame")
    def frame(self, spec: str = "") -> None:
        """Jump the movie timeline to a 1-based frame (also ``+N``/``-N``/``last``)."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        val = str(spec).strip()
        if not val:
            self._emit_error("Usage: frame index")
            return

        try:
            curr = viewer.get_current_frame()
            total = viewer.get_total_frames()

            val_l = val.lower()
            if val_l in {"last", "end"}:
                viewer.set_current_frame(total - 1)
            elif val.startswith("+"):
                viewer.set_current_frame((curr + int(val[1:])) % total)
            elif val.startswith("-"):
                viewer.set_current_frame((curr + int(val)) % total)
            else:
                frame_no = int(val)
                # Ensure 1-based to 0-based conversion and wrapping
                viewer.set_current_frame((frame_no - 1) % total)
        except Exception:
            self._emit_error("Frame index must be an integer (e.g., 10, +1, -1).")

    @command("mplay")
    def mplay(self) -> None:
        """Start movie playback (~30 fps)."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        if viewer._animation_timer is None:
            viewer._animation_timer = QtCore.QTimer(viewer)
            viewer._animation_timer.timeout.connect(self._on_animation_tick)

        # Default ~30fps
        viewer._animation_timer.start(33)
        viewer._animation_running = True
        self._emit_message("Playing movie...")

    @command("mpause")
    def mpause(self) -> None:
        """Pause movie playback."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        if viewer._animation_timer is not None:
            viewer._animation_timer.stop()
        viewer._animation_running = False
        self._emit_message("Movie paused.")

    @command("mstop")
    def mstop(self) -> None:
        """Stop playback and rewind to the first frame."""
        self.mpause()
        window, viewer = self._require_window_and_viewer()
        if viewer is not None:
            viewer.set_current_frame(0)

    def _on_animation_tick(self) -> None:
        window, viewer = self._require_window_and_viewer()
        if viewer is None or not viewer._animation_running:
            return

        curr = viewer.get_current_frame()
        total = viewer.get_total_frames()

        next_frame = (curr + 1) % total
        viewer.set_current_frame(next_frame)

    @command("mdo", mode="raw1")
    def mdo(self, frame: str = "", command: str = "") -> None:
        """Attach a command to a movie frame (``mdo frame, command``)."""
        self._emit_error("mdo is not yet implemented (deferred to Phase 5.2)")

    @command("mview")
    def mview(self, *tokens: str) -> None:
        """Store/interpolate camera keyframes (``mview action [, target]``)."""
        self._emit_error("mview (keyframes) is not yet implemented (deferred to Phase 5.2)")

    @command("mclear")
    def mclear(self) -> None:
        """Clear all animation data."""
        window, viewer = self._require_window_and_viewer()
        if viewer is not None:
            viewer._keyframes.clear()
            viewer.set_total_frames(1)
            self._emit_message("Animation cleared.")


def _kabsch(moving: np.ndarray, target: np.ndarray) -> np.ndarray:
    """The rotation taking ``moving`` onto ``target``, both already centred.

    Kabsch by SVD, with the reflection guard: without correcting for a negative
    determinant the "best fit" can be a mirror image, which superposes the atoms
    beautifully and inverts the chirality of the molecule.
    """
    covariance = moving.T @ target
    u, _s, vt = np.linalg.svd(covariance)
    sign = np.sign(np.linalg.det(vt.T @ u.T))
    correction = np.diag([1.0, 1.0, sign if sign else 1.0])
    return vt.T @ correction @ u.T
