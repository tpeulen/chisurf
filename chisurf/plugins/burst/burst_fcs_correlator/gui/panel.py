"""The Qt-free view model behind the burst-FCS window: what ``burst_fcs_emtk.view.json`` reads and calls.

The controller owns the files, the pairs and the computation; this panel gives the spec forms the settings of the model, the
tables (inputs, channel pairs, curves) as records, and the actions the app answers (file dialogs, Run, Stop).
"""

from __future__ import annotations

import json
from pathlib import Path

from chisurf.emtk.channel_definition import format_ranges, parse_ranges

FIT_MODES = ("none", "simple", "maxent")
FIT_LABELS = ("None", "Simple", "MaxEnt")
#: The settings the model holds (the Qt AutoForm's ``value`` fields) and the limits the spec declares for them.
MAXENT_ONLY = ("maxent_log10_reg", "maxent_td_min", "maxent_td_max")


def channels_text(chs) -> str:
    return ", ".join(str(c) for c in chs)


def parse_channels(text) -> list[int]:
    out = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            if not part.lstrip("+").isdigit():
                raise ValueError(f"{part!r} is not a channel number")
            out.append(int(part))
    return out


class BurstFcsPanel:
    """Fields, tables and actions of the window."""

    def __init__(self, app) -> None:
        object.__setattr__(self, "app", app)

    @property
    def c(self):
        return self.app.controller

    def __getattr__(self, name):
        return getattr(self.app.controller._model, name)

    def __setattr__(self, name, value):
        if self.app.controller.running:
            return
        setattr(self.app.controller._model, name, value)

    def enabled(self, name: str) -> bool:
        c = self.c
        if name in MAXENT_ONLY:
            return self.fit_mode == "maxent"
        if name == "stop":
            return c.running
        if name in ("guide", "help", "show_pairs"):
            return True
        if c.running:
            return False
        if name == "run":
            return bool(c.checked_files()) and any(
                p["pair_name"] in c.enabled_pairs for p in c._pair_presets
            )
        if name == "remove_files":
            return self.app.selected_file is not None
        if name == "remove_pair":
            return self.app.selected_pair is not None
        if name == "export_curves":
            return bool(c._curves)
        if name in ("clear",):
            return bool(c.files or c._curves)
        return True

    def edited(self, *_):
        pass

    def fit_modes(self):
        return list(zip(FIT_MODES, FIT_LABELS))

    # -- tables ------------------------------------------------------------------------------------------ #
    def file_columns(self):
        return [
            {
                "key": "use",
                "label": "Use",
                "width": 40,
                "description": "Correlate this input. Click to tick or untick.",
            },
            {
                "key": "name",
                "label": "Burst file",
                "editable": False,
                "description": "The BUR or BST burst table, or the analysis folder.",
            },
            {
                "key": "where",
                "label": "Folder",
                "editable": False,
                "description": "Where the input is.",
            },
        ]

    def file_rows(self):
        c = self.c
        return [
            {
                "use": p not in c.unchecked,
                "name": Path(p).name or p,
                "where": str(Path(p).parent),
                "_path": p,
            }
            for p in c.files
        ]

    def edit_file(self, record, key, value):
        if key == "use" and not self.c.running:
            (self.c.unchecked.discard if value else self.c.unchecked.add)(record["_path"])

    def file_editable(self, record, key):
        return key == "use" and not self.c.running

    def select_file(self, record):
        self.app.selected_file = None if record is None else record["_path"]

    def pair_columns(self):
        return [
            {
                "key": "use",
                "label": "Use",
                "width": 40,
                "description": "Correlate this channel pair in every burst.",
            },
            {
                "key": "name",
                "label": "Pair",
                "width": 76,
                "description": "Name of the pair, shown in the curve list. Double click, type and press Enter to rename it.",
            },
            {
                "key": "chs_a",
                "label": "Ch A",
                "width": 52,
                "description": "Routing channels of the first signal, separated by commas (0, 8).",
            },
            {
                "key": "chs_b",
                "label": "Ch B",
                "width": 52,
                "description": "Routing channels of the second signal; the same as A makes an auto-correlation.",
            },
            {
                "key": "micro_a",
                "label": "Micro A",
                "width": 78,
                "description": "Micro-time gates of the first signal as start:end in raw TAC channels; several with , or ; (0:10;20:30). Empty uses every photon.",
            },
            {
                "key": "micro_b",
                "label": "Micro B",
                "width": 78,
                "description": "Micro-time gates of the second signal, as for A.",
            },
        ]

    def pair_rows(self):
        c = self.c
        return [
            {
                "use": p["pair_name"] in c.enabled_pairs,
                "name": p["pair_name"],
                "chs_a": channels_text(p["chs_a"]),
                "chs_b": channels_text(p["chs_b"]),
                "micro_a": format_ranges(p.get("micro_a") or []),
                "micro_b": format_ranges(p.get("micro_b") or []),
                "_name": p["pair_name"],
            }
            for p in c._pair_presets
        ]

    def edit_pair(self, record, key, value):
        c = self.c
        if c.running:
            return
        pair = next((p for p in c._pair_presets if p["pair_name"] == record["_name"]), None)
        if pair is None:
            return
        try:
            if key == "use":
                c.set_pair_enabled(pair["pair_name"], bool(value))
            elif key == "name":
                new = str(value).strip()
                if not new or any(p["pair_name"] == new for p in c._pair_presets if p is not pair):
                    raise ValueError("A pair needs a name that no other pair has.")
                if pair["pair_name"] in c.enabled_pairs:
                    c.enabled_pairs.discard(pair["pair_name"])
                    c.enabled_pairs.add(new)
                pair["pair_name"] = new
            elif key in ("chs_a", "chs_b"):
                chs = parse_channels(value)
                if not chs:
                    raise ValueError("A pair needs at least one channel on each side.")
                pair[key] = chs
            elif key in ("micro_a", "micro_b"):
                pair[key] = [list(r) for r in parse_ranges(value)]
            c.pairs_text = json.dumps(c._pair_presets, indent=2)
            c.status = "Channel pairs edited."
        except ValueError as exc:
            c.status = f"Invalid channel pairs: {exc}"

    def pair_editable(self, record, key):
        return not self.c.running

    def select_pair(self, record):
        self.app.selected_pair = None if record is None else record["_name"]

    def curve_columns(self):
        many = len({c.get("file", "") for c in self.c._curves}) > 1
        return (
            [
                {
                    "key": "file",
                    "label": "File",
                    "editable": False,
                    "description": "Measurement the burst comes from.",
                }
            ]
            if many
            else []
        ) + [
            {
                "key": "burst",
                "label": "Burst",
                "width": 46,
                "editable": False,
                "description": "Index of the burst in the burst table.",
            },
            {
                "key": "pair",
                "label": "Pair",
                "width": 84,
                "editable": False,
                "description": "Channel pair of the curve.",
            },
            {
                "key": "td",
                "label": "tau_D (ms)",
                "format": "%.4g",
                "editable": False,
                "description": "Diffusion time of the fit (the mean of the distribution for MaxEnt).",
            },
        ]

    def curve_rows(self):
        return [
            {
                "file": c.get("file", ""),
                "burst": int(c.get("burst_index", 0)),
                "pair": c.get("pair_name", ""),
                "td": float(c.get("td_mean", float("nan")) or float("nan")),
                "_index": i,
            }
            for i, c in enumerate(self.c._curves)
        ]

    def select_curve(self, record):
        self.c._model._selected = None if record is None else self.c._curves[record["_index"]]
        if record is not None:
            self.app._used("curves")

    @property
    def progress_fraction(self):
        return float(self.c.progress)

    def progress_text(self):
        return f"{int(self.c.progress * 100)} %"

    def status_line(self):
        return self.c.status

    # -- actions ------------------------------------------------------------------------------------------ #
    def run(self):
        self.c._on_run()

    def stop(self):
        self.c.stop()

    def add_files(self):
        self.app.choose("files")

    def add_folder(self):
        self.app.choose("folder")

    def mmfdb(self):
        self.c.datasets.open()

    def check_all(self):
        self.c.check_all()

    def check_none(self):
        self.c.check_none()

    def remove_files(self):
        if self.app.selected_file is not None:
            self.c.remove_files([self.app.selected_file])
            self.app.selected_file = None

    def clear(self):
        self.c.clear()
        self.app.selected_file = None

    def load_settings(self):
        self.app.choose("load_settings")

    def save_settings(self):
        self.app.choose("save_settings")

    def load_pairs(self):
        self.app.choose("load_pairs")

    def save_pairs(self):
        self.app.choose("save_pairs")

    def show_pairs(self):
        self.app.show_pairs_json()

    def add_pair(self):
        c = self.c
        n = 1
        while f"pair_{n}" in {p["pair_name"] for p in c._pair_presets}:
            n += 1
        c._pair_presets.append(
            {"pair_name": f"pair_{n}", "chs_a": [0], "chs_b": [0], "micro_a": [], "micro_b": []}
        )
        c.enabled_pairs.add(f"pair_{n}")

    def remove_pair(self):
        c = self.c
        name = self.app.selected_pair
        c._pair_presets = [p for p in c._pair_presets if p["pair_name"] != name]
        c.enabled_pairs.discard(name)
        self.app.selected_pair = None

    def export_curves(self):
        self.app.choose("export_curves")

    def example(self):
        self.app.load_example()

    def guide(self):
        self.app.tour.start()

    def help(self):
        self.app.help_window.show()

    def use_setup(self):
        self.app.adopt_current_setup()
