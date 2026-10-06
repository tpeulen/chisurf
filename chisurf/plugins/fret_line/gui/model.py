"""The FRET line generator without Qt: the mixture, the sweep, the computed lines, the donor references and the CSV.

The window is a view over this class (``gui/fret_line_emtk.view.json`` + ``gui/app.py``). Every method a button calls
takes no arguments; ``enabled(action)`` greys the buttons that have nothing to act on, as the Qt tool did.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable

import numpy as np

from chisurf.core.registry.parameter_groups import (
    get_registered_parameter_group,
    iter_registered_parameter_groups,
    register_parameter_group,
    unregister_parameter_group,
)

from ..core.algorithms import (
    _build_component,
    _parameters_of,
    compute_fret_line_for_models,
    list_models,
    sweep_targets_for_models,
)

#: Colour cycle of the computed lines (the Qt tool's).
PALETTE = (
    "#e05c00",
    "#1f77b4",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#17becf",
    "#bcbd22",
    "#7f7f7f",
)
NO_NDX_WINDOW = "No ndX window is open to take the lines.\nOpen ndX, then push again; Save CSV keeps them in a file."


def push_to_ndx(lines) -> int:
    """Draw *lines* (the computed lines) in every open ndX window; how many took them.

    The host connection ChiSurf gives this tool: ndX draws them as data curves
    of its Overlays tab (E vs τ_F), named "FRET line — <name> · <sweep>".
    """
    from chisurf.plugins.ndxplorer.window import push_overlay_lines

    from ..core.algorithms import computed_lines_as_overlays

    taken = push_overlay_lines(computed_lines_as_overlays(lines), source="ChiSurf FRET lines")
    if not taken:
        from ndxplorer.app.frame import live_apps

        if live_apps():
            raise ValueError(
                "The open ndX window(s) rejected the lines. Check their columns "
                "and axis hints; details are in the log."
            )
    return taken


def hex_rgba(colour: str) -> tuple[int, int, int, int]:
    """``#rrggbb`` as an RGBA tuple."""
    c = colour.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255


class FretLineModel:
    """Mixture components, one sweep, and the collection of computed lines."""

    def __init__(self, push_callback: Callable[[list], Any] | None = None) -> None:
        self.model_names = list_models()
        self.push_callback = push_callback
        self.components: list[dict] = []
        self.component_index = 0
        self.show_all_parameters = False
        self._sweep_filter = ""
        self.sweep_index = 0
        self.minimum = 0.0
        self.maximum = 100.0
        self.n_points = 100
        self.log_scale = False
        self.tau_d0 = 4.0
        self.lines: list[dict] = []
        self.line_index = -1
        self._line_seq = 0
        self.message = "Ready"
        # notice dialog (the Qt tool's information / warning boxes)
        self.dialog_title = ""
        self.dialog_text = ""
        self.request = ""
        self._registered: set[str] = set()
        self._sweep_signature: list = []
        self._sweep_key = None
        self.add_component()
        self._select_default_sweep()

    # -- the mixture ----------------------------------------------------------- #
    def add_component(self) -> None:
        """Append a component of the model the selected component has (the first model when there is none)."""
        name = self.model_label if self.components else self.model_names[0]
        self.components.append({"model_name": name, "model": _build_component(name), "weight": 1.0})
        self.component_index = len(self.components) - 1
        self.sync_registry()
        self.message = f"Added component C{self.component_index}: {name}"

    def remove_component(self) -> None:
        """Remove the selected component; one always stays."""
        if len(self.components) <= 1:
            return
        removed = self.components.pop(self.component_index)
        self.component_index = min(self.component_index, len(self.components) - 1)
        self.sync_registry()
        self.message = f"Removed a {removed['model_name']} component"

    def select_component(self, record: Any) -> None:
        """The components table's ``selected_call``."""
        if isinstance(record, dict) and 0 <= int(record.get("index", -1)) < len(self.components):
            self.component_index = int(record["index"])

    def component_rows(self) -> list[dict]:
        """One row per component for the table: ``C0``, its model and its weight (the Qt list's text)."""
        return [
            {"index": i, "name": f"C{i}", "model": c["model_name"], "weight": c["weight"]}
            for i, c in enumerate(self.components)
        ]

    @property
    def selected(self) -> dict:
        return self.components[self.component_index]

    @property
    def model_label(self) -> str:
        """The model of the selected component; assigning replaces it (weight kept, parameters reset)."""
        return self.selected["model_name"]

    @model_label.setter
    def model_label(self, name: str) -> None:
        if name == self.selected["model_name"] or name not in self.model_names:
            return
        self.selected["model_name"] = name
        self.selected["model"] = _build_component(name)
        self.sync_registry()

    @property
    def weight(self) -> float:
        return self.selected["weight"]

    @weight.setter
    def weight(self, value: float) -> None:
        self.selected["weight"] = max(0.0, float(value))

    def model_labels(self) -> list[str]:
        return list(self.model_names)

    def enabled(self, action: str) -> bool:
        if action == "remove_component":
            return len(self.components) > 1
        if action in ("save_csv",):
            return bool(self.lines)
        if action == "push":
            return bool(self.lines)
        if action in ("show_all", "hide_all", "clear_lines"):
            return bool(self.lines)
        if action == "remove_line":
            return bool(self.lines)
        return True

    # -- the Global View registry ------------------------------------------------- #
    def sync_registry(self) -> None:
        """Expose each component's model to the Global View parameter registry; drop the removed ones."""
        prefix = f"native_fret_line_{id(self)}_c"
        current = {prefix + str(i) for i in range(len(self.components))}
        for owner in self._registered - current:
            unregister_parameter_group(owner)
        for i, component in enumerate(self.components):
            owner = prefix + str(i)
            if (
                owner not in self._registered
                or get_registered_parameter_group(owner) is not component["model"]
            ):
                register_parameter_group(
                    component["model"],
                    owner_id=owner,
                    label=f"FRET Line C{i}: {component['model_name']}",
                )
        self._registered = current

    def close(self) -> None:
        for owner in self._registered:
            unregister_parameter_group(owner)
        self._registered = set()

    # -- the sweep -------------------------------------------------------------------- #
    def sweep_targets(self) -> list[dict]:
        """Every sweepable parameter and mixing fraction (nuisance parameters only with *All parameters*)."""
        targets = sweep_targets_for_models(
            [c["model"] for c in self.components],
            [c["model_name"] for c in self.components],
            relevant_only=not self.show_all_parameters,
        )
        signature = [(t.get("kind"), t.get("component"), t.get("name")) for t in targets]
        if signature != self._sweep_signature and self._sweep_key in signature:
            self.sweep_index = signature.index(self._sweep_key)
        self.sweep_index = min(self.sweep_index, max(0, len(signature) - 1))
        self._sweep_signature = signature
        self._sweep_key = signature[self.sweep_index] if signature else None
        return targets

    def _select_default_sweep(self) -> None:
        targets = self.sweep_targets()
        self.sweep_index = next(
            (i for i, t in enumerate(targets) if (t.get("name") or "").startswith("distance.mean")),
            0,
        )
        self.sweep_targets()

    @property
    def sweep_filter(self) -> str:
        return self._sweep_filter

    @sweep_filter.setter
    def sweep_filter(self, text: str) -> None:
        """Filtering keeps the *Vary* choice on a target that is listed: when the current one is filtered out the first match is taken."""
        self._sweep_filter = str(text)
        matches = self.sweep_labels()
        if matches and self.sweep_label not in matches:
            self.sweep_label = matches[0]

    def sweep_labels(self) -> list[str]:
        """The labels the *Vary* choice offers: the targets that contain the filter text."""
        needle = self.sweep_filter.casefold()
        return [t["label"] for t in self.sweep_targets() if needle in t["label"].casefold()]

    @property
    def sweep_label(self) -> str:
        targets = self.sweep_targets()
        return targets[self.sweep_index]["label"] if targets else ""

    @sweep_label.setter
    def sweep_label(self, label: str) -> None:
        for i, target in enumerate(self.sweep_targets()):
            if target["label"] == label:
                self.sweep_index = i
                self.sweep_targets()
                return

    def set_all_parameters(self, value: bool) -> None:
        self.show_all_parameters = bool(value)
        self.sweep_targets()

    # -- computing and the collection of lines ----------------------------------------- #
    def add_line(self) -> dict | None:
        """Compute the current mixture and sweep and append the result as a new line (the Qt *+ Add FRET line*)."""
        try:
            targets = self.sweep_targets()
            if not targets:
                raise ValueError("No sweep target selected.")
            sweep = targets[min(self.sweep_index, len(targets) - 1)]
            snapshots = [(p, p.value) for c in self.components for p in _parameters_of(c["model"])]
            try:
                response = compute_fret_line_for_models(
                    [c["model"] for c in self.components],
                    sweep,
                    self.minimum,
                    self.maximum,
                    self.n_points,
                    [c["weight"] for c in self.components],
                    self.tau_d0 or None,
                    self.log_scale,
                )
            finally:  # a sweep moves the swept parameter; the mixture the user built stays as it was
                for parameter, value in snapshots:
                    parameter.value = value
            if not response.get("ok"):
                raise ValueError(response.get("error", "?"))
        except Exception as exc:
            self.message = f"Compute error: {exc}"
            self.dialog_title, self.dialog_text = (
                ("Sweep", "No sweep target selected.")
                if "No sweep target" in str(exc)
                else ("Compute error", str(exc))
            )
            return None
        self._line_seq += 1
        line = {
            "name": f"Line {self._line_seq}",
            "sweep_label": sweep["label"],
            "result": response["result"],
            "color": PALETTE[(self._line_seq - 1) % len(PALETTE)],
            "visible": True,
            "log": self.log_scale,
            "tau_d0": self.tau_d0 or None,
            "components": "; ".join(
                f"C{i}={c['model_name']}(w={c['weight']:g})" for i, c in enumerate(self.components)
            ),
        }
        self.lines.append(line)
        self.line_index = len(self.lines) - 1
        self.message = f"Added {line['name']}: {line['sweep_label']}"
        return line

    def line_rows(self) -> list[dict]:
        """The collection as table rows (the line dicts themselves, so a ticked *Show* writes straight into a line)."""
        for line in self.lines:
            line["colour_text"] = line["color"]
        return self.lines

    def select_line(self, record: Any) -> None:
        if isinstance(record, dict):
            for i, line in enumerate(self.lines):
                if line is record or line["name"] == record.get("name"):
                    self.line_index = i
                    return
        else:
            self.line_index = -1

    def line_edited(self, record: dict, key: str, value: Any) -> None:
        """The table wrote a ticked / unticked *Show* box."""
        self.message = f"{record['name']} {'shown' if record.get('visible') else 'hidden'}"

    def show_all(self) -> None:
        for line in self.lines:
            line["visible"] = True

    def hide_all(self) -> None:
        for line in self.lines:
            line["visible"] = False

    def remove_line(self) -> None:
        """Remove the selected line (the last one when none is selected)."""
        if not self.lines:
            return
        index = self.line_index if 0 <= self.line_index < len(self.lines) else len(self.lines) - 1
        removed = self.lines.pop(index)
        self.line_index = min(index, len(self.lines) - 1)
        self.message = f"Removed {removed['name']}"

    def clear_lines(self) -> None:
        self.lines.clear()
        self.line_index = -1
        self.message = "Cleared all lines"

    # -- export ---------------------------------------------------------------------------- #
    def save_csv(self) -> None:
        """Ask the window for the Save dialog."""
        if self.lines:
            self.request = "save"

    def write_csv(self, path: str | Path) -> None:
        """Write every line in the Qt tool's format (two comment lines, then one row per sweep point)."""
        path = Path(path)
        if path.suffix.lower() != ".csv":
            path = path.with_name(path.name + ".csv")
        with open(path, "w") as fh:
            fh.write(f"# {len(self.lines)} FRET line(s)\n")
            fh.write("# line,sweep,log,components,parameter,tau_F_ns,tau_X_ns,E_FRET\n")
            for ln in self.lines:
                r = ln["result"]
                comps = ln["components"].replace(",", ";")
                for p, tf, tx, e in zip(r["parameter_values"], r["tau_f"], r["tau_x"], r["e_fret"]):
                    fh.write(
                        f"{ln['name']},{ln['sweep_label']},{ln['log']},{comps},{p:.8g},{tf:.8g},{tx:.8g},{e:.8g}\n"
                    )
        self.notice("Saved", f"Saved {len(self.lines)} line(s) to:\n{path}")

    def push(self) -> None:
        """Hand the lines to the host's ndX connection, or say that no ndX window takes them.

        The connection returns how many windows took the lines (``0``: none is
        open); ``None`` counts as taken.
        """
        if not self.lines:
            return
        try:
            taken = None if self.push_callback is None else self.push_callback(self.lines)
        except Exception as exc:
            self.notice("Push to ndX", f"Could not send the lines: {exc}")
            return
        if self.push_callback is None or taken == 0:
            self.notice("Push to ndX", NO_NDX_WINDOW)
        else:
            self.message = f"Sent {len(self.lines)} line(s) to ndX"

    def notice(self, title: str, text: str) -> None:
        self.dialog_title, self.dialog_text = title, text

    @property
    def dialog_open(self) -> bool:
        return bool(self.dialog_text)

    def dialog_ok(self) -> None:
        self.dialog_title = self.dialog_text = ""

    # -- the parameters of the selected component (the Qt editor's table) ------------------------------------- #
    def parameter_rows(self) -> list[dict]:
        """One record per parameter the selected model uses: name, value, fixed, bounds on, lower, upper."""
        rows = []
        for p in _parameters_of(self.selected["model"]):
            low, high = p.bounds
            rows.append(
                {
                    "id": getattr(p, "canonical_id", p.name),
                    "name": p.name,
                    "value": float(p.value),
                    "fixed": bool(p.fixed),
                    "bounds_on": bool(p.bounds_on),
                    "lower": float(low) if low is not None else float("-inf"),
                    "upper": float(high) if high is not None else float("inf"),
                }
            )
        return rows

    def parameter_edited(self, record: dict, key: str, value: Any) -> None:
        """The table wrote a cell: put it into the live parameter (a value that is not a number is refused)."""
        parameter = next(
            (
                p
                for p in _parameters_of(self.selected["model"])
                if getattr(p, "canonical_id", p.name) == record["id"]
            ),
            None,
        )
        if parameter is None:
            return
        try:
            if key == "value":
                parameter.value = float(value)
            elif key == "fixed":
                parameter.fixed = bool(value)
            elif key == "bounds_on":
                parameter.bounds_on = bool(value)
            elif key in ("lower", "upper"):
                pair = list(parameter.bounds)
                pair[0 if key == "lower" else 1] = float(value)
                parameter.bounds = tuple(pair)
        except (TypeError, ValueError) as exc:
            self.message = f"{parameter.name}: {exc}"
            return
        self.message = f"{parameter.name} set"

    # -- the donor references and measured inputs of the editor ---------------------------------- #
    @staticmethod
    def spectrum_of(model: Any) -> dict:
        values = {}
        for parameter in getattr(model, "parameters_all", []):
            pieces = getattr(parameter, "canonical_id", "").split(".")
            if (
                len(pieces) == 3
                and pieces[0] in ("donor", "lifetime")
                and pieces[1] in ("amplitude", "tau")
            ):
                values[(pieces[1], int(pieces[2]))] = parameter.value
        return values

    def donor_references(self) -> list[tuple[str, dict]]:
        import chisurf

        sources = [(label, group) for _, label, group in iter_registered_parameter_groups()]
        for fit in getattr(chisurf, "fits", []):
            models = getattr(fit, "models", None) or [getattr(fit, "model", None)]
            sources.extend((getattr(m, "name", "Fit donor"), m) for m in models if m is not None)
        own = {id(c["model"]) for c in self.components}
        return [
            (label, self.spectrum_of(m))
            for label, m in sources
            if id(m) not in own and self.spectrum_of(m)
        ]

    def apply_donor_reference(self, spectrum: dict) -> None:
        model = self.selected["model"]
        group_name = "donor" if "donor" in model._groups else "lifetime"
        count = 1 + max(i for _, i in spectrum)
        from chisurf.core.fluorescence.fret.fret_line import find_parameter

        for _ in range(40):
            current = len(
                {
                    int(p.canonical_id.split(".")[-1])
                    for p in model._groups[group_name].component_parameters()
                }
            )
            if current == count:
                break
            if not model.change_components(group_name, 1 if current < count else -1):
                raise ValueError("This model cannot represent the reference spectrum.")
        for (kind, index), value in spectrum.items():
            find_parameter(model, f"{group_name}.{kind}.{index}").value = value

    def bind_input(self, slot: str, curve: Any, model: Any = None) -> None:
        x, y = np.asarray(curve.x, dtype=float), np.asarray(curve.y, dtype=float)
        if (
            x.ndim != 1
            or y.ndim != 1
            or not len(x)
            or len(x) != len(y)
            or not np.isfinite(x).all()
            or not np.isfinite(y).all()
        ):
            raise ValueError("Measured input curves need matching finite x/y arrays.")
        model = self.selected["model"] if model is None else model
        model.set_dataset(slot, curve)
        if slot == "response" and "generated_response" in model.scalar_names():
            model.set_scalar("generated_response", 0.0)

    def unload_input(self, slot: str) -> None:
        model = self.selected["model"]
        model.unset_dataset(slot)
        if slot == "response" and "generated_response" in model.scalar_names():
            model.set_scalar("generated_response", 1.0)

    # -- settings --------------------------------------------------------------------------------- #
    def export_state(self) -> dict:
        return {
            "minimum": self.minimum,
            "maximum": self.maximum,
            "n_points": self.n_points,
            "log_scale": self.log_scale,
            "tau_d0": self.tau_d0,
            "show_all_parameters": self.show_all_parameters,
        }

    def restore_state(self, settings: dict) -> None:
        for key, kind in (
            ("minimum", float),
            ("maximum", float),
            ("tau_d0", float),
            ("n_points", int),
        ):
            try:
                value = kind(settings[key])
            except (KeyError, TypeError, ValueError):
                continue
            if key == "n_points" and not 2 <= value <= 10000:
                continue
            if key == "tau_d0" and not 0.0 <= value <= 1000.0:
                continue
            setattr(self, key, value)
        for key in ("log_scale", "show_all_parameters"):
            if isinstance(settings.get(key), bool):
                setattr(self, key, settings[key])
        self.sweep_targets()
