---
type: Plan
title: Owner instructions - photon-acquisition UX (verbatim record)
description: The owner's photon-acquisition instructions from 2026-10-30 on, verbatim and in order, each followed by where it landed, plus the standing constraints and the dated continuation checkpoints of the acquisition work stream.
tags: [plans, design, acquisition, owner-instructions]
timestamp: '2026-11-02T00:00:00Z'
---

# Owner instructions — photon-acquisition UX (verbatim record, 2026-10-30)

> **For the receiving agent:** this file is the authoritative record of everything the owner (T.O. Peulen) instructed in this work stream — his words verbatim, in order, each followed by where it landed. It travels with the working tree. The structured engineering version (requirements, tests, verification bar) is `chisurf/plugins/core/acq/UX_UI_BACKLOG.md`; the design decisions are in `okf/design/2026-10-30-acquisition-ux.md`. When an interpretation here and the owner's words conflict, **his words win**.

## Standing constraints — binding until the owner lifts them

1. **Local only.** Verbatim: *"do not restart on mt200, meas is running. continue locally"*. No remote commands, SSH, deployment, restart, instrument/camera probes, laser/shutter actions or scheduled tasks on MT200 until explicitly authorized again. Everything since that correction is undeployed local work.
2. **Never drop photons.** Verbatim (inside the UX batch): *"never drop photons."* When analysis overloads, drop/slow the *analysis*, never the recorded raw stream. Report overflow/loss explicitly.
3. **No commits, staging, publishing, deployment** of the shared dirty tree without explicit authorization. Preserve all unrelated dirty changes across `chisurf`, `emtk`, `libphacq`.
4. **Light is authorized only by explicit operator gestures.** Render/select cannot energize lasers. Post-measurement power/pulse changes warn and invalidate timing/IRF validity.
5. **No invented science.** Missing calibration → drive %, not fake µW. Unconfigured bounds → shown as no-verdict, never green. Simulation evidence is labeled SIMULATION ONLY, never claimed as instrument verification.
6. Simulator connection and tests stub camera/instrument enumeration; simulated objects only.

## All owner messages, verbatim and in order

### 1. Session topic (2026-10-30, ~07:39)

Session title: *"Enable photon acquisition for phacq on mt200"*. The working goal derived from the morning exchange: a clear, operator-friendly photon-acquisition application with simple, advanced and guided modes; a complete local simulator; safely controlled, simply calibrated lasers; persistent live diagnostics; novice-first guided workflow; experiment-specific analysis — without compromising recorded photons or disturbing the running MT200 measurement.

### 2. During the guided-wizard work

> always present plts in workflow.

→ Landed: every wizard stage carries live plots (count trace, correlation, decay, stage distributions), kept visible before, during and after acquisition; idle axes drawn empty rather than hidden.

> laser list all connected, do not hide in combobox, before was good. stack: lasername. power, on/off pulsed, calibration btn

→ Landed: `gui/laser_cards.py` — one stacked block per connected head (name, power, on/off, pulsed, Calibrate). No color combobox.

### 3. The UX/UI batch (2026-10-30)

> improve ux/ui use colors to create acq regions, why complete sim and leave sim? there should be only one (complete sim). settings load add ... with file dialog. allow ptu pto json. if there is no calibration for laser, use the percentage values, when user uses calibrated values, use the laser diode reading, diode is additive, minimze turn on off of lasers for pwr reading, ideally use combined pwr to adj the readings, diode linear, use offset. always display hist, camera, etc, even if no data, make interface uniform independent of runnign acq or not, just use empty plts. camera: auto connect, hide record, and detailed settings in ctx menu. detailed quality report only in advanced mode only show yellow, red, in case of simple mode. hide range setter for plts in simple mode, declutter. integrate pwr cal in laser menu. double lick on count rate on count rate enu should open a large count rate display (really large floating window) this is useful for aligning - operator may be far away from screen. remove "power cal" and guided measurement btn from top row. make subfolder for traces belonging to images. images end up in folder traces are places in a subfolder. we talsked about different experiment types: pol single-molecule, smfret, fcs, etc. make a choice for the experiment type that displays different windows depending on the experiment. in smfret need stoich fret and burst view, in pol need aniso decay, lifetime estimate, anisot estimate, calibration tool/helper for g factor l1/l2, in fcs need correlation amplitude brightness, diffusiontime realt ime analysis. so different views should be there dependent on the experiment (just display different docks, this can be just a layout preset, a dock that is not visible should not result in computation, also high count rates may overload the analysis, ie, burat analysis, then just drop the analysis, and display a warning live burst analysis not possible, similar for correlator if cournt rates too high, just slow down analysis, never drop photons. the help btn is not working needs fix. write down my comments contiune what you are working on  and afterwards do what i told you.

Status per item:
- **Colored acquisition regions** — landed (dock accents, four families, spec-review PASS).
- **One complete simulator** — complete local rig exists (`live/instrument_sim.py`, `connect_instrument_simulator`); the *single-lifecycle* cleanup (removing the old complete/leave duplicate controls) is still queued.
- **`…` settings file dialog, PTU/PTO/JSON** — landed and fully reviewed (spec PASS, guard-delta SPEC PASS, quality APPROVED after fixes: worker-thread adoption, no catch-all filter, extension guard).
- **Uncalibrated = %, calibrated = diode readback, additive/linear/offset diode** — landed: additive mixed-diode control with attribution ledger (`live/diode_context.py`), consent before ever zeroing another head, never silently isolate; parent-verified 27 tests.
- **Always-display plots, empty when idle** — landed (persistent empty axes).
- **Camera auto-connect / hide record / ctx-menu settings** — landed (auto-connect configured camera, context-menu settings, unavailable state).
- **Quality: detailed only in Advanced; Simple shows yellow/red only; hide range setters in Simple** — landed.
- **Power cal in laser menu** — landed (per-head Calibrate).
- **Double-click count rate → giant floating alignment display** — landed.
- **Remove "Power cal" + "Guided measurement" top-row buttons** — landed.
- **Image folder with traces/ subfolder** — landed (`point_paths` staging in `parent / 'traces'`).
- **Experiment-type selector with per-type dock layouts (smFRET / pol / FCS)** — landed (dedicated docks `plot_correlation` and `plot_polarization`, run-bar selector, layout sync, and Ströhl et al. 2018 DOI 10.1088/2050-6120/aa872e G-factor helper).
- **High rates: drop analysis, not photons; explicit warnings** — landed (bounded analysis queue, explicit "Live burst analysis not possible" and "Live correlator throttled" warnings).
- **Help button fix** — landed (real `show()` + Escape, click-tested).
- **"write down my comments … afterwards do what i told you"** — that instruction produced `UX_UI_BACKLOG.md` and this file.

### 4. The MT200 correction (2026-10-30, after an early deployment attempt)

> do not restart on mt200, meas is running. continue locally

→ Standing constraint #1. The four files touched before this correction were pulled back; all subsequent work is local and undeployed.

### 5. The guided-novice workflow request (2026-10-30 evening)

Sent twice with the suffix *"for implementing use gpt 6.1 terra!"* (both returns errored client-side and were not processed), then processed on the third send without it:

> the guided requires too many clicks. also the laser pwr should be setup by the user. after the calibrations in guided mode, preset the user the option to measure multiple samples, the calibraiton is valid for all, the dna measurement is used for accurate fret, after that do accurate fret, while measureing the samples user must see burst traces, and ES histogram with marginals. count bursts, meas time etc, display quality indicator, when good simply display green, when yellow/ red tell what should be better. The users are very dumb, they do not know how to do FCS, start with low power to not fry detectos, gradually increase and check correlation amplitude, afterwards give clear instructions on how to dilute, default target volume 50 uL, they are so dumb that they need to be told how many microliters to take from the pre dilution and how to dilute. same rules apply to the single molecule measurements, let the users do FCS before, aim for 5 min FCS before doing longer smFRET experiments, for smFRET use the previous fcs concentration and tell user how to dilute, do it simple, eg, put 47 uL buffer on slide, add 3 uL of the FCS solution.

→ Landed and tested (43 guided/sim/dilution/panel tests, incl. full simulated water→buffer→FCS→green→red→DNA→sample×2 end-to-end):
- **Fewer clicks**: filters+splitter = one optics confirmation; one allow-light gesture chains every head; green stages auto-advance.
- **User sets laser power**: editable per-head session target (µW, calibration-bounded; also editable inside the FCS stage).
- **Multi-sample**: loop "Measure another sample (same calibration)"; references + DNA corrections valid for all samples; accurate-FRET after DNA.
- **Live sample feedback**: burst trace, E–S histogram **with E and S marginals**, bursts/time/photons counters.
- **Quality indicator**: traffic light — plain green when good; yellow/red name the improvement; unconfigured checks are no-verdict and do not block green.
- **FCS-first, novice-proof**: low-power start, gradual increase watching correlation amplitude, ~5 min default; unusable correlation refuses to advance; amplitude-derived N → `live/dilution.py` prints exact µL steps to 50 µL ("put X µL buffer on the slide, add Y µL of the pre-dilution"), auto pre-dilution when unpipettable, "use directly" when already single-molecule.
- Help (`gui/help.md`) documents the novice flow.

### 6. Handoff instructions (2026-10-30, latest)

> write the plan to an md file. you are doing it wrong, need to pass to another agent.

> put all my instructions into and .md file.

→ This file. Execution of the remaining plan passes to a fresh agent (subagent-driven: one implementer lane per wave, one test lane machine-wide, spec review then quality review before proceeding).

### 7. Laser power nag-free in Advanced mode + session ignore (2026-10-31)

> continue with /Users/tpeulen/dev/chisurf/okf/design/2026-10-30-owner-instructions.md add allow adjusting laser pwr without nagging in advanced mode (only simple anoy, add checkbox ignore - remember ignore for session)

→ Landed:
- **Advanced mode nag-free**: adjusting laser power (µW target slider, raw drive %, pulsed mode) in Advanced mode (`ui_mode == 'advanced'` / `model.advanced == True`) applies directly without modal confirmation dialogs; timing/IRF invalidations are noted in `power_change_invalidations` without nagging the operator.
- **Simple mode nags ("only simple anoy")**: in Simple mode (`ui_mode == 'simple'`), adjusting laser power when session references exist prompts the confirmation dialog with an "Ignore" checkbox.
- **Ignore checkbox ("add checkbox ignore - remember ignore for session")**: checking "Ignore" in the confirmation dialog remembers the setting on the model for the remainder of the session (`power_change_ignore = True`), so subsequent adjustments in Simple mode apply directly without nagging.
- Independent focused test suite: `chisurf/plugins/core/acq/test/test_power_nag_suppression.py` (5 passed).

### 8. Laser power max 1 mW, Full power button, max calibration on start, threshold warning, Laser & Shutter dock & foldable settings (2026-10-31)

> weird max power make 1 mW max power (the laser may not reach it in practice).
> add full pwr btn.
> calibrate max pwr on start (typical max 1 mM). Also in sim. max cal with detector shutter closed.
> even if calibrated the laser should show the used percentage. give warning if too close to laser threshold, most lasers start lasering at 40-45% power, below unstable, turn laser info yellow.
> use the tooltips for detailed informations in case of warning
> combine shutter into laser dock. Laser & Shutter
> make better use of foldable settings to hide details.

→ Landed:
- **1 mW max power**: `SimulationRig.seed_power_book` and `AveragePowerMixin.calibrate_max_power` scale to 1000 µW (1 mW). Calibrated target sliders go up to 1000 µW.
- **Full pwr button**: `laser_cards.py` adds a `Full pwr` button (`laser_full_{slot}`) alongside `Calibrate`. On calibrated lasers, it requests 1000 µW (1 mW) and updates the target slider; on uncalibrated lasers, it sets drive to 100%.
- **Max power calibration on start with detector shutters closed**: `AveragePowerMixin.calibrate_max_power(max_uw=1000.0)` strictly closes all detector shutters (`Green`, `Red`) to protect detector channels from strong optical emission, opens excitation shutter, measures dark and 100% drive diode signals, records calibrated points `(dark, 0 µW)` and `(max, 1000 µW)` in `power_book`, restores previous shutter states, and resets the attribution ledger cleanly. Called on start during `connect_instrument_simulator()`.
- **Used percentage shown on calibrated lasers**: `laser_cards.py` displays `Drive: {drive_pct:.1f}%` on every calibrated head card (`laser_drive_pct_{slot}`).
- **Threshold warning (< 45% power)**: Diode lasers have a threshold current around 40–45%; below this drive they operate in an unstable/spontaneous regime. When `0.0 < drive_pct <= 45.0`, the drive percentage line and laser reading turn yellow (`im.text_colored((1.0, 0.72, 0.15, 1.0), ...)`), displaying `⚠ Drive: {pct:.1f}% (near threshold)` and `⚠ {power_reading}`.
- **Detailed warning tooltips**: Tooltips on near-threshold warnings detail that diode output below 40–45% is unstable, spontaneous emission dominates, and timing jitter increases, advising the operator to increase power above 45%.
- **Combined "Laser & Shutter" dock**: `DOCKS` merges shutters into `("laser", "Laser & Shutter", "settings")`. `record.view.json` places the shutters panel under `"dock": "laser"` titled `"Shutters & Diode"`. `docks.window('shutters')`, `docks.is_shown('shutters')`, and `focus_dock('shutters')` are transparently aliased to `'laser'`.
- **Foldable settings to hide details**:
  - `Shutters & Diode` panel is collapsible (`"collapsible": true, "collapsed": false`).
  - `Session` metadata panel in Acquisition settings is collapsed by default (`"collapsible": true, "collapsed": true`).
  - `Running trace` settings panel in Analysis is collapsed by default (`"collapsible": true, "collapsed": true`).
- Independent test suite: `chisurf/plugins/core/acq/test/test_laser_shutter_power_enhancements.py` (7 passed). Full acquisition regression suite: 54/54 passed in 10.67s.

## Current state (2026-10-31)

- Repos: `chisurf` HEAD `69213445a9e68f3412ddaed752979b759cd2b335` (branch not established, no commits); `emtk` 0.1.38; `libphacq`, `tttrlib` siblings. Interpreter `/Users/tpeulen/mambaforge/envs/arm64/bin/python`; env `QT_QPA_PLATFORM=offscreen PYTHONPATH=modules/chimol:modules/mmfdb/src:modules/imp-tricks/src:.` from `/Users/tpeulen/dev/chisurf`.
- Green: guided/sim/dilution/panel **43**; chooser **25**; mixed-diode + power regressions **27**; novice flow **13**; chooser/model/power focused lanes all green.
- **Full-directory acq regression (first complete run): 652 passed, 16 failed, 1 skipped (24 min).** The 16 fall into clusters, classified by git state:
  1. `test_record_laser_settings.py` — **6** failures, root cause diagnosed (`laser_program_shown` requires `advanced` at `gui/record_settings.py:95` vs default `advanced=False` at `gui/record_app.py:136`); implementer lane `deleg_d698171d` active on exactly this.
  2. `test_setup_quality.py` — **3** failures: untracked new test file; `gui/setup_quality.py` does not exist. RED tests of an unlanded slice (setup-reference QC), not a regression. Needs its own implementation lane.
  3. `test_record_windows.py` — **2** failures, both OLD tests (`test_a_run_with_wrong_windows_warns_and_update_takes_the_detected_ones`, `test_keep_leaves_the_windows`); the dirty ALEX round-trip work (`alex_windows_override` at `record_app.py:751`) passes its own new test but likely changed default window behavior. Needs a diagnosis lane.
  4. `test_record_imaging_points.py::test_the_scanner_comes_from_the_settings_file` — **1** failure; the file's local diff is only an import reorder, so this is behavioral (possibly settings-adoption related). Needs a diagnosis lane.
  - 16 − 12 accounted = **4 further failures not captured** by the run's tail cut; enumerate with a targeted rerun once the test lane is free.
- Also pre-existing, outside this directory: emtk 2 GLFW hidden-window pointer failures; libphacq `test_snapi.py` 5 failures (untouched, unrelated).
- Owed: human-style visual read of the new wizard renders (`~/.hermes/cache/scratch/acq-local-ux-evidence/*.png` — pixel checks passed; vision backend was down); the simulated FCS stage's µL-dilution evidence path (tttrlib's concentration knob does not map linearly onto the correlation N; the µL branch is unit-verified with N≈64 instead).

## Remaining plan, in order (for the receiving agent)

1. **Restore the failing tests — mostly DONE.** Child lane `deleg_d698171d` + parent follow-ups: `laser_program_shown` restored to HEAD semantics (program draws in both modes; new regression `test_the_laser_program_shows_in_simple_mode`), `stop_after` test adaptations in laser settings + docks + windows files (runs were hanging — the new semantics "a run measures until Stop" is pinned elsewhere and wins), the stale installed **phacq wheel rebuilt locally** from the current source (shutters `advanced` flags + our pqusb timer fix; local env only), and the Advanced-toggle test adapted to the new **User-mode choice** (`ui_mode='advanced'; ui_mode_changed()` — the old toggle no longer exists). Result: laser settings **15/15**, docks **6/6**, windows **10/10**, imaging scanner **passing after the wheel rebuild**. 11 of the 16 full-run failures fixed.
   - **Setup-quality slice: GREEN 8/8** — the contract grew from 3 to 8 tests during the lane. **Coordination flag:** the owner's own Codex agent (cmux, PID 75410, `codex resume`, active since 22:46, "gpt 6.1 terra") is the main implementer — `record_app.py` +1023/−49, `setup_quality.py`, the test file. Hermes lanes (`deleg_8c91c047` interrupted-nothing-landed, `deleg_fc748c7a` verification + additive dock panel in `record.view.json` + one accent line) verified 8/8 green 3× across its churn and contributed only additive dock registration. **Until that agent goes quiet, no Hermes lane may touch `record_app.py`, `setup_quality.py`, `test_setup_quality.py`, or the laser-power/plot-range regions** — two tests (`test_the_laser_power_slider_drags_edits_and_clamps`, `test_the_ranges_are_applied_to_the_rate_decay_and_histogram_plots`) were transiently red mid-churn at 22:52+ and need a re-run once it settles. Final full-directory rerun still owed after that.
2. **Single simulator lifecycle** — remove the leftover complete/leave duplicate controls; source selection owns the sim lifecycle; safe transitions while idle only.
3. **Image/trace storage layout** — per-image folder with `traces/` subfolder; provenance preserved; never overwrite recordings.
4. **Camera lane** — auto-connect configured camera, hide record controls, settings in context menu, explicit unavailable/waiting message on failure.
5. **Experiment-type selector + layout presets** — smFRET (stoichiometry–FRET, burst view), FCS (amplitude, brightness, diffusion time), pol (anisotropy decay, lifetime/anisotropy estimates, G-factor l1/l2 helper — **research primary literature first, cite DOIs, no placeholder calibration**). Hidden docks must not compute; presets are layout, not data transformation.
6. **High-rate lossless architecture** — bounded droppable analysis queues, never raw photons; explicit "Live burst analysis not possible" / correlator slowdown warnings; the design gates (writer-priority `_push`-before-`_write_batch`, dock-consumer subscriptions, resume/gap semantics) are already written in `okf/design/2026-10-30-acquisition-ux.md`.
7. **Close the owed verifications** — visual read of renders; simulated µL dilution evidence; full-suite green claim.

Execution rules: one implementation lane per wave; only that lane runs tests; spec review PASS before quality review; no commits/push/deploy; protected files = every other lane's uncommitted edits; update `okf/agent-board.md` (controller-only) and this file's status lines as items complete.

## Continuation checkpoint — setup quality

Setup-reference quality implemented locally in `gui/setup_quality.py` and integrated as an Advanced-only dock. Real and simulated reference histories use separate namespaces, including after settings change the output directory. Lifetime has no verdict; diffusion and brightness are judged separately only against configured bounds. External-fit entry time is identified as such, with measurement time unknown. Spec review passed and quality review approved after fixes. Independent local offscreen setup-quality and dock tests: **14 passed**. No instrument verification, deployment, staging or commits. Remaining plan items 2–7 remain open.

## Continuation checkpoint — simulator lifecycle

The Source selector owns the complete simulator lifecycle; duplicate controls removed, idle-only transitions, restored device settings do not open hardware automatically, real profile fields cannot replace the simulated rig setup, and laser backend is restored on exit. Simulated image and point sources follow rig light/shutter state and preserve scan markers (synthetic background scales with illumination, a simulator approximation). Spec review passed, quality review approved; independent local simulator/image tests **20 passed**. No hardware verification or deployment. Image/trace storage is the next wave.

## Continuation checkpoint — image and trace storage

Images now receive their own folders and picked traces go into the corresponding `traces/`; mixed-image project links and independent PTU backtraces retain provenance. Point PTUs stage privately and publish with an atomic no-replace hard link; on publication failure the staged photons are retained and their location reported. Invalid path-bearing names are rejected. Spec review passed, quality review approved; independent local imaging/point tests **17 passed**, including simulated readback and failure cases. Hard-link support is required for publication; unsupported filesystems retain staged data and report the error. Camera is the next wave.

## Continuation checkpoint — camera

Configured camera preview auto-connects after settings restoration; no unspecified camera is probed. The preview remains visible with waiting/unavailable status, clears stale frames on loss, and detailed/record controls are in its context menu. Hidden preview reads pause unless recording. No fallback silently changes camera identity; finalization errors remain visible across disconnect. Spec review passed and quality review approved. Independent local stubbed video tests **18 passed**; implementer focused suite **24 passed**. No real camera or instrument tested. Experiment presets are next.

## Continuation checkpoint — experiment and analysis dependency

Experiment presets remain open: existing session analysis runs synchronously before the raw writer and shared subclasses depend on it, so hiding docks cannot yet meet the no-compute and photon-priority requirements. A dedicated bounded-analysis wave is active before exposing the presets. Independent forward synthetic tests in `test_experiment_polarization_conventions.py` passed (2); they pin G and l1/l2 computation conventions, not a calibration procedure. Existing G-factor input validation and contradictory rt_curves documentation require correction before a helper is exposed. No scientific or hardware validation claimed.

## Continuation checkpoint — writer-priority prerequisite

Unpaused batches are submitted to the raw writer before analysis; writer/source closure is protected against analysis finalization errors, writer close failure is surfaced, and a marker-collision batch is submitted before reporting the collision. Incomplete analysis is marked and not registered as a complete burst run. Narrow spec review passed and quality review approved; independent writer/pause tests **9 passed**. This does NOT complete the lossless design: analysis remains synchronous, overload can delay source reads, and existing explicit pause deliberately excludes photons. Bounded analysis and pause semantics are active follow-up; no instrument verification.

## Continuation checkpoint — analysis pause preserves raw photons

Pause now suspends analysis while raw recording continues; v2 marker semantics state this explicitly. Acknowledged pauses mark analysis incomplete even with no photon events; received totals and analyzed totals are distinct and coherent across threads. Spec review passed, quality review approved; independent simulated pause/writer/rate tests **13 passed**. Full bounded overload handling and dock subscriptions remain open; do not claim lossless acquisition under overload.

## Continuation checkpoint — incremental bounded analysis

Raw batches are written before a bounded optional-analysis consumer; overload or analysis failure disables further analysis for the run and reports an incomplete/no-verdict result. Source errors and overflow are shown immediately and at completion; point capture failures retain the current file and stop subsequent points. Stops drain sources that advertise support, with timeout and explicit errors. Narrow spec review passed, quality review approved; independent simulated bounded/writer/pause/imaging tests **49 passed**. This is not full architecture completion: per-dock subscriptions, correlator slowdown/restart, sustained throughput and real-hardware verification remain open. Experiment views are the next active wave.

## Continuation checkpoint — polarization prerequisite

G-factor input validation rejects invalid intensities/reference anisotropy and non-finite results; documentation now matches the implemented convention and cites DOI 10.1088/2050-6120/aa872e. Spec review passed, quality review approved, independent local tests **26 passed**. This is not an l1/l2 calibration procedure or experiment-preset implementation. Per-dock consumer separation remains the active prerequisite.

## Continuation checkpoint — laser power nag suppression

Laser power adjustments in Advanced mode (`model.advanced == True` or `ui_mode == 'advanced'`) now proceed without modal confirmation dialogs; timing/IRF calibrations are marked invalidated directly in `power_change_invalidations`. In Simple mode, adjusting power when earlier session recordings/references exist displays the confirmation dialog with an "Ignore" checkbox (`power_change.checkbox`). Checking "Ignore" sets `model.power_change_ignore = True` for the session, suppressing subsequent confirmation prompts in Simple mode. All existing and new tests pass (48 passed).

## Continuation checkpoint — experiment selector & dock layout presets

Experiment type selection (`smFRET`, `FCS`, `Polarization single-molecule`, `Image scan`) is now exposed both prominently on the top run bar (`bar_mode`) and within the Acquisition Source panel with clear labeling. The user mode (`Simple`, `Advanced`, `Guided`) is also exposed on the top run bar (`bar_ui_mode`) when window width permits (>= 850px), preventing toolbar clipping on narrow displays. Selecting an experiment type activates its dedicated dock preset:
- **smFRET**: E–S stoichiometry–FRET histogram dock with marginals (`plot_hist`), live mirrored burst trace (`plot_trace`), microtime decays (`plot_decays`), and explicit overload warning `Live burst analysis not possible` on dropped analysis.
- **FCS**: Dedicated FCS correlation dock (`plot_correlation`), real-time correlation curve with log lag scale, live metrics cards (plateau amplitude $N$, molecular brightness in kHz/mol, diffusion time $\tau_D$ via empirical half-decay, and count rate), and `Live correlator throttled` warning.
- **Polarization single-molecule**: Dedicated polarization dock (`plot_polarization`), steady-state anisotropy $r_{\text{cor}}$, apparent anisotropy $r_{\text{app}}$, tail lifetime estimate $\tau$ (ns), active G-factor, parallel/perpendicular counts, time-resolved anisotropy decay $r(t)$ plot, and built-in calibration helper with parallel/perpendicular channel routing configuration and high-NA aperture corrections ($l_1/l_2$) grounded in Ströhl et al. 2018 (DOI 10.1088/2050-6120/aa872e).
- **Image**: Fast-FLIM image dock (`plot_image`) and points table (`points`).
Inactive main docks are hidden and do not compute display frames. All 80 focused regression tests pass in 17.87s without staging or committing.

## Continuation checkpoint — 2026-11-01 responsiveness/modes/example pass (agy + parent)

Owner: "a lot implemented, but not good - improve, make not too complicated, make good ui/ux clear advanced simple mode and guided mode. make sure all works, example sim weird. fix gui responsive." Codex (gpt-6.1-sol) could not run (OpenAI quota exhausted until Nov 4); the lane ran on agy gemini-3.8-flash-high with a verified-findings brief, parent-verified afterward.

- Frame cost (offscreen 1500x950, parent-measured): simple idle 153→39 ms, running 179→87 ms, advanced 154→44 ms, guided 624→34 ms. Causes fixed: modal blur backdrop cached per open+resize instead of per frame; guided cumulative histograms cached per data version (was 6x cumsum/frame); inert background no longer double-drawn behind the wizard; empty-plot placeholders cheapened; emtk software rasterizer hot paths vectorized.
- Mode separation: experiment presets apply their dock sets; Simple shows the experiment's operator docks (expert docks hidden), Guided shows only the wizard, Advanced shows all; user dock overrides persist; reset_layout restores presets.
- Example: physics verified offscreen (FCS N=4.0, tau_D=0.281 ms, 150 kHz/mol; smFRET E populations 0.248/0.704, 1794 bursts; image 64x64x4, tau 1.0/3.5 ns); non-PIE schemes were misfiltering photons by microtime — fixed. Screenshots in scratch/acq-ui-status/example-*.
- Full suite after the pass: 804/806. The two reds root-caused and fixed by parent: (1) duration-boundary photon truncation was removed (delivered batches are atomic) but elapsed overshot to segment end — fixed in RecordSession: a duration is propagated to any source that accepts one (simulator ends its generation there like a device timer; _self_timed now includes hasattr(source,'duration_s')); guard-test tolerance widened to one batch with comment; (2) restore_settings auto-connects again ONLY when a device is attached (attached_devices enumeration), else shows the Choose Load hint — satisfies both the snapi restart test and the no-hardware-restore lifecycle test.
- Status: local only, nothing committed, no remote/MT200 contact. Vision backend still down (all image reads timed out); human visual pass over the new screenshots still owed.
- FINAL: full acq suite after the parent fixes **806 passed, 0 failed (462.93 s)** — acq-final.log in scratch.

## Continuation checkpoint — 2026-11-01 simulator laser semantics (owner round)

Owner: "default sim why also burst with laser off, why lasers not turned on when acq starts, make 60 uW (blue), 25 uW (red) default setting." All three root-caused with probes and fixed:

1. Bursts with laser off — `_RigSource.read` gated only FRET-species photons (`truth < len(populations)`); donor-only/acceptor-only/aggregate photons (truth >= n_pop, present under the default REALISTIC preset) bypassed the gate entirely. Now every labeled molecule photon scales with its exciting head; with the laser off only detector background remains (and none at all once the excitation shutter closes). Unit-pinned in test_simulator_laser_defaults.py.
2. Lasers at acq start — start() now switches the SIMULATED emission on (simulator only; real hardware keeps gesture-only light) and Simple mode opens the shutters as before.
3. Defaults 60/25 µW — new `laser_diode_drive_for_power` inverse + `DEFAULT_LASER_TARGETS_UW {488: 60, 640: 25}`; connect applies them after calibration (drive 38.78%/48.22% at the 1 mW book) and re-captures laser_program; guided protocol targets updated. The rig's excitation gain is measured RELATIVE to these defaults (1.0 at 60/25 µW = the canonical tuned view; dimmer below; saturated above), so FCS brightness contracts and the smFRET burst view hold at the default powers.
4. Found and fixed on the way: `DiodeContext.head_emitting` now false while emission is blocked (the diode itself reads dark); a session-verified driven head is never silently zeroed by another head's request (wizard chain had green zeroed by red's apply); `SimulationRig.source` stage overrides apply only when the caller passes no populations (the guided FCS stage's model sample was silently replaced by a brightness-100000 default that wrote 564 MB per run; bare default now N=4, 150 kHz).

Status: local only, nothing committed; full-suite verification running (acq-laser-defaults.log).

FINAL (laser-defaults round): full acq suite green after the idle-targets reconciliation — drives stay ZERO while idle (passive dark capture + mixed-diode consent contracts intact); 60/25 µW live as the heads' TARGETS on the cards; acq start applies them (drive 38.78%/48.22%) together with simulated emission. head_emitting keeps its original driven+output-enabled semantics; the session-verified-head preservation (ledger entry) is what protects the wizard chain. Entry logged above; see acq-final2.log.

FCS window + Settings-in-workspace round: (1) the live correlation window is bounded by the acquisition — G(τ) is only published for 0 < τ ≤ acq span (was: every lag the 25-cascade correlator emits, i.e. garbage lags far beyond the measurement); the window grows with the running acquisition; pinned by test_correlation_window_is_bounded_by_the_acquisition (2 s cap → 5 s cap on a longer stream). All consumers (FCS dock, guided plots, QC, fits) get valid lags only. (2) Settings dock moved into the central workspace (main tabs, alongside the plots); visibility unchanged — Advanced only (probe: simple shows 8 operator docks w/o settings; advanced includes it). Two stale pins updated (test_emtk_record_docks workspace membership, test_phacq_settings_dock region). Full suite after both: acq-settings-workspace.log. No git ops; local offscreen only.

## Owner round 2026-11-01 (evening) — obis + NI + settings; verbatim and in order

> continue with chisurf.acq plugin. fix all issues, make sure it works fast.

> also the laser settings need to be in the settings, let user connect different lasers, all lasers connected to sys must show up in settings, so that user can select which laser actually ar4 use. the presets json also needs better editor, for json why not use code edit, alredy exist.

> https://github.com/craggslab/ clone gits form https://github.com/craggslab/ to junk learn how they did it (treat as okf like) also need the obis laser support for normal obis and the national instrument ard support.

> but must map to MFD pie with alex to pie.

> the ni goes to libphacq

> must be general, not only dingle ondr acceptr, like the mfd pie stuff

Status where each landed:
- **junk clones** — `chisurf/junk/smfBox` (e81ff90, analysis notebooks) and `chisurf/junk/smOTTER` (d542278, acquisition software; `nicard.cpp/.h` is the NI DAQmx recipe: DO waveform at the control resolution across the ALEX period from duty cycles, counter edge-decode into photons, AI laser-power readback triggered off the DO start). Findings recorded as **`okf/references/craggslab-smfbox-smotter.md`** with CHISURF-REVIEWED headers on the mined files.
- **NI → libphacq** — LANDED: `modules/drivers/ni/` (general N-laser/N-detector slot-plan DO waveform, counter photon events, AI power readback, simulator; DAQmx optional) and `modules/drivers/obis/` (serial, simulator, CDRH guard, box device-index routing) — **general per the owner constraint: N lasers / N detectors / arbitrary PIE-ALEX slot plans, never a hardcoded donor/acceptor pair**; the waveform derives from the general laser program (`pie_slots` shape), ALEX→PIE and the MFD paths unchanged. Controller-verified: every simulated photon inside a slot window, monotonic, routed, macro-time-only; 4-slot multi-laser + gap waveform unit tests. Chisurf `open_laser("obis")` → phacq-backed `ObisBackend` (W setpoints, DIGITAL gate for pulsed, oscillator program kept for `pie_slots`; CDRH cleared at open). Env wheel rebuilt so both drivers load. Tests: libphacq ctest 4/4 + pytest 54; chisurf `test_obis_backend.py` 9.
- **Obis command set** — researched from four independent implementations (storm-control `obis.py`, AndrewGYork/tools `coherent.py`, amsikking `coherent_OBIS_LSLX_laser_box`, mmCoreAndDevices PR #645 + Coherent OBIS LX/LS operators manual §9.2.5): `\r` terminator, response + `OK\r\n` handshake, 115200 8N1; `SYSTem:INFormation:{MODel,WAVelength,POWer,TYPe,SNUMber}?`; `SOURce:POWer:LIMit:{LOW,HIGH}?`; `SOURce:POWer:LEVel:IMMediate:AMPLitude <W>`; `SOURce:AM:{STATe,SOURce}` (CWP/CWC/DIGITAL/ANALOG/MIXED/DIGSO/MIXSO); `SYSTem:AUTostart`, `SYSTem:CDRH`, `SYSTem:ERRor?` → `ERR-xxx`; device-index prefix `SYSTem<i>:`/`SOURce<i>:` selects the laser in a box (0 = the laser when directly connected).
- **Laser settings in the Settings dock** — LANDED: `laser_devices()`/`select_laser_device()` (2 s-cached passive enumeration across sepia/obis/ni phacq drivers + CMC + auto/simulated; idle-only reconnect, light off) + the "🔦 Lasers" category with the Use-per-row chooser + the `lasers` group riding the JSON document both ways. Settings suite 11 passed; renders inspected.
- **Presets JSON editor** — the Settings dock's JSON source editor now uses the real code editor (new public `emtk.draw_editor`, emtk 0.1.39, colourised JSON, click-to-focus; view_form's `_draw_code_editor` delegates to the same loop; emtk suites green 335 passed).
- **Fast** — the 2026-11-01 responsiveness pass above (frames 624→34 ms guided) stands; the round's red chooser test (`connecting` race) fixed deterministically (adoption held open by a gate; chooser suite 23 passed).

## Owner round 2026-11-02 — "acq plugin stutters every few seconds, when laser off acq must continue, also simulated acq"

- **Stutter, root-caused:** two option lists drawn every frame refreshed every 2 s *synchronously*: the
  Settings-library setup list (`setup_options` -> `library_setups`, ~0.2 s: opens the setup DB) and the
  laser-device enumeration (`laser_devices` / `_sepia_status` / `_cmc_status`, ~0.33 s). New
  `gui/refreshed.py` (`Refreshed`: last value at once, refresh on a worker; `now()` for actions;
  `HARDWARE_LOCK` + `@holds_hardware` on `connect_laser` / `disconnect_laser` / `connect_device`, so an
  enumeration never runs while a device is being opened). Measured worst call: 221/328 ms -> 16/0.5 ms.
  Actions (connect, start with a library setup, settings load) read availability/setups fresh.
- **"Acquisition stops" (laser off, simulator too), root-caused:** the recording itself never stopped
  (laser off -> background-only photons keep being recorded: verified 3.6k -> 1.6k photons/s). What
  stopped was the *live analysis*: `BoundedAnalysis` closed itself for the rest of the run after one
  overflow (a >1.6 s hiccup -- GC, first import, the 2 s refresh stalls above), and the run bar / plots
  read the analysis' counters, so the run looked frozen. Now an overflow is a **gap**: the batch is
  skipped, a continuity boundary (the pause's flush) goes in before the next accepted batch, and the
  analysis continues; the run stays `analysis_complete=False` with the explicit warning. The run bar's
  clock is the recorder's (`received_elapsed_s`). Verified: a forced 3 s analysis stall recovers
  (bursts 67 -> 213 by the end, one gap).
- Tests: full acq suite **824 passed**; `test_bounded_analysis.py` rewritten to the gap-and-resume
  contract. Uncommitted (shared files): `gui/record_app.py`, `gui/record_settings.py`,
  `gui/refreshed.py`, `live/bounded_analysis.py`, `test/test_bounded_analysis.py`,
  `test/test_simulator_lifecycle.py`.
