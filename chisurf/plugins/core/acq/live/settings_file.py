"""Acquisition settings files: one readable JSON document for a whole measurement.

A settings file holds what the Record tool needs to repeat a measurement -- the TCSPC device, the
laser program, the experiment (measurement type, channel setup, burst rule), the run and the
simulator -- in plain JSON that a person can read and edit::

    {
      "schema": "chisurf.acquisition/1",
      "name": "PIE smFRET, 485/640",
      "device": {"backend": "pqusb", "model": "MultiHarp", "mode": "T3", "refsource": 0,
                 "sync": {"divider": 1, "level_mv": -50, "edge": "falling", "offset_ps": 0},
                 "inputs": [{"channel": 0, "level_mv": -50, "edge": "falling", "offset_ps": 0,
                             "enabled": true}],
                 "binning": 0, "offset_ns": 0},
      "laser": {"backend": "sepia2", "heads": [{"slot": 200, "output": 0, "enabled": true,
                                                 "intensity_pct": 40.0}],
                "oscillator": {"divider": 4, "burst_lengths": [1, 1, 0, 0, 0, 0, 0, 0],
                               "output_enabled": [true, true, false, false, false, false, false, false]}},
      "experiment": {"preset": "pie", "setup": {"detectors": {...}, "windows": {...}},
                     "burst": {"min_photons": 30, "window_photons": 10, "window_time_ms": 1.0}},
      "run": {"duration_s": 600, "name": "sample_{date}", "project_data": "link"},
      "scan": {"pixels_x": 64, "pixels_y": 64, "area_x_um": 16, "area_y_um": 16, "dwell_ms": 0.1,
               "frames": 1, "bidirectional": false, "z_planes": 1},
      "simulator": {}
    }

Every section is optional; keys this module does not know are kept as they are, so a file written by
a newer ChiSurf survives a round trip through an older one. :func:`validate` lists every problem with
its path (``device.inputs[1].level_mv``) rather than stopping at the first.

Settings also come back out of old measurements: :func:`from_ptu` reads a PicoQuant PTU header (the
TCSPC settings and, where SymPhoTime recorded them, the Sepia II program); :func:`from_header_json`
reads the header tttrlib keeps for a photon stream (a ``.pto`` member or a workspace dataset's
``header_json``). Both report which fields the measurement did not record.

These files enter ChiSurf like every input, through the workspace drop: ``chisurf.core.fio.classify``
sorts a JSON with this ``schema`` as a ``setup``.
"""

from __future__ import annotations

import copy
import json
import math
import re
import struct
from pathlib import Path
from typing import Any

#: The schema identifier this module writes; files with the same major version are read.
SCHEMA = "chisurf.acquisition/1"
SCHEMA_PREFIX = "chisurf.acquisition/"
#: Measurement types the live analysis knows (tttrlib StreamingBurstAnalyzer presets).
PRESETS = ("single_color", "two_color", "pie", "alex", "mfd", "three_color_pie")
MODES = {"T2": 2, "T3": 3}
EDGES = {"falling": 0, "rising": 1}
PROJECT_DATA = ("link", "embed")
#: Sync dividers PicoQuant TCSPC units accept.
SYNC_DIVIDERS = (1, 2, 4, 8, 16)


class SettingsError(ValueError):
    """A settings document is invalid; ``problems`` lists every finding with its path."""

    def __init__(self, problems: list[str], source: str = "") -> None:
        self.problems = list(problems)
        where = f"{source}: " if source else ""
        super().__init__(where + "; ".join(self.problems))


# ---------------------------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------------------------
def new_settings(**sections: Any) -> dict:
    """An empty settings document, with the given sections filled in."""
    doc: dict = {"schema": SCHEMA}
    doc.update(copy.deepcopy(sections))
    return doc


def is_acquisition_settings(data: Any) -> bool:
    """Whether *data* (a parsed JSON value) is an acquisition settings document."""
    return isinstance(data, dict) and str(data.get("schema", "")).startswith(SCHEMA_PREFIX)


def _num(
    problems: list[str],
    where: str,
    value: Any,
    lo: float | None = None,
    hi: float | None = None,
    integer: bool = False,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (isinstance(value, float) and not math.isfinite(value))
    ):
        problems.append(f"{where}: expected a number, got {value!r}")
        return
    if integer and int(value) != value:
        problems.append(f"{where}: expected a whole number, got {value!r}")
    if lo is not None and value < lo:
        problems.append(f"{where}: {value} is below {lo}")
    if hi is not None and value > hi:
        problems.append(f"{where}: {value} is above {hi}")


def _choice(problems: list[str], where: str, value: Any, allowed) -> None:
    if value not in allowed:
        problems.append(f"{where}: {value!r} is not one of {', '.join(map(str, allowed))}")


def _trigger(problems: list[str], where: str, t: Any) -> None:
    if not isinstance(t, dict):
        problems.append(f"{where}: expected an object")
        return
    if "level_mv" in t:
        _num(problems, f"{where}.level_mv", t["level_mv"], -1200, 1200)
    if "zero_cross_mv" in t:
        _num(problems, f"{where}.zero_cross_mv", t["zero_cross_mv"], -100, 100)
    if "edge" in t:
        _choice(problems, f"{where}.edge", t["edge"], tuple(EDGES))
    if "offset_ps" in t:
        _num(
            problems, f"{where}.offset_ps", t["offset_ps"], -100_000_000, 100_000_000, integer=True
        )
    if "dead_time_ps" in t and t["dead_time_ps"] is not None:
        _num(problems, f"{where}.dead_time_ps", t["dead_time_ps"], 0, 1e7)
    if "enabled" in t and not isinstance(t["enabled"], bool):
        problems.append(f"{where}.enabled: expected true or false")


def validate(doc: Any) -> list[str]:
    """Every problem in *doc*, each with its path; an empty list means valid."""
    p: list[str] = []
    if not isinstance(doc, dict):
        return ["expected a JSON object at the top level"]
    schema = doc.get("schema")
    if schema is None:
        p.append(f"schema: missing (expected {SCHEMA!r})")
    elif not str(schema).startswith(SCHEMA_PREFIX):
        p.append(f"schema: {schema!r} is not an acquisition settings file")
    elif str(schema).split("/", 1)[1].split(".")[0] != SCHEMA.split("/", 1)[1]:
        p.append(f"schema: version {schema!r} is newer than this ChiSurf reads ({SCHEMA!r})")
    for key in ("device", "laser", "experiment", "run", "simulator", "scan"):
        if key in doc and not isinstance(doc[key], dict):
            p.append(f"{key}: expected an object")
    dev = doc.get("device") if isinstance(doc.get("device"), dict) else {}
    if "mode" in dev:
        _choice(p, "device.mode", dev["mode"], tuple(MODES))
    if "refsource" in dev:
        _num(p, "device.refsource", dev["refsource"], 0, 10, integer=True)
    if "sync" in dev:
        _trigger(p, "device.sync", dev["sync"])
        if isinstance(dev["sync"], dict) and "divider" in dev["sync"]:
            _choice(p, "device.sync.divider", dev["sync"]["divider"], SYNC_DIVIDERS)
    seen: set[int] = set()
    for i, ch in enumerate(dev.get("inputs") or []):
        where = f"device.inputs[{i}]"
        _trigger(p, where, ch)
        if isinstance(ch, dict):
            if "channel" not in ch:
                p.append(f"{where}.channel: missing")
            else:
                _num(p, f"{where}.channel", ch["channel"], 0, 63, integer=True)
                if ch["channel"] in seen:
                    p.append(f"{where}.channel: {ch['channel']} appears twice")
                seen.add(ch["channel"])
    if "binning" in dev:
        _num(p, "device.binning", dev["binning"], 0, 24, integer=True)
    if "offset_ns" in dev:
        _num(p, "device.offset_ns", dev["offset_ns"], 0, 1e9, integer=True)
    las = doc.get("laser") if isinstance(doc.get("laser"), dict) else {}
    for i, h in enumerate(las.get("heads") or []):
        where = f"laser.heads[{i}]"
        if not isinstance(h, dict):
            p.append(f"{where}: expected an object")
            continue
        if "slot" not in h:
            p.append(f"{where}.slot: missing")
        if "intensity_pct" in h:
            _num(p, f"{where}.intensity_pct", h["intensity_pct"], 0, 100)
        if "output" in h:
            _num(p, f"{where}.output", h["output"], -1, 7, integer=True)
    osc = las.get("oscillator")
    if osc is not None:
        if not isinstance(osc, dict):
            p.append("laser.oscillator: expected an object")
        else:
            if "divider" in osc:
                _num(p, "laser.oscillator.divider", osc["divider"], 1, 65535, integer=True)
            if "base_hz" in osc:
                _num(p, "laser.oscillator.base_hz", osc["base_hz"], 1)
            for key in ("burst_lengths", "output_enabled", "sync_enabled", "delays_ns"):
                if key in osc and (not isinstance(osc[key], list) or len(osc[key]) != 8):
                    p.append(f"laser.oscillator.{key}: expected a list of 8 entries")
            for j, n in enumerate(
                osc.get("burst_lengths") or [] if isinstance(osc.get("burst_lengths"), list) else []
            ):
                _num(p, f"laser.oscillator.burst_lengths[{j}]", n, 0, 2**24, integer=True)
    exp = doc.get("experiment") if isinstance(doc.get("experiment"), dict) else {}
    if "preset" in exp and exp["preset"] not in (None, "", "auto"):
        _choice(p, "experiment.preset", exp["preset"], PRESETS + ("auto",))
    if "setup" in exp and not isinstance(exp["setup"], dict):
        p.append("experiment.setup: expected an object (a channel definition)")
    burst = exp.get("burst") if isinstance(exp.get("burst"), dict) else {}
    if "min_photons" in burst:
        _num(p, "experiment.burst.min_photons", burst["min_photons"], 1, 1e9, integer=True)
    if "window_photons" in burst:
        _num(p, "experiment.burst.window_photons", burst["window_photons"], 1, 1e6, integer=True)
    if "window_time_ms" in burst:
        _num(p, "experiment.burst.window_time_ms", burst["window_time_ms"], 1e-6, 1e6)
    trace = exp.get("trace") if isinstance(exp.get("trace"), dict) else {}
    if "window_s" in trace:
        _num(p, "experiment.trace.window_s", trace["window_s"], 1e-3, 3600)
    if "bin_ms" in trace:
        _num(p, "experiment.trace.bin_ms", trace["bin_ms"], 1e-4, 1e5)
    if isinstance(doc.get("scan"), dict):
        from .scanner import ScanSettings

        try:
            scan = ScanSettings.from_dict(doc["scan"])
        except (TypeError, ValueError) as exc:
            p.append(f"scan: {exc}")
        else:
            p += [f"scan.{problem}" for problem in scan.validate()]
    run = doc.get("run") if isinstance(doc.get("run"), dict) else {}
    if "duration_s" in run and run["duration_s"] is not None:
        _num(p, "run.duration_s", run["duration_s"], 0, 360_000)
    if "project_data" in run:
        _choice(p, "run.project_data", run["project_data"], PROJECT_DATA)
    return p


def loads(text: str, source: str = "") -> dict:
    """Parse and validate a settings document; raises :class:`SettingsError` with every problem."""
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise SettingsError([f"not valid JSON: {e}"], source) from e
    problems = validate(doc)
    if problems:
        raise SettingsError(problems, source)
    return doc


def load(path: str | Path) -> dict:
    """Read and validate a settings file."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SettingsError([f"cannot read: {e}"], str(path)) from e
    return loads(text, str(path))


def dumps(doc: dict) -> str:
    """The document as indented JSON (validated first)."""
    problems = validate(doc)
    if problems:
        raise SettingsError(problems)
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def save(doc: dict, path: str | Path) -> Path:
    """Validate and write *doc*; returns the path."""
    path = Path(path)
    text = dumps(doc)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------------------------
# Device (a pqusb TcspcDevice, duck-typed -- pqusb is not imported here)
# ---------------------------------------------------------------------------------------------
def apply_device(dev: Any, device: dict, *, initialize: bool = True) -> list[str]:
    """Apply the ``device`` section to a pqusb ``TcspcDevice``.

    Initializes the device first (mode, reference source) unless *initialize* is false. Settings
    the device does not implement are skipped and returned as notes rather than failing the run.
    """
    notes: list[str] = []
    if initialize:
        dev.initialize(MODES.get(device.get("mode", "T3"), 3), int(device.get("refsource", 0)))

    def call(name: str, *args) -> None:
        fn = getattr(dev, name, None)
        if fn is None:
            notes.append(f"{name}: not offered by {type(dev).__name__}")
            return
        try:
            fn(*args)
        except Exception as e:  # pqusb raises DeviceError for unsupported setters
            notes.append(f"{name}{args}: {e}")

    sync = device.get("sync") or {}
    if "divider" in sync:
        call("set_sync_div", int(sync["divider"]))
    if "level_mv" in sync or "edge" in sync:
        call(
            "set_sync_edge_trg", int(sync.get("level_mv", -50)), EDGES[sync.get("edge", "falling")]
        )
    if "offset_ps" in sync:
        call("set_sync_channel_offset", int(sync["offset_ps"]))
    if sync.get("dead_time_ps") is not None:
        call("set_sync_dead_time", True, int(sync["dead_time_ps"]))
    nchan = int(getattr(dev, "nchan", 0) or 0)
    for ch in device.get("inputs") or []:
        c = int(ch["channel"])
        if nchan and c >= nchan:
            notes.append(f"input {c}: the device has {nchan} inputs")
            continue
        if "level_mv" in ch or "edge" in ch:
            call(
                "set_input_edge_trg",
                c,
                int(ch.get("level_mv", -50)),
                EDGES[ch.get("edge", "falling")],
            )
        if "offset_ps" in ch:
            call("set_input_channel_offset", c, int(ch["offset_ps"]))
        if "enabled" in ch:
            call("set_input_channel_enable", c, bool(ch["enabled"]))
        if ch.get("dead_time_ps") is not None:
            call("set_input_dead_time", c, True, int(ch["dead_time_ps"]))
    if "binning" in device:
        call("set_binning", int(device["binning"]))
    if "offset_ns" in device:
        call("set_offset", int(device["offset_ns"]))
    markers = device.get("markers") or {}
    if markers.get("edges"):
        call("set_marker_edges", *[EDGES.get(e, e) for e in markers["edges"]])
    if markers.get("enabled"):
        call("set_marker_enable", *[int(bool(x)) for x in markers["enabled"]])
    if "holdoff_ns" in markers:
        call("set_marker_holdoff", int(markers["holdoff_ns"]))
    return notes


def _edge_name(e: int) -> str:
    return "rising" if int(e) else "falling"


def capture_device(dev: Any) -> dict:
    """The device's current settings as a ``device`` section (what the driver last sent)."""
    s = dev.settings
    ident = getattr(dev, "identity", None)
    mode = {v: k for k, v in MODES.items()}.get(getattr(dev, "mode", None), "T3")
    out = {
        "backend": "pqusb",
        "model": getattr(ident, "model", "") or getattr(dev, "hw_type", ""),
        "serial": getattr(ident, "serial", ""),
        "mode": mode,
        "sync": {
            "divider": int(s.sync_div),
            "level_mv": int(s.sync.level_mv),
            "edge": _edge_name(s.sync.edge),
            "offset_ps": int(s.sync.offset_ps),
        },
        "inputs": [
            {
                "channel": i,
                "level_mv": int(ch.level_mv),
                "edge": _edge_name(ch.edge),
                "offset_ps": int(ch.offset_ps),
                "enabled": bool(ch.enabled),
            }
            for i, ch in enumerate(s.inputs)
        ],
        "binning": int(s.binning),
        "offset_ns": int(s.offset_ns),
    }
    with _suppress():
        out["resolution_ps"] = round(dev.resolution_s() * 1e12, 6)
    return out


class _suppress:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True


def apply(
    doc: dict, *, device: Any = None, laser: Any = None, initialize: bool = True
) -> list[str]:
    """Apply a whole settings document to a device and/or a laser backend; returns notes.

    The laser's emission stays blocked (:meth:`LaserBackend.apply`); the caller enables it.
    """
    problems = validate(doc)
    if problems:
        raise SettingsError(problems)
    notes: list[str] = []
    if device is not None and doc.get("device"):
        notes += apply_device(device, doc["device"], initialize=initialize)
    if laser is not None and doc.get("laser"):
        laser.apply(doc["laser"])
    return notes


def capture(*, device: Any = None, laser: Any = None, base: dict | None = None) -> dict:
    """A settings document from the current device/laser state, on top of *base* (kept otherwise)."""
    doc = copy.deepcopy(base) if base else new_settings()
    doc["schema"] = SCHEMA
    if device is not None:
        doc["device"] = {**(doc.get("device") or {}), **capture_device(device)}
    if laser is not None:
        doc["laser"] = {**(doc.get("laser") or {}), **laser.capture()}
    return doc


# ---------------------------------------------------------------------------------------------
# Settings from old measurements
# ---------------------------------------------------------------------------------------------
#: The tag ChiSurf stores a whole settings document in (an ANSI string tag in the PTU header).
CHISURF_SETTINGS_TAG = "ChiSurf_AcquisitionSettings"


def _tags_from_list(tags: list[dict]) -> dict:
    out: dict = {}
    for t in tags:
        name, idx = t.get("name"), int(t.get("idx", -1))
        out[f"{name}({idx})" if idx > -1 else name] = t.get("value")
    return out


def _indexed(tags: dict, name: str) -> dict[int, Any]:
    out = {}
    pat = re.compile(re.escape(name) + r"\((\d+)\)$")
    for k, v in tags.items():
        m = pat.match(k)
        if m:
            out[int(m.group(1))] = v
    return out


def _mode_from(tags: dict) -> str | None:
    rt = tags.get("TTResultFormat_TTTRRecType")
    if isinstance(rt, int):
        return {2: "T2", 3: "T3"}.get((rt >> 8) & 0xFF)
    mm = tags.get("Measurement_Mode")
    return {2: "T2", 3: "T3"}.get(mm) if isinstance(mm, int) else None


def from_ptu_tags(tags: dict | list) -> tuple[dict, list[str]]:
    """A settings document from PicoQuant header tags, and the fields the header did not record.

    *tags* is ``{"Name": value, "Name(idx)": value}`` (pqusb's ``read_header``, :func:`read_ptu_tags`)
    or tttrlib's header JSON tag list. A ``ChiSurf_AcquisitionSettings`` tag, when present, is the
    document itself and is returned as written.
    """
    if isinstance(tags, list):
        tags = _tags_from_list(tags)
    stored = tags.get(CHISURF_SETTINGS_TAG)
    if isinstance(stored, str) and stored.strip():
        with _suppress():
            doc = json.loads(stored)
            if is_acquisition_settings(doc):
                return doc, []
    missing: list[str] = []
    dev: dict = {"backend": "pqusb"}
    hw = tags.get("HW_Type")
    if hw:
        dev["model"] = str(hw)
    else:
        missing.append("device.model")
    if tags.get("HW_SerialNo"):
        dev["serial"] = str(tags["HW_SerialNo"])
    mode = _mode_from(tags)
    if mode:
        dev["mode"] = mode
    else:
        missing.append("device.mode")
    sync: dict = {}
    if "HWSync_Divider" in tags:
        sync["divider"] = int(tags["HWSync_Divider"])
    else:
        missing.append("device.sync.divider")
    if "HWSync_TrgLevel" in tags:
        sync["level_mv"] = int(tags["HWSync_TrgLevel"])
        if "HWSync_TrgEdge" in tags:
            sync["edge"] = _edge_name(tags["HWSync_TrgEdge"])
    elif "HWSync_CFDLevel" in tags:
        # A CFD unit (PicoHarp 300, HydraHarp 400, TimeHarp 260 PICO): the level is a CFD
        # discriminator level; zero cross is kept so a CFD device can be set back up exactly.
        sync["level_mv"] = int(tags["HWSync_CFDLevel"])
        sync["zero_cross_mv"] = int(tags.get("HWSync_CFDZeroCross", 0))
        sync["discriminator"] = "cfd"
    else:
        missing.append("device.sync.level_mv")
    if "HWSync_Offset" in tags:
        sync["offset_ps"] = int(tags["HWSync_Offset"])
    if sync:
        dev["sync"] = sync
    levels = _indexed(tags, "HWInpChan_TrgLevel") or _indexed(tags, "HWInpChan_CFDLevel")
    cfd = not _indexed(tags, "HWInpChan_TrgLevel") and bool(levels)
    edges = _indexed(tags, "HWInpChan_TrgEdge")
    zero = _indexed(tags, "HWInpChan_CFDZeroCross")
    offsets = _indexed(tags, "HWInpChan_Offset")
    enabled = _indexed(tags, "HWInpChan_Enabled")
    chans = sorted(set(levels) | set(offsets) | set(enabled))
    inputs = []
    for c in chans:
        ch: dict = {"channel": c}
        if c in levels:
            ch["level_mv"] = int(levels[c])
        if cfd:
            ch["discriminator"] = "cfd"
            if c in zero:
                ch["zero_cross_mv"] = int(zero[c])
        elif c in edges:
            ch["edge"] = _edge_name(edges[c])
        if c in offsets:
            ch["offset_ps"] = int(offsets[c])
        if c in enabled:
            ch["enabled"] = bool(enabled[c])
        inputs.append(ch)
    if inputs:
        dev["inputs"] = inputs
    else:
        missing.append("device.inputs")
    if "MeasDesc_BinningFactor" in tags:
        f = int(tags["MeasDesc_BinningFactor"]) or 1
        dev["binning"] = int(round(math.log2(f)))
    else:
        missing.append("device.binning")
    if "MeasDesc_Offset" in tags:
        dev["offset_ns"] = int(tags["MeasDesc_Offset"])
    if "MeasDesc_Resolution" in tags:
        dev["resolution_ps"] = round(float(tags["MeasDesc_Resolution"]) * 1e12, 6)
    if "HW_BaseResolution" in tags:
        dev["base_resolution_ps"] = round(float(tags["HW_BaseResolution"]) * 1e12, 6)
    if "TTResult_SyncRate" in tags:
        dev["measured_sync_rate_hz"] = int(tags["TTResult_SyncRate"])
    m_en = _indexed(tags, "HWMarkers_Enabled")
    if m_en:
        m_edge = _indexed(tags, "HWMarkers_RisingEdge")
        dev["markers"] = {
            "enabled": [bool(m_en[i]) for i in sorted(m_en)],
            "edges": ["rising" if m_edge.get(i) else "falling" for i in sorted(m_en)],
        }
        if "HWMarkers_HoldOff" in tags:
            dev["markers"]["holdoff_ns"] = int(tags["HWMarkers_HoldOff"])
    missing += ["device.sync.dead_time_ps", "device.inputs[*].dead_time_ps"]

    doc = new_settings(device=dev)
    laser = _laser_from_tags(tags)
    if laser:
        doc["laser"] = laser
        if "laser.oscillator.delays_ns" not in missing:
            missing.append("laser.oscillator.delays_ns")
    else:
        missing.append("laser")
    acq = tags.get("MeasDesc_AcquisitionTime")
    if isinstance(acq, (int, float)) and acq > 0:
        doc["run"] = {"duration_s": float(acq) / 1e3}
    missing += ["experiment.preset", "experiment.setup", "experiment.burst"]
    if any(str(k).startswith("ImgHdr_") for k in tags):
        from .scanner import scan_from_tags

        scan, scan_missing = scan_from_tags(
            {k: v for k, v in tags.items() if "(" not in str(k)}
        )
        if scan is not None:
            doc["scan"] = scan.to_dict()
        missing += scan_missing
    if doc.get("laser") and "MeasDesc_Resolution" in tags:
        from chisurf.plugins.core.acq.live.laser import propose_pie_windows

        prop = propose_pie_windows(
            doc["laser"], float(tags["MeasDesc_Resolution"]), sync_offset_s=0.0
        )
        if len(prop.get("windows") or {}) >= 2:
            doc["experiment"] = {"proposed_windows": prop["windows"]}
    return doc, missing


def _laser_from_tags(tags: dict) -> dict | None:
    """The Sepia II program SymPhoTime records as ``Sep2_*`` tags."""
    soms = sorted({m.group(1) for k in tags for m in [re.match(r"Sep2_(SOMD?_\d+)_", k)] if m})
    slms = sorted(
        {m.group(1) for k in tags for m in [re.match(r"Sep2_SLM_(\d+)_", k)] if m}, key=int
    )
    if not soms and not slms:
        return None
    laser: dict = {"backend": "sepia2", "heads": []}
    if tags.get("Sep2_SerialNo"):
        laser["serial"] = str(tags["Sep2_SerialNo"])
    if tags.get("Sep2_FirmwareVersion"):
        laser["firmware"] = str(tags["Sep2_FirmwareVersion"])
    if soms:
        pre = f"Sep2_{soms[0]}_"
        osc: dict = {}
        if f"{pre}BaseOscFreq" in tags:
            osc["base_hz"] = float(tags[f"{pre}BaseOscFreq"])
        if f"{pre}Divider" in tags:
            osc["divider"] = int(tags[f"{pre}Divider"])
        if f"{pre}PreSync" in tags:
            osc["pre_sync"] = int(tags[f"{pre}PreSync"])
        if f"{pre}SyncMask" in tags:
            osc["sync_mask"] = int(tags[f"{pre}SyncMask"])
        if f"{pre}InvSyncMask" in tags:
            osc["sync_inverse"] = bool(tags[f"{pre}InvSyncMask"])
        lens = _indexed(tags, f"{pre}Seq_BurstLen")
        if lens:
            osc["burst_lengths"] = [int(lens.get(i, 0)) for i in range(8)]
        ena = _indexed(tags, f"{pre}Seq_EnaOutput")
        if ena:
            osc["output_enabled"] = [bool(ena.get(i, False)) for i in range(8)]
        sync = _indexed(tags, f"{pre}Seq_EnaSync")
        if sync:
            osc["sync_enabled"] = [bool(sync.get(i, False)) for i in range(8)]
        laser["oscillator"] = osc
    names = _indexed(tags, "UsrHeadName")
    for i, slot in enumerate(slms):
        pre = f"Sep2_SLM_{slot}_"
        head: dict = {"slot": int(slot), "output": i}
        if i in names:
            head["name"] = str(names[i])
            m = re.match(r"\s*([\d.]+)\s*nm", str(names[i]))
            if m:
                head["wavelength_nm"] = float(m.group(1))
        if f"{pre}FineIntensity" in tags:
            head["intensity_pct"] = float(tags[f"{pre}FineIntensity"]) / 10.0
        if f"{pre}TriggerIndex" in tags:
            head["trigger_index"] = int(tags[f"{pre}TriggerIndex"])
        if f"{pre}CW_PulseDisable" in tags:
            head["pulsed"] = not bool(tags[f"{pre}CW_PulseDisable"])
        if f"{pre}SerialNo" in tags:
            head["serial"] = str(tags[f"{pre}SerialNo"])
        if f"{pre}HeadType" in tags:
            head["kind"] = str(tags[f"{pre}HeadType"]).lower()
        osc = laser.get("oscillator") or {}
        if osc.get("output_enabled") and i < 8:
            head["enabled"] = bool(osc["output_enabled"][i]) and str(names.get(i, "")) != "Disabled"
        laser["heads"].append(head)
    return laser


# PicoQuant tag types (PTU file format demos, public).
_TY_EMPTY8, _TY_BOOL8, _TY_INT8, _TY_BITSET64, _TY_COLOR8 = (
    0xFFFF0008,
    0x00000008,
    0x10000008,
    0x11000008,
    0x12000008,
)
_TY_FLOAT8, _TY_TDATETIME, _TY_FLOAT8ARRAY = 0x20000008, 0x21000008, 0x2001FFFF
_TY_ANSISTRING, _TY_WIDESTRING, _TY_BINARYBLOB = 0x4001FFFF, 0x4002FFFF, 0xFFFFFFFF


def read_ptu_tags(path: str | Path) -> dict:
    """The header tags of a PTU file, without reading its records (``{"Name(idx)": value}``)."""
    with open(path, "rb") as f:
        return _parse_ptu_header(f, str(path))


def _parse_ptu_header(f, source: str = "") -> dict:
    tags: dict = {}
    if f.read(8).rstrip(b"\0") != b"PQTTTR":
        raise SettingsError(["not a PicoQuant PTU file"], source)
    f.read(8)
    while True:
        head = f.read(48)
        if len(head) < 48:
            raise SettingsError(["the header ends before Header_End"], source)
        name = head[:32].rstrip(b"\0").decode("ascii", "replace")
        idx, typ = struct.unpack("<iI", head[32:40])
        raw = head[40:48]
        key = f"{name}({idx})" if idx > -1 else name
        if typ in (_TY_ANSISTRING, _TY_WIDESTRING, _TY_BINARYBLOB, _TY_FLOAT8ARRAY):
            n = struct.unpack("<q", raw)[0]
            data = f.read(n)
            if typ == _TY_ANSISTRING:
                value: Any = data.split(b"\0", 1)[0].decode("utf-8", "replace")
            elif typ == _TY_WIDESTRING:
                value = data.decode("utf-16le", "ignore").rstrip("\0")
            else:
                value = None  # blobs and float arrays carry no settings
        elif typ in (_TY_FLOAT8, _TY_TDATETIME):
            value = struct.unpack("<d", raw)[0]
        elif typ == _TY_BOOL8:
            # PicoQuant: true is any non-zero 64-bit value (written as -1).
            value = struct.unpack("<q", raw)[0] != 0
        elif typ == _TY_EMPTY8:
            value = None
        else:
            value = struct.unpack("<q", raw)[0]
        tags[key] = value
        if name == "Header_End":
            return tags


def from_ptu(path: str | Path) -> tuple[dict, list[str]]:
    """Settings recorded in a PTU file's header (records are not read)."""
    return from_ptu_tags(read_ptu_tags(path))


#: Bool8 tag type code in tttrlib's header JSON.
_HEADER_JSON_BOOL8 = 8


def from_header_json(header_json: str) -> tuple[dict, list[str]]:
    """Settings from tttrlib's header JSON (``TTTR.header.json``, a dataset's ``header_json``).

    tttrlib's PicoQuant reader decodes boolean tags from one byte of the 64-bit value, so a
    PicoQuant "true" (``-1``) arrives as ``false``; boolean tags are therefore not used here and the
    fields they carry (enabled inputs, markers and laser outputs) are reported as not recovered.
    Prefer :func:`from_ptu` / :func:`from_address`, which read the PTU header itself.
    """
    try:
        data = json.loads(header_json)
    except (TypeError, ValueError) as e:
        raise SettingsError([f"the header is not JSON: {e}"]) from e
    tags = data.get("tags") if isinstance(data, dict) else data
    if not isinstance(tags, list):
        raise SettingsError(["the header has no tag list"])
    dropped = sorted({t.get("name") for t in tags if t.get("type") == _HEADER_JSON_BOOL8})
    doc, missing = from_ptu_tags([t for t in tags if t.get("type") != _HEADER_JSON_BOOL8])
    missing += [f"{name} (boolean tag; tttrlib header JSON misreads it)" for name in dropped]
    return doc, missing


def from_address(address: str) -> tuple[dict, list[str]]:
    """Settings of the measurement at *address*: a ``.ptu`` file, a PTU member of a ``.pto``
    container (its own header is read), or any other photon stream ChiSurf opens (through its
    header JSON, see :func:`from_header_json`)."""
    import io

    path = Path(address)
    if path.suffix.lower() == ".ptu" and path.is_file():
        return from_ptu(path)
    from chisurf.core.fio.address import split_address

    container, member = split_address(address)
    if container is not None and member and member.lower().endswith(".ptu"):
        from chisurf.core.fio import pto

        blob = pto.Measurement.open(container).get_blob(member)
        return from_ptu_tags(_parse_ptu_header(io.BytesIO(blob), str(address)))
    from chisurf.core.fio import staging

    tttr = staging.open_tttr(str(address), apply_lut=False)
    return from_header_json(tttr.header.json)


def from_dataset(dataset: Any) -> tuple[dict, list[str]]:
    """Settings of a workspace photon dataset (its stored header, else its address)."""
    header = getattr(dataset, "header_json", "") or ""
    if header:
        return from_header_json(header)
    address = getattr(dataset, "address", None) or getattr(dataset, "filename", None)
    if not address:
        raise SettingsError(["the dataset has neither a stored header nor an address"])
    return from_address(str(address))
