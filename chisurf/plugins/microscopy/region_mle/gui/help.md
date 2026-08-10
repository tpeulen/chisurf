# Region MLE

Fits a **single fluorescence lifetime per region** by Poisson maximum
likelihood — tttrlib's `Fit23`, the Maus-2001 2I\* estimator — on the parallel
and perpendicular decays together.

It does not segment. The regions come from the **Spot Finder**, from a saved
label image, or from regions handed over in memory, and the fit answers for
exactly those and no others.

## Why it does not find its own regions

Because a fit that does cannot be shown what it is about to fit. This tool used
to segment inside the same function that fitted, so the preview a user tuned was
not what got fitted — a second segmentation that agreed only while every setting
reached both paths.

Now the preview and the run resolve the regions through the *same call*. "What
is previewed is what is fitted" is structural rather than a promise two code
paths make separately.

## What a region needs before it can be fitted

- **Two detection channels.** The estimator wants a VV/VH stack: parallel then
  perpendicular, laid end to end. Channels are split even/odd from the detector
  list.
- **An IRF measurement**, on the same optics and detectors, with the same
  micro-time axis. It is what lets the fit deconvolve rather than assume. An
  analytic, noiseless IRF against noisy data hands the fit an advantage no
  measurement provides.
- **Enough photons.** A region below **Min photons** is not fitted and keeps a
  row with NaN parameters. It is never dropped: a missing row silently shifts
  every result after it when tables are merged by position.

## The parameters

`τ` is the lifetime, `γ` the scatter fraction, `r0` and `ρ` the anisotropy.
With a few thousand photons per region the data cannot support four free
parameters — **fix r0 and ρ** for a first look, and free them only when the
photon count justifies it. Freeing everything buys a worse-determined τ, not
more information.

`l1` and `l2` are the objective's polarisation mixing corrections and belong to
the detector setup rather than to the sample; the shared Setup panel supplies
them, along with the G factor.

## Reading the result

The **Decay** tab draws the data, the fitted model, the IRF and the background
on a log axis, with the **weighted residuals** above sharing the time axis, so a
systematic deviation lines up with the channel that caused it. It is the same
panel the burst-wise MLE draws — a region and a burst are the same measurement
under different membership rules.

Four things the panel does deliberately: a **diverged** model is clipped for
display (raw, it takes the log view to 1e6 and hides the data), the IRF and
background are **area**-matched (peak matching lets one hot bin set the scale),
the y-range is pinned to the **data**, and the residual band is the 99th
percentile with a floor so one bad channel cannot flatten the rest.

## Try it without your own data

**🧪 Load demo** simulates a field whose four objects have lifetimes of 1.0,
3.6, 2.2 and 0.6 ns, detects them with the standard workflow and fills this
panel in. Fit it and compare. The long lifetimes come back a few percent low,
and that is real rather than a defect: a 3.6 ns decay is not finished inside the
demo's 8.2 ns excitation period.

## Further reading

- [TCSPC and the fluorescence lifetime](docs/concepts/tcspc_lifetime.md)
- [Region properties](docs/concepts/region_properties.md)
