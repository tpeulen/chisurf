"""GUI adapters for the Burst Selection plugin."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional

import numpy as np

from chisurf.core.datastore import (
    column_names,
    concat_stores,
    numeric_column,
    read_csv_table,
    row_count,
    store_from_arrays,
    take_where,
)

from ..api.models import (
    AnalysisSettings,
    BurstDetectionSettings,
    BurstFilterMode,
    CountRateFilterSettings,
    DeltaMacroTimeFilterSettings,
    GMMSettings,
    PhotonFilterSettings,
    BocpdFilterSettings,
    KalmanFilterSettings,
    CusumFilterSettings,
    TttrlibSearchSettings,
)
from ..api.selection import analyze_file

UI_COLUMNS = [
    "File Idx",
    "First Photon",
    "Last Photon",
    "Duration (ms)",
    "Mean Macro Time (ms)",
    "Number of Photons",
    "Count Rate (KHz)",
    "Number of Photons (red)",
    "Number of Photons (green)",
]

PROXIMITY_RATIO_COLUMN = "Proximity Ratio"


def _numeric_series(frame, column: str):
    """Return ``column`` as floats when present, else ``None``."""
    if column not in column_names(frame):
        return None
    return numeric_column(frame, column)


def _ratio_series(numerator, denominator):
    """Return ``numerator / denominator``, ``NaN`` where the denominator is
    not positive — a burst with no signal has no ratio, and 0/0 must not
    become 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.divide(
            numerator, denominator,
            out=np.full(len(numerator), np.nan, dtype=float),
            where=denominator > 0,
        )
    return out


def proximity_ratio_from_frame(frame):
    """Compute or return the proximity ratio when source columns exist."""
    if PROXIMITY_RATIO_COLUMN in column_names(frame):
        return numeric_column(frame, PROXIMITY_RATIO_COLUMN)
    red = _numeric_series(frame, "Number of Photons (red)")
    green = _numeric_series(frame, "Number of Photons (green)")
    if red is not None and green is not None:
        return _ratio_series(red, red + green)
    red_rate = _numeric_series(frame, "Red Count Rate (KHz)")
    green_rate = _numeric_series(frame, "Green Count Rate (KHz)")
    if red_rate is not None and green_rate is not None:
        return _ratio_series(red_rate, red_rate + green_rate)
    return None


def analysis_settings_from_wizard(wizard: Any) -> AnalysisSettings:
    """Create API analysis settings from a BurstSelectionTool instance."""
    output_formats = ["bur"]
    if wizard.checkBox_FileMFDHDF.isChecked():
        output_formats.append("hdf5")
    settings = AnalysisSettings(
        output_formats=output_formats,
        zip_output=bool(wizard.checkBox_ZipOutput.isChecked()),
        remove_folder=bool(wizard.checkBox_RemoveFolder.isChecked()),
    )
    settings.photon_filter = photon_filter_settings_from_wizard(wizard.burst_finder)
    settings.burst_detection = BurstDetectionSettings(
        min_photons=int(wizard.burst_finder.min_ph),
        photon_window=int(wizard.burst_finder.ph_window),
        time_window=float(wizard.burst_finder.dT_max) / 1000.0,
    )
    settings.gmm = GMMSettings(
        covariance_type=str(wizard.gmm_settings["covariance_type"]),
        random_state=int(wizard.gmm_settings["random_state"]),
        max_iter=int(wizard.gmm_settings["max_iter"]),
        n_init=int(wizard.gmm_settings["n_init"]),
        tol=float(wizard.gmm_settings["tol"]),
        max_components=int(wizard.gmm_settings["max_components"]),
        reg_covar=float(wizard.gmm_settings["reg_covar"]),
        auto_components=bool(wizard.checkBox_auto_components.isChecked()),
    )
    return settings


def photon_filter_settings_from_wizard(wizard_filter: Any) -> PhotonFilterSettings:
    """Create photon filter settings from a WizardTTTRPhotonFilter instance."""
    # Safe checks for BOCPD settings
    bocpd_settings = BocpdFilterSettings(
        prior_count=float(getattr(wizard_filter, "bocpd_prior_count", 1.0)),
        prior_duration=float(getattr(wizard_filter, "bocpd_prior_duration", 0.1)),
        changepoint_prob=float(getattr(wizard_filter, "bocpd_changepoint_prob", 1e-5)),
        dt=float(getattr(wizard_filter, "trace_bin_width", 1.0)) / 1000.0,
    )

    # Safe checks for Kalman settings
    kalman_settings = KalmanFilterSettings(
        q=float(getattr(wizard_filter, "kalman_q", 0.01)),
        r_scale=float(getattr(wizard_filter, "kalman_r_scale", 0.1)),
        z_thresh=float(getattr(wizard_filter, "kalman_z_thresh", 3.0)),
        min_len=int(getattr(wizard_filter, "kalman_min_len", 2)),
        merge_gap=int(getattr(wizard_filter, "kalman_merge_gap", 5)),
        dt=float(getattr(wizard_filter, "trace_bin_width", 1.0)) / 1000.0,
    )

    # Safe checks for CUSUM settings
    cusum_settings = CusumFilterSettings(
        min_photons=int(getattr(wizard_filter, "min_ph", 50)),
        background_rate=int(getattr(wizard_filter, "cusum_bg_rate", 2000)),
        sb_ratio=float(getattr(wizard_filter, "cusum_sb_ratio", 30.0)),
        alpha=float(getattr(wizard_filter, "cusum_alpha", 0.05)),
        beta=float(getattr(wizard_filter, "cusum_beta", 0.05)),
    )

    # The selected tttrlib search and its parameters, both free-form so that a
    # new algorithm needs no field here.
    tttrlib_settings = TttrlibSearchSettings(
        algorithm=str(getattr(wizard_filter, "tttrlib_algorithm", "") or "maxtree"),
        parameters=dict(getattr(wizard_filter, "tttrlib_parameters", {}) or {}),
    )

    return PhotonFilterSettings(
        channels=list(wizard_filter.channels),
        # `microtime_ranges` is None when no window is selected ("All"); an
        # empty list is what "apply no micro-time mask" looks like downstream.
        microtime_ranges=list(wizard_filter.microtime_ranges or []),
        filter_active=bool(wizard_filter.settings.get("filter_active", True)),
        used_filter=BurstFilterMode(str(wizard_filter.used_filter)),
        count_rate_filter=CountRateFilterSettings(
            n_ph_max=int(wizard_filter.settings["count_rate_filter"]["n_ph_max"]),
            time_window=float(wizard_filter.settings["count_rate_filter"]["time_window"]),
            invert=bool(wizard_filter.settings.get("invert_filter", False)),
        ),
        bocpd_filter=bocpd_settings,
        kalman_filter=kalman_settings,
        cusum_filter=cusum_settings,
        tttrlib_search=tttrlib_settings,
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(
            dT_min=float(wizard_filter.dT_min),
            dT_max=float(wizard_filter.dT_max),
            dT_min_active=bool(wizard_filter.use_lower),
            dT_max_active=bool(wizard_filter.use_upper),
        ),
        invert_filter=bool(wizard_filter.settings.get("invert_filter", False)),
        max_gap=int(wizard_filter.max_gap),
        use_gap_fill=bool(wizard_filter.use_gap_fill),
    )


#: Stored ``photon_filter`` settings that the generated filter form owns, mapped
#: onto its field names. The two differ because the settings dataclass groups by
#: algorithm (``cusum_filter.alpha``) while the form is flat (``alpha``).
#:
#: **Only these go through the generic restore.** The filter page is a partial
#: AutoForm port: its view spec covers the settings that apply whichever search
#: is chosen — channel, macro-time interval, the enable/invert switches — while
#: the *search parameters* are rendered from the JSON Schema tttrlib publishes,
#: and a few legacy modes still read shared spin boxes. Those cannot be restored
#: by writing form state because the form has no field for them, so they go
#: through the page's own accessors below. When the search parameters move into
#: the declarative settings, their entries move here and the fallback shrinks.
_FILTER_STATE_MAP = {
    ("", "filter_active"): "filter_active",
    ("", "invert_filter"): "invert",
    ("delta_macro_time_filter", "dT_min"): "dt_min",
    ("delta_macro_time_filter", "dT_max"): "dt_max",
    ("delta_macro_time_filter", "dT_min_active"): "dt_min_active",
    ("delta_macro_time_filter", "dT_max_active"): "dt_max_active",
}




#: The form binds its controls through this target, so state keys carry it.
_FILTER_TARGET = "settings"


def _filter_state_from_settings(photon: dict) -> dict:
    """Translate stored ``photon_filter`` settings into filter-form state."""
    state: dict[str, Any] = {}
    for (group, key), field in _FILTER_STATE_MAP.items():
        block = photon if not group else (photon.get(group) or {})
        if isinstance(block, dict) and block.get(key) is not None:
            state[f"{_FILTER_TARGET}.{field}"] = block[key]
    return state


#: Settings the generated form has no field for, written through the page's own
#: accessors. Each is ``(page attribute, group, key)``; the page's properties
#: already funnel into one settings object, so this is a naming bridge and not a
#: second store. It shrinks to nothing as the search parameters are ported.
_UNPORTED_FILTER_SETTINGS = (
    ("channels", "", "channels"),
    ("microtime_ranges", "", "microtime_ranges"),
    ("use_gap_fill", "", "use_gap_fill"),
    ("max_gap", "", "max_gap"),
    ("min_ph", "count_rate_filter", "n_ph_max"),
    ("cusum_sb_ratio", "cusum_filter", "sb_ratio"),
    ("cusum_alpha", "cusum_filter", "alpha"),
    ("cusum_beta", "cusum_filter", "beta"),
    ("kalman_q", "kalman_filter", "q"),
    ("kalman_r_scale", "kalman_filter", "r_scale"),
    ("kalman_z_thresh", "kalman_filter", "z_thresh"),
    ("kalman_min_len", "kalman_filter", "min_len"),
    ("kalman_merge_gap", "kalman_filter", "merge_gap"),
    ("bocpd_prior_count", "bocpd_filter", "prior_count"),
    ("bocpd_prior_duration", "bocpd_filter", "prior_duration"),
    ("bocpd_changepoint_prob", "bocpd_filter", "changepoint_prob"),
    ("tttrlib_algorithm", "tttrlib_search", "algorithm"),
    ("tttrlib_parameters", "tttrlib_search", "parameters"),
)


def _apply_unported_filter_settings(finder: Any, photon: dict, skipped: list) -> None:
    """Write the settings the generated form does not yet cover."""
    for attribute, group, key in _UNPORTED_FILTER_SETTINGS:
        block = photon if not group else (photon.get(group) or {})
        if not isinstance(block, dict):
            continue
        value = block.get(key)
        if value is None:
            continue
        try:
            setattr(finder, attribute, value)
        except Exception as exc:
            skipped.append(f"photon_filter.{group or ''}{'.' if group else ''}{key}: {exc}")


def _filter_mode_from_settings(photon: dict) -> Optional[str]:
    """The filter mode to select before restoring mode-specific parameters."""
    used = photon.get("used_filter")
    if used is None:
        return None
    return str(getattr(used, "value", used))

def apply_analysis_settings_to_wizard(wizard: Any, settings: Any) -> list[str]:
    """Repopulate the wizard from stored analysis settings — the inverse of
    :func:`analysis_settings_from_wizard`.

    A burst-analysis folder records the settings it ran with
    (:mod:`chisurf.core.fio.fluorescence.burst_manifest`), which is only half a
    reproducible result: reading them back into the tool is the other half.
    Accepts either an :class:`AnalysisSettings` or the plain mapping the
    manifest stores.

    Lenient, for the same reason the AutoForm restore is: a folder written by an
    older version should restore the fields it still shares rather than fail
    whole. Anything not applied is returned rather than raised.

    **One unit trap, handled here.** ``dT_max`` is read out twice with different
    units — ``burst_detection.time_window`` is it in seconds, while
    ``delta_macro_time_filter.dT_max`` is the raw widget value in milliseconds.
    The raw one is authoritative on the way back; deriving the widget from
    ``time_window`` would silently rescale the burst search by 1000 on every
    round trip.

    Parameters
    ----------
    wizard : BurstSelectionTool
        The tool to repopulate.
    settings : AnalysisSettings or mapping
        Settings to apply.

    Returns
    -------
    list of str
        Human-readable notes about anything that could not be applied.
    """
    from dataclasses import asdict, is_dataclass

    from chisurf.gui.autoform.state import apply_state

    data = asdict(settings) if is_dataclass(settings) else dict(settings or {})
    skipped: list[str] = []

    def _check(widget_name: str, value: Any) -> None:
        widget = getattr(wizard, widget_name, None)
        if widget is None or value is None:
            if value is not None:
                skipped.append(widget_name)
            return
        try:
            widget.setChecked(bool(value))
        except Exception as exc:
            skipped.append(f"{widget_name}: {exc}")

    def _set(owner: Any, attr: str, value: Any, label: str) -> None:
        if owner is None or value is None:
            return
        try:
            setattr(owner, attr, value)
        except Exception as exc:
            skipped.append(f"{label}: {exc}")

    formats = data.get("output_formats")
    if formats is not None:
        _check("checkBox_FileMFDHDF", "hdf5" in formats)
    _check("checkBox_ZipOutput", data.get("zip_output"))
    _check("checkBox_RemoveFolder", data.get("remove_folder"))

    finder = getattr(wizard, "burst_finder", None)

    detection = data.get("burst_detection") or {}
    if finder is not None and detection:
        _set(finder, "min_ph", detection.get("min_photons"), "burst_detection.min_photons")
        _set(finder, "ph_window", detection.get("photon_window"),
             "burst_detection.photon_window")

    # The photon-filter page is already declarative: its controls are generated
    # from a view spec over a FilterSettings dataclass, and the page attributes
    # this adapter used to set one by one are properties over that same object.
    # So there is nothing to hand-map — the generic AutoForm restore writes the
    # settings straight back, and a filter parameter added to the spec is
    # restored without being named here.
    photon = data.get("photon_filter") or {}
    if finder is not None and photon:
        model = getattr(finder, "_filter_settings_model", None)
        if model is None:
            skipped.append("photon_filter: the filter form is not built yet")
        else:
            # The mode decides which parameter sections the form has, so it is
            # applied first and the spec re-read: restoring CUSUM parameters
            # into a form still showing Kalman's would report every one of them
            # as unknown.
            mode = _filter_mode_from_settings(photon)
            if mode is not None:
                apply_state(model, {f"{_FILTER_TARGET}.mode": mode}, sync=False)

            result = apply_state(model, _filter_state_from_settings(photon))
            skipped.extend(f"photon_filter.{k}: {v}" for k, v in result.failed.items())
            skipped.extend(
                f"photon_filter.{k}: the filter form has no such control"
                for k in result.unknown
            )
            _apply_unported_filter_settings(finder, photon, skipped)

    gmm = data.get("gmm") or {}
    if gmm:
        stored = getattr(wizard, "gmm_settings", None)
        if isinstance(stored, dict):
            for key in ("covariance_type", "random_state", "max_iter", "n_init",
                        "tol", "max_components", "reg_covar"):
                if gmm.get(key) is not None:
                    stored[key] = gmm[key]
        _check("checkBox_auto_components", gmm.get("auto_components"))

    return skipped


def apply_analysis_folder(wizard: Any, folder: Any) -> list[str]:
    """Repopulate the wizard from a burst-analysis folder's manifest.

    Parameters
    ----------
    wizard : BurstSelectionTool
        The tool to repopulate.
    folder : path-like
        A ``.bur`` file, the folder holding it, or the analysis folder.

    Returns
    -------
    list of str
        Notes about anything that could not be applied. A folder with no
        manifest -- one written before manifests existed -- returns a single
        explanatory note rather than raising.
    """
    from chisurf.core.fio.fluorescence.burst_manifest import restore_settings

    stored = restore_settings(folder)
    if not stored:
        return ["this analysis folder records no settings"]
    return apply_analysis_settings_to_wizard(wizard, stored)



def save_current_selection(
    wizard: Any,
    output_types: set[str],
    zip_output: bool,
    remove_folder: bool,
) -> None:
    """Save the current wizard photon/burst selection using the existing GUI path."""
    wizard.burst_finder.save_selection(
        output_types=output_types,
        zip_output=zip_output,
        remove_folder=remove_folder,
    )


def bur_file_path(file_path: str | Path, target_path: str) -> Path:
    """Return the direct ``.bur`` path used by the current GUI."""
    file_path = Path(file_path)
    return file_path.parent / target_path / "bi4_bur" / f"{file_path.stem}.bur"


def _read_bur_member(handle):
    """Read a ``.bur`` that lives inside a zip.

    The threaded reader takes a *path*, not a file object, so a zip member has
    to reach the disk first. Handing it the open member instead would stringify
    the wrapper and read nothing, with no error.

    Parameters
    ----------
    handle : file-like
        An open zip member, in binary mode.

    Returns
    -------
    tttrlib.DataStore or None
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".bur", delete=False) as scratch:
        scratch.write(handle.read())
        name = scratch.name
    try:
        return read_csv_table(name, delimiter="\t")
    finally:
        Path(name).unlink(missing_ok=True)

def load_burst_dataframe(file_path: str | Path, target_path: str):
    """Load a saved ``.bur`` file, including zip fallback paths used by the GUI."""
    file_path = Path(file_path)
    direct = bur_file_path(file_path, target_path)
    if direct.exists():
        return read_csv_table(direct, delimiter="\t")

    zip_file_path = file_path.parent / target_path / f"{target_path}.zip"
    alt_zip_paths = [
        file_path.parent / f"{target_path}.zip",
        file_path.parent / target_path / "output.zip",
        file_path.parent / "output.zip",
    ]
    for alt_path in alt_zip_paths:
        if alt_path.exists():
            zip_file_path = alt_path
            break
    else:
        if not zip_file_path.exists():
            return None

    bur_filenames = [
        f"bi4_bur/{file_path.stem}.bur",
        f"bur/{file_path.stem}.bur",
        f"{file_path.stem}.bur",
        f"{target_path}/bi4_bur/{file_path.stem}.bur",
        f"{target_path}/bur/{file_path.stem}.bur",
    ]
    with zipfile.ZipFile(str(zip_file_path), "r") as zip_file:
        all_files = zip_file.namelist()
        for bur_filename in bur_filenames:
            try:
                with zip_file.open(bur_filename) as bur_file:
                    return _read_bur_member(bur_file)
            except KeyError:
                continue
        matching = [name for name in all_files if name.endswith(f"{file_path.stem}.bur")]
        if matching:
            with zip_file.open(matching[0]) as bur_file:
                return _read_bur_member(bur_file)
    return None


def make_ui_dataframe(df):
    """Create the limited table the GUI shows."""
    rows = burst_rows_for_display(df)
    n = row_count(rows)
    present = column_names(rows)
    columns = {
        name: (numeric_column(rows, name) if name in present else np.zeros(n))
        for name in UI_COLUMNS
    }
    # From the zero-filled columns, not from the source rows: a table missing
    # the red/green counts still gets a Proximity Ratio column (of zeros), and
    # the GUI's feature list is built from what is here.
    proximity_ratio = proximity_ratio_from_frame(columns)
    if proximity_ratio is not None:
        columns[PROXIMITY_RATIO_COLUMN] = np.round(
            np.nan_to_num(proximity_ratio, nan=0.0), 6
        )
    return store_from_arrays(columns)


def burst_rows_for_display(df):
    """Return burst rows for GUI display, excluding Margarita zero separators.

    The ChiSurf/Margarita ``.bur`` format writes interleaved all-zero rows for
    compatibility. Those rows must remain in files, but they should not appear
    in tables, histograms, or GMM inputs.
    """
    names = column_names(df)
    if row_count(df) == 0:
        return df
    if "Number of Photons" in names:
        photons = np.nan_to_num(numeric_column(df, "Number of Photons"))
        return take_where(df, photons > 0)
    if {"Number of Photons (red)", "Number of Photons (green)"} <= set(names):
        red = np.nan_to_num(numeric_column(df, "Number of Photons (red)"))
        green = np.nan_to_num(numeric_column(df, "Number of Photons (green)"))
        return take_where(df, (red + green) > 0)
    # No photon-count column: a row is a separator when every numeric column of
    # it is zero.
    numeric = [np.nan_to_num(numeric_column(df, n)) for n in names]
    numeric = [v for v in numeric if np.isfinite(v).any()]
    if not numeric:
        return df
    return take_where(df, ~np.all(np.vstack(numeric) == 0, axis=0))


def combine_ui_dataframes(frames: Iterable):
    """Stack the GUI tables, or ``None`` when there are none."""
    frames = list(frames)
    if not frames:
        return None
    return concat_stores(frames)


def analyze_file_for_wizard(
    path: str | Path,
    wizard: Any,
    output_dir: str | Path | None = None,
) -> Any:
    """Run the shared Burst Selection API for one file using wizard settings."""
    settings = analysis_settings_from_wizard(wizard)
    return analyze_file(
        path,
        settings=settings,
        filetype=None,
        windows=wizard.burst_finder.windows,
        detectors=wizard.burst_finder.detectors,
        output_dir=output_dir,
    )


def gmm_settings_from_wizard(wizard: Any) -> dict[str, Any]:
    """Return the GUI GMM settings dictionary."""
    return dict(wizard.gmm_settings)


def selected_histogram_data(current_df, selected_feature: str) -> np.ndarray:
    """Return numeric histogram data for the selected GUI feature."""
    if selected_feature == PROXIMITY_RATIO_COLUMN:
        data = proximity_ratio_from_frame(current_df)
        if data is not None:
            return data[np.isfinite(data)]
    data = numeric_column(burst_rows_for_display(current_df), selected_feature)
    return data[np.isfinite(data)]
