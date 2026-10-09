"""Qt-free state of the FCS curve merger (the Qt ``WizardFcsMerger`` page's logic).

The curves of a correlation folder, which of them are used, the highlighted one, the
target file and the merge. Reading and averaging are the core's
(:mod:`chisurf.core.fluorescence.fcs.merge`); this model adds the screening table, the
lag-grid check the average needs, and the target name the Qt page derives.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from chisurf.core.fluorescence.fcs.merge import _correlation_from_cor_array

from ..api import compute_average_correlations, save_mean_correlation


def target_for(folder) -> str:
    """The Qt page's target: ``<parent>/<sanitised folder name>.cor``."""
    folder = Path(folder)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", folder.stem)
    if not stem or stem in {".", "..", "_"}:
        stem = "correlation"
    return str(folder.parent / f"{stem}.cor")


def channel_rates(curve) -> tuple[float, float]:
    """CR A and CR B in kHz, as the Qt table computes them (half the total rate as a fallback)."""
    duration = float(curve.get("duration", 0.0))
    try:
        if duration <= 0:
            return 0.0, 0.0
        return (
            float(curve["channel_a"]["counts"]) / duration / 1000.0,
            float(curve["channel_b"]["counts"]) / duration / 1000.0,
        )
    except (KeyError, TypeError):
        half = float(curve.get("count_rate", 0.0)) / 2.0
        return half, half


def read_folder(folder):
    """``(curves, paths, skipped)`` of a folder's ``*.json.gz`` then ``*.cor`` chunks, in the Qt order."""
    from chisurf.core.fio.zipped import open_maybe_zipped

    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"{folder} is not a folder.")
    curves, paths, skipped = [], [], []
    for path in sorted(folder.glob("*.json.gz")) + sorted(folder.glob("*.cor")):
        try:
            if path.name.endswith(".json.gz"):
                with open_maybe_zipped(path) as stream:
                    curve = json.load(stream)
            else:
                curve = _correlation_from_cor_array(np.loadtxt(str(path), delimiter="\t"))
        except Exception as exc:  # noqa: BLE001 - a bad chunk is listed, the rest load
            skipped.append(f"{path.name}: {exc}")
            continue
        curves.append(curve)
        paths.append(str(path))
    if not curves:
        raise ValueError(f"No readable .cor or .json.gz curves in {folder}.")
    validate(curves)
    return curves, paths, skipped


def validate(curves):
    """Refuse curves the average cannot combine: unequal or non-finite lag grids."""
    axis = None
    for curve in curves:
        x = np.asarray(curve["x"], dtype=float)
        y = np.asarray(curve["y"], dtype=float)
        if x.ndim != 1 or y.ndim != 1 or len(x) != len(y) or len(x) < 2:
            raise ValueError(
                "Each correlation needs matching one-dimensional lag and correlation arrays."
            )
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise ValueError("Correlation data must contain finite lag times and values.")
        if axis is not None and (
            len(x) != len(axis) or not np.allclose(x, axis, rtol=1e-9, atol=0)
        ):
            raise ValueError("Curves must share the same lag grid; resample before averaging.")
        axis = x


class MergerModel:
    """The curves on screen and the merge of the used ones."""

    def __init__(self):
        self.correlations = []
        self.paths = []
        self.use = []
        self.selected = -1
        self.folder = ""
        self.output = ""
        self.status = "Drop or open a folder of correlation curves."
        self.error = ""
        self._rows = []

    # -- curves ------------------------------------------------------------------------
    def set_correlations(self, correlations, source_folder=None, paths=None):
        """Show *correlations* (all used); a source folder sets the folder and the Qt target."""
        validate(correlations)
        self.correlations = list(correlations)
        self.paths = (
            list(paths) if paths else [f"chnk-{i:04}" for i in range(len(self.correlations))]
        )
        self.use = [True] * len(self.correlations)
        self.selected = 0 if self.correlations else -1
        if source_folder:
            self.folder = str(source_folder)
            self.output = target_for(source_folder)
        self._rebuild()

    def clear(self):
        self.correlations, self.paths, self.use, self.selected = [], [], [], -1
        self.folder = self.output = self.error = ""
        self.status = "Drop or open a folder of correlation curves."
        self._rebuild()

    @property
    def labels(self):
        return [Path(path).name for path in self.paths]

    @property
    def mean_correlation(self):
        """The average of the used curves; of all of them when none is used, as the Qt page does."""
        chosen = [c for c, used in zip(self.correlations, self.use) if used] or self.correlations
        return compute_average_correlations(chosen) if chosen else None

    def n_used(self):
        return sum(self.use) if any(self.use) else len(self.use)

    # -- the table ---------------------------------------------------------------------
    def _rebuild(self):
        rows = []
        for i, (curve, path) in enumerate(zip(self.correlations, self.paths)):
            rate_a, rate_b = channel_rates(curve)
            rows.append(
                {
                    "index": i,
                    "use": bool(self.use[i]),
                    "file": Path(path).stem,
                    "cr_a": rate_a,
                    "cr_b": rate_b,
                    "duration": float(curve.get("duration", 0.0)),
                    "path": str(path),
                    "muted": not self.use[i],
                }
            )
        self._rows = rows  # a new list: the table rebinds on its identity

    def curve_rows(self):
        return self._rows

    def cell_editable(self, record, key):
        return key == "use"

    def use_edited(self, record, key, value):
        if key == "use":
            self.use[record["index"]] = bool(value)
            self._rebuild()

    def select_curve(self, record):
        if isinstance(record, dict):
            self.selected = record["index"]

    def toggle_curve(self, record):
        """A double click toggles a curve in or out of the merge, as in the Qt table."""
        if isinstance(record, dict):
            index = record["index"]
            self.use[index] = not self.use[index]
            self._rebuild()

    def remove_curve(self, record):
        if not isinstance(record, dict):
            return
        index = record["index"]
        for values in (self.correlations, self.paths, self.use):
            values.pop(index)
        self.selected = min(self.selected, len(self.correlations) - 1)
        self._rebuild()

    # -- output ------------------------------------------------------------------------
    def save(self, filename=None):
        mean = self.mean_correlation
        if mean is None:
            raise ValueError("Load curves before saving a merge.")
        target = Path(filename or self.output or "")
        if not str(filename or self.output or "").strip():
            raise ValueError("Set a target file first.")
        save_mean_correlation(mean, target)
        return target

    # -- persisted state ---------------------------------------------------------------
    def export_state(self):
        return {
            "folder": self.folder,
            "output": self.output,
            "use": list(self.use),
            "selected": self.selected,
        }
