---
type: Guide
title: IRF estimation
description: The one IRF extraction tool -- from a fluorescence decay (blind), a reference dye, a scatter or the photons outside the bursts; Burst MLE and Burst IRF & Background take their IRF from it.
tags: [guides, tcspc, decay]
---

# IRF estimation

:::{admonition} Theory
:class: seealso
See {ref}`concept-tcspc-lifetime` for the IRF and the reconvolution model it feeds.
:::

## Overview

IRF estimation infers the instrument response function (IRF) blindly from a
measured fluorescence decay, without a separate IRF measurement: a truncated
exponential is fitted to the decay tail, and the IRF is recovered from the decay
by Richardson–Lucy deconvolution with that exponential.

Two entry points:

- the **IRF Estimation** tool (**Spectroscopy → Decay → IRF Estimation**,
  `chisurf/plugins/fluorescence_decay/irf_estimator/`);
- the `IRFEstimator` class (`chisurf.core.fluorescence.tcspc`) for scripts.

### Reference

This implementation is based on the algorithm described in:

**Adrián Gómez-Sánchez et al., "Blind instrument response function identification from fluorescence decays", _Biophysical Reports_, 2024.**  
DOI: [10.1016/j.bpr.2024.100155](https://doi.org/10.1016/j.bpr.2024.100155)

The core is `chisurf/core/fluorescence/tcspc/irf_estimation.py`. It handles
several detector channels at once (they share one decay rate). `run()` computes
the whole estimate in tttrlib's compiled engine (`tttrlib.blind_irf_estimate`);
the step-by-step methods below run the same pipeline in Python and keep its
intermediates.

## Sources: one extraction for every tool

The tool extracts an IRF from what it is given. **Source** in the parameters
says what the loaded data is; the extraction is the module
`chisurf/plugins/fluorescence_decay/irf_estimator/core/extraction.py`, which
Burst MLE, Burst IRF & Background and the MFD burst fit call too -- no tool
extracts an IRF of its own ([theory](../concepts/irf_extraction.md)):

| Source | What the data is | How the IRF is taken |
|---|---|---|
| Blind | a fluorescence decay | truncated exponential + Richardson–Lucy (below) |
| Reference dye | a dye of one known lifetime (Rh110, Alexa647) | its polarised exponential deconvolved (Richardson–Lucy); τ from the tail of VV + 2VH, ρ from VV and VH |
| Scatter | water, Ludox | the prompt above the floor (and a buffer) |
| Non-burst | the photons outside the bursts | a (skewed) Gaussian fitted to the prompt's rising edge |

The window opens **Simple**: the source, **Estimate IRF**, the plot and the
results are all a typical run needs. **Advanced** (top right of the
parameters) shows every setting of the extraction. When Burst MLE opened the
window (**IRF tool**), every estimate you make here goes back to it for that
detector and is fitted there ("IRF tool (tuned)"); the estimate made on
opening is the one Burst MLE already has and is not sent back. An automatic
choice takes a reference dye first, then a scatter (`AUTO_ORDER`).

Burst MLE also calibrates the IRF's time shift against the reference dye
(`calibrate_shifts`, the dye's lifetime fixed to the dye database's); opened
from Burst MLE, **Advanced** shows **Shift VV / VH** and a value you change there
goes back with the IRF and replaces the calibrated one.

```{figure} figures/irf_estimation_advanced_from_mle.png
:name: fig-irf-estimation-advanced-from-mle
:width: 100%

**Advanced**, opened from Burst MLE: the dye's lifetime and rotation (0: from
the data) and the time shifts Burst MLE calibrated against the dye.
```

**VV | VH halves** says the data holds two polarisations one after the other
(the rotation of a reference dye is read from them). For a reference dye,
**Lifetime** 0 fits τ to the tail (the **Listed** one when that fails), **ρ** 0
reads the rotation from the data. Burst MLE's **IRF tool** button opens this
window with what its current detector's IRF was extracted from, and the
estimate starts at once: the IRF it shows is the one Burst MLE fits with.

```{figure} figures/irf_estimation_reference_from_mle.png
:name: fig-irf-estimation-reference-from-mle
:width: 100%

Opened from Burst MLE (DNA13bp_3, G|G): the Rh110_thick_1.ptu reference, VV
then VH, and the IRF extracted from each (green, scaled to its half's peak):
τ 4.02 ns from the tail, ρ 0.17 ns from the data -- the IRF Burst MLE fits with.
```

Script use (the arrays are counts on the same bins):

```python
from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import (
    best_irf, irf_from_reference, irf_from_scatter,
)

dye = irf_from_reference(vv, vh, dt_ns=0.08, listed_tau_ns=4.0, name="Rh110.ptu", dye="Rh110")
water = irf_from_scatter([vv_h2o, vh_h2o], buffer=[vv_buf, vh_buf])
irf = best_irf([dye, water], min_counts=500)   # the reference dye first (AUTO_ORDER)
print(irf.text, irf.info)                      # irf.irf: VV | VH, each summing to one
```

**Measured** against a known IRF (simulated Rh110, 80 ps bins): the exact
difference IRF[i] = D[i] − exp(−Δt/τ)·D[i−1] used before was 0.16 (TV) off the
IRF and moved a 2.5 ns sample to 2.63 ns; the deconvolution is 0.03 off and
gives 2.50 ns. Details in the [concept](../concepts/irf_extraction.md).

## Algorithm Pipeline

1. **Decay Boundary Detection**: Uses Savitzky-Golay filtering to identify decay start (t0) and end (t1)
2. **Exponential Fitting**: Fits truncated exponential model to decay region
3. **Kernel Generation**: Creates normalized deconvolution kernel from fitted parameters
4. **Richardson-Lucy Deconvolution**: Iteratively deconvolves IRF from measured data
5. **Regularization**: Applies median filtering for noise reduction

```{figure} figures/irf_estimator.png
:name: fig-irf-estimator
:width: 100%

The **IRF Estimator** plugin on a simulated decay whose answer is known — a
single exponential at $\tau = 4.0$ ns reconvolved with a Gaussian instrument
response of 1.18 ns FWHM centred at 5.0 ns. The recovered IRF (**green**) peaks
at 5 ns with about the right width; the ragged tail beyond it is
Richardson-Lucy ringing at the one-count level, not instrument response. The
orange **forward model** is the check that matters: it is the estimated IRF
reconvolved with the fitted exponential, so where it lies on the measured decay
(**blue**) the estimate reproduces the data — across the whole 50 ns here. The
fitted offset comes back at 10 counts against a true 8.
```

### In the window

```{figure} figures/irf_estimator_native_window.png
:name: fig-irf-estimator-native-window
:width: 100%

The native estimator at its declared first-use size on the independent
Gaussian/exponential reference. Peak recovery does not imply an unbiased
lifetime: the displayed estimate is about 3.62 ns for a 4 ns input.
```

The standalone native estimator declares **1100 × 720** pixels on first use.
Its parameter, plot and result docks remain available after resizing; scroll the
parameters when the host is smaller than the declaration. Saved native
preferences retain geometry and docks, while a reopened analysis starts empty:
load the decay and estimate again. Check **Time/Channel (ns)** when the input has
no time metadata; the fallback is 1 ns per channel, not a measured calibration.

The estimated IRF peak and the fitted lifetime are distinct checks. In the
known 4 ns exponential/Gaussian reference, the peak is near 5.11 ns but the blind
fit returns about 3.62 ns. Inspect the reconvolved forward curve and residual
agreement as well as the recovered peak; an estimated IRF alone does not prove
that a measured decay fits the assumed exponential model.

1. **📂 Load Decay** reads a VV/VH `.dat` file (the VV channel is used; dropping
   the file on the window does the same). **📊 Load from Dataset** lists the
   decay curves already open in ChiSurf. Loading sets **Manual Background** to
   the median of the last 10 % of channels.
2. Check **Time/Channel (ns)**. It comes from the file; a file without a time
   axis gives 1 ns per channel. The native window lets you correct it, which
   rescales the lifetime and rate without re-estimating.
3. **🔮 Estimate IRF** runs the tail fit and the Richardson–Lucy deconvolution
   in the background. **📍 Use Range Selection** limits the estimate to the
   green region (drag it in the plot, or type the first and last channel).
   **🔄 Auto-Update IRF** re-estimates with 50 iterations after a change, once
   an IRF exists.
4. **💾 Save IRF** writes identical VV and VH channels. **🚀 Transfer to
   ChiSurf** registers the IRF as a TCSPC VV/VH dataset (g = 1, 10 MHz).

The scaled IRF is drawn only where it is at least one count, so the log axis
stays on the data. **Guide** walks through the same steps.

## Usage

### Basic Usage

```python
from chisurf.core.fluorescence.tcspc import IRFEstimator
import numpy as np

# Load or create your decay data
time = np.linspace(0, 50, 500)
dt = time[1] - time[0]
decay_data = your_measured_decay  # shape: (n_time, n_channels)

# Estimate IRF
estimator = IRFEstimator(decay_data, dt=dt)
irf = estimator.run()  # 500 RL iterations by default
```

`run()` returns the IRF only; `estimator.params` (lifetime, amplitude, offset)
is filled by the step-by-step pipeline below.

### Step-by-Step Usage

```python
from chisurf.core.fluorescence.tcspc import IRFEstimator

# Create estimator
estimator = IRFEstimator(data, dt=0.1)

# Step 1: Find decay boundaries
estimator.find_t0_t1(window_length=11, polyorder=3)

# Step 2: Fit exponential decay
estimator.fit_exponential(method='L-BFGS-B', max_iter=1000)

# Step 3: Generate fitted curves
estimator.generate_data_fit()

# Step 4: Generate deconvolution kernel
estimator.generate_kernel()

# Step 5: Perform Richardson-Lucy deconvolution
estimator.richardson_lucy_deconvolution(iterations=30, regularization=3)

# Access IRF and the fitted exponential
irf = estimator.irf
print(f"Estimated lifetime: {1.0 / estimator.params['k']:.2f} ns")
print(f"Background offset: {estimator.params['C'][0]:.2f}")
```

### Multi-Channel Data

```python
# Data shape: (n_time, n_channels)
multi_channel_data = np.column_stack([decay1, decay2, decay3])

estimator = IRFEstimator(multi_channel_data, dt=0.1)
irf = estimator.run()

# IRF will have same shape as input: (n_time, n_channels)
```

### Visualization

The two diagnostic plots show the step pipeline's intermediates (the boundary
markers, the fitted exponential, the kernel), so they follow the step-by-step
calls above. `run()` hands the whole estimate to the photon library's engine in
one call and keeps none of them.

```python
estimator.find_t0_t1(window_length=11, polyorder=3)
estimator.fit_exponential()
estimator.generate_data_fit()
estimator.generate_kernel()
estimator.richardson_lucy_deconvolution(iterations=200, regularization=3)

fig1, ax1 = estimator.plot_raw_and_fit()      # raw data, fit, fitting interval
fig2, ax2 = estimator.plot_forward_model()    # IRF ⊗ exp vs measured data
fig1.save("raw_and_fit.png")                  # in a notebook the figure shows inline
```

## API Reference

### IRFEstimator Class

#### Constructor

```python
IRFEstimator(data, dt=1.0)
```

**Parameters:**
- `data` (np.ndarray): 1D or 2D array of fluorescence decay data
  - 1D: shape (n_time,) - single channel
  - 2D: shape (n_time, n_channels) - multiple channels
- `dt` (float): Time step between samples (default: 1.0)

#### Methods

##### `find_t0_t1(window_length=11, polyorder=3, persistence=5, threshold=0.05)`

Estimate decay start (t0) and end (t1) indices using Savitzky-Golay filtering.

**Parameters:**
- `window_length` (int): SG filter window length (must be odd)
- `polyorder` (int): Polynomial order for SG filter
- `persistence` (int): Number of consecutive positive derivative samples for t1
- `threshold` (float): Minimum amplitude threshold for t1 (fraction of range)

##### `fit_exponential(offset=0, method='L-BFGS-B', max_iter=1000)`

Fit truncated exponential curves to decay data.

**Parameters:**
- `offset` (int): Shift applied to t0 when selecting fitting data
- `method` (str): Scipy optimization method
- `max_iter` (int): Maximum optimization iterations

##### `generate_data_fit()`

Generate fitted exponential curves using estimated parameters.

##### `generate_kernel()`

Build normalized deconvolution kernel from fitted exponential.

##### `richardson_lucy_deconvolution(iterations=30, eps=1e-4, regularization=3)`

Perform Richardson-Lucy deconvolution.

**Parameters:**
- `iterations` (int): Number of RL iterations (default: 30 when the step is called
  directly; `run()` passes 500 via its own `rl_iterations`)
- `eps` (float): Small value to avoid division by zero
- `regularization` (int): Median filter window size (default: 3, set to 1 to disable)

##### `run(window_length=11, polyorder=3, persistence=5, threshold=0.05, fit_method='L-BFGS-B', fit_max_iter=1000, rl_iterations=500, regularization=3)`

Execute the full IRF estimation pipeline (boundaries → exponential fit → kernel →
deconvolution) in tttrlib's engine (`tttrlib.blind_irf_estimate`).

**Parameters:** the engine takes `window_length`, `polyorder`, `rl_iterations`
and `regularization`. `persistence`, `threshold`, `fit_method` and
`fit_max_iter` are accepted but not passed on — the engine uses its own
boundary and fit settings. Note the renames against the step methods:
`rl_iterations` (not `iterations`).

**Returns:** np.ndarray - Estimated IRF (shape: [n_time, n_channels]), also
stored as `irf`. `params`, `data_fit` and `kernel` stay unset.

##### `plot_raw_and_fit(ax=None)`

Plot raw data and fitted exponential curves, one panel per channel on shared
axes. Needs `generate_data_fit()` first.

**Returns:** `(fig, ax)` -- an `emtk.figure.Figure` (`fig.save(path)` writes a
PNG; no GUI toolkit needed) and its panels.

##### `plot_forward_model(ax=None)`

Plot forward model (IRF ⊗ exponential) vs measured data. Needs
`richardson_lucy_deconvolution()` first.

**Returns:** `(fig, ax)`, as above.

#### Attributes

- `data` (np.ndarray): Input decay data
- `time` (np.ndarray): Time vector
- `dt` (float): Time step
- `num_samples` (int): Number of time points
- `num_channels` (int): Number of channels
- `t0` (np.ndarray): Per-channel decay start indices
- `t1` (np.ndarray): Per-channel decay end indices
- `params` (dict): Fitted parameters {"A", "C", "k"}
  - `A`: Amplitude (per channel)
  - `C`: Constant offset (per channel)
  - `k`: Decay rate (shared across channels)
- `data_fit` (np.ndarray): Fitted exponential curves
- `kernel` (np.ndarray): Deconvolution kernel
- `irf` (np.ndarray): Estimated IRF


## Utility Functions

### `generate_truncated_exponential(t, params)`

Generate truncated exponential curve.

**Parameters:**
- `t` (np.ndarray): Time points
- `params` (dict): {"A", "k", "C", "t0"}

**Returns:** np.ndarray - Model values

### `estimate_lifetime(x, y, t0, t1)`

Estimate lifetime from centroid of decay region.

**Parameters:**
- `x` (np.ndarray): Time points
- `y` (np.ndarray): Signal values
- `t0` (int): Start index
- `t1` (int): End index

**Returns:** float - Estimated lifetime

### `median_filter_nd(x, window_size=3, axes=None, mode='reflect')`

Apply N-dimensional median filter.

### `pad_array(x, pad_left, pad_right, axis, mode='reflect')`

Pad array along one axis.

### `partial_convolution_fft(signal, kernel, axis=0)`

Perform FFT-based convolution along specified axis.

## Examples

{src}`test/tcspc/test_irf_estimation.py` exercises the basic estimate, the
step-by-step pipeline and multi-channel data. The tool's own controls are
described under [In the window](#in-the-window) above.

## Technical Details

### Richardson-Lucy Algorithm

The Richardson-Lucy algorithm iteratively refines the IRF estimate:

```
x_{n+1} = x_n * [(y / (x_n ⊗ h)) ⊗ h_reversed]
```

where:
- `x_n` is the current IRF estimate
- `y` is the measured data
- `h` is the deconvolution kernel
- `⊗` denotes convolution

### Regularization

Median filtering is applied after each RL iteration to reduce noise amplification:
- Window size 3 (default) provides good balance
- Set to 1 to disable regularization
- Larger windows provide more smoothing but may over-regularize

### Optimization

`fit_exponential` minimizes with `chisurf.core.math.numerics.minimize`:
- Method: L-BFGS-B (bounded optimization)
- Bounds: A > 0, C ≥ 0, k > 0
- Loss: Mean squared error across all channels

## Limitations

1. **Assumes Exponential Decay**: Works best with single or multi-exponential decays
2. **Shared Decay Rate**: All channels share the same decay rate k
3. **Requires Clear Decay**: Needs sufficient signal-to-noise ratio
4. **Needs the decay to reach baseline.** Step 2 fits a *truncated* exponential,
   and over a short window the offset $C$ is degenerate against the exponential
   itself: both can absorb the same counts. Measured on simulated decays with a
   known answer ($\tau = 3.8$ ns), the recovered lifetime and offset are:

   | Measured tail | Recovered $\tau$ | Recovered $C$ (true 8) |
   |---|---|---|
   | 4.3 $\tau$ (true 3.8 ns) | 2.94 ns (−23 %) | 1125 |
   | 8.7 $\tau$ (true 3.8 ns) | 3.19 ns (−16 %) | 30 |
   | 12.5 $\tau$ (true 4.0 ns) | 3.62 ns (−9 %) | 10 |

   Those come from `estimate_irf` — the plugin's own API, with its default
   Savitzky–Golay window of 11 — so they are what this tool gives you. Calling
   `IRFEstimator` directly with *its* defaults recovers 4.00 ns in the last row;
   the difference is the smoothing window, not the tail, and it is worth knowing
   that the two entry points do not agree out of the box.

   The **IRF position** is recovered correctly in every one of those cases —
   it is $\tau$ and $C$ that degrade. So a short window still gives you a
   usable IRF *position*, but do not read the lifetime off it, and treat a
   recovered IRF with a long tail as a symptom of this rather than of the
   instrument. Use the forward-model overlay as the check: if it does not lie
   on the measured decay, the estimate has not converged on the data.

## References

### Primary Reference

{cite}`gomezsanchez2024` — the blind IRF identification algorithm the tool implements.

### Algorithm References

- **Richardson, W. H. (1972).** "Bayesian-Based Iterative Method of Image Restoration." _Journal of the Optical Society of America_, 62(1), 55-59.
- **Lucy, L. B. (1974).** "An iterative technique for the rectification of observed distributions." _The Astronomical Journal_, 79, 745-754.
- **Savitzky, A.; Golay, M. J. E. (1964).** "Smoothing and Differentiation of Data by Simplified Least Squares Procedures." _Analytical Chemistry_, 36(8), 1627-1639.

## Testing

```bash
pytest test/tcspc/test_irf_estimation.py -v
```

## See also

- Concept: {ref}`concept-tcspc-lifetime` — what the IRF is and how reconvolution
  uses it.
- Fitting decays once the IRF is known:
  [lifetime & anisotropy fitting](10_lifetime_anisotropy_fitting.md).
- Measuring the IRF and background from the data instead of inferring it:
  [background rates](15_background_rates.md).
- Micro-time axis quality, which limits any IRF estimate:
  [TAC linearization](37_tttr_microtime_lut.md).
