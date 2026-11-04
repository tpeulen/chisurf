"""Comprehensive unified Settings dock for hardware, camera, simulation, and profiles.

Follows the ChiSurf settings architecture (categorized groups, searchable fields,
and interactive JSON source editor with bidirectional hardware synchronization).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.i18n import tr

from chisurf.emtk.typed_field import parse_number, typed_number_field
from chisurf.plugins.core.acq.live import devices
from chisurf.plugins.core.acq.live import settings_file


class SettingsPanel:
    """Unified Settings dock for Record.

    Combines:
    - TCSPC Hardware (device, sync, stop channels, timing, markers)
    - Camera & Video (source address, discovery, matrix vision, preview gain, recording)
    - Sample & Realism (donor/acceptor only, bleaching, background, crosstalk, IRF, dead time)
    - Settings Profiles & Storage documents
    - Interactive JSON source editor with live validation & hardware application
    """

    CATEGORIES = (
        ("all", "All Settings", "View and edit all acquisition parameters together"),
        ("tcspc", "📟 TCSPC Hardware", "Device index, routing mode, and reference clock"),
        ("lasers", "🔦 Lasers", "Every laser system connected to this computer; pick which one this session drives"),
        ("sync_inputs", "⚡ Sync & Inputs", "Laser sync trigger channel and detector stop channel CFD parameters"),
        ("timing", "⏱ Timing & Delays", "Time binning resolution, sync offset, and stop channel delays"),
        ("scanner", "🪞 Scanner & Markers", "Fast-FLIM raster markers and marker holdoff times"),
        ("camera", "📹 Camera & Video", "Camera selection, display gain, recording file, and capture controls"),
        ("realism", "🧪 Realism & Simulation", "Confocal realism: donor/acceptor only, bleaching, background, and IRF"),
        ("storage", "📁 Profiles & Storage", "Acquisition profiles, PTU imports, and export to disk"),
        ("driver", "🛠 Low-Level Driver", "Native hardware driver registers and device-specific parameters"),
        ("json", "💻 JSON Source Editor", "Direct interactive JSON document editor with hardware synchronization"),
    )

    def __init__(self, model, app=None):
        self.model = model
        self.app = app
        self.category = "all"
        self.group_filter = ""
        self.source_mode = False
        self.setting_filter = ""
        self._json_text = ""
        self._json_dirty = False
        self._json_error = ""
        self._status_msg = ""
        self._drafts: dict[str, str] = {}
        self._number_buffers: dict[str, str] = {}
        self._number_paths: dict[str, tuple[str, ...]] = {}
        self._invalid_fields: dict[str, str] = {}
        self.item_rects: dict[str, tuple] = {}

    # -- data construction & serialization -------------------------------------------------------
    def _build_grouped_data(self) -> dict[str, Any]:
        """Build the structured configuration dictionary from current model, device, and camera."""
        m = self.model
        n_ch = 4
        if getattr(m, "device", None) is not None:
            try:
                n_ch = m.device.information().number_of_channels
            except Exception:
                pass

        vals = getattr(m, "device_values", {})

        # 1. Device
        dev = {
            "index": str(getattr(m, "device_index", "") or "Simulation"),
            "mode": str(vals.get("mode", "T3")),
            "reference_clock": str(vals.get("reference_clock", "Internal")),
        }

        # 2. Sync
        sync = {
            "divider": int(vals.get("sync_divider", 1)),
            "level_mv": int(vals.get("sync_level_mv", vals.get("sync_cfd_discr_mv", -50))),
            "zero_cross_mv": int(vals.get("sync_cfd_zerox_mv", 0)),
            "edge": int(vals.get("sync_edge", 0)),
            "offset_ps": int(vals.get("sync_offset_ps", 0)),
        }

        # 3. Inputs
        inputs = {}
        for i in range(n_ch):
            inputs[f"channel_{i}"] = {
                "enabled": bool(vals.get(f"input_enable[{i}]", True)),
                "level_mv": int(vals.get(f"input_level_mv[{i}]", vals.get(f"input_cfd_discr_mv[{i}]", -50))),
                "zero_cross_mv": int(vals.get(f"input_cfd_zerox_mv[{i}]", 0)),
                "edge": int(vals.get(f"input_edge[{i}]", 0)),
                "offset_ps": int(vals.get(f"input_offset_ps[{i}]", 0)),
                "dead_time_ps": int(vals.get(f"input_dead_time_ps[{i}]", 800)),
            }

        # 4. Timing
        timing = {
            "binning": int(vals.get("binning", 0)),
            "offset_ns": int(vals.get("offset_ns", 0)),
            "resolution_ps": float(4.0 * (1 << int(vals.get("binning", 0)))),
        }

        # 5. Scanner
        scanner = {
            "raster_start_marker": int(vals.get("raster_start_marker", 1)),
            "raster_stop_marker": int(vals.get("raster_stop_marker", 2)),
            "marker_holdoff_ns": int(vals.get("marker_holdoff_ns", 0)),
        }

        # 6. Camera (relocated settings)
        cam = {}
        if self.app and hasattr(self.app, "video") and self.app.video:
            v = self.app.video
            cam = {
                "address": str(getattr(v, "address", "0")),
                "display_gain": float(getattr(v, "display_gain", 1.0)),
                "output": str(getattr(v, "output", "capture.tif")),
                "fps": float(getattr(v, "fps", 30.0)),
            }

        # 7. Realism (relocated complicated simulation settings)
        realism = {
            "preset": str(getattr(m, "realism_preset", "realistic")),
            "donor_only": float(getattr(m, "sim_p_d_only", 0.05)),
            "acceptor_only": float(getattr(m, "sim_p_a_only", 0.05)),
            "bleaching": float(getattr(m, "sim_p_bleach", 0.02)),
            "crosstalk": float(getattr(m, "sim_p_crosstalk", 0.03)),
            "background_donor_cps": float(getattr(m, "sim_bg_d_cps", 1200.0)),
            "background_acceptor_cps": float(getattr(m, "sim_bg_a_cps", 800.0)),
            "irf_fwhm_ns": float(getattr(m, "sim_irf_fwhm_ns", 0.25)),
            "dead_time_ns": float(getattr(m, "sim_dead_time_ns", 0.8)),
            "drift_per_min": float(getattr(m, "sim_drift_rate", 0.0)),
        }

        # 8. Storage & Profiles
        storage = {
            "profile": str(getattr(m, "settings_address", "") or "default"),
            "output_directory": str(getattr(m, "output_dir", "")),
            "store_mode": str(getattr(m, "recording_store", "link")),
        }

        # Extra native driver keys
        handled_prefixes = (
            "input_", "sync_", "binning", "offset_ns", "mode", "reference_clock",
            "raster_", "marker_"
        )
        extra_driver = {k: v for k, v in vals.items() if not any(k.startswith(p) for p in handled_prefixes)}

        data = {
            "lasers": {
                "kind": str(getattr(m, "laser_kind", "auto")),
                "address": str(getattr(m, "laser_address", "") or ""),
                "connected": bool(m.laser_connected),
            },
            "device": dev,
            "sync": sync,
            "inputs": inputs,
            "timing": timing,
            "scanner": scanner,
            "camera": cam,
            "realism": realism,
            "storage": storage,
        }
        if extra_driver:
            data["hardware_driver"] = extra_driver

        return data

    def _apply_grouped_data(self, data: dict[str, Any]) -> None:
        """Apply structured configuration dictionary back to model, device, and camera."""
        m = self.model
        updates: dict[str, Any] = {}

        # 0. Lasers (the chooser's scalars: which laser system this session drives)
        lasers = data.get("lasers", {})
        if isinstance(lasers, dict) and "kind" in lasers:
            kind = str(lasers["kind"])
            address = str(lasers.get("address", "") or "")
            if kind != m.laser_kind or address != (m.laser_address or ""):
                if getattr(m, "running", False):
                    self._status_msg = tr("A recording is running")
                elif getattr(m, "connecting", False):
                    self._status_msg = tr("A settings file is loading")
                else:
                    if m.laser_connected:
                        m.disconnect_laser()
                    m.laser_kind, m.laser_address = kind, address
                    m._sepia_at = m._cmc_at = -1e9
                    if m.connect_laser():
                        self._status_msg = m.laser_text
                    else:
                        self._status_msg = m.laser_detail or tr("Cannot connect the laser")

        # 1. Device
        dev = data.get("device", {})
        if "mode" in dev:
            updates["mode"] = dev["mode"]
        if "reference_clock" in dev:
            updates["reference_clock"] = dev["reference_clock"]
        if "index" in dev and hasattr(m, "device_index"):
            m.device_index = dev["index"]

        # 2. Sync
        sync = data.get("sync", {})
        if "divider" in sync:
            updates["sync_divider"] = int(sync["divider"])
        if "level_mv" in sync:
            updates["sync_level_mv"] = int(sync["level_mv"])
            updates["sync_cfd_discr_mv"] = int(sync["level_mv"])
        if "zero_cross_mv" in sync:
            updates["sync_cfd_zerox_mv"] = int(sync["zero_cross_mv"])
        if "edge" in sync:
            updates["sync_edge"] = int(sync["edge"])
        if "offset_ps" in sync:
            updates["sync_offset_ps"] = int(sync["offset_ps"])

        # 3. Inputs
        inputs = data.get("inputs", {})
        for ch_key, ch_vals in inputs.items():
            if not isinstance(ch_vals, dict):
                continue
            idx_str = str(ch_key).replace("channel_", "").replace("channel", "").strip()
            if not idx_str.isdigit():
                continue
            idx = int(idx_str)
            if "enabled" in ch_vals:
                updates[f"input_enable[{idx}]"] = bool(ch_vals["enabled"])
            if "level_mv" in ch_vals:
                updates[f"input_level_mv[{idx}]"] = int(ch_vals["level_mv"])
                updates[f"input_cfd_discr_mv[{idx}]"] = int(ch_vals["level_mv"])
            if "zero_cross_mv" in ch_vals:
                updates[f"input_cfd_zerox_mv[{idx}]"] = int(ch_vals["zero_cross_mv"])
            if "edge" in ch_vals:
                updates[f"input_edge[{idx}]"] = int(ch_vals["edge"])
            if "offset_ps" in ch_vals:
                updates[f"input_offset_ps[{idx}]"] = int(ch_vals["offset_ps"])
            if "dead_time_ps" in ch_vals:
                updates[f"input_dead_time_ps[{idx}]"] = int(ch_vals["dead_time_ps"])

        # 4. Timing
        timing = data.get("timing", {})
        if "binning" in timing:
            updates["binning"] = int(timing["binning"])
        if "offset_ns" in timing:
            updates["offset_ns"] = int(timing["offset_ns"])

        # 5. Scanner
        scanner = data.get("scanner", {})
        if "raster_start_marker" in scanner:
            updates["raster_start_marker"] = int(scanner["raster_start_marker"])
        if "raster_stop_marker" in scanner:
            updates["raster_stop_marker"] = int(scanner["raster_stop_marker"])
        if "marker_holdoff_ns" in scanner:
            updates["marker_holdoff_ns"] = int(scanner["marker_holdoff_ns"])

        # 6. Extra driver parameters
        extra = data.get("hardware_driver", {})
        if isinstance(extra, dict):
            updates.update(extra)

        # 7. Camera parameters
        cam = data.get("camera", {})
        if self.app and hasattr(self.app, "video") and self.app.video:
            v = self.app.video
            if "address" in cam:
                v.address = str(cam["address"])
            if "display_gain" in cam:
                v.display_gain = float(cam["display_gain"])
            if "output" in cam:
                v.output = str(cam["output"])
            if "fps" in cam:
                v.fps = float(cam["fps"])

        # 8. Realism parameters
        realism = data.get("realism", {})
        if "preset" in realism and hasattr(m, "realism_preset"):
            m.realism_preset = str(realism["preset"])
        if "donor_only" in realism and hasattr(m, "sim_p_d_only"):
            m.sim_p_d_only = float(realism["donor_only"])
        if "acceptor_only" in realism and hasattr(m, "sim_p_a_only"):
            m.sim_p_a_only = float(realism["acceptor_only"])
        if "bleaching" in realism and hasattr(m, "sim_p_bleach"):
            m.sim_p_bleach = float(realism["bleaching"])
        if "crosstalk" in realism and hasattr(m, "sim_p_crosstalk"):
            m.sim_p_crosstalk = float(realism["crosstalk"])
        if "background_donor_cps" in realism and hasattr(m, "sim_bg_d_cps"):
            m.sim_bg_d_cps = float(realism["background_donor_cps"])
        if "background_acceptor_cps" in realism and hasattr(m, "sim_bg_a_cps"):
            m.sim_bg_a_cps = float(realism["background_acceptor_cps"])
        if "irf_fwhm_ns" in realism and hasattr(m, "sim_irf_fwhm_ns"):
            m.sim_irf_fwhm_ns = float(realism["irf_fwhm_ns"])
        if "dead_time_ns" in realism and hasattr(m, "sim_dead_time_ns"):
            m.sim_dead_time_ns = float(realism["dead_time_ns"])
        if "drift_per_min" in realism and hasattr(m, "sim_drift_rate"):
            m.sim_drift_rate = float(realism["drift_per_min"])

        # 9. Storage parameters
        storage = data.get("storage", {})
        if "profile" in storage and hasattr(m, "settings_address"):
            m.settings_address = str(storage["profile"])
        if "store_mode" in storage and hasattr(m, "recording_store"):
            m.recording_store = str(storage["store_mode"])

        # Apply TCSPC parameters
        if not hasattr(m, "device_values"):
            m.device_values = {}
        m.device_values.update(updates)

        if hasattr(m, "update_device_parameter"):
            for k, v in updates.items():
                m.update_device_parameter(k, v)
        elif getattr(m, "device", None) is not None and not getattr(m, "running", False):
            try:
                devices.apply_settings(m.device, updates)
                m.device_values = dict(m.device.settings())
                if getattr(m, "device_form", None) is not None:
                    m.device_form.update_values(m.device_values)
            except Exception:
                pass

    def _sync_rate(self) -> tuple[float, str, str]:
        m = self.model
        if hasattr(m, "sync_rate_display"):
            return m.sync_rate_display()
        rate = 0.0
        if getattr(m, "device_rates_hz", None):
            rate = float(m.device_rates_hz[0])
        elif getattr(m, "source_kind", "") == "simulator":
            try:
                n_micro, res = m._clock()
                rate = 1.0 / (n_micro * res) if (n_micro * res) > 0 else 80e6
            except Exception:
                rate = 80e6
        if rate >= 1e6:
            return rate, f"{rate / 1e6:.2f} MHz", "ok"
        elif rate >= 1e3:
            return rate, f"{rate / 1e3:.1f} kHz", "warn"
        elif rate > 0:
            return rate, f"{rate:.0f} Hz", "warn"
        return 0.0, "0 Hz (No Sync)", "none"

    def _channel_list(self) -> list[dict]:
        m = self.model
        if hasattr(m, "channel_info_list"):
            return m.channel_info_list()
        n_ch = 4
        if getattr(m, "device", None) is not None:
            try:
                n_ch = m.device.information().number_of_channels
            except Exception:
                pass
        rates = m.device_rates_hz[1:] if len(getattr(m, "device_rates_hz", [])) > 1 else []
        out = []
        for i in range(n_ch):
            rate_hz = float(rates[i]) if i < len(rates) else 0.0
            en = bool(self.model.device_values.get(f"input_enable[{i}]", True) if hasattr(self.model, "device_values") else True)
            lvl = int(self.model.device_values.get(f"input_level_mv[{i}]", -50) if hasattr(self.model, "device_values") else -50)
            zx = int(self.model.device_values.get(f"input_cfd_zerox_mv[{i}]", 0) if hasattr(self.model, "device_values") else 0)
            off = int(self.model.device_values.get(f"input_offset_ps[{i}]", 0) if hasattr(self.model, "device_values") else 0)
            dt = int(self.model.device_values.get(f"input_dead_time_ps[{i}]", 800) if hasattr(self.model, "device_values") else 800)
            rate_str = f"{rate_hz / 1e3:.1f} kHz" if rate_hz >= 1e3 else (f"{rate_hz:.0f} Hz" if rate_hz > 0 else "0 Hz")
            out.append({
                "index": i,
                "name": f"Det {i}",
                "enabled": en,
                "rate_hz": rate_hz,
                "rate_str": rate_str,
                "overload": rate_hz > 1e6,
                "level_mv": lvl,
                "zero_cross_mv": zx,
                "offset_ps": off,
                "dead_time_ps": dt,
            })
        return out

    # -- drawing ---------------------------------------------------------------------------------
    def draw(self, width: float = 300.0) -> None:
        m = self.model
        if not getattr(m, "advanced", False):
            return

        avail = im.get_content_region_avail()
        avail_w = avail[0] if avail[0] > 0 else width

        # Header Title
        im.push_style_color(im.Col.TEXT, (0.15, 0.75, 0.90, 1.0))
        im.text(f"⚡ {tr('Settings — Hardware, Camera, Simulation & Acquisition')}")
        im.pop_style_color()
        im.separator()

        # Responsive sidebar width: room for groups list
        if avail_w >= 700.0:
            sidebar_w = 200.0
        elif avail_w >= 500.0:
            sidebar_w = 175.0
        else:
            sidebar_w = max(130.0, avail_w * 0.35)

        # 1. Left side: Groups / Destinations sidebar
        self._draw_groups_sidebar(sidebar_w)

        im.same_line()

        # 2. Right side: Settings content for the selected group
        self._draw_settings_content()

    def _draw_groups_sidebar(self, width: float) -> None:
        """Left side groups navigation matching ChiSurf Settings hub."""
        im.begin_child("##settings_groups_sidebar", (width, 0.0))
        changed, self.group_filter = im.begin_filtered_list(
            "groups_filter_list",
            self.group_filter,
            tr("Search groups..."),
            tooltip=tr("Filter the setting groups by name."),
        )
        filt = self.group_filter.strip().casefold()
        shown_count = 0
        for key, label, tip in self.CATEGORIES:
            if filt and filt not in label.casefold() and filt not in key.casefold():
                continue
            shown_count += 1
            is_active = (self.category == key)
            if is_active:
                im.push_style_color(im.Col.HEADER, (0.15, 0.55, 0.75, 1.0))
            if im.selectable(tr(label) + f"##grp_{key}", is_active, size=(0, 24)):
                self.category = key
                if key == "json":
                    self.source_mode = True
                    data = self._build_grouped_data()
                    self._json_text = json.dumps(data, indent=2)
                else:
                    self.source_mode = False
            im.set_item_tooltip(tr(tip))
            if is_active:
                im.pop_style_color()
        if shown_count == 0:
            im.text_disabled(tr("No matching groups."))
        im.end_filtered_list()
        im.end_child()

    def _draw_category_selector(self, width: float) -> None:
        """Compatibility wrapper for category selector."""
        self._draw_groups_sidebar(width)

    def _draw_settings_content(self) -> None:
        """Right side settings content area for the active group."""
        im.begin_child("##settings_content_pane", (0.0, 0.0))

        # Mode Selector: Grouped Settings vs JSON Editor toggle
        was_source = self.source_mode or (self.category == "json")
        _, new_source = im.checkbox(tr("Edit source (JSON)"), was_source)
        im.set_item_tooltip(tr("Switch between structured grouped settings and the complete JSON source editor."))

        if was_source and not new_source:
            # Switching from JSON to Grouped: validate & parse
            try:
                parsed = json.loads(self._json_text)
                self._apply_grouped_data(parsed)
                self._json_error = ""
                self._status_msg = tr("Applied JSON settings to hardware.")
                self.source_mode = False
                if self.category == "json":
                    self.category = "all"
            except Exception as exc:
                self._json_error = f"{tr('Invalid JSON')}: {exc}"
                self.source_mode = True
        elif not was_source and new_source:
            # Switching from Grouped to JSON: update text
            data = self._build_grouped_data()
            self._json_text = json.dumps(data, indent=2)
            self._json_error = ""
            self._status_msg = ""
            self.source_mode = True
            self.category = "json"

        # Right pane toolbar: Profiles/Document picker, Hardware presets, Status badges
        avail_w = im.get_content_region_avail()[0]
        self._draw_document_toolbar(avail_w)
        im.spacing()
        self._draw_presets_row(avail_w)
        im.spacing()
        self._draw_live_status_bar(avail_w)
        im.separator()

        # Draw active mode
        if self.source_mode or self.category == "json":
            self._draw_json_editor(avail_w)
        else:
            self._draw_grouped_settings(avail_w)

        im.end_child()

    def _draw_document_toolbar(self, width: float) -> None:
        m = self.model

        opts = m.settings_options() if hasattr(m, "settings_options") else []
        cur_addr = getattr(m, "settings_address", "")
        cur_label = next((lbl for addr, lbl in opts if addr == cur_addr), cur_addr or tr("Choose settings or a measurement"))
        if im.begin_combo(tr("From##phacq_from"), cur_label):
            for addr, lbl in opts:
                is_sel = (addr == cur_addr)
                if im.selectable(lbl, is_sel):
                    m.settings_address = addr
                    if hasattr(m, "settings_chosen"):
                        m.settings_chosen()
                if is_sel:
                    im.set_item_default_focus()
            im.end_combo()
        im.set_item_tooltip(tr("Select an acquisition settings file, profile, or measurement PTU."))

        if im.button(f"⚙ {tr('Load')}"):
            if hasattr(m, "load_settings"):
                m.load_settings()
            self._json_text = json.dumps(self._build_grouped_data(), indent=2)
            self._status_msg = tr("Loaded profile settings onto hardware.")
        im.set_item_tooltip(tr("Load the selected acquisition settings document onto hardware."))

        im.same_line()
        if im.button("…"):
            if hasattr(m, "request_settings_file"):
                m.request_settings_file()
        im.set_item_tooltip(tr("Browse for a PTU, PTO, or JSON acquisition settings file."))

        im.same_line()
        if im.button(tr("From Meas.")):
            if hasattr(m, "use_measurement_settings"):
                m.use_measurement_settings()
        im.set_item_tooltip(tr("Recover settings from the chosen measurement file header."))

        im.same_line()
        if im.button(tr("Validate")):
            self.validate()
        im.set_item_tooltip(tr("Validate JSON syntax and parameter boundaries."))

        im.same_line()
        if im.button(f"💾 {tr('Save as…')}"):
            if hasattr(m, "save_settings_as"):
                m.save_settings_as()
        im.set_item_tooltip(tr("Save current hardware, laser, and experiment settings to a JSON file."))

        status_name = getattr(m, "settings_name", "") or getattr(m, "settings_text", tr("No settings loaded"))
        detail = getattr(m, "settings_detail", "")
        im.text_disabled(f"{tr('Active')}: {status_name}")
        if detail:
            im.set_item_tooltip(detail)

    def _draw_presets_row(self, width: float) -> None:
        m = self.model
        im.text(f"{tr('Hardware Presets')}:")
        if im.button(tr("NIM (-50mV)")):
            if hasattr(m, "apply_device_preset"):
                m.apply_device_preset("nim")
            self._json_text = json.dumps(self._build_grouped_data(), indent=2)
            self._status_msg = tr("Applied NIM preset (-50 mV, falling edge).")
        im.set_item_tooltip(tr("Standard NIM logic levels (-50 mV, falling edge) across all channels."))

        im.same_line()
        if im.button(tr("TTL (+1.5V)")):
            if hasattr(m, "apply_device_preset"):
                m.apply_device_preset("ttl")
            self._json_text = json.dumps(self._build_grouped_data(), indent=2)
            self._status_msg = tr("Applied TTL preset (+1.5 V, rising edge).")
        im.set_item_tooltip(tr("Standard TTL/CMOS logic levels (+1.5 V, rising edge) across all channels."))

        if width >= 380.0:
            im.same_line()
        if im.button(tr("SPAD (-80mV)")):
            if hasattr(m, "apply_device_preset"):
                m.apply_device_preset("spad")
            self._json_text = json.dumps(self._build_grouped_data(), indent=2)
            self._status_msg = tr("Applied SPAD preset (-80 mV, 800 ps dead time).")
        im.set_item_tooltip(tr("High-speed SPAD / PDM levels (-80 mV, 800 ps dead time)."))

        im.same_line()
        if im.button(tr("Zero Delays")):
            if hasattr(m, "apply_device_preset"):
                m.apply_device_preset("zero_offsets")
            self._json_text = json.dumps(self._build_grouped_data(), indent=2)
            self._status_msg = tr("Reset sync and channel delays to 0 ps.")
        im.set_item_tooltip(tr("Clear all channel offsets and sync delay to 0 ps."))

    def _draw_live_status_bar(self, width: float) -> None:
        rate_hz, rate_str, status = self._sync_rate()
        im.text(f"{tr('Sync')}:")
        im.same_line()
        if status == "ok":
            im.push_style_color(im.Col.TEXT, (0.2, 0.9, 0.4, 1.0))
            im.text(f"● {rate_str} ({tr('Sync OK')})")
            im.pop_style_color()
        elif status == "warn":
            im.push_style_color(im.Col.TEXT, (0.95, 0.75, 0.2, 1.0))
            im.text(f"▲ {rate_str} ({tr('Low')})")
            im.pop_style_color()
        else:
            im.push_style_color(im.Col.TEXT, (0.9, 0.3, 0.3, 1.0))
            im.text(f"⚠ {rate_str}")
            im.pop_style_color()

        channels = self._channel_list()
        overloaded = [ch["name"] for ch in channels if ch.get("overload")]
        if overloaded:
            im.same_line()
            im.push_style_color(im.Col.TEXT, (1.0, 0.25, 0.25, 1.0))
            im.text(f"⚠ {', '.join(overloaded)} >1 MHz!")
            im.pop_style_color()

        if self.app and hasattr(self.app, "video") and self.app.video:
            im.same_line()
            v = self.app.video
            is_cam_conn = getattr(v, "_connected", False) or (v.frame is not None)
            if is_cam_conn:
                im.push_style_color(im.Col.TEXT, (0.3, 0.9, 0.4, 1.0))
                im.text(f"● {tr('Camera Connected')}")
                im.pop_style_color()
            else:
                im.text_disabled(f"○ {tr('Camera Disconnected')}")

    # -- Mode 1: Grouped Settings View (ChiSurf Settings Architecture) ---------------------------
    def _draw_grouped_settings(self, width: float) -> None:
        data = self._build_grouped_data()
        indent = 12.0
        edited = False

        # Filter bar ("Find a setting")
        im.align_text_to_frame_padding()
        im.text_unformatted(tr("Find a setting"))
        im.same_line()
        _, self.setting_filter = im.begin_filtered_list(
            "settings_dock_body",
            self.setting_filter,
            tooltip=tr("Search setting names; matching entries retain parent section names."),
            height=-36.0,
        )

        def keys(value, depth=0):
            if isinstance(value, dict):
                for k, item in value.items():
                    if isinstance(item, dict):
                        yield from keys(item, depth + 1)
                    else:
                        yield depth, str(k)

        room = im.get_content_region_avail()[0]
        widest = max((im.calc_text_size(k)[0] + indent * d for d, k in keys(data)), default=80.0)
        column = min(widest + 16.0, max(120.0, room * 0.42))

        # Filter by selected category if not "all"
        target_sections = data
        if self.category in ("tcspc", "device"):
            target_sections = {"device": data.get("device", {})}
        elif self.category in ("sync_inputs", "sync", "inputs"):
            target_sections = {k: data[k] for k in ("sync", "inputs") if k in data}
        elif self.category == "timing":
            target_sections = {"timing": data.get("timing", {})}
        elif self.category == "scanner":
            target_sections = {"scanner": data.get("scanner", {})}
        elif self.category == "camera":
            target_sections = {"camera": data.get("camera", {})}
        elif self.category == "realism":
            target_sections = {"realism": data.get("realism", {})}
        elif self.category == "storage":
            target_sections = {"storage": data.get("storage", {})}
        elif self.category == "driver":
            target_sections = {"hardware_driver": data.get("hardware_driver", {})}

        def draw_values(value: dict[str, Any], prefix: tuple[str, ...] = ()) -> None:
            nonlocal edited
            for key, item in value.items():
                path = prefix + (key,)
                label = ".".join(map(str, path))

                if isinstance(item, dict):
                    if self.setting_filter:
                        draw_values(item, path)
                    else:
                        group_title = label
                        if label == "device":
                            group_title = f"⚙ {tr('device')} — TCSPC Hardware & Clock"
                        elif label == "sync":
                            group_title = f"⏱ {tr('sync')} — Laser Trigger Channel"
                        elif label == "inputs":
                            group_title = f"🔬 {tr('inputs')} — Detector Stop Channels"
                        elif label == "timing":
                            group_title = f"📏 {tr('timing')} — Binning & Global Offset"
                        elif label == "scanner":
                            group_title = f"🗺 {tr('scanner')} — Fast-FLIM Markers"
                        elif label == "camera":
                            group_title = f"📹 {tr('camera')} — Camera Source, Gain & Video"
                        elif label == "lasers":
                            group_title = f"🔦 {tr('lasers')} — Connected Laser Systems"
                        elif label == "realism":
                            group_title = f"🧪 {tr('realism')} — Instrument & Sample Realism"
                        elif label == "storage":
                            group_title = f"📁 {tr('storage')} — Profiles & Storage"
                        elif label == "hardware_driver":
                            group_title = f"🛠 {tr('hardware_driver')} — Native Driver Parameters"

                        opened = im.collapsing_header(group_title, open_=True)
                        im.set_item_tooltip(label)
                        if opened:
                            # Render dedicated action buttons for Camera under its section
                            if label == "camera" and self.app and hasattr(self.app, "video") and self.app.video:
                                self._draw_camera_actions()
                            elif label == "lasers":
                                self._draw_laser_devices()
                            elif label == "storage":
                                self._draw_storage_actions()
                            draw_values(item, path)
                    continue

                if self.setting_filter.casefold() not in label.casefold():
                    continue

                im.push_id(label)
                depth = len(prefix)
                if depth:
                    im.indent(indent * depth)
                im.align_text_to_frame_padding()
                im.text_unformatted(str(key))
                if depth:
                    im.unindent(indent * depth)
                im.set_item_tooltip(label)

                im.same_line(column)
                im.set_next_item_width(-1)

                changed = False
                new_val: Any = item

                if isinstance(item, bool):
                    changed, new_val = im.checkbox("##Value", item)
                elif isinstance(item, (int, float)):
                    self._number_paths[label] = path
                    new_val, problem = typed_number_field(
                        label, item, self._number_buffers, integer=isinstance(item, int)
                    )
                    changed = (new_val is not None)
                    if problem:
                        self._json_error = f"{label}: {problem}"
                else:
                    text = str(item)
                    changed, new_val = im.input_text("##Value", self._drafts.get(label, text))
                    if changed:
                        self._drafts[label] = new_val

                if changed:
                    self._invalid_fields.pop(label, None)
                    value[key] = new_val
                    edited = True

                im.pop_id()

        draw_values(target_sections)
        im.end_filtered_list()

        if edited:
            self._apply_grouped_data(data)
            self._json_text = json.dumps(data, indent=2)
            self._status_msg = tr("Setting updated.")

        # Status Line
        if self._json_error:
            im.text_colored((0.95, 0.25, 0.25, 1.0), self._json_error)
        elif self._status_msg:
            im.text_colored((0.2, 0.85, 0.4, 1.0), self._status_msg)

    def _draw_laser_devices(self) -> None:
        """The laser chooser inside the Lasers group of the Settings dock: one row per laser
        system connected to this computer -- pick which one this session drives."""
        m = self.model
        busy = bool(getattr(m, "running", False)) or bool(getattr(m, "connecting", False))
        im.text_wrapped(tr("Lasers this computer is connected to; switching is idle-only and "
                           "always starts with the light off."))
        for entry in m.laser_devices():
            im.push_id(entry["key"])
            connected = entry["connected"] or (
                entry["backend"] == m.laser_kind and m.laser_connected
                and (not entry["address"] or m.laser_address == entry["address"]))
            if connected:
                im.text_colored((0.4, 0.9, 0.5, 1.0), "●")
            else:
                im.text_colored((0.5, 0.5, 0.5, 0.6), "○")
            im.same_line()
            im.text_unformatted(str(entry["label"]))
            im.same_line()
            im.text_disabled(str(entry["detail"]))
            if connected:
                im.same_line()
                im.text_colored((0.4, 0.9, 0.5, 1.0), tr("in use"))
            im.same_line()
            if busy:
                im.begin_disabled()
            if im.button(f"{tr('Use')}##laser_use"):
                ok, why = m.select_laser_device(entry["key"])
                self._status_msg = why if not ok else f"{entry['label']}: {why}"
            if busy:
                im.end_disabled()
            im.set_item_tooltip(tr("Connect this laser system for the session."))
            im.pop_id()

    def _draw_camera_actions(self) -> None:
        """Action buttons inside the Camera group of the Settings dock."""
        v = self.app.video
        if im.button(f"🔍 {tr('Discover')}##cam_discover"):
            v.discover()
        im.set_item_tooltip(tr("Scan system for USB cameras and capture devices."))

        im.same_line()
        if im.button(tr("Matrix Vision") + "##cam_mv"):
            v.address = "mv:0"
        im.set_item_tooltip(tr("Select the first Matrix Vision SDK capture device."))

        im.same_line()
        if not getattr(v, "_connected", False):
            im.push_style_color(im.Col.BUTTON, (0.15, 0.55, 0.35, 1.0))
            if im.button(f"🔌 {tr('Connect')}##cam_conn"):
                v.connect()
            im.pop_style_color()
        else:
            im.push_style_color(im.Col.BUTTON, (0.65, 0.25, 0.25, 1.0))
            if im.button(f"🛑 {tr('Disconnect')}##cam_disconn"):
                v.disconnect()
            im.pop_style_color()

        im.same_line()
        if getattr(v, "_recorder", None) is None:
            if im.button(f"⏺ {tr('Record')}##cam_rec"):
                v.record()
        else:
            im.push_style_color(im.Col.BUTTON, (0.75, 0.25, 0.25, 1.0))
            if im.button(f"⏹ {tr('Stop')}##cam_stop"):
                v.stop_recording()
            im.pop_style_color()

        if v.status:
            im.text_disabled(f"{tr('Status')}: {v.status}")
        if v.discovered and v.discovered != "No discovery performed.":
            im.text_wrapped(v.discovered)
        im.separator()

    def _draw_storage_actions(self) -> None:
        """Action buttons inside the Storage & Profiles group."""
        m = self.model
        if im.button(f"⚙ {tr('Load Active Profile')}##stor_load"):
            if hasattr(m, "load_settings"):
                m.load_settings()
            self._json_text = json.dumps(self._build_grouped_data(), indent=2)
            self._status_msg = tr("Loaded active profile settings onto hardware.")
        im.set_item_tooltip(tr("Apply currently selected settings profile onto hardware."))

        im.same_line()
        if im.button(f"💾 {tr('Save Profile As…')}##stor_save"):
            if hasattr(m, "save_settings_as"):
                m.save_settings_as()
        im.set_item_tooltip(tr("Save active settings and calibration to a new profile."))

        im.same_line()
        if im.button(tr("Recover from Meas.") + "##stor_meas"):
            if hasattr(m, "use_measurement_settings"):
                m.use_measurement_settings()
        im.set_item_tooltip(tr("Recover settings from selected PTU measurement file header."))
        im.separator()

    # -- Mode 2: JSON Source Editor (Interactive Code / JSON) -----------------------------------
    def _draw_json_editor(self, width: float) -> None:
        if not self._json_text:
            data = self._build_grouped_data()
            self._json_text = json.dumps(data, indent=2)

        # Editor Toolbar
        if im.button(f"⚡ {tr('Apply to Hardware')}"):
            try:
                parsed = json.loads(self._json_text)
                self._apply_grouped_data(parsed)
                self._json_error = ""
                self._status_msg = tr("Successfully applied JSON configuration to hardware & camera.")
            except Exception as exc:
                self._json_error = f"{tr('JSON Apply Failed')}: {exc}"
        im.set_item_tooltip(tr("Parse and commit this JSON document directly into hardware parameters."))

        im.same_line()
        if im.button(f"🧹 {tr('Format JSON')}"):
            try:
                parsed = json.loads(self._json_text)
                self._json_text = json.dumps(parsed, indent=2)
                self._json_error = ""
                self._status_msg = tr("Formatted JSON with standard 2-space indentation.")
            except Exception as exc:
                self._json_error = f"{tr('Format Failed')}: {exc}"
        im.set_item_tooltip(tr("Re-indent and prettify JSON syntax."))

        if width >= 400.0:
            im.same_line()
        if im.button(f"↺ {tr('Reset to Hardware')}"):
            data = self._build_grouped_data()
            self._json_text = json.dumps(data, indent=2)
            self._json_error = ""
            self._status_msg = tr("Reset JSON editor to current hardware values.")
        im.set_item_tooltip(tr("Discard unapplied edits and refresh JSON from connected device."))

        im.same_line()
        if im.button(f"✓ {tr('Validate')}"):
            self.validate()
        im.set_item_tooltip(tr("Check JSON syntax."))

        # Editor Surface: the real code editor (colourised JSON, click-to-focus,
        # wheel scroll) -- a plain multiline field cannot edit a document this size
        # comfortably. External text changes (Load/Format/Reset above) replace the
        # content through the editor's bound-text sync.
        from emtk.widgets.text_editor import draw_editor

        avail_h = im.get_content_region_avail()[1]
        _, new_text = draw_editor(
            "SettingsJsonSource",
            self._json_text,
            height=max(260.0, avail_h - 45.0),
            language="json",
        )
        im.set_item_tooltip(tr("Edit the settings' JSON source; Apply to Hardware commits it."))
        if new_text != self._json_text:
            self._json_text = new_text
            self._json_dirty = True

        # Status and Validation Readout
        if self._json_error:
            im.push_style_color(im.Col.TEXT, (0.95, 0.25, 0.25, 1.0))
            im.text(f"❌ {self._json_error}")
            im.pop_style_color()
        elif self._status_msg:
            im.push_style_color(im.Col.TEXT, (0.2, 0.85, 0.4, 1.0))
            im.text(f"● {self._status_msg}")
            im.pop_style_color()
        else:
            im.text_disabled(tr("Type or paste JSON. Click 'Apply to Hardware' to commit."))

    def validate(self) -> bool:
        """Validate current JSON source or grouped data."""
        target_text = self._json_text or json.dumps(self._build_grouped_data(), indent=2)
        try:
            parsed = json.loads(target_text)
            if not isinstance(parsed, dict):
                raise ValueError(tr("Root must be a JSON object / dictionary."))
            self._json_error = ""
            self._status_msg = tr("JSON syntax valid.")
            return True
        except Exception as exc:
            self._json_error = f"{tr('Validation error')}: {exc}"
            return False


# Backwards compatibility alias
PhacqSettingsPanel = SettingsPanel
