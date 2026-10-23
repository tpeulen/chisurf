"""The FCS correlator workflow, Qt-free: what each step hands the next.

Channel definitions → files → (photon/burst filter) → correlator → (merger). The native workflow (:mod:`chisurf.plugins.fcs.fcs_correlator.gui.app`)
keep one :class:`FcsWorkflow` and call it when a step is opened; neither re-implements the hand-over.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .regions import TimeRegions

#: Files the Files step accepts (the Qt list's extensions).
#: Photon-stream inputs: the container first, then the vendor stream files the
#: container is packed from. Legacy .bst/.bur layouts are reached through the
#: legacy import/export plugins, never loaded here.
FILE_EXTENSIONS = (".pto", ".spc", ".ht3", ".ptu", ".hdf", ".h5")
#: The photon files a folder in the Files step stands for (burst lists are added one by one).
FOLDER_EXTENSIONS = (".spc", ".ht3", ".ptu", ".hdf", ".h5", ".pto")


@dataclass
class FcsWorkflowContext:
    detector_settings: dict[str, Any] = field(default_factory=dict)
    channel_defs: dict[str, Any] = field(default_factory=dict)
    file_paths: list[pathlib.Path] = field(default_factory=list)
    expanded_files: list[str] = field(default_factory=list)
    use_photon_filter: bool = False
    use_fcs_merger: bool = True
    #: Several files: correlate each on its own (the merger then averages their curves) instead of stacking their
    #: photons into one stream first.
    per_file: bool = False
    #: Optional micro-time coarsening factor shared with downstream tools (Filter
    #: Calculator) so lifetime filters use the same micro-time axis as the
    #: correlation. The micro-time *resolution* itself comes from the loaded data.
    microtime_binning: int = 1


def setup_context(setup_name: str, setups: dict) -> tuple[dict, dict]:
    """``(detector_settings, channel_defs)`` of a detector setup, as the channel-definition step hands them on.

    No detector-setup step: the container type is auto-detected per file (``tttr_reading`` empty) and the logical
    channels are built from the setup's windows and detectors.
    """
    from chisurf.core.fluorescence.fcs.channel_setups import build_channels_from_setup

    setup = setups.get(setup_name, {}) if isinstance(setups, dict) else {}
    detectors = setup.get("detectors", {}) if isinstance(setup, dict) else {}
    windows = setup.get("windows", {}) if isinstance(setup, dict) else {}
    channels = build_channels_from_setup(windows or {}, detectors or {})
    return {
        "setup_name": setup_name or "",
        "detectors": detectors or {},
        "tttr_reading": {},
    }, channels


def expand_paths(paths) -> list[str]:
    """*paths* with each folder replaced by the TTTR files in it (sorted), all resolved.

    A folder's photon files are recognised by extension; tttrlib's container *names* (``SPC-130``, ``PHOTON-HDF5``)
    are not extensions, and matching against them silently dropped every ``.spc`` and ``.h5`` file in a folder.
    """
    expanded: list[str] = []
    for p_str in paths:
        p = pathlib.Path(p_str).resolve()
        if p.is_dir():
            for child in sorted(p.iterdir()):
                if child.is_file() and child.suffix.lower() in FOLDER_EXTENSIONS:
                    expanded.append(str(child.resolve()))
        else:
            expanded.append(str(p))
    return expanded


def filter_step_allowed(files) -> bool:
    """The photon filter step needs photons: it is always allowed -- inputs are
    photon streams (containers or vendor files), never burst-ID tables."""
    return True


class FcsWorkflow:
    """The workflow context and the hand-over between the steps."""

    def __init__(self) -> None:
        self.context = FcsWorkflowContext()
        #: The time regions drawn per file in Files & Steps; only photons inside them are filtered and correlated.
        self.regions = TimeRegions()

    # ── inputs ────────────────────────────────────────────────────────────

    def set_setup(self, setup_name: str, setups: dict) -> None:
        self.context.detector_settings, self.context.channel_defs = setup_context(
            setup_name, setups
        )

    def set_files(self, checked: list, use_filter: bool, use_merger: bool, per_file: bool = False) -> None:
        self.context.file_paths = [pathlib.Path(p) for p in checked]
        self.context.use_photon_filter = bool(use_filter) and filter_step_allowed(checked)
        self.context.use_fcs_merger = bool(use_merger)
        self.context.per_file = bool(per_file)

    # ── files and photons ─────────────────────────────────────────────────

    def expanded_files(self) -> list[str]:
        """The checked files, a folder replaced by the TTTR files in it."""
        return expand_paths(self.context.file_paths)

    @property
    def file_type(self) -> str:
        """The container type of the detector step (``tttr_reading.file_type``), empty to auto-detect."""
        return str(
            self.context.detector_settings.get("tttr_reading", {}).get("file_type", "") or ""
        )

    def lut_open_kwargs(self) -> dict:
        """LUT/shift ``open_tttr`` kwargs for the currently selected setup."""
        from chisurf.core.data_io.detector_setups import setup_lut_open_kwargs

        try:
            return setup_lut_open_kwargs(self.context.detector_settings)
        except Exception:  # noqa: BLE001 - a setup without LUTs reads plainly
            return {}

    @staticmethod
    def read_tttr(path: str, filetype: str, lut_kwargs: dict | None = None):
        """Read a TTTR file, preferring ``filetype`` but auto-detecting on failure.

        ``tttrlib.TTTR(path, "")`` (or a wrong container type) can return an *empty* object without raising, so an
        empty result also triggers the filename-based auto-detection. With *lut_kwargs* (the setup's LUT/shift) the
        read is LUT-aware.
        """
        from chisurf.core.fio.staging import open_tttr

        lut_kwargs = lut_kwargs or {}
        tt = None
        if filetype:
            try:
                tt = open_tttr(path, filetype, **lut_kwargs)
            except Exception:  # noqa: BLE001 - fall back to detection
                tt = None
        if tt is None or len(tt) == 0:
            try:
                tt = open_tttr(path, None, **lut_kwargs)
            except Exception:  # noqa: BLE001
                return tt if (tt is not None and len(tt)) else None
        return tt

    def read_for_trace(self, path: str):
        """*path* read as the correlator reads it (setup container type and LUTs), for drawing its regions."""
        return self.read_tttr(pathlib.Path(path).as_posix(), self.file_type, self.lut_open_kwargs())

    @staticmethod
    def stack(pieces):
        """The photons of ``(path, tttr)`` *pieces* concatenated into a new stream; ``None`` without any.

        ``TTTR.append`` extends the stream it is called on, so the first piece is copied: appending to it in place
        made the first file's own stream hold every file (its per-file pieces lasted as long as all files together).
        """
        combined = None
        for _path, tt in pieces:
            if combined is None:
                combined = tt[0 : len(tt)]
            else:
                combined.append(tt)
        return combined

    def load_raw_combined(self, expanded: list[str]):
        """Read and concatenate the raw TTTR files (unfiltered path), each cut to its time regions."""
        return self.stack(self.raw_pieces(expanded))

    def raw_pieces(self, expanded: list[str]) -> list:
        """``(path, tttr)`` of each raw TTTR file, cut to its time regions; unreadable or empty files left out."""
        lut_kwargs = self.lut_open_kwargs()
        pieces = []
        for fn in expanded:
            if not pathlib.Path(fn).exists():
                continue
            tt = self.read_tttr(pathlib.Path(fn).as_posix(), self.file_type, lut_kwargs)
            if tt is None:
                continue
            if self.regions.get(fn):
                idx = np.where(self.regions.mask(fn, tt))[0]
                if idx.size == 0:
                    continue
                tt = tt[idx]
            pieces.append((fn, tt))
        return pieces

    # ── hand-over to the steps ────────────────────────────────────────────

    def load_files_into_filter(self, model) -> None:
        """The checked files into the filter model; unchanged files are not re-read (the user's tweaks stay)."""
        model.set_time_regions(self.regions)
        expanded = self.expanded_files()
        if not expanded or (model._files == expanded and model._tttr is not None):
            return
        lut_kwargs = self.lut_open_kwargs()
        objs: dict = {}
        for fn in expanded:
            p = pathlib.Path(fn)
            if not p.exists():
                continue
            tt = self.read_tttr(p.as_posix(), self.file_type, lut_kwargs)
            if tt is not None:
                objs[str(p.resolve())] = tt
        model.set_tttr_objects(objs, expanded)

    @classmethod
    def filtered_tttr(cls, filter_model):
        """The photons kept by the filter step, all files concatenated; ``None`` when it has no usable selection."""
        return cls.stack(cls.filtered_pieces(filter_model))

    @staticmethod
    def filtered_pieces(filter_model) -> list:
        """``(path, tttr)`` of the photons the filter step keeps in each file; files it keeps nothing of left out."""
        if filter_model is None or not filter_model._tttr_objects:
            return []
        pieces = []
        for path in filter_model._files:
            tt = filter_model._tttr_objects.get(str(pathlib.Path(path).resolve()))
            if tt is None:
                continue
            try:
                mask = np.asarray(filter_model.compute_selection(tt, path), dtype=bool)
            except Exception:  # noqa: BLE001 - a file the filter cannot judge is skipped
                continue
            if mask.size != len(tt):
                continue
            idx = np.where(mask)[0]
            if idx.size == 0:
                continue
            pieces.append((path, tt[idx]))
        return pieces

    def apply_to_correlator(self, model, filter_model=None) -> None:
        """The setup's channels and presets, the analysis folder and the photons (filtered or raw) into the correlator."""
        if self.context.channel_defs:
            model._channel_defs = self.context.channel_defs
        settings = self.context.detector_settings
        dets = {
            k: v
            for k, v in (settings.get("detectors", {}) or {}).items()
            if isinstance(k, str) and k.strip()
        }
        model.load_fcs_presets(settings.get("setup_name", ""), dets)
        expanded = self.expanded_files()
        if expanded:
            model._analysis_folder = pathlib.Path(expanded[0]).resolve().parent
        from .provenance import photon_record

        if self.context.use_photon_filter:
            # Correlate the photons the filter kept; fall back to the raw files when the filter step has no
            # selection yet, so the correlator is never left empty.
            pieces = self.filtered_pieces(filter_model)
            used_filter = filter_model if pieces else None
            files = list(filter_model._files) if pieces else expanded
            pieces = pieces or self.raw_pieces(expanded)
        elif expanded:
            pieces, used_filter, files = self.raw_pieces(expanded), None, expanded
        else:
            return
        model._tttr = self.stack(pieces)
        #: With per_file the correlator correlates each file on its own; ``None`` correlates the stacked stream.
        model._tttr_files = pieces if self.context.per_file and len(pieces) > 1 else None
        model._photon_record = photon_record(self, files, used_filter)

    @staticmethod
    def merger_input(correlator_model) -> tuple[list, pathlib.Path | None]:
        """What the merger step gets: the correlator's curves and the folder they were (or would be) written to."""
        correlations = list(getattr(correlator_model, "_correlations", None) or [])
        folder = getattr(correlator_model, "_analysis_folder", None)
        sub = getattr(correlator_model, "_output_subdir", None)
        if folder is not None and sub:
            folder = pathlib.Path(folder) / sub
        return correlations, folder

    @staticmethod
    def merger_labels(correlations: list) -> list[str] | None:
        """Names of the pieces in the merger: ``<file>-<n>`` when each file was correlated on its own."""
        if not any("file" in c for c in correlations):
            return None
        seen: dict[str, int] = {}
        labels = []
        for c in correlations:
            stem = pathlib.Path(c.get("file", "stacked")).stem
            labels.append(f"{stem}-{seen.get(stem, 0):02}")
            seen[stem] = seen.get(stem, 0) + 1
        return labels

    @staticmethod
    def merger_provenance(correlator_model) -> dict | None:
        """The settings record of the correlator's curves (photons, regions, filter, correlator settings)."""
        return getattr(correlator_model, "_provenance", None)
