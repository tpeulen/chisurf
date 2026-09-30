"""Qt-free model of the native Region MLE tool.

:class:`RegionMleModel` is the plugin's own :class:`~.view_model.RegionMleViewModel`
(the file lists, the fit settings, the analysis region and the results, unchanged)
plus what a drawn window needs and a Qt host gets from its widgets: whether a
worker is running, which file dialog is wanted, what greys a button, and the
settings that outlive the window.

Buttons of the spec name view-model methods that only *announce* the work
(``request_run`` notifies ``start_run``); :mod:`.app` listens and runs the
blocking method on a :class:`chisurf.emtk.jobs.SnapshotJob`, exactly as the Qt
tool does on its thread pool.
"""

from __future__ import annotations

import logging
from typing import Any

from chisurf.core.roi import RegionCollection

from .view_model import RegionMleViewModel

logger = logging.getLogger(__name__)

#: Photon files the file lists accept (Qt-style dialog filter).
PHOTON_FILE_FILTER = "Photon data (*.pto *.ptu *.ht3 *.spc *.pt3);;All files (*)"

#: Scalar settings kept between sessions (attributes of the view-model).
PERSISTED_SCALARS = (
    "detector_chs_text",
    "mtr_start",
    "mtr_stop",
    "micro_time_binning",
    "min_photons",
    "region_set",
    "tau",
    "gamma",
    "r0",
    "rho",
    "fix_tau",
    "fix_gamma",
    "fix_r0",
    "fix_rho",
    "l1",
    "l2",
    "p2s_twoIstar",
    "soft_bifl_scatter",
)

#: Button actions and what each needs before it is usable.
ACTIONS = (
    "request_demo",
    "request_preview",
    "request_run",
    "request_export",
    "request_open_results",
)


class RegionMleModel(RegionMleViewModel):
    """View-model plus the state of a drawn window."""

    def __init__(self) -> None:
        super().__init__()
        #: True while a worker runs (set from the job by the app every frame).
        self.busy = False
        #: Progress line of the running worker.
        self.progress_text = ""
        #: Error of a worker that raised (the methods themselves report in ``status_text``).
        self.error_text = ""
        #: ``"add_files"`` / ``"add_irf"`` / ``"export"`` / ``"open_results"`` /
        #: ``"save_regions"`` / ``"load_regions"`` while the app should open a dialog.
        self.dialog = ""
        #: Last folder a dialog was used in.
        self.folder = ""

    # ── what the window shows ────────────────────────────────────────
    def info_html(self) -> str:
        """Summary text; a running worker's progress or a failed one's error comes first."""
        if self.error_text:
            return f"<i>{self.error_text}</i>"
        if self.busy and self.progress_text:
            return f"<i>{self.progress_text}</i>"
        return super().info_html()

    def enabled(self, name: str) -> bool:
        """Whether the field or action *name* is usable now.

        Everything is greyed while a worker runs (it works on a snapshot, so an
        edit would be lost); the actions also need their inputs.
        """
        if self.busy:
            return False
        if name == "request_preview":
            return bool(self.files)
        if name == "request_run":
            return self.can_run()[0]
        if name == "request_export":
            return self.has_results()
        return True

    # ── actions that only ask the window for a dialog ────────────────
    def request_open_results(self) -> None:
        """Button action: ask for a saved ``molecule_data.tsv`` to browse."""
        self.dialog = "open_results"

    def request_add_files(self) -> None:
        """Ask for imaging files to add to the analysis."""
        self.dialog = "add_files"

    def request_add_irf(self) -> None:
        """Ask for the IRF file."""
        self.dialog = "add_irf"

    def add_paths(self, target: str, paths: list) -> int:
        """Add *paths* to the ``sel_files`` or ``sel_irf_files`` list.

        Parameters
        ----------
        target : str
            ``"sel_files"`` (any number) or ``"sel_irf_files"`` (the first is used,
            so a new one replaces the old).
        paths : list
            Files to add; duplicates are skipped.

        Returns
        -------
        int
            How many were added.
        """
        current = list(getattr(self, target))
        added = [p for p in dict.fromkeys(str(p) for p in paths) if p not in current]
        if target == "sel_irf_files":
            new = added[:1] or current
            added = added[:1]
        else:
            new = current + added
        setattr(self, target, new)
        if added:
            self.status_text = ""
            self.notify("settings")
        return len(added)

    # ── persistence ──────────────────────────────────────────────────
    def export_settings(self) -> dict[str, Any]:
        """Everything worth remembering, as plain JSON-able data."""
        state: dict[str, Any] = {name: getattr(self, name) for name in PERSISTED_SCALARS}
        state.update(
            files=list(self.files),
            irf_files=list(self.irf_files),
            regions=self.regions.to_dict(),
            folder=self.folder,
        )
        return state

    def restore_settings(self, state: dict) -> None:
        """Adopt a dict from :meth:`export_settings`; unusable entries are ignored."""
        for name in PERSISTED_SCALARS:
            if name in state:
                try:
                    setattr(self, name, state[name])
                except (TypeError, ValueError):
                    logger.debug("ignored saved setting %s=%r", name, state[name])
        if "files" in state:
            self.sel_files = list(state["files"])
        if "irf_files" in state:
            self.sel_irf_files = list(state["irf_files"])
        if isinstance(state.get("regions"), dict):
            try:
                self.regions = RegionCollection.from_dict(state["regions"])
            except Exception:  # noqa: BLE001 - a bad saved region must not stop the tool
                logger.debug("ignored saved regions", exc_info=True)
            else:
                self.apply_regions()
        self.folder = str(state.get("folder", self.folder) or "")
