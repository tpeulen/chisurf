"""TCSPC devices as Record sources -- every device through libphacq.

libphacq drives the hardware natively (no vendor library, no vendor kernel driver): PicoQuant
MultiHarp 150/160, PicoHarp 330 and HydraHarp 500 over USB, and Becker & Hickl SPC cards
(130/131/132/140/15x/16x/830/930) over PCI. One ``phacq.Device`` API for all of them:

* :func:`attached_devices` lists what is connected, :func:`open_device` opens and initialises one
  in its time-tagged mode (PicoQuant T3, B&H FIFO).
* Every setting a device has is described by the device itself
  (``Device.parameter_schema()``: a registry entry in tttrlib's dialect -- JSON Schema with titles,
  units, ranges, choices and groups, one property per input for per-input settings). The Record
  tool renders that schema with :func:`settings_form`, so no setting is left out and a new driver
  setting appears without code here. Values travel as one flat dict (``Device.settings()`` /
  ``Device.apply()``), which is also what an acquisition settings file stores.
* :class:`DeviceSource` streams the device's events (packed ``phacq.EVENT_DTYPE`` records) into
  :class:`~chisurf.plugins.core.acq.live.sources.PhotonBatch` es and records them to a PTU with
  phacq's ``PtuWriter``.

phacq is optional at import: :data:`PHACQ` says whether it is installed; without it the Record tool
offers the simulator and replay only.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .sources import PhotonBatch, PhotonSource, SourceInfo, SourceUnavailable

try:
    import phacq

    PHACQ = True
except Exception:  # noqa: BLE001 - optional dependency
    phacq = None
    PHACQ = False

__all__ = [
    "PHACQ",
    "TCSPC_DRIVERS",
    "DeviceEntry",
    "DeviceSource",
    "attached_devices",
    "device_label",
    "open_device",
    "settings_form",
]

#: phacq drivers that are TCSPC units (the Sepia II laser driver is :mod:`.laser`'s). The
#: TimeHarp 260 is listed and identified; phacq cannot measure with it (its connect says why).
TCSPC_DRIVERS = ("picoquant", "bh", "th260")

#: Micro-time bins a T3 start-stop time can span (15-bit dtime): the provisional macro step of a
#: run without a sync.
NO_SYNC_MICRO_RANGE = 1 << 15

#: Events per FIFO read.
_CHUNK_EVENTS = 1 << 16


@dataclass(frozen=True)
class DeviceEntry:
    """One connected device as phacq enumerates it."""

    driver: str
    serial: str
    vendor: str = ""
    model: str = ""

    @property
    def key(self) -> str:
        """``driver:serial`` -- what a settings file and the device chooser store."""
        return f"{self.driver}:{self.serial}"

    @property
    def label(self) -> str:
        """What the device chooser shows."""
        name = " ".join(x for x in (self.vendor, self.model) if x) or self.driver
        return f"{name} {self.serial}".strip()


def _registry():
    return phacq.DriverRegistry.instance()


def attached_devices(drivers: tuple[str, ...] = TCSPC_DRIVERS) -> list[DeviceEntry]:
    """The connected devices of *drivers*; empty without phacq, without devices, or without
    access (no USB permission, no PCI access)."""
    if not PHACQ:
        return []
    out: list[DeviceEntry] = []
    loaded = set(_registry().driver_names())
    for name in drivers:
        if name not in loaded:
            continue
        try:
            found = _registry().driver(name).enumerate()
        except Exception:  # noqa: BLE001 - a driver without hardware access lists nothing
            continue
        for info in found:
            out.append(DeviceEntry(name, str(info.serial_number), str(info.vendor), str(info.model)))
    return out


def find_device(key: str, drivers: tuple[str, ...] = TCSPC_DRIVERS) -> DeviceEntry | None:
    """The attached device ``driver:serial`` (or the first one for an empty *key*)."""
    for entry in attached_devices(drivers):
        if not key or entry.key == key:
            return entry
    return None


def device_for(section: dict, drivers: tuple[str, ...] = TCSPC_DRIVERS) -> DeviceEntry | None:
    """The attached device a settings file's ``device`` section is for.

    Matched by ``driver`` and ``serial`` when the section names a serial (the unit it was
    recorded on), else by ``driver`` and ``model``, else the driver's first device. ``None``
    when that device is not attached -- never another unit in its place.
    """
    driver = str(section.get("driver") or "")
    serial = str(section.get("serial") or "").strip()
    model = str(section.get("model") or "").strip().lower()
    found = [e for e in attached_devices(drivers) if not driver or e.driver == driver]
    if serial:
        return next((e for e in found if e.serial.strip() == serial), None)
    if model:
        return next((e for e in found if e.model.strip().lower() == model), None)
    return found[0] if found else None


def time_tag_mode(driver: str):
    """The time-tagged mode the Record tool measures in: T3 on PicoQuant units, the FIFO (TTTR)
    mode on B&H cards."""
    return phacq.MeasurementMode.TTTR if driver == "bh" else phacq.MeasurementMode.T3


def open_device(entry: DeviceEntry | str, *, mode=None):
    """Open and initialise a device for time-tagged measurement.

    Parameters
    ----------
    entry : DeviceEntry or str
        A listed device, or ``driver:serial`` (``driver:`` opens the driver's first device; the
        drivers also accept their test inputs, e.g. ``picoquant:replay:<file>``,
        ``sepia:sim:``).
    mode : phacq.MeasurementMode, optional
        Defaults to :func:`time_tag_mode`.

    Returns
    -------
    phacq.Device
    """
    if not PHACQ:
        raise SourceUnavailable("libphacq is not installed")
    if isinstance(entry, DeviceEntry):
        driver, serial = entry.driver, entry.serial
    else:
        driver, _, serial = str(entry).partition(":")
    dev = _registry().driver(driver).open(serial)
    if driver != "sepia":  # a laser driver has no measurement mode
        dev.initialize(mode if mode is not None else time_tag_mode(driver),
                       phacq.ReferenceClock.Internal)
    dev.phacq_driver = driver  # where it came from, for the settings file
    return dev


def device_label(dev) -> str:
    """``vendor model serial`` of an opened device."""
    info = dev.information()
    return " ".join(x for x in (info.vendor, info.model, info.serial_number) if x)


def settings_form(dev, values: dict | None = None, on_change=None, *, folded: bool = True,
                  advanced: bool = True, exclude: tuple = ()):
    """The device's complete settings form: every setting phacq describes, grouped as the driver
    groups them (sync, inputs one panel each, timing, markers ...).

    The schema is a registry entry in tttrlib's dialect, so it renders through the same grouped
    form as tttrlib's own registry entries. ``form.params()`` is the flat ``{name: value}`` dict
    ``dev.apply`` takes.

    Parameters
    ----------
    dev : phacq.Device
    values : dict, optional
        Initial values; defaults to what the device holds now (``dev.settings()``).
    on_change : callable, optional
        Called with no argument after an edit.
    folded : bool
        Start with every group folded (the default: a TCSPC unit has dozens of settings).
    advanced : bool
        Show the settings the driver marks advanced (``"advanced": true`` in its schema);
        off, the form is the simple view without them.
    exclude : tuple of str
        Settings another panel owns (a scanner's raster comes from the Scan panel).
    """
    from chisurf.core.registry.tttrlib import entry_form_view_for

    current = dict(dev.settings())
    if values:
        current.update({k: v for k, v in values.items() if k in current})
    schema = dev.schema()
    if not advanced:
        schema = simple_schema(schema)
    if exclude:
        params = dict(schema.get("params_schema") or {})
        params["properties"] = {k: v for k, v in (params.get("properties") or {}).items()
                                if k not in exclude}
        if "required" in params:
            params["required"] = [k for k in params["required"] if k in params["properties"]]
        schema = {**schema, "params_schema": params}
    if not advanced or exclude:
        current = {k: v for k, v in current.items()
                   if k in schema["params_schema"]["properties"]}
    return entry_form_view_for(schema, values=current, on_change=on_change, folded=folded)


def simple_schema(schema: dict) -> dict:
    """*schema* without the settings its driver marks ``advanced``."""
    params = dict(schema.get("params_schema") or {})
    props = {k: v for k, v in (params.get("properties") or {}).items() if not v.get("advanced")}
    params["properties"] = props
    if "required" in params:
        params["required"] = [k for k in params["required"] if k in props]
    return {**schema, "params_schema": params}


def apply_settings(dev, values: dict) -> list[str]:
    """Apply a flat settings dict, the editable keys only; returns problems (empty when it all
    applied). phacq validates everything before it sends anything, so on a problem nothing of
    *values* reached the device and the message names the offending setting."""
    props = dev.schema()["params_schema"]["properties"]
    editable = {
        k: v for k, v in values.items()
        if k in props and not props[k].get("readOnly") and v is not None
    }
    unknown = sorted(set(values) - set(props))
    notes = [f"{k}: not a setting of {device_label(dev)}" for k in unknown]
    try:
        dev.apply(editable)
    except Exception as e:  # noqa: BLE001 - phacq.Error carries the setting and the rule
        notes.append(str(e))
    return notes


# ---------------------------------------------------------------------------------------------
# streaming
# ---------------------------------------------------------------------------------------------
class DeviceSource(PhotonSource):
    """A phacq device streaming time-tagged events, decoded into photon batches and recorded.

    Parameters
    ----------
    device : phacq.Device
        Opened and initialised (:func:`open_device`), settings applied.
    duration_s : float or None
        The device's acquisition time; ``None`` measures until :meth:`stop`.
    chunk_events : int
        Events per read.

    Notes
    -----
    A timed run ends on the device (``stops_itself``), and the device keeps delivering what it
    acquired after the end (``measuring()`` stays true until its FIFO is empty), so the recording
    and the analysis cover the same events.
    """

    stops_itself = True

    def __init__(self, device, *, duration_s: float | None = None,
                 chunk_events: int = _CHUNK_EVENTS):
        if not PHACQ:
            raise SourceUnavailable("libphacq is not installed")
        self.device = device
        self.duration_s = duration_s
        self.chunk_events = int(chunk_events)
        info = device.information()
        self.sync_rate_hz = self._sync_rate()
        micro = float(info.base_resolution_ps) * 1e-12
        if info.macro_resolution_ps > 0:  # a macro clock of its own (B&H FIFO, T2)
            macro = float(info.macro_resolution_ps) * 1e-12
            n_micro = 4096 if getattr(device, "phacq_driver", "") == "bh" else max(
                1, int(round(macro / micro)) if micro else 1)
        else:  # T3: the macro time counts sync periods
            if self.sync_rate_hz > 0:
                macro = self._divider() / self.sync_rate_hz
            else:
                # No sync (laser off, cable out): record anyway. The unit still time-tags its
                # inputs; until a sync is measured the macro step is the unit's whole start-stop
                # range, and the file's header takes the rate measured at its close.
                macro = micro * NO_SYNC_MICRO_RANGE if micro else 1e-3
            # micro times travel as 16 bit (PhotonBatch); real units span a few hundred to a few
            # thousand bins per period, a slow simulated sync can exceed that
            n_micro = min(1 << 16, max(1, int(round(macro / micro)))) if micro else 1
        if micro <= 0:
            raise SourceUnavailable(f"{device_label(device)} reports no time resolution")
        #: no sync was measured when the source was made (the run is recorded anyway)
        self.no_sync = info.macro_resolution_ps <= 0 and self.sync_rate_hz <= 0
        self.info = SourceInfo(
            name=device_label(device) + (" (no sync)" if self.no_sync else ""),
            macro_clock_s=macro, micro_res_s=micro, n_micro=n_micro,
        )
        self._stop = threading.Event()
        self._done = threading.Event()
        self._started = 0.0
        self._gaps = 0
        self._error = ""

    def _divider(self) -> int:
        """Sync pulses per T3 macro-time step. A device that counts every sync whatever its
        divider (HydraHarp 400) says so in ``macro_sync_divider``; otherwise the step is the
        sync divider (MultiHarp, B&H)."""
        for name in ("macro_sync_divider", "sync_divider", "sync_freq_div"):
            try:
                return max(1, int(self.device.get_parameter(name, -1)))
            except Exception:  # noqa: BLE001 - not a setting of this device
                continue
        return 1

    def _sync_rate(self) -> float:
        try:
            rates = list(self.device.count_rates())
        except Exception:  # noqa: BLE001 - a device without rate counters
            return 0.0
        return float(rates[0]) if rates else 0.0

    # -- the source interface -----------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._done.clear()
        self._gaps = 0
        self._error = ""
        self.device.start(float(self.duration_s) if self.duration_s else 0.0)
        self._started = time.monotonic()

    def stop(self) -> None:
        """Stop measuring; what the device acquired is still read out (``finished`` follows)."""
        self._stop.set()
        try:
            self.device.stop()
        except Exception as e:  # noqa: BLE001 - shown in the status line
            self._error = str(e)

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    def status(self) -> dict[str, Any]:
        return {"queued": 0, "dropped": int(self._gaps), "stalls": 0, "error": self._error}

    def read(self, timeout: float = 0.2) -> PhotonBatch | None:
        """The next events, decoded (called by the session's worker thread only)."""
        if self._done.is_set():
            return None
        try:
            raw = self.device.read_events_raw(self.chunk_events)
        except Exception as e:  # noqa: BLE001 - a device error ends the run, shown
            self._error = str(e)
            self._done.set()
            return None
        if not raw:
            if not self.device.measuring():
                self._done.set()
            else:
                time.sleep(min(0.005, max(0.0, timeout)))
            return None
        events = np.frombuffer(raw, dtype=phacq.EVENT_DTYPE)
        flags = events["flags"]
        self._gaps += int(np.count_nonzero(flags & phacq.kEventFlagOverflow))
        marker = (flags & phacq.kEventFlagMarker) != 0
        return PhotonBatch(
            events["macro_time"].astype(np.uint64),
            events["micro_time"].astype(np.uint16),
            events["channel"].astype(np.int8),
            raw=events,
            event=marker.astype(np.int8),
        )

    # -- recording -----------------------------------------------------------------------------
    def make_recorder(self, path, name: str = "", extra: dict | None = None):
        """A PTU writer for the device's events, with the device header and the *extra* tags (the
        run's acquisition settings, a scan's ``ImgHdr_*`` tags). str values are string tags; bool,
        int and float keep their PicoQuant type."""
        mode = phacq.MeasurementMode.T3
        writer = phacq.PtuWriter(str(path), self.device.information(), mode)
        for key, value, index in hardware_tags(self.device):
            if isinstance(value, bool):
                writer.set_tag_bool(key, value, index)
            else:
                writer.set_tag_int(key, int(value), index)
        for key, value in (extra or {}).items():
            # an indexed tag is written "Name(i)" (SymPhoTime's UsrHeadName(0), ...)
            m = re.match(r"^(.*)\((\d+)\)$", str(key))
            key, index = (m.group(1), int(m.group(2))) if m else (key, -1)
            if isinstance(value, bool):
                writer.set_tag_bool(key, value, index)
            elif isinstance(value, (int, np.integer)):
                writer.set_tag_int(key, int(value), index)
            elif isinstance(value, (float, np.floating)):
                writer.set_tag_float(key, float(value), index)
            else:
                writer.set_tag(key, str(value), index)
        spc = None
        if getattr(self.device, "phacq_driver", "") == "bh":
            # B&H's own files beside the PTU: .spc (FIFO_32) and its .set (the card's settings)
            spc = (phacq.SpcWriter(str(Path(path).with_suffix(".spc")),
                                   self.info.macro_clock_s, True), Path(path).with_suffix(".set"))
        return _PtuRecorder(writer, self, spc, title=name)


#: phacq setting -> PicoQuant PTU tag (the time-tagged file format's tag dictionary); per-input
#: settings become indexed tags. What a reader such as SymPhoTime or ChiSurf's settings recovery
#: (``settings_file.from_ptu_tags``) takes the instrument state from.
_SYNC_TAGS = {
    "sync_divider": "HWSync_Divider",
    "sync_level_mv": "HWSync_TrgLevel",
    "sync_edge": "HWSync_TrgEdge",
    "sync_offset_ps": "HWSync_Offset",
    "sync_cfd_discr_mv": "HWSync_CFDLevel",
    "sync_cfd_zerox_mv": "HWSync_CFDZeroCross",
}
_INPUT_TAGS = {
    "input_level_mv": "HWInpChan_TrgLevel",
    "input_edge": "HWInpChan_TrgEdge",
    "input_offset_ps": "HWInpChan_Offset",
    "input_enable": "HWInpChan_Enabled",
    "input_cfd_discr_mv": "HWInpChan_CFDLevel",
    "input_cfd_zerox_mv": "HWInpChan_CFDZeroCross",
}


#: A CFD unit's (HydraHarp 400) levels under SymPhoTime's tag names.
_SYNC_CFD_TAGS = {"sync_level_mv": "HWSync_CFDLevel", "sync_zero_cross_mv": "HWSync_CFDZeroCross"}
_INPUT_CFD_TAGS = {"input_level_mv": "HWInpChan_CFDLevel",
                   "input_zero_cross_mv": "HWInpChan_CFDZeroCross"}


def hardware_tags(dev) -> list[tuple[str, Any, int]]:
    """The device's settings as PTU header tags ``(name, value, index)``; index -1 = not indexed.

    Only settings the device has and reports are written: a PicoQuant unit fills them, a B&H
    card (other names) writes none of these.
    """
    try:
        s = dict(dev.settings())
    except Exception:  # noqa: BLE001 - a device that cannot report: no hardware tags
        return []
    out: list[tuple[str, Any, int]] = []
    # A constant-fraction discriminator (HydraHarp 400: level + zero cross) is written as
    # SymPhoTime writes it, HWSync_CFDLevel/CFDZeroCross, not as an edge trigger level.
    cfd = "sync_zero_cross_mv" in s
    sync_tags = {**_SYNC_TAGS, **(_SYNC_CFD_TAGS if cfd else {})}
    input_tags = {**_INPUT_TAGS, **(_INPUT_CFD_TAGS if cfd else {})}
    for name, tag in sync_tags.items():
        if s.get(name) is not None:
            out.append((tag, s[name], -1))
    for key, value in s.items():
        base, _, rest = key.partition("[")
        if value is None or not rest or base not in input_tags:
            continue
        out.append((input_tags[base], value, int(rest.rstrip("]"))))
    if s.get("binning") is not None:
        out.append(("MeasDesc_BinningFactor", int(2 ** int(s["binning"])), -1))
    if s.get("offset_ns") is not None:
        out.append(("MeasDesc_Offset", s["offset_ns"], -1))
    if s.get("marker_enable") is not None:
        enable, edges = int(s["marker_enable"]), int(s.get("marker_edges") or 0)
        for i in range(4):
            out.append(("HWMarkers_Enabled", bool(enable >> i & 1), i))
            out.append(("HWMarkers_RisingEdge", bool(edges >> i & 1), i))
        if s.get("marker_holdoff_ns") is not None:
            out.append(("HWMarkers_HoldOff", s["marker_holdoff_ns"], -1))
    return out


class _PtuRecorder:
    """The PTU of a device run, and for a B&H card its .spc + .set as well."""

    def __init__(self, writer, source: DeviceSource, spc=None, title: str = ""):
        self.writer = writer
        self.source = source
        self.spc = spc
        self.title = title

    def write(self, batch: PhotonBatch) -> bool:
        if batch.raw is not None and len(batch.raw):
            raw = np.ascontiguousarray(batch.raw).tobytes()
            self.writer.write_raw(raw)
            if self.spc is not None:
                self.spc[0].write_raw(raw)
        return True

    def close(self) -> None:
        acq_s = time.monotonic() - self.source._started if self.source._started else 0.0
        rate = float(self.source.sync_rate_hz)
        if rate <= 0:
            # no sync at the start: the rate now, else the provisional macro step's
            rate = self.source._sync_rate() or self.source._divider() / self.source.info.macro_clock_s
        self.writer.close(acq_s, rate)
        if self.spc is not None:
            self.spc[0].close()
            phacq.write_bh_set(str(self.spc[1]), self.source.device, self.title)
