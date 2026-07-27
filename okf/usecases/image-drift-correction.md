---
type: Reference
title: Use case — inter-frame drift correction
description: Measure and remove stage drift in a camera stack or a photon-stream confocal image — pick the channel, the reference frame and how the correction is applied, read the drift trace and the before/after projections, and export the corrected stack and the shift table.
tags: [usecase, imaging, drift, preprocessing, microscopy, clsm]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: inter-frame drift correction

**Goal:** find out whether the sample moved during the acquisition, by how much,
and remove it. For a plain intensity image drift is a cosmetic blur; for anything
that correlates *frames* — RICS/ICS, number & brightness, a frame-lag FCS carpet
— a translation between two frames looks exactly like diffusive decorrelation, so
uncorrected drift inflates the fitted diffusion coefficient. This is the
pre-processing step that has to happen before every per-pixel map, and the one
that decides whether the rest of the imaging pipeline is measuring the sample or
the stage.

**Data:**

- a real camera movie — `junk/PAM-sampledata/N-and-B/01_Venus_130604_…_BB_stack3.tif`
  (100 frames, 300 × 300, uint16, live cells expressing Venus);
- a real photon stream — `test/data/clsm/PQ_Olympus_MFIS.ht3` (40 frames,
  256 × 256, 5 routing channels);
- a ground-truth control built for this run: the first 20 frames of the repo's
  `test/data/rics/RICS_EGFPGFP.tif` rolled by a known linear drift
  (dy = 0.2·k, dx = −0.1·k px per frame).

## Steps

1. Open the tool. Either **Imaging → Drift Correction** standalone
   (`ImgDriftTool`), or **Spectroscopy → Image Tools** and pick **🎯 Drift**,
   the third navigation entry, above the numbered steps. Headless:
   `csc img-drift STACK.tif --out-shifts drift.csv --out-stack corrected.tif`.
2. Load the movie: drop the file on the window, or use the 📂 button beside
   **Image** (a database entry works too). The tool reads the file, fills the
   **Measure on** channel list, and *starts measuring immediately* — dropping a
   file is the run trigger, there is no separate "load" step.
3. Pick the channel the estimate runs on in **Measure on**. The sample moves as a
   whole, so one channel drives the estimate and the correction is applied to
   every channel; choose the brightest, most structured one.
4. Choose a **Reference**: *First frame* (slow monotonic stage drift; never
   accumulates error), *Previous frame* (follows non-monotonic wander, but small
   per-frame errors add up), *Stack mean* (noisy data — note that under this
   reference frame 0 is displaced like every other frame, so its row is not zero).
5. Choose **Apply by**: *Wrapping* rolls what leaves one edge back in at the
   other and conserves every photon; *Blanking* drops it and leaves the vacated
   strip empty.
6. Open the collapsed **Estimator** box if the trace looks wrong: **Smoothing
   (σ px)** blurs the cross-correlation before the peak search (default 2.0), and
   **Sub-pixel refinement** fits a parabola through the peak's neighbours.
7. Press **▶ Measure** after any of those changes — nothing recomputes on its own.
8. Read the answer in the status line at the bottom left: `Max drift 7.3 px over
   100 frames`, or `Max drift below one pixel — correction changes nothing`.
9. Look at the **Drift trace** tab: `dx` (blue), `dy` (orange) and `|d|` (grey)
   per frame. A straight line is stage drift, a step is a bump or a refocus,
   noise about zero means there was nothing to correct.
10. Check it in the **Projection** tab — all frames summed, before and after. This
    is the check that does not depend on the numbers: drift shows up on the left
    as a directional blur that sharpens on the right.
11. Read the per-frame numbers in the **Shifts** tab (`Frame`, `dx / px`,
    `dy / px`, `|d| / px`).
12. Export: **💾 Export shifts** writes `frame,dx_px,dy_px,magnitude_px` as CSV;
    **💾 Export stack** writes the corrected multi-page TIFF with *every* channel
    corrected by the single estimate. Both open a save dialog pre-filled beside
    the source file (`….drift.csv`, `….corrected.tif`).

## Expected

- The measured shifts reproduce a drift that is really in the data, to about a
  pixel, and the maximum displacement is stated in pixels in one line.
- Wrapping conserves the total signal exactly; blanking loses only what left the
  frame.
- The After projection is visibly sharper than the Before one when there was
  drift, and indistinguishable from it when there was none.
- A photon stream is corrected **photon by photon**, so the corrected confocal
  image is still usable for lifetime, decay and correlation work.
- The exported stack is the stack the user just approved on screen.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, `arm64` env) standalone and
inside the Image Tools hub; every tab visited and every screenshot inspected.

**The measurement is right and it is fast.** On the ground-truth control the tool
recovered the injected drift to within one pixel on every frame
(`Max drift 4.1 px over 20 frames`, 16 of 20 frames exact, the rest off by 1 px —
this is real-data estimator noise: consecutive frames of a live confocal movie
are not the same image). The default smoothing matters and is well chosen: at
σ = 0 fifteen of twenty frames come back wrong, by up to 2 px; σ = 1 → 6 wrong,
**σ = 2 → 4 wrong**, σ = 4 → 5 wrong. Photons are conserved exactly under
wrapping (22 781 387 before and after) and blanking loses the 1.2 % that left the
frame, as documented. The 100-frame camera movie measures in **1.2 s** and the
40-frame × 5-channel photon stream in **1.9 s**, so no progress indication is
needed; the run happens on a worker thread and the UI stays live. The CLI
(`csc img-drift … --json`) produces the same numbers. The `?` help is genuinely
good — it explains why drift is a systematic error rather than a cosmetic one.

**What a user actually hits:**

- **A file the tool rejects takes the previous result with it, silently.**
  Dropping `Leica_SP8.ptu` (one frame — nothing to align) on top of a finished
  measurement leaves the window *completely unchanged*: the old file name in the
  **Image** field, the old drift trace, the old 100-row shift table, and the old
  `Max drift 7.3 px over 100 frames` in the status bar. Internally the model has
  already switched to the rejected file and thrown the result away. Everything on
  screen now describes a measurement that no longer exists, for a file that is no
  longer loaded, and the explanation (`1 frame(s): drift correction needs at
  least two`) is never shown anywhere. Same for an unreadable file. RF-554.
- **When a run does fail, the status bar says only "Drift measurement failed".**
  The reason — which the model computed and stored — is dropped. RF-555.
- **▶ Measure and both 💾 Export buttons do nothing, quietly, when their
  precondition is unmet.** No message, no disabled state; clicking Export before
  a measurement is indistinguishable from a broken button. RF-556.
- **"Apply by" is inert until the next Measure.** Switching Wrapping ↔ Blanking
  leaves the After projection exactly as it was — but **Export stack** applies
  the *current* mode to the stored shifts, so the file written is not the image
  the user just approved. RF-557.
- **The Before/After pair cannot be compared.** The two panels are laid out
  unequally (image widgets 349 px and 560 px wide, so the same field is drawn at
  two different zooms) and each auto-scales its own contrast (`levels` [0, 407]
  on the left, [86, 395] on the right), so identical counts are painted different
  colours. Guide 43 tells the user "if your after looks no sharper than your
  before, the correction did not work — do not export it"; that judgement cannot
  be made from this pair. RF-558. On the real cell movie the summed projection is
  in fact marginally *less* structured after correction (std 49.5 → 48.9) because
  most of what the estimator tracked is sub-pixel jitter around a slow trend —
  worth knowing before trusting the visual check.
- **Inside Image Tools the Drift panel is not connected at either end.** After
  picking the measurement for the pipeline, every other panel receives it
  (`1. Intensity` shows the file) while Drift still says *No image loaded* —
  `DriftViewModel` implements no `apply_pipeline_context`, so "Next ▶" walks into
  an empty panel and the user re-picks the same file by hand. RF-559. And nothing
  downstream consumes the correction: `estimate_drift`/`correct_drift` are
  referenced only by this plugin and by the ICS reader (which re-measures the
  drift itself), so the numbered steps read the uncorrected source — contradicting
  the panel's own description ("the steps below still see real photons"), its
  help text and guide 43 ("Correct the drift first, then walk the pipeline with
  **Next ▶**"). RF-560.
- **The documented headless command does not exist.** Guide 43 gives
  `img-drift movie.tif …`; no such console script is installed. `csc img-drift …`
  is the working form. RF-561. (Same shape as RF-456 for `psf-determination`.)
- **Closing Image Tools while it pre-computes raises from a worker thread.**
  `RuntimeError: wrapped C/C++ object of type _PipelineSignals has been deleted`,
  reproduced by closing the hub shortly after picking a source. RF-562.
- **A single-frame photon stream is a real case, not a corner case.** Both
  `Leica_SP5.ptu` and `Leica_SP8.ptu` reconstruct to one frame with a nonsensical
  geometry (7921 × 256 and 14 × 512) and the loader says so only on stderr
  (`WARNING: no complete frames; salvaging 1 frame(s) …`). The drift tool then
  rejects them, correctly but invisibly (see RF-554).
- **The exported stack is float32.** A 4.4 MB uint16 movie comes back as a
  36 MB float32 TIFF although the correction only ever rolls whole pixels — even
  with sub-pixel refinement on, `apply_drift` rounds.
- **Negative zero everywhere.** The shift table shows `-0.00` for most rows and
  the CLI prints `dy=-0.00`; frames with no measured displacement look like they
  moved a little in the wrong direction.

## UX / UI suggestions

- **Never let a rejected file destroy a good result.** Validate first, keep the
  previous measurement (and the previous file name) when the new file cannot be
  used, and put the explanation where the user is looking — the status bar plus a
  visible field. The view model already has the right sentence; the view simply
  never asks for it on the failure path.
- **Show the status permanently, not just for eight seconds.** A one-line
  read-only status/info section at the top of *Settings* (file, frames,
  channels, geometry, last result) would make every silent path above visible,
  and would remove the "did my drop register?" question entirely.
- **Disable what cannot be done.** Grey out ▶ Measure with no file, and both
  exports with no result — or say why when they are pressed.
- **Make the result know what produced it.** Changing *Apply by*, *Reference*,
  *Smoothing* or *Sub-pixel* should mark the shown result stale (a "re-measure"
  hint, or simply re-run — it takes ~1 s), and *Export stack* should refuse to
  write a mode the user has not seen.
- **Lock the two projections together.** Equal split, one shared intensity
  window (levels from the Before image, applied to both) and linked
  zoom/pan — the panels exist to be compared. A single number under them
  (e.g. the ratio of projection variances, or the FWHM of a picked spot before
  and after) would turn the "is it sharper?" judgement into an answer.
- **Join the pipeline.** Accept the hub's source like every other panel, and let
  the correction flow on: for a photon stream the corrected `CLSMImage` is
  exactly what steps 1–6 want, and for a TIFF stack the corrected array is. If
  that is not intended, then say so in the panel description and in guide 43,
  and point the user at *Export stack* → reload instead.
- **Suggest the ROI.** The estimator is markedly better on a bright, structured
  patch, the core already accepts `roi=`, and the CLI exposes `--roi` — but the
  GUI has no way to draw one, though ChiSurf has a shared region editor.
- **Write the corrected stack in the source dtype** (and compressed): the
  correction is a whole-pixel roll, so float32 buys nothing and costs 8×.
- **Print `0.00`, not `-0.00`.** Add zero before formatting.
- **Say what "below one pixel" means for the workflow.** The status line
  ("Max drift below one pixel — correction changes nothing over 40 frames")
  reads awkwardly and buries the actionable part; "no correction needed
  (max 0.4 px over 40 frames)" says it in the order the user thinks it.
- **Give an all-zero trace a sane axis.** With no drift the plot auto-scales to
  ±500 ×10⁻³ px, which looks like a measurement; a fixed ±1 px range would read
  as "flat".

## Bugs filed

- RF-554 — a rejected drop silently discards the current measurement and leaves
  the whole window showing the previous file's results.
- RF-555 — a failed measurement reports "Drift measurement failed" without the
  reason the model already holds.
- RF-556 — ▶ Measure and the two 💾 Export actions are silent no-ops when their
  precondition is unmet.
- RF-557 — "Apply by" does not invalidate the shown result, and Export stack
  writes the current mode against the stored shifts.
- RF-558 — the Before/After projections are drawn at different sizes and with
  independently auto-scaled contrast.
- RF-559 — the Drift panel never receives the Image Tools pipeline source.
- RF-560 — the measured correction is not consumed by the numbered pipeline
  steps, contrary to the panel description, the help and guide 43.
- RF-561 — guide 43 documents an `img-drift` console script that is not
  installed.
- RF-562 — closing Image Tools during its background pre-compute raises
  `RuntimeError` from the worker thread.
