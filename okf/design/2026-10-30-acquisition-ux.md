---
type: Plan
title: Acquisition UX implementation plan
description: The task-by-task plan (settings chooser, simulator lifecycle, additive diode control, uniform surfaces, camera, experiment presets with lossless bounded analysis, novice guided workflow) behind the owner's 2026-10-30 photon-acquisition UX requirements, with the native-analysis reconnaissance and the design gates for writer priority and dock subscriptions.
tags: [plans, design, acquisition, ux]
timestamp: '2026-10-30T00:00:00Z'
---

# Acquisition UX implementation plan

> **For Hermes:** Use the subagent-driven-development skill, with independent spec review before quality review. This is a continuation of the verified local batch, not a restart.

**Goal:** Implement the operator's recorded UX requirements without contacting MT200 or compromising photon recording.

**Architecture:** Keep instrument/application state toolkit-neutral. Use existing emtk docks, dialogs and plots; select experiment layouts through dock visibility. Separate lossless recording from optional, bounded live analysis. New science must reuse verified native implementations or be traced to primary references and tested on independently generated data.

**Tech stack:** ChiSurf, emtk, native tttrlib/phacq, Python in `/Users/tpeulen/mambaforge/envs/arm64`.

## Controlling context

- Owner: “do not restart on mt200, meas is running. continue locally.” No remote commands, deployment, instrument/camera probing or hardware control. Only local simulated objects and stubbed video backends in tests.
- Owner: “write down my comments contiune what you are working on and afterwards do what i told you.” Comments are in `chisurf/plugins/core/acq/UX_UI_BACKLOG.md`; current wizard/laser/diagnostic batch is verified.
- Owner: “always present plts in workflow”; “laser list all connected”; “never drop photons.”
- No commits, staging, push, stash/reset or edits to unrelated dirty work. Shared plans/board are controller-owned. Children have explicit disjoint file claims and must not edit `record_app.py` / `record.view.json` unless reassigned.

## Verified starting point

- Focused acquisition suite: **75 passed**. emtk wizard/docs/i18n/API: **43 passed, 2 skipped**. pqusb duration/status: **7 passed**.
- Six simulated wizard recordings independently read by tttrlib; counts agree with full decay accumulators; timestamps monotonic; DNA has actual bursts and populated E/S content.
- Persistent guided plots, compact full-height Quality, stacked laser cards, uncalibrated percentage fallback, guarded target commit, fixed footer and inert background are implemented.
- New toolbar clutter removed; Help fixed (`show()` instead of calling boolean `open`) and tested by real clicks/content/Escape at normal and narrow sizes.
- Full emtk suite is NOT established green: the earlier log includes two GLFW hidden-window pointer-after-move failures, beyond subsequently fixed wizard documentation/i18n errors.
- Simulator evidence: `/Users/tpeulen/.hermes/cache/scratch/acq-local-ux-evidence/readback-report.json` and PNGs in that folder. These are local simulated evidence, not instrument qualification.

## Execution policy

**Current checkpoint:** parent-verified **105 acquisition tests passed** after integration of the file chooser, task accents, Simple/Advanced filtering, empty idle axes and giant alignment display. Fresh rendered scenes were inspected. Independent spec reviews are pending; quality review follows a passing spec review. Mixed-diode implementation `sa-0-71175455` now holds the sole test lease; parent does no tests/heavy renders during it.

1. Read-only reconnaissance verifies live seams and file claims before implementation fan-out.
2. Use strict RED → GREEN → regression for each vertical slice. One explicitly named test lane at a time; other lanes do read-only/design work until the test lease transfers. Parent does not overlap heavy renders with a child test lane.
3. A child reports changed paths, exact tests/output and integration API. Parent reads code and re-runs acceptance before claiming completion. Incomplete work is continued, not recreated.
4. Source-backed science includes references/DOIs, units, assumptions, failed/missing states and independent synthetic recovery tests. No invented diffusion/lifetime/calibration verdicts.

## Task 1 — explicit settings file chooser

**Files:** `acq/gui/record_settings.py`, new `acq/gui/settings_file_dialog.py`, new focused settings chooser tests; parent integration in `record_app.py` and `record.view.json`.

- Write a failing test for choosing a real JSON settings file, then actual PTU and PTO fixtures with recoverable settings. Reuse the existing `settings_file.from_address` / dataset readers rather than making a parallel format parser.
- Expose a request flag/action and an emtk `DialogWindow` + `FileDialog` accepting `.ptu`, `.pto`, `.json`.
- Keep chooser rendering modal/input-isolated over retained tables. Cancel changes nothing. Reject unreadable/invalid files visibly; validate before adopting settings or connecting anything.
- Preserve the established explicit settings-application semantics and live-recording guard. No hardware is opened merely by browsing.
- Exercise actual ellipsis click, file selection and cancellation; test blocked application during recording.

## Task 2 — one complete simulator lifecycle

**Files:** source-control mixin/helper discovered by reconnaissance; parent `record_app.py` / `record.view.json`; `live/instrument_sim.py` only where necessary.

- Write regressions for a single visible simulator choice, complete simulated laser/shutter/diode/source state, and transitions to/from real/replay sources while idle.
- Remove competing Complete sim/Leave sim controls. Never leave simulated lasers attached to a real device or silently connect real hardware while leaving simulation.
- Cover initial default selection, profile/settings application, image versus point source paths and recording-time rejection. Retain explicit SIMULATION labels and metadata.

## Task 3 — additive diode target adjustment

**Files:** `gui/power_controls.py`, `gui/laser_cards.py`, existing `live/calibration/average_power.py` after inspection, new mixed-diode tests. Parent owns integration only.

- Preserve manual average-power curves independently of repetition/pulse timing. Use per-head calibrated sensitivity and one common dark offset.
- Write a two-head simulated acceptance test: adjusting one known contribution while another emits must not switch the other head or cycle global emission/shutters unnecessarily.
- Servo relative to the measured combined signal with unchanged other contributions. An unknown mixture is not identifiable: request a baseline or report unverified, never invent per-head powers or silently toggle heads to manufacture a measurement.
- Retain no-extrapolation/range, expired calibration, recording guard, confirmation and timing/IRF invalidation requirements. Zero remains a safe light-off action. Rendering/selection never enables light.
- Test nonlinear/invalid curves, mixed unknown state, dark offset, readback failure, target cancellation and changing other-head drive mid-servo.

**Engineering corrections from parent review:** derive targets through the actual synthetic calibration. The current sim uses dark20, Green raw-per-driver-percent10 and Red8; its endpoint maps100% to10µW. A parent PowerBook probe returned Green2µW aloneRaw220, Red3µW aloneRaw260, combinedRaw460 and correctly recovered Red3µW after subtracting Green's net200. The earlier worker example40/44/84 was wrong and is not evidence. Attribution signatures must include full oscillator timing/divider/mapping, not only output-enabled bits. Never let enabling a selected shared oscillator output silently energize another stored-positive head. Keep dark capture passive, contributions session-scoped and independently verified, and mixed-unknown isolation explicitly consented rather than automatic.

## Task 4 — uniform/simple acquisition surfaces and alignment display

**Files:** parent `record_app.py`, `record.view.json`; new `gui/alignment_display.py` if needed; focused UI tests.

- Persistent empty histogram/decay/trace/camera frames when idle; do not insert fake curves. Colored dock/task accents distinguish acquisition, illumination and analysis regions.
- Advanced mode retains detailed Quality. Simple mode shows only yellow/red actionable warnings and hides range controls. Unknown critical setup states must not be silently represented as safe.
- Double-click a detector count-rate row opens a very large floating numeric view with detector label/unit, live updates, no-data/disconnected state and close behavior. Test real double-click and quantitative viewport/font sizing, not only object construction.

## Task 5 — camera and image/trace organization

**Files:** `gui/video_panel.py`, camera tests, image-point output helper/runner located by reconnaissance; no parent core edits by child.

- Auto-connect preview once when appropriate; failures remain visibly unavailable, not simulated/live. Tests stub all capture/device APIs.
- Remove routine Record control; move detailed device/exposure/recording options to context menu without silently enabling recording.
- Keep empty camera surface visible. Pause unnecessary hidden-preview work unless video recording explicitly needs it.
- New image-associated point traces go under `<image folder>/traces/`; images stay in image folder. Preserve dataset parent links and metadata addresses; never move existing user recordings.
- Record/read one local simulated image and associated point traces to verify paths, metadata and independent photon readback.

## Task 6 — experiment presets and lossless/optional-analysis scheduling

**Files:** new `gui/experiment_views.py`, `live/experiment_analysis.py` / bounded-analysis helper if justified; parent core/view integration; existing recording/analyzer modules only under a new explicit ownership claim.

- Presets: smFRET (E/S and bursts), polarization (decays/anisotropy/lifetime estimates and G/l1/l2 helper), FCS (correlation amplitude/brightness/diffusion estimates). Reuse dock visibility rather than creating separate applications.
- Research model equations in primary literature before implementing new fits/corrections; document exact units, correction conventions, limits and configured assumptions. Reuse existing native scientific routines where available.
- Fit recovery and rejection tests use known independently generated data. Keep low-count/unfitted/unconfigured outputs unverified.
- Invisible analysis docks do not schedule computation. Keep essential recording counters separate from optional scientific analyses.
- Isolate writer/drain priority from optional burst/correlator work. Under overload skip optional analysis with visible status or reduce cadence, never thin raw PTU input. Mark incomplete analysis honestly rather than labeling its partial results complete.
- Stress-test overload using local generated photons; independently read every raw record/count/timestamp and verify optional work was skipped/throttled. Do not claim hardware throughput from a local test.

## Task 7 — novice guided workflow (owner's latest, 2026-10-30 evening)

**Files:** parent `gui/measurement_wizard.py`, `gui/guided_plots.py`, `live/guided_analysis.py`, `gui/record_app.py` glue; new `live/dilution.py` + tests (implementation child); new guided tests.

1. **Click budget.** Audit every wizard stage; each stage carries at most one primary action. Auto-advance a completed green stage instead of demanding an extra Next. Keep guarded rollback for real reversals only.
2. **User power setup.** After calibration the wizard presents explicit per-head power setup (calibrated µW via the existing target gesture, drive % fallback) — the user, not hidden defaults, sets session power. Powers persist for every following sample.
3. **FCS-first novices lane.** For smFRET start at bounded low power (protect detectors), step power up while watching correlation amplitude, then concentration guidance. All power changes remain explicit user gestures with existing confirmations.
4. **Dilution advisor.** `live/dilution.py` pure-math planner: from measured concentration to target concentration at a default 50 µL total, emitting exact µL instructions ("put 47 µL buffer on the slide, add 3 µL of the FCS solution"). A direct volume below a pipettable minimum triggers an explicit pre-dilution step. Refuse invalid inputs; round to practical volumes and state the achieved concentration and tolerance. No invented concentrations.
5. **Multi-sample session.** After references/DNA the wizard offers a sample loop: calibration and DNA corrections valid for all samples, DNA-derived factors applied through the native corrected E/S path (no new correction science). Each sample: start/stop, then next sample.
6. **Live sample feedback.** During samples show burst/intensity traces, E–S histogram **with marginal projections**, burst count and measurement time counters, and a traffic light: green when configured checks pass; yellow/red list what to improve. Reuse warning-only Quality semantics; missing bounds never show green.
7. **5-minute FCS before smFRET.** The wizard recommends ~5 min FCS at the chosen concentration before longer smFRET runs and reuses the FCS concentration for the smFRET dilution instruction.

## Native-analysis reconnaissance (checked against source)

- Reuse `StreamingBurstAnalyzer` for PIE/ALEX E/S and MFD per-burst anisotropy. `Experiment.factors` and per-channel setup G/l1/l2 are existing configuration, not new UI-local correction models.
- Reuse `core/fluorescence/anisotropy/rt.py::rt_curves` for time-resolved anisotropy and `live/calibration/measurements.py::g_factor` for the reference helper. Parent read their executable bodies: g multiplies the perpendicular channel. **The rt.py docstring/long comment contradicts its current body about a reciprocal/parallel convention.** Do not copy that prose or accept the recon headline as proof of complete consistency; pin the actual forward/inverse behavior in recovery tests before exposing it. No native l1/l2 measurement estimator was found: expose values/provenance with a physically specified reference workflow, never invent an estimator.
- Additional convention warning: `integrals.py::compute_g_factor_isotropic` currently returns sum(perpendicular)/sum(parallel), whereas `compute_g_factor_perrin` and the acquisition `measurements.g_factor` use the opposite sensitivity convention. Do not interchange those results without an explicit tested conversion; the recon report's blanket consistency claim was too strong.
- Existing `plugins/burst/burst_fcs_correlator/core/algorithms.py::fit_simple_diffusion` is a grid estimate with fixed structure parameter 3.5 and fitted baseline/amplitude. Label that assumption; finite output alone does not prove a resolvable diffusion time (a constant curve can yield an arbitrary grid value). Free-3D diffusion assumptions and fit-range identifiability must be explicit.
- Native lifetime/anisotropy fitting exists through fit23/fit2x, but availability in the running extension and required IRF/setup must be exercised, not inferred from source existence.
- **Writer priority is currently wrong for the new requirement:** parent read `RecordSession._run`; it calls `_push` under the shared lock before `_write_batch`. The comment in guided_analysis saying photons already passed the writer is therefore not true for this Python path. A bounded optional-analysis worker/gate must preserve unconditional raw writes, separate truthful raw counters from incomplete analysis, handle optional exceptions without killing recording, and qualify all `_push` subclasses. Do not describe the current implementation as overload-safe.
- Optional-analysis design gate: export the **shown and active** dock set from DockManager into immutable model/session subscriptions. Keep raw capture/counters/safety independent of display subscriptions. A visible Quality consumer may legitimately share an analyzer even when a histogram tab is hidden; track actual consumers rather than a blanket preset flag.
- Gap semantics must be tested: when a hidden/overloaded consumer resumes, do not silently treat discarded analysis intervals as observed zero photons. Reset correlation windows or explicitly support segmented exposure; flush burst state across skipped intervals and label coverage incomplete. Do not save partial tables/maps as complete analyses or claim a fitted scientific calibration from them.
- Stress qualification must compare independently read raw PTU event/photon counts and monotonic timestamps while an optional analyzer is deliberately stalled/raises. Writer errors and source overflow remain recording faults, never disguised as optional-analysis skips. These are local software guarantees, not a proof of hardware throughput or immunity to native process crashes.
- Candidate paper metadata is recorded in the task-specific citations ledger at `~/.hermes/cache/scratch/acq-ux-citations.json`. Primary-paper equations have not all been independently read; native API reuse is not a claim of full literature validation.

## Completion gate

Every backlog item must be linked to implemented paths, real-input/rendered acceptance and appropriate numeric/file tests. Re-run focused acquisition, native timer and shared toolkit checks, inspect populated and empty screenshots at normal/narrow sizes, then independent spec and quality reviews. Update this plan/backlog with verified status. No deployment/restart is part of this plan.
