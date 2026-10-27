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

import threading
import time
from dataclasses import dataclass
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

#: phacq drivers that are TCSPC units (the Sepia II laser driver is :mod:`.laser`'s).
TCSPC_DRIVERS = ("picoquant", "bh")

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


def settings_form(dev, values: dict | None = None, on_change=None, *, folded: bool = True):
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
    """
    from chisurf.core.registry.tttrlib import entry_form_view_for

    current = dict(dev.settings())
    if values:
        current.update({k: v for k, v in values.items() if k in current})
    return entry_form_view_for(dev.schema(), values=current, on_change=on_change, folded=folded)


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
            if self.sync_rate_hz <= 0:
                raise SourceUnavailable("no sync signal: connect the laser's sync output")
            macro = self._divider() / self.sync_rate_hz
            # micro times travel as 16 bit (PhotonBatch); real units span a few hundred to a few
            # thousand bins per period, a slow simulated sync can exceed that
            n_micro = min(1 << 16, max(1, int(round(macro / micro)))) if micro else 1
        if micro <= 0:
            raise SourceUnavailable(f"{device_label(device)} reports no time resolution")
        self.info = SourceInfo(
            name=device_label(device), macro_clock_s=macro, micro_res_s=micro, n_micro=n_micro
        )
        self._stop = threading.Event()
        self._done = threading.Event()
        self._started = 0.0
        self._gaps = 0
        self._error = ""

    def _divider(self) -> int:
        try:
            return max(1, int(self.device.get_parameter("sync_divider", -1)))
        except Exception:  # noqa: BLE001 - B&H calls it sync_freq_div, others have none
            try:
                return max(1, int(self.device.get_parameter("sync_freq_div", -1)))
            except Exception:  # noqa: BLE001
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
        for key, value in (extra or {}).items():
            if isinstance(value, bool):
                writer.set_tag_bool(key, value)
            elif isinstance(value, (int, np.integer)):
                writer.set_tag_int(key, int(value))
            elif isinstance(value, (float, np.floating)):
                writer.set_tag_float(key, float(value))
            else:
                writer.set_tag(key, str(value))
        return _PtuRecorder(writer, self)


class _PtuRecorder:
    def __init__(self, writer, source: DeviceSource):
        self.writer = writer
        self.source = source

    def write(self, batch: PhotonBatch) -> bool:
        if batch.raw is not None and len(batch.raw):
            self.writer.write_raw(np.ascontiguousarray(batch.raw).tobytes())
        return True

    def close(self) -> None:
        acq_s = time.monotonic() - self.source._started if self.source._started else 0.0
        self.writer.close(acq_s, float(self.source.sync_rate_hz))
