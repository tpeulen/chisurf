"""State and actions of the native Burst Selection app, without a toolkit.

The Qt tool keeps this state in widgets: the files in a list widget, the filter settings in the shared photon-filter
wizard page, the search parameters in a form generated from tttrlib's registry, the display settings in spin boxes.
:class:`BurstSelectionModel` holds the same state as plain attributes, builds the same
:class:`~..api.models.AnalysisSettings` from it, and runs the same backend call (``BurstSelectionClient.analyze_files``),
so a search from the native app writes the same burst tables as one from the Qt tool. What the diagnostic plots draw
is computed here too, as arrays, and the emtk app only draws them.

Values the Qt tool reported wrongly are written correctly here (see ``okf/references/known-issues.md``): the
``burst_detection.time_window`` is the macro-time cut in seconds (Qt wrote ``min_photons / 1000``), the CUSUM /
Kalman / BOCPD fields carry their defaults (Qt filled them from unrelated widgets), and the parameters recorded with a
run are this run's (Qt recorded a stale ``dT_min`` and ``use_gap_fill``). The registry search reads none of them, so
the bursts are identical.

Nothing here imports Qt, emtk or ``chisurf.gui``.
"""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np

from chisurf.core.datastore import (
    column_names,
    concat_stores,
    new_store,
    numeric_column,
    row_count,
    rows_from_table,
    store_from_rows,
    write_csv_table,
)

from ..api.models import (
    AnalysisSettings,
    BurstDetectionSettings,
    BurstFilterMode,
    CountRateFilterSettings,
    DeltaMacroTimeFilterSettings,
    PhotonFilterSettings,
    TttrlibSearchSettings,
)
from . import diagnostics as diag_mod
from .adapter import PROXIMITY_RATIO_COLUMN, UI_COLUMNS, burst_rows_for_display

#: Bump in the same change that alters what this tool computes (shared with the Qt tool's cache tag).
ALGORITHM_VERSION = 1

#: Advanced Gaussian-mixture settings (the Qt ``GMMSettingsDialog`` defaults).
DEFAULT_GMM_SETTINGS = {
    "covariance_type": "full",
    "random_state": 42,
    "max_iter": 300,
    "n_init": 10,
    "tol": 1e-3,
    "max_components": 10,
    "reg_covar": 1e-6,
}

#: The Qt "Settings > Metadata" dialog offers these keys first; the PDBx keys follow.
COMMON_METADATA_KEYS = [
    "pH",
    "temperature",
    "ionic_strength",
    "buffer_composition",
    "solvent_phase",
    "labeling_efficiency",
    "donor_only_fraction",
    "acceptor_only_fraction",
    "dye_ratio",
    "quencher_concentration",
    "time_resolution",
    "excitation_wavelength",
    "emission_wavelength",
    "power",
    "temperature_control",
    "data_notes",
]

#: "Do not restrict to one detector / micro-time window" (the wizard's spelling).
ALL = "All"

#: Default burst search (the first entry of tttrlib's registry, as the Qt combo starts on it).
DEFAULT_ALGORITHM = "sliding_window"

#: Plot point budget per curve (the Qt tool's thinning budget).
MAX_PLOT_POINTS = 20000

#: Scatter features offered by the 2D plot, beside every numeric column of the burst table.
SCATTER_DEFAULTS = (PROXIMITY_RATIO_COLUMN, "Duration (ms)")

#: Settings file kind written by Save settings.
SETTINGS_KIND = "burst_selection_native"

_FILTER_ATTRS = (
    "detector",
    "window",
    "dt_min",
    "dt_max",
    "dt_min_active",
    "dt_max_active",
    "use_gap_fill",
    "merge_gap",
    "filter_active",
    "invert",
    "min_photons",
    "photon_window",
)
_DISPLAY_ATTRS = (
    "show_all_photons",
    "show_selected_photons",
    "window_start_s",
    "window_length_s",
    "trace_bin_ms",
    "decay_bins",
    "burst_bins",
    "hist_feature",
    "hist_bins",
    "hist_min",
    "hist_max",
    "hist_log",
    "gmm_components",
    "gmm_auto_components",
    "scatter_x",
    "scatter_y",
)


def search_algorithms() -> dict[str, dict[str, Any]]:
    """tttrlib's burst searches (``{name: registry entry}``); empty when tttrlib publishes none."""
    try:
        from chisurf.core.fluorescence.burst import tttrlib_search

        return tttrlib_search.algorithms()
    except Exception:  # noqa: BLE001 - an old tttrlib has no registry; the app says so
        return {}


def search_defaults(algorithm: str) -> dict[str, Any]:
    """Registry defaults of *algorithm* (``{}`` if unknown)."""
    try:
        from chisurf.core.fluorescence.burst import tttrlib_search

        return dict(tttrlib_search.defaults(algorithm))
    except Exception:  # noqa: BLE001
        return {}


def _groups_text(value: Any) -> str:
    """``[[0, 1], [8, 9]]`` as ``0,1; 8,9``."""
    groups = value or []
    return "; ".join(",".join(str(int(c)) for c in group) for group in groups)


def _groups_value(text: str) -> list[list[int]]:
    """``0,1; 8,9`` as ``[[0, 1], [8, 9]]`` (empty groups dropped)."""
    groups = []
    for part in str(text or "").replace("|", ";").split(";"):
        channels = [int(c) for c in part.replace(" ", ",").split(",") if c.strip()]
        if channels:
            groups.append(channels)
    return groups


def load_setups() -> dict[str, dict[str, Any]]:
    """The detector setups (``{name: setup}``) of the store the shared detector editor reads (MMFDB, else JSON)."""
    from chisurf.core.setup_channel_definition import ChannelDefinition

    definition = ChannelDefinition()
    definition.refresh_setups()
    return definition.setups


def save_setup(name: str, data: dict[str, Any]) -> None:
    """Write one setup to that store (the other setups are left alone)."""
    from chisurf.core.fio import setup_store
    from chisurf.core.setup_channel_definition import CONFIG, _save_row

    payload = {k: v for k, v in data.items() if k not in ("_owner",)}
    if not setup_store.save_setups({"setups": {name: payload}}, CONFIG, save_row_fn=_save_row):
        raise OSError(f"The setup '{name}' could not be saved.")


class SearchParameters:
    """The selected search's parameters as attributes, so a spec form can bind them (``attr`` = parameter name).

    *path* names a nested parameter dict (the coincident search's inner ``parameters``). Arrays of channel groups are
    shown as text (``0,1; 8,9``).
    """

    def __init__(self, model: BurstSelectionModel, path: tuple[str, ...] = ()) -> None:
        object.__setattr__(self, "_model", model)
        object.__setattr__(self, "_path", path)

    def _values(self) -> dict[str, Any]:
        values = self._model.parameters
        for key in self._path:
            values = values.setdefault(key, {})
        return values

    def _schema(self) -> dict[str, Any]:
        if self._path:
            return self._model.nested_schema()
        return self._model.search_schema()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        prop = (self._schema().get("properties") or {}).get(name, {})
        value = self._values().get(name, prop.get("default"))
        if prop.get("type") == "array":
            return _groups_text(value)
        return value

    def __setattr__(self, name: str, value: Any) -> None:
        prop = (self._schema().get("properties") or {}).get(name, {})
        kind = prop.get("type")
        if kind == "array":
            value = _groups_value(value)
        elif kind == "integer":
            value = int(value)
        elif kind == "number":
            value = float(value)
        elif kind == "boolean":
            value = bool(value)
        values = self._values()
        if values.get(name) == value:
            return
        values[name] = value
        if (
            not self._path
            and name == "algorithm"
            and "parameters" in (self._schema().get("properties") or {})
        ):
            # The coincident search's inner search changed: its parameters start from that search's defaults.
            values["parameters"] = search_defaults(str(value))
        self._model.settings_changed()


def schema_sections(schema: dict[str, Any], *, skip: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Spec sections (emtk ``view_form``) for the parameters of a registry JSON Schema."""
    sections = []
    for name, prop in (schema.get("properties") or {}).items():
        if name in skip or prop.get("type") == "object":
            continue
        unit = prop.get("unit")
        description = str(prop.get("description") or prop.get("title") or name)
        if unit:
            description += f" Unit: {unit}."
        section: dict[str, Any] = {
            "attr": name,
            "label": str(prop.get("title") or name),
            "description": description,
        }
        kind = prop.get("type")
        if prop.get("enum") is not None:
            section.update(type="choice", options=list(prop["enum"]))
        elif kind == "boolean":
            section.update(type="toggle")
        elif kind == "integer":
            section.update(type="value", kind="int")
        elif kind == "number":
            section.update(type="value", kind="float")
            if prop.get("scale") == "log" or (
                prop.get("default") not in (None, 0) and abs(float(prop["default"])) < 1e-2
            ):
                section["style"] = "scientific"
                section["decimals"] = 3
            else:
                section["decimals"] = 4
        elif kind == "array":
            section.update(type="value", kind="str", placeholder="0,1; 8,9")
        else:
            section.update(type="value", kind="str")
        for bound in ("minimum", "maximum"):
            if prop.get(bound) is not None and kind in ("integer", "number"):
                section[bound] = prop[bound]
        sections.append(section)
    return sections


class BurstSelectionModel:
    """Files, detector setup, filter and search settings, results and plot data of Burst Selection."""

    def __init__(self, client: Any = None) -> None:
        self._observers: list[Callable[[str], None]] = []
        self._client = client
        self._cancel = threading.Event()
        # -- files ----------------------------------------------------------------------------------------- #
        self.files: list[Path] = []
        self.active_index = 0
        # -- detector setup -------------------------------------------------------------------------------- #
        self.setup_name = ""
        self.detectors: dict[str, dict[str, Any]] = {}
        self.windows: dict[str, Any] = {}
        self.file_type: str | None = None
        # -- filter (the wizard's FilterSettings defaults) -------------------------------------------------- #
        self.detector = ALL
        self.window = ALL
        self.dt_min = 0.001
        self.dt_max = 0.150
        self.dt_min_active = False
        self.dt_max_active = True
        self.use_gap_fill = True
        self.merge_gap = 3
        self.filter_active = True
        self.invert = False
        self.min_photons = 60
        self.photon_window = 5
        # -- search ---------------------------------------------------------------------------------------- #
        self.algorithms = search_algorithms()
        self.algorithm = (
            DEFAULT_ALGORITHM
            if DEFAULT_ALGORITHM in self.algorithms
            else next(iter(self.algorithms), "")
        )
        self.parameters: dict[str, Any] = search_defaults(self.algorithm)
        self.search = SearchParameters(self)
        self.inner_search = SearchParameters(self, ("parameters",))
        # -- output ---------------------------------------------------------------------------------------- #
        self.zip_output = False
        self.remove_folder = False
        self.mmfdb_output = False
        self.sample_id = ""
        self.metadata: dict[str, str] = {}
        # -- display (the Qt tool's defaults) -------------------------------------------------------------- #
        self.show_all_photons = True
        self.show_selected_photons = True
        self.window_start_s = 0.0
        self.window_length_s = 10.0
        self.trace_bin_ms = diag_mod.DEFAULT_TRACE_BIN_WIDTH_MS
        self.decay_bins = diag_mod.DEFAULT_DECAY_BINS
        self.burst_bins = diag_mod.DEFAULT_BURST_BINS
        self.hist_feature = PROXIMITY_RATIO_COLUMN
        self.hist_bins = diag_mod.DEFAULT_HISTOGRAM_BINS
        self.hist_min = 0.0
        self.hist_max = 1.0
        self.hist_log = False
        self.gmm_components = 0
        self.gmm_auto_components = False
        self.gmm_settings = dict(DEFAULT_GMM_SETTINGS)
        self.scatter_x, self.scatter_y = SCATTER_DEFAULTS
        # -- results --------------------------------------------------------------------------------------- #
        self.status_text = "Add TTTR files and choose a detector setup, then press Run."
        self.result: dict[str, Any] | None = None
        self.frames_by_file: dict[str, Any] = {}
        self.display_frame = None
        self.preview = False
        self.diagnostic: dict[str, Any] | None = None
        self.gmm_result: dict[str, Any] | None = None
        self._open_tttr: dict[str, Any] = {}
        self._fingerprint: str | None = None
        self._result_fingerprint: str | None = None
        self.unchanged = False
        self.has_processed = False

    # -- observers ------------------------------------------------------------------------------------------- #
    def notify(self, event: str = "updated") -> None:
        for observer in list(self._observers):
            observer(event)

    def settings_changed(self) -> None:
        """A filter or search setting changed: the displayed diagnostics are stale."""
        self.unchanged = False
        self.notify("settings")

    # -- backend --------------------------------------------------------------------------------------------- #
    @property
    def client(self):
        if self._client is None:
            from .client import BurstSelectionClient

            self._client = BurstSelectionClient(
                mmfdb_db_provider=self._mmfdb_db, mmfdb_session_provider=self._mmfdb_session
            )
        return self._client

    # -- files ----------------------------------------------------------------------------------------------- #
    def add_paths(self, paths) -> int:
        """Add TTTR files and the TTTR files of folders (sorted, as the Qt tool); return how many were added."""
        from chisurf.core.fio.staging import TTTR_EXTENSIONS

        added = 0
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                children = sorted(
                    child.resolve()
                    for child in path.iterdir()
                    if child.is_file() and child.suffix.lower() in TTTR_EXTENSIONS
                )
            elif path.is_file():
                children = [path.resolve()]
            else:
                children = []
            for child in children:
                if child not in self.files:
                    self.files.append(child)
                    added += 1
        if added:
            self.status_text = f"{len(self.files)} file(s) loaded. Press Run to search the bursts."
            self.notify("files")
        return added

    def remove_index(self, index: int) -> None:
        if 0 <= index < len(self.files):
            removed = self.files.pop(index)
            self.frames_by_file.pop(str(removed), None)
            self._open_tttr.pop(str(removed), None)
            self.active_index = min(self.active_index, max(0, len(self.files) - 1))
            self.diagnostic = None
            self.notify("files")

    def remove_file_row(self, row: dict) -> None:
        """``data_table`` delete hook."""
        path = Path(str(row.get("path", "")))
        if path in self.files:
            self.remove_index(self.files.index(path))

    def clear(self) -> None:
        """Remove every file and every result (the settings stay)."""
        self.files.clear()
        self.active_index = 0
        self.result = None
        self.frames_by_file.clear()
        self.display_frame = None
        self.diagnostic = None
        self.gmm_result = None
        self._open_tttr.clear()
        self._result_fingerprint = None
        self.has_processed = False
        self.unchanged = False
        self.status_text = "Cleared. Add TTTR files to begin."
        self.notify("files")

    def select_file(self, row: dict | int | None) -> None:
        """``data_table`` selection hook: the active file is the one the plots and the table show."""
        if isinstance(row, dict):
            path = Path(str(row.get("path", "")))
            index = self.files.index(path) if path in self.files else self.active_index
        elif row is None:
            return
        else:
            index = int(row)
        if 0 <= index < len(self.files) and index != self.active_index:
            self.active_index = index
            self.diagnostic = None
            self._refresh_display_frame()
            self.notify("files")

    @property
    def active_file(self) -> Path | None:
        return self.files[self.active_index] if 0 <= self.active_index < len(self.files) else None

    def file_rows(self) -> list[dict[str, Any]]:
        rows = []
        for index, path in enumerate(self.files):
            frame = self.frames_by_file.get(str(path))
            rows.append(
                {
                    "index": index,
                    "file": path.name,
                    "folder": str(path.parent),
                    "bursts": str(_burst_count(frame)) if frame is not None else "",
                    "path": str(path),
                }
            )
        return rows

    # -- detector setup -------------------------------------------------------------------------------------- #
    def set_setup(self, settings: dict) -> None:
        """Take the detector definition of the shared editor (every change of it)."""
        self.detectors = copy.deepcopy(settings.get("detectors") or {})
        self.windows = copy.deepcopy(settings.get("windows") or {})
        reading = settings.get("tttr_reading") or {}
        self.file_type = diag_mod.normalize_filetype(reading.get("file_type"))
        name = str(settings.get("setup_name") or settings.get("name") or "")
        if name:
            self.setup_name = name
        if self.detector not in (ALL, *self.detectors):
            self.detector = ALL
        if self.window not in (ALL, *self.windows):
            self.window = ALL
        defaults = settings.get("burst_selection")
        if isinstance(defaults, dict) and defaults:
            self.apply_setup_defaults(defaults)
        self.diagnostic = None
        self.settings_changed()

    def select_setup(self, name: str) -> bool:
        """Read the named setup from the setups store the shared detector editor uses (``True`` if it exists)."""
        setup = load_setups().get(name)
        if not setup:
            return False
        self.setup_name = name
        self.set_setup({**setup, "setup_name": name})
        return True

    def setup_text(self) -> str:
        return diag_mod.setup_summary(self.setup_name or None, self.file_type)

    def detector_options(self) -> list[str]:
        return [ALL, *self.detectors]

    def window_options(self) -> list[str]:
        return [ALL, *self.windows]

    @property
    def channels(self) -> list[int]:
        """Routing channels the filter keeps (empty = all), as the wizard's channel line."""
        if self.detector == ALL or self.detector not in self.detectors:
            return []
        return [int(c) for c in (self.detectors[self.detector] or {}).get("chs", [])]

    @property
    def microtime_ranges(self) -> list[tuple[int, int]]:
        """Micro-time ranges the filter keeps (empty = all), as the wizard's window line."""
        if self.window == ALL or self.window not in self.windows:
            return []
        win = self.windows[self.window]
        if isinstance(win, int):
            return [(win, win)]
        if (
            isinstance(win, (list, tuple))
            and len(win) == 2
            and all(isinstance(x, (int, np.integer)) for x in win)
        ):
            lo, hi = int(win[0]), int(win[1])
            return [(min(lo, hi), max(lo, hi))]
        ranges = []
        for item in win or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                lo, hi = int(item[0]), int(item[1])
                ranges.append((min(lo, hi), max(lo, hi)))
            elif isinstance(item, (int, np.integer)):
                ranges.append((int(item), int(item)))
        return ranges

    def channel_text(self) -> str:
        chs = self.channels
        return "Routing channels: " + (
            ", ".join(str(c) for c in chs) if chs else "all (unfiltered)"
        )

    def window_text(self) -> str:
        ranges = self.microtime_ranges
        return "Micro-time: " + (
            "; ".join(f"{a}-{b}" for a, b in ranges) if ranges else "full decay (unfiltered)"
        )

    def apply_setup_defaults(self, params: dict[str, Any]) -> None:
        """A setup's saved ``burst_selection`` block (the keys the Qt page reads and writes)."""
        if "dT_min" in params:
            self.dt_min = float(params["dT_min"])
        if "dT_max" in params:
            self.dt_max = float(params["dT_max"])
        if "use_dT_min" in params:
            self.dt_min_active = bool(params["use_dT_min"])
        if "use_dT_max" in params:
            self.dt_max_active = bool(params["use_dT_max"])
        if "photon_threshold" in params:
            self.min_photons = int(params["photon_threshold"])
        if "ph_window" in params:
            self.photon_window = int(params["ph_window"])
        if "invert_filter" in params:
            self.invert = bool(params["invert_filter"])
        if "filter_active" in params:
            self.filter_active = bool(params["filter_active"])
        if "use_gap_fill" in params:
            self.use_gap_fill = bool(params["use_gap_fill"])
        if "max_gap" in params:
            self.merge_gap = int(params["max_gap"])
        if "trace_bin_width" in params:
            self.trace_bin_ms = float(params["trace_bin_width"])
        if "number_of_burst_bins" in params:
            self.burst_bins = int(params["number_of_burst_bins"])
        if "decay_coarse" in params:
            self.decay_bins = int(params["decay_coarse"])
        algorithm = params.get("tttrlib_algorithm")
        if algorithm and algorithm in self.algorithms:
            self.algorithm = str(algorithm)
            self.parameters = {
                **search_defaults(self.algorithm),
                **dict(params.get("tttrlib_parameters") or {}),
            }

    def burst_selection_parameters(self) -> dict[str, Any]:
        """This run's parameters in the setup / ``Info`` file vocabulary (the Qt page's keys, with true values)."""
        params: dict[str, Any] = {
            "dT_min": float(self.dt_min),
            "dT_max": float(self.dt_max),
            "use_dT_min": bool(self.dt_min_active),
            "use_dT_max": bool(self.dt_max_active),
            "photon_threshold": int(self.min_photons),
            "invert_filter": bool(self.invert),
            "filter_mode": BurstFilterMode.TTTRLIB.value,
            "filter_active": bool(self.filter_active),
            "use_gap_fill": bool(self.use_gap_fill),
            "max_gap": int(self.merge_gap),
            "trace_bin_width": float(self.trace_bin_ms),
            "number_of_burst_bins": int(self.burst_bins),
            "channels": self.channels,
            "decay_coarse": int(self.decay_bins),
            "ph_window": int(self.photon_window),
            "tttrlib_algorithm": self.algorithm,
            "tttrlib_parameters": copy.deepcopy(self.parameters),
        }
        if self.microtime_ranges:
            params["microtime_ranges"] = [list(r) for r in self.microtime_ranges]
        return params

    def save_defaults_to_setup(self) -> str:
        """Store the current filter and search as the selected setup's defaults (the Qt page's save button)."""
        if not self.setup_name:
            raise ValueError(
                "No detector setup selected: choose or save one in the detector setup first."
            )
        setup = load_setups().get(self.setup_name)
        if setup is None:
            raise ValueError(f"The setup '{self.setup_name}' is not in the setups store.")
        setup = copy.deepcopy(setup)
        setup["burst_selection"] = self.burst_selection_parameters()
        save_setup(self.setup_name, setup)
        self.status_text = f"Burst-selection defaults saved to the setup '{self.setup_name}'."
        return self.setup_name

    # -- search ---------------------------------------------------------------------------------------------- #
    def algorithm_options(self) -> list[tuple[str, str]]:
        return [(name, str(spec.get("label", name))) for name, spec in self.algorithms.items()]

    def set_algorithm(self, name: str) -> None:
        """Select a search; its parameters start from the registry defaults (as the Qt form does)."""
        name = str(name)
        if name == self.algorithm or name not in self.algorithms:
            return
        self.algorithm = name
        self.parameters = search_defaults(name)
        if "channel_groups" in self.search_schema().get(
            "properties", {}
        ) and not self.parameters.get("channel_groups"):
            self.parameters["channel_groups"] = [
                list(map(int, d.get("chs", []))) for d in self.detectors.values()
            ]
        self.settings_changed()

    def search_schema(self) -> dict[str, Any]:
        return dict((self.algorithms.get(self.algorithm) or {}).get("params_schema") or {})

    def search_summary(self) -> str:
        return str((self.algorithms.get(self.algorithm) or {}).get("summary") or "")

    def nested_schema(self) -> dict[str, Any]:
        """Schema of the inner search of a composite search (``{}`` for a flat one)."""
        props = self.search_schema().get("properties") or {}
        nested = props.get("parameters") or {}
        selector = (nested.get("parameters_of") or {}).get("selector")
        if not selector:
            return {}
        inner = self.parameters.get(selector) or (props.get(selector) or {}).get("default")
        return dict((self.algorithms.get(str(inner)) or {}).get("params_schema") or {})

    def search_sections(self) -> list[dict[str, Any]]:
        return schema_sections(self.search_schema())

    def nested_sections(self) -> list[dict[str, Any]]:
        return schema_sections(self.nested_schema())

    # -- settings -------------------------------------------------------------------------------------------- #
    def output_formats(self) -> list[str]:
        return diag_mod.output_formats_for_inputs(self.files)

    def output_text(self) -> str:
        formats = self.output_formats()
        if not self.files:
            return "Results go to: the measurement's .pto"
        if "bur" in formats and "pto" in formats:
            return "Results go to: each .pto, and a folder per vendor file"
        if "bur" in formats:
            return "Results go to: a bi4_bur/ folder beside each file"
        return "Results go to: the measurement's own .pto"

    def enabled(self, name: str) -> bool:
        """Spec hook: the zip options apply to a companion folder only."""
        if name == "zip_output":
            return "bur" in self.output_formats()
        if name == "remove_folder":
            return bool(self.zip_output) and "bur" in self.output_formats()
        if name == "dt_min":
            return bool(self.dt_min_active)
        if name == "dt_max":
            return bool(self.dt_max_active)
        if name == "merge_gap":
            return bool(self.use_gap_fill)
        return True

    def analysis_settings(self) -> AnalysisSettings:
        """The :class:`AnalysisSettings` of a run (the fields the search reads equal the Qt tool's)."""
        filter_settings = PhotonFilterSettings(
            channels=self.channels,
            microtime_ranges=self.microtime_ranges,
            filter_active=bool(self.filter_active),
            used_filter=BurstFilterMode.TTTRLIB,
            count_rate_filter=CountRateFilterSettings(
                n_ph_max=int(self.min_photons), time_window=1e-3, invert=bool(self.invert)
            ),
            tttrlib_search=TttrlibSearchSettings(
                algorithm=self.algorithm, parameters=copy.deepcopy(self.parameters)
            ),
            delta_macro_time_filter=DeltaMacroTimeFilterSettings(
                dT_min=float(self.dt_min),
                dT_max=float(self.dt_max),
                dT_min_active=bool(self.dt_min_active),
                dT_max_active=bool(self.dt_max_active),
            ),
            invert_filter=bool(self.invert),
            max_gap=int(self.merge_gap) if self.use_gap_fill else 0,
            use_gap_fill=bool(self.use_gap_fill),
        )
        formats = self.output_formats()
        return AnalysisSettings(
            photon_filter=filter_settings,
            burst_detection=BurstDetectionSettings(
                min_photons=int(self.min_photons),
                photon_window=int(self.photon_window),
                time_window=float(self.dt_max) / 1000.0,
            ),
            output_formats=formats,
            zip_output=bool(self.zip_output) and "bur" in formats,
            remove_folder=bool(self.remove_folder) and bool(self.zip_output) and "bur" in formats,
        )

    def request(self) -> dict[str, Any]:
        """Keyword arguments of ``BurstSelectionClient.analyze_files`` (without the files and MMFDB context)."""
        return dict(
            settings=asdict(self.analysis_settings()),
            windows=copy.deepcopy(self.windows),
            detectors=copy.deepcopy(self.detectors),
            filetype=self.file_type,
            legacy_output=True,
            selected_setup=self.setup_name,
            legacy_parameters=self.burst_selection_parameters(),
        )

    def blocked_reason(self) -> str | None:
        """Why a search must not run (an unconverted µs-ALEX file under micro-time gates), or ``None``."""
        if not self.detectors or not self.files:
            return None
        from chisurf.core.fio.staging import open_tttr

        try:
            tttr = open_tttr(str(self.files[0]))
        except Exception:  # noqa: BLE001 - an unreadable file fails in the run, with its own message
            return None
        reason = diag_mod.gate_mismatch_warning(tttr, self.detectors)
        if reason is None:
            return None
        return (
            "Burst search not run.\n\n"
            + reason
            + "\n\nNothing was written. Run the Alternation step "
            "(press its convert button); the search then runs on the converted measurement."
        )

    def _fingerprint_of(self, request: dict[str, Any]) -> str:
        from chisurf.core.runtime import analysis_cache

        return analysis_cache.fingerprint(
            self.files,
            {**request, "_read_context": analysis_cache.photon_read_context()},
            extra=analysis_cache.algorithm_tag("burst_selection", ALGORITHM_VERSION, "tttrlib"),
        )

    # -- MMFDB output ---------------------------------------------------------------------------------------- #
    def _mmfdb_db(self):
        from ..api.mmfdb import acquire_mmfdb_connection

        return acquire_mmfdb_connection()

    def _mmfdb_session(self):
        db = self._mmfdb_db()
        if db is None:
            return None
        from chisurf.core.transform.mmfdb import runtime_session_for_database

        return runtime_session_for_database(db)

    def sample_options(self) -> list[tuple[str, str]]:
        """MMFDB samples (``[(id, label)]``), first entry "derive from the files"."""
        options = [("", "From the raw files")]
        try:
            db = self._mmfdb_db()
            if db is not None:
                from mmfdb.samples.sample_manager import list_samples

                for sample in list_samples(db):
                    sid = str(sample.get("sample_id") or sample.get("id") or "")
                    if sid:
                        options.append((sid, str(sample.get("name") or sid)))
        except Exception:  # noqa: BLE001 - no database: only the default entry
            pass
        return options

    def mmfdb_context(self) -> dict[str, Any] | None:
        """The MMFDB archival context of a run (``None`` when MMFDB output is off), as the Qt tool builds it.

        Raises
        ------
        RuntimeError
            When no sample can be determined (the Qt tool asks in a dialog; here the Sample field says which).
        """
        if not self.mmfdb_output:
            return None
        from ..api.mmfdb import (
            raw_artifact_id_for_path,
            register_raw_input_for_sample,
            sample_id_for_raw_path,
        )

        db = self._mmfdb_db()
        if db is None:
            return {"enabled": True}
        session = self._mmfdb_session()
        if session is None:
            raise RuntimeError("MMFDB output requires an authenticated session.")
        paths = [p.resolve() for p in self.files if p.is_file()]
        known = {sid for p in paths if (sid := sample_id_for_raw_path(db, p))}
        sample_id = self.sample_id or (next(iter(known)) if len(known) == 1 else "")
        if not sample_id:
            raise RuntimeError(
                "MMFDB output needs a sample: choose one in the Sample field of Output."
            )
        setup_id = self._ensure_setup_in_mmfdb(db, session)
        artifacts = {}
        for path in paths:
            artifact_id = raw_artifact_id_for_path(db, path) or register_raw_input_for_sample(
                db=db,
                path=path,
                sample_id=sample_id,
                filetype=self.file_type,
                selected_setup=self.setup_name,
                setup_id=setup_id,
                session=session,
            )
            if artifact_id:
                artifacts[str(path)] = artifact_id
        return {
            "enabled": True,
            "sample_id": sample_id,
            "source_artifact_ids": artifacts,
            "register_missing_inputs": True,
            "setup_id": setup_id,
        }

    def _ensure_setup_in_mmfdb(self, db, session) -> str:
        if not self.setup_name:
            return ""
        from chisurf.core.fio.setup_store import setup_id_for_name

        setup_id = setup_id_for_name(self.setup_name, session.user_id, "tttr_detector_setup")
        if db.get_setup(setup_id) is not None:
            return setup_id
        reading = {"file_type": self.file_type}
        data = {"windows": self.windows, "detectors": self.detectors, "tttr_reading": reading}
        db.save_setup(
            setup_id=setup_id,
            name=self.setup_name,
            description="TTTR detector and PIE-window setup",
            configuration={"setup_type": "tttr_detector_setup", "setup_data": data},
            detectors=self.detectors,
            windows=self.windows,
            timing_resolution=reading,
            created_by_user_id=session.user_id,
            is_public=False,
        )
        return setup_id

    # -- the run --------------------------------------------------------------------------------------------- #
    def prepare_run(self, force: bool = False) -> str | None:
        """Check a run on the GUI thread; return why it does not run (``None`` = start the job).

        An identical request to the displayed result is answered by that result unless *force*.
        """
        if not self.files:
            return "No TTTR files selected."
        blocked = self.blocked_reason()
        if blocked is not None:
            return blocked
        if not self.algorithms:
            return "This tttrlib publishes no burst searches; update tttrlib."
        fingerprint = self._fingerprint_of(self.request())
        if not force and self.has_processed and fingerprint == self._result_fingerprint:
            self.unchanged = True
            self.status_text = (
                "Unchanged - kept the previous burst search (same files, same settings; nothing re-searched). "
                "Press Restart to search them again anyway."
            )
            return self.status_text
        self.unchanged = False
        self._fingerprint = fingerprint
        try:
            self._mmfdb = self.mmfdb_context()
        except RuntimeError as exc:
            return str(exc)
        return None

    def run(self) -> dict[str, Any]:
        """Search every file (worker side of the job): one backend call, per-file progress."""
        paths = list(self.files)

        def progress(done: int, total: int, path: str) -> None:
            self.status_text = f"Searched {Path(path).name} ({done}/{total})"
            self.notify("progress")

        self.status_text = f"Searching {len(paths)} file(s) ..."
        self.notify("progress")
        result = self.client.analyze_files(
            paths, mmfdb=getattr(self, "_mmfdb", None), progress_callback=progress, **self.request()
        )
        self._finish(result)
        return result

    def _finish(self, result: dict[str, Any]) -> None:
        self.result = result
        dataframes = result.get("dataframes", {}) or {}
        self.frames_by_file = {}
        for path in self.files:
            frame = None
            for key in (str(path), str(path.resolve()), path.name):
                rows = dataframes.get(key)
                if rows:
                    frame = store_from_rows(rows)
                    break
            self.frames_by_file[str(path)] = frame if frame is not None else new_store()
        meta = dict(result.get("metadata") or {})
        self.has_processed = bool(self.frames_by_file)
        self._result_fingerprint = self._fingerprint if self.has_processed else None
        self.preview = False
        self._refresh_display_frame()
        warnings = result.get("warnings") or []
        self.status_text = (
            f"{meta.get('n_bursts', 0)} bursts in {meta.get('n_files', len(self.files))} file(s); "
            f"{meta.get('n_selected', 0)} of {meta.get('n_photons', 0)} photons selected."
            + (f" Output: {meta['output_folder']}" if meta.get("output_folder") else "")
            + (f" Warnings: {'; '.join(map(str, warnings))}" if warnings else "")
        )

    @property
    def n_bursts(self) -> int:
        meta = (self.result or {}).get("metadata") or {}
        return int(meta.get("n_bursts", 0))

    def summary_rows(self) -> list[dict[str, str]]:
        """Key figures of the last run (the Qt Summary dock)."""
        meta = dict((self.result or {}).get("metadata") or {})
        frame = self.display_frame
        rows = [
            ("Files", meta.get("n_files", len(self.files))),
            ("Bursts", meta.get("n_bursts", "")),
            ("Photons", meta.get("n_photons", "")),
            ("Selected photons", meta.get("n_selected", "")),
            ("Output folder", meta.get("output_folder", "")),
            ("Detector setup", self.setup_name or "custom"),
            ("Search", f"{self.algorithm} {json.dumps(self.parameters, default=str)}"),
        ]
        if frame is not None and row_count(frame):
            data = _display_rows_frame(frame)
            for name in ("Number of Photons", "Duration (ms)", "Count Rate (KHz)"):
                if name in column_names(data):
                    values = numeric_column(data, name)
                    values = values[np.isfinite(values)]
                    if values.size:
                        rows.append((f"Mean {name}", f"{float(np.mean(values)):.4g}"))
        return [{"key": str(k), "value": str(v)} for k, v in rows]

    def result_json(self) -> str:
        meta = dict((self.result or {}).get("metadata") or {})
        return json.dumps(
            meta | {"settings": asdict(self.analysis_settings())}, indent=2, default=str
        )

    # -- the displayed burst table ----------------------------------------------------------------------- #
    def _refresh_display_frame(self) -> None:
        path = self.active_file
        frame = self.frames_by_file.get(str(path)) if path is not None else None
        if frame is None or row_count(frame) == 0:
            if not self.preview:
                self.display_frame = None
            return
        self.display_frame = diag_mod.display_frame([frame], [self.active_index])

    def burst_columns(self) -> list[str]:
        if self.display_frame is None:
            return list(UI_COLUMNS)
        return column_names(self.display_frame)

    def burst_rows(self, limit: int = 5000) -> list[dict[str, Any]]:
        """Rows of the displayed table without the zero separator rows (the first *limit*)."""
        if self.display_frame is None:
            return []
        rows = rows_from_table(_display_rows_frame(self.display_frame))[:limit]
        out = []
        for index, row in enumerate(rows):
            entry = {"row": index}
            for key in UI_COLUMNS:
                if key in row:
                    value = row[key]
                    entry[key] = f"{value:.4g}" if isinstance(value, float) else str(value)
            out.append(entry)
        return out

    def feature_options(self) -> list[str]:
        if self.display_frame is None:
            return list(diag_mod.HISTOGRAM_FEATURES)
        names = [n for n in column_names(self.display_frame) if n != "File Idx"]
        return [*names, PROXIMITY_RATIO_COLUMN] if PROXIMITY_RATIO_COLUMN not in names else names

    def feature_data(self, feature: str) -> np.ndarray:
        if self.display_frame is None:
            return np.array([], dtype=float)
        try:
            return diag_mod.histogram_data_from_frame(self.display_frame, feature)
        except Exception:  # noqa: BLE001 - a non-numeric column has no histogram
            return np.array([], dtype=float)

    # -- histogram and GMM ------------------------------------------------------------------------------- #
    def histogram_range(self, data: np.ndarray) -> tuple[float, float]:
        lo, hi = float(self.hist_min), float(self.hist_max)
        if lo >= hi and data.size:
            lo, hi = float(np.min(data)), float(np.max(data))
            if lo == hi:
                lo, hi = lo - 0.5, hi + 0.5
        return lo, hi

    def auto_range(self) -> None:
        data = self.feature_data(self.hist_feature)
        if data.size == 0:
            return
        lo, hi = float(np.min(data)), float(np.max(data))
        if lo == hi:
            lo, hi = lo - 0.5, hi + 0.5
        self.hist_min, self.hist_max = lo, hi
        self.gmm_result = None

    def histogram(self) -> tuple[np.ndarray, np.ndarray, float] | None:
        """``(centres, counts, width)`` of the feature histogram, or ``None``."""
        data = self.feature_data(self.hist_feature)
        if data.size == 0:
            return None
        lo, hi = self.histogram_range(data)
        counts, edges = np.histogram(data, bins=max(1, int(self.hist_bins)), range=(lo, hi))
        return (edges[:-1] + edges[1:]) / 2.0, counts.astype(float), float(edges[1] - edges[0])

    def _gmm(self, n_components: int):
        from chisurf.core.ml import GaussianMixture

        s = self.gmm_settings
        return GaussianMixture(
            n_components=n_components,
            covariance_type=s["covariance_type"],
            random_state=s["random_state"],
            max_iter=s["max_iter"],
            n_init=s["n_init"],
            tol=s["tol"],
            reg_covar=s["reg_covar"],
        )

    def fit_gmm(self) -> dict[str, Any]:
        """Fit the feature histogram with a Gaussian mixture (the Qt ``_plot_gmm``); the result is kept for the plot."""
        data = self.feature_data(self.hist_feature)
        hist = self.histogram()
        n = int(self.gmm_components)
        if self.gmm_auto_components and n == 0 and data.size > 1:
            max_c = min(int(self.gmm_settings["max_components"]), data.size)
            bic = [
                self._gmm(c).fit(data.reshape(-1, 1)).bic(data.reshape(-1, 1))
                for c in range(1, max_c + 1)
            ]
            n = int(np.argmin(bic) + 1)
        if hist is None or n <= 0 or data.size < n:
            self.gmm_result = {
                "error": "GMM fitting skipped: not enough data points or zero components."
            }
            return self.gmm_result
        centres, counts, _w = hist
        lo, hi = self.histogram_range(data)
        x = np.linspace(lo, hi, 200)
        model = self._gmm(n)
        model.fit(data.reshape(-1, 1))
        y = np.exp(model.score_samples(x.reshape(-1, 1)))
        scale = float(np.max(counts)) / float(np.max(y)) if np.max(y) > 0 else 1.0
        components = []
        rows = []
        for i in range(n):
            mean = float(model.means_[i, 0])
            var = float(np.asarray(model.covariances_).reshape(n, -1)[i, 0])
            weight = float(model.weights_[i])
            components.append(
                weight * np.exp(-0.5 * (x - mean) ** 2 / var) / np.sqrt(2 * np.pi * var) * scale
            )
            rows.append(
                {
                    "component": str(i + 1),
                    "weight": f"{weight:.3f}",
                    "mean": f"{mean:.3f}",
                    "std": f"{np.sqrt(var):.3f}",
                }
            )
        self.gmm_result = {
            "x": x,
            "total": y * scale,
            "components": components,
            "rows": rows,
            "n": n,
        }
        return self.gmm_result

    def gmm_rows(self) -> list[dict[str, str]]:
        return list((self.gmm_result or {}).get("rows") or [])

    def scatter(self) -> tuple[np.ndarray, np.ndarray] | None:
        x, y = self.feature_data(self.scatter_x), self.feature_data(self.scatter_y)
        if x.size == 0 or y.size == 0 or self.display_frame is None:
            return None
        frame = _display_rows_frame(self.display_frame)
        xs = _column_or_pr(frame, self.scatter_x)
        ys = _column_or_pr(frame, self.scatter_y)
        if xs is None or ys is None:
            return None
        ok = np.isfinite(xs) & np.isfinite(ys)
        return xs[ok], ys[ok]

    # -- diagnostics (the visible window of the active file) ------------------------------------------------- #
    def load_diagnostics(self) -> dict[str, Any] | None:
        """Filter and search the visible window of the active file (photon arrays + bursts), and preview its bursts."""
        path = self.active_file
        if path is None:
            self.diagnostic = None
            return None
        settings = asdict(self.analysis_settings())
        diag = self.client.load_diagnostics(
            path,
            settings,
            window_s=float(self.window_length_s) or None,
            window_start_s=float(self.window_start_s),
            tttr=self._open_tttr.get(str(path)),
        )
        if not diag or "tttr" not in diag:
            self.diagnostic = None
            self.status_text = f"Diagnostics unavailable for {path.name}."
            return None
        diag["path"] = path
        self._open_tttr[str(path)] = diag["tttr"]
        self.diagnostic = diag
        if not self.has_processed:
            self._preview(diag)
        return diag

    def _preview(self, diag: dict[str, Any]) -> None:
        start_stop = diag.get("start_stop")
        if start_stop is None or len(start_stop) == 0:
            return
        from ..api.selection import summarize_bursts

        frame = summarize_bursts(
            start_stop,
            str(diag["path"]),
            diag["tttr"],
            windows=self.windows,
            detectors=self.detectors,
        )
        self.display_frame = diag_mod.display_frame([frame], [self.active_index])
        self.preview = True
        end = float(self.window_start_s) + float(self.window_length_s)
        warning = diag_mod.gate_mismatch_warning(diag["tttr"], self.detectors)
        self.status_text = (
            f"Preview of {self.window_start_s:.1f}-{end:.1f} s: {len(start_stop)} burst(s). "
            "These are the bursts of the visible window only; press Run to search every photon and write the table."
            + (f" Warning: {warning}" if warning else "")
        )

    def timeline_span(self) -> float:
        """Length of the active file in seconds (0 before its diagnostics are loaded)."""
        tttr = (self.diagnostic or {}).get("tttr")
        if tttr is None:
            return 0.0
        mt = np.asarray(tttr.macro_times)
        return float(mt[-1] - mt[0]) * float(tttr.header.macro_time_resolution) if mt.size else 0.0

    def _window_indices(self) -> tuple[int, int]:
        diag = self.diagnostic or {}
        tttr = diag.get("tttr")
        n = int(len(diag.get("selected", [])))
        if tttr is None or n == 0:
            return 0, 0
        window = self.client._window_indices(
            tttr, float(self.window_length_s) or None, float(self.window_start_s)
        )
        return window if window is not None else (0, n)

    def trace_curves(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Count-rate trace (Hz) of the visible window: ``{"all": (t, rate), "selected": (t, rate)}``."""
        from chisurf.core.fio.decimate import thin_for_plot

        diag = self.diagnostic or {}
        tttr = diag.get("tttr")
        first, last = self._window_indices()
        if tttr is None or last <= first:
            return {}
        width_ms = max(float(self.trace_bin_ms), 1e-3)
        out = {}
        if self.show_all_photons:
            t, r = diag_mod.trace_rate_hz(
                tttr[np.arange(first, last)], width_ms / 1000.0, width_ms, 0.0
            )
            out["all"] = thin_for_plot(t, r, max_points=MAX_PLOT_POINTS)
        selected = np.asarray(diag["selected"], dtype=bool)
        idx = np.where(selected[first:last])[0] + first
        if self.show_selected_photons and idx.size:
            t, r = diag_mod.trace_rate_hz(tttr[idx], width_ms / 1000.0, width_ms, 0.0)
            out["selected"] = thin_for_plot(t, r, max_points=MAX_PLOT_POINTS)
        return out

    def dt_curves(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Inter-photon time (ms) against photon index over the visible window (all / selected)."""
        from chisurf.core.fio.decimate import thin_for_plot

        diag = self.diagnostic or {}
        tttr = diag.get("tttr")
        first, last = self._window_indices()
        if tttr is None or last <= first:
            return {}
        d_t = diag_mod.delta_macro_time_ms(tttr)[first:last]
        index = np.arange(first, last, dtype=float)
        selected = np.asarray(diag["selected"], dtype=bool)[first:last]
        out = {}
        if self.show_all_photons:
            out["all"] = thin_for_plot(index, d_t, max_points=MAX_PLOT_POINTS)
        if self.show_selected_photons and selected.any():
            out["selected"] = thin_for_plot(
                index[selected], d_t[selected], max_points=MAX_PLOT_POINTS
            )
        return out

    def decay_curves(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Micro-time histograms (ns, counts) of the file and of the selected photons, trailing zeros cut."""
        diag = self.diagnostic or {}
        tttr = diag.get("tttr")
        if tttr is None:
            return {}
        coarse = max(1, int(self.decay_bins))
        out = {}

        def trimmed(y, x):
            y, x = np.asarray(y, dtype=float), np.asarray(x, dtype=float)
            positive = np.where(y > 0)[0]
            if positive.size == 0:
                return None
            end = int(positive[-1]) + 1
            return x[:end] * 1e9, y[:end]

        if self.show_all_photons:
            got = trimmed(*tttr.get_microtime_histogram(coarse))
            if got is not None:
                out["all"] = got
        idx = np.where(np.asarray(diag["selected"], dtype=bool))[0]
        if self.show_selected_photons and idx.size:
            got = trimmed(*tttr[idx].get_microtime_histogram(coarse))
            if got is not None:
                out["selected"] = got
        return out

    def duration_histogram(self) -> tuple[np.ndarray, np.ndarray, float] | None:
        """``(centres, counts, width)`` of the burst durations (ms) of the visible window."""
        if self.diagnostic is None:
            return None
        durations = diag_mod.burst_durations_ms(self.diagnostic)
        if durations.size == 0:
            return None
        counts, edges = np.histogram(durations, bins=max(3, int(self.burst_bins)))
        return (edges[:-1] + edges[1:]) / 2.0, counts.astype(float), float(edges[1] - edges[0])

    def thresholds(self) -> dict[str, float | None]:
        """Lines the dT plot draws: the active macro-time cuts in ms."""
        return {
            "dt_min": float(self.dt_min) if self.dt_min_active else None,
            "dt_max": float(self.dt_max) if self.dt_max_active else None,
        }

    # -- output ---------------------------------------------------------------------------------------------- #
    def combined_frame(self):
        frames = [f for f in self.frames_by_file.values() if f is not None and row_count(f)]
        return concat_stores(frames) if frames else None

    def save_bur(self, path) -> Path:
        """Write the burst tables of every file of the last run as one ``.bur`` (the Qt "Save .bur")."""
        frame = self.combined_frame()
        if frame is None:
            raise ValueError("No burst table to save: run the search first.")
        self.client.save_bur(frame, Path(path))
        self.status_text = f"Saved {path}"
        return Path(path)

    def export_bur(self, path) -> Path:
        """Write the displayed table (the active file, with ``File Idx``) as a tab-separated ``.bur``."""
        if self.display_frame is None or row_count(self.display_frame) == 0:
            raise ValueError("No burst data to export.")
        write_csv_table(str(path), self.display_frame)
        self.status_text = f"Exported to {path}"
        return Path(path)

    def export_flr_cif(self, path) -> Path:
        """Write the displayed table and the metadata as flrCIF (the Qt ``_write_flr_cif``)."""
        if self.display_frame is None or row_count(self.display_frame) == 0:
            raise ValueError("No burst data to export.")
        lines = [
            "# flrCIF export from Burst Selection Tool",
            "#",
            "data_",
            "",
            "# Analysis metadata",
        ]
        for key, value in sorted(self.metadata.items()):
            lines.append(f"_{key} {value}")
        lines += ["", "# Burst data", "loop_"]
        names = column_names(self.display_frame)
        lines += [f"_{col}" for col in names]
        for row in rows_from_table(self.display_frame):
            lines.append("\t".join(str(row[name]) for name in names))
        Path(path).write_text("\n".join(lines))
        self.status_text = f"Exported to {path}"
        return Path(path)

    def metadata_rows(self) -> list[dict[str, str]]:
        return [{"key": k, "value": str(v)} for k, v in self.metadata.items()]

    def set_metadata(self, key: str, value: str) -> None:
        key = str(key).strip()
        if not key:
            raise ValueError("A metadata entry needs a key.")
        self.metadata[key] = str(value)

    def delete_metadata(self, key: str) -> None:
        self.metadata.pop(str(key), None)

    def metadata_keys(self) -> list[str]:
        try:
            from chisurf.core.fio.mmcif.pdbx_metadata import get_pdbx_metadata_keys

            extra = get_pdbx_metadata_keys()
        except Exception:  # noqa: BLE001
            extra = []
        return COMMON_METADATA_KEYS + [k for k in extra if k not in COMMON_METADATA_KEYS]

    def output_path(self) -> str | None:
        """Folder or file of the last run's output (what ndX opens)."""
        result = self.result or {}
        paths = result.get("output_paths") or {}
        for key in ("output_folder", "bur", "zip"):
            if paths.get(key):
                return str(paths[key])
        for roles in (result.get("output_paths_by_file") or {}).values():
            for key in ("output_folder", "bur"):
                if roles.get(key):
                    return str(roles[key])
        meta = result.get("metadata") or {}
        return str(meta["output_folder"]) if meta.get("output_folder") else None

    # -- persistence ----------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        """Everything a user sets (filter, search, output switches, display, GMM, metadata), JSON-ready."""
        data = {
            "kind": SETTINGS_KIND,
            "algorithm": self.algorithm,
            "parameters": copy.deepcopy(self.parameters),
        }
        data.update({a: getattr(self, a) for a in _FILTER_ATTRS + _DISPLAY_ATTRS})
        data.update(
            zip_output=self.zip_output,
            remove_folder=self.remove_folder,
            mmfdb_output=self.mmfdb_output,
            sample_id=self.sample_id,
            gmm_settings=dict(self.gmm_settings),
            metadata=dict(self.metadata),
        )
        return data

    def import_settings(self, data: dict[str, Any]) -> None:
        if data.get("kind") not in (None, SETTINGS_KIND):
            raise ValueError(f"Not a Burst Selection settings file (kind {data.get('kind')!r}).")
        for attr in (
            _FILTER_ATTRS
            + _DISPLAY_ATTRS
            + ("zip_output", "remove_folder", "mmfdb_output", "sample_id")
        ):
            if attr in data:
                current = getattr(self, attr)
                value = data[attr]
                setattr(
                    self,
                    attr,
                    type(current)(value)
                    if current is not None and not isinstance(current, str)
                    else value,
                )
        if data.get("algorithm") in self.algorithms:
            self.algorithm = str(data["algorithm"])
            self.parameters = {
                **search_defaults(self.algorithm),
                **dict(data.get("parameters") or {}),
            }
        if isinstance(data.get("gmm_settings"), dict):
            self.gmm_settings = {**DEFAULT_GMM_SETTINGS, **data["gmm_settings"]}
        if isinstance(data.get("metadata"), dict):
            self.metadata = {str(k): str(v) for k, v in data["metadata"].items()}
        self.settings_changed()

    def save_settings(self, path) -> None:
        Path(path).write_text(json.dumps(self.export_settings(), indent=2, default=str))

    def load_settings(self, path) -> None:
        self.import_settings(json.loads(Path(path).read_text()))

    @staticmethod
    def remembered_path() -> Path:
        from chisurf.core.settings.path_utils import get_path

        return get_path("settings") / "burst_selection_native.json"

    def remember(self) -> None:
        """Keep the settings for the next start (written after each run and on close)."""
        try:
            self.save_settings(self.remembered_path())
        except OSError:
            pass

    def restore(self) -> bool:
        path = self.remembered_path()
        if not path.is_file():
            return False
        try:
            self.load_settings(path)
        except (OSError, ValueError):
            return False
        return True

    # -- workflow hand-off --------------------------------------------------------------------------------- #
    def output_folder(self) -> Path | None:
        """The burst folder the later workflow steps read (``None`` before a run)."""
        result = self.result or {}
        candidates = [
            result.get("output_folder"),
            (result.get("metadata") or {}).get("output_folder"),
        ]
        candidates.append((result.get("output_paths") or {}).get("output_folder"))
        for value in candidates:
            if isinstance(value, str) and Path(value).is_dir():
                return Path(value)
        return None


def _burst_count(frame) -> int:
    """Bursts in a zero-interleaved burst table (separator rows not counted)."""
    if frame is None:
        return 0
    try:
        return row_count(burst_rows_for_display(frame))
    except Exception:  # noqa: BLE001
        return row_count(frame)


def _display_rows_frame(frame):
    return burst_rows_for_display(frame)


def _column_or_pr(frame, name: str):
    if name == PROXIMITY_RATIO_COLUMN:
        from .adapter import proximity_ratio_from_frame

        values = proximity_ratio_from_frame(frame)
        return None if values is None else np.asarray(values, dtype=float)
    if name not in column_names(frame):
        return None
    return np.asarray(numeric_column(frame, name), dtype=float)


__all__ = [
    "ALL",
    "BurstSelectionModel",
    "DEFAULT_GMM_SETTINGS",
    "SearchParameters",
    "schema_sections",
    "search_algorithms",
    "search_defaults",
]
