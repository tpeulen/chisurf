"""The ALEX Suite window: the old program's workflow, over ChiSurf's tools.

Someone arriving from ALEX-Suite knows an order — pick files, set the microscope,
run the burst search, then E vs S, Burst Properties, Titration, with BVA, the
Dataset Viewer and the Trace Viewer behind "Advanced". Everything in that list
exists in ChiSurf, under other names, in eight separate windows. That is the only
real barrier to switching, and it is a *navigation* problem, so this plugin is a
navigation shell and not a new analysis.

It subclasses
:class:`~chisurf.plugins.burst.burst_analysis.gui.tool.BurstAnalysisTool` and
replaces only the panel list. Everything below that — how the detector setup, the
raw files and the burst folder are threaded from one step to the next — is the
same code the PIE workflow runs, so the **output is the same**: one `.pto`
container per measurement with the bursts inside it and the companion tables
beside them (``okf/subsystems/burst-companions.md``). There is no ALEX-shaped
result format, and an analysis started here can be finished in the Burst Analysis
window and back again.

Two steps are ALEX Suite's own because the old program had them and ChiSurf did
not: :mod:`.alternation` (which is what makes µs-ALEX data ordinary PIE data) and
:mod:`.titration`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from qtpy import QtWidgets

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.navigation import embed_mainwindow
from chisurf.plugins.burst.burst_analysis.gui.tool import (
    BurstAnalysisTool,
    _bind,
    _burst_accurate_fret,
    _burst_background,
    _burst_browser,
    _burst_bva,
    _burst_selection,
    _data_selection,
)

logger = logging.getLogger("chisurf.plugins.burst")

# ``burst_analysis`` is this plugin's one hard dependency, and the reason its
# manifest names so few optional ones: every burst tool the pipeline embeds
# (burst_selection, burst_background, accurate_fret, burst_browser, burst_bva)
# is reached through *its* panel factories, so those edges belong to
# burst_analysis's manifest and declaring them again here would be a second
# statement to keep true.


# ── the two panels this workflow adds ───────────────────────────────────


def _alternation(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the µs-ALEX alternation step."""
    from .alternation import AlexAlternationPanel

    widget = AlexAlternationPanel(parent=parent)
    _bind(parent, "alternation", widget)
    return widget


def _titration(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the titration / stack-plot step."""
    from .titration import TitrationPanel

    widget = TitrationPanel(parent=parent)
    _bind(parent, "titration", widget)
    return widget


def _legacy_export(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the ALEX-Suite-compatible CSV export."""
    from .legacy_export_panel import LegacyExportPanel

    widget = LegacyExportPanel(parent=parent)
    _bind(parent, "legacy_export", widget)
    return widget


def _es_explorer(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the E–S view: ndX, which is the old E vs S *and* Dataset Viewer.

    The old program had two windows here — a fixed E–S histogram with
    thresholds, and a "Dataset Viewer" that plotted any burst property against
    any other. ndX is both, so they are one step.
    """
    from chisurf.plugins.ndxplorer.rpc_bridge import make_ndxplorer

    widget = embed_mainwindow(make_ndxplorer())
    _bind(parent, "es", widget)
    return widget


def _trace(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the trace viewer."""
    from chisurf.plugins.tttr.trace_browser.gui.tool import TraceBrowserTool

    widget = embed_mainwindow(TraceBrowserTool())
    _bind(parent, "trace", widget)
    return widget


# ── the workflow ────────────────────────────────────────────────────────

#: The pipeline, in the order the old program's windows were used. Six numbered
#: steps and five side tools — deliberately fewer than the Burst Analysis
#: window's eight, because everything an ALEX experiment does not need
#: (segmentation, per-segment fits, fusion) is reachable there and is noise here.
ALEX_PANELS = [
    {
        "name": "1. Files",
        "icon": Glyphs.OPEN,
        "description": (
            "The measurements. Any format tttrlib reads, including the .sm "
            "files the old ALEX-Suite worked on."
        ),
        "factory": _data_selection,
        "role": "data",
    },
    # Optional, and the shell therefore walks past it without running it: this
    # step *rewrites the measurements*, and pressing Next should never do that
    # on data that is already PIE.
    {
        "name": "2. Alternation (µs-ALEX)",
        "icon": "🚦",
        "description": (
            "µs-ALEX only: find the laser alternation and fold it into the "
            "micro-time, which turns the measurement into ordinary PIE data. "
            "Skip for PIE / ns-ALEX."
        ),
        "factory": _alternation,
        "role": "alternation",
        "optional": True,
    },
    {
        "name": "3. Burst search",
        "icon": Glyphs.SEARCH,
        "description": (
            "Find the bursts. All-photon (APBS) or dual-channel (DCBS) — the "
            "old program's two search modes are the search settings here."
        ),
        "factory": _burst_selection,
        "role": "selection",
    },
    {
        "name": "4. Background",
        "icon": "🌙",
        "description": (
            "Per-channel background rate from the inter-photon times — the "
            "numbers the old Accurate FRET panel asked you to type in."
        ),
        "factory": _burst_background,
        "role": "background",
    },
    {
        "name": "5. Accurate FRET",
        "icon": Glyphs.TARGET,
        "description": (
            "α, δ, γ and β from the donor-only, acceptor-only and FRET "
            "populations of your own bursts — no hand-drawn gates."
        ),
        "factory": _burst_accurate_fret,
        "role": "accurate_fret",
    },
    {
        "name": "6. E–S histogram",
        "icon": Glyphs.CHART,
        "description": (
            "The E vs S map, its projections, and any burst property against "
            "any other — the old E vs S and Dataset Viewer windows in one."
        ),
        "factory": _es_explorer,
        "role": "es",
    },
    {
        "name": "────────",
        "icon": "",
        "separator": True,
        "role": "separator",
    },
    {
        "name": "Burst properties",
        "icon": Glyphs.COPY,
        "description": "The burst table: sizes, durations, per-channel counts.",
        "factory": _burst_browser,
        "role": "browser",
    },
    {
        "name": "Titration",
        "icon": "🧪",
        "description": (
            "A concentration series fitted together with shared population "
            "positions, and the binding isotherm in it."
        ),
        "factory": _titration,
        "role": "titration",
        "optional": True,
    },
    {
        "name": "BVA",
        "icon": Glyphs.CHART,
        "description": (
            "Burst variance analysis: is a population one state, or fast "
            "exchange between two?"
        ),
        "factory": _burst_bva,
        "role": "bva",
    },
    {
        "name": "Trace viewer",
        "icon": "📈",
        "description": "The binned photon trace of a measurement, per channel.",
        "factory": _trace,
        "role": "trace",
    },
    {
        "name": "Export (ALEX-Suite CSV)",
        "icon": Glyphs.SAVE,
        "description": (
            "The five CSV files the old program wrote, for scripts built on "
            "that layout. The analysis itself is in the .pto container."
        ),
        "factory": _legacy_export,
        "role": "legacy_export",
        "optional": True,
    },
]


class AlexSuiteTool(BurstAnalysisTool):
    """The ALEX Suite pipeline: same engine as Burst Analysis, ALEX's order."""

    PANELS = ALEX_PANELS
    TITLE = "ALEX Suite"
    NAVIGATION_WIDTH = 280
    NAVIGATION_MIN_WIDTH = 260

    def __init__(self, parent=None):
        """Create the ALEX Suite window."""
        #: Burst files already opened in ndX, so returning to that step does not
        #: reload them over the user's selections.
        self._es_loaded: list[str] = []
        super().__init__(parent)

    def _apply_context_to_panel(self, role: str, widget: QtWidgets.QWidget) -> None:
        """Apply the workflow context, including to this workflow's own steps."""
        if role == "alternation":
            self._apply_context_to_alternation(widget)
        elif role == "titration":
            self._apply_context_to_titration(widget)
        elif role == "legacy_export":
            self._apply_context_to_legacy_export(widget)
        elif role == "es":
            self._apply_context_to_es(widget)
        elif role == "trace":
            self._apply_context_to_trace(widget)
        else:
            super()._apply_context_to_panel(role, widget)

    # ── the ALEX-only steps ─────────────────────────────────────────────

    def _apply_context_to_alternation(self, widget: QtWidgets.QWidget) -> None:
        """Give the alternation step the raw files chosen in step 1."""
        setter = getattr(widget, "set_files", None)
        if callable(setter) and self.workflow_context.raw_files:
            setter(self.workflow_context.raw_files)

    def adopt_alex_conversion(self, setup: dict, converted) -> None:
        """Take the alternation step's output as the workflow's data and setup.

        Called by :class:`~.alternation.AlexAlternationPanel` once it has
        converted. Two things change at once and both matter: the *files* the
        rest of the pipeline analyses become the converted containers (analysing
        the originals would mean searching an un-folded stream, where every
        micro-time window is meaningless), and the *detector setup* becomes the
        one whose windows are the detected laser gates. Publishing the setup to
        the shared ``detector_setups.*`` store is what makes the burst search,
        BVA and Accurate FRET all see the same definition.
        """
        converted = [Path(p) for p in converted if Path(p).exists()]
        if converted:
            self.workflow_context.raw_files = converted
            # BOTH file lists, not just the context. The context is re-derived
            # from these two panels on every step change (`_sync_data_context`
            # reads the data panel, `_sync_selection_context` the burst search's
            # own list), so leaving either holding the originals silently puts
            # them back the moment the user pressed Next -- and the burst search
            # would then run on the un-folded stream, where every micro-time
            # window is meaningless and no error is raised.
            self._replace_files(self._workflow_panels.get("data"), converted)
            self._replace_files(self._workflow_panels.get("selection"), converted)
        if setup:
            name = str(setup.get("setup_name") or "")
            self._publish_setup(name, setup)
            self.workflow_context.channel_settings = setup
            self.workflow_context.setup_name = name
        self._apply_context_to_downstream()

    def _publish_setup(self, name: str, setup: dict) -> None:
        """Save a setup where every reader of one will find it.

        Two stores, and they are not the same one. The RPC store
        (``detector_setups.*``, what the workflow context and the headless
        server read) writes the settings JSON; the *pickers* — every
        ``SetupSelector`` in the application, including the burst search's own —
        read through the wizard's loader, which reads MMFDB and, once MMFDB is
        in use, never falls back to that JSON. A setup written to one is
        invisible in the other, which is how this step could publish a setup the
        picker beside it did not list. Writing through both is the honest
        workaround until the two stores are one (recorded in
        ``okf/references/known-issues.md``).
        """
        try:
            self._setup_client.save_setup(name, setup)
            self._setup_client.set_current(setup)
        except Exception as exc:
            logger.warning(f"ALEX Suite: could not publish the setup — {exc}")
        try:
            from chisurf.gui.widgets.wizard.tttr_channeldefinition import (
                save_detector_setups,
            )

            save_detector_setups({"setups": {name: setup}, "last_used": name})
        except Exception as exc:
            logger.warning(
                f"ALEX Suite: the setup was published but not saved where the "
                f"pickers read — {exc}"
            )

    @staticmethod
    def _replace_files(panel, files) -> None:
        """Point one panel's file list at *files*, dropping what it held."""
        if panel is None:
            return
        for clear_name in ("clear", "_clear_file_list"):
            clear = getattr(panel, clear_name, None)
            if callable(clear):
                try:
                    clear()
                except Exception:
                    pass
                break
        for add_name in ("add_paths", "_add_paths"):
            add = getattr(panel, add_name, None)
            if callable(add):
                try:
                    add([str(path) for path in files]
                        if add_name == "add_paths" else list(files))
                except Exception as exc:
                    logger.warning(f"ALEX Suite: could not set the files — {exc}")
                return

    def _apply_context_to_titration(self, widget: QtWidgets.QWidget) -> None:
        """Seed the titration series and its correction factors."""
        seed = getattr(widget, "set_burst_files", None)
        sources = self.burst_sources()
        if callable(seed) and sources:
            seed(sources)
        calibration = self._calibration()
        corrections = getattr(widget, "set_corrections", None)
        if calibration and callable(corrections):
            corrections(
                gamma=calibration.get("gamma"), beta=calibration.get("beta"))

    def _apply_context_to_legacy_export(self, widget: QtWidgets.QWidget) -> None:
        """Offer the workflow's burst files to the CSV export."""
        setter = getattr(widget, "set_burst_files", None)
        sources = self.burst_sources()
        if callable(setter) and sources:
            setter(sources)

    # ── the reused tools that Burst Analysis does not thread ────────────

    def _apply_context_to_es(self, widget: QtWidgets.QWidget) -> None:
        """Open this workflow's burst files in ndX — once per set of them.

        The context is re-applied on every step change, and ndX is an explorer:
        re-opening the same files would throw away the selections, gates and
        derived columns the user built on them. So the *file set* is the key —
        a new burst search loads, returning to the step does not.

        Not keyed on "does ndX hold data": a fresh ``NDXplorer`` reports a
        non-empty ``data_source`` (it starts with a placeholder), so that test
        reads "already loaded" for a window that has never seen a file, and the
        step silently stayed on the splash screen.
        """
        ndx = getattr(widget, "_embedded_mainwindow", widget)
        files = [str(path) for path in self.burst_sources()]
        if not files or files == self._es_loaded:
            return
        open_files = getattr(ndx, "open_files", None)
        if not callable(open_files):
            return
        try:
            open_files(file_handles=files)
        except Exception as exc:
            logger.warning(f"ALEX Suite: could not open the bursts in ndX — {exc}")
            return
        self._es_loaded = files

    def _apply_context_to_trace(self, widget: QtWidgets.QWidget) -> None:
        """Point the trace viewer at the folder the measurements are in."""
        browser = getattr(widget, "_embedded_mainwindow", widget)
        files = self.workflow_context.raw_files
        setter = getattr(browser, "set_folder", None)
        if files and callable(setter):
            try:
                setter(str(Path(files[0]).parent))
            except Exception as exc:
                logger.warning(f"ALEX Suite: could not set the trace folder — {exc}")

    # ── helpers ─────────────────────────────────────────────────────────

    def _calibration(self) -> dict:
        """Return the α/β/γ/δ stored on the current detector setup, if any."""
        name = self.workflow_context.setup_name
        if not name:
            return {}
        try:
            from chisurf.core.data_io.detector_setups import get_setup_calibration

            return get_setup_calibration(name) or {}
        except Exception:
            return {}


__all__ = ["AlexSuiteTool", "ALEX_PANELS"]
