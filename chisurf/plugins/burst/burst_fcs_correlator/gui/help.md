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

- **▶ Run FCS**: Executes multi-channel multi-tau correlation across all selected bursts and channel pairs.
- **Region Gating**: Drag the interactive bounding box on the correlation curve to constrain the fitting window.
