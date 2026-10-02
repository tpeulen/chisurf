# Burst-wise FCS Correlator

The **Burst-wise FCS Correlator** computes multi-tau fluorescence correlation spectroscopy (FCS) curves directly from segmented single-molecule bursts across selected detector channel pairs.

---

## Overview

Unlike continuous FCS which computes autocorrelations across an entire photon stream, Burst-wise FCS isolates photons belonging to individual bursts (optionally with microsecond time padding), preventing baseline dilution and long-tail artifacts from inter-burst solvent delays.

---

## Correlator Parameters

- **FCS bins (B)**: Number of linear correlation bins per cascade tier (default: 3).
- **Cascades**: Total cascade levels used in the multi-tau correlator (default: 20).
- **Padding (ms)**: Additional photon stream duration before and after each burst included in the correlation window.
- **Fine grid**: Enable high-resolution micro-time correlation for resolving ultra-fast photophysical dynamics (antibunching/triplet).

---

## Fitting Modes

1. **None**: Display computed raw correlation curves $G(\tau)$ without analytical fitting.
2. **Simple**: Fit single-species 3D Brownian diffusion with triplet dynamics:
   $$G(\tau) = G_0 \left(1 + \frac{\tau}{\tau_D}\right)^{-1} \left(1 + \frac{\tau}{S^2 \tau_D}\right)^{-1/2}$$
3. **MaxEnt**: Non-parametric Maximum Entropy inversion yielding a continuous diffusion-time distribution $P(\tau_D)$.

---

## Actions

- **Run FCS** / **Stop**: correlates every ticked burst file with every ticked channel pair; Stop cancels between files and keeps the previous results.
- **Example**: writes a small seeded demonstration photon stream and burst table and adds them, so the guide can be walked without data.
- **Files... / Folder... / Database...**: add BUR/BST burst tables, an analysis folder or an MMFDB dataset; files and folders can also be dropped on the window. **All**, **None**, **Remove** and **Clear** manage the list.
- **Channel pairs**: a table of pairs (routing channels A and B, micro-time gates); equal sides give an auto-correlation. **Pairs of the setup** (Detector setup tab) builds them from a detector setup.
- **Curves**: every burst and pair with its diffusion time; filter by file or pair name and select a row to plot it. **Export curves...** writes JSON.
- **Fit window**: drag the two vertical lines on the correlation plot (or type **t_min** and **t_max**) to constrain the fit; the wheel zooms a plot.
- **Settings files**: **Load settings...** and **Save settings...** read and write the correlator and fit settings as JSON.
