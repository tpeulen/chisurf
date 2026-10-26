---
type: Spec
title: Live recording — ChiSurf records PicoQuant TCSPC with a live PIE E–S view, built on CMC
description: Design for ChiSurf replacing the PicoQuant acquisition software — MultiHarp 150 (USB) plus Sepia II laser driver first, every PicoQuant TCSPC family covered — with live PIE burst analysis (E–S histogram building up during the measurement), recording into PTU and the .cs.pto project; CMC is the acquisition engine, ChiSurf the UI and analysis; Windows, Linux and macOS.
tags: [specs, acquisition, recording, picoquant, multiharp, sepia, pie, smfret, live, cmc, tttrlib]
timestamp: '2026-10-26T00:00:00Z'
---

# Live recording — ChiSurf records, CMC acquires, the E–S histogram builds up live

Owner directive 2026-10-26: ChiSurf replaces the PicoQuant software for the owner's **MultiHarp 150 (USB)**
and **Sepia II (PDL 828)** laser driver, measuring in **PIE** mode, with a **live 2-D E–S histogram** that
builds up while measuring. Recording must cover **every PicoQuant TCSPC device**. The owner's measurement
PC runs **Windows**, and recording must **also work on Linux and macOS**.

**Status: design only, nothing built.** CMC (`~/dev/cmc`, bundle `~/dev/cmc/okf`) already has most of the
acquisition engine. This spec does not redesign it: it decides how ChiSurf uses it and lists what each side
must add. Where CMC's bundle documents something, this page links it instead of restating it.

## Decisions

1. **CMC is the device layer; ChiSurf does not drive hardware itself.** CMC's backends already cover
   PicoQuant through snAPI ([picoquant](../../../cmc/okf/backends/picoquant.md)), the simulators
   ([tttrsim](../../../cmc/okf/backends/tttrsim.md), [sim](../../../cmc/okf/backends/sim.md)) and file replay
   ([tttr](../../../cmc/okf/backends/tttr.md)) behind one `IBackend`
   ([backend interface](../../../cmc/okf/architecture/backend-interface.md)), and CMC already reproduces the
   Sepia2 API ([cmc-sepia2-api](../../../cmc/okf/backends/cmc-sepia2-api.md)). ChiSurf's `acq` plugin
   carries a second snAPI ctypes wrapper (`chisurf/plugins/core/acq/tcspc_devices/picoquant/wrapper.py`,
   "duplicating snAPI functionality"). That duplicate is **retired** once the CMC path has run on hardware,
   since two drivers for one device drift. *Reason:* one driver per device, owned where the hardware work
   already happens.
2. **The ChiSurf `acq` plugin becomes the Record tool.** It is not a new plugin: `acq` already has the
   streaming pipeline the live view needs (`chisurf/plugins/core/acq/pipeline.py`: one decode path through
   `tttrlib.decode_records`, tttrlib's streaming consumers, bounded display state). It gains the laser panel,
   the PIE live E–S view and recording into the project. *Reason:* do not build a third acquisition UI.
3. **Live analysis runs next to the device and ships results, not photons, to viewers.** On the measurement
   machine, ChiSurf's acquisition service takes CMC's `PhotonEvent` batches in-process and runs the live PIE
   analysis. It publishes small updates (histogram increments, rates, run status) to any number of viewers:
   the local window, a remote desktop ChiSurf, and a browser. *Reason:* a browser cannot take a photon
   stream at MultiHarp rates, and the E–S view needs only a few kB per update. Photons still go through
   CMC's hub for C++ subscribers ([photon streaming](../../../cmc/okf/architecture/photon-streaming.md)).
4. **The live numbers are the offline numbers.** Live burst search, PIE window assignment, background and
   the E/S corrections use the **same tttrlib code and the same Instrument setup** as ChiSurf's offline
   burst chain (`burst_selection`, accurate FRET in tttrlib). A guard checks that a live run and an offline
   re-analysis of the recorded file agree burst for burst. CMC's own burst app
   ([apps/burst](../../../cmc/okf/apps/burst.md), [analysis/burst](../../../cmc/okf/analysis/burst.md)) uses
   a different criterion: inter-photon time, proximity ratio only, no stoichiometry. It stays as it is and
   is not the live E–S engine. *Reason:* a live histogram the offline analysis does not reproduce is a
   trap.
5. **The laser settings define the PIE scheme, and they are recorded.** The Sepia sequencer program
   (repetition rate, which head fires in which slot, delays) determines the sync period and the PIE windows.
   ChiSurf derives the **prompt/delay windows of the Instrument setup** from it and the user only confirms.
   The full laser state is written into the measurement's metadata (PTU tags and the project record).
   *Reason:* a PIE file whose excitation scheme is not recorded cannot be re-analysed correctly.
6. **Recording writes PicoQuant-compatible PTU, linked or embedded in the project.**
   - **PicoQuant hardware:** snAPI's own PTU writer, raw device records under PicoQuant's header. ChiSurf
     adds its tags (laser, setup, run id) through snAPI's tag calls, which exist only in the current ABI
     ([picoquant](../../../cmc/okf/backends/picoquant.md), "Two incompatible snAPI ABIs").
   - **Simulator and non-PicoQuant sources:** tttrlib's `RecordStreamWriter`, which streams PTU with the
     record count patched at checkpoints.
   - **Into the project:** the PTU becomes a photons dataset in the `.cs.pto` project, linked by default, per
     the [data workspace](data-workspace.md). The live burst runs go into
     `project.cs.pto/<dataset>.pto` in the format ndXplorer's `pto_reader` reads (same rule as the burst
     chain).

   *Reason:* existing PicoQuant, tttrlib and ndX readers keep working, and the project is the one place
   results live.
7. **Control goes through ChiSurf's RPC, not a new protocol.** The acquisition service is ChiSurf's
   headless server (`chisurf/server`, ZMQ RPC plus the PUB event channel, `chisurf/core/server_events.py`)
   with `acq.*` methods. `acq` already declares RPC methods in its manifest. CMC's hub carries data only (no
   control or status messages, see [photon streaming](../../../cmc/okf/architecture/photon-streaming.md)), and
   CMC's own plan to add control RPCs serves its FPGA device. ChiSurf does not wait for it. *Reason:* the
   control surface is ChiSurf's settings and project model, which ChiSurf's server already exposes to the
   agent, the CLI and remote clients.
8. **ChiSurf reaches CMC in process through pycmc, and as a hub subscriber.** pycmc is CMC's SWIG
   wrapper: committed, 73 classes including `BackendFactory`, the bridges and `protocol_defs`
   ([current-work](../../../cmc/okf/current-work.md), "pycmc"). Through it the service creates the backend
   and attaches a Python sink (SWIG directors). When CMC's own app is recording, ChiSurf can instead
   subscribe to its hub. That needs a Python client for the 64-byte `PHOT` protocol, a few hundred lines
   with `struct`, so ChiSurf needs no compiled CMC on a viewer machine. *Reason:* in-process avoids a
   socket hop on the measurement PC, and the hub client lets a lightweight viewer attach anywhere.
9. **The web client connects over a WebSocket bridge to the service, never to the device.** The browser
   gets live results (decision 3) and sends control calls. It connects with an origin allowlist and
   credentials, modelled on mmfdb's CORS allowlist. The bridge is ChiSurf's (server side), since CMC has
   no WebSocket. *Reason:* WebUSB is Chromium-only and the PicoQuant USB protocols are closed. The device
   side stays a local service.

## Architecture

```
measurement PC (Windows / Linux; macOS later, see Phase 5)
  Sepia II ── Sepia2_Lib ─────────────┐
  MultiHarp ─ snAPI → MHLib ── CMC picoquant backend ─┬─ CMC PhotonHub (TCP, C++ subscribers)
  (simulator: CMC tttrsim backend)                    └─ pycmc sink → ChiSurf acq service
                                                           ├─ tttrlib streaming PIE analysis
                                                           ├─ PTU writer + project (.cs.pto)
                                                           └─ ChiSurf server: RPC + PUB events
                                                                 ├─ local Record window (emtk)
                                                                 ├─ remote desktop ChiSurf (ZMQ)
                                                                 └─ WebSocket bridge → ChiSurf web
```

## Device coverage — every PicoQuant TCSPC family

Access paths: **snAPI**, PicoQuant's open-source C++/Python layer that dispatches to the per-device
libraries it ships alongside (`libmhlib`, `libhhlib`, `libhh500lib`, `libph330`, `libth260lib`, see
[picoquant](../../../cmc/okf/backends/picoquant.md)); the **per-device library** directly; CMC's **th200**
backend ([th200](../../../cmc/okf/backends/th200.md)); and the **native libusb** effort
([picoquant-native](../../../cmc/okf/backends/picoquant-native.md)). snAPI and its libraries run on Windows
and Linux, x86-64 only, and PicoQuant publishes no macOS build (snAPI product page; CMC picoquant page).

| Device | Bus | snAPI (Win / Linux) | Other path | macOS | T2 / T3 | CMC today | Missing | tttrlib reads |
|---|---|---|---|---|---|---|---|---|
| **MultiHarp 150** (owner's) | USB 3 | yes (`libmhlib`) | MHLib direct | none (native: Phase 5) | yes / yes | snAPI backend; T3 macro/micro + markers decode, **never run on hardware** | first hardware run; PIE sync check | PTU rtMultiHarpT2/T3 = Generic T2/T3 ✓ |
| MultiHarp 160 | USB 3 | yes (`libmhlib`) | MHLib direct | none | yes / yes | as MH150 | as MH150 | Generic T2/T3 ✓ |
| HydraHarp 500 | USB 3 | yes (`libhh500lib`) | HH500Lib | none | yes / yes | snAPI backend, untested | hardware run; **its PTU record code is not confirmed** (PicoQuant's PTU demos list none; presumably Generic) | ? (see tttrlib gaps) |
| PicoHarp 330 | USB 3 | yes (`libph330`) | PH330Lib | none | yes / yes | snAPI backend, untested | hardware run | Generic T2/T3 ✓ |
| TimeHarp 260 PICO / NANO | PCIe (+ USB 3 per the product table) | yes (`libth260lib`) | TH260Lib; Linux needs the `th260pcie` module | none (kernel driver per OS: out of scope) | yes / yes | snAPI backend, untested | hardware run | rtTimeHarp260N/P T2/T3 ✓ |
| HydraHarp 400 | USB 2 / USB 3 | yes (`libhhlib`) | HHLib | native libusb: protocol decoded statically, **no code, no hardware test** | yes / yes | snAPI backend, untested; native notes | hardware run; native driver | rtHydraHarpT2/T3 v1, v2 ✓; `.ht3` ✓, `.ht2` ✗ |
| PicoHarp 300 (discontinued) | USB 2 | **no** (no `phlib` in the snAPI repo) | PHLib (Win / Linux) | none | yes / yes | **none** | a per-device-lib backend (PHLib) in CMC | PTU rtPicoHarpT2/T3 ✓; native `.pt2`/`.pt3` ✗ (see gaps) |
| TimeHarp 200 (discontinued) | PCI | no | `thmtlib.dll` (Windows only) | none | – / T3 | `th200_hardware`, **record decoding unverified** | validate decode on a known signal | native `.t3r` ✗ |
| Sepia II PDL 828 (laser driver) | USB | — | Sepia2_Lib (PQLaserDrv): **Windows**; Linux only under **Wine** + libusb (PQLaserDrv `Linux/README.md`) | none (native: Phase 5) | — | `cmc_sepia2` reproduces the API for CMC's own device; it does **not** drive a real Sepia | a Sepia II control path for the real device | — |

Live-analysis implications that differ by device:

- **Clock semantics.** In T3 a macro tick is one sync period and the microtime is in device resolution
  units. In T2 a macro tick is the device resolution and there is no microtime. CMC records this
  ([picoquant](../../../cmc/okf/backends/picoquant.md), "resolution semantics"). PIE needs T3, or T2
  with the sync recorded as a marker and microtime rebuilt from it. **P1/P2 use T3.**
- **Resolution and range.** These come from `getDeviceConfig` (`Resolution` in ps) and the sync divider,
  never from a table. The PIE windows are stored in **ns** in the setup and converted to bins per run,
  so one setup serves every device.
- **Sync divider.** With a divider above 1 a T3 record's microtime spans several laser periods, and PIE
  windows must be placed per period. The service refuses a PIE setup whose windows do not fit the
  recorded period.
- **Channel numbering.** A channel definition's `chs` are tttrlib routing channels. Live and offline must
  number detectors the same way ([CMC ⇄ ChiSurf compatibility](../../../cmc/okf/architecture/chisurf-compatibility.md),
  pitfalls). This is checked per device in the A/B guard (decision 4).

### tttrlib reading gaps (tttrlib's job)

tttrlib maps every PTU record code PicoQuant publishes: PicoHarp 300, HydraHarp v1/v2, TimeHarp 260
N/P, and Generic T2/T3 for MultiHarp and PicoHarp 330 (`modules/core/src/TTTRHeader.cpp`). It also reads the
HydraHarp `.ht3` container. Gaps, to be closed in tttrlib:

1. **An unknown PTU record code silently decodes as HHT3v2** (the `default:` of the switch). It must
   refuse by name. Otherwise a T2 file of a device whose code is not listed decodes into nonsense
   without any error.
2. **HydraHarp 500's PTU record code is unconfirmed.** Get it from a real HH500 PTU or snAPI's writer and
   add it to the map with a test file.
3. **Legacy native files have no reader:** PicoHarp 300 `.pt2`/`.pt3` (`pt3` appears in the extension
   list, but no container reads its header), HydraHarp `.ht2`, TimeHarp 200 `.t2r`/`.t3r`/`.thd`. These are
   for archives; the recorder never writes them.
4. **PHU files are histograms, not TTTR**, and are out of scope for photon data.

## Live PIE analysis

On every batch, decoded through `tttrlib.decode_records` with a carried `TTTRDecodeState` for raw-record
sources, or taken as already-decoded CMC `PhotonEvent` arrays:

1. **Assign each photon** to donor/acceptor channel and prompt/delay window from the Instrument setup
   (the shared chisurf/CMC channel-definition JSON: `windows`, `detectors`, `tttr_reading`).
2. **Search bursts** with tttrlib's `StreamingBurstDetector`: the sliding-window (m photons in T) rule,
   identical to the batch `burst_search_sliding_window` (tttrlib `modules/streaming/README.md`). An open
   burst carries across batches. All-photon search comes first; DCBS (two detectors, intersect) follows.
3. **Count each burst** into F_DD, F_DA and F_AA, subtract background per channel (estimated live from
   inter-burst photons), and compute E and S with the γ, β, α, δ corrections of tttrlib's accurate-FRET
   code (`modules/spectroscopy/corrections`). Raw E/S are shown until corrections exist in the setup.
4. **Accumulate** the 2-D E–S histogram, its two marginals, the burst rate, and per-channel count rates
   (`StreamingIntensityTrace`). Per-channel decays in the PIE windows (`StreamingDecayHistogram`) show
   the window placement.
5. **Publish** increments at a fixed display rate, about 5 Hz. The view redraws from accumulators and
   never re-scans photons. At the end the run's bursts are written to the project as a burst run.

**Missing in tttrlib.** A `StreamingPieBurstAnalyzer` consumer in `modules/streaming`. It combines the
detector with per-burst window counters, which today give only boundaries, so the pipeline would otherwise
have to keep photons. It adds live background, E/S with corrections, and the 2-D accumulator. It must come
with a batch-agreement test like the other streaming consumers. **Missing in ChiSurf:** the `acq` pipeline
stage that drives it, and the A/B guard against `burst_selection` on the recorded file.

## Laser control (Sepia II)

- **Path:** PicoQuant's Sepia2_Lib through ctypes. PicoQuant ships a Python wrapper and demos (PQLaserDrv
  repository; CMC used them as interface documentation only, see
  [cmc-sepia2-api](../../../cmc/okf/backends/cmc-sepia2-api.md)). It runs on Windows natively and on Linux
  under Wine (PQLaserDrv `Linux/README.md`). The ChiSurf service talks to it through the same `LaserBackend`
  shape CMC uses: `make_cmctdc_backend` for CMC's device, and a new Sepia2_Lib-backed implementation for
  the real Sepia.
- **What ChiSurf sets:** oscillator, pre-divider, the SOM 828-D sequencer (bursts per channel, which
  output fires in which slot, delays, sync source), the per-head intensity, and laser on/off (SCM soft
  lock). CMC's page maps SOM 828-D semantics precisely. The ChiSurf UI writes the same model.
- **PIE from the laser program:** the period is the oscillator divided by the pre-divider, times the
  sequence length. Each laser slot becomes a window with its delay. The setup's prompt/delay windows are
  proposed from it and confirmed by the user.
- **Recorded:** the full laser state (module map, serials, every setting, the derived PIE scheme) as
  metadata on the measurement, in PTU tags and the project record.

## Device layer (owner 2026-10-26)

The device layer is CMC's own driver stack, not PicoQuant's libraries: `pqusb` (Python reference
implementation, `~/dev/cmc/tools/pqusb`) and **rustytime** (`~/dev/cmc/tools/rustytime`, the Rust
implementation: SymPhoTime-compatible acquisition, native PicoQuant device control, continuous T2/T3
streaming to PTU). Both are developed in the CMC repository by the owner. ChiSurf consumes them through
one source interface in the Record tool (`chisurf/plugins/core/acq/live/`); it never talks to USB itself.
ChiSurf uses pqusb today and switches to rustytime when rustytime exposes what ChiSurf needs (a Python
binding or a streaming interface); the switch is a backend choice, not a rewrite.

## Imaging acquisition (owner 2026-10-26)

The Record tool also acquires **images**, like SymPhoTime: a scanner (piezo stage first, then whatever
SymPhoTime supports — galvo/LSM integration via line/frame markers) moves the focus while the TCSPC
device records photons with frame/line/pixel markers.

- **Scanner control** is a device-layer job (rustytime): scan area, pixels, dwell time, line/frame
  rates, bidirectional scanning, z-stacks, point measurements at chosen positions, marker generation.
  ChiSurf drives it through the same source interface as the TCSPC device.
- **Live view:** the image builds up line by line from the marker stream (tttrlib's CLSM image
  reconstruction): intensity, mean arrival time (fast FLIM), per-channel and per-PIE-window images;
  the FRET quality panel does not apply, an imaging quality panel does (count rate per pixel, pile-up,
  marker consistency).
- **Recording:** the photons with markers go into the project like any recording (embedded in the
  .cs.pto, a photons dataset with representation `photons`, experiment Imaging); the imaging tools take
  it from the workspace.
- **Until rustytime has a scanner:** a simulated scanner (tttrlib SimEngine `run_scan`, CLSM raster with
  markers) behind the same interface, so the whole path is built and tested now.

## The Record tool (UI)

The `acq` plugin, as an emtk AutoForm `view.json`:

- **Connection:** local service or a remote host (with credentials), the device list from the backend,
  and the simulator.
- **Laser:** heads, intensity, repetition rate, the PIE sequence, and the derived period. Output on/off is a
  safety-relevant control and is always visible.
- **TCSPC:** mode (T3), sync divider, CFD or edge levels, offsets, resolution, channel enables, and live
  count rates per input.
- **PIE setup:** the Instrument-setup picker (a workspace `setup` row), the windows proposed from the
  laser program, and window placement over the live decays.
- **Run:** duration or until stop, name and target in the project, link or embed, start and stop.
- **Live:** the E–S histogram with marginals, burst rate, count-rate trace, decays per window, and health
  (dropped blocks, FIFO overflow flags, disk queue).

The result appears in the Datasets workspace as a photons dataset with its burst run as a child row.

## Phases

| Phase | Deliverable | Hardware needed | Testable now |
|---|---|---|---|
| **P1** | `acq` on CMC's `tttrsim` backend through pycmc (PIE/ALEX, see [tttrsim](../../../cmc/okf/backends/tttrsim.md)); tttrlib `StreamingPieBurstAnalyzer`; live E–S view; PTU plus project recording; the A/B guard against offline `burst_selection` | none | yes |
| **P2** | MultiHarp 150 through CMC's snAPI backend, and Sepia II through Sepia2_Lib, on the Windows measurement PC; laser-derived PIE; metadata | owner's MH150 + Sepia II | on the measurement PC |
| **P3** | remote viewers: the ChiSurf desktop client over ZMQ, then the WebSocket bridge and ChiSurf web (results plus control) | as P2 | bridge with the simulator |
| **P4** | the other PicoQuant families (table above): hardware runs per family; a PHLib backend in CMC for PicoHarp 300; TimeHarp 200 decode validation; tttrlib gaps 1–3 | per device | partly (file gaps) |
| **P5** | macOS acquisition: native libusb drivers for MultiHarp 150 and Sepia II | MH150 + Sepia II + a USB analyser | no |

### Phase 5 — macOS through native drivers

PicoQuant ships no macOS libraries, so macOS acquisition needs a userspace libusb driver per device.
Until then macOS works with the **simulator** and as a **client** of a Windows or Linux measurement
service (P3).

- **Model:** CMC's HydraHarp 400 effort. The protocol was recovered by Ghidra decompilation of PicoQuant's
  Linux library: transport, init, FPGA image load, register map, FIFO read, start/stop. All of it is
  **still unverified on hardware, and no driver code is written**
  ([picoquant-native](../../../cmc/okf/backends/picoquant-native.md)).
- **MultiHarp 150:** USB 3. The HH400 notes show PicoQuant's USB 3 parts tunnel register access through a
  Mass-Storage Bulk-Only Transport, behind an unidentified controller. The MH150 adds an FPGA image to
  load and a different register map, so the HH400 notes reduce the work but do not carry over.
  - **Estimate:** several person-months to a first verified measurement. Static analysis takes weeks; the
    real cost is hardware iteration with a USB analyser.
  - **High risk:** firmware or FPGA-image changes in later MHLib versions, and the macOS USB 3 mass-storage
    class driver claiming the device before libusb can.
- **Sepia II:** USB 2. Its command set is smaller than a TCSPC unit's, so the effort is lower: weeks to a
  usable on/off/rate/sequence subset. But CMC's own Sepia work **deliberately stopped decompiling
  Sepia2_Lib**, and its page says not to ([cmc-sepia2-api](../../../cmc/okf/backends/cmc-sepia2-api.md),
  "Sources"). Recovering the Sepia wire protocol therefore needs an explicit owner decision. The less
  intrusive method is capturing the USB traffic of the official library on Windows, without decompiling.
- **Legal and interoperability (not legal advice; owner decision):**
  - Reverse engineering for interoperability is narrowly permitted in some jurisdictions: the EU Software
    Directive 2009/24/EC Art. 6 allows decompilation when it is indispensable for interoperability, limited
    to that purpose, and the information is not otherwise available.
  - PicoQuant's licence terms for MHLib, Sepia2_Lib and snAPI must be checked for clauses against it.
    CMC's notes record that the PQLaserDrv repository carries no licence file.
  - Clean-room separation (one person documents, another implements from the document) and keeping vendor
    code out of the repository, as CMC already does with Ghidra output, are the minimum.
  - **WebUSB** would need the same native protocol, plus a browser that exposes the device, which macOS
    and Windows driver binding can prevent. It stays out of scope until a native driver exists.

## Open questions for the owner

1. **Measurement PC:** Windows is confirmed. Which version, and is its admin (driver install, firewall
   for remote viewers) under your control?
2. **PIE scheme:** which heads and wavelengths, which repetition rate, and how many PIE slots? Do you
   also want DCBS, or all-photon burst search only, at first?
3. **Corrections in the live view:** raw E/S, or corrected with the γ, β, α, δ of a stored Instrument
   setup? Should the live view refuse to show corrected values without a calibration?
4. **Recording target:** keep the PTU as a linked file next to the project (default), or embed it? Where
   do raw files go on the measurement PC?
5. **Remote viewing:** only on the lab network, or from outside (VPN)? This decides authentication and
   TLS for the bridge.
6. **Phase 5 go-ahead:** is reverse engineering the MultiHarp 150 and Sepia II USB protocols acceptable
   given PicoQuant's licence terms, and is a USB analyser available? Or should macOS stay a viewer and
   simulator platform?
7. **Old devices:** are PicoHarp 300 or TimeHarp 200 actually in use, or can P4 skip them?

## What each side must add

**CMC:**
- the first hardware run of the snAPI backend on a MultiHarp 150 (T3 microtime, markers, sync period);
- a Sepia2_Lib-backed `LaserBackend` for the real Sepia II;
- a PHLib backend for PicoHarp 300 (P4);
- validated TH200 decoding (P4);
- optional: the hub's `STATUS` message, which is defined but never sent today, and control RPCs (its own
  plan).

**tttrlib:**
- `StreamingPieBurstAnalyzer`, with a batch-agreement test;
- refusing unknown PTU record codes;
- HydraHarp 500's record code;
- legacy native readers (`.pt2/.pt3/.ht2/.t3r`).

**ChiSurf:**
- `acq` on pycmc (backend plus a Python sink), retiring its own snAPI wrapper after P2;
- the live PIE stage, the E–S view and laser-derived PIE windows;
- recording into PTU (with tags) and the `.cs.pto` project, with burst runs in the embedded container;
- `acq.*` RPC for laser, TCSPC and run;
- the Python `PHOT` hub client;
- the WebSocket bridge and the web Record view (P3);
- the A/B guard (live vs offline).

## Proposed PRD item

> **Live recording (owner 2026-10-26).** ChiSurf records PicoQuant TCSPC data in place of PicoQuant's
> software, with a live PIE E–S histogram that builds up during the measurement:
> - MultiHarp 150 (USB) plus Sepia II on the Windows measurement PC first;
> - every PicoQuant TCSPC family after that;
> - Linux through PicoQuant's libraries;
> - macOS as viewer and simulator, with native drivers as a separate, owner-approved phase.
>
> CMC is the acquisition engine (snAPI backend, simulators, hub). ChiSurf's `acq` plugin is the Record
> tool and runs the live analysis with tttrlib's streaming consumers, which must agree burst for burst
> with ChiSurf's offline burst chain. Recording writes PicoQuant-compatible PTU with the laser state as
> metadata. The PTU is linked or embedded in the `.cs.pto` project, and burst runs go into the project's
> embedded container. Viewers (desktop, browser over a WebSocket bridge) get results, not photons.
>
> Acceptance:
> - P1 runs on the simulator with the A/B guard green;
> - P2 records a PIE smFRET measurement on the MultiHarp 150, and its live E–S histogram equals the offline
>   analysis of the recorded file;
> - every PicoQuant record type tttrlib meets is read or refused by name.
>
> Design: [live recording](../specs/live-recording.md).

## Sources

- **CMC bundle** (read 2026-10-26):
  - [index](../../../cmc/okf/index.md), [current-work](../../../cmc/okf/current-work.md);
  - architecture: [overview](../../../cmc/okf/architecture/overview.md),
    [photon data model](../../../cmc/okf/architecture/photon-data-model.md),
    [backend interface](../../../cmc/okf/architecture/backend-interface.md),
    [photon streaming](../../../cmc/okf/architecture/photon-streaming.md),
    [ChiSurf compatibility](../../../cmc/okf/architecture/chisurf-compatibility.md),
    [instrument upgrade path](../../../cmc/okf/architecture/instrument-upgrade-path.md),
    [project history](../../../cmc/okf/architecture/project-history.md),
    [primer20k SD updates](../../../cmc/okf/architecture/primer20k-sd-updates.md) (control-RPC gap);
  - backends: [index](../../../cmc/okf/backends/index.md), [picoquant](../../../cmc/okf/backends/picoquant.md),
    [picoquant-native](../../../cmc/okf/backends/picoquant-native.md), [tttrsim](../../../cmc/okf/backends/tttrsim.md),
    [th200](../../../cmc/okf/backends/th200.md), [cmc-sepia2-api](../../../cmc/okf/backends/cmc-sepia2-api.md);
  - apps and analysis: [apps/burst](../../../cmc/okf/apps/burst.md),
    [analysis/burst](../../../cmc/okf/analysis/burst.md).
- **tttrlib:**
  - `modules/core/include/TTTR.h` (`decode_records`, `TTTRDecodeState`), `TTTRStream.h`;
  - `modules/io/base/include/{PhotonSink.h (PhotonStreamHub), TTTRStreamWriter.h}`,
    `modules/core/include/RecordStreamWriter.h`, `modules/io/pto/include/io_pto.h` (`PtoPhotonStream`);
  - `modules/streaming/README.md`;
  - `modules/core/src/TTTRHeader.cpp` (the PTU record-code switch),
    `modules/io/base/include/TTTRHeaderTypes.h`.
- **PicoQuant:**
  - [PTU file demos](https://github.com/PicoQuant/PicoQuant-Time-Tagged-File-Format-Demos)
    (`PTU/Python/Read_PTU.py` record codes; `changelog.txt`: Generic T2/T3 covers MultiHarp and
    PicoHarp 330);
  - [snAPI](https://www.picoquant.com/products/software/snapi/) (Windows and Linux, x86-64);
  - [PQLaserDrv](https://github.com/PicoQuant/PQLaserDrv) (`Linux/README.md`: Wine plus libusb);
  - [TCSPC product overview](https://www.picoquant.com/products/category/tcspc-and-time-tagging-modules);
  - [MultiHarp 150](https://www.picoquant.com/products/time-tagging-tcspc-electronics/multiharp-150/).
- **ChiSurf:** `chisurf/plugins/core/acq/{manifest.json, pipeline.py, tcspc_devices/}`,
  `chisurf/core/server_events.py`, [data workspace](data-workspace.md).
