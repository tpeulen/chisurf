from __future__ import annotations

import copy

from .base import BaseCmd
from .registry import command
from .selection_types import Selection


class LifecycleMixin(BaseCmd):
    """Object and session lifecycle commands."""


    @command("activate")
    def activate(self, name: str = "") -> None:
        """Make an object the active one (``activate name``).

        What a click on a name in the object list does now that visibility
        moved onto the eye: the active object is the one the density panel,
        the hierarchy and the per-object commands act on by default.
        """
        _window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        wanted = self._unquote_name(name).strip()
        if not wanted:
            self._emit_error("Usage: activate <object>")
            return
        from .loader import LoaderMixin

        object_id = LoaderMixin._object_id_for_name(viewer, wanted)
        if object_id is None:
            self._emit_error(f"activate: no object called {wanted!r}")
            return
        try:
            viewer.set_active_object(str(object_id))
        except Exception as exc:
            self._emit_error(f"activate: {exc}")
            return
        self._emit_message(f"activate: {wanted} is the active object")

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

    #: PyMOL's group actions, from ``creating.py::group_action_dict``. ``auto``
    #: is resolved before dispatch, and ``ungroup`` is deprecated there in favour
    #: of the standalone command, so neither appears here.
    _GROUP_ACTIONS = (
        "add", "remove", "open", "close", "toggle", "auto",
        "ungroup", "empty", "purge", "excise", "raise",
    )

    @command("group")
    def group(self, name: str = "", members: str = "", action: str = "auto") -> None:
        """Collect objects under one panel row (PyMOL ``group``).

        ``group kinases, 1oky 1pkg`` puts those objects in a group; ``group
        kinases, close`` collapses it. With no members and an existing name the
        default ``auto`` toggles it open or closed, which is what PyMOL does.

        Parameters
        ----------
        name : str
            Group name. It is a row in the object panel, not an object.
        members : str, optional
            Space-separated object names. When this names an *action* instead --
            ``group kinases, close`` -- it is read as one, matching PyMOL's own
            two-meanings-for-one-argument behaviour.
        action : str, optional
            One of ``add``, ``remove``, ``open``, ``close``, ``toggle``,
            ``auto``, ``empty``, ``purge``, ``excise``, ``raise``.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        group_name = str(name).strip().rstrip(",")
        if not group_name:
            self._emit_error("Usage: group <name> [, <members> | <action>]")
            return

        member_text = str(members).strip()
        act = str(action).strip().lower() or "auto"

        # PyMOL lets the second argument carry an action -- `group kinases,
        # close` -- because that is how the menu writes it. Honour that before
        # treating the text as object names, or "close" becomes a missing object.
        if member_text.lower() in self._GROUP_ACTIONS and act == "auto":
            act = member_text.lower()
            member_text = ""

        if act not in self._GROUP_ACTIONS:
            self._emit_error(
                f"Unknown group action '{act}'. Use one of: "
                + ", ".join(self._GROUP_ACTIONS)
            )
            return

        if act == "ungroup":
            self._emit_message(
                "action=ungroup is deprecated; use the 'ungroup' command"
            )
            act = "remove"

        existing = viewer.group_names()
        if act == "auto":
            act = "add" if member_text else ("toggle" if group_name in existing else "add")

        if act in ("open", "close", "toggle"):
            if group_name not in existing:
                self._emit_error(f"No group named '{group_name}'")
                return
            want = (
                True if act == "open"
                else False if act == "close"
                else not viewer.is_group_open(group_name)
            )
            viewer.set_group_open(group_name, want)
            self._refresh_object_panel()
            self._emit_message(
                f"group {group_name} {'opened' if want else 'closed'}"
            )
            return

        if act in ("empty", "purge", "excise"):
            ids = viewer.group_members(group_name)
            if not ids:
                self._emit_error(f"No group named '{group_name}'")
                return
            for oid in ids:
                if act == "empty":
                    viewer.set_object_group(oid, None)
                else:
                    viewer.remove_object(oid)
            self._refresh_object_panel()
            verb = {"empty": "emptied", "purge": "purged", "excise": "excised"}[act]
            self._emit_message(f"group {group_name} {verb} ({len(ids)} objects)")
            return

        if act == "raise":
            ids = viewer.group_members(group_name)
            if not ids:
                self._emit_error(f"No group named '{group_name}'")
                return
            viewer.move_objects_to_edge(ids, top=True)
            self._refresh_object_panel()
            self._emit_message(f"group {group_name} raised")
            return

        # add / remove
        if not member_text:
            self._emit_error(f"Usage: group {group_name}, <members>")
            return
        wanted, missing = self._object_ids_for_names(viewer, member_text)
        if missing:
            self._emit_error("No such object: " + ", ".join(missing))
            return

        target = group_name if act == "add" else None
        rejected = [
            oid for oid in wanted if not viewer.set_object_group(oid, target)
        ]
        if rejected and act == "add":
            self._emit_error(f"'{group_name}' cannot contain itself")
            return
        self._refresh_object_panel()
        verb = "added to" if act == "add" else "removed from"
        self._emit_message(f"{len(wanted)} objects {verb} group {group_name}")

    @command("ungroup")
    def ungroup(self, members: str = "") -> None:
        """Take objects out of whatever group they are in (PyMOL ``ungroup``).

        Parameters
        ----------
        members : str
            Space-separated object names. A *group* name here empties that
            group, since that is the obvious reading and PyMOL accepts it.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        text = str(members).strip()
        if not text:
            self._emit_error("Usage: ungroup <members>")
            return

        released: list[str] = []
        unknown: list[str] = []
        for token in text.split():
            group_ids = viewer.group_members(token)
            if group_ids:
                released.extend(group_ids)
                continue
            obj = self._find_object_by_name(viewer, token)
            if obj is None:
                unknown.append(token)
                continue
            released.append(str(obj.get("id")))

        if unknown:
            self._emit_error("No such object or group: " + ", ".join(unknown))
            return
        for oid in released:
            viewer.set_object_group(oid, None)
        self._refresh_object_panel()
        self._emit_message(f"{len(released)} objects ungrouped")

    @command("order")
    def order(self, names: str = "", sort: str = "", location: str = "current") -> None:
        """Reorder rows in the object panel (PyMOL ``order``).

        ``order 1dn2 1fgh 1rnd`` sets those three into that order; ``order *,
        yes`` sorts everything; ``order 1frg, location=top`` moves one to the
        top.

        Parameters
        ----------
        names : str
            Space-separated object names, or a pattern with ``*``.
        sort : str, optional
            ``yes`` to sort the matched names alphabetically instead of using
            the order given.
        location : str, optional
            ``current`` (default), ``top`` or ``bottom``.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        text = str(names).strip()
        if not text:
            self._emit_error("Usage: order <names> [, <sort> [, <location>]]")
            return

        where = str(location).strip().lower() or "current"
        if where not in ("current", "top", "bottom"):
            self._emit_error("location must be one of: current, top, bottom")
            return
        do_sort = str(sort).strip().lower() in ("yes", "1", "on", "true")

        matched, missing = self._object_ids_for_names(viewer, text, patterns=True)
        if missing:
            self._emit_error("No such object: " + ", ".join(missing))
            return
        if not matched:
            self._emit_error(f"'{text}' matched no objects")
            return

        if do_sort:
            by_name = {
                str(o.get("id")): str(o.get("name", "")) for o in viewer.list_objects()
            }
            matched = sorted(matched, key=lambda oid: by_name.get(oid, "").lower())

        if where == "current":
            viewer.reorder_objects(matched)
        else:
            viewer.move_objects_to_edge(matched, top=(where == "top"))
        self._refresh_object_panel()
        self._emit_message(f"order: {len(matched)} objects, {where}")

    # ------------------------------------------------------------------ #
    # Group/order helpers
    # ------------------------------------------------------------------ #
    def _object_ids_for_names(
        self, viewer, text: str, *, patterns: bool = False
    ) -> tuple[list[str], list[str]]:
        """Resolve space-separated object names to ids, in panel order.

        A group name expands to its members, so every command that takes object
        names takes a group too -- which is what PyMOL means by "a group can be
        used as an argument to a command".

        Parameters
        ----------
        viewer : MolView
            The viewer to resolve against.
        text : str
            Space-separated names.
        patterns : bool, optional
            Allow ``*`` wildcards, as ``order`` does.

        Returns
        -------
        tuple of list of str
            ``(ids in the order the names were given, names that matched
            nothing)``. The *given* order is kept because ``order lig nag``
            means exactly that -- resolving to panel order instead made the
            command a no-op whenever the names were already in panel order,
            which is most of the time. A group or pattern expands to several
            ids, and those take panel order among themselves, since the name
            said nothing about how to arrange them.
        """
        import fnmatch

        objects = viewer.list_objects()
        panel = [str(o.get("id")) for o in objects]
        names = {str(o.get("id")): str(o.get("name", "")) for o in objects}

        found: list[str] = []
        missing: list[str] = []

        def _extend(ids: list[str]) -> None:
            for oid in ids:
                if oid not in found:
                    found.append(oid)

        for token in str(text).split():
            if patterns and ("*" in token or "?" in token):
                hits = [
                    oid for oid in panel
                    if fnmatch.fnmatch(names.get(oid, "").lower(), token.lower())
                ]
                # A pattern matching nothing is not a typo the way a plain name
                # is; `order 1dn2_*, yes` on a session without them is harmless.
                _extend(hits)
                continue
            group_ids = viewer.group_members(token)
            if group_ids:
                _extend([oid for oid in panel if oid in set(group_ids)])
                continue
            obj = self._find_object_by_name(viewer, token)
            if obj is None:
                missing.append(token)
                continue
            _extend([str(obj.get("id"))])
        return found, missing

    def _refresh_object_panel(self) -> None:
        """Ask the window to redraw its object list, if there is one."""
        window = getattr(self, "window", None)
        method = getattr(window, "_refresh_objects_from_viewer", None)
        if callable(method):
            try:
                method()
            except Exception:
                pass

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
    def split_chains(self, prefix: str = "", group: str = "") -> None:
        """Split the active object into one object per chain (PyMOL ``split_chains``).

        Parameters
        ----------
        prefix : str, optional
            Name prefix for the new objects; the source object's name by default.
        group : str, optional
            Collect the new objects into this group, as PyMOL's ``group``
            argument does.

        Notes
        -----
        The source object is **hidden** afterwards, which is what PyMOL does
        (``_self.disable(model)`` at the end of its own ``split_chains``).
        Leaving it visible draws the whole structure on top of every chain copy:
        two cartoons per residue, in the same place, fighting for the depth
        buffer. That is not a subtle difference -- it is what "the cartoons look
        weird after split_chains" is.
        """
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

        before = {str(o.get("id")) for o in viewer.list_objects()}
        prefix = (prefix or "").strip() or None

        try:
            viewer.split_chains(prefix=prefix, object_ids=[active_id])
        except Exception as exc:
            self._emit_error(f"Failed to split chains: {exc}")
            return

        created = [
            str(o.get("id")) for o in viewer.list_objects()
            if str(o.get("id")) not in before
        ]

        # Hide the source, as PyMOL does. Not delete: the split is meant to be
        # undoable by re-enabling it, and the original still carries anything the
        # per-chain copies do not (inter-chain measurements, say).
        if created:
            try:
                if window is not None and hasattr(window, "_set_object_visible"):
                    window._set_object_visible(active_id, False)
                else:
                    viewer.set_object_visible(active_id, False)
            except Exception:
                pass

        target = str(group).strip()
        if target and created:
            for object_id in created:
                viewer.set_object_group(object_id, target)

        self._refresh_window_objects(window)
        self._emit_message(
            f"split_chains: {len(created)} chains"
            + (f" in group {target}" if target and created else "")
            + (" (source hidden)" if created else "")
        )
