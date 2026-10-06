"""The FPS JSON editor card of Structure Tools: edit fps.json files for FRET accessible-volume modelling.

The native counterpart of the Qt ``FpsJsonEditorTool``: Load / Save / Update / Clear, and the Positions, Distances,
FlexFit, JSON and 3D tabs, drawn from specs (``views/fps_*.view.json``) with ``data_table`` tables. The state and the
rules live in :class:`~.fps_model.FpsEditor`; this file draws it and routes the user's input to it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot3d
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form

from chisurf.emtk.chimol_view import ChimolView
from chisurf.plugins.emtk_layout import LabelColumn, layout_spec

from .fps_model import (
    ALL_DISTANCES,
    DISTANCE_TYPE_NAMES,
    DISTANCE_TYPES,
    PDB_ID,
    POSITION_DEFAULTS,
    FpsEditor,
    colour_from_hex,
    dye_presets,
    hex_colour,
    safe_mrc_stem,
)
from .shell import CardShell

HERE = Path(__file__).resolve().parent
RES = HERE / "resources" / "fps_json"
VIEWS = HERE / "views"
TABS = ("Positions", "Distances", "FlexFit", "JSON", "3D View")
#: The dock window of each view (the Qt editor's docks; the user can split and rearrange them).
VIEW_KEYS = {
    "Positions": "positions",
    "Distances": "distances",
    "FlexFit": "flexfit",
    "JSON": "json",
    "3D View": "view3d",
}
TAB_TIPS = {
    "Positions": "Labelling positions: structure, chain, residue, atom and the dye of each.",
    "Distances": "Distance restraints between two positions, and the scoring groups.",
    "FlexFit": "Flexible residues and bonds for the FlexFit simulation.",
    "JSON": "The raw fps.json text; edit it and press Update.",
    "3D View": "The accessible volumes and distance lines of the computed positions.",
}
FPS_FILTER = "fps.json (*.fps.json *.json);;All files (*)"
PDB_FILTER = "PDB (*.pdb *.pdb.gz *.ent);;All files (*)"
MRC_FILTER = "MRC map (*.mrc *.map *.ccp4);;All files (*)"


def _spec(name: str) -> dict:
    return layout_spec(json.loads((VIEWS / name).read_text(encoding="utf-8")))


def _with(options: list, current: Any) -> list[str]:
    """The choices, with the current value in them (a typed value that is not in the list stays visible)."""
    out = [str(o) for o in options]
    if str(current) not in out and str(current) != "":
        out.append(str(current))
    return out


class _View:
    """What a spec reads: the editor's rows, the selected row's fields and the table callbacks."""

    def __init__(self, card: FpsJsonCard) -> None:
        object.__setattr__(self, "card", card)
        object.__setattr__(self, "ed", card.editor)

    def enabled(self, name: str) -> bool:
        return not self.card.blocked


class PositionsView(_View):
    """The Positions tab: the table and the form of the selected position."""

    @property
    def pos_rows(self):
        return self.ed.rows_pos

    @property
    def has_position(self) -> bool:
        return bool(self.ed.selected_pos) and self.ed._pos(self.ed.selected_pos) is not None

    # table callbacks
    def select_row(self, record) -> None:
        self.ed.selected_pos = record["row"] if isinstance(record, dict) else ""
        self.card.used("positions")

    def edit_row(self, record, key: str, value) -> None:
        field = {
            "show": "visible",
            "name": "name",
            "pdb": "pdb_path",
            "chain": "chain_identifier",
            "res": "residue_seq_number",
            "atom": "atom_name",
        }.get(key)
        if field is None:
            return
        rid = record["row"]
        self.ed.selected_pos = rid
        if field == "visible":
            value = value in (True, "True", "true", 1)
        self.ed.set_position(rid, field, value)
        if self.ed.selected_pos != rid and rid.startswith("#") is False:
            pass
        self.card.sync_status()
        if key == "name":
            self.card.used("name")

    def delete_row(self, record) -> None:
        if isinstance(record, dict):
            self.card.ask_delete_position(record["row"])

    # the selected position's fields
    def _get(self, key: str):
        return self.ed.position_field(self.ed.selected_pos, key, "")

    def _set(self, key: str, value) -> None:
        if self.has_position:
            self.ed.set_position(self.ed.selected_pos, key, value)
            self.card.sync_status()

    @property
    def p_pdb(self) -> str:
        return str(self._get("pdb_path") or self._get("pdb_id") or "")

    @p_pdb.setter
    def p_pdb(self, value: str) -> None:
        self._set("pdb_path", value)

    @property
    def p_chain(self) -> str:
        return str(self._get("chain_identifier"))

    @p_chain.setter
    def p_chain(self, value: str) -> None:
        self._set("chain_identifier", value)

    @property
    def p_res(self) -> str:
        return str(self._get("residue_seq_number"))

    @p_res.setter
    def p_res(self, value: str) -> None:
        self._set("residue_seq_number", value)

    @property
    def p_atom(self) -> str:
        return str(self._get("atom_name"))

    @p_atom.setter
    def p_atom(self, value: str) -> None:
        self._set("atom_name", value)

    @property
    def p_preset(self) -> str:
        return str(self._get("dye_preset") or "Custom")

    @p_preset.setter
    def p_preset(self, value: str) -> None:
        self._set("dye_preset", value)

    @property
    def p_model(self) -> str:
        return str(self._get("simulation_type") or "AV1")

    @p_model.setter
    def p_model(self, value: str) -> None:
        self._set("simulation_type", value)

    @property
    def p_color(self) -> str:
        return hex_colour(self.ed.colour_of(self.ed.selected_pos))

    @p_color.setter
    def p_color(self, value: str) -> None:
        try:
            alpha = float(self.ed.colour_of(self.ed.selected_pos)[3])
            self._set("av_color", colour_from_hex(str(value), alpha))
        except (ValueError, TypeError, IndexError):
            self.ed.say(f"Not a colour: {value}", True)

    def chain_options(self) -> list[str]:
        pdb = str(self._get("pdb_path") or self._get("pdb_id") or "")
        return _with(self.ed.chains(pdb), self.p_chain)

    def residue_options(self) -> list[str]:
        pdb = str(self._get("pdb_path") or "")
        return _with([str(r) for r in self.ed.residues(pdb, self.p_chain)], self.p_res)

    def atom_options(self) -> list[str]:
        pdb = str(self._get("pdb_path") or "")
        res = self._get("residue_seq_number")
        return _with(self.ed.atoms(pdb, self.p_chain, res), self.p_atom)

    def preset_options(self) -> list[str]:
        return _with([*dye_presets(), "Custom"], self.p_preset)

    def __getattr__(self, name: str):
        if name in POSITION_DEFAULTS:
            return self._get(name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value) -> None:
        if name in POSITION_DEFAULTS:
            self._set(name, value)
        else:
            object.__setattr__(self, name, value)


class DistancesView(_View):
    """The Distances tab: the table and the form of the selected restraint."""

    @property
    def dist_rows(self):
        return self.ed.rows_dist

    @property
    def has_distance(self) -> bool:
        return bool(self.ed.selected_dist) and self.ed._dist(self.ed.selected_dist) is not None

    def select_row(self, record) -> None:
        self.ed.selected_dist = record["row"] if isinstance(record, dict) else ""

    def edit_row(self, record, key: str, value) -> None:
        if key == "show":
            self.ed.set_distance(record["row"], "visible", value in (True, "True", "true", 1))
            self.card.sync_status()

    def delete_row(self, record) -> None:
        if isinstance(record, dict):
            self.card.ask_delete_distance(record["row"])

    def _params(self) -> dict:
        return self.ed._dist(self.ed.selected_dist) or {}

    def _set(self, key: str, value) -> None:
        if self.has_distance:
            self.ed.set_distance(self.ed.selected_dist, key, value)
            self.card.sync_status()

    @property
    def d_label1(self) -> str:
        return str(self._params().get("position1_name", ""))

    @d_label1.setter
    def d_label1(self, value: str) -> None:
        self._set("position1_name", value)

    @property
    def d_label2(self) -> str:
        return str(self._params().get("position2_name", ""))

    @d_label2.setter
    def d_label2(self, value: str) -> None:
        self._set("position2_name", value)

    @property
    def d_type(self) -> str:
        return DISTANCE_TYPE_NAMES.get(self._params().get("distance_type", "RDAMean"), "dRDA")

    @d_type.setter
    def d_type(self, value: str) -> None:
        self._set("type", value)

    @property
    def d_set(self) -> str:
        return self.ed.distance_set(self.ed.selected_dist) if self.has_distance else ""

    @d_set.setter
    def d_set(self, value: str) -> None:
        self._set("score_set", value)

    def label_options(self) -> list[str]:
        return _with(self.ed.position_names, "")

    def set_options(self) -> list[str]:
        return ["", *self.ed.score_set_names]

    def __getattr__(self, name: str):
        if name in ("Forster_radius", "distance", "error_neg", "error_pos"):
            from .fps_model import DISTANCE_DEFAULTS

            return float(self._params().get(name, DISTANCE_DEFAULTS[name]))
        raise AttributeError(name)

    def __setattr__(self, name: str, value) -> None:
        if name in ("Forster_radius", "distance", "error_neg", "error_pos"):
            self._set(name, value)
        else:
            object.__setattr__(self, name, value)


class FlexView(_View):
    """The FlexFit tab: the residues and bonds tables of the selected set."""

    @property
    def res_rows(self):
        return self.ed.rows_res

    @property
    def bond_rows(self):
        return self.ed.rows_bond

    def select_residue(self, record) -> None:
        self.ed.selected_residue = record["row"] if isinstance(record, dict) else -1

    def select_bond(self, record) -> None:
        self.ed.selected_bond = record["row"] if isinstance(record, dict) else -1

    def edit_residue(self, record, key, value) -> None:
        self.ed.edit_flexfit_residue(record["row"], key, value)

    def edit_bond(self, record, key, value) -> None:
        self.ed.edit_flexfit_bond(record["row"], key, value)

    def delete_residue(self, record) -> None:
        self.ed.remove_flexfit_residue(record["row"])

    def delete_bond(self, record) -> None:
        self.ed.remove_flexfit_bond(record["row"])


class FpsJsonCard(CardShell):
    """The FPS JSON editor window."""

    def __init__(self, editor: FpsEditor | None = None) -> None:
        self.editor = editor or FpsEditor()
        self._tab = TABS[0]
        self._seen_selection: dict = {}
        self.views = {}
        super().__init__("FPS JSON Editor", RES, "fps")
        self.editor.on_change = self.request_frame
        self.views = {
            "positions": PositionsView(self),
            "distances": DistancesView(self),
            "flexfit": FlexView(self),
        }
        self.specs = {
            "positions": _spec("fps_positions.view.json"),
            "distances": _spec("fps_distances.view.json"),
            "flexfit": _spec("fps_flexfit.view.json"),
        }
        self.forms = {name: FormState(on_used=self.used) for name in self.specs}
        self.json_form = FormState(on_used=self.used)
        self.labels = LabelColumn()
        self._av_sizes = {}
        #: The 3D tab's molecular viewer (chimol, as the Qt editor embeds it); started when the tab is first shown.
        self.chimol = ChimolView()
        self._chimol_scene = None
        self._chimol_objects: dict[str, str] = {}
        self._chimol_picks = False
        self.chimol.claim_click = self._claim_3d_click
        #: The position the camera was last centred on (a row picked in a table brings the 3D view to it).
        self._centred_on = ""
        #: Set while a pick in the viewer changes the selection, so the camera does not jump to what was clicked.
        self._picking = False
        # Saved under a name of its own: the one-window layout ("main") of the earlier editor would hide the split.
        self.native_layouts = {"views": self.docks}

    # ── status ────────────────────────────────────────────────────────────

    def sync_status(self) -> None:
        """Show the editor's last message."""
        self.status, self.status_error = self.editor.status, self.editor.status_error
        self.request_frame()

    # ── file actions ──────────────────────────────────────────────────────

    def load(self) -> None:
        self.open_file(
            "Open JSON Labeling-File", FPS_FILTER, self.load_path, current=self.editor.path
        )

    def load_path(self, path: str) -> None:
        if self.editor.load(path):
            self.used("load")
        self.sync_status()

    def save(self) -> None:
        name = Path(self.editor.path).name if self.editor.path else "labeling.fps.json"
        self.save_file(
            "Save JSON Labeling-File",
            FPS_FILTER,
            self.save_path,
            filename=name,
            directory=os.path.dirname(self.editor.path) if self.editor.path else "",
        )

    def save_path(self, path: str) -> None:
        if not str(path).endswith(".json"):
            path = f"{path}.fps.json"
        if self.editor.save(path):
            self.used("save")
        self.sync_status()

    def update_from_json(self) -> None:
        self.editor.apply_json_text()
        self.sync_status()
        self.used("update")

    def clear(self) -> None:
        self.ask(
            "Clear Configuration",
            "Are you sure you want to clear all parameters?",
            self._clear,
            yes="Clear all",
            no="Keep",
        )

    def _clear(self) -> None:
        self.editor.clear()
        self.sync_status()
        self.used("clear")

    def take_drop(self, paths: list[str]) -> bool:
        """A dropped ``.json`` file is loaded (the first one wins, as in the Qt tool)."""
        for path in paths:
            if os.path.isfile(path) and path.lower().endswith(".json"):
                self.load_path(path)
                return True
        self.say("No .json file among the dropped paths.", True)
        return False

    # ── positions / distances ─────────────────────────────────────────────

    def ask_delete_position(self, rid: str) -> None:
        self.ask(
            "Remove position",
            f"Remove {rid or 'the empty row'}"
            + (" and every distance that uses it?" if rid and not rid.startswith("#") else "?"),
            lambda: self._delete_position(rid),
            yes="Remove",
            no="Keep",
        )

    def _delete_position(self, rid: str) -> None:
        self.editor.delete_position(rid)
        self.sync_status()

    def ask_delete_distance(self, rid: str) -> None:
        self.ask(
            "Remove Restraint?",
            "Are you sure you want to remove this restraint?",
            lambda: self._delete_distance(rid),
            yes="Remove",
            no="Keep",
        )

    def _delete_distance(self, rid: str) -> None:
        self.editor.delete_distance(rid)
        self.sync_status()

    def browse_pdb(self) -> None:
        rid = self.editor.selected_pos
        if not rid or self.editor._pos(rid) is None:
            self.say("Select a position row first.", True)
            return
        self.open_file(
            "Open PDB-File",
            PDB_FILTER,
            lambda p: self._set_pdb(rid, p),
            current=str(self.editor._pos(rid).get("pdb_path") or ""),
        )

    def _fetch_pdb(self, pdb_id: str) -> None:
        """The Fetch PDB prompt: the ID becomes the structure of the selected row (a new row when none is)."""
        pdb_id = pdb_id.strip()
        if not PDB_ID.match(pdb_id):
            self.say(f"{pdb_id!r} is not a PDB ID (4 characters, such as 1R0A).", True)
            return
        rid = self.editor.selected_pos
        if not rid or self.editor._pos(rid) is None:
            rid = self.editor.add_position_row()
        self._set_pdb(rid, pdb_id.lower())
        self.used("fetch_pdb")

    def _set_pdb(self, rid: str, path: str) -> None:
        self.editor.set_position(rid, "pdb_path", path)
        self.sync_status()
        self.used("pdb")

    def save_mrc(self) -> None:
        names = self.editor.computed_names(self.editor.selected_pos)
        if not names:
            self.editor.av_message = "No computed AVs available to save as MRC."
            self.say(self.editor.av_message, True)
            return
        if len(names) == 1:
            self.save_file(
                "Save AV as MRC",
                MRC_FILTER,
                lambda p: self._write_mrc(names, p),
                filename=f"{safe_mrc_stem(names[0])}.mrc",
            )
        else:
            self.open_file(
                f"Save {len(names)} AV MRC maps",
                "All files (*)",
                lambda p: self._write_mrc(names, p),
                folder=True,
            )

    def _write_mrc(self, names: list[str], target: str) -> None:
        try:
            if len(names) == 1:
                written = [self.editor.write_mrc(names[0], target)]
            else:
                written = [
                    self.editor.write_mrc(n, Path(target) / f"{safe_mrc_stem(n)}.mrc")
                    for n in names
                ]
        except Exception as exc:  # noqa: BLE001
            self.editor.av_message = f"Failed to save AV MRC: {exc}"
            self.say(self.editor.av_message, True)
            return
        self.editor.av_message = f"Saved {len(written)} AV MRC map(s)."
        self.say(self.editor.av_message)

    def load_distribution(self) -> None:
        rid = self.editor.selected_dist
        if not rid or self.editor._dist(rid) is None:
            self.say("Select a restraint row first.", True)
            return
        self.open_file(
            "DA-Distance distribution (1st column RDA, 2nd pRDA)",
            "CSV/Text Files (*.csv *.txt);;All files (*)",
            lambda p: (self.editor.load_distribution(rid, p), self.sync_status()),
        )

    # ── frame ─────────────────────────────────────────────────────────────

    def before_frame(self) -> None:
        if self.editor.poll() and self.editor.status != self.status:
            self.sync_status()
        if self.editor.busy:
            self.request_frame()

    def animating(self) -> bool:
        return super().animating() or self.editor.busy

    def next_frame_in(self):
        return 0.05 if self.editor.busy else super().next_frame_in()

    # ── windows ───────────────────────────────────────────────────────────

    def build_docks(self) -> DockManager:
        """One dock window per view: the tables tabbed on the left and the 3D View beside them, so a dye placed in a
        table (or a click in the viewer) shows at once. Any tab can be dragged to re-tab or split; the arrangement is
        kept with the card's layout."""
        docks = DockManager(Split("h", 0.5, Region("views"), Region("scene")))
        draw = {
            "Positions": self._draw_positions,
            "Distances": self._draw_distances,
            "FlexFit": self._draw_flexfit,
            "JSON": self._draw_json,
            "3D View": self._draw_3d,
        }
        for title in TABS:
            docks.add_window(
                VIEW_KEYS[title],
                title,
                lambda box, t=title, f=draw[title]: self._draw_view(box, t, f),
                dock="scene" if title == "3D View" else "views",
                closable=False,
                tooltip=TAB_TIPS[title],
            )
        docks.focus(VIEW_KEYS[TABS[0]])
        return docks

    def _draw_view(self, box, title, draw) -> None:
        """One view; a press inside it brings it forward as :attr:`tab` (with views side by side, the one in use)."""
        if im.is_mouse_clicked(0):
            mx, my = im.get_mouse_pos()
            if (
                box[0] <= mx < box[0] + box[2]
                and box[1] <= my < box[1] + box[3]
                and self._tab != title
            ):
                self._tab = title
                self.used(f"tab_{title}")
        draw()

    @property
    def tab(self) -> str:
        """The view in front (the last one the user picked, or that was brought forward)."""
        return self._tab

    @tab.setter
    def tab(self, title: str) -> None:
        if title in VIEW_KEYS:
            self._tab = title
            if getattr(self, "docks", None) is not None:
                self.docks.focus(VIEW_KEYS[title])

    def toolbar_height(self) -> float:
        return 52.0

    def draw_toolbar(self, box) -> None:
        pressed = self.toolbar(
            [
                {
                    "label": "Load",
                    "key": "load",
                    "tip": "Open an fps.json labelling file (a dropped .json file does the same).",
                },
                {
                    "label": "Save",
                    "key": "save",
                    "tip": "Save the whole configuration as an fps.json file.",
                },
                {
                    "label": "Update",
                    "key": "update",
                    "tip": "Update the editor from the text of the JSON tab.",
                },
                {
                    "label": "Clear",
                    "key": "clear",
                    "tip": "Remove all positions and distances to start from scratch (asks first).",
                },
                *self.help_buttons(),
            ]
        )
        if pressed:
            {
                "load": self.load,
                "save": self.save,
                "update": self.update_from_json,
                "clear": self.clear,
                "guide": self.start_guide,
                "help": self.show_help,
            }[pressed]()
        self.status_line()
        self._track_views()

    def _track_views(self) -> None:
        """The views' tabs for the tour and the tests (``tab_<title>``), and which view the user brought forward."""
        keys = {key: title for title, key in VIEW_KEYS.items()}
        for title, key in VIEW_KEYS.items():
            rect = self.docks.tab_rect(key)
            if rect is not None:
                self.item_rects[f"tab_{title}"] = tuple(rect)
        for region, key in self.docks.selected.items():
            if key in keys and self._seen_selection.get(region) != key:
                if region in self._seen_selection:  # a pick, not the first frame
                    self._tab = keys[key]
                    self.used(f"tab_{keys[key]}")
                self._seen_selection[region] = key

    def _draw_positions(self) -> None:
        ed = self.editor
        has_place = ed.attachment(ed.selected_pos) is not None if ed.selected_pos else False
        pressed = self.toolbar(
            [
                {
                    "label": "Add Row",
                    "key": "add_row",
                    "tip": "Add an empty position row; it becomes a position once it has a name.",
                },
                {
                    "label": "Delete Row",
                    "key": "delete_row",
                    "enabled": bool(ed.selected_pos) and ed._pos(ed.selected_pos) is not None,
                    "tip": "Remove the selected row (asks first; the distances that use a position go with it).",
                },
                {
                    "label": "Browse PDB...",
                    "key": "browse_pdb",
                    "enabled": bool(ed.selected_pos),
                    "tip": "Choose the structure file of the selected row.",
                },
                {
                    "label": "Fetch PDB...",
                    "key": "fetch_pdb",
                    "tip": "Download a structure from the RCSB by its 4-character ID: for the selected row, else a new "
                    "row on it. Typing the ID into PDB file or ID does the same.",
                },
                {
                    "label": "\u25c0 Residue",
                    "key": "res_prev",
                    "enabled": has_place,
                    "tip": "Move the selected position to the previous residue of its chain; its volume is recomputed "
                    "and shown in the 3D View.",
                },
                {
                    "label": "Residue \u25b6",
                    "key": "res_next",
                    "enabled": has_place,
                    "tip": "Move the selected position to the next residue of its chain; its volume is recomputed "
                    "and shown in the 3D View.",
                },
                {
                    "label": "Compute AVs",
                    "key": "compute_avs",
                    "tip": "Recompute the accessible volume of every named position.",
                },
                {
                    "label": "Save AV MRC",
                    "key": "save_mrc",
                    "tip": "Save the selected position's computed accessible volume (else every one) as an MRC density map.",
                },
            ]
        )
        if pressed == "add_row":
            ed.add_position_row()
            self.sync_status()
            self.used("add_row")
        elif pressed == "delete_row":
            self.ask_delete_position(ed.selected_pos)
        elif pressed == "browse_pdb":
            self.browse_pdb()
        elif pressed == "fetch_pdb":
            self.prompt("Fetch PDB", "PDB ID (4 characters, from the RCSB):", self._fetch_pdb)
        elif pressed in ("res_prev", "res_next"):
            if ed.step_residue(ed.selected_pos, -1 if pressed == "res_prev" else 1):
                self.sync_status()
                self.used(pressed)
        elif pressed == "compute_avs":
            ed.compute_all()
            self.used("compute_avs")
        elif pressed == "save_mrc":
            self.save_mrc()
        im.text_wrapped(ed.av_message)
        self.remember("av_message")
        self._form("positions")

    def _draw_distances(self) -> None:
        ed = self.editor
        pressed = self.toolbar(
            [
                {
                    "label": "Add Row",
                    "key": "add_dist",
                    "tip": "Add an empty restraint row; choose its two labels below.",
                },
                {
                    "label": "Delete Row",
                    "key": "delete_dist",
                    "enabled": bool(ed.selected_dist) and ed._dist(ed.selected_dist) is not None,
                    "tip": "Remove the selected restraint (asks first).",
                },
                {
                    "label": "Add Scoring Group",
                    "key": "add_set",
                    "tip": "Add a scoring group (a chi-squared set of restraints).",
                },
                {
                    "label": "Remove Scoring Group",
                    "key": "remove_set",
                    "enabled": ed.score_filter != ALL_DISTANCES,
                    "tip": "Remove the scoring group shown in the filter (asks first).",
                },
            ]
        )
        if pressed == "add_dist":
            ed.add_distance_row()
            self.sync_status()
        elif pressed == "delete_dist":
            self.ask_delete_distance(ed.selected_dist)
        elif pressed == "add_set":
            self.prompt("New Scoring Group", "Scoring group name:", self._add_set)
        elif pressed == "remove_set":
            name = ed.score_filter
            self.ask(
                "Remove Scoring Group?",
                f"Are you sure you want to remove scoring group '{name}'?",
                lambda: (ed.remove_score_set(name), self.sync_status()),
                yes="Remove",
                no="Keep",
            )
        self._set_filter()
        self._form("distances")
        if (
            ed.selected_dist
            and ed._dist(ed.selected_dist) is not None
            and DISTANCE_TYPE_NAMES.get(ed._dist(ed.selected_dist).get("distance_type"), "dRDA")
            == "pRDA"
        ):
            if im.button("Load DA Distribution..."):
                self.load_distribution()
            im.set_item_tooltip(
                "A file with R_DA in the first column and p(R_DA) in the second; one header line."
            )
            self.remember("load_distribution")

    def _add_set(self, name: str) -> None:
        self.editor.add_score_set(name)
        self.sync_status()

    def _set_filter(self) -> None:
        ed = self.editor
        options = [ALL_DISTANCES, *ed.score_set_names]
        idx = options.index(ed.score_filter) if ed.score_filter in options else 0
        im.text("Scoring group / set:")
        im.same_line()
        im.set_next_item_width(200)
        changed, new = im.combo("##scorefilter", idx, options)
        if changed:
            ed.set_score_filter(options[new])
        self.remember("score_filter")
        im.set_item_tooltip("Show only the restraints of one scoring group, or all of them.")

    def _draw_flexfit(self) -> None:
        ed = self.editor
        names = ed.flexfit_names
        im.text("Set:")
        im.same_line()
        im.set_next_item_width(220)
        idx = names.index(ed.flexfit_set) if ed.flexfit_set in names else 0
        changed, new = im.combo("##flexset", idx, names or [""])
        if changed and names:
            ed.select_flexfit_set(names[new])
        self.remember("flex_set")
        im.set_item_tooltip("The FlexFit set whose residues and bonds are shown.")
        im.same_line()
        pressed = self.toolbar(
            [
                {"label": "+", "key": "flex_add_set", "tip": "Add a new FlexFit set."},
                {
                    "label": "-",
                    "key": "flex_remove_set",
                    "enabled": bool(names),
                    "tip": "Remove the current FlexFit set.",
                },
            ]
        )
        if pressed == "flex_add_set":
            self.prompt(
                "New FlexFit set",
                "Set name:",
                lambda n: (ed.add_flexfit_set(n), self.sync_status()),
            )
        elif pressed == "flex_remove_set":
            ed.remove_flexfit_set()
            self.sync_status()
        pressed = self.toolbar(
            [
                {
                    "label": "Add residue",
                    "key": "flex_add_res",
                    "tip": "Add a flexible residue to the set.",
                },
                {
                    "label": "Remove selected residue",
                    "key": "flex_remove_res",
                    "enabled": ed.selected_residue >= 0,
                    "tip": "Remove the selected residue row.",
                },
                {
                    "label": "Add bond",
                    "key": "flex_add_bond",
                    "tip": "Add a bond (two atoms) to the set.",
                },
                {
                    "label": "Remove selected bond",
                    "key": "flex_remove_bond",
                    "enabled": ed.selected_bond >= 0,
                    "tip": "Remove the selected bond row.",
                },
            ]
        )
        if pressed == "flex_add_res":
            ed.add_flexfit_residue()
        elif pressed == "flex_remove_res":
            ed.remove_flexfit_residue(ed.selected_residue)
        elif pressed == "flex_add_bond":
            ed.add_flexfit_bond()
        elif pressed == "flex_remove_bond":
            ed.remove_flexfit_bond(ed.selected_bond)
        if pressed:
            self.sync_status()
        self._form("flexfit")

    def _draw_json(self) -> None:
        spec = {
            "sections": [
                {
                    "type": "custom",
                    "key": "code_editor",
                    "target": "json_text",
                    "options": {"language": "JSON", "expand": True, "height": 200},
                }
            ]
        }
        self.json_form.rects.clear()
        draw_form(spec, self._json_view(), self.json_form)
        self.item_rects.update(self.json_form.rects)

    def _json_view(self):
        return self.editor_view

    @property
    def editor_view(self):
        return self.editor

    def _form(self, name: str) -> None:
        form = self.forms[name]
        form.rects.clear()
        if not self.labels.ready:
            self.labels.measure(
                [s["label"] for s in _labelled(self.specs[name]["sections"])] or [""]
            )
        draw_form(self.specs[name], self.views[name], form)
        self.item_rects.update(form.rects)

    def _draw_3d(self) -> None:
        scene = self.editor.scene3d()
        if not scene["structures"] and not scene["avs"]:
            im.text_wrapped(
                "Nothing to show: give a position a structure (Positions tab, PDB file or ID), and compute its "
                "accessible volume with Compute AVs."
            )
            self.remember("empty_3d")
            return
        viewer = self.chimol.viewer
        if viewer is None:
            im.text_wrapped(
                f"The molecular viewer could not start ({self.chimol.error}); the accessible volumes are shown as "
                "points instead."
            )
            self._draw_3d_points()
            return
        rid = (
            self.editor.selected_pos
            if self.editor._pos(self.editor.selected_pos) is not None
            else ""
        )
        im.text_wrapped(
            f"Click an atom to attach {rid} there; click a coloured sphere to select its position."
            if rid
            else "Click an atom to start a new position there; click a coloured sphere to select its position."
        )
        self.remember("pick_hint")
        self._sync_chimol(viewer, scene)
        self._follow_selection(viewer)
        self.chimol.draw(enabled=not self.blocked)
        im.set_item_tooltip(
            "The structures as cartoon, the accessible volumes as surfaces with their mean positions, and the "
            "distance lines; the selected position's attachment atom is the white sphere. Drag to rotate, wheel to "
            "zoom; click an atom to attach the selected position to it, click a mean sphere to select its position."
        )
        self.remember("plot3d")

    def _follow_selection(self, viewer) -> None:
        """A position picked in a table (or stepped along its chain) brings the camera to its attachment atom; a
        pick in the viewer does not move the camera."""
        rid = self.editor.selected_pos
        place = self.editor.attachment(rid) if rid else None
        key = f"{rid}:{tuple(np.round(place[2], 2))}" if place is not None else ""
        if key == self._centred_on:
            self._picking = False
            return
        if place is not None and not self._picking and hasattr(viewer, "center_on_point"):
            viewer.center_on_point(place[2])
        self._centred_on = key
        self._picking = False

    def _claim_3d_click(self, x: float, y: float) -> bool:
        """A press on an AV's mean sphere selects that position (and is not an atom pick)."""
        means = [(name, mean) for name, _p, mean, _s, _c in self.editor.scene3d()["avs"]]
        if not means:
            return False
        sx, sy, visible = self.chimol.screen_points(np.array([m for _n, m in means]))
        if not len(sx):
            return False
        d = np.hypot(sx - x, sy - y)
        d[~visible.astype(bool)] = np.inf
        best = int(np.argmin(d))
        if d[best] > 9.0:
            return False
        self.editor.selected_pos = means[best][0]
        self.editor.say(f"{means[best][0]} selected (clicked in the 3D View)")
        self._picking = True  # the camera stays where the user is looking
        self.sync_status()
        self.used("pick_sphere")
        return True

    def _sync_chimol(self, viewer, scene: dict) -> None:
        """Give the viewer what the Qt editor gave its viewer, when it changed: each structure once (cartoon, framed
        when the set of structures changes), the AV surfaces with mean spheres, and the distance lines."""
        paths = tuple(scene["structures"])
        # By the cached AV arrays, not the points handed over: scene3d slices them afresh each call, and an id that
        # changes every frame re-meshed every surface every frame.
        cache = self.editor.av_cache
        avs = tuple(
            (n, id(cache[n][0]) if n in cache else id(p), tuple(c))
            for n, p, _m, _s, c in scene["avs"]
        )
        lines = tuple((k, round(length, 3), tuple(c)) for k, _a, _b, length, c in scene["lines"])
        rid = self.editor.selected_pos
        place = self.editor.attachment(rid) if rid else None
        marker = (rid, tuple(np.round(place[2], 3))) if place is not None else None
        signature = (paths, avs, lines, marker)
        if signature == self._chimol_scene:
            return
        new_structures = self._chimol_scene is None or self._chimol_scene[0] != paths
        self._chimol_scene = signature
        if not self._chimol_picks:
            viewer.atomSelectionChanged.connect(self._on_chimol_pick)
            self._chimol_picks = True
        if new_structures:
            for oid in list(self._chimol_objects):
                viewer.remove_object(oid)
            self._chimol_objects = {}
            for path, struct in scene["structures"].items():
                oid = viewer.add_structure(struct, name=Path(path).stem, source_path=path)
                self._chimol_objects[oid] = path
            self.chimol.sync_panel()
        viewer.clear_point_overlays()
        for name, points, mean, step, colour in scene["avs"]:
            # With a position selected its volume stands out and the others are muted (chimol's labelling window
            # does the same: selected / muted), so the one being placed is seen.
            base = colour[3]
            alpha = base if marker is None else max(base, 0.45) if name == rid else 0.3 * base
            viewer.add_surface_overlay(
                f"av_{name}",
                points,
                color=(*colour[:3], alpha),
                alpha=1.0,
                grid_spacing=max(step, 0.1),
                padding=max(step * 2.0, 1.0),
                smoothing_sigma=0.75,
                dilation_iterations=1,
                max_dim=112,
                fallback_size_scale=0.02,
                fallback_min_size=1.5,
            )
            viewer.add_sphere(
                mean,
                radius=1.5,
                color=(*colour[:3], max(colour[3], 0.9)),
                label=name,
                key=f"mean_{name}",
            )
        if marker is not None:
            # The selected position's attachment atom: where a click or the residue buttons put the dye.
            viewer.add_sphere(
                place[2],
                radius=1.2,
                color=(1.0, 1.0, 1.0, 0.95),
                label=f"{rid} *",
                key="attachment_selected",
            )
        measurements = {
            k: v for k, v in viewer.measurements.items() if not k.startswith("dist_line_")
        }
        for key, a, b, length, colour in scene["lines"]:
            measurements[f"dist_line_{key}"] = {
                "kind": "distance",
                "positions": np.array([a, b]),
                "color": [*colour[:3], 0.8],
                "label": f"{length:.1f} Å",
            }
        viewer.measurements = measurements
        viewer.update_view(fit_camera=new_structures)

    def _on_chimol_pick(self, atom_indices) -> None:
        """An atom clicked in the viewer: the selected position takes it as its attachment (Qt behaviour)."""
        if not atom_indices or self.chimol.app is None:
            return
        oid = self.chimol.app.viewer.get_active_object_id()
        self._picking = True
        if self.editor.pick_atom(self._chimol_objects.get(oid, ""), int(atom_indices[0])):
            self.sync_status()
            self.used("pick_atom")

    def _draw_3d_points(self) -> None:
        """The fallback without chimol: AV point clouds, means, distance lines and the backbone trace."""
        data = self.editor.view3d()
        flags = implot3d.FLAGS_NO_LEGEND if not data["clouds"] else 0
        if implot3d.begin_plot("Accessible volumes##fps3d", (-1, -1), flags):
            implot3d.setup_axes("x [A]", "y [A]", "z [A]")
            back = data["backbone"]
            if back is not None and len(back):
                implot3d.plot_line("Backbone", back[:, 0], back[:, 1], back[:, 2])
            for name, pts, color in data["clouds"]:
                step = max(1, len(pts) // 1500)
                rgba = (*color[:3], 0.8)
                spec = implot3d.Spec(
                    marker_size=1.5, marker_fill_color=rgba, marker_line_color=rgba
                )
                implot3d.plot_scatter(
                    f"{name}", pts[::step, 0], pts[::step, 1], pts[::step, 2], spec=spec
                )
            for name, mean, color in data["means"]:
                rgba = (*color[:3], 1.0)
                spec = implot3d.Spec(
                    marker_size=5,
                    marker_fill_color=rgba,
                    marker_line_color=rgba,
                    flags=implot3d.ITEM_FLAGS_NO_LEGEND,
                )
                implot3d.plot_scatter(
                    f"mean {name}", [float(mean[0])], [float(mean[1])], [float(mean[2])], spec=spec
                )
            for key, a, b, length in data["lines"]:
                implot3d.plot_line(
                    f"{key} {length:.1f} A",
                    [float(a[0]), float(b[0])],
                    [float(a[1]), float(b[1])],
                    [float(a[2]), float(b[2])],
                    spec=implot3d.Spec(flags=implot3d.ITEM_FLAGS_NO_LEGEND),
                )
            implot3d.end_plot()
            im.set_item_tooltip(
                "Accessible volumes (points), mean positions and distance lines; "
                "drag to rotate, wheel to zoom."
            )
            self.remember("plot3d")

    # ── persistence ───────────────────────────────────────────────────────

    def export_settings(self) -> dict:
        return {**self.editor.export_settings(), "tab": self.tab}

    def restore_settings(self, settings: dict) -> None:
        if not isinstance(settings, dict):
            return
        self.editor.restore_settings(settings)
        if settings.get("tab") in TABS:
            self.tab = settings["tab"]

    def close(self) -> None:
        self.editor._executor.shutdown(wait=False, cancel_futures=True)
        self.chimol.close()


def _labelled(sections):
    for s in sections:
        if s.get("type") in ("value", "choice") and s.get("label"):
            yield s
        yield from _labelled(s.get("sections", []))


def make_app(editor: FpsEditor | None = None) -> FpsJsonCard:
    """The FPS JSON editor card."""
    from chisurf.emtk.i18n import install

    install()
    return FpsJsonCard(editor)


__all__ = ["FpsJsonCard", "make_app"]
