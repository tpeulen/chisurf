---
type: Reference
title: "craggslab smfBox / smOTTER: how an NI-card smFRET rig drives lasers"
description: What the open-hardware smFRET box and its acquisition software teach the NI and Obis driver lanes - the NI DAQ waveform/counter/AI recipe, its validation rules, the two-laser generality gap, and the Obis serial command set - and where each landed in the acquisition drivers.
tags: [reference, acquisition, drivers, ni-daq, obis, alex, pie]
timestamp: '2026-11-01T00:00:00Z'
---

# Reference: craggslab smfBox / smOTTER — how an NI-card smFRET rig drives lasers

*Recorded 2026-11-01 from `chisurf/junk/smfBox` (e81ff90) and `chisurf/junk/smOTTER`
(d542278), cloned from https://github.com/craggslab/ with `.git` stripped (ORIGIN.txt in
each; a plain directory cannot be pushed to). Study material for the PhAcq obis + NI
driver lanes.*

## What the repos are

- **smfBox** — the Craggs lab's open-hardware single-molecule fluorescence confocal box
  (published smFRET instrument). The repo carries the *analysis* side: Jupyter notebooks
  (FRET analysis), converters, and hardware parts lists (`Part nr …xlsx`). 2.0 GB — mostly
  datasets. No acquisition control code.
- **smOTTER** — "C++ and Qt5 based acquisition software for the Craggs Lab smfBox": the
  *acquisition* side. The load-bearing file for us is **`nicard.h` / `nicard.cpp`** — the
  National Instruments DAQ card layer. No serial laser control anywhere: the lasers are
  run at fixed current and *shaped entirely by the NI card's digital outputs*.

## The NI recipe (nicard.h/.cpp)

The smfBox has no TCSPC card. The NI USB card does everything:

- **DO waveform task** — 4 digital channels: donor-laser pin, acceptor-laser pin, and two
  detector gate pins. One sample per **laser control resolution** (ns) across the
  **ALEX period** (µs); the pattern is derived from donor/acceptor **duty cycles**
  (off % / on % within the period), i.e. the excitation alternation lives in the waveform,
  not in the lasers.
- **Counter tasks** — one counter input per detector (APD counting modules): buffered edge
  counts; `analysePhotons` decodes 0→1 transitions into photon arrivals (sample offset →
  time). Detector gate lines exist as configuration (written HIGH in this version).
- **AI task** — laser power photodiode readback, sample-clock triggered off the DO start
  trigger, at resolution/10.
- **Validation rules worth keeping**: ALEX period ≥ 100× control resolution and evenly
  divisible by it; experiment length a multiple of the ALEX period.
- **Generality gap (owner correction)**: smOTTER hardcodes *two* lasers and *two*
  detectors (donor/acceptor DutyCycles). Our drivers must be **general: N lasers,
  N detectors, arbitrary PIE/ALEX slot plans** derived from the laser program
  (`pie_slots`: `{output, head, wavelength_nm, start_s, stop_s}` in one sync period) —
  never a hardcoded pair. That keeps ALEX→PIE and the MFD analysis paths unchanged.

## Obis command set (for `drivers/obis`)

Pinned from four independent implementations (storm-control `obis.py`, AndrewGYork/tools
`coherent.py`, amsikking `coherent_OBIS_LSLX_laser_box`, mmCoreAndDevices PR #645) + the
Coherent OBIS LX/LS operators manual §9.2.5:

- Serial 115200 8N1; commands end `\r`; every command answers with its response then the
  handshake line `OK\r\n`; errors as `ERR-xxx` (ERR-000 none, ERR-100 unrecognized,
  ERR-102 syntax, ERR-200 execution, ERR-220 invalid parameter, ERR-203 protected).
- Identity: `SYSTem:INFormation:{MODel, WAVelength, POWer, TYPe, SNUMber}?`
- Power: `SOURce:POWer:LIMit:{LOW,HIGH}?`, setpoint
  `SOURce:POWer:LEVel:IMMediate:AMPLitude <W>`, readback `SOURce:POWer:LEVel?`.
- Emission/modulation: `SOURce:AM:STATe ON|OFF`; `SOURce:AM:SOURce` ∈
  {CWP, CWC, DIGITAL, ANALOG, MIXED, DIGSO, MIXSO} — **DIGITAL is how an Obis joins the
  NI ALEX/PIE waveform** (external modulation input, current fixed).
- Safety: `SYSTem:AUTostart`, `SYSTem:CDRH` (5 s CDRH delay must be OFF for software
  control), `SYSTem:ERRor?`.
- Multi-laser boxes prefix commands with the laser index (`SYSTem1:…`, `SOURce1:…`);
  a directly connected single laser answers unprefixed (index 0 ≡ bare).

## Where it landed

- `libphacq modules/drivers/obis/` — serial laser driver + in-process simulator
  (`sepia.open("sim:")` pattern), channel-indexed for combiner boxes.
- `libphacq modules/drivers/ni/` — the generalized card: counter-input photon events,
  slot-plan-derived DO waveform (channel-indexed `slot_start_s/stop_s/output/gate`
  parameters + `sequence_period_s` + `do_resolution_ns`), AI power readback, simulated
  device generating gate-consistent photons so the whole ALEX→PIE path tests
  hardware-free.
- chisurf acq side: `pie_slots(laser_program)` → the NI driver's slot parameters; photon
  stream keeps macro times with routing = detector index (micro time 0) — exactly the
  shape `detect_alex_windows`/`update_alex` already consumes for the ALEX→PIE conversion.
