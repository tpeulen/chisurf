from __future__ import annotations

import copy

from .base import BaseCmd
from .registry import command
from .selection_types import Selection


class LifecycleMixin(BaseCmd):
    """Object and session lifecycle commands."""


    @command("create")
    def create(self, name: str = "", sel: Selection = "") -> None:
        """Make a new object from a selection (PyMOL ``create name, selection``).

        The new object sits exactly where the selected atoms are, so it overlays
        the structure it came from; ``extract`` is the same but also removes the
        atoms from the source.
        """
        self._create_or_extract(name, sel, extract=False)

    @command("extract")
    def extract(self, name: str = "", sel: Selection = "") -> None:
        """Move a selection into a new object (PyMOL ``extract``).

        Unlike ``create`` this **removes** the atoms from the source, which is how
        you pull a ligand or a chain out for separate treatment rather than
        duplicating it.
        """
        self._create_or_extract(name, sel, extract=True)

    def _create_or_extract(self, name: str, sel, *, extract: bool) -> None:
        verb = "extract" if extract else "create"
        target = str(name).strip()
        selection = str(sel).strip()
        if not target or not selection:
            self._emit_error(f"Usage: {verb} <name>, <selection>")
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        try:
            source_id, _, mask = self._resolve_selection_to_atom_mask(
                viewer, selection
            )
        except Exception as exc:
            self._emit_error(f"{verb}: {exc}")
            return

        import numpy as np

        if mask is None or not np.asarray(mask, dtype=bool).any():
            self._emit_error(f"{verb}: '{selection}' matched no atoms")
            return

        n = int(np.count_nonzero(np.asarray(mask, dtype=bool)))
        try:
            new_id = viewer.create_from_selection(
                mask, name=target, source_id=source_id, extract=extract
            )
        except Exception as exc:
            self._emit_error(f"{verb} failed: {exc}")
            return

        if new_id is None:
            self._emit_error(f"{verb}: could not build '{target}'")
            return

        # The object list is the window's, not the viewer's, so it has to be told.
        refresh = getattr(window, "_refresh_objects_from_viewer", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass

        moved = "moved" if extract else "copied"
        self._emit_message(f"{verb}: {moved} {n} atoms into '{target}'")

    @command("delete", aliases=("del",))
    def delete(self, *targets_in: str) -> None:
        """Delete objects by id/name, or delete all loaded objects."""
        if not targets_in:
            self._emit_error("Usage: delete <object_name|id|all> [more ...]")
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        targets = [(token or "").strip() for token in targets_in if (token or "").strip()]
        if not targets:
            self._emit_error("Usage: delete <object_name|id|all> [more ...]")
            return

        removed: list[str] = []
        failed: list[str] = []

        if any(target.lower() in ("all", "*") for target in targets):
            try:
                objects = list(viewer.list_objects())
            except Exception as exc:
                self._emit_error(f"Failed to list objects: {exc}")
                return
            for obj in objects:
                oid = str(obj.get("id", "")).strip()
                if not oid:
                    continue
                oname = str(obj.get("name") or oid).strip()
                try:
                    ok = bool(viewer.remove_object(oid))
                except Exception:
                    ok = False
                if ok:
                    removed.append(f"{oname} ({oid})")
                else:
                    failed.append(oname)
            self._named_selections.clear()
        else:
            for target in targets:
                obj = self._find_object_by_name(viewer, target)
                if obj is None:
                    if target.lower() in self._named_selections:
                        del self._named_selections[target.lower()]
                        removed.append(target)
                    else:
                        failed.append(target)
                    continue

                oid = str(obj.get("id", "")).strip()
                oname = str(obj.get("name") or oid).strip()
                if not oid:
                    failed.append(target)
                    continue

                try:
                    ok = bool(viewer.remove_object(oid))
                except Exception:
                    ok = False

                if ok:
                    removed.append(f"{oname} ({oid})")
                else:
                    failed.append(target)

        self._refresh_window_objects(window)

        if removed:
            self._emit_message("Deleted: " + ", ".join(removed))
        if failed:
            self._emit_error("Not found or failed: " + ", ".join(failed))

    @command("reinitialize", aliases=("reinit",))
    def reinitialize(self, what: str = "everything") -> None:
        """Reset Chimol state similar to PyMOL ``reinitialize``."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        what = (what or "everything").strip().lower()
        if what not in ("everything", "settings", "store_defaults", "original_settings", "purge_defaults"):
            self._emit_error("Usage: reinitialize [everything|settings]")
            return

        if what == "everything":
            try:
                for obj in list(viewer.list_objects()):
                    oid = str(obj.get("id", "")).strip()
                    if oid:
                        viewer.remove_object(oid)
            except Exception as exc:
                self._emit_error(f"Failed to delete objects: {exc}")
                return
            self._named_selections.clear()

        self._reset_viewer_display(viewer)
        self._refresh_window_objects(window)
        self._emit_message(f"Reinitialized {what}")

    @command("copy")
    def copy(self, target: str = "", source: str = "") -> None:
        """Create a new object by copying an existing object."""
        target = (target or "").strip()
        source = (source or "").strip()
        if not target or not source:
            self._emit_error("Usage: copy target, source")
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        src = self._find_object_by_name(viewer, source)
        if src is None:
            self._emit_error(f"Unknown source object: {source}")
            return

        src_id = str(src.get("id", "")).strip()
        if not src_id:
            self._emit_error(f"Unknown source object: {source}")
            return

        # Only a *missing* method falls back. Catching AttributeError around the
        # whole call meant any attribute slip inside `copy_object` was read as
        # "this viewer cannot copy", and the fallback then left a second, broken
        # object behind instead of reporting the bug.
        try:
            copy_object = viewer.copy_object
        except AttributeError:
            copy_object = None

        try:
            if copy_object is None:
                new_id = self._copy_object_fallback(viewer, src_id, target)
            else:
                new_id = copy_object(src_id, name=target)
        except Exception as exc:
            self._emit_error(f"Failed to copy {source}: {exc}")
            return

        if not new_id:
            self._emit_error(f"Failed to copy {source}")
            return

        self._refresh_window_objects(window)
        self._emit_message(f"Copied {source} to {target}")

    @command("set_name")
    def set_name(self, old_name: str = "", new_name: str = "") -> None:
        """Rename a loaded object (PyMOL ``set_name old, new``)."""
        old_name = (old_name or "").strip()
        new_name = (new_name or "").strip()
        if not old_name or not new_name:
            self._emit_error("Usage: set_name old_name, new_name")
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        obj = self._find_object_by_name(viewer, old_name)
        if obj is None:
            self._emit_error(f"Unknown object: {old_name}")
            return

        oid = str(obj.get("id", "")).strip()
        entry = getattr(viewer, "_objects", {}).get(oid)
        if entry is None:
            self._emit_error(f"Unknown object: {old_name}")
            return

        entry.name = new_name
        self._refresh_window_objects(window)
        self._emit_message(f"Renamed {old_name} to {new_name}")

    def _copy_object_fallback(self, viewer, source_id: str, target: str):
        entry = getattr(viewer, "_objects", {}).get(source_id)
        if entry is None:
            return None
        if not hasattr(viewer, "_create_object"):
            return None
        new_id = viewer._create_object(name=target)
        new_entry = getattr(viewer, "_objects", {}).get(new_id)
        if new_entry is None:
            return None
        new_entry.state = copy.deepcopy(entry.state)
        new_entry.visible = bool(getattr(entry, "visible", True))
        try:
            viewer.set_active_object(new_id)
        except Exception:
            pass
        try:
            viewer._update_view()
        except Exception:
            pass
        return new_id

    def _reset_viewer_display(self, viewer) -> None:
        for method, value in (
            ("set_cartoon_visible", True),
            ("set_trace_visible", False),
            ("set_atoms_visible_all", False),
            ("set_sticks_visible", False),
            ("set_dots_visible", False),
            ("set_surface_visible", False),
            ("set_metaballs_visible", False),
            ("set_plane_visible", False),
        ):
            func = getattr(viewer, method, None)
            if callable(func):
                try:
                    func(value)
                except Exception:
                    pass

        for method, args in (
            ("clear_color_overrides", ()),
            ("set_color_mode", ("by_sequence",)),
            ("reset_view", ()),
            ("set_selected_residues", ([],)),
        ):
            func = getattr(viewer, method, None)
            if callable(func):
                try:
                    func(*args)
                except Exception:
                    pass

    def _refresh_window_objects(self, window) -> None:
        try:
            if window is not None:
                window._refresh_objects_from_viewer()
        except Exception:
            pass

    @command("split_chains")
    def split_chains(self, prefix: str = "") -> None:
        """Split the active object into one object per chain."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        try:
            active_id = viewer.get_active_object_id()
        except Exception:
            active_id = None
        if active_id is None:
            self._emit_error("No active object for split_chains")
            return

        prefix = (prefix or "").strip() or None

        try:
            viewer.split_chains(prefix=prefix, object_ids=[active_id])
        except Exception as exc:
            self._emit_error(f"Failed to split chains: {exc}")
            return

        self._refresh_window_objects(window)
        self._emit_message("Split chains completed")
