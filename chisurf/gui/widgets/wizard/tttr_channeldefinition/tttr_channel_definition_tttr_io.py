import logging
import os
import tempfile

import numpy as np
import tttrlib
from emtk.i18n import tr

from chisurf.gui import dialogs

logger = logging.getLogger(__name__)

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QFileDialog, QLineEdit, QMessageBox

from chisurf.core.fio import write_vv_vh
from chisurf.core.fio.fluorescence.bhfiles import BeckerHicklSetReader
from chisurf.gui.widgets.staged_loading import load_with_progress

from .tttr_detector_setups import load_detector_setups
from chisurf.core.data_io.detector_setups import save_detector_setups


def _create_gfactor_host(parent=None, on_close=None):
    """Host the existing native calculator for a legacy detector setup caller."""
    from chisurf.plugins.vv_vh_g_factor.gui.app import create_host

    return create_host(parent=parent, on_close=on_close)


def _publish_gfactor_result(page, model, detector_info, client=None):
    """Persist one valid native result using the detector's context and model metadata."""
    if model is None or model.g_factor is None or not np.isfinite(model.g_factor) or model.g_factor <= 0:
        return False
    if getattr(page, "read_only", False) or not page.detectors_form.isEnabled():
        return False
    row = detector_info["row"]
    name = detector_info["name"]
    item = page.detectors_form.item(row, 0)
    if item is None or item.text().strip() != name:
        raise ValueError(tr("The calibrated detector is no longer the selected row."))
    prior = []
    for column in (4, 5):
        editor = page.detectors_form.cellWidget(row, column)
        try:
            value = float(editor.text()) if editor else 0.0
        except ValueError:
            value = 0.0
        prior.append(value)
    parameters = model.detector_parameters(
        prior_l1=prior[0], prior_l2=prior[1],
        micro_time_resolution=getattr(page, "effective_micro_time_resolution", None),
    )
    from chisurf.core.fio.setup_store import resolve_active_user_id
    from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient

    client = client or VvVhGFactorClient()
    archived = client.archive_g_factor(
        file_path=model.fast_file, parameters=parameters, active_user=resolve_active_user_id()
    )
    if not isinstance(archived, dict) or not archived.get("ok", True) or not archived.get("calibration_id"):
        error = archived.get("error") if isinstance(archived, dict) else None
        raise ValueError(error or tr("Calibration archival returned no identifier."))
    page._set_g_factor_programmatically(
        row, f"{model.g_factor:.3f}", archived.get("reference_decay_id"),
        archived["calibration_id"], l1=f"{parameters['l1']:.5f}", l2=f"{parameters['l2']:.5f}",
    )
    limits = sorted(int(float(value)) for value in model.region)
    range_text = f"{limits[0]}-{limits[1]}"
    editor = page.detectors_form.cellWidget(row, 6)
    if editor is None:
        editor = QLineEdit(range_text)
        page.detectors_form.setCellWidget(row, 6, editor)
    else:
        editor.setText(range_text)
    if page.current_setup_name:
        data = page.get_settings()
        setups = load_detector_setups(page.current_setups_file)
        existing = setups.setdefault("setups", {}).get(page.current_setup_name, {})
        for key, value in data.items():
            if key == "detectors":
                for detector, info in value.items():
                    detectors = existing.setdefault("detectors", {})
                    if isinstance(detectors.get(detector), dict):
                        detectors[detector].update(info)
                    else:
                        detectors[detector] = info
            else:
                existing[key] = value
        setups["setups"][page.current_setup_name] = existing
        setups["last_used"] = page.current_setup_name
        save_detector_setups(setups, page.current_setups_file)
    message = tr("G-Factor calculated: {g:.4f}\nUpdated G-Factor for detector: {name}\nG-Factor Channels: {range_text}\n").format(g=model.g_factor, name=name, range_text=range_text)
    message += (tr("Setup '{name}' saved automatically.").format(name=page.current_setup_name)
                if page.current_setup_name else tr("No setup was selected, so changes were not saved automatically."))
    dialogs.information(page, tr("Success"), message)
    return True


def _apply_setup_lut_to_tttr(page, tttr) -> bool:
    """Apply the page's per-channel LUT + shifts to *tttr* in place when enabled.

    Returns ``True`` if a LUT was applied. Uses tttrlib's native
    ``apply_channel_luts`` / ``apply_luts_and_shifts`` with the same fixed dither
    seed as the reading seam, so the preview matches production reads.
    """
    try:
        from chisurf.core.fio.staging import apply_setup_lut

        return apply_setup_lut(
            tttr,
            getattr(page, "_channel_luts", None),
            getattr(page, "_channel_shifts", None),
            apply_lut=bool(getattr(page, "_apply_lut", False)),
        )
    except Exception as exc:  # pragma: no cover - best-effort preview
        logger.debug("Applying setup LUT to preview failed: %s", exc)
        return False


def _update_microtime_preview(page, tttr, file_path=None):
    """Feed the page's micro-time preview with the data's decay histogram.

    Extracts both the full (all-channel) histogram and per-routing-channel
    histograms so the preview can show individual routing channel decays
    and persist them separately for downstream detector splitting.

    Parameters
    ----------
    page : DetectorWizardPage
        The wizard page whose preview plot to update.
    tttr : tttrlib.TTTR
        The loaded TTTR data.
    file_path : str or None
        Source file path; stored with the histogram for persistence.
    """
    setter = getattr(page, "set_microtime_data", None)
    if not callable(setter):
        return
    # Apply the setup's TAC-linearization LUT so the preview reflects the
    # correction the user configured in the LUT-handling box (else the decay
    # shown here is raw and ignores the LUT). Mutates the local ``tttr``.
    _apply_setup_lut_to_tttr(page, tttr)
    try:
        hist, _ = tttr.get_microtime_histogram(1)
        setter(np.asarray(hist, dtype=float), file_path=file_path)
    except Exception as exc:  # pragma: no cover - preview is best-effort
        logger.debug("Micro-time preview update failed: %s", exc)
        return

    # Extract per-routing-channel microtime histograms
    per_channel_setter = getattr(page, "set_microtime_per_channel_data", None)
    if not callable(per_channel_setter):
        return
    try:
        used_channels = sorted(int(c) for c in tttr.get_used_routing_channels())
        per_channel = {}
        for ch in used_channels:
            ch_hist, _ = tttr.get_microtime_histogram(1, [ch])
            per_channel[ch] = np.asarray(ch_hist, dtype=float)
        per_channel_setter(per_channel, file_path=file_path)
    except Exception as exc:
        logger.debug("Per-channel microtime extraction failed: %s", exc)


def _auto_save_decay_to_setup(page):
    """Persist decay data to the current setup so it survives widget restart."""
    if not page.current_setup_name:
        return
    try:
        data = page.get_settings()
        decay = data.get("_microtime_decay")
        per_ch = data.get("_microtime_per_channel_decay")
        if not decay and not per_ch:
            return
        setups = load_detector_setups(page.current_setups_file)
        setups.setdefault("setups", {})
        if page.current_setup_name in setups["setups"]:
            existing = setups["setups"][page.current_setup_name]
            if decay:
                existing["_microtime_decay"] = decay
            if per_ch:
                existing["_microtime_per_channel_decay"] = per_ch
            setups["setups"][page.current_setup_name] = existing
        else:
            setups["setups"][page.current_setup_name] = data
        save_detector_setups(setups, page.current_setups_file)
    except Exception as exc:
        logger.debug("Auto-save decay to setup failed: %s", exc)


def read_from_tttr_file(page):
    path, _ = QFileDialog.getOpenFileName(
        page,
        "Open TTTR or SPC File",
        "",
        "All Files (*);;Photon data (*.pto *.ptu *.ht3 *.pt3 *.spc *.set);;"
        "Photon container (*.pto);;TTTR Files (*.ptu *.ht3 *.pt3);;"
        "SPC Files (*.spc *.set)",
    )
    if not path:
        return

    try:
        if path.lower().endswith(".set"):
            reader = BeckerHicklSetReader(path)
            micro_time_res = reader.micro_time_resolution
            if micro_time_res is not None:
                page.micro_time_le.setText(str(micro_time_res * 1000.0))
            page._update_effective_resolution()
            logger.info("Successfully read microtime calibration from SET file: %s", path)
            _auto_save_decay_to_setup(page)
        elif path.lower().endswith(".spc"):
            tttr = load_with_progress(page, tttrlib.TTTR, path, title="Reading calibration")
            if tttr is None:
                return
            header = tttr.get_header()
            page.macro_time_le.setText(str(header.macro_time_resolution * 1e9))
            page.micro_time_le.setText(str(header.micro_time_resolution * 1e12))
            page._update_effective_resolution()
            _update_microtime_preview(page, tttr, file_path=path)
            logger.info("Successfully read macrotime calibration from SPC file: %s", path)
            _auto_save_decay_to_setup(page)
        else:
            tttr = load_with_progress(page, tttrlib.TTTR, path, title="Reading calibration")
            if tttr is None:
                return
            if len(tttr) == 0:
                raise ValueError("File is not a supported TTTR file format or contains no events.")
            header = tttr.get_header()
            page.macro_time_le.setText(str(header.macro_time_resolution * 1e9))
            page.micro_time_le.setText(str(header.micro_time_resolution * 1e12))
            page._update_effective_resolution()
            _update_microtime_preview(page, tttr, file_path=path)
            logger.info("Successfully read calibrations from TTTR file: %s", path)
            _auto_save_decay_to_setup(page)

    except Exception as e:
        dialogs.error(page, "Error", f"Failed to read file: {e}")


def on_calc_g_factor(page, row=None):
    if getattr(page, "read_only", False) or not page.detectors_form.isEnabled():
        return
    if row is None:
        selected_rows = page.detectors_form.selectedIndexes()
        if not selected_rows:
            dialogs.warning(page, "Warning", "Please select a detector row first.")
            return
        row = selected_rows[0].row()

    settings = page.get_settings()
    settings["detectors"]

    path, _ = QFileDialog.getOpenFileName(
        page, "Open TTTR File for G-Factor Calculation", "", "All Files (*)"
    )
    if not path:
        return

    try:
        tttr = load_with_progress(page, tttrlib.TTTR, path, title="Reading TTTR file")
        if tttr is None:
            return
        if len(tttr) == 0:
            raise ValueError("File is not a supported TTTR file format or contains no events.")
        micro_time_binning = int(page.micro_binning_combo.currentText())

        selected_detector = page.detectors_form.item(row, 0).text().strip()
        channels_text = page.detectors_form.cellWidget(row, 1).text()
        all_channels = list(map(int, channels_text.split(",")))

        parallel_channels = all_channels[::2]
        perpendicular_channels = all_channels[1::2]

        if len(all_channels) < 2 or len(parallel_channels) == 0 or len(perpendicular_channels) == 0:
            dialogs.warning(
                page,
                "Warning",
                "Selected detector must contain at least two routing channels (parallel and perpendicular) to calculate G-Factor.",
            )
            return

        page.selected_detector = {
            "row": row,
            "name": selected_detector,
            "parallel_channels": parallel_channels,
            "perpendicular_channels": perpendicular_channels,
        }

        parallel_hist, _ = tttr.get_microtime_histogram(micro_time_binning, parallel_channels)
        perpendicular_hist, _ = tttr.get_microtime_histogram(
            micro_time_binning, perpendicular_channels
        )

        parallel_nonzero = np.where(parallel_hist > 0)[0]
        perpendicular_nonzero = np.where(perpendicular_hist > 0)[0]

        if len(parallel_nonzero) > 0 and len(perpendicular_nonzero) > 0:
            start_idx = min(parallel_nonzero[0], perpendicular_nonzero[0])
            end_idx = max(parallel_nonzero[-1], perpendicular_nonzero[-1]) + 1
            parallel_hist_trimmed = parallel_hist[start_idx:end_idx]
            perpendicular_hist_trimmed = perpendicular_hist[start_idx:end_idx]
        else:
            parallel_hist_trimmed = parallel_hist
            perpendicular_hist_trimmed = perpendicular_hist

        fd, vv_vh_file = tempfile.mkstemp(suffix=".dat")
        os.close(fd)
        vv_vh_data = np.concatenate([parallel_hist_trimmed, perpendicular_hist_trimmed])
        write_vv_vh(filename=vv_vh_file, data=vv_vh_data)

        # Check for headless calculation option
        gf_widget = page.detectors_form.cellWidget(row, 6)
        gf_range_text = gf_widget.text().strip() if gf_widget else ""
        has_valid_range = False
        s, e = 0, 0
        if gf_range_text:
            try:
                parts = gf_range_text.replace(" ", "").split("-")
                if len(parts) == 2:
                    s = int(float(parts[0]))
                    e = int(float(parts[1]))
                    if e < s:
                        s, e = e, s
                    has_valid_range = True
            except Exception:
                pass

        run_headless = False
        if has_valid_range:
            reply = dialogs.question(
                page,
                "Headless Calculation",
                f"A G-factor channel range '{gf_range_text}' is already defined.\n"
                "Would you like to run the calculation headlessly without opening the interactive GUI?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Cancel:
                return
            run_headless = reply == QMessageBox.Yes

        if run_headless:
            from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient
            from chisurf.plugins.vv_vh_g_factor.gui.model import GFactorModel

            client = VvVhGFactorClient()
            model = GFactorModel()
            model.load(vv_vh_file)
            model.region = [float(s), float(e)]
            model.fp_dt_ns = float(page.effective_micro_time_resolution) * 1e-3
            model.compute(client)
            _publish_gfactor_result(page, model, {"row": row, "name": selected_detector}, client)
            return

        detector_info = {"row": row, "name": selected_detector}

        def finished(model):
            try:
                _publish_gfactor_result(page, model, detector_info)
            except Exception as exc:
                logger.warning("Failed to publish native G-factor calibration: %s", exc)
                dialogs.error(page, tr("Error"), tr("Failed to save G-Factor calibration: {error}").format(error=exc))

        host = _create_gfactor_host(parent=page, on_close=finished)
        host.setWindowFlags(host.windowFlags() | Qt.Window)
        host.setWindowModality(Qt.ApplicationModal)
        calculator = host.control
        calculator.model.fp_dt_ns = float(page.effective_micro_time_resolution) * 1e-3
        page.g_factor_calculator = host
        page.vv_vh_file = vv_vh_file
        # File reading/calculation uses the same native model/client as its own UI.
        calculator.model.load(vv_vh_file)
        if has_valid_range:
            calculator.model.region = [float(s), float(e)]
        calculator.model.compute(calculator.client)
        calculator.settings_signature = calculator.fingerprint()
        calculator.plot_signature = None
        host.resize(1600, 1000)
        host.show()

    except Exception as e:
        dialogs.error(page, "Error", f"Failed to calculate G-Factor: {str(e)}")
