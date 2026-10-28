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

* :class:`SepiaBackend` -- PicoQuant's Sepia II (PDL 828) through libphacq's native ``sepia``
  driver (USB, no PicoQuant library, Linux / macOS / Windows). Every setting phacq has for the unit
  is reachable through the backend's ``device``; the oscillator module (SOM 828 sequencer) is not
  driven by phacq yet. :func:`sepia_available` says whether a unit is connected.
* :class:`SimLaser` -- the same interface in pure Python, for tests and for the UI without hardware.

:func:`propose_pie_windows` turns a laser program into the micro-time windows of an Experiment setup:
the repetition rate gives the sync period, the sequencer slots give which excitation lies in which
part of it.
"""

from __future__ import annotations

import contextlib
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

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
# Sepia II through libphacq
# ---------------------------------------------------------------------------------------------
def _sepia_units() -> list:
    from chisurf.plugins.core.acq.live import devices

    return devices.attached_devices(("sepia",))


def sepia_available() -> tuple[bool, str]:
    """Whether a Sepia II can be opened here, and which (or why not)."""
    from chisurf.plugins.core.acq.live import devices

    if not devices.PHACQ:
        return False, "not available: libphacq is not installed"
    units = _sepia_units()
    if not units:
        return False, "not available: no Sepia II connected (USB, VID 0x0E0D PID 0x0007)"
    return True, ", ".join(u.label for u in units)


class SepiaBackend(LaserBackend):
    """Sepia II (PDL 828) through libphacq's native ``sepia`` driver -- no PicoQuant library.

    phacq drives the main board (soft lock) and the laser driver modules (SLM: repetition rate or
    external trigger, pulsed / CW, intensity); every setting it has is reachable through
    :attr:`device` (``device.schema()`` / ``device.settings()`` / ``device.apply()``), which the
    Record tool renders as a whole. An oscillator module (SOM 828 sequencer) is not driven by
    phacq yet: :attr:`LaserState.oscillator` stays ``None`` and setting one raises.
    """

    kind = "sepia"

    def __init__(self, serial: str = "") -> None:
        super().__init__()
        self._serial = str(serial)
        self.device = None
        self._slots: list[int] = []

    @classmethod
    def available(cls) -> tuple[bool, str]:
        return sepia_available()

    def _open_device(self, index: int) -> None:
        from chisurf.plugins.core.acq.live import devices

        units = _sepia_units()
        if self._serial:
            units = [u for u in units if u.serial == self._serial] or units
        if not units or index >= len(units):
            raise LaserError(sepia_available()[1])
        self.device = devices.open_device(units[index])
        settings = self.device.settings()
        n = int(self.device.schema().get("channels", 0))
        self._slots = [int(settings.get(f"slot[{c}]") or 0) for c in range(n)]

    def _close_device(self) -> None:
        if self.device is not None:
            self.device.close()
        self.device = None

    def _channel(self, slot: int) -> int:
        try:
            return self._slots.index(int(slot))
        except ValueError:
            raise LaserError(f"no laser driver in slot {slot} (slots {self._slots})") from None

    def _read_state(self) -> LaserState:
        s = self.device.settings()
        info = self.device.information()
        heads = []
        for c, slot in enumerate(self._slots):
            heads.append(
                HeadState(
                    slot=slot,
                    name=f"SLM {slot}",
                    kind="laser",
                    output=-1,
                    pulsed=bool(s.get(f"pulse_mode[{c}]", 1)),
                    intensity_pct=float(s.get(f"intensity_permille[{c}]") or 0) / 10.0,
                    trigger_index=int(s.get(f"frequency_index[{c}]") or 0),
                )
            )
        return LaserState(
            model=str(info.model),
            serial=str(info.serial_number),
            library="libphacq",
            heads=heads,
            oscillator=None,
            emission_blocked=bool(s.get("soft_lock", True)),
            warnings=list(self._state.warnings),
        )

    def _set_emission(self, on: bool) -> None:
        self.device.apply({"soft_lock": not on})

    def _set_head(self, slot, enabled, intensity_pct, pulsed, trigger_index) -> None:
        c = self._channel(slot)
        values: dict = {}
        if intensity_pct is not None:
            values[f"intensity_permille[{c}]"] = int(round(float(intensity_pct) * 10.0))
        if pulsed is not None:
            values[f"pulse_mode[{c}]"] = int(bool(pulsed))
        if trigger_index is not None:
            values[f"frequency_index[{c}]"] = int(trigger_index)
        if enabled is not None and not enabled:
            # A head is switched by its oscillator output; without an oscillator module the soft
            # lock is the switch (all heads).
            note = f"slot {slot}: no oscillator output to disable it; the soft lock switches all"
            if note not in self._state.warnings:
                self._state.warnings.append(note)
        if values:
            self.device.apply(values)

    def _set_oscillator(
        self, base_hz, divider, burst_lengths, output_enabled, sync_enabled, sync_inverse, delays_ns
    ) -> None:
        raise LaserError(
            "phacq does not drive a Sepia II oscillator module (SOM 828) yet; "
            "the laser drivers run on their own oscillator or an external trigger"
        )


def _parse_frequency(text: str) -> float | None:
    """'internal 80.00 MHz' -> 80e6 (Sepia2's decoded frequency/trigger mode)."""
    m = re.search(r"([\d.]+)\s*([kMG]?)Hz", text or "")
    if not m:
        return None
    return float(m.group(1)) * {"": 1.0, "k": 1e3, "M": 1e6, "G": 1e9}[m.group(2)]


def open_laser(kind: str = "auto", **kwargs) -> LaserBackend:
    """A backend by kind: ``"sepia"`` (libphacq; ``"sepia2"`` in older settings files),
    ``"simulated"`` or ``"auto"`` (a connected Sepia II, else the simulator)."""
    if kind == "simulated":
        return SimLaser(**kwargs)
    if kind in ("sepia", "sepia2"):
        return SepiaBackend(**kwargs)
    if kind == "auto":
        return SepiaBackend(**kwargs) if sepia_available()[0] else SimLaser()
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


def ptu_tags(backend: LaserBackend | None, program: dict | None = None) -> dict:
    """The laser's state as PTU header tags, under the names SymPhoTime writes for a Sepia II
    (checked against an MT200 recording): ``Sep2_SerialNo``, per laser driver module
    ``Sep2_SLM_<slot>_SerialNo/FineIntensity/TriggerIndex/CW_PulseDisable/HeadType``, and the
    heads' names ``UsrHeadName(<i>)`` from the program. An indexed tag is ``Name(i)``.

    Empty for a backend that is not a phacq device (the simulated laser).
    """
    dev = getattr(backend, "device", None)
    if dev is None:
        return {}
    tags: dict = {}
    try:
        s = dict(dev.settings())
        info = dev.information()
    except Exception:  # noqa: BLE001 - a laser that cannot report: no tags
        return {}
    tags["Sep2_SerialNo"] = str(info.serial_number)
    head_types = {1: "LED", 2: "LASER", 3: "LASER"}
    c = 0
    while f"slot[{c}]" in s:
        slot = int(s.get(f"slot[{c}]") or 0)
        pre = f"Sep2_SLM_{slot:03d}_"
        if s.get(f"intensity_permille[{c}]") is not None:
            tags[pre + "FineIntensity"] = int(round(float(s[f"intensity_permille[{c}]"]) / 10))
        if s.get(f"frequency_index[{c}]") is not None:
            tags[pre + "TriggerIndex"] = int(s[f"frequency_index[{c}]"])
        if s.get(f"pulse_mode[{c}]") is not None:
            tags[pre + "CW_PulseDisable"] = not bool(s[f"pulse_mode[{c}]"])
        if s.get(f"head_type[{c}]") is not None:
            tags[pre + "HeadType"] = head_types.get(int(s[f"head_type[{c}]"]), "LASER")
        c += 1
    for i, head in enumerate((program or {}).get("heads") or []):
        if head.get("name"):
            tags[f"UsrHeadName({i})"] = str(head["name"])
    return tags
