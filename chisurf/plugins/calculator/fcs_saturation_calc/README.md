# FCS Saturation & Volume Expansion Calculator

## Overview

In Fluorescence Correlation Spectroscopy (FCS), high excitation laser power flattens the local fluorescence emission profile near the focal center ($r=0$) because dye molecules saturate in the excited singlet state ($S_1$) or get trapped in long-lived dark states (triplet state $T_1$, cis/trans photo-isomerization, blinks).

This non-Gaussian perturbation expands the effective observation volume $V_{\text{eff}}$, causing:
1. **Apparent Concentration Overestimation**: $G(0)$ decreases, leading to overestimation of molecule count $N$.
2. **Diffusion Time Broadening**: Apparent diffusion time $\tau_D$ shifts to longer lag times as the emission volume expands.
3. **Photochemical Relaxation Dynamics**: Intersystem crossing and dark state population create characteristic short-time bunching decays in $G(\tau)$.

This tool numerically integrates the steady-state master equation over a 3D confocal volume for arbitrary $N$-state photophysical kinetics schemes ($N=2 \dots 6$).

---

## Physical Formulation & Laser Power Equations

### 1. Total Laser Power & Photon Flux
The excitation light is specified by the total average laser power $P_{\text{total}}$ (mW) measured at the objective back aperture:

$$P_{\text{total}} = \iint I(x, y) \, dx \, dy \quad [\text{mW}]$$

The integrated photon flux $\Phi_{\text{total}}$ ($\text{photons/s}$) is:

$$\Phi_{\text{total}} = \frac{P_{\text{total}}}{h \nu} = \frac{P_{\text{total}} \cdot \lambda}{h c}$$

### 2. Integrated & Peak Focal Excitation Rates
The integrated excitation rate $k_{\text{exc, int}}$ ($\text{m}^2/\text{s}$) across the focal plane is:

$$k_{\text{exc, int}} = \sigma_{\text{abs}} \cdot \Phi_{\text{total}} = \frac{\ln(10) \cdot 1000 \cdot \varepsilon}{N_A} \cdot \frac{P_{\text{total}} \lambda}{h c}$$

For a 3D Gaussian focal intensity profile $I(r, z) = I(0,0) \exp\left(-\frac{2r^2}{w_r^2} - \frac{2z^2}{w_z^2}\right)$, the peak focal excitation rate $k_{\text{exc}}(0,0)$ ($\text{s}^{-1}$) at the origin is:

$$k_{\text{exc}}(0,0) = \frac{2 \, k_{\text{exc, int}}}{\pi w_r^2} = \frac{2 \sigma_{\text{abs}} P_{\text{total}}}{\pi w_r^2 h \nu}$$

### 3. Voxel Steady-State Solution
At each spatial voxel $(r, z)$, the local excitation rate is $k_{\text{exc}}(r, z) = k_{\text{exc}}(0,0) \exp\left(-\frac{2r^2}{w_r^2} - \frac{2z^2}{w_z^2}\right)$.

The $N$-state population vector $\vec{P}(r, z) = [P_1, P_2, \dots, P_N]^T$ is obtained by solving:

$$\mathbf{K}(r, z) \cdot \vec{P}(r, z) = 0 \quad \text{subject to} \quad \sum_{i=1}^N P_i(r, z) = 1$$

where $\mathbf{K}(r, z) = \mathbf{K}_{\text{dark}} + k_{\text{exc}}(r, z) \mathbf{K}_{\text{exc}}$.

The local emission profile is $S(r, z) = \sum_{i=1}^N Q_i P_i(r, z)$, where $Q_i$ is the relative quantum yield/brightness of state $i$.

---

## Key GUI Features & Interactive Controls

### 1. Interactive Photophysical State Scheme (`StateSchemeWidget`)
- **Interactive Node Dragging**: Drag state nodes ($S_0, S_1, T_1, P$) to arrange custom Jablonski layouts.
- **Reshape Transition Arcs**: Click and drag directed rate arrows or rate badges to custom-curve transition arcs.
- **Rate Value Spinbox**: Double-click any transition rate badge to edit its rate constant in real time.
- **Global Canvas Panning**: Click-drag the dark background canvas to pan the entire diagram across the field.
- **Import & Export Schemes**: Click **📂 Load** or **💾 Save** at the top of the State Scheme panel to export/import photophysical schemes in `.json` format.

### 2. Normalization Mode
Toggle **Normalize G(τ) to 1.0** to scale $G(\tau)/G(0) = 1.0$, allowing direct visual comparison of shape broadening, diffusion time shifts $\tau_D$, and bunching dynamics between unperturbed Gaussian and saturated curves.

### 3. High-Resolution Lag Time Grid
Computes 300 log-spaced lag time points from $100\text{ ns}$ to $10\text{ s}$, accurately resolving fast triplet/isomer bunching and slow diffusion tails.

### 4. Automatic Session Persistence
All parameters, rate matrices, focal volume geometry ($w_r = 200\text{ nm}, w_z = 1000\text{ nm}, D = 400\,\mu\text{m}^2/\text{s}$), toggle states, and custom rate matrix units are saved automatically to `~/.chisurf/plugins/fcs_saturation_calc/settings.json` upon closing or updating.

---

## Interactive Step-by-Step Walkthrough

Click **Guide** in the top plugin toolbar to launch the step-by-step interactive walkthrough detailing laser power setup, photophysical state schemes, rate matrix editing, normalization, and volume expansion profiles.
