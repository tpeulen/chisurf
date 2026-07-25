from __future__ import annotations

import numpy as np

from ..colors import _PYMOL_COLORS
from .base import BaseCmd
from .registry import command
from .selection_types import Selection


class RenderingMixin(BaseCmd):
    """Background, representation toggles, color modes and per-selection coloring."""

    # User-defined colors (via set_color command)
    _user_colors: dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------ #
    # Background / rep toggles
    # ------------------------------------------------------------------ #
    @command("bg_color", aliases=("bg_colour",))
    def bg_color(self, color: str) -> None:
        """Set the background color (PyMOL ``bg_color <color>``)."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        try:
            rgba = self._parse_color_spec(str(color))
            viewer.set_background_color(rgba)
        except Exception as exc:
            self._emit_error(f"Failed to set background color: {exc}")

    @command("show")
    def show(self, rep: str, sel: Selection = "") -> None:
        """Show a representation (PyMOL ``show rep [, selection]``)."""
        self._toggle_representation(str(rep), str(sel), visible=True)

    @command("hide")
    def hide(self, rep: str, sel: Selection = "") -> None:
        """Hide a representation (PyMOL ``hide rep [, selection]``)."""
        self._toggle_representation(str(rep), str(sel), visible=False)

    @command("as", aliases=("show_as",))
    def show_as(self, rep: str) -> None:
        """Set the primary representation mode (cartoon/lines/sticks/spheres)."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        rep = str(rep).strip().lower()
        if rep in ("cartoon", "ribbon"):
            try:
                viewer.set_representation("cartoon")
            except Exception as exc:
                self._emit_error(f"Failed to set representation: {exc}")
            return
        if rep in ("lines", "wire", "wireframe"):
            try:
                viewer.set_representation("lines")
            except Exception as exc:
                self._emit_error(f"Failed to set representation: {exc}")
            return
        if rep in ("trace", "ca_trace", "ribbon_trace"):
            try:
                viewer.set_representation("ca_trace")
            except Exception as exc:
                self._emit_error(f"Failed to set representation: {exc}")
            return
        if rep in ("spheres", "atoms", "balls", "ball"):
            try:
                viewer.set_representation("atoms")
            except Exception as exc:
                self._emit_error(f"Failed to set representation: {exc}")
            return

        self._emit_error(f"Unsupported representation for 'as': {rep}")

    #: Every representation ``everything`` stands for, in the order applied.
    _ALL_REPRESENTATIONS = ("cartoon", "trace", "lines", "nonbonded", "labels",
                            "atoms", "sticks", "dots", "surface", "metaball")

    def _toggle_representation(self, rep: str, sel: str, *, visible: bool) -> None:
        rep_target = (rep or "").strip().lower()
        if not rep_target:
            self._emit_error("Usage: show/hide <cartoon|trace|atoms|sticks|dots|surface|metaball|plane|everything>[, selection]")
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        selection = (sel or "").strip() or None
        vis = bool(visible)

        # `hide water` is the obvious thing to type and PyMOL rejects it too
        # ("unknown representation"), because the representation slot is not a
        # selection slot. Rather than repeat that, take the hint: if the word is
        # not a representation but does name a selection, treat it as
        # `everything, <selection>` and say what was assumed, so the PyMOL
        # spelling is still learned.
        if rep_target not in self._ALL_REPRESENTATIONS and rep_target not in (
            "everything", "all", "*", "ribbon", "ca_trace", "ribbon_trace",
            "spheres", "balls", "ball", "bonds", "points", "surf", "metaballs",
            "mesh", "plane", "grid", "wire", "wireframe", "nb_spheres", "label",
        ):
            if selection is None and self._names_a_selection(viewer, rep_target):
                self._emit_message(
                    f"'{rep_target}' is a selection, not a representation; "
                    f"showing/hiding everything in it "
                    f"(PyMOL spelling: hide everything, {rep_target})."
                )
                selection = rep_target
                rep_target = "everything"

        if rep_target == "everything":
            for name in self._ALL_REPRESENTATIONS:
                self._toggle_representation(name, selection or "", visible=vis)
            return

        if rep_target in ("all", "*"):
            # If selection given, maybe support it? For now, object-level visibility
            try:
                objects = viewer.list_objects()
            except Exception as exc:
                self._emit_error(f"Failed to list objects: {exc}")
                return
            for obj in objects:
                oid = obj.get("id")
                if not oid:
                    continue
                try:
                    if hasattr(window, "_set_object_visible"):
                        window._set_object_visible(str(oid), vis)
                    else:
                        viewer.set_object_visible(str(oid), vis)
                except Exception:
                    continue
            return

        if selection:
            # 1. Handle cartoon/ribbon (residue-level)
            if rep_target in ("cartoon", "ribbon"):
                try:
                    obj_id, obj_name, res_indices = self._resolve_selection_to_residue_indices(
                        viewer, selection
                    )
                    entry = viewer._objects.get(obj_id)
                    mask = np.asarray(getattr(entry.state, "cartoon_mask"), dtype=bool).copy()
                    for ri in res_indices:
                         if 0 <= ri < mask.shape[0]:
                            mask[ri] = vis
                    entry.state.cartoon_mask = mask
                    viewer._update_view()
                    return
                except Exception as exc:
                    self._emit_error(str(exc))
                    return

            # 2. Handle balls/sticks (atom-level)
            if rep_target in ("atoms", "spheres", "balls", "ball", "sticks", "bonds"):
                try:
                    obj_id, obj_name, atom_mask = self._resolve_selection_to_atom_mask(
                        viewer, selection
                    )
                    entry = viewer._objects.get(obj_id)
                    field = "ball_mask" if rep_target not in ("sticks", "bonds") else "sticks_mask"

                    cur_mask = getattr(entry.state, field)
                    if cur_mask is None or len(cur_mask) != len(atom_mask):
                         cur_mask = np.zeros(len(atom_mask), dtype=bool)
                    else:
                         cur_mask = cur_mask.copy()

                    if vis:
                        cur_mask |= atom_mask
                    else:
                        cur_mask &= ~atom_mask

                    setattr(entry.state, field, cur_mask)
                    viewer._update_view()
                    return
                except Exception as exc:
                    self._emit_error(str(exc))
                    return

        # Fallback to global representation toggle
        try:
            if rep_target in ("cartoon", "ribbon"):
                viewer.set_cartoon_visible(vis)
            elif rep_target in ("trace", "ca_trace", "ribbon_trace"):
                viewer.set_trace_visible(vis)
            elif rep_target in ("lines", "wire", "wireframe"):
                # PyMOL's `lines` is the per-bond wireframe, not the CA trace.
                viewer.set_lines_visible(vis)
            elif rep_target in ("nonbonded", "nb_spheres"):
                viewer.set_nonbonded_visible(vis)
            elif rep_target in ("label", "labels"):
                # Hiding labels keeps the text, as PyMOL's does: you turn them
                # off to read the structure, not to lose what you annotated.
                viewer.set_labels_visible(vis)
            elif rep_target in ("atoms", "spheres", "balls", "ball"):
                viewer.set_atoms_visible_all(vis)
            elif rep_target in ("sticks", "bonds"):
                viewer.set_sticks_visible(vis)
            elif rep_target in ("dots", "points"):
                viewer.set_dots_visible(vis)
            elif rep_target in ("surface", "surf"):
                viewer.set_surface_visible(vis)
            elif rep_target in ("plane", "grid"):
                viewer.set_plane_visible(vis)
            elif rep_target in ("metaball", "metaballs", "mesh"):
                viewer.set_metaballs_visible(vis)
            else:
                self._emit_error(
                    f"Unsupported representation for show/hide: {rep_target}"
                )
                return
        except Exception as exc:
            self._emit_error(f"Failed to update representation '{rep_target}': {exc}")

    def _names_a_selection(self, viewer, token: str) -> bool:
        """Report whether ``token`` resolves to a non-empty atom selection.

        Used only to turn an unknown representation into a helpful action rather
        than an error; a token that selects nothing is left to fail as a
        representation, which is the more useful message in that case.
        """
        try:
            _, _, mask = self._resolve_selection_to_atom_mask(viewer, token)
        except Exception:
            return False
        try:
            return bool(np.asarray(mask, dtype=bool).any())
        except Exception:
            return False

    @command("center")
    def center(self, sel: Selection = "") -> None:
        """Center view on selection or all objects."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        selection = str(sel).strip() or None
        if selection:
            try:
                # Note: this helper is available when mixed into Cmd
                obj_id, _, res_indices = self._resolve_selection_to_residue_indices(viewer, selection) # type: ignore
                if obj_id:
                    viewer.center(res_indices, object_id=obj_id)
                else:
                    self._emit_error(f"Selection '{selection}' did not resolve.")
            except Exception as exc:
                self._emit_error(f"Failed to center: {exc}")
        else:
            viewer.center()

    @command("orient")
    def orient(self, sel: Selection = "") -> None:
        """Orient view on selection."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        selection = str(sel).strip() or None
        if selection:
            try:
                obj_id, _, res_indices = self._resolve_selection_to_residue_indices(viewer, selection) # type: ignore
                if obj_id:
                    viewer.orient(res_indices, object_id=obj_id)
                else:
                    self._emit_error(f"Selection '{selection}' did not resolve.")
            except Exception as exc:
                self._emit_error(f"Failed to orient: {exc}")
        else:
            viewer.orient()

    @command("zoom")
    def zoom(self, sel: Selection = "", buffer: float = 0.0, complete: bool = False) -> None:
        """Zoom view to fit a selection (PyMOL ``zoom [sel [, buffer [, complete]]]``).

        ``buffer`` adds room around the fit; ``complete`` guarantees nothing is
        clipped by fitting the bounding sphere instead of the bounding box.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        selection = str(sel).strip() or None
        if selection:
            try:
                obj_id, _, res_indices = self._resolve_selection_to_residue_indices(viewer, selection)  # type: ignore
                if obj_id:
                    viewer.zoom(res_indices, buffer=float(buffer),
                                complete=bool(complete), object_id=obj_id)
                else:
                    self._emit_error(f"Selection '{selection}' did not resolve.")
            except Exception as exc:
                self._emit_error(f"Failed to zoom: {exc}")
        else:
            viewer.zoom(buffer=float(buffer), complete=bool(complete))

    @command("reset")
    def reset(self) -> None:
        """Reset view to default orientation and center."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        viewer.reset_view()

    @command("turn")
    def turn(self, axis: str, angle: float) -> None:
        """Rotate the camera about a screen axis (PyMOL ``turn axis, angle``)."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None or not hasattr(viewer, "turn"):
            return
        try:
            viewer.turn(str(axis).lower(), float(angle))
        except Exception as exc:
            self._emit_error(f"turn failed: {exc}")

    @command("move")
    def move(self, axis: str, dist: float) -> None:
        """Translate the camera along a screen axis (PyMOL ``move axis, dist``)."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None or not hasattr(viewer, "move"):
            return
        try:
            viewer.move(str(axis).lower(), float(dist))
        except Exception as exc:
            self._emit_error(f"move failed: {exc}")

    @command("clip")
    def clip(self, mode: str, dist: float) -> None:
        """Move the clipping planes (PyMOL ``clip mode, dist``)."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None or not hasattr(viewer, "clip"):
            return
        try:
            viewer.clip(str(mode).lower(), float(dist))
        except Exception as exc:
            self._emit_error(f"clip failed: {exc}")

    @command("rotate")
    def rotate(self, axis: str, angle: float, sel: Selection = "") -> None:
        """Rotate object coordinates (PyMOL ``rotate axis, angle [, selection]``)."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None or not hasattr(viewer, "apply_transform_to_object"):
            return
        axis_map = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
        ax = axis_map.get(str(axis).lower())
        if ax is None:
            self._emit_error("rotate axis must be x, y or z")
            return
        a = np.radians(float(angle))
        kx, ky, kz = ax
        k = np.array([[0.0, -kz, ky], [kz, 0.0, -kx], [-ky, kx, 0.0]])
        rot = np.eye(3) + np.sin(a) * k + (1.0 - np.cos(a)) * (k @ k)
        object_id = self._resolve_object_id(viewer, str(sel) or None)
        try:
            viewer.apply_transform_to_object(rot, np.zeros(3), object_id=object_id)
        except Exception as exc:
            self._emit_error(f"rotate failed: {exc}")

    @command("translate")
    def translate(self, vector: str, sel: Selection = "") -> None:
        """Translate object coordinates (PyMOL ``translate [x,y,z] [, selection]``)."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None or not hasattr(viewer, "apply_transform_to_object"):
            return
        nums = [
            t
            for t in str(vector).replace("[", "").replace("]", "").replace(",", " ").split()
            if t
        ]
        if len(nums) < 3:
            self._emit_error("Usage: translate [x, y, z] [, selection]")
            return
        try:
            vec = np.array([float(nums[0]), float(nums[1]), float(nums[2])], dtype=float)
        except ValueError:
            self._emit_error("translate vector must be three numbers")
            return
        # PyMOL's `translate` is in Angstrom, but apply_transform_to_object
        # works on the scene-unit arrays the renderer holds. Without this the
        # molecule moves by `vector / scale` -- `translate [100,0,0]` shifted it
        # 10 A, which only shows up once the result is written to a file.
        vec = vec * float(getattr(viewer, "_scale_factor", 1.0) or 1.0)
        object_id = self._resolve_object_id(viewer, str(sel) or None)
        try:
            viewer.apply_transform_to_object(np.eye(3), vec, object_id=object_id)
        except Exception as exc:
            self._emit_error(f"translate failed: {exc}")

    def _resolve_object_id(self, viewer, selection: str | None):
        """Resolve a selection/object name to an object id, or the active one."""
        if selection:
            try:
                obj_id, _, _ = self._resolve_selection_to_residue_indices(viewer, selection)  # type: ignore
                if obj_id:
                    return obj_id
            except Exception:
                pass
            try:
                entry = self._find_object_by_name(selection)  # type: ignore
                if entry is not None:
                    return getattr(entry, "id", None) or getattr(entry, "object_id", None)
            except Exception:
                pass
        try:
            return viewer.get_active_object_id()
        except Exception:
            return None

    @command("cartoon")
    def cartoon(self, mode: str, sel: Selection = "") -> None:
        """Set cartoon display type similar to PyMOL ``cartoon``."""
        mode = str(mode).strip().lower()
        from ..config import _DISPLAY_CONFIG
        cfg = _DISPLAY_CONFIG.setdefault("cartoon", {})
        if mode in ("automatic", "auto", "default", "oval", "rect", "rectangle", "arrow", "loop"):
            cfg["style"] = "ribbon"
        elif mode in ("tube", "trace"):
            cfg["style"] = "tube"
        else:
            self._emit_error(f"Unsupported cartoon type: {mode}")
            return
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        try:
            viewer.set_cartoon_visible(True)
            viewer._update_view()
        except Exception:
            pass
        self._emit_message(f"Cartoon type set to {mode}")

    @command("dss")
    def dss(self) -> None:
        """Recompute the secondary structure from the coordinates (PyMOL ``dss``).

        Loading a PDB file adopts its deposited ``HELIX``/``SHEET`` records; this
        throws those away and derives H/E/C from the backbone geometry instead,
        which is what you want when the records are missing, stale, or describe a
        conformation the model has since left.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        assign = getattr(viewer, "recompute_secondary_structure", None)
        if not callable(assign):
            self._emit_error("This viewer cannot recompute secondary structure")
            return
        try:
            n_assigned = int(assign())
        except Exception as exc:
            self._emit_error(f"dss failed: {exc}")
            return

        if not n_assigned:
            self._emit_error("dss: no backbone to assign from")
            return
        try:
            viewer._update_view()
        except Exception:
            pass
        self._emit_message(f"dss: assigned secondary structure for {n_assigned} residues")

    @command("get_view")
    def get_view(self) -> str:
        """Return a copy/pasteable PyMOL-style set_view command."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return ""
        try:
            vals = [float(v) for v in viewer.get_view_state()]
        except Exception as exc:
            self._emit_error(f"Failed to get view: {exc}")
            return ""
        return "set_view (" + ", ".join(f"{v:.9g}" for v in vals) + ")"

    @command("set_view")
    def set_view(self, view: str = "") -> None:
        """Restore an 18-float view tuple (PyMOL ``set_view (...)``).

        Accepts the parenthesised string form from the command line, or a
        list/tuple of 18 numbers from the Python API.
        """
        if isinstance(view, (list, tuple)):
            view = ", ".join(str(v) for v in view)
        joined = str(view).strip()
        if not joined:
            self._emit_error("Usage: set_view (<18 floats>)")
            return
        text = joined.replace("set_view", " ").replace("(", " ").replace(")", " ")
        text = text.replace("\\", " ").replace(",", " ")
        try:
            vals = [float(tok) for tok in text.split()]
        except Exception:
            self._emit_error("set_view requires 18 numeric values")
            return
        if len(vals) != 18:
            self._emit_error("set_view requires 18 numeric values")
            return
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        try:
            viewer.set_view_state(vals)
        except Exception as exc:
            self._emit_error(f"Failed to set view: {exc}")

    # ------------------------------------------------------------------ #
    # Color handling
    # ------------------------------------------------------------------ #
    def _update_sequence_view_safe(self, window) -> None:
        try:
            if window is not None:
                window._update_sequence_view()
        except Exception:
            pass

    @command("color")
    def color(self, spec: str = "", sel: Selection = "") -> None:
        """Set a color mode or per-selection color (PyMOL ``color``)."""
        spec = str(spec).strip()
        selection = str(sel).strip()
        if not spec:
            self._emit_error(
                "Usage: color <single|by_residue|by_ss|by_sequence>[, selection] "
                "or color <color>, selection"
            )
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        # With a selection: either mode+selection or color+selection.
        if selection:
            try:
                mode = self._normalize_color_mode(spec.lower())
            except ValueError:
                mode = None
            if mode is not None:
                try:
                    self._apply_color_mode(viewer, mode, selection=selection)
                except ValueError as exc:
                    self._emit_error(str(exc))
                else:
                    self._update_sequence_view_safe(window)
                return

            rgba = None
            sele_expr = None
            try:
                rgba = self._parse_color_spec(spec)
                sele_expr = selection
            except ValueError:
                # Fallback for the user's original order: color selection, color
                try:
                    rgba = self._parse_color_spec(selection)
                    sele_expr = spec
                except ValueError:
                    self._emit_error(
                        "Usage: color <single|by_residue|by_ss|by_sequence>[, selection] "
                        "or color <color>, selection"
                    )
                    return
            try:
                self._apply_color_to_selection(viewer, sele_expr, rgba)
            except ValueError as exc:
                self._emit_error(str(exc))
            else:
                self._update_sequence_view_safe(window)
            return

        # No selection: mode toggle or uniform color on the active object.
        raw = spec.lower()
        try:
            mode = self._normalize_color_mode(raw)
        except ValueError:
            try:
                self._parse_color_spec(raw)
            except ValueError:
                self._emit_error(
                    f"Unrecognized color '{raw}'. Use a color name, #hex, "
                    "or one of: single, by_residue, by_ss, by_sequence, "
                    "by_element, by_chain, spectrum."
                )
                return
            self.color(raw, "all")  # uniform color to all
            return

        try:
            self._apply_color_mode(viewer, mode, selection=None)
        except ValueError as exc:
            self._emit_error(str(exc))
        else:
            self._update_sequence_view_safe(window)

    @command("spectrum")
    def spectrum(self, expression: str = "", palette: str = "", sel: Selection = "") -> None:
        """Color by a spectrum (rainbow). PyMOL ``spectrum`` (mode part only)."""
        self.color("spectrum")

    @command("set_color", mode="raw1")
    def set_color(self, name: str, color: str) -> None:
        """Define a named color (PyMOL ``set_color name, [r,g,b] | #hex``)."""
        name_part = str(name).strip()
        color_part = str(color).strip()
        if not name_part or not color_part:
            self._emit_error("Usage: set_color <name>, <r,g,b> or <#hex>")
            return
        try:
            rgba = self._parse_color_spec(color_part)
        except (ValueError, KeyError) as exc:
            self._emit_error(f"Cannot parse color value: {exc}")
            return
        self._user_colors[name_part.lower()] = rgba
        self._emit_message(f"Defined color '{name_part}' = {rgba[:3]}")

    @command("get_color_index")
    def get_color_index(self, name: str) -> int | None:
        """Return the internal index for a named color (always 0 for compat)."""
        name = str(name).strip().lower()
        if name in _PYMOL_COLORS or name in self._user_colors:
            # PyMOL returns -1 for unknown colors; Chimol returns 0 for known.
            self._emit_message(f"Color index for '{name}': 0")
            return 0
        self._emit_error(f"Unknown color: {name}")
        return None

    def _normalize_color_mode(self, raw: str) -> str:
        token = (raw or "").strip().lower()
        if token in ("single", "uniform"):
            return "single"
        if token in ("by_residue", "residue", "aa", "by_aa"):
            return "by_residue"
        if token in (
            "by_ss",
            "ss",
            "secondary",
            "by_secondary_structure",
        ):
            return "by_secondary_structure"
        if token in ("by_sequence", "sequence", "seq"):
            return "by_sequence"
        if token in ("by_element", "element", "elem", "cpk", "by_elem"):
            return "by_element"
        if token in ("by_chain", "chain"):
            return "by_chain"
        if token in ("spectrum", "rainbow"):
            return "spectrum"
        raise ValueError(
            "Unsupported color mode. Use one of: "
            "single, by_residue, by_ss, by_sequence, by_element, by_chain, spectrum."
        )

    def _apply_color_mode(self, viewer, mode: str, *, selection: str | None) -> None:
        # Clear any explicit overrides so the mode is visible.
        clear_overrides = getattr(viewer, "clear_color_overrides", None)

        if not selection:
            if callable(clear_overrides):
                try:
                    clear_overrides()
                except Exception:
                    pass
            viewer.set_color_mode(mode)
            self._emit_message(f"Color mode set to {mode}")
            return

        obj_id, obj_name, _ = self._resolve_selection_to_residue_indices(
            viewer, selection
        )
        if not obj_id:
            raise ValueError("Selection did not resolve to an object")

        activate = getattr(viewer, "_activate_object", None)
        if callable(activate):
            try:
                with activate(obj_id):
                    if callable(clear_overrides):
                        try:
                            clear_overrides()
                        except Exception:
                            pass
                    viewer.set_color_mode(mode)
            except Exception as exc:
                raise ValueError(f"Failed to set color mode on {obj_name}: {exc}")
        else:
            try:
                viewer.set_active_object(obj_id)
                if callable(clear_overrides):
                    try:
                        clear_overrides()
                    except Exception:
                        pass
                viewer.set_color_mode(mode)
            except Exception as exc:
                raise ValueError(f"Failed to set color mode on {obj_name}: {exc}")

        self._emit_message(f"Color mode for {obj_name} set to {mode}")

    def _parse_color_spec(self, spec: str) -> np.ndarray:
        text = (spec or "").strip()
        if not text:
            raise ValueError("Empty color specification")

        name = text.lower()

        # Check built-in PyMOL colors
        if name in _PYMOL_COLORS:
            r, g, b = _PYMOL_COLORS[name]
            return np.array([r, g, b, 1.0], dtype=float)

        # Check user-defined colors
        if name in self._user_colors:
            return self._user_colors[name].copy()

        if name.startswith("#") and len(name) in (7, 9):
            try:
                r = int(name[1:3], 16) / 255.0
                g = int(name[3:5], 16) / 255.0
                b = int(name[5:7], 16) / 255.0
                a = (
                    int(name[7:9], 16) / 255.0
                    if len(name) == 9
                    else 1.0
                )
            except Exception:
                raise ValueError(f"Invalid hex color: {spec!r}")
            return np.array([r, g, b, a], dtype=float)

        # Fallback: try comma- or space-separated numeric triplet/quadruplet.
        for sep in (",", " "):
            if sep in text:
                parts = [p for p in text.replace(",", " ").split() if p]
                if not parts:
                    break
                vals: list[float] = []
                for p in parts:
                    try:
                        v = float(p)
                    except Exception:
                        raise ValueError(f"Invalid color component {p!r} in {spec!r}")
                    if v > 1.0:
                        v = v / 255.0
                    vals.append(v)
                if len(vals) == 3:
                    vals.append(1.0)
                if len(vals) != 4:
                    raise ValueError(f"Color spec {spec!r} must have 3 or 4 components")
                return np.asarray(vals, dtype=float)

        raise ValueError(f"Unrecognized color specification: {spec!r}")

    def _apply_color_to_selection(
        self,
        viewer,
        sele_expr: str,
        rgba: np.ndarray,
    ) -> None:
        obj_id, obj_name, atom_mask = self._resolve_selection_to_atom_mask(
            viewer, sele_expr
        )
        if not obj_id:
            raise ValueError("Selection did not resolve to an object")

        try:
            entry = viewer._objects.get(obj_id)
        except Exception:
            entry = None
        if entry is None:
            raise ValueError(f"Unknown object in selection: {obj_name}")

        state = getattr(entry, "state", None)
        if state is None:
            raise ValueError(f"Object {obj_name} has no state")

        all_atom_res_ids = getattr(state, "all_atom_res_ids", None)
        residue_ids = getattr(state, "residue_ids", None)
        all_atom_coords = getattr(state, "all_atom_coords", None)

        if (
            all_atom_res_ids is None
            or residue_ids is None
            or all_atom_coords is None
        ):
            raise ValueError(
                f"Object {obj_name} does not expose atom-level coordinates for coloring"
            )

        try:
            n_atoms = int(np.asarray(all_atom_coords).shape[0])
            atom_mask = np.asarray(atom_mask, dtype=bool)
            if atom_mask.shape[0] != n_atoms:
                 # This shouldn't happen if Evaluator is correct
                 raise ValueError("Internal error: atom mask size mismatch")
        except Exception as exc:
            raise ValueError(f"Invalid atom data for coloring: {exc}")

        # Build/extend per-atom override array with NaN -> no override.
        try:
            cur_atom = np.asarray(state.colors_per_atom_override, dtype=float)
        except Exception:
            cur_atom = None
        if cur_atom is None or cur_atom.ndim != 2 or cur_atom.shape[0] != n_atoms:
            cur_atom = np.full((n_atoms, 4), np.nan, dtype=float)

        rgba4 = np.asarray(rgba, dtype=float).reshape(4)

        # Apply to atoms
        cur_atom[atom_mask, :] = rgba4
        state.colors_per_atom_override = cur_atom

        # Update per-residue override for residues where atoms were colored.
        # This keeps the cartoon view mostly consistent with the atom view.
        try:
            n_res = int(residue_ids.shape[0])
            cur_res = np.asarray(state.colors_per_residue_override, dtype=float)
        except Exception:
            cur_res = None
        if cur_res is None or cur_res.ndim != 2 or cur_res.shape[0] != n_res:
            cur_res = np.full((n_res, 4), np.nan, dtype=float)

        # Find which residue IDs have at least one colored atom
        res_ids_arr = np.asarray(residue_ids)
        atom_res_ids_arr = np.asarray(all_atom_res_ids)
        affected_rid = np.unique(atom_res_ids_arr[atom_mask])

        # Map affected global residue IDs to indices
        affected_res_mask = np.isin(res_ids_arr, affected_rid)
        cur_res[affected_res_mask, :] = rgba4
        state.colors_per_residue_override = cur_res

        try:
            viewer._update_view()
        except Exception:
            pass


