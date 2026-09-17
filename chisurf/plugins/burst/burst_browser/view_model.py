"""Qt-free view-model backing the Burst Browser (AutoForm) tool.

:class:`BurstBrowserViewModel` reads burstwise ``.bur`` tables (merging the ``…4``
companions — BVA ``bv4``, 2CDE ``2c4`` … — via
:func:`chisurf.core.fio.fluorescence.burst.read_bur_with_companions`), derives the
per-burst FRET efficiency ``E`` and stoichiometry ``S`` when absent, and holds the
gating state (E/S/size ranges, selected detector, histogram column, selection
mode). It computes the gating mask and the histogram data. All Qt concerns (table
view, plot, combos, foldable panels, docks) live in ``gui/sections.py`` + the
AutoForm rendered from ``burst_browser.view.json``.

The table is a columnar store, not a data frame — see the
[columnar store concept](/subsystems/columnar-store.md). A folder of ten
measurements is stacked into one store, and every column this asks for is
already numeric, so the whole gating path is plain numpy over
:func:`~chisurf.core.datastore.numeric_column`.
"""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Callable
from typing import Any

import numpy as np

from chisurf.core.datastore import (
    column_names,
    concat_stores,
    numeric_column,
    row_count,
    store_from_arrays,
    take_where,
)
from chisurf.core.fio.fluorescence import burst as burstio
from chisurf.core.fio.fluorescence import burst_tree

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "gui" / "burst_browser.view.json"

_ALL = "All"


class BurstBrowserViewModel:
    """State + logic for the Burst Browser (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``burst_browser.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        # Data state.
        #: The burst table, as a ``tttrlib.DataStore``.
        self.table: Any = None
        self.mask: np.ndarray | None = None
        self.path_text: str = "No data loaded"
        self._col_E: str | None = None
        self._col_S: str | None = None
        self._col_size: str | None = None
        self.have_E: bool = False
        self.have_S: bool = False
        self.setup_info: dict | None = None
        self.setup_windows: dict | None = None
        self.setup_detectors: dict | None = None
        #: Base-frame row indices selected in the table (set by the table section).
        self.selected_indices: list[int] = []

        # Bound controls (AutoForm value/choice/toggle sections).
        self.detector: str = _ALL
        self.hist_column: str = ""
        self.e_min: float = 0.0
        self.e_max: float = 1.0
        self.s_min: float = 0.0
        self.s_max: float = 1.0
        self.size_min: int = 0
        self.size_max: int = 0
        self.use_selection: bool = False

        self._observers: list[Callable[[str], None]] = []

    # ── observer hook ──────────────────────────────────────────────────
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb* to be called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("burst-browser observer failed", exc_info=True)

    def update(self) -> None:
        """AutoForm hook: a bound value/toggle changed — recompute + refresh."""
        self.refresh()

    def refresh(self) -> None:
        """Recompute the gating mask and notify observers (gating/column/toggle)."""
        self._recompute_mask()
        self.notify("gating")

    # ── AutoForm choice sources ────────────────────────────────────────
    def detector_options(self) -> list[str]:
        """Detector names for the combo (``All`` + names from columns/setup)."""
        dets: set[str] = set()
        if self.table is not None:
            for s in column_names(self.table):
                if s.startswith("Number of Photons (") and ")" in s:
                    name = s.split("Number of Photons (", 1)[1].split(")", 1)[0]
                    # "Number of Photons (fit window) (green)" yields "fit window",
                    # which is not a detector — skip it.
                    if name and name != "fit window":
                        dets.add(name)
        try:
            if self.setup_detectors:
                dets.update(str(d) for d in self.setup_detectors.keys())
        except Exception:
            pass
        return [_ALL, *sorted(dets)]

    def hist_column_options(self) -> list[str]:
        """Histogram-column choices — global first, then detector-scoped columns."""
        if self.table is None:
            return []
        names = column_names(self.table)
        preferred: list[str] = []
        for col in ("E", "S", "Number of Photons"):
            if col in names and col not in preferred:
                preferred.append(col)

        sel_det = None if self.detector in ("", _ALL) else str(self.detector)
        for c in names:
            if c in preferred:
                continue
            if sel_det:
                if f"({sel_det})" in c or f" {sel_det} (" in c or f" {sel_det})" in c:
                    preferred.append(c)
                elif "Count Rate" in c and sel_det.lower() in c.lower():
                    preferred.append(c)
            elif "Count Rate" in c or "Number of Photons (" in c:
                preferred.append(c)
        return preferred or names

    def on_detector_changed(self, value: str) -> None:
        """Detector combo changed — keep it and re-derive the column choices."""
        self.detector = value
        cols = self.hist_column_options()
        if cols and self.hist_column not in cols:
            self.hist_column = cols[0]
        self.notify("gating")

    # ── loading ────────────────────────────────────────────────────────
    def load_bur(self, path) -> None:
        """Load a single ``.bur`` file (with its ``…4`` companions)."""
        path = pathlib.Path(path)
        table = burstio.read_bur_with_companions(path)
        self.path_text = str(path)
        self._prepare_table(table)
        self._load_setup_info(path.parent)
        self.refresh()
        self.notify("data")

    def _load_container(self, path) -> None:
        """Load the burst table of a `.pto` run (or the file's first run)."""
        from chisurf.core.fio.fluorescence.burst import read_burst_analysis

        try:
            table, _ = read_burst_analysis(path, "PTO")
        except Exception as exc:
            logger.warning("BurstBrowser: could not read %s: %s", path, exc)
            return
        if table is None or row_count(table) == 0:
            logger.info("No bursts in: %s", path)
            return
        self.path_text = str(path)
        self._prepare_table(table)
        self._load_setup_info(pathlib.Path(path).parent)
        self.refresh()
        self.notify("data")

    def load_folder(self, folder) -> None:
        """Load a burst analysis: a folder of ``.bur`` files, or a container.

        A `.pto` is addressed like a folder and *is* where a container-backed
        burst search puts its results, so a workflow that hands this browser its
        output hands it a container path — which ``is_dir()`` answers ``False``
        for. The browser then logged "Folder does not exist" and showed nothing,
        with the analysis sitting in the file it had just been given.
        """
        folder = pathlib.Path(folder)
        if burst_tree.is_container_path(folder):
            self._load_container(folder)
            return
        if not folder.exists() or not folder.is_dir():
            logger.warning("Folder does not exist: %s", folder)
            return
        bur_files = sorted(folder.glob("**/*.bur"))
        if not bur_files:
            logger.info("No .bur files found in: %s", folder)
            return
        parts: list[Any] = []
        for fn in bur_files:
            try:
                part = burstio.read_bur_with_companions(fn)
                # A dictionary-encoded text column: one string per file, not one
                # per burst, however many measurements are stacked.
                part.append_columns(
                    store_from_arrays({"burst_file": np.full(row_count(part), fn.name)})
                )
                parts.append(part)
            except Exception as exc:
                logger.warning("BurstBrowser: failed to read %s: %s", fn, exc)
        if not parts:
            logger.info("No .bur files could be read.")
            return
        table = concat_stores(parts)
        self.path_text = f"{folder} ({len(bur_files)} .bur)"
        self._prepare_table(table)
        self._load_setup_info(folder)
        self.refresh()
        self.notify("data")

    # ── data prep (E / S / size columns + gating ranges) ───────────────
    def _prepare_table(self, table: Any) -> None:
        names = column_names(table)
        if "Number of Photons" in names:
            table = take_where(table, numeric_column(table, "Number of Photons") > 0)

        self._col_E = self._col_S = self._col_size = None
        self.have_E = self.have_S = False
        red_col = green_col = None
        derived: dict[str, np.ndarray] = {}

        # Which columns are the FRET channels is a question the shared burst-table
        # conventions answer -- including the case that matters here: on a
        # PIE/ALEX table the *gated* streams are the channels, and the
        # whole-detector "Number of Photons (red)" beside them sums the acceptor
        # over BOTH excitation periods. Deriving E from those un-gated columns
        # gave (DA + AA) / (DD + DA + AA + AD), which is not a proximity ratio
        # and put the populations of a two-state sample at the wrong efficiency.
        from chisurf.core.fluorescence.burst.es import apparent_es
        from chisurf.core.fluorescence.burst.table import guess_columns

        mapping = guess_columns(names)
        green_col, red_col = mapping.get("i_dd"), mapping.get("i_da")
        yellow_col = mapping.get("i_aa")

        if "E" in names:
            self._col_E, self.have_E = "E", True
        elif "Proximity Ratio" in names:
            self._col_E, self.have_E = "Proximity Ratio", True
        elif green_col and red_col:
            i_dd = numeric_column(table, green_col)
            i_da = numeric_column(table, red_col)
            i_aa = numeric_column(table, yellow_col) if yellow_col else None
            values = apparent_es(i_dd, i_da, i_aa)
            with np.errstate(divide="ignore", invalid="ignore"):
                derived["E"] = np.where(i_dd + i_da > 0, values["E"], np.nan)
                if values["S"] is not None:
                    total = i_dd + i_da + i_aa
                    derived["S"] = np.where(total > 0, values["S"], np.nan)
            self._col_E, self.have_E = "E", True

        if "S" in names:
            self._col_S, self.have_S = "S", True
        elif "S" in derived:
            self._col_S, self.have_S = "S", True
        elif self.have_E and red_col and green_col and "Number of Photons" in names:
            # No acceptor-excitation channel: the closest thing to a
            # stoichiometry is the FRET pair's share of all the burst's photons.
            nd = numeric_column(table, green_col)
            na = numeric_column(table, red_col)
            total = numeric_column(table, "Number of Photons")
            with np.errstate(divide="ignore", invalid="ignore"):
                derived["S"] = np.where(total > 0, (nd + na) / total, np.nan)
            self._col_S, self.have_S = "S", True

        if derived:
            table.append_columns(store_from_arrays(derived))

        if "Number of Photons" in names:
            self._col_size = "Number of Photons"
        else:
            cands = [c for c in names if "Number of Photons" in c]
            self._col_size = cands[0] if cands else None

        self.table = table
        self.selected_indices = []

        # Seed the gating ranges from the data.
        self.e_min, self.e_max = self._col_range(self._col_E, 0.0, 1.0, as_int=False)
        self.s_min, self.s_max = self._col_range(self._col_S, 0.0, 1.0, as_int=False)
        smin, smax = self._col_range(self._col_size, 0, 0, as_int=True)
        self.size_min, self.size_max = int(smin), int(smax)

        # Reset the choice selections to valid values for the new frame.
        self.detector = _ALL
        cols = self.hist_column_options()
        self.hist_column = cols[0] if cols else ""

    def _col_range(self, col, lo, hi, *, as_int):
        if not col or self.table is None or col not in column_names(self.table):
            return lo, hi
        v = numeric_column(self.table, col)
        if not np.isfinite(v).any():
            return lo, hi
        vmin = float(np.nanmin(v))
        vmax = float(np.nanmax(v))
        if as_int:
            vmin, vmax = max(0, int(vmin)), int(vmax)
        if vmin >= vmax:
            return lo, hi
        return vmin, vmax

    # ── gating ─────────────────────────────────────────────────────────
    def _recompute_mask(self) -> None:
        if self.table is None:
            self.mask = None
            return
        names = column_names(self.table)
        mask = np.ones(row_count(self.table), dtype=bool)
        for have, col, lo, hi in (
            (self.have_E, self._col_E, self.e_min, self.e_max),
            (self.have_S, self._col_S, self.s_min, self.s_max),
            (self._col_size is not None, self._col_size, self.size_min, self.size_max),
        ):
            if have and col and col in names:
                c = numeric_column(self.table, col)
                mask &= np.isfinite(c) & (c >= float(lo)) & (c <= float(hi))
        self.mask = mask

    def status_text(self) -> str:
        """One-line 'N / total selected' summary for the status bar."""
        if self.table is None or self.mask is None:
            return "No data loaded"
        return f"Bursts: {int(self.mask.sum())} / {row_count(self.table)} selected"

    def masked_row_indices(self) -> np.ndarray:
        """Table row indices passing the gate (all rows if no mask yet)."""
        if self.table is None:
            return np.zeros(0, dtype=int)
        if self.mask is None:
            return np.arange(row_count(self.table))
        return np.where(self.mask)[0]

    # ── histogram ──────────────────────────────────────────────────────
    def histogram(self) -> dict | None:
        """Return ``{centers, counts, width, label}`` for the current column.

        Uses the table selection when ``use_selection`` is on, else all gated
        bursts. Returns ``None`` when there is nothing to plot.
        """
        if self.table is None:
            return None
        col = self.hist_column
        if not col or col not in column_names(self.table):
            return None
        if self.use_selection:
            rows = np.asarray(self.selected_indices, dtype=int)
        else:
            rows = self.masked_row_indices()
        if rows.size == 0:
            return None
        # Not-finite rather than not-a-number: an infinity survived the frame's
        # dropna() and then made np.histogram refuse the whole column, so the
        # plot went blank rather than dropping the one row.
        data = numeric_column(self.table, col)[rows]
        data = data[np.isfinite(data)]
        if data.size == 0:
            return None
        counts, edges = np.histogram(data, bins=60)
        if counts.size == 0:
            return None
        centers = 0.5 * (edges[:-1] + edges[1:])
        return {
            "centers": centers,
            "counts": counts,
            "width": float(edges[1] - edges[0]),
            "label": str(col),
        }

    # ── setup info ─────────────────────────────────────────────────────
    def _load_setup_info(self, root: pathlib.Path) -> None:
        self.setup_info = self.setup_windows = self.setup_detectors = None
        try:
            from chisurf.core.settings.file_utils import safe_open_file
        except Exception:
            return
        for info_dir in (root / "Info", root.parent / "Info"):
            jf = info_dir / "photon_selection_parameters.json"
            if jf.exists():
                try:
                    data = safe_open_file(
                        jf,
                        processor=json.load,
                        default_value=None,
                        error_message=f"Could not read setup info from {jf}",
                    )
                except Exception as exc:
                    logger.warning("BurstBrowser: failed to read setup info: %s", exc)
                    data = None
                if isinstance(data, dict):
                    setup = data.get("setup_info") or {}
                    if isinstance(setup, dict):
                        self.setup_info = setup
                        self.setup_windows = setup.get("windows", {}) or {}
                        self.setup_detectors = setup.get("detectors", {}) or {}
                        logger.info("BurstBrowser: loaded experimental setup from %s", info_dir)
                return


__all__ = ["BurstBrowserViewModel"]
