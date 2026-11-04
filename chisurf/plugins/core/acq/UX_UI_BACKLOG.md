# Acquisition UX/UI requirements and implementation order

## Active constraint

MT200 is actively measuring. Work and verification are **local only**. No remote commands, deployment, restart, acquisition probes, laser/shutter commands, camera access or scheduled-task actions on MT200 until the owner explicitly authorizes them again. Historical permission to restart is superseded.

## Implementation order

1. Finish the current work: shared modal wizard with fixed navigation and blurred/noninteractive background; always-present live plots and stage-specific reference/IRF/DNA checks; visible stacked controls for every connected laser; vertically stretched Quality dock; complete instrument simulator; safe calibrated-power gesture and explicit post-measurement warning; truthful backend timer limit.
2. Then implement the new requirements below in tested vertical slices. Do not call a simulated/backend-only feature a verified real instrument feature. Preserve unrelated shared working-tree changes. No commits/publishing/deployment without authorization.

## Current-work acceptance requirements (earlier owner corrections)

- No Guided measurement dock: only the guided modal wizard.
- Previous / Stop-block-light / Next remain reachable at the bottom; task content scrolls.
- Guided measurement always contains plots, not only instructions and a final results table. Show live count rates, correlations, decays and stage-relevant distributions/checks while measuring water/IRF, buffer, reference dyes, DNA and sample. Keep plots present before data and after acquisition; distinguish waiting, advisory estimates and validated checks.
- Show quantitative/visual reference analysis and configured acceptance limits. Missing data or unconfigured scientific criteria are not a pass. Do not invent universal dye, diffusion, lifetime, anisotropy or FRET calibration bounds.
- Quality table fills its available dock height and resizes with the dock. Keep advice/explanations in tooltips, not a Guidance column or duplicate prose.
- List **all connected lasers**, not a color/laser combobox. Each stacked block: laser name, power, on/off, pulsed switch, calibration button.
- The existing pqusb one-hour fallback is a software policy, not an established hardware duration limit. Remove the arbitrary policy only within supported timer semantics. Never claim that a 100-hour finite timer is truly unlimited, or restart/splice acquisitions without clock-continuity evidence.

## New requirements — queued after the current work

### Local implementation checkpoint

- Implemented and exercised: shared wizard/footer/blur; live count-rate, native multi-tau correlation, decay/IRF and stage-specific plot frames in every workflow stage; full-height Quality table; stacked connected-head controls; automatic calibrated-target gesture plus confirmation; percentage-drive fallback when a calibration is missing.
- First new decluttering fixes landed: removed global **Power cal** and **Guided measurement** buttons from the acquisition row. Use each laser's **Calibrate** control and the **Guided** operating mode. Help now calls the real `show()` API rather than attempting to call its boolean `open` flag; real toolbar-click/content/Escape tests cover normal and narrow hosts.
- Next local UI slice is implemented and tested: task-colored dock regions; **Load …** file chooser with native PTU/PTO/JSON readback and inert background; Simple-mode warning-only Quality and no range setters; persistent empty main plot axes; giant floating alignment readout from a real rate-row double click. Full-run mean can be derived from native photon/duration counters. File loading also refuses active power-servo changes and clears a stale workspace reload selection.
- Latest combined focused acquisition verification: **105 passed**. Fresh simple/advanced, chooser and giant-rate renders were generated and inspected. Independent spec/quality reviews are separate gates, still in progress.
- Complete simulated water, buffer, green reference, red reference, DNA and sample recordings have been written as six distinct PTUs and independently read back. Curves/decays/counts come from those generated photons. This is simulation evidence, not MT200 verification.
- Scientific boundary: amplitude-derived N/raw brightness are preliminary; fitted diffusion time and fitted lifetime remain explicitly **unverified**, not invented. Configured live-check failures block stage acceptance. Missing scientific bounds are shown, not counted as passes.
- The local pqusb change uses the documented 100-hour maximum instead of the arbitrary one-hour fallback. It is a finite single-acquisition limit, not proven unlimited operation; nothing has been deployed to the running instrument.
- Still queued from the new list: single-source simulator lifecycle/duplicate sim controls; additive-offset multi-laser diode compensation (implementation lane active; current qualified controller still isolates other heads); camera auto-connect/context-menu/empty-preview simplification; image/trace directory structure; experiment-dependent layouts and validated analyses; hidden-dock and high-rate scheduling. No completion is claimed for these items.

### Novice guided workflow checkpoint (2026-10-30 evening)

- Implemented and tested locally: the two optics checks merged into **one optics confirmation**; **one allow-light gesture chains every laser head** through the power stage; the power page offers an **editable session target** per head bounded by its calibration; **green stages advance automatically**; a new **FCS-first stage** (low-power start guidance, correlation-amplitude checks, ~5 min default) reads the amplitude-derived N and prints **explicit µL dilution volumes** for smFRET via the new `live/dilution.py` advisor; **multi-sample loop** keeps calibration/references/DNA corrections valid for every sample; DNA/sample views now show the **burst trace**, **E–S histogram with marginals**, **burst/time/photon counters**, and a **green/yellow/red traffic light** that names what to improve.
- Verification: `test_guided_novice_flow.py` **13 passed** (incl. FCS repeat-until-usable with in-stage power adjust, direct-use when already single-molecule, and unverified≠warning traffic-light semantics), dilution advisor suite green, guided/sim/panel suites **43 passed** combined including the seven-stage simulated end-to-end (water, buffer, FCS, green, red, DNA, sample with finish plus a second sample).
- Render evidence regenerated end-to-end (`~/.hermes/cache/scratch/acq-local-ux-evidence/`): optics/power/FCS-instructions/FCS-live/DNA/sample-2 captures plus `render-rects.json`; pixel verification confirms the traffic light renders **green** on a passing sample and **yellow** while waiting, and the E–S stage cell draws heatmap-plus-marginal structure. The image-analysis backend timed out repeatedly this round, so a human-style visual read of the new captures is still owed; FCS dilution readback printed a correct direct-use verdict for the simulated concentration (the explicit-µL branch is unit-verified with N≈64). The simulated FCS pre-dilution was made realistically bright (448k photons) — tttrlib's engine does not map its concentration knob linearly onto the amplitude N, so the render shows the honest direct-use case.
- FCS stage power stepping is guided but every emission change remains an explicit operator gesture; the dilution math never invents concentrations, and missing quality bounds still never display green.

### 1. Visual hierarchy and uniform acquisition surfaces

- Use restrained color accents to create recognizable acquisition regions (instrument controls, acquisition, live analysis, quality/status).
- Keep histogram, camera and other applicable plot surfaces visible whether acquiring, stopped or empty. Draw empty axes/placeholders rather than replacing the layout or hiding plots for lack of data.
- Keep routine/simple mode uncluttered. Hide plot range setters there; retain them in Advanced mode or an appropriate context menu.
- Show the detailed quality report only in Advanced mode. In Simple mode surface only yellow/red warnings and actionable failures; do not flood it with passing checks or verbose advice.
- Remove the **Power cal** and **Guided measurement** buttons from the top row. Keep workflows accessible through their appropriate menus/mode controls.

### 2. Exactly one complete simulator

- There is only one simulator mode: the complete instrument simulator (PIE heads, sequencer, shutters, diode, photon data and workflow support).
- Remove the confusing separate **Complete PIE simulator** and **Leave simulator** buttons/workflows. Source selection owns simulator lifecycle, with safe transitions while idle.
- Synthetic calibration and results remain explicitly labeled and isolated from laboratory data.

### 3. Settings loading

- Add a visible **…** file-dialog button beside settings loading.
- Accept **PTU**, **PTO** and **JSON**. Recover stored acquisition settings from supported measurement/project containers; validate the format and show useful errors without modifying instrument state for an invalid file.
- Local selection/preview must not secretly connect hardware. Preserve the established explicit settings-application semantics.

### 4. Laser controls and additive diode feedback

- Keep every connected laser visible as a stacked block; do not hide heads behind a combobox.
- If a laser has no valid calibration, offer **drive percentage** controls instead of a dead µW control. Label the unit and calibration state clearly; never present drive percentage as measured optical power.
- When calibrated µW controls are used, use fresh **laser-diode readback** for control and displayed measured power.
- The diode is additive and linear with an offset. Minimize toggling other lasers merely to obtain a reading. Prefer a combined-signal/baseline correction using calibrated, stable contributions and the diode offset.
- Identifiability guard: one summed diode reading alone cannot identify several independently unknown changing powers. Use known/stable contributions or single-head-change differences; otherwise label combined/individual power unavailable rather than fabricating per-head readings. Verify offset/linearity assumptions in tests and with measurements before claiming hardware validation.
- Keep safe bounds, shutter/readback checks and failure shutdown. Never change a real active measurement's illumination as an incidental UI action.
- Integrate power calibration in the **Laser menu/surface**, including per-head calibration actions, rather than a top-row global button.
- Warn before post-measurement power/pulse changes and invalidate dependent timing/IRF calibrations. In Advanced mode, allow adjusting laser power/drive/pulsed without confirmation nagging (apply directly, noting invalidations). In Simple mode, show the warning dialog with an "Ignore" checkbox to remember the choice for the session. Preserve independent diode-to-average-power calibration curves where still applicable.

### 5. Camera

- Auto-connect the configured camera/preview.
- Hide recording controls from the normal camera surface.
- Put recording and detailed camera settings in its **context menu**.
- Retain a camera surface with an explicit unavailable/waiting message when connection fails; do not claim a simulated or missing feed is live.

### 6. Alignment count-rate display

- Double-clicking a count-rate item/surface opens a **very large floating count-rate window**.
- Use genuinely large, distance-readable detector/sync rate numerals for alignment by an operator away from the screen.
- Keep the ordinary count-rate dock compact. Share real rate data and automatic Hz/kHz/MHz scaling; do not invent rates or open an additional device handle.

### 7. Image and trace storage

- Each image acquisition gets its own folder.
- Point traces belonging to that image go in a **traces/** subfolder inside the image folder, not mixed into the image directory or the global recordings folder.
- Preserve trace/image provenance and portable dataset links; do not overwrite existing recordings.

### 8. Experiment selector and layout presets

*(Landed locally: exposed in run-bar and Acquisition panel; dedicated `plot_hist`, `plot_correlation`, `plot_polarization`, `plot_image` docks; Ströhl et al. 2018 DOI 10.1088/2050-6120/aa872e G-factor helper; bounded queue & overload warnings; 10 dedicated tests pass)*

- Add an explicit experiment-type choice, including **polarization single-molecule**, **smFRET** and **FCS**.
- Choosing a type shows its appropriate dock layout/preset; switching layouts is not a scientific transformation of already-recorded data.
- **smFRET:** stoichiometry–FRET plot, burst view and the applicable traces/decays.
- **Polarization single-molecule:** anisotropy decay, lifetime estimate, anisotropy estimate, and a guided calibration helper for **G factor and l1/l2**. Trace equations, conventions and model assumptions to primary literature before implementation; no placeholder calibration results.
- **FCS:** live correlation, amplitude, molecular brightness and diffusion-time analysis with explicit model/background/fit limits and readiness state.
- An analysis dock that is not visible must not keep computing merely for display. Preserve the acquisition/recording path independently of analysis visibility.

### 9. High-rate behavior: recording before analysis

- At rates that overload live burst analysis, drop/skip **analysis work**, not recorded photons. Display **Live burst analysis not possible** (or an equally explicit warning).
- Throttle or reduce correlation analysis work at high count rates and report it.
- Do not silently discard raw photons to keep analysis responsive. Architect and test recording independently from bounded, droppable analysis queues.
- Report actual FIFO overflow/device/storage data loss separately and explicitly; no promise of lossless acquisition beyond measured hardware/storage throughput.
- Test hidden-dock gating, bounded analysis backlog, throttling, warning recovery and unchanged raw PTU photon counts.

### 10. Help

- Fix the nonworking Help button.
- Exercise a real click and verify visible help content and dismissal, including interaction with modal/table surfaces. A successful open-method call alone is insufficient.

### 11. Guided workflow — novice-first (owner's latest, 2026-10-30 evening)

- **Fewer clicks.** The guided wizard currently demands too many interactions; streamline stages, sensible defaults and auto-advance so a novice completes a session with minimal clicking.
- **Laser power is set by the user.** After calibration, guided mode offers explicit per-head power setup (calibrated µW or drive %) instead of buried/automatic choices; the chosen powers apply to the whole session.
- **Multi-sample sessions.** After the guided calibrations, present the option to measure **multiple samples**: the calibration (and the DNA measurement) is valid for all of them; the DNA measurement provides the corrections for **accurate FRET**; each following sample is then measured with accurate-FRET settings.
- **Live sample feedback.** While measuring samples the operator must see: burst/intensity traces, an **E–S histogram with marginal projections**, and counters (burst count, measurement time, etc.).
- **Quality traffic light.** When everything is good, display simply **green**. Yellow/red states must say **what should be better** (novice-actionable guidance), consistent with the Simple-mode warning-only rule.
- **FCS-first for novices.** Users do not know FCS: start at **low laser power** to protect detectors, gradually increase while checking the **correlation amplitude**, then give explicit **dilution instructions**. Default target volume **50 µL**. Instructions must state exactly **how many µL to take from the pre-dilution and how much buffer to add** ("put 47 µL buffer on the slide, add 3 µL of the FCS solution").
- **FCS before single-molecule.** Same rules for smFRET: do FCS first, aim for **~5 min FCS** before longer smFRET experiments; for smFRET reuse the previous FCS concentration and tell the user how to dilute to it with simple µL instructions.

### 12. Laser 1 mW max power, Full power button, max calibration with detector shutters closed, threshold warnings, Laser & Shutter dock & foldable settings (2026-10-31)

- **1 mW max power.** Power calibration and target range support up to 1000 µW (1 mW), replacing the simulated 10 µW cap.
- **Full power button.** Each laser card provides a `Full pwr` button (`laser_full_{slot}`). For calibrated heads it requests 1000 µW (or calibrated max); for uncalibrated heads it sets drive to 100%.
- **Max power calibration on start with detector shutters closed.** `calibrate_max_power(max_uw=1000.0)` strictly closes all detector shutters (`Green`, `Red`) to protect detectors, opens excitation shutter, measures dark and 100% drive readback, and pairs them in `power_book`. Runs automatically on startup in the simulator.
- **Used percentage on calibrated cards.** Calibrated laser cards display the active drive percentage (`Drive: {drive_pct:.1f}%`).
- **Threshold warning (< 45% power).** Diodes near or below the lasing threshold (~40–45%) are unstable; when `0 < drive_pct <= 45.0`, the drive percentage line and laser reading turn yellow (`⚠ Drive: ... (near threshold)`) with detailed tooltips explaining threshold physics.
- **Combined "Laser & Shutter" dock.** Shutters are merged into the `Laser & Shutter` dock (`"dock": "laser"`, `"title": "Shutters & Diode"`). `shutters` window lookups and focus calls are aliased to `laser`.
- **Foldable settings.** Panels (`Shutters & Diode`, `Session`, `Running trace`) use collapsible folding to declutter the settings tabs.

## Verification bar

For each slice: write/run the failing regression, implement, rerun focused tests, execute the real local/simulated path, inspect a populated and an empty render at practical large/small window sizes, and verify click/scroll reachability. Re-read saved PTUs independently where recording changes. Record known unsupported scientific/hardware behavior rather than substituting invented results.

## Owner's latest request — verbatim (guided workflow, 2026-10-30 evening)

> the guided requires too many clicks. also the laser pwr should be setup by the user. after the calibrations in guided mode, preset the user the option to measure multiple samples, the calibraiton is valid for all, the dna measurement is used for accurate fret, after that do accurate fret, while measureing the samples user must see burst traces, and ES histogram with marginals. count bursts, meas time etc, display quality indicator, when good simply display green, when yellow/ red tell what should be better. The users are very dumb, they do not know how to do FCS, start with low power to not fry detectos, gradually increase and check correlation amplitude, afterwards give clear instructions on how to dilute, default target volume 50 uL, they are so dumb that they need to be told how many microliters to take from the pre dilution and how to dilute. same rules apply to the single molecule measurements, let the users do FCS before, aim for 5 min FCS before doing longer smFRET experiments, for smFRET use the previous fcs concentration and tell user how to dilute, do it simple, eg, put 47 uL buffer on slide, add 3 uL of the FCS solution.

## Owner request 2026-10-30 (UX batch) — verbatim

> improve ux/ui use colors to create acq regions, why complete sim and leave sim? there should be only one (complete sim). settings load add ... with file dialog. allow ptu pto json. if there is no calibration for laser, use the percentage values, when user uses calibrated values, use the laser diode reading, diode is additive, minimze turn on off of lasers for pwr reading, ideally use combined pwr to adj the readings, diode linear, use offset. always display hist, camera, etc, even if no data, make interface uniform independent of runnign acq or not, just use empty plts. camera: auto connect, hide record, and detailed settings in ctx menu. detailed quality report only in advanced mode only show yellow, red, in case of simple mode. hide range setter for plts in simple mode, declutter. integrate pwr cal in laser menu. double lick on count rate on count rate enu should open a large count rate display (really large floating window) this is useful for aligning - operator may be far away from screen. remove "power cal" and guided measurement btn from top row. make subfolder for traces belonging to images. images end up in folder traces are places in a subfolder. we talsked about different experiment types: pol single-molecule, smfret, fcs, etc. make a choice for the experiment type that displays different windows depending on the experiment. in smfret need stoich fret and burst view, in pol need aniso decay, lifetime estimate, anisot estimate, calibration tool/helper for g factor l1/l2, in fcs need correlation amplitude brightness, diffusiontime realt ime analysis. so different views should be there dependent on the experiment (just display different docks, this can be just a layout preset, a dock that is not visible should not result in computation, also high count rates may overload the analysis, ie, burat analysis, then just drop the analysis, and display a warning live burst analysis not possible, similar for correlator if cournt rates too high, just slow down analysis, never drop photons. the help btn is not working needs fix. write down my comments contiune what you are working on  and afterwards do what i told you.
