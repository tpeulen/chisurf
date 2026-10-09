"""The Qt-free view model behind the saturation window: what ``saturation_emtk.view.json`` reads and calls.

The model (:class:`~.model.SaturationModel`) holds the physics; this panel adds what a window needs on top of it:
the tables of the rate matrices and the parameters as records, the edits written back to the live parameters, the
logarithmic power slider and the summary as label/value rows.
"""

from __future__ import annotations

import math
import re

from .model import SaturationModel

#: The lowest power the logarithmic slider reaches (the Qt slider's lower end).
POWER_FLOOR_MW = 0.001
POWER_CEILING_MW = 100.0
#: Names of the plot tabs, in the order of the Qt tool's dock tabs after the state diagram.
TABS = ("State diagram", "FCS curve", "Info", "Volume profile", "Volume(P)", "Diffusion time")
#: Short row names of the Optics table, the symbols the Qt table shows.
SYMBOLS = {
    "power": "P",
    "wavelength": "\u03bb_exc",
    "extinction": "\u03b5",
    "tau_R1": "\u03c4_R1",
    "tau_R2": "\u03c4_R2",
}
#: Plain rows of the Optics & measurement table that are results of the scheme, not inputs.
OUTPUT_ROWS = ("tau_R1", "tau_R2")


def _number(text) -> float | None:
    """A float typed into a cell, or None."""
    try:
        value = float(str(text).replace(",", ".").strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


class SaturationPanel:
    """The model's fields plus the tables, drawn by ``emtk.view_form`` from ``saturation_emtk.view.json``."""

    def __init__(self, app) -> None:
        object.__setattr__(self, "app", app)

    # -- model fields (the spec's ``attr`` names) -------------------------------------------------------------- #
    def __getattr__(self, name: str):
        return getattr(self.app.model, name)

    def __setattr__(self, name: str, value) -> None:
        if name == "power_log":
            self.power_mW = 10.0 ** float(value)
        elif name == "n_states":
            self.app.model.saturation.n_states = int(value)
            self.app.model._on_changed()
        elif name == "result_tab":
            self.app.result_tab = str(value)
        else:
            setattr(self.app.model, name, value)

    @property
    def power_log(self) -> float:
        """log10 of the power in mW, the position of the logarithmic slider."""
        return math.log10(max(float(self.app.model.power_mW), POWER_FLOOR_MW))

    @property
    def n_states(self) -> int:
        return int(self.app.model.saturation.n_states)

    @property
    def result_tab(self) -> str:
        return self.app.result_tab

    def dye_options(self) -> list:
        """The MMFDB dyes with an empty first choice (type the extinction by hand)."""
        names = list(self.app.model.dye_names())
        return [("", "(none, type the extinction)")] + [(n, n) for n in names if n]

    def enabled(self, name: str) -> bool:
        return True

    # -- the specs' hooks ----------------------------------------------------------------------------------- #
    def edited(self, *_value) -> None:
        """A field committed: recompute (the Qt tool's ``_on_changed``)."""
        self.app.model._on_changed()
        self.app.error = ""

    def compute(self) -> None:
        self.app.compute()

    def load_scheme(self) -> None:
        self.app.choose("open")

    def save_scheme(self) -> None:
        self.app.choose("save")

    def load_session(self) -> None:
        self.app.load_session()

    def save_session(self) -> None:
        self.app.save_session()

    def guide(self) -> None:
        self.app.tour.start()

    def help(self) -> None:
        self.app.help_window.show()

    # -- the rate matrices ------------------------------------------------------------------------------------ #
    def _group(self, which: str):
        sat = self.app.model.saturation
        return sat.dark if which == "dark" else sat.exc

    def matrix_columns(self) -> list:
        labels = self.app.model.saturation.state_labels
        cols = [
            {
                "key": "state",
                "label": "from / to",
                "editable": False,
                "description": "The state a transition starts from (row); the columns are the states it ends in.",
            }
        ]
        cols += [
            {
                "key": f"c{j}",
                "label": str(label),
                "format": "%.6g",
                "description": f"Rate of the transition into {label}. Double click to type a value; zero removes the transition.",
            }
            for j, label in enumerate(labels)
        ]
        return cols

    def _rows(self, which: str) -> list[dict]:
        sat = self.app.model.saturation
        labels = list(sat.state_labels)
        values = {name: float(p.value) for name, p in self._group(which).rates_by_name().items()}
        prefix = "k" if which == "dark" else "sigma"
        rows = []
        for i, label in enumerate(labels):
            row: dict = {"state": str(label), "_i": i, "_which": which}
            for j in range(len(labels)):
                row[f"c{j}"] = None if i == j else values.get(f"{prefix}{i + 1}_{j + 1}", 0.0)
            rows.append(row)
        return rows

    def dark_rows(self) -> list[dict]:
        return self._rows("dark")

    def exc_rows(self) -> list[dict]:
        return self._rows("exc")

    def _cell_editable(self, record, key: str, which: str) -> bool:
        if key == "state" or not key.startswith("c"):
            return False
        j = int(key[1:])
        if record["_i"] == j:
            return False  # the diagonal is minus the sum of the row, not a rate
        # K_dark's ground-state row is the excitation, entered as a cross-section instead
        return not (which == "dark" and record["_i"] == 0)

    def dark_editable(self, record, key) -> bool:
        return self._cell_editable(record, key, "dark")

    def exc_editable(self, record, key) -> bool:
        return self._cell_editable(record, key, "exc")

    def _edit_rate(self, record, key, value, which: str) -> None:
        number = _number(value)
        if number is None or not self._cell_editable(record, key, which):
            return
        j = int(key[1:])
        prefix = "k" if which == "dark" else "sigma"
        parameter = self._group(which).rates_by_name().get(f"{prefix}{record['_i'] + 1}_{j + 1}")
        if parameter is None:
            return
        ceiling = 1e9 if which == "dark" else 1.0
        parameter.value = min(
            max(number, 0.0), ceiling
        )  # a rate is never negative; a cross-section is at most the peak
        self.edited()
        self.app.tour.notify_used("k_dark" if which == "dark" else "k_exc")

    def edit_dark(self, record, key, value) -> None:
        self._edit_rate(record, key, value, "dark")

    def edit_exc(self, record, key, value) -> None:
        self._edit_rate(record, key, value, "exc")

    # -- the parameter tables (brightness Q, optics and measurement) ----------------------------------------- #
    def _parameter_rows(self, parameters, labels=None, table="optics") -> list[dict]:
        rows = []
        for i, p in enumerate(parameters):
            output = p.name in OUTPUT_ROWS
            lo, hi = p.bounds
            rows.append(
                {
                    "name": labels[i] if labels else SYMBOLS.get(str(p.name), str(p.name)),
                    "value": float(p.value),
                    "fixed": None if output else bool(p.fixed),
                    "lo": None if output or lo is None else float(lo),
                    "hi": None if output or hi is None else float(hi),
                    "bounds": None if output else bool(p.bounds_on),
                    "error": None,
                    "description": str(getattr(p, "description", "") or ""),
                    "_parameter": p,
                    "_table": table,
                    "_output": output,
                }
            )
        return rows

    def brightness_rows(self) -> list[dict]:
        sat = self.app.model.saturation
        params = list(sat.brightness._brightness)
        return self._parameter_rows(
            params, [f"Q({label})" for label in sat.state_labels], "brightness"
        )

    def optics_rows(self) -> list[dict]:
        sat = self.app.model.saturation
        sat.find_parameters()
        outputs = list(getattr(sat, "_relaxation_outputs", []))
        rows = self._parameter_rows(list(sat._parameters))
        for row in rows:
            row["_output"] = row["_parameter"] in outputs or row["_output"]
            if row["_output"]:
                row["fixed"] = row["lo"] = row["hi"] = row["bounds"] = None
        return rows

    def parameter_columns(self) -> list:
        return [
            {
                "key": "name",
                "label": "Name",
                "width": 50,
                "editable": False,
                "description": "The parameter's name; hover a row for what it means.",
            },
            {
                "key": "value",
                "label": "Value",
                "width": 62,
                "format": "%.4g",
                "description": "The value the calculation uses. Double click to type one (clamped to the limits while they are on).",
            },
            {
                "key": "fixed",
                "label": "Fixed",
                "width": 42,
                "description": "Hold this parameter constant when it is fitted elsewhere. It does not change this calculator's curves.",
            },
            {
                "key": "lo",
                "label": "Lo",
                "width": 44,
                "format": "%.6g",
                "description": "Lower limit, used while Bounds is ticked.",
            },
            {
                "key": "hi",
                "label": "Hi",
                "width": 48,
                "format": "%.6g",
                "description": "Upper limit, used while Bounds is ticked.",
            },
            {
                "key": "bounds",
                "label": "Bounds",
                "width": 50,
                "description": "Apply the lower and upper limit to this parameter.",
            },
            {
                "key": "error",
                "label": "Error",
                "width": 42,
                "editable": False,
                "description": "Uncertainty of a fitted value; empty here because nothing is fitted.",
            },
        ]

    def parameter_editable(self, record, key) -> bool:
        if record.get("_output"):
            return False  # the relaxation times are results of the scheme
        return key in ("value", "fixed", "lo", "hi", "bounds")

    def edit_parameter(self, record, key, value) -> None:
        if not self.parameter_editable(record, key):
            return
        p = record["_parameter"]
        if key in ("fixed", "bounds"):
            if key == "fixed":
                p.fixed = bool(value)
            else:
                p.bounds_on = bool(value)
            self.app.model._on_changed()
            self.app.tour.notify_used(record.get("_table", "optics"))
            return
        number = _number(value)
        if number is None:
            return
        lo, hi = p.bounds
        if key == "value":
            if p.bounds_on:
                if lo is not None:
                    number = max(number, float(lo))
                if hi is not None:
                    number = min(number, float(hi))
            p.value = number
        else:
            pair = [lo, hi]
            pair[0 if key == "lo" else 1] = number
            if pair[0] is not None and pair[1] is not None and pair[0] > pair[1]:
                return  # inverted limits are refused
            p.bounds = tuple(pair)
        self.edited()
        self.app.tour.notify_used(record.get("_table", "optics"))

    # -- the summary -------------------------------------------------------------------------------------------- #
    def info_rows(self) -> list[tuple[str, str]]:
        """The Qt summary table as (label, value) pairs without its markup."""
        html = self.app.model.info_text()
        rows = []
        for label, value in re.findall(r"<tr><td[^>]*>(.*?)</td><td[^>]*>(.*?)</td></tr>", html):
            rows.append((self._plain(label), self._plain(value)))
        return rows

    @staticmethod
    def _plain(markup: str) -> str:
        import html as _html

        text = re.sub(r"<br\s*/?>", "\n", markup)
        text = re.sub(r"<sub>(.*?)</sub>", lambda m: "_" + m.group(1), text)
        text = re.sub(r"<[^>]*>", "", text)
        return _html.unescape(text).replace("\xa0", " ").strip()

    def info_footer(self) -> str:
        match = re.search(r"</table><p><i>(.*?)</i></p>", self.app.model.info_text())
        return self._plain(match.group(1)) if match else ""

    def info_title(self) -> str:
        match = re.search(r"<h4>(.*?)</h4>", self.app.model.info_text())
        return self._plain(match.group(1)) if match else ""

    @staticmethod
    def state_edges(model) -> list[tuple[int, int, str, float]]:
        """The directed transitions of the diagram as (from, to, group, rate)."""
        sat = model.saturation
        edges = []
        for group_name, group, prefix in (
            ("dark", sat.dark, "k"),
            ("excitation", sat.exc, "sigma"),
        ):
            for name, parameter in group.rates_by_name().items():
                match = re.fullmatch(rf"{prefix}(\d+)_(\d+)", name)
                value = float(parameter.value)
                if match and value != 0.0 and match.group(1) != match.group(2):
                    edges.append(
                        (int(match.group(1)) - 1, int(match.group(2)) - 1, group_name, value)
                    )
        return edges


__all__ = ["SaturationPanel", "TABS"]
