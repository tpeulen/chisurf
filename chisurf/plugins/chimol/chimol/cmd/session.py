"""Session commands: ``session_save``, ``session_load``, and the ``.pse`` hook.

PyMOL keeps a whole working state in one file and reaches it through ``save`` and
``load`` by extension. Both spellings exist here: the explicit
``session_save``/``session_load`` pair, and the extension dispatch that lets
``save figure.pse`` do what a PyMOL user expects it to.
"""

from __future__ import annotations

from pathlib import Path

from ..renderer.session import (
    SessionError,
    load_session,
    read_manifest,
    save_session,
)
from .base import BaseCmd
from .registry import command

#: Extensions that mean "a whole session" rather than "a structure".
SESSION_SUFFIXES = (".pse", ".cms", ".chimol")


class SessionMixin(BaseCmd):
    """Save and restore everything the viewer holds."""

    @command("session_save", aliases=("save_session",))
    def session_save(self, filename: str = "") -> None:
        """Write the whole session -- objects, colours, camera, scenes, settings.

        Parameters
        ----------
        filename : str
            Destination. ``.pse``, ``.cms`` and ``.chimol`` all mean a session;
            ``save`` routes those extensions here too.

        Notes
        -----
        The file is **chimol's own format**, not PyMOL's ``.pse`` (which is a
        pickle of PyMOL's C structures). Writing to ``.pse`` is allowed because
        that is the extension a PyMOL user will type, and it says so rather than
        letting the file be discovered as unreadable later.
        """
        if not str(filename).strip():
            self._emit_error("Usage: session_save <filename>")
            return
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        path = Path(str(filename)).expanduser()
        if not path.suffix:
            path = path.with_suffix(".cms")
        try:
            result = save_session(viewer, path, scenes=self._scene_store)
        except Exception as exc:
            self._emit_error(f"session_save: {exc}")
            return

        message = f"session_save: {result['objects']} objects -> {path}"
        if path.suffix.lower() == ".pse":
            message += " (chimol's own session format; PyMOL cannot read it)"
        self._emit_message(message)
        if result["skipped"]:
            # Naming what could not be carried beats a session that silently
            # comes back missing something.
            self._emit_message(
                "session_save: not saved -- " + ", ".join(result["skipped"])
            )

    @command("session_load", aliases=("load_session",))
    def session_load(self, filename: str = "") -> None:
        """Restore a session written by ``session_save``, replacing the current one.

        Parameters
        ----------
        filename : str
            A chimol session file.
        """
        if not str(filename).strip():
            self._emit_error("Usage: session_load <filename>")
            return
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        path = Path(str(filename)).expanduser()
        if not path.exists():
            self._emit_error(f"session_load: no such file: {path}")
            return
        try:
            result = load_session(viewer, path, scenes=self._scene_store)
        except SessionError as exc:
            self._emit_error(f"session_load: {exc}")
            return
        except Exception as exc:
            self._emit_error(f"session_load: could not read {path}: {exc}")
            return

        if window is not None:
            for attr in ("_refresh_objects_from_viewer", "_update_sequence_view"):
                method = getattr(window, attr, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
        # After the refresh, not before: rebuilding the panel re-zooms, which
        # replaced the session's camera distance and clip planes with ones
        # derived from the molecule's bounding sphere. The rotation and pivot
        # survived, so the view looked restored while the framing was not.
        if result.get("view"):
            try:
                viewer.set_view_state([float(v) for v in result["view"]])
            except Exception:
                pass
        self._emit_message(f"session_load: {result['objects']} objects from {path}")
        if result["skipped"]:
            self._emit_message(
                "session_load: was not in the session -- "
                + ", ".join(result["skipped"])
            )

    @command("session_info")
    def session_info(self, filename: str = "") -> None:
        """Report what a session file holds, without loading it.

        Parameters
        ----------
        filename : str
            A chimol session file.
        """
        if not str(filename).strip():
            self._emit_error("Usage: session_info <filename>")
            return
        path = Path(str(filename)).expanduser()
        if not path.exists():
            self._emit_error(f"session_info: no such file: {path}")
            return
        try:
            manifest, arrays = read_manifest(path)
        except SessionError as exc:
            self._emit_error(f"session_info: {exc}")
            return

        objects = manifest.get("objects") or []
        names = ", ".join(str(o.get("name")) for o in objects) or "none"
        groups = sorted({o.get("group") for o in objects if o.get("group")})
        self._emit_message(
            f"session_info: version {manifest.get('version')}, "
            f"{len(objects)} objects ({names}), "
            f"{len(manifest.get('scenes') or [])} scenes, "
            f"{len(groups)} groups, {len(arrays)} arrays"
        )

    # ------------------------------------------------------------------ #
    # Extension dispatch, so `save x.pse` / `load x.pse` work
    # ------------------------------------------------------------------ #
    @staticmethod
    def names_a_session(filename: str) -> bool:
        """Whether this filename means a session rather than a structure."""
        return Path(str(filename)).suffix.lower() in SESSION_SUFFIXES
