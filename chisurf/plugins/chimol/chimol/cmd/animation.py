from __future__ import annotations

from qtpy import QtCore

from .base import BaseCmd
from .registry import command


class AnimationMixin(BaseCmd):
    """Timeline control and keyframe animation commands."""

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
