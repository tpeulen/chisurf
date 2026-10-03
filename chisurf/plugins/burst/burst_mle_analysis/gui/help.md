# Burst lifetime by maximum likelihood (MLE)

A single-molecule burst holds a few hundred photons, so its micro-time decay is sparse. Least squares is wrong at
those counts; the burst-MLE tool fits **one lifetime (and anisotropy) per burst and detector** by Poisson maximum
likelihood, with the instrument response (IRF) and the background held fixed.

Press **Guide** for the walk-through.

## What the windows show

Everything in the windows is read from the wizard that did the work. With no fit they say so; nothing is drawn as a
placeholder.

* **Burst MLE** tab: **Add files** / **Add folder** (or drop .bur files), **Auto IRF/background**, **Refit**, **Fit bursts**,
  **Stop**, **Save results** and **Save/Load settings**; below them the burst-file table, the detector and fit window,
  the IRF settings and the editable *Fit parameters* table (start value, fixed flag, fitted value). A change refits the
  current decay. **Detector setup** is the shared detector editor.
* **Decay and IRF fit**: the micro-time decay of the current file (data), the fitted model, the IRF and the
  background, VV window followed by VH window, on a log axis. IRF and background are scaled to the area of the data for
  display only; their fit weight is the scatter parameter.
* **Burst lifetime distribution**: histogram of the fitted per-burst lifetimes. Drag the box to count the bursts in a
  lifetime gate.
* **Fitted lifetimes**: in the segment-level analysis (split by H2MM state) the pooled lifetime of each state.

## The model

The default model (`fit23`, Maus 2001) fits the lifetime $\tau$, the scatter fraction $\gamma$, the fundamental
anisotropy $r_0$ and the rotational correlation time $\rho$ to the parallel and perpendicular decays together. The
quantity minimised is the likelihood statistic $2I^*$; it is about one per degree of freedom for a good fit. The model
curve is the exponential decay convolved with the IRF, plus the scaled background and the scattered light.

* The **IRF** and **background** belong to the setup, not to a burst: they are taken from measured files or estimated
  from the photons between bursts (Auto IRF/background in the wizard).
* The **fit window** is given in micro-time bins after binning. Leave out the empty bins before the prompt and the
  noisy tail.
* A fit whose $\gamma$ ran to its bound is marked as diverged; the displayed model is then clipped and the status line
  says so. Fix $\gamma$ or use a measured IRF.

## Splitting by H2MM state

A burst that changes state has no single lifetime. With **split by H2MM state** every burst is also fitted once per
Viterbi state, and the pooled decay of each state gives the state's lifetime. This needs the segmentation from the
H2MM step in the same analysis folder.

## Further reading

* [Fluorescence lifetime from photon bursts](docs/guides/21_lifetime_from_bursts.md)
* [TCSPC: fluorescence-lifetime fitting](docs/concepts/tcspc_lifetime.md)
