"""Laser control for the Record tool: one interface, a Sepia II backend, a simulator.

A :class:`LaserBackend` drives a picosecond laser driver the way an acquisition needs it: the laser
heads (on/off, intensity, pulsed or continuous), the base oscillator (frequency and divider, i.e. the
repetition rate), the sequencer that decides which head fires in which slot (pulsed interleaved
excitation), the sync output to the TCSPC unit, and a status line. Two rules hold for every backend:

* **Outputs are off after** :meth:`LaserBackend.open` **and after any error** while settings are being
  applied; light is emitted only once the caller has applied a program and called
  :meth:`LaserBackend.set_emission` ``(True)``.
* :meth:`LaserBackend.laser_off` **always works**: it never raises, on any backend, open or not.

Backends:

* :class:`SepiaBackend` -- PicoQuant's Sepia II (PDL 828) through the *public* ``Sepia2_Lib`` C API
  (the documented PQLaserDrv API and its Python ctypes wrapper), loaded with :mod:`ctypes`. The
  library is found in this order: an explicit path, ``$CHISURF_SEPIA2_LIB``, PicoQuant's
  ``Sepia2_Lib`` (Windows; Linux only through Wine), then CMC's ``cmc_sepia2`` (same API, see CMC's
  ``okf/backends/cmc-sepia2-api.md``; ``CMC_SEPIA2_SIM=1`` makes it simulate one device). On macOS
  without ``cmc_sepia2`` the backend is unavailable and :func:`sepia_available` says why.
* :class:`SimLaser` -- the same interface in pure Python, for tests and for the UI without hardware.

:func:`propose_pie_windows` turns a laser program into the micro-time windows of an Experiment setup:
the repetition rate gives the sync period, the sequencer slots give which excitation lies in which
part of it.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import os
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Sequencer outputs of a Sepia II oscillator module (SOM 828 / SOM 828-D).
SEQUENCER_OUTPUTS = 8

#: Repetition rates of a laser driver module (SLM 828) running on its own oscillator, by index; 6 and 7
#: mean "triggered" (rising / falling edge), i.e. driven by the oscillator module's sequencer.
SLM_FREQUENCIES_HZ = (80e6, 40e6, 20e6, 10e6, 5e6, 2.5e6)
SLM_TRIGGER_RISING = 6
SLM_TRIGGER_FALLING = 7

#: Sepia2 module type codes (public ``Sepia2_Def``).
_SCM, _SOM, _SOMD, _SLM = 0x40, 0x50, 0x51, 0x70


class LaserError(RuntimeError):
    """A laser operation failed; outputs have been switched off."""


@dataclass
class HeadState:
    """One laser head (a laser driver module and the head plugged into it)."""

    slot: int
    name: str = ""
    kind: str = "laser"  # laser | led | none | failure
    serial: str = ""
    wavelength_nm: float | None = None
    #: The sequencer output that triggers this head (-1: the head runs on its own oscillator).
    output: int = -1
    pulsed: bool = True
    intensity_pct: float = 0.0
    #: Optical power when the API reports it (Sepia II does not; per-head calibrations may).
    power_mw: float | None = None
    #: Own repetition rate index (:data:`SLM_FREQUENCIES_HZ`) or a trigger mode (6, 7).
    trigger_index: int = SLM_TRIGGER_FALLING


@dataclass
class OscillatorState:
    """The base oscillator and its sequencer (which output fires in which slot)."""

    slot: int = -1
    base_hz: float = 80e6
    divider: int = 1
    pre_sync: int = 0
    sync_mask: int = 0
    #: Pulses per output in one sequence, in sequencer order.
    burst_lengths: list[int] = field(default_factory=lambda: [1] + [0] * (SEQUENCER_OUTPUTS - 1))
    output_enabled: list[bool] = field(default_factory=lambda: [False] * SEQUENCER_OUTPUTS)
    sync_enabled: list[bool] = field(
        default_factory=lambda: [True] + [False] * (SEQUENCER_OUTPUTS - 1)
    )
    sync_inverse: bool = False
    #: Per-output delay in ns (SOM 828-D only; 0 elsewhere).
    delays_ns: list[float] = field(default_factory=lambda: [0.0] * SEQUENCER_OUTPUTS)
    trigger_mode: str = "internal"

    @property
    def pulse_rate_hz(self) -> float:
        """Rate of the pulses the sequencer distributes (base frequency / divider)."""
        return self.base_hz / max(1, int(self.divider))

    @property
    def sequence_period_s(self) -> float:
        """One full sequence: every output's burst once."""
        pulses = sum(int(n) for n in self.burst_lengths if n > 0) or 1
        return pulses / self.pulse_rate_hz


@dataclass
class LaserState:
    model: str = ""
    serial: str = ""
    library: str = ""
    heads: list[HeadState] = field(default_factory=list)
    oscillator: OscillatorState | None = None
    #: True while all outputs are blocked (Sepia II: the controller's soft lock).
    emission_blocked: bool = True
    hardware_locked: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class LaserBackend(ABC):
    """A laser driver as the Record tool uses it. Subclasses implement the ``_``-methods."""

    #: Short name shown in the UI.
    kind = "laser"

    def __init__(self) -> None:
        self._open = False
        self._state = LaserState()

    # -- lifecycle -----------------------------------------------------------------------------
    @classmethod
    def available(cls) -> tuple[bool, str]:
        """Whether this backend can be opened here, and why not."""
        return True, ""

    def open(self, index: int = 0) -> LaserState:
        """Open device *index*; all outputs are off afterwards."""
        self._open_device(index)
        self._open = True
        self.laser_off()
        self._state = self._read_state()
        return self._state

    def close(self) -> None:
        if not self._open:
            return
        self.laser_off()
        try:
            self._close_device()
        finally:
            self._open = False

    def __enter__(self) -> LaserBackend:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return self._open

    # -- state ---------------------------------------------------------------------------------
    def state(self) -> LaserState:
        self._require_open()
        self._state = self._read_state()
        return self._state

    def laser_off(self) -> None:
        """Block all emission. Never raises."""
        with contextlib.suppress(Exception):
            if self._open:
                self._set_emission(False)
        self._state.emission_blocked = True

    def set_emission(self, on: bool) -> None:
        """Allow (``True``) or block all outputs."""
        self._require_open()
        self._guarded(lambda: self._set_emission(bool(on)))
        self._state.emission_blocked = not on

    # -- program -------------------------------------------------------------------------------
    def set_head(
        self,
        slot: int,
        *,
        enabled: bool | None = None,
        intensity_pct: float | None = None,
        pulsed: bool | None = None,
        trigger_index: int | None = None,
    ) -> None:
        self._require_open()
        if intensity_pct is not None and not 0.0 <= float(intensity_pct) <= 100.0:
            raise LaserError(f"intensity {intensity_pct} % outside 0..100 %")
        self._guarded(lambda: self._set_head(slot, enabled, intensity_pct, pulsed, trigger_index))

    def set_oscillator(
        self,
        *,
        base_hz: float | None = None,
        divider: int | None = None,
        burst_lengths: list[int] | None = None,
        output_enabled: list[bool] | None = None,
        sync_enabled: list[bool] | None = None,
        sync_inverse: bool | None = None,
        delays_ns: list[float] | None = None,
    ) -> None:
        self._require_open()
        if divider is not None and int(divider) < 1:
            raise LaserError(f"divider {divider} must be at least 1")
        for name, seq in (
            ("burst_lengths", burst_lengths),
            ("output_enabled", output_enabled),
            ("sync_enabled", sync_enabled),
            ("delays_ns", delays_ns),
        ):
            if seq is not None and len(seq) != SEQUENCER_OUTPUTS:
                raise LaserError(f"{name} needs {SEQUENCER_OUTPUTS} entries, got {len(seq)}")
        self._guarded(
            lambda: self._set_oscillator(
                base_hz,
                divider,
                burst_lengths,
                output_enabled,
                sync_enabled,
                sync_inverse,
                delays_ns,
            )
        )

    def apply(self, laser: dict) -> LaserState:
        """Apply the ``laser`` section of an acquisition settings file (emission stays blocked)."""
        self._require_open()
        self.laser_off()
        try:
            osc = laser.get("oscillator") or {}
            if osc:
                self.set_oscillator(
                    base_hz=osc.get("base_hz"),
                    divider=osc.get("divider"),
                    burst_lengths=osc.get("burst_lengths"),
                    output_enabled=osc.get("output_enabled"),
                    sync_enabled=osc.get("sync_enabled"),
                    sync_inverse=osc.get("sync_inverse"),
                    delays_ns=osc.get("delays_ns"),
                )
            for head in laser.get("heads") or []:
                self.set_head(
                    int(head["slot"]),
                    enabled=head.get("enabled"),
                    intensity_pct=head.get("intensity_pct"),
                    pulsed=head.get("pulsed"),
                    trigger_index=head.get("trigger_index"),
                )
        except Exception:
            self.laser_off()
            raise
        return self.state()

    def capture(self) -> dict:
        """The current program as the ``laser`` section of an acquisition settings file."""
        st = self.state()
        out: dict = {"backend": self.kind, "model": st.model, "serial": st.serial, "heads": []}
        osc = st.oscillator
        for h in st.heads:
            enabled = bool(
                osc and 0 <= h.output < SEQUENCER_OUTPUTS and osc.output_enabled[h.output]
            )
            out["heads"].append(
                {
                    "slot": h.slot,
                    "name": h.name,
                    "wavelength_nm": h.wavelength_nm,
                    "output": h.output,
                    "enabled": enabled,
                    "pulsed": h.pulsed,
                    "intensity_pct": h.intensity_pct,
                    "trigger_index": h.trigger_index,
                }
            )
        if osc is not None:
            out["oscillator"] = {k: v for k, v in asdict(osc).items() if k != "slot"}
            out["repetition_rate_hz"] = osc.pulse_rate_hz
        return out

    # -- helpers -------------------------------------------------------------------------------
    def _require_open(self) -> None:
        if not self._open:
            raise LaserError("the laser is not open")

    def _guarded(self, op) -> None:
        try:
            op()
        except Exception as e:
            self.laser_off()
            raise LaserError(f"{e} -- outputs switched off") from e

    # -- backend -------------------------------------------------------------------------------
    @abstractmethod
    def _open_device(self, index: int) -> None: ...

    @abstractmethod
    def _close_device(self) -> None: ...

    @abstractmethod
    def _read_state(self) -> LaserState: ...

    @abstractmethod
    def _set_emission(self, on: bool) -> None: ...

    @abstractmethod
    def _set_head(self, slot, enabled, intensity_pct, pulsed, trigger_index) -> None: ...

    @abstractmethod
    def _set_oscillator(
        self, base_hz, divider, burst_lengths, output_enabled, sync_enabled, sync_inverse, delays_ns
    ) -> None: ...


# ---------------------------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------------------------
class SimLaser(LaserBackend):
    """A Sepia II-like driver in memory: one oscillator with sequencer, two heads (485 / 640 nm)."""

    kind = "simulated"

    def __init__(self, heads: list[tuple[str, float]] | None = None, base_hz: float = 80e6) -> None:
        super().__init__()
        self._heads_def = heads or [("LDH-D-C-485", 485.0), ("LDH-D-C-640", 640.0)]
        self._base_hz = float(base_hz)
        self.events: list[str] = []

    def _open_device(self, index: int) -> None:
        if index != 0:
            raise LaserError(f"no simulated laser {index}")
        self._sim = LaserState(
            model="Simulated PDL 828",
            serial="SIM-0001",
            library="simulator",
            oscillator=OscillatorState(slot=100, base_hz=self._base_hz),
        )
        self._sim.heads = [
            HeadState(slot=200 + 100 * i, name=n, wavelength_nm=w, output=i, serial=f"SIM-HEAD-{i}")
            for i, (n, w) in enumerate(self._heads_def)
        ]
        self.events.append("open")

    def _close_device(self) -> None:
        self.events.append("close")

    def _read_state(self) -> LaserState:
        import copy

        return copy.deepcopy(self._sim)

    def _set_emission(self, on: bool) -> None:
        self._sim.emission_blocked = not on
        self.events.append(f"emission {'on' if on else 'off'}")

    def _head(self, slot: int) -> HeadState:
        for h in self._sim.heads:
            if h.slot == slot:
                return h
        raise LaserError(f"no laser head in slot {slot}")

    def _set_head(self, slot, enabled, intensity_pct, pulsed, trigger_index) -> None:
        h = self._head(slot)
        if intensity_pct is not None:
            h.intensity_pct = float(intensity_pct)
        if pulsed is not None:
            h.pulsed = bool(pulsed)
        if trigger_index is not None:
            h.trigger_index = int(trigger_index)
        if enabled is not None and 0 <= h.output < SEQUENCER_OUTPUTS:
            self._sim.oscillator.output_enabled[h.output] = bool(enabled)

    def _set_oscillator(
        self, base_hz, divider, burst_lengths, output_enabled, sync_enabled, sync_inverse, delays_ns
    ) -> None:
        o = self._sim.oscillator
        if base_hz is not None:
            o.base_hz = float(base_hz)
        if divider is not None:
            o.divider = int(divider)
        if burst_lengths is not None:
            o.burst_lengths = [int(n) for n in burst_lengths]
        if output_enabled is not None:
            o.output_enabled = [bool(x) for x in output_enabled]
        if sync_enabled is not None:
            o.sync_enabled = [bool(x) for x in sync_enabled]
        if sync_inverse is not None:
            o.sync_inverse = bool(sync_inverse)
        if delays_ns is not None:
            o.delays_ns = [float(x) for x in delays_ns]


# ---------------------------------------------------------------------------------------------
# Sepia II through the public Sepia2_Lib API
# ---------------------------------------------------------------------------------------------
def _candidate_libraries(explicit: str | os.PathLike | None = None) -> list[Path]:
    out: list[Path] = []
    for p in (explicit, os.environ.get("CHISURF_SEPIA2_LIB"), os.environ.get("CMC_SEPIA2_LIB")):
        if p:
            out.append(Path(p))
    if sys.platform == "win32":
        for name in ("Sepia2_Lib.dll", "Sepia2_Lib64.dll"):
            found = ctypes.util.find_library(name)
            out.append(Path(found) if found else Path(name))
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        out += [pf / "PicoQuant" / "PQLaserDrv" / "Sepia2_Lib.dll"]
    for name in ("cmc_sepia2", "libcmc_sepia2"):
        found = ctypes.util.find_library(name)
        if found:
            out.append(Path(found))
    cmc = Path(os.environ.get("CMC_ROOT", Path.home() / "dev" / "cmc"))
    ext = {"darwin": ".dylib", "win32": ".dll"}.get(sys.platform, ".so")
    out += [cmc / "bin" / f"libcmc_sepia2{ext}", cmc / "bin" / f"cmc_sepia2{ext}"]
    return out


def sepia_available(explicit: str | os.PathLike | None = None) -> tuple[bool, str]:
    """Whether a Sepia2 library can be loaded here, and which (or why not)."""
    for path in _candidate_libraries(explicit):
        if path.is_absolute() and not path.exists():
            continue
        try:
            _load(path)
        except OSError:
            continue
        return True, str(path)
    if sys.platform == "darwin":
        return False, (
            "not available: no Sepia2 library for this platform (PicoQuant ships Sepia2_Lib "
            "for Windows only; build CMC's cmc_sepia2 or use the simulated laser)"
        )
    return (
        False,
        "not available: no Sepia2 library found (install PQLaserDrv or set CHISURF_SEPIA2_LIB)",
    )


def _load(path: Path):
    if sys.platform == "win32":
        return ctypes.WinDLL(str(path))
    return ctypes.CDLL(str(path))


class SepiaBackend(LaserBackend):
    """Sepia II (PDL 828) over the public Sepia2_Lib C API -- no access below the documented API."""

    kind = "sepia2"

    def __init__(self, library: str | os.PathLike | None = None) -> None:
        super().__init__()
        self._library_hint = library
        self._lib = None
        self._dev = -1
        self._scm = -1
        self._som = -1
        self._somd = False
        self._slms: list[int] = []

    @classmethod
    def available(cls) -> tuple[bool, str]:
        return sepia_available()

    # -- library plumbing ----------------------------------------------------------------------
    def _call(self, name: str, *args) -> None:
        rc = getattr(self._lib, f"SEPIA2_{name}")(*args)
        if rc != 0:
            buf = ctypes.create_string_buffer(64)
            with contextlib.suppress(Exception):
                self._lib.SEPIA2_LIB_DecodeError(rc, buf)
            text = buf.value.decode("latin-1", "replace") or str(rc)
            raise LaserError(f"Sepia2 {name}: {text} ({rc})")

    def _open_device(self, index: int) -> None:
        ok, where = sepia_available(self._library_hint)
        if not ok:
            raise LaserError(where)
        self._lib = _load(Path(where))
        self._library_path = where
        model = ctypes.create_string_buffer(64)
        serial = ctypes.create_string_buffer(64)
        self._call("USB_OpenDevice", index, model, serial)
        self._dev = index
        self._model = model.value.decode("latin-1", "replace")
        self._serial = serial.value.decode("latin-1", "replace")
        count = ctypes.c_int()
        self._call("FWR_GetModuleMap", self._dev, 0, ctypes.byref(count))
        self._slms = []
        for i in range(count.value):
            slot, primary, back, uptime = (
                ctypes.c_int(),
                ctypes.c_ubyte(),
                ctypes.c_ubyte(),
                ctypes.c_ubyte(),
            )
            self._call(
                "FWR_GetModuleInfoByMapIdx",
                self._dev,
                i,
                ctypes.byref(slot),
                ctypes.byref(primary),
                ctypes.byref(back),
                ctypes.byref(uptime),
            )
            mtype = ctypes.c_int()
            self._call("COM_GetModuleType", self._dev, slot.value, 1, ctypes.byref(mtype))
            if mtype.value == _SCM:
                self._scm = slot.value
            elif mtype.value in (_SOM, _SOMD):
                self._som, self._somd = slot.value, mtype.value == _SOMD
            elif mtype.value == _SLM:
                self._slms.append(slot.value)
        if self._scm < 0:
            raise LaserError(
                "Sepia2: no controller module (SCM) -- emission cannot be blocked safely"
            )

    def _close_device(self) -> None:
        with contextlib.suppress(Exception):
            self._call("FWR_FreeModuleMap", self._dev)
        with contextlib.suppress(Exception):
            self._call("USB_CloseDevice", self._dev)

    def _p(self, name: str) -> str:
        return ("SOMD_" if self._somd else "SOM_") + name

    def _read_state(self) -> LaserState:
        st = LaserState(model=self._model, serial=self._serial, library=self._library_path)
        lock = ctypes.c_ubyte()
        self._call("SCM_GetLaserSoftLock", self._dev, self._scm, ctypes.byref(lock))
        st.emission_blocked = bool(lock.value)
        with contextlib.suppress(Exception):
            locked = ctypes.c_ubyte()
            self._call("SCM_GetLaserLocked", self._dev, self._scm, ctypes.byref(locked))
            st.hardware_locked = bool(locked.value)
            if st.hardware_locked:
                st.warnings.append("hardware interlock or key switch locks the laser")
        if self._som >= 0:
            st.oscillator = self._read_oscillator()
        for i, slot in enumerate(self._slms):
            freq, mode, htype = ctypes.c_int(), ctypes.c_ubyte(), ctypes.c_int()
            self._call(
                "SLM_GetPulseParameters",
                self._dev,
                slot,
                ctypes.byref(freq),
                ctypes.byref(mode),
                ctypes.byref(htype),
            )
            inten = ctypes.c_ushort()
            self._call("SLM_GetIntensityFineStep", self._dev, slot, ctypes.byref(inten))
            serial = ctypes.create_string_buffer(64)
            with contextlib.suppress(Exception):
                self._call("COM_GetSerialNumber", self._dev, slot, 1, serial)
            kind = {0: "failure", 1: "led", 2: "laser", 3: "none"}.get(htype.value, "laser")
            if kind == "failure":
                st.warnings.append(f"laser head in slot {slot} reports a failure")
            st.heads.append(
                HeadState(
                    slot=slot,
                    kind=kind,
                    serial=serial.value.decode("latin-1", "replace"),
                    output=i,
                    pulsed=bool(mode.value),
                    intensity_pct=inten.value / 10.0,
                    trigger_index=freq.value,
                )
            )
        return st

    def _read_oscillator(self) -> OscillatorState:
        o = OscillatorState(slot=self._som)
        idx = ctypes.c_int()
        if self._somd:
            sync = ctypes.c_ubyte()
            self._call(
                "SOMD_GetFreqTrigMode", self._dev, self._som, ctypes.byref(idx), ctypes.byref(sync)
            )
        else:
            self._call("SOM_GetFreqTrigMode", self._dev, self._som, ctypes.byref(idx))
        text = ctypes.create_string_buffer(64)
        with contextlib.suppress(Exception):
            if self._somd:
                self._call("SOMD_DecodeFreqTrigMode", self._dev, self._som, idx.value, text)
            else:
                self._call("SOM_DecodeFreqTrigMode", self._dev, self._som, idx.value, text)
        o.trigger_mode = text.value.decode("latin-1", "replace") or f"mode {idx.value}"
        hz = _parse_frequency(o.trigger_mode)
        if hz:
            o.base_hz = hz
        div, pre, mask = ctypes.c_ushort(), ctypes.c_ubyte(), ctypes.c_ubyte()
        self._call(
            self._p("GetBurstValues"),
            self._dev,
            self._som,
            ctypes.byref(div),
            ctypes.byref(pre),
            ctypes.byref(mask),
        )
        o.divider, o.pre_sync, o.sync_mask = div.value, pre.value, mask.value
        lens = [ctypes.c_int() for _ in range(SEQUENCER_OUTPUTS)]
        self._call(
            self._p("GetBurstLengthArray"), self._dev, self._som, *[ctypes.byref(x) for x in lens]
        )
        o.burst_lengths = [x.value for x in lens]
        out_en, sync_en, inv = ctypes.c_ubyte(), ctypes.c_ubyte(), ctypes.c_ubyte()
        self._call(
            self._p("GetOutNSyncEnable"),
            self._dev,
            self._som,
            ctypes.byref(out_en),
            ctypes.byref(sync_en),
            ctypes.byref(inv),
        )
        o.output_enabled = [bool(out_en.value >> i & 1) for i in range(SEQUENCER_OUTPUTS)]
        o.sync_enabled = [bool(sync_en.value >> i & 1) for i in range(SEQUENCER_OUTPUTS)]
        o.sync_inverse = bool(inv.value)
        if self._somd:
            for i in range(SEQUENCER_OUTPUTS):
                d, f, c, m = ctypes.c_ubyte(), ctypes.c_ubyte(), ctypes.c_ubyte(), ctypes.c_ubyte()
                coarse, fine = ctypes.c_double(), ctypes.c_ubyte()
                with contextlib.suppress(LaserError):
                    self._call(
                        "SOMD_GetSeqOutputInfos",
                        self._dev,
                        self._som,
                        i,
                        ctypes.byref(d),
                        ctypes.byref(f),
                        ctypes.byref(c),
                        ctypes.byref(m),
                        ctypes.byref(coarse),
                        ctypes.byref(fine),
                    )
                    o.delays_ns[i] = coarse.value if d.value else 0.0
        return o

    def _set_emission(self, on: bool) -> None:
        self._call("SCM_SetLaserSoftLock", self._dev, self._scm, 0 if on else 1)

    def _set_head(self, slot, enabled, intensity_pct, pulsed, trigger_index) -> None:
        if slot not in self._slms:
            raise LaserError(f"no laser driver module in slot {slot}")
        if intensity_pct is not None:
            self._call(
                "SLM_SetIntensityFineStep", self._dev, slot, int(round(float(intensity_pct) * 10))
            )
        if pulsed is not None or trigger_index is not None:
            freq, mode, htype = ctypes.c_int(), ctypes.c_ubyte(), ctypes.c_int()
            self._call(
                "SLM_GetPulseParameters",
                self._dev,
                slot,
                ctypes.byref(freq),
                ctypes.byref(mode),
                ctypes.byref(htype),
            )
            self._call(
                "SLM_SetPulseParameters",
                self._dev,
                slot,
                int(trigger_index if trigger_index is not None else freq.value),
                int(pulsed if pulsed is not None else mode.value),
            )
        if enabled is not None and self._som >= 0:
            out = self._slms.index(slot)
            o = self._read_oscillator()
            o.output_enabled[out] = bool(enabled)
            self._write_enables(o)

    def _write_enables(self, o: OscillatorState) -> None:
        out_mask = sum(1 << i for i, x in enumerate(o.output_enabled) if x)
        sync_mask = sum(1 << i for i, x in enumerate(o.sync_enabled) if x)
        self._call(
            self._p("SetOutNSyncEnable"),
            self._dev,
            self._som,
            out_mask,
            sync_mask,
            int(o.sync_inverse),
        )

    def _set_oscillator(
        self, base_hz, divider, burst_lengths, output_enabled, sync_enabled, sync_inverse, delays_ns
    ) -> None:
        if self._som < 0:
            raise LaserError(
                "Sepia2: no oscillator module (SOM) -- repetition rate and sequencer are fixed"
            )
        o = self._read_oscillator()
        if base_hz is not None and abs(float(base_hz) - o.base_hz) > 1.0:
            raise LaserError(
                f"the base oscillator runs at {o.base_hz / 1e6:g} MHz; choosing another "
                "oscillator is done on the device (set the divider instead)"
            )
        if divider is not None or sync_inverse is not None:
            self._call(
                self._p("SetBurstValues"),
                self._dev,
                self._som,
                int(divider if divider is not None else o.divider),
                o.pre_sync,
                o.sync_mask,
            )
        if burst_lengths is not None:
            self._call(
                self._p("SetBurstLengthArray"),
                self._dev,
                self._som,
                *[int(n) for n in burst_lengths],
            )
        if output_enabled is not None:
            o.output_enabled = [bool(x) for x in output_enabled]
        if sync_enabled is not None:
            o.sync_enabled = [bool(x) for x in sync_enabled]
        if sync_inverse is not None:
            o.sync_inverse = bool(sync_inverse)
        if output_enabled is not None or sync_enabled is not None or sync_inverse is not None:
            self._write_enables(o)
        if delays_ns is not None and any(delays_ns):
            if not self._somd:
                raise LaserError("per-output delays need an SOM 828-D oscillator module")
            for i, ns in enumerate(delays_ns):
                self._call(
                    "SOMD_SetSeqOutputInfos",
                    self._dev,
                    self._som,
                    i,
                    int(ns > 0),
                    1 << i,
                    0,
                    float(ns),
                    0,
                )


def _parse_frequency(text: str) -> float | None:
    """'internal 80.00 MHz' -> 80e6 (Sepia2's decoded frequency/trigger mode)."""
    m = re.search(r"([\d.]+)\s*([kMG]?)Hz", text or "")
    if not m:
        return None
    return float(m.group(1)) * {"": 1.0, "k": 1e3, "M": 1e6, "G": 1e9}[m.group(2)]


def open_laser(kind: str = "auto", **kwargs) -> LaserBackend:
    """A backend by kind: ``"sepia2"``, ``"simulated"`` or ``"auto"`` (Sepia2 when available)."""
    if kind == "simulated":
        return SimLaser(**kwargs)
    if kind == "sepia2":
        return SepiaBackend(**kwargs)
    if kind == "auto":
        return SepiaBackend(**kwargs) if sepia_available(kwargs.get("library"))[0] else SimLaser()
    raise ValueError(f"unknown laser backend {kind!r}")


# ---------------------------------------------------------------------------------------------
# The PIE scheme a laser program implies
# ---------------------------------------------------------------------------------------------
def pie_slots(laser: dict | LaserState) -> list[dict]:
    """Which enabled head fires when within one sync period, from a laser program.

    Returns one entry per enabled output with pulses, in sequencer order: ``{output, head, name,
    wavelength_nm, start_s, stop_s}`` relative to the start of the sequence (the sync).
    """
    if isinstance(laser, LaserState):
        osc = laser.oscillator
        heads = [asdict(h) for h in laser.heads]
        if osc is None:
            return []
        osc_d = asdict(osc)
    else:
        osc_d = laser.get("oscillator") or {}
        heads = laser.get("heads") or []
        if not osc_d:
            return []
    o = OscillatorState(
        **{k: v for k, v in osc_d.items() if k in OscillatorState.__dataclass_fields__}
    )
    period = 1.0 / o.pulse_rate_hz
    by_output = {int(h.get("output", -1)): h for h in heads}
    slots, t = [], 0.0
    for out, n in enumerate(o.burst_lengths):
        n = int(n)
        if n <= 0:
            continue
        start = t + float(o.delays_ns[out] if out < len(o.delays_ns) else 0.0) * 1e-9
        t += n * period
        if not o.output_enabled[out]:
            continue
        h = by_output.get(out, {})
        slots.append(
            {
                "output": out,
                "head": h.get("slot"),
                "name": h.get("name") or f"output {out + 1}",
                "wavelength_nm": h.get("wavelength_nm"),
                "start_s": start,
                "stop_s": start + n * period,
            }
        )
    return slots


def propose_pie_windows(
    laser: dict | LaserState,
    micro_resolution_s: float,
    *,
    n_micro: int | None = None,
    sync_offset_s: float = 0.0,
    names: list[str] | None = None,
) -> dict:
    """An Experiment-setup patch with micro-time windows from the laser program.

    One window per enabled excitation slot, in micro-time channels ``[lo, hi)`` of
    *micro_resolution_s*, shifted by *sync_offset_s* (the TCSPC sync offset), clipped to
    *n_micro*. Two slots are named ``prompt``/``delayed`` (PIE), otherwise by wavelength (``ex485``)
    or output, unless *names* is given. The patch also carries the sync period and the slots:
    ``{"windows": {...}, "sync_period_s": ..., "excitation": [...]}``.
    """
    slots = pie_slots(laser)
    if not slots:
        return {"windows": {}, "excitation": []}
    if names is None:
        if len(slots) == 2:
            names = ["prompt", "delayed"]
        else:
            names = [
                f"ex{int(s['wavelength_nm'])}"
                if s.get("wavelength_nm")
                else f"out{s['output'] + 1}"
                for s in slots
            ]
    if len(names) != len(slots):
        raise ValueError(f"{len(names)} names for {len(slots)} excitation slots")
    osc = laser.oscillator if isinstance(laser, LaserState) else laser.get("oscillator")
    seq = (
        osc.sequence_period_s
        if isinstance(osc, OscillatorState)
        else OscillatorState(
            **{k: v for k, v in osc.items() if k in OscillatorState.__dataclass_fields__}
        ).sequence_period_s
    )
    windows = {}
    for name, s in zip(names, slots):
        lo = int(round((s["start_s"] - sync_offset_s) / micro_resolution_s))
        hi = int(round((s["stop_s"] - sync_offset_s) / micro_resolution_s))
        lo, hi = max(lo, 0), max(hi, 0)
        if n_micro is not None:
            lo, hi = min(lo, int(n_micro)), min(hi, int(n_micro))
        windows[name] = [lo, hi]
    return {
        "windows": windows,
        "sync_period_s": seq,
        "excitation": [dict(s, window=n) for n, s in zip(names, slots)],
    }
