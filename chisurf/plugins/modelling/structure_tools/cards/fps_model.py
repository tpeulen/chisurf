"""The FPS JSON editor's view model: positions, distances, score sets, FlexFit and the raw JSON, without Qt.

The Qt editor kept this state in table cells and panel signals. Here one object owns it: the fps.json document
(:class:`~chisurf.plugins.modelling.fps_json_editor.core.model.FpsJsonModel`, the Qt tool's own model) plus the
rows the user has started but not named yet (the Qt tool's trailing empty row), the structures the positions refer to,
and the accessible volumes computed for them. Every edit goes through a method here, so the window and the tests
drive the same code.

Differences to the Qt panels that fix defects (each has a test):

* renaming a position renames it in the distances that refer to it (the Qt tool deleted those distances);
* clearing a name does not delete the position and its distances (the Qt tool did, silently);
* properties the editor does not show (``pdb_id`` and any unknown key) survive an edit.
"""

from __future__ import annotations

import concurrent.futures
import copy
import json
import re
import threading
from pathlib import Path
from typing import Any, Callable

import numpy as np

from chisurf.plugins.modelling.fps_json_editor.core.colors import DEFAULT_AV_COLOR, normalize_rgba, rgba_to_json
from chisurf.plugins.modelling.fps_json_editor.core.model import FpsJsonModel
from chisurf.plugins.modelling.fps_json_editor.core.naming import default_label_name, unique_label_name

#: The dye parameters a new row starts with (the Qt row's defaults).
POSITION_DEFAULTS: dict[str, Any] = {
    "linker_length": 20.0, "linker_width": 4.5, "radius1": 3.5, "radius2": 0.0, "radius3": 0.0, "body_id": 0,
    "allowed_sphere_radius": 1.5, "simulation_grid_resolution": 1.5, "anchor_atoms": "", "strip_mask": "",
    "contact_volume_thickness": 0.0, "contact_volume_trapped_fraction": -1.0, "min_sphere_volume_fraction": 0.0,
    "chain_weighting": False,
}
DYE_MODELS = ("AV1", "AV0", "AV3", "ROTAMER")
#: The Qt distance type names and what fps.json calls them.
DISTANCE_TYPES = {"dRDA": "RDAMean", "dRDAE": "RDAMeanE", "dRMP": "Rmp", "pRDA": "pRDA"}
DISTANCE_TYPE_NAMES = {v: k for k, v in DISTANCE_TYPES.items()}
ALL_DISTANCES = "All distances"
DISTANCE_DEFAULTS = {"Forster_radius": 52.0, "distance": 50.0, "error_neg": 5.0, "error_pos": 5.0}

#: Colours of the rows' accessible volumes (the Qt tool's palette: new rows take the next one).
DISTINGUISHABLE_COLORS = [
    (0.89, 0.10, 0.11, 0.35), (0.12, 0.47, 0.71, 0.35), (0.20, 0.63, 0.17, 0.35), (1.00, 0.50, 0.00, 0.35),
    (0.42, 0.24, 0.60, 0.35), (0.69, 0.35, 0.16, 0.35), (0.97, 0.51, 0.75, 0.35), (0.00, 0.75, 0.75, 0.35),
    (0.87, 0.87, 0.00, 0.35), (0.50, 0.50, 0.50, 0.35),
]

PDB_ID = re.compile(r"^[A-Za-z0-9]{4}$")


class Rows(list):
    """A table source: a list with a ``revision`` the table reads to notice that a rebuilt list changed."""

    revision = 0


def dye_presets() -> dict[str, dict]:
    """The dye definitions the preset list offers (an installation without the definition file offers none)."""
    try:
        from chisurf.core.structure import av

        return {str(k): dict(v) for k, v in av.dye_definition.items() if isinstance(v, dict)}
    except Exception:  # noqa: BLE001 - no presets, "Custom" only
        return {}


def hex_colour(rgba) -> str:
    r, g, b, _a = normalize_rgba(rgba)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def colour_from_hex(text: str, alpha: float) -> tuple[float, float, float, float]:
    text = text.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"not a colour: {text!r}")
    r, g, b = (int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b, alpha)


def safe_mrc_stem(name: str) -> str:
    """A file-system-safe stem for an AV label (the Qt tool's rule)."""
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip()).strip("._")
    return stem or "av"


class FpsEditor:
    """Positions, distances, score sets, FlexFit and the JSON text of one fps.json document."""

    def __init__(self, fetcher: Callable[[str], str] | None = None) -> None:
        self.doc = FpsJsonModel()
        #: A structure fetched by 4-character ID: ``fetcher(pdb_id) -> path`` (the RCSB download by default).
        self.fetcher = fetcher
        self.status = ""
        self.status_error = False
        self.path = ""                         # the file last loaded or saved
        self.dirty = False
        # unnamed rows (the Qt trailing empty row): id -> record
        self.pos_drafts: dict[str, dict] = {}
        self.dist_drafts: dict[str, dict] = {}
        self._draft_counter = 0
        self.selected_pos = ""
        self.selected_dist = ""
        self.score_filter = ALL_DISTANCES
        self.flexfit_set = ""
        self.selected_residue = -1
        self.selected_bond = -1
        self.json_text = ""
        # structures and AVs
        self.structures: dict[str, Any] = {}
        self.struct_errors: dict[str, str] = {}
        self._fetching: set[str] = set()
        self.av_cache: dict[str, tuple] = {}
        self.av_signatures: dict[str, tuple] = {}
        self.av_state: dict[str, str] = {}      # name -> "computing" | "done" | error text
        self.av_message = "AV: Not computed"
        self._executor = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="fps-av")
        self._lock = threading.Lock()
        self._futures: dict[str, concurrent.futures.Future] = {}
        self._finished: list[tuple] = []
        self.on_change: Callable[[], None] = lambda: None
        self.auto_av = True
        self.rows_pos: Rows = Rows()
        self.rows_dist: Rows = Rows()
        self.rows_res: Rows = Rows()
        self.rows_bond: Rows = Rows()
        self.sync()

    # ── status ────────────────────────────────────────────────────────────

    def say(self, text: str, error: bool = False) -> None:
        self.status, self.status_error = text, error

    # ── names ─────────────────────────────────────────────────────────────

    def _new_draft_id(self) -> str:
        self._draft_counter += 1
        return f"#new{self._draft_counter}"

    @staticmethod
    def is_draft(rid: str) -> bool:
        return rid.startswith("#")

    def _pos(self, rid: str) -> dict | None:
        return self.pos_drafts.get(rid) if self.is_draft(rid) else self.doc.positions.get(rid)

    def _dist(self, rid: str) -> dict | None:
        return self.dist_drafts.get(rid) if self.is_draft(rid) else self.doc.distances.get(rid)

    @property
    def position_names(self) -> list[str]:
        return list(self.doc.positions)

    @property
    def score_set_names(self) -> list[str]:
        return list(self.doc.score_sets)

    # ── document ──────────────────────────────────────────────────────────

    def load(self, path: str) -> bool:
        """Read an fps.json file; a failure leaves the document as it was."""
        try:
            fresh = FpsJsonModel()
            fresh.load_file(str(path))
        except Exception as exc:  # noqa: BLE001 - reported on the status line
            self.say(f"Failed to load the JSON file: {exc}", True)
            return False
        self.doc = fresh
        self.pos_drafts.clear()
        self.dist_drafts.clear()
        self.selected_pos = self.selected_dist = ""
        self.score_filter = ALL_DISTANCES
        self.path = str(path)
        self.dirty = False
        self.av_cache.clear()
        self.av_signatures.clear()
        self.av_state.clear()
        self.say(f"Loaded {Path(path).name}: {len(fresh.positions)} positions, {len(fresh.distances)} distances.")
        self._changed(schedule_all=True)
        return True

    def save(self, path: str) -> bool:
        """Write the document (the Qt tool wrote ``sort_keys`` JSON with four spaces)."""
        try:
            self.doc.save_file(str(path))
        except Exception as exc:  # noqa: BLE001
            self.say(f"Failed to save the JSON file: {exc}", True)
            return False
        self.path = str(path)
        self.dirty = False
        self.say(f"Saved {Path(path).name}.")
        return True

    def clear(self) -> None:
        """Forget everything (the caller has asked the user first)."""
        self.doc = FpsJsonModel()
        self.pos_drafts.clear()
        self.dist_drafts.clear()
        self.selected_pos = self.selected_dist = ""
        self.score_filter = ALL_DISTANCES
        self.flexfit_set = ""
        self.av_cache.clear()
        self.av_signatures.clear()
        self.av_state.clear()
        self.dirty = False
        self.say("Cleared.")
        self._changed()

    def apply_json_text(self) -> bool:
        """The Update button: rebuild the model from the JSON text (invalid text changes nothing)."""
        try:
            payload = json.loads(self.json_text)
        except json.JSONDecodeError as exc:
            self.say(f"The editor content is not valid JSON: {exc}", True)
            return False
        if not isinstance(payload, dict):
            self.say("The editor content is not valid JSON: the document must be an object.", True)
            return False
        self.doc.fps_json_payload = payload
        self.pos_drafts.clear()
        self.dist_drafts.clear()
        self.dirty = True
        self.say("Updated the editor from the JSON text.")
        self._changed(schedule_all=True)
        return True

    def _changed(self, schedule_all: bool = False, only: str | None = None) -> None:
        """Rebuild rows and the JSON text; optionally queue accessible volumes."""
        self.sync()
        if self.auto_av:
            if schedule_all:
                for name in self.doc.positions:
                    self.schedule_av(name)
            elif only:
                self.schedule_av(only)
        self.on_change()

    def sync(self, json_text: bool = True) -> None:
        """Rebuild the table rows (and the JSON text, unless only a result arrived that is not in the document)."""
        if json_text:
            self.json_text = json.dumps(self.doc.fps_json_payload, sort_keys=True, indent=4, separators=(",", ": "))
        self.rows_pos = self._position_rows()
        self.rows_dist = self._distance_rows()
        self.rows_res, self.rows_bond = self._flexfit_rows()

    # ── positions ─────────────────────────────────────────────────────────

    def colour_of(self, rid: str) -> tuple[float, float, float, float]:
        """The colour of a position's volume: its ``av_color``, else the next one of the palette (as the Qt rows,
        the file is not changed by showing it)."""
        params = self._pos(rid) or {}
        if params.get("av_color") is not None:
            return normalize_rgba(params["av_color"])
        names = [*self.doc.positions, *self.pos_drafts]
        index = names.index(rid) if rid in names else 0
        return DISTINGUISHABLE_COLORS[index % len(DISTINGUISHABLE_COLORS)]

    def _position_rows(self) -> Rows:
        rows = Rows()
        rows.revision = getattr(self.rows_pos, "revision", 0) + 1
        entries = [(name, params) for name, params in self.doc.positions.items()]
        entries += list(self.pos_drafts.items())
        for rid, params in entries:
            volume = ""
            if rid in self.av_cache:
                coords, _mean, step, _c = self.av_cache[rid]
                volume = f"{len(coords) * step ** 3:.0f}"
            elif self.av_state.get(rid) == "computing":
                volume = "..."
            rows.append({
                "row": rid, "name": "" if self.is_draft(rid) else rid, "show": bool(params.get("visible", True)),
                "pdb": _short_path(str(params.get("pdb_path") or params.get("pdb_id") or "")),
                "chain": str(params.get("chain_identifier", "")),
                "res": str(params.get("residue_seq_number", "")) if params.get("residue_seq_number", "") != "" else "",
                "atom": str(params.get("atom_name", "")),
                "preset": str(params.get("dye_preset", "Custom")),
                "dye_model": str(params.get("simulation_type", "AV1")),
                "color": hex_colour(self.colour_of(rid)),
                "volume": volume,
            })
        return rows

    def add_position_row(self) -> str:
        """The Add Row button: an empty row that becomes a position when it has a name."""
        rid = self._new_draft_id()
        index = len(self.doc.positions) + len(self.pos_drafts)
        self.pos_drafts[rid] = {
            **POSITION_DEFAULTS, "pdb_path": "", "chain_identifier": "", "residue_seq_number": "", "atom_name": "",
            "simulation_type": "AV1", "dye_preset": "Custom", "visible": True,
            "av_color": list(DISTINGUISHABLE_COLORS[index % len(DISTINGUISHABLE_COLORS)]),
        }
        self.selected_pos = rid
        self.say("Added an empty row: give it a name, or a chain and residue.")
        self._changed()
        return rid

    def position_field(self, rid: str, key: str, default: Any = None) -> Any:
        params = self._pos(rid)
        return default if params is None else params.get(key, POSITION_DEFAULTS.get(key, default))

    def set_position(self, rid: str, key: str, value: Any) -> bool:
        """Change one property of a position row (``name``, ``pdb_path``, ``chain_identifier`` ... or a dye number)."""
        params = self._pos(rid)
        if params is None:
            return False
        if key == "name":
            return self._rename_position(rid, str(value).strip())
        if key == "pdb_path":
            value = str(value).strip()
            params["pdb_path"] = value
            params.pop("pdb_id", None)
            self._after_pdb(rid)
            self._auto_name(rid)
            self._commit_position(rid)
            return True
        if key == "residue_seq_number":
            text = str(value).strip()
            if text and not text.lstrip("-").isdigit():
                self.say(f"Residue must be a whole number, not {text!r}.", True)
                return False
            params[key] = int(text) if text else ""
            self._after_residue(rid)
        elif key == "chain_identifier":
            params[key] = str(value).strip()
            self._after_chain(rid)
        elif key == "atom_name":
            params[key] = str(value).strip()
        elif key == "visible":
            params[key] = bool(value)
        elif key == "av_color":
            params[key] = rgba_to_json(value)
        elif key in ("dye_preset", "simulation_type"):
            params[key] = str(value)
            if key == "dye_preset":
                self._apply_preset(rid, str(value))
        elif key in POSITION_DEFAULTS:
            params[key] = type(POSITION_DEFAULTS[key])(value) if not isinstance(POSITION_DEFAULTS[key], bool) \
                else bool(value)
        else:
            params[key] = value
        self._auto_name(rid)
        self._commit_position(rid)
        return True

    def _apply_preset(self, rid: str, preset: str) -> None:
        definition = dye_presets().get(preset)
        params = self._pos(rid)
        if preset == "Custom" or not definition or params is None:
            return
        for key in ("linker_length", "linker_width", "radius1", "radius2", "radius3"):
            params[key] = float(definition.get(key, POSITION_DEFAULTS[key]))
        params["simulation_type"] = str(definition.get("simulation_type", "AV1"))

    def _auto_name(self, rid: str) -> None:
        """Name an unnamed draft from its chain and residue (``A132``), unique among the positions."""
        if not self.is_draft(rid):
            return
        params = self.pos_drafts.get(rid)
        if params is None:
            return
        base = default_label_name(params.get("chain_identifier"), params.get("residue_seq_number"))
        if base:
            self._rename_position(rid, unique_label_name(base, self.doc.positions))

    def _rename_position(self, rid: str, new: str) -> bool:
        params = self._pos(rid)
        if params is None:
            return False
        if not new:
            if self.is_draft(rid):
                return True
            self.say("A position needs a name; use Delete to remove it.", True)
            return False
        if new == rid:
            return True
        if new in self.doc.positions:
            self.say(f"There is already a position named {new!r}.", True)
            return False
        if self.is_draft(rid):
            del self.pos_drafts[rid]
            self.doc.positions[new] = params
        else:
            positions = {(new if k == rid else k): v for k, v in self.doc.positions.items()}
            self.doc.positions = positions
            for dist in self.doc.distances.values():
                for field in ("position1_name", "position2_name"):
                    if dist.get(field) == rid:
                        dist[field] = new
            for cache in (self.av_cache, self.av_signatures, self.av_state):
                if rid in cache:
                    cache[new] = cache.pop(rid)
            self._refresh_distance_names()
        if self.selected_pos == rid:
            self.selected_pos = new
        self.dirty = True
        self._changed(only=new)
        return True

    def _refresh_distance_names(self) -> None:
        """Distances are named ``<label1>_<label2>``: keep the keys in step after a position was renamed."""
        renamed = {}
        for key, dist in self.doc.distances.items():
            want = f"{dist.get('position1_name', '')}_{dist.get('position2_name', '')}"
            renamed[key] = want if want not in self.doc.distances or want == key else key
        if all(k == v for k, v in renamed.items()):
            return
        self.doc.distances = {renamed[k]: v for k, v in self.doc.distances.items()}
        for group in self.doc.score_sets.values():
            if isinstance(group, dict):
                group["distances"] = [renamed.get(d, d) for d in group.get("distances", [])]
        if self.selected_dist in renamed:
            self.selected_dist = renamed[self.selected_dist]

    def _commit_position(self, rid: str) -> None:
        self.dirty = True
        rid = self.selected_pos if rid not in self.doc.positions and rid not in self.pos_drafts else rid
        self._changed(only=rid if rid in self.doc.positions else None)

    def delete_position(self, rid: str) -> bool:
        """Remove a row; for a named position also the distances that use it (as the Qt tool does)."""
        if self.is_draft(rid):
            self.pos_drafts.pop(rid, None)
        elif rid in self.doc.positions:
            self.doc.remove_position(rid)
            for cache in (self.av_cache, self.av_signatures, self.av_state):
                cache.pop(rid, None)
        else:
            return False
        if self.selected_pos == rid:
            self.selected_pos = ""
        self.dirty = True
        self.say(f"Removed {rid}." if not self.is_draft(rid) else "Removed the empty row.")
        self._changed()
        return True

    def toggle_position(self, rid: str) -> None:
        params = self._pos(rid)
        if params is not None:
            self.set_position(rid, "visible", not params.get("visible", True))

    # ── structures ────────────────────────────────────────────────────────

    def structure(self, pdb_val: str):
        """The structure behind a path or a PDB ID, or None (the reason is in :attr:`struct_errors`)."""
        pdb_val = (pdb_val or "").strip()
        if not pdb_val:
            return None
        if pdb_val in self.structures:
            return self.structures[pdb_val]
        if PDB_ID.match(pdb_val) and not Path(pdb_val).exists():
            self._fetch(pdb_val)
            return None
        if Path(pdb_val).is_file():
            try:
                import chisurf.core.structure as cs_structure

                self.structures[pdb_val] = cs_structure.Structure(pdb_val)
                self.struct_errors.pop(pdb_val, None)
                return self.structures[pdb_val]
            except Exception as exc:  # noqa: BLE001
                self.struct_errors[pdb_val] = f"Failed to load structure from path '{pdb_val}': {exc}"
                self.say(self.struct_errors[pdb_val], True)
                return None
        self.struct_errors[pdb_val] = f"No such file: {pdb_val}"
        return None

    def _fetch(self, pdb_id: str) -> None:
        """Download a PDB ID off the UI thread; the structure is there on a later frame."""
        if pdb_id in self._fetching or pdb_id in self.struct_errors:
            return
        self._fetching.add(pdb_id)
        self.say(f"Downloading PDB ID '{pdb_id}'...")

        def work() -> None:
            try:
                if self.fetcher is not None:
                    path = self.fetcher(pdb_id)
                else:
                    from chisurf.plugins.modelling.fps_json_editor.core.pdb import download_pdb_file

                    path = download_pdb_file(pdb_id.lower())
                import chisurf.core.structure as cs_structure

                struct = cs_structure.Structure(str(path))
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._finished.append(("fetch", pdb_id, None, f"Failed to fetch/load PDB ID '{pdb_id}': {exc}"))
                return
            with self._lock:
                self._finished.append(("fetch", pdb_id, struct, str(path)))

        self._executor.submit(work)

    def chains(self, pdb_val: str) -> list[str]:
        struct = self.structure(pdb_val)
        if struct is None or struct.atoms is None:
            return []
        return sorted({str(c) for c in struct.atoms["chain"]})

    def residues(self, pdb_val: str, chain: str) -> list[int]:
        struct = self.structure(pdb_val)
        if struct is None or struct.atoms is None or not chain:
            return []
        mask = struct.atoms["chain"] == chain
        return sorted({int(r) for r in struct.atoms["res_id"][mask]})

    def atoms(self, pdb_val: str, chain: str, res) -> list[str]:
        struct = self.structure(pdb_val)
        if struct is None or struct.atoms is None or not chain or res in ("", None):
            return []
        mask = (struct.atoms["chain"] == chain) & (struct.atoms["res_id"] == int(res))
        return sorted({str(a) for a in struct.atoms["atom_name"][mask]})

    def _after_pdb(self, rid: str) -> None:
        """A new structure: pick a chain, residue and atom from it the way the Qt combos did (first, ``CB``/``CA``)."""
        params = self._pos(rid)
        struct = self.structure(params.get("pdb_path", ""))
        if struct is None:
            return
        chains = self.chains(params["pdb_path"])
        if chains and params.get("chain_identifier") not in chains:
            params["chain_identifier"] = chains[0]
        self._after_chain(rid)

    def _after_chain(self, rid: str) -> None:
        params = self._pos(rid)
        residues = self.residues(params.get("pdb_path", ""), params.get("chain_identifier", ""))
        if residues and params.get("residue_seq_number", "") not in residues:
            params["residue_seq_number"] = residues[0]
        self._after_residue(rid)

    def _after_residue(self, rid: str) -> None:
        params = self._pos(rid)
        names = self.atoms(params.get("pdb_path", ""), params.get("chain_identifier", ""),
                           params.get("residue_seq_number", ""))
        if names and params.get("atom_name", "") not in names:
            params["atom_name"] = "CB" if "CB" in names else "CA" if "CA" in names else names[0]

    # ── accessible volumes ────────────────────────────────────────────────

    def _av_inputs(self, rid: str) -> tuple | None:
        params = self.doc.positions.get(rid)
        if params is None:
            return None
        pdb = str(params.get("pdb_path") or params.get("pdb_id") or "").strip()
        chain, res, atom = (str(params.get("chain_identifier", "")), params.get("residue_seq_number", ""),
                            str(params.get("atom_name", "")))
        if not pdb:
            self.av_message = f"AV: Not computed (no PDB path/ID for '{rid}')"
            return None
        if not (chain and str(res) != "" and atom):
            self.av_message = f"AV: Not computed ('{rid}' needs Chain, Residue, and Atom)"
            return None
        try:
            res_id = int(res)
        except (TypeError, ValueError):
            self.av_message = f"AV: Not computed (invalid residue seq number '{res}' for '{rid}')"
            return None
        if PDB_ID.match(pdb) and not Path(pdb).exists():
            struct = self.structure(pdb)
            if struct is None:
                return None
            pdb = str(struct.filename)
        elif not Path(pdb).is_file():
            self.av_message = f"AV: Not computed (failed to load structure for '{rid}' with PDB '{pdb}')"
            return None
        radii = (float(params.get("radius1", 3.5)), float(params.get("radius2", 0.0)),
                 float(params.get("radius3", 0.0)))
        return (pdb, chain, res_id, atom, str(params.get("simulation_type", "AV1")),
                float(params.get("linker_length", 20.0)), float(params.get("linker_width", 4.5)), radii,
                float(params.get("simulation_grid_resolution", 1.5)))

    def schedule_av(self, rid: str, force: bool = False) -> bool:
        """Queue the accessible volume of a position (nothing when it is up to date or lacks inputs)."""
        inputs = self._av_inputs(rid)
        if inputs is None:
            return False
        signature = tuple(inputs)
        if not force and self.av_signatures.get(rid) == signature and rid in self.av_cache:
            return False
        self.av_signatures[rid] = signature
        self.av_state[rid] = "computing"
        self.av_message = f"AV: Computing {rid}..."
        pdb, chain, res_id, atom, _model, length, width, radii, step = inputs
        source = {"chain_identifier": chain, "residue_seq_number": res_id, "atom_name": atom}

        def work() -> None:
            try:
                from chisurf.plugins.modelling.fret.core import av

                atoms_xyzr = av.load_structure_with_vdw(pdb)
                xyz = av._find_attachment_point(atoms_xyzr, chain, res_id, atom, pdb_path=pdb)
                if xyz is None:
                    raise ValueError(f"Attachment point '{chain}:{res_id}:{atom}' not found in {pdb}")
                clean = av._strip_residue_atoms(atoms_xyzr, chain, res_id, pdb_path=pdb)
                volume = av.compute_av(atoms=clean, source_xyz=xyz, linker_length=length, linker_width=width,
                                       radii=radii, disc_step=step, pdb_path=pdb, source_info=source)
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._finished.append(("av", rid, signature, f"AV calculation failed for {rid}: {exc}"))
                return
            with self._lock:
                self._finished.append(("av", rid, signature, volume))

        self._futures[rid] = self._executor.submit(work)
        return True

    def compute_all(self) -> int:
        """The Compute AVs button: recompute every named position."""
        n = sum(1 for name in list(self.doc.positions) if self.schedule_av(name, force=True))
        if not n and not self.doc.positions:
            self.say("No positions to compute.", True)
        self.sync()
        return n

    @property
    def busy(self) -> bool:
        return any(not f.done() for f in self._futures.values()) or bool(self._fetching)

    def poll(self) -> bool:
        """Take finished work (AV results, fetched structures); True when something changed."""
        with self._lock:
            done, self._finished = self._finished, []
        changed = False
        for kind, key, extra, payload in done:
            if kind == "fetch":
                self._fetching.discard(key)
                if extra is None:
                    self.struct_errors[key] = payload
                    self.say(payload, True)
                else:
                    self.structures[key] = extra
                    self.say(f"Downloaded and loaded PDB ID '{key}'.")
                    for rid, params in list(self.doc.positions.items()) + list(self.pos_drafts.items()):
                        if str(params.get("pdb_path") or "") == key:
                            self._after_pdb(rid)
                            self._auto_name(rid)
                    self._changed(schedule_all=True)
                changed = True
                continue
            rid, signature = key, extra
            if rid not in self.doc.positions or self.av_signatures.get(rid) != signature:
                continue                              # the row was removed or edited while it ran
            if isinstance(payload, str):
                self.av_state[rid] = payload
                self.av_message = payload
                self.say(payload, True)
            else:
                color = self.colour_of(rid)
                mean = np.asarray(payload.mean_position, dtype=float)
                self.av_cache[rid] = (np.asarray(payload.points), mean, float(payload.grid_step), color)
                self.av_state[rid] = "done"
                volume = payload.n_points * payload.grid_step ** 3
                self.av_message = f"AV: Calculated {rid} (Vol: {volume:.1f} Å³, Points: {payload.n_points})"
            changed = True
        if changed:
            self.sync(json_text=False)
        return changed

    def wait(self, timeout: float = 60.0) -> bool:
        """Block until queued work is in (tests, headless use)."""
        import time

        end = time.monotonic() + timeout
        while self.busy and time.monotonic() < end:
            time.sleep(0.01)
        self.poll()
        return not self.busy

    def computed_names(self, selected: str = "") -> list[str]:
        """The computed AVs of the selected position, else of every position."""
        if selected and selected in self.av_cache:
            return [selected]
        return [n for n in self.doc.positions if n in self.av_cache]

    def write_mrc(self, name: str, path: str | Path) -> Path:
        import IMP.bff as bff

        coords, _mean, step, _color = self.av_cache[name]
        return Path(bff.write_points_mrc(str(path), np.ascontiguousarray(coords, dtype=np.float64), float(step)))

    # ── distances ─────────────────────────────────────────────────────────

    def _distance_rows(self) -> Rows:
        rows = Rows()
        rows.revision = getattr(self.rows_dist, "revision", 0) + 1
        sets = self.doc.score_sets
        if self.score_filter != ALL_DISTANCES and self.score_filter in sets:
            keys = [k for k in sets[self.score_filter].get("distances", []) if k in self.doc.distances]
        else:
            keys = list(self.doc.distances)
        entries = [(k, self.doc.distances[k]) for k in keys] + list(self.dist_drafts.items())
        for rid, params in entries:
            dtype = DISTANCE_TYPE_NAMES.get(params.get("distance_type", "RDAMean"), "dRDA")
            if dtype == "pRDA":
                details = f"R0 {params.get('Forster_radius', 52.0):g}, {len(params.get('rda', []))} points"
            else:
                details = (f"R0 {params.get('Forster_radius', 52.0):g}, d {params.get('distance', 50.0):g} "
                           f"(-{params.get('error_neg', 5.0):g}/+{params.get('error_pos', 5.0):g})")
            rows.append({
                "row": rid, "name": "" if self.is_draft(rid) else rid, "show": bool(params.get("visible", True)),
                "label1": str(params.get("position1_name", "")), "label2": str(params.get("position2_name", "")),
                "type": dtype, "details": details, "score_set": self.distance_set(rid),
            })
        return rows

    def distance_set(self, rid: str) -> str:
        """The score set the row shows: the first one that lists it (the Qt combo)."""
        if self.is_draft(rid):
            return str(self.dist_drafts.get(rid, {}).get("_set", ""))
        for name, group in self.doc.score_sets.items():
            if isinstance(group, dict) and rid in group.get("distances", []):
                return name
        return ""

    def add_distance_row(self) -> str:
        rid = self._new_draft_id()
        self.dist_drafts[rid] = {**DISTANCE_DEFAULTS, "position1_name": "", "position2_name": "",
                                 "distance_type": "RDAMean", "visible": True, "_set": ""}
        self.selected_dist = rid
        self.say("Added an empty row: choose two labels.")
        self._changed()
        return rid

    def set_distance(self, rid: str, key: str, value: Any) -> bool:
        """Change a distance row: ``position1_name``, ``position2_name``, ``type`` (a Qt type name), ``score_set``,
        ``visible``, or a detail (``Forster_radius``, ``distance``, ``error_neg``, ``error_pos``)."""
        params = self._dist(rid)
        if params is None:
            return False
        if key == "type":
            params["distance_type"] = DISTANCE_TYPES.get(str(value), "RDAMean")
        elif key == "score_set":
            return self._set_distance_set(rid, str(value))
        elif key in ("Forster_radius", "distance", "error_neg", "error_pos"):
            params[key] = float(value)
        else:
            params[key] = value
        self.dirty = True
        return self._commit_distance(rid)

    def _commit_distance(self, rid: str) -> bool:
        params = self._dist(rid)
        l1, l2 = params.get("position1_name", ""), params.get("position2_name", "")
        if not l1 or not l2:
            self._changed()
            return True
        if l1 == l2:
            self.say("Label 1 and Label 2 must be different.", True)
            self._changed()
            return False
        new = f"{l1}_{l2}"
        if self.is_draft(rid):
            group = params.pop("_set", "")
            del self.dist_drafts[rid]
            if new in self.doc.distances:
                self.say(f"The distance {new} already exists.", True)
                self.dist_drafts[rid] = params
                self._changed()
                return False
            self.doc.add_distance(new, params, group or None)
        elif new != rid:
            if new in self.doc.distances:
                self.say(f"The distance {new} already exists.", True)
                self._changed()
                return False
            self.doc.distances = {(new if k == rid else k): v for k, v in self.doc.distances.items()}
            for group in self.doc.score_sets.values():
                if isinstance(group, dict):
                    group["distances"] = [new if d == rid else d for d in group.get("distances", [])]
        if self.selected_dist == rid:
            self.selected_dist = new
        self._changed()
        return True

    def _set_distance_set(self, rid: str, group: str) -> bool:
        if self.is_draft(rid):
            self.dist_drafts[rid]["_set"] = group
            self._changed()
            return True
        old = self.distance_set(rid)
        if old and old in self.doc.score_sets and old != group:
            sets = self.doc.score_sets[old]
            sets["distances"] = [d for d in sets.get("distances", []) if d != rid]
        if group and group in self.doc.score_sets:
            members = self.doc.score_sets[group].setdefault("distances", [])
            if rid not in members:
                members.append(rid)
        self.dirty = True
        self._changed()
        return True

    def delete_distance(self, rid: str) -> bool:
        if self.is_draft(rid):
            self.dist_drafts.pop(rid, None)
        elif rid in self.doc.distances:
            self.doc.remove_distance(rid)
        else:
            return False
        if self.selected_dist == rid:
            self.selected_dist = ""
        self.dirty = True
        self.say(f"Removed {rid}." if not self.is_draft(rid) else "Removed the empty row.")
        self._changed()
        return True

    def toggle_distance(self, rid: str) -> None:
        params = self._dist(rid)
        if params is not None:
            self.set_distance(rid, "visible", not params.get("visible", True))

    def load_distribution(self, rid: str, path: str) -> bool:
        """A pRDA row's distribution file: first column R_DA, second p(R_DA) (one header line, as in Qt)."""
        params = self._dist(rid)
        if params is None:
            return False
        try:
            from chisurf.core.fio.ascii import Csv

            csv = Csv(filename=str(path), skiprows=1)
            params["rda"] = [float(v) for v in csv.data[0]]
            params["prda"] = [float(v) for v in csv.data[1]]
        except Exception as exc:  # noqa: BLE001
            self.say(f"Failed to load distribution: {exc}", True)
            return False
        self.dirty = True
        self.say(f"Loaded: {len(params['rda'])} points")
        self._changed()
        return True

    # ── score sets ────────────────────────────────────────────────────────

    def add_score_set(self, name: str) -> bool:
        name = name.strip()
        if not name:
            return False
        if name == ALL_DISTANCES or name in self.doc.score_sets:
            self.say(f"There is already a scoring group named {name!r}.", True)
            return False
        self.doc.add_score_set(name)
        self.dirty = True
        self.say(f"Added the scoring group {name}.")
        self._changed()
        return True

    def remove_score_set(self, name: str) -> bool:
        if not name or name == ALL_DISTANCES or name not in self.doc.score_sets:
            return False
        self.doc.remove_score_set(name)
        if self.score_filter == name:
            self.score_filter = ALL_DISTANCES
        self.dirty = True
        self.say(f"Removed the scoring group {name}.")
        self._changed()
        return True

    def set_score_filter(self, name: str) -> None:
        self.score_filter = name if name in self.doc.score_sets else ALL_DISTANCES
        self.sync()

    # ── FlexFit ───────────────────────────────────────────────────────────

    @property
    def flexfit(self) -> dict:
        flex = self.doc.extra_sections.get("FlexFit")
        return flex if isinstance(flex, dict) else {}

    @property
    def flexfit_names(self) -> list[str]:
        return list(self.flexfit)

    def _flexfit_entry(self) -> dict | None:
        names = self.flexfit_names
        if not names:
            return None
        if self.flexfit_set not in names:
            self.flexfit_set = names[0]
        entry = self.flexfit.get(self.flexfit_set)
        return entry if isinstance(entry, dict) else None

    def _flexfit_rows(self) -> tuple[Rows, Rows]:
        residues, bonds = Rows(), Rows()
        entry = self._flexfit_entry() or {}
        for i, res in enumerate(entry.get("Flexible residues", []) or []):
            residues.append({"row": i, "chain": str(res.get("chain_identifier", "")),
                             "residue": str(res.get("residue_seq_number", ""))})
        for i, bond in enumerate(entry.get("Bonds", []) or []):
            if not (isinstance(bond, list) and len(bond) >= 2):
                continue
            e1, e2 = bond[0] or {}, bond[1] or {}
            bonds.append({"row": i, "chain1": str(e1.get("chain_identifier", "")),
                          "residue1": str(e1.get("residue_seq_number", "")), "atom1": str(e1.get("atom_name", "")),
                          "chain2": str(e2.get("chain_identifier", "")),
                          "residue2": str(e2.get("residue_seq_number", "")), "atom2": str(e2.get("atom_name", ""))})
        residues.revision = getattr(self.rows_res, "revision", 0) + 1
        bonds.revision = getattr(self.rows_bond, "revision", 0) + 1
        return residues, bonds

    def select_flexfit_set(self, name: str) -> None:
        if name in self.flexfit:
            self.flexfit_set = name
            self.selected_residue = self.selected_bond = -1
            self.sync()

    def add_flexfit_set(self, name: str) -> bool:
        name = name.strip()
        if not name or name in self.flexfit:
            if name:
                self.say(f"There is already a FlexFit set named {name!r}.", True)
            return False
        flex = self.doc.extra_sections.setdefault("FlexFit", {})
        if not isinstance(flex, dict):
            flex = self.doc.extra_sections["FlexFit"] = {}
        flex[name] = {"Flexible residues": [], "Bonds": []}
        self.flexfit_set = name
        self.dirty = True
        self.say(f"Added the FlexFit set {name}.")
        self._changed()
        return True

    def remove_flexfit_set(self) -> bool:
        if not self._flexfit_entry() and self.flexfit_set not in self.flexfit:
            return False
        del self.flexfit[self.flexfit_set]
        self.say(f"Removed the FlexFit set {self.flexfit_set}.")
        self.flexfit_set = ""
        self.dirty = True
        self._changed()
        return True

    def add_flexfit_residue(self) -> bool:
        entry = self._flexfit_entry()
        if entry is None:
            self.say("Add a FlexFit set first.", True)
            return False
        entry.setdefault("Flexible residues", []).append({"chain_identifier": "", "residue_seq_number": 0})
        self.dirty = True
        self._changed()
        return True

    def remove_flexfit_residue(self, index: int) -> bool:
        entry = self._flexfit_entry()
        residues = (entry or {}).get("Flexible residues", [])
        if not 0 <= index < len(residues):
            return False
        del residues[index]
        self.selected_residue = -1
        self.dirty = True
        self._changed()
        return True

    def add_flexfit_bond(self) -> bool:
        entry = self._flexfit_entry()
        if entry is None:
            self.say("Add a FlexFit set first.", True)
            return False
        end = {"chain_identifier": "", "residue_seq_number": 0, "atom_name": ""}
        entry.setdefault("Bonds", []).append([dict(end), dict(end)])
        self.dirty = True
        self._changed()
        return True

    def remove_flexfit_bond(self, index: int) -> bool:
        entry = self._flexfit_entry()
        bonds = (entry or {}).get("Bonds", [])
        if not 0 <= index < len(bonds):
            return False
        del bonds[index]
        self.selected_bond = -1
        self.dirty = True
        self._changed()
        return True

    def edit_flexfit_residue(self, index: int, key: str, value: str) -> bool:
        entry = self._flexfit_entry()
        residues = (entry or {}).get("Flexible residues", [])
        if not 0 <= index < len(residues):
            return False
        if key == "chain":
            residues[index]["chain_identifier"] = str(value).strip()
        else:
            residues[index]["residue_seq_number"] = _int_or(value)
        self.dirty = True
        self._changed()
        return True

    def edit_flexfit_bond(self, index: int, key: str, value: str) -> bool:
        entry = self._flexfit_entry()
        bonds = (entry or {}).get("Bonds", [])
        if not 0 <= index < len(bonds):
            return False
        end = bonds[index][0 if key.endswith("1") else 1]
        name = key.rstrip("12")
        if name == "chain":
            end["chain_identifier"] = str(value).strip()
        elif name == "residue":
            end["residue_seq_number"] = _int_or(value)
        else:
            end["atom_name"] = str(value).strip()
        self.dirty = True
        self._changed()
        return True

    # ── 3D ────────────────────────────────────────────────────────────────

    def view3d(self) -> dict:
        """What the 3D tab draws: the AV point clouds and mean positions of the visible computed positions, the
        distance lines between them, and the backbone of the structure of the selected (else first) row."""
        clouds, means, lines = [], [], []
        for name, params in self.doc.positions.items():
            if name in self.av_cache and params.get("visible", True):
                coords, mean, _step, _cached = self.av_cache[name]
                color = self.colour_of(name)
                clouds.append((name, np.asarray(coords)[:, :3], color))
                means.append((name, mean, color))
        by_name = {n: m for n, m, _c in means}
        for key, dist in self.doc.distances.items():
            a, b = dist.get("position1_name"), dist.get("position2_name")
            if dist.get("visible", True) and a in by_name and b in by_name and a != b:
                lines.append((key, by_name[a], by_name[b], float(np.linalg.norm(by_name[a] - by_name[b]))))
        backbone = None
        anchor = self.selected_pos if self.selected_pos in self.doc.positions else next(iter(self.doc.positions), "")
        pdb = str(self.doc.positions.get(anchor, {}).get("pdb_path") or "") if anchor else ""
        struct = self.structures.get(pdb)
        if struct is not None and struct.atoms is not None:
            atoms = struct.atoms
            keep = np.isin(atoms["atom_name"], ["CA", "P"])
            backbone = np.asarray(atoms["xyz"])[keep]
        return {"clouds": clouds, "means": means, "lines": lines, "backbone": backbone}

    def scene3d(self) -> dict:
        """What the molecular viewer of the 3D tab shows, as the Qt editor gave its viewer: every structure a position
        uses (``{path: structure}``, as cartoon), the AV of each visible computed position as a surface with its mean
        as a sphere (``(name, points, mean, grid_step, colour)``), and a line per visible distance between computed
        means, in the colour of its first label (``(key, a, b, length, colour)``)."""
        structures: dict = {}
        for params in self.doc.positions.values():
            pdb = str(params.get("pdb_path") or params.get("pdb_id") or "").strip()
            struct = self.structure(pdb) if pdb and pdb not in structures else None
            if struct is not None and getattr(struct, "atoms", None) is not None:
                structures[pdb] = struct
        avs, means = [], {}
        for name, params in self.doc.positions.items():
            if name in self.av_cache and params.get("visible", True):
                coords, mean, step, _cached = self.av_cache[name]
                colour = self.colour_of(name)
                avs.append((name, np.asarray(coords)[:, :3], np.asarray(mean), float(step), colour))
                means[name] = (np.asarray(mean), colour)
        lines = []
        for key, dist in self.doc.distances.items():
            a, b = dist.get("position1_name"), dist.get("position2_name")
            if dist.get("visible", True) and a in means and b in means and a != b:
                (ma, colour), (mb, _c) = means[a], means[b]
                lines.append((key, ma, mb, float(np.linalg.norm(ma - mb)), colour))
        return {"structures": structures, "avs": avs, "lines": lines}

    def pick_atom(self, pdb: str, atom_index: int) -> bool:
        """An atom picked in the viewer becomes the attachment of the selected position (Qt: the current row takes
        the picked atom's chain, residue and atom). Only a pick in the selected position's own structure counts."""
        rid = self.selected_pos
        params = self._pos(rid)
        struct = self.structure(pdb) if pdb else None
        if params is None or struct is None or getattr(struct, "atoms", None) is None:
            return False
        own = str(params.get("pdb_path") or params.get("pdb_id") or "").strip()
        if own != pdb or not 0 <= int(atom_index) < len(struct.atoms):
            return False
        atom = struct.atoms[int(atom_index)]
        chain = atom["chain"].decode() if isinstance(atom["chain"], bytes) else str(atom["chain"])
        name = atom["atom_name"].decode() if isinstance(atom["atom_name"], bytes) else str(atom["atom_name"])
        self.set_position(rid, "chain_identifier", chain.strip())
        self.set_position(rid, "residue_seq_number", int(atom["res_id"]))
        self.set_position(rid, "atom_name", name.strip())
        self.say(f"{rid}: attached to {chain.strip()} {int(atom['res_id'])} {name.strip()} (picked)")
        return True

    # ── persistence ───────────────────────────────────────────────────────

    def export_settings(self) -> dict:
        """What the window remembers: the document (positions, distances, sets, FlexFit) and the selections."""
        return {"payload": copy.deepcopy(self.doc.fps_json_payload), "path": self.path,
                "score_filter": self.score_filter, "flexfit_set": self.flexfit_set}

    def restore_settings(self, settings: dict) -> None:
        if not isinstance(settings, dict):
            return
        payload = settings.get("payload")
        if isinstance(payload, dict):
            self.doc.fps_json_payload = copy.deepcopy(payload)
        self.path = str(settings.get("path", "") or "")
        flt = settings.get("score_filter")
        self.score_filter = flt if flt in self.doc.score_sets else ALL_DISTANCES
        flex = settings.get("flexfit_set")
        self.flexfit_set = flex if flex in self.flexfit else ""
        self._changed(schedule_all=True)


def _short_path(value: str) -> str:
    """A path as its file name (a PDB ID stays as it is): the table column is narrow, the form has the whole path."""
    return Path(value).name if ("/" in value or "\\" in value) else value


def _int_or(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


__all__ = ["ALL_DISTANCES", "DISTANCE_TYPES", "DYE_MODELS", "FpsEditor", "POSITION_DEFAULTS", "Rows",
           "colour_from_hex", "dye_presets", "hex_colour", "safe_mrc_stem"]
