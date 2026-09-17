"""Qt-free view model for the ALEX Suite titration panel.

Holds the concentration/file table, runs
:func:`~chisurf.plugins.burst.alex_suite.api.titration.run_titration`, and turns
the result into the plot series and the summary text the AutoForm view renders.
No Qt import — the panel is
:class:`~chisurf.plugins.burst.alex_suite.gui.titration.TitrationPanel`.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable

import numpy as np

from chisurf.plugins.burst.alex_suite.api.histograms import Corrections, Thresholds
from chisurf.plugins.burst.alex_suite.api.titration import (
    BINDING_MODELS,
    Condition,
    run_titration,
)

logger = logging.getLogger("chisurf.plugins.burst")

_VIEW_JSON = pathlib.Path(__file__).parent / "titration.view.json"

#: Colour ramp for the stack plot: cool (no ligand) to warm (saturating).
_RAMP = (
    "#3b4cc0",
    "#5977e3",
    "#7b9ff9",
    "#9ebeff",
    "#c0d4f5",
    "#f2cbb7",
    "#f7ac8e",
    "#e8765c",
    "#d03b33",
    "#b40426",
)


class TitrationViewModel:
    """State and actions of the titration step."""

    def view_spec(self):
        """Resolve AutoForm's view spec from ``titration.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        """Start with an empty series and the defaults of a 2-population fit."""
        self.rows: list[dict] = []
        self.n_populations: int = 2
        self.binding_model: str = "hill"
        self.concentration_unit: str = "nM"
        self.fix_peak_positions: bool = False
        self.bins: int = 81
        self.min_photons: int = 50
        self.gamma: float = 1.0
        self.beta: float = 1.0
        self.s_low: float = 0.3
        self.s_high: float = 0.8
        self.summary: str = (
            "Add one burst file per ligand concentration, type the "
            "concentrations, and press **Fit series**."
        )
        self._result = None
        self._observers: list[Callable[[str], None]] = []
        #: Set by the Qt panel to a callable returning chosen paths. The model
        #: never opens a dialog itself, so the same object drives a script.
        self.request_files: Callable[[], list[str]] | None = None

    # ── observer plumbing (the AutoForm convention) ─────────────────────

    def add_observer(self, callback: Callable[[str], None]) -> None:
        """Register a callback fired on every state change."""
        self._observers.append(callback)

    def notify(self, event: str = "changed") -> None:
        """Fire every registered observer."""
        for callback in list(self._observers):
            callback(event)

    def update(self) -> None:
        """AutoForm calls this after a field commits."""
        self.notify("changed")

    # ── options ─────────────────────────────────────────────────────────

    def binding_model_options(self) -> list[str]:
        """Return the isotherm models the panel offers."""
        return list(BINDING_MODELS)

    # ── the series table ────────────────────────────────────────────────

    def series_rows(self) -> list[dict]:
        """Return the table rows: one concentration and one burst file each."""
        return self.rows

    def update_series_cell(self, row: int, key: str, value) -> None:
        """Commit one edited table cell."""
        if not (0 <= row < len(self.rows)):
            return
        if key == "concentration":
            try:
                self.rows[row]["concentration"] = float(value)
            except (TypeError, ValueError):
                return
        else:
            self.rows[row][key] = str(value)
        self.notify("changed")

    def add_files(self, paths) -> None:
        """Append one row per file, keeping any concentrations already typed."""
        for path in paths:
            self.rows.append(
                {
                    "concentration": 0.0,
                    "file": str(path),
                    "name": pathlib.Path(path).name,
                }
            )
        self.notify("changed")

    def browse_files(self) -> None:
        """Ask the host for files and append a row for each."""
        if self.request_files is None:
            return
        self.add_files(self.request_files() or [])

    def remove_last_row(self) -> None:
        """Drop the last row."""
        if self.rows:
            self.rows.pop()
            self.notify("changed")

    def clear_rows(self) -> None:
        """Drop every row and the fit that went with them."""
        self.rows = []
        self._result = None
        self.notify("changed")

    # ── the fit ─────────────────────────────────────────────────────────

    def can_run(self) -> str | None:
        """Return ``None`` when the fit can run, else why it cannot."""
        if len(self.rows) < 2:
            return "A titration needs at least two concentrations."
        if len({r["concentration"] for r in self.rows}) < len(self.rows):
            return "Two rows have the same concentration — check the table."
        missing = [r["file"] for r in self.rows if not pathlib.Path(r["file"]).exists()]
        if missing:
            return f"Missing file: {pathlib.Path(missing[0]).name}"
        return None

    def run(self) -> None:
        """Fit the whole series and store the result."""
        problem = self.can_run()
        if problem:
            self.summary = problem
            self._result = None
            self.notify("changed")
            return
        conditions = [
            Condition(
                concentration=float(row["concentration"]),
                source=row["file"],
                label=f"{row['concentration']:g} {self.concentration_unit}",
            )
            for row in self.rows
        ]
        try:
            self._result = run_titration(
                conditions,
                n_components=int(self.n_populations),
                binding_model=self.binding_model,
                corrections=Corrections(gamma=self.gamma, beta=self.beta),
                thresholds=Thresholds(
                    total_min=float(self.min_photons),
                    s_range_for_e=(self.s_low, self.s_high),
                ),
                bins=int(self.bins),
                fix_centres=bool(self.fix_peak_positions),
                fix_widths=bool(self.fix_peak_positions),
            )
        except Exception as exc:
            logger.warning(f"ALEX Suite: titration fit failed — {exc}")
            self._result = None
            self.summary = f"Fit failed: {exc}"
            self.notify("changed")
            return
        self.summary = self._summarise()
        logger.info(self.summary.replace("**", "").splitlines()[0])
        self.notify("changed")

    def _summarise(self) -> str:
        """Return the markdown summary shown under the plots."""
        result = self._result
        if result is None:
            return "No fit yet."
        fit, binding = result.fit, result.binding
        lines = [
            f"**{len(result.stack)} concentrations**, "
            f"{int(fit.fractions.shape[1])} shared populations "
            f"(χ²ᵣ = {fit.chi2r:.3g}).",
            "",
            "| population | E | width | fraction (lowest → highest) |",
            "|---|---|---|---|",
        ]
        for k in range(fit.centres.size):
            low, high = fit.fractions[0, k], fit.fractions[-1, k]
            mark = " ←" if k == result.component else ""
            lines.append(
                f"| {k}{mark} | {fit.centres[k]:.3f} | {fit.widths[k]:.3f} | "
                f"{low:.2f} → {high:.2f} |"
            )
        if binding is None:
            lines += ["", "_Three concentrations are needed for a binding fit._"]
        else:
            lines += [
                "",
                f"**K_d = {binding.kd:.3g} {self.concentration_unit}** "
                f"(Hill n = {binding.hill:.2f}, χ²ᵣ = {binding.chi2r:.3g}), "
                f"from population {result.component}.",
            ]
        return "\n".join(lines)

    # ── plot sources ────────────────────────────────────────────────────

    def stack_series(self) -> list[dict]:
        """Return the stack plot: one offset histogram per concentration."""
        result = self._result
        if result is None:
            return []
        stack, fit = result.stack, result.fit
        # Offset by a constant fraction of the tallest row: a stack plot whose
        # rows overlap is unreadable, and one whose offset is per-row is a lie
        # about the relative amplitudes.
        step = float(np.max(stack.histograms)) * 0.55 if stack.histograms.size else 1.0
        series = []
        for i in range(len(stack)):
            colour = _RAMP[int(i * (len(_RAMP) - 1) / max(len(stack) - 1, 1))]
            base = i * step
            series.append(
                {
                    "x": stack.centres.tolist(),
                    "y": (stack.histograms[i] + base).tolist(),
                    "name": stack.labels[i],
                    "color": colour,
                    "width": 1,
                }
            )
            series.append(
                {
                    "x": stack.centres.tolist(),
                    "y": (fit.curves[i] + base).tolist(),
                    "color": "#444444",
                    "width": 2,
                    "style": "dash",
                }
            )
        return series

    def binding_series(self) -> list[dict]:
        """Return the isotherm: the measured fractions and the fitted curve."""
        result = self._result
        if result is None:
            return []
        fractions = result.fit.fractions[:, result.component]
        series = [
            {
                "x": result.stack.concentrations.tolist(),
                "y": fractions.tolist(),
                "name": f"population {result.component}",
                "color": "#b40426",
                "symbol": "o",
                "symbol_size": 10,
                "no_line": True,
            }
        ]
        if result.binding is not None:
            series.append(
                {
                    "x": result.binding.curve_x.tolist(),
                    "y": result.binding.curve_y.tolist(),
                    "name": f"K_d = {result.binding.kd:.3g} {self.concentration_unit}",
                    "color": "#3b4cc0",
                    "width": 2,
                }
            )
        return series

    def binding_axes(self) -> dict:
        """Axis labels/scale for the isotherm plot."""
        return {
            "x_label": f"[ligand] ({self.concentration_unit})",
            "y_label": "fraction",
            "log_x": True,
        }

    # ── export ──────────────────────────────────────────────────────────

    def result(self):
        """Return the last :class:`TitrationResult`, or ``None``."""
        return self._result

    def export_csv(self, path: str | pathlib.Path) -> pathlib.Path:
        """Write the stack, the fitted curves and the isotherm as one CSV.

        One file, three blocks, because a titration is one result — three files
        get separated the first time someone moves a folder.

        Raises
        ------
        ValueError
            If nothing has been fitted yet.
        """
        import csv

        result = self._result
        if result is None:
            raise ValueError("nothing to export — run the fit first")
        path = pathlib.Path(path)
        stack, fit = result.stack, result.fit
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["STACK"])
            writer.writerow(
                ["E"]
                + [f"{lab} data" for lab in stack.labels]
                + [f"{lab} fit" for lab in stack.labels]
            )
            for j, centre in enumerate(stack.centres):
                writer.writerow(
                    [centre] + [row[j] for row in stack.histograms] + [row[j] for row in fit.curves]
                )
            writer.writerow([])
            writer.writerow(["POPULATIONS"])
            writer.writerow(["population", "E", "width"])
            for k in range(fit.centres.size):
                writer.writerow([k, fit.centres[k], fit.widths[k]])
            writer.writerow([])
            writer.writerow(["ISOTHERM"])
            writer.writerow(
                [f"concentration ({self.concentration_unit})"]
                + [f"fraction {k}" for k in range(fit.centres.size)]
            )
            for i, concentration in enumerate(stack.concentrations):
                writer.writerow([concentration, *fit.fractions[i]])
            if result.binding is not None:
                writer.writerow([])
                writer.writerow(["BINDING FIT"])
                for name, value in (
                    ("model", result.binding.model),
                    (f"Kd ({self.concentration_unit})", result.binding.kd),
                    ("hill", result.binding.hill),
                    ("f_min", result.binding.f_min),
                    ("f_max", result.binding.f_max),
                    ("chi2r", result.binding.chi2r),
                    ("population", result.component),
                ):
                    writer.writerow([name, value])
        return path
