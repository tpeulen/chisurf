# Burst lifetime by maximum likelihood (MLE)

A single-molecule burst holds a few hundred photons, so its micro-time decay is sparse. Least squares is wrong at
those counts; the burst-MLE tool fits **one lifetime (and anisotropy) per burst and detector** by Poisson maximum
likelihood, with the instrument response (IRF) and the background held fixed.

Press **Guide** for the walk-through. **Demo** loads 16 generated bursts of 1000 photons each with a known input lifetime of 2 ns and a 32 ps clock into `demos/burst_mle_analysis` under the ChiSurf settings folder, with a parameter sidecar. It replaces working inputs; press Auto IRF/background and Fit bursts yourself. Fitted estimates fluctuate.

## What the windows show

Everything in the windows is read from the fit that the engine computed. With no fit they say so; nothing is drawn as a
placeholder.

* **Burst MLE** tab: the **Input** section lists the burst runs of the measurement containers in the Datasets
  workspace (drop a measurement on the ChiSurf window and run a burst search; *Open in…* or dragging rows onto this
  window does the same as **Use selected**), then **Clear**, **Auto IRF/background**, **Refit**, **Fit bursts**,
  **Stop**, **Save results** and **Save/Load settings**; below them the burst-file table, the detector and fit window,
  the IRF settings and the editable *Fit parameters* table (start value, fixed flag, fitted value). A change refits the
  current decay. Its last three rows are the detector's time shifts, in Simple mode too: **IRF shift VV** and
  **IRF shift VH** (the IRF against the VV and VH data, bins) and **Shift VV/VH** (the VH decay against the VV decay,
  whole bins). They start at the calibration on the reference dye (hover a row: from which dye, its χ²ᵣ, or "set by
  hand"), fixed; unfixed, the fit refines them within half a bin (one bin). A start you type replaces the calibration
  until **Reset shifts**. **Detector setup** is the shared detector editor. Every finished **Fit bursts** writes its lifetimes
  into the burst run they were fitted from (`<run>/mle G|G`, one row per burst, linked to the run's burst table): ndX
  opens that run with `Tau (G|G)`, `Tau (R|G)`, `Tau (R|R)` beside the burst columns. **Save results** writes them
  again.
* **IRF** tab: one choice, **IRF from** -- **Auto** (the reference dye of Data Selection, else the IRF
  measurement, else the photons outside the bursts, else an estimate from the data), or one of them; a
  source whose measurement is missing is greyed. One line says what the IRF is (details in its tooltip),
  then the IRF and **IRF tool**: it opens the IRF Estimation tool on the same data, and what you estimate
  there comes back here ("IRF tool (tuned)") and is fitted. The IRF's settings are the tool's. With a
  reference dye the IRF's time shift (VV, VH) is calibrated before the fit against it, its lifetime
  fixed to the dye database's; a single-molecule dye measurement is preferred ("shift calibrated").
  The red detectors under green excitation (`R|G`) are `R|R`'s detectors: they take `R|R`'s calibration
  on the red dye (G, IRF shape, shifts), the IRF placed at the green pulse by the setup's PIE windows.
  Then the dye itself is fitted with the IRF and the burst model (one amplitude, the setup's G, l1, l2,
  its rotation): the line shows that **reference fit's χ²ᵣ** -- about 1 when the IRF, G and the rotation
  describe the reference -- and ⚠ when the dye asks for another G than the setup has (apply Data
  Selection's G). The IRF tool's **Reference fit** view draws it with its residuals.
* **IRF/BG files** tab (outside Burst Analysis only; in the pipeline the files are Data Selection's): the **Measured IRF** and **Measured background** sections take photon streams from the
  workspace (measured patterns, per detector or *one for all*), **Save VV/VHs**. **Opt** (in the *Burst MLE* tab) searches the
  shifts, IRF window and thresholds for the lowest 2I*; **Save fit** stores a detector's fit settings on the selected
  detector setup. The fit model **Tail fit (multi-exp)** previews a multi-exponential tail fit (no IRF; not used by
  **Fit bursts**).
* **Decay and IRF fit**: the micro-time decay of the current file (data), the fitted model, the IRF and the
  background, VV window followed by VH window, on a log axis. IRF and background are scaled to the area of the data for
  display only; their fit weight is the scatter parameter. Under it, on the same x axis, the **weighted residuals**
  (data − model) / √model of each fit window (√data where the model is zero) around a zero line, and in its title
  χ²ᵣ = Σ w.res.² / (bins − free parameters): about 1 and no structure for a good fit.
* **Burst lifetime distribution**: histogram of the fitted per-burst lifetimes. Drag the box to count the bursts in a
  lifetime gate.
* **Fitted lifetimes**: in the segment-level analysis (split by H2MM state) the pooled lifetime of each state.

## The model

The default model (`fit23`, Maus 2001) fits the lifetime $\tau$, the scatter fraction $\gamma$, the fundamental
anisotropy $r_0$ and the rotational correlation time $\rho$ to the parallel and perpendicular decays together. The
quantity minimised is the likelihood statistic $2I^*$; it is about one per degree of freedom for a good fit. The model
curve is the exponential decay convolved with the IRF, plus the scaled background and the scattered light.

* The **IRF** and **background** belong to the setup, not to a burst. The background is the **buffer** of Data
  Selection when there is one (its shape and rate); else the **strict background selection** of the measurement --
  not the photons outside the bursts, which hold molecules below the threshold and the bursts' flanks (a decay), but
  only the stretches away from every burst (margins) whose local count rate stays at the background's level -- when
  its histogram is a background's; else a **flat + scatter model** (the flat level before the prompt, a scatter of
  the IRF's shape), never a decay. Its rate times the time in the bursts is what the plot draws; the fit text and
  the detector line say which it is, how much time the strict selection kept and its rate.
* The **fit window** is fitted as a window: the model is normalised over the window's bins, not over the period
  with the bins outside it scored as zeros (which bent every fit).
* The **fit window** is given in micro-time bins after binning. Leave out the empty bins before the prompt and the
  noisy tail.
* A fit whose $\gamma$ ran to its bound is marked as diverged; the displayed model is then clipped and the status line
  says so. Fix $\gamma$ or use a measured IRF.

## Selecting the tttrlib model

**Fit model** selects Fit23, Fit24 or Fit25 for both preview and batch. Double-click a parameter's **Start** to edit it; click **Fixed** to hold a fitted parameter. Each model retains its edits in saved settings.

* **Fit23:** tau, gamma, r0 and rho; one lifetime with polarization.
* **Fit24:** tau1, gamma, tau2, A2 and offset; a two-lifetime mixture. A2 reports the effective second-component amplitude.
* **Fit25:** four fixed candidate lifetimes and gamma. Candidate values are editable but remain fixed inputs; the winner is reported as selected_index (0-based). Its r0 is supplied by the provider.

Fit26 needs two reference patterns and fit_nexp needs array inputs, so neither is offered here. The tail fitter is preview-only. A completed batch retains its original model and output schema even if you change the selector before saving.

The saved detector definition supplies channel LUTs and shifts to the canonical reader. Header timing is used unless Override timing is explicitly selected; setup micro-time values are in ps and period values in ns. Binning is applied once.

## Splitting by H2MM state

A burst that changes state has no single lifetime. With **split by H2MM state** every burst is also fitted once per
Viterbi state, and the pooled decay of each state gives the state's lifetime. This needs the segmentation from the
H2MM step in the same analysis folder.

## Further reading

* [Fluorescence lifetime from photon bursts](docs/guides/21_lifetime_from_bursts.md)
* [TCSPC: fluorescence-lifetime fitting](docs/concepts/tcspc_lifetime.md)
