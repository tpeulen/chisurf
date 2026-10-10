---
type: Guide
title: The G-factor of a polarised setup (VV/VH G-Factor Calculator)
description: Measuring the detection-efficiency ratio G of two polarisation channels by tail matching on a fast-rotating dye, estimating the linked polarisation mixing from a slow protein, and applying the calibration to a batch of decays.
tags: [guides, fret, calibration]
---

# The G-factor of a polarised setup (VV/VH G-Factor Calculator)

**What you get:** the factor $G$ that makes the parallel (VV) and perpendicular (VH) channels of your
instrument comparable, with its standard deviation, an estimate of the linked polarisation mixing
$l_1 = l_2$, a check of the corrected anisotropy $r(t)$, and the steady anisotropy $r_\infty$ of any
number of further decays under the same calibration.

## Theory

Gratings, mirrors and detectors are not polarisation-neutral: the two channels see the same photons with
different efficiency. The ratio is $G = S_\mathrm{VV}/S_\mathrm{VH}$ and it multiplies $I_\mathrm{VH}$ in
$r(t) = (I_\mathrm{VV} - G I_\mathrm{VH})/(I_\mathrm{VV} + 2 G I_\mathrm{VH})$, so an error in $G$ scales
every anisotropy you report. $G$ is measured on a dye that depolarises within the pulse width: in the
tail its anisotropy is zero and $I_\mathrm{VV}/I_\mathrm{VH}$ equals $G$ alone (tail matching). A high
numerical aperture additionally mixes the polarisations geometrically; one steady-state observable
(a slow, long-lived reference with a known Perrin anisotropy) fixes only the single linked value
$l_1 = l_2$, and an estimate outside 0 to 0.5 is shown but not applied. See {ref}`concept-anisotropy`.

The standalone native window starts at **1100 × 720** pixels unless saved
geometry takes precedence. Narrow batch tables keep readable column widths
and scroll horizontally; hover a row for its file path. Native preferences
restore the selected reference files and settings, reload existing files and
recompute their results. The stored window state does not contain decay arrays.

```{figure} figures/gfactor_native_primary_window.png
:width: 100%

Known references: tail matching gives G = 2. The calibrated fast reference has
zero anisotropy; the slow-reference mixing estimate is l1 = l2 = 0.1, and its
corrected anisotropy is 0.304. The example uses a manual 4 ns lifetime rather
than treating the finite-window first moment as the exact input lifetime.
```

## 1. Open the tool and load the fast reference

*Spectroscopy → Decay → VV/VH G-Factor Calculator*. Press **Fast reference...** and choose the
VV/VH file of the fast dye (or drop it on the window). The status line reports $G$ and the results table
lists $G$ raw and its standard deviation.

The controls and plots are one native emtk/AutoForm app. ChiSurf's existing
detector-calibration and lifetime-analysis windows host that same app. Its
**G-factor and mixing** and **Batch anisotropy** tabs share the reference,
background, shift and mixing settings; **Help** explains the controls and
**Guide** walks through them. **Stop** discards a pending calculation, although
an archival already running may finish.

For a desktop with a working display/GPU, launch it independently:

```bash
pixi run -e test python -m chisurf.plugins.vv_vh_g_factor
```

The shared launcher also accepts
`pixi run -e test python -m chisurf.emtk --plugin vv_vh_g_factor --size 1600x1000`.
The calculations below run headlessly; offscreen Qt capture is a separate
rendering path from the native desktop launcher.

```{figure} figures/vv_vh_g_factor_native_reference.png
:name: fig-vv-vh-g-factor
:width: 100%

Synthetic seeded references: fast dye (rho 0.2 ns) and slow protein (rho 16 ns),
with a generated detector ratio of 1.2 and background correction on. The
calculated corrected G is about 1.21871 with SD 0.155055. The yellow lines mark
the tail, the blue ones the background; the plots use TAC bins. These generated
photons demonstrate the workflow, not a measured instrument calibration.
```

## 2. Match the tails

Set the tail with **Tail start** / **Tail stop** (type a bin and press Enter, use the arrows, or drag the
yellow lines in the plot; the mouse wheel zooms). Tick **Background correction** and set the blue region
on a signal-free stretch when the pre-pulse level matters: the table then shows $G$ corrected and the
background of each channel. **VH shift** moves the VH axis by fractional bins; **Flip VV/VH** swaps the
channels of a file written the other way round. **Manual G** replaces the calculated value by one you type.

The **G SD** and **G corrected SD** rows retain the spread of the valid
per-bin ratios in the selected tail. Background levels for VV and VH are
reported separately. **Fast reference**, **Slow reference**, **Raw**,
**Corrected** and **Log counts** switch the displayed traces; these controls
change the view rather than the tail-matching calculation.

## 3. Slow reference and mixing

**Slow protein...** loads the slow reference. Set **dt**, **rho** and **r0**; the first-moment lifetime and
the Perrin steady anisotropy give the linked $l_1 = l_2$ estimate in the *Mixing estimate* table. The
manual toggles override the lifetime, the target anisotropy or the mixing parameter.

One steady-state observable determines only the linked mixing estimate. If it
is missing or outside the physical range, the detector-calibration handoff
preserves its previously stored mixing values. To replace them deliberately
with zero, enable **Manual l1 = l2** and enter **0**; an unchecked override with
no estimate is not a request to erase the stored calibration. Set **dt** from
the acquisition calibration in ns/bin before interpreting the slow-reference
lifetime or the Perrin estimate.

## 4. Batch, export, archive

The **Batch anisotropy** tab queues further decays (**Add files...**; Delete removes the selected one),
**Run batch** evaluates $r_\infty$ of each with the frozen calibration and **Save table...** writes a
tab-separated file. **Export calibration JSON...** writes the values and settings;
**Archive reference calibration** registers the reference decay, corrected traces and provenance in MMFDB.

The archive uses one resolved MMFDB session for the reference, processed traces
and calibration, including their operation and ACL ownership. It also retains
the supplied source measurement and complete calibration input settings in the
reference metadata; the derived records link back to that reference. An
explicit calibration actor takes precedence, otherwise the service resolves the
authenticated actor or configured local default.

```{figure} figures/vv_vh_g_factor_native_batch.png
:name: fig-vv-vh-g-factor-native-batch
:width: 100%

Two synthetic seeded batch decays evaluated with the same corrected G
(1.21871) and tail bins 358–460. Their steady anisotropies are approximately
0.165208 and 0.342232. The native tab retains Add files, Folder, Database, Remove,
Clear, Run batch and Save table; its table includes the file, anisotropy,
region, G, both backgrounds and an error column.
```

The shared native detector editor's **Calc G** action reads an independent TTTR
reference and hosts this full calculator inside its existing canvas; it does
not replace the detector page's loaded measurement or preview. A valid saved
raw tail offers **Run headlessly** or **Open calculator**. The separate
**Preview G** action estimates G from the already loaded detector preview,
updates that working value without archival and clears its old calibration
identifiers. See [independent reference calibration](87_channel_definition.md#6-independent-reference-calibration).

In that detector workflow, use **Apply calibration and close** to publish a
valid completed result after any pending field commit/recomputation, or
**Discard calibration** to retain the previous calibration. Escape cancels a
nested Help window or file chooser while leaving the calculator open. Closing a completed, valid calculator also publishes once.
Closing while work is pending or after an error, cancelling the reference, or
using a read-only definition leaves the working detector calibration
unchanged. Repeated closure does not apply or archive it again. A changed
selected setup or reloaded fast input requires a fresh **Calc G** TTTR handoff;
the old detector context is not applied to a replacement reference.

Reference aggregation uses the detector's alternating VV/VH routing-channel
order, configured LUTs and shifts, and micro-time binning. The calculator's
tail/background/shift controls use binned histogram bins, while the detector's
saved tail uses raw TAC channels. The saved tail is divided by binning on
entry and multiplied back when applied. **dt** starts from the independent
reference's effective micro-time resolution in ps, multiplied by 0.001 for
ns/bin; the existing working definition's timing is not overwritten.

The configured MMFDB calibration actor is passed to archival. G and its
calculated SD, both backgrounds, shift, flip, mixing and source/provenance
information are stored with the archived reference and calibration. The
working detector receives G, l1/l2, the raw tail and linked reference-decay and
calibration UUIDs. Archival succeeds before an owned, previously saved setup
is persisted. A named-save failure restores the working detector, but may
leave the already archived records; a setup that is not eligible for that
save remains a working definition until **Save** is used separately.

## Headless and Python

```python
from chisurf.plugins.vv_vh_g_factor.gui.model import GFactorModel

m = GFactorModel()
m.load("fast.dat")
m.load("slow.dat", slow=True)
m.fp_dt_ns = 0.05  # ns/bin for the synthetic reference; use your acquisition calibration
m.background = True
m.compute()
print(m.g_factor, m.result["g_factor_stddev_corrected"], m.fp_result.get("l1"))
```

Here `fast.dat` and `slow.dat` are your stacked VV/VH reference files. The
synthetic figure above uses 0.05 ns/bin; substitute the physical acquisition
value for measured data. A missing mixing estimate is reported as `None`.
The bundled noisy `test_vv_vh_data.dat` is a reader/calculation fixture;
its observed G near 15.6 is not calibration ground truth.

The plugin's `calculate` command is dispatched through ChiSurf's `csc` CLI and
runs the same tail-matching core without a GUI:

```bash
pixi run -e test csc vv-vh-g-factor calculate fast.dat --region-min 358 --region-max 460 --use-bg --bg-min 25 --bg-max 76
```

Tail and background bounds are TAC bins. The command emits G, raw/corrected
standard deviations and channel backgrounds as JSON; use bounds appropriate
to your reference rather than copying the synthetic figure's region blindly.

## See also

- Concept: {ref}`concept-anisotropy`; workflow: [Fluorescence lifetime and anisotropy decay fitting](10_lifetime_anisotropy_fitting.md).
- The g-factor and l1/l2 enter the [Anisotropy Wizard](10_lifetime_anisotropy_fitting.md).
