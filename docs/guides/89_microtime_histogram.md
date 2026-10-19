---
type: Guide
title: Histogramming micro times per detector and polarization (Histogram-Microtime)
description: Building the VV/VH decay of one or many photon files with Histogram-Microtime — queue files and burst selections, choose the detector and channels, gate, bin and shift, compute, save and transfer to the TCSPC analysis — in the window and from Python.
tags: [guides, tcspc, decay, photons, bursts, fret, python]
---

# Histogramming micro times per detector and polarization (Histogram-Microtime)

**What you get:** the cumulative decay of the photons you select (VV and VH, and the combined VV + 2G·VH trace), a
one-column file of it, and with one more click a TCSPC dataset in ChiSurf with the right time step, G-factor and
polarization.

Theory: how photons are selected and combined is in {ref}`concept-microtime-histogram`; what the decay is used for is
{ref}`concept-tcspc-lifetime`; the detectors and windows come from the detector setup of
{doc}`87_channel_definition`. The generic decay of a photon file without polarization handling is in
{doc}`73_tttr_decay_and_correlation`.

## 1. Open the tool

**Spectroscopy → Decay → Histogram-Microtime**. Two tabs share the left dock:
**Inputs and options** and **Detector definition** (the shared detector editor: reading routine, PIE windows,
detectors, TAC linearization). The decay is on the right and gets the room. **Guide** walks through the tool, **Help**
explains every group.

The ChiSurf shell docks this emtk/AutoForm app. For a desktop with a working display/GPU, launch it with
`pixi run -e test python -m chisurf.plugins.tttr.microtime_histogram`.
Its startup options can queue an existing burst-analysis folder:

```bash
pixi run -e test python -m chisurf.plugins.tttr.microtime_histogram --bid-folder path/to/bursts --setup-name my_setup --auto-transfer
```

`--bid-folder` reads the folder's burst-index inputs and finds their photon
sources. `--setup-name` selects a saved detector setup. If omitted, the launcher
reads `Info/photon_selection_parameters.json` and its `selected_setup` field
beside the measurement: first the burst folder's parent, then the grandparent
only when the parent's `Info` directory is absent. `--auto-transfer` requests
transfer after a successful histogram. A nonexistent folder is rejected before
opening a window. This is a desktop launcher; use the Python model below for
windowless computation.

```{figure} figures/microtime_native_bh132.png
:name: fig-microtime-histogram
:width: 100%

Measured BH132 photon fixture (183,657 photons), green detector: parallel
channels 8 and 3, perpendicular channel 0. The selected VV/VH counts are
79,468/56,499. The combined 113-bin width reads 0.372 ns under provider/header-derived
0.0032958984375 ns/bin timing; this headerless SPC fixture does not independently
calibrate the instrument. The logarithmic plot and complete native inputs are
shown after computation.
```

## 2. Queue photons

Without your own data, press **Generate synthetic demo**. It queues a
deterministic PTU with exactly **3,000 VV** and **1,500 VH** photons and selects
the explicit synthetic VV/VH setup. Its generated header declares a 32 ps
micro-time step and 25 ns macro-time clock; the known four-channel FWHM is
0.128 ns. This is a synthetic workflow check, not instrument calibration.
The file lives in `demos/microtime_histogram` under the ChiSurf settings
folder. Generation replaces the queued inputs, leaves saved setups/data
intact, and does not start computation. Press **Compute** yourself; the
**Guide** waits for these real button clicks.

**Files…**, **Folder…** (recursive) and **Database…** (the MMFDB object store) fill the *Photon files* list; you can
also drop files on the window. Untick a file to leave it out; **All**, **None**, **Remove** (the selected row) and
**Clear** act on the list, and a right-click on a row removes it. Headerless SPC files need their subtype in **TTTR
format** (e.g. SPC-130), otherwise Compute says so. The *Burst selections* header unfolds the list of `.bst`/`.bur`
photon-index files; **Find TTTR** looks up to four folders above for the photon files they were made on.

## 3. Detector, channels and gates

Define the detectors in the **Detector definition** tab (or load a saved setup), then choose **Detector**: its
interleaved routing channels fill *Parallel* and *Perpendicular* (editable, comma-separated) and its G-factor fills
**G-Factor**. Untick **Polarization resolved** for one unpolarized stream. **Excitation window** keeps one gate,
**Binning** groups bins. **dt** is read from the provider's header timing; typing a value keeps it (**Manual time step**). **VV
shift** and **VH shift** pad or clip a histogram to line the two decays up.

The displayed **dt** is the output step in ns/bin. For the measured BH132
fixture, the provider reports **3.2958984375 ps/bin**, or **0.0032958984375 ns/bin**
at binning one. This headerless SPC fixture does not independently establish
the instrument's acquisition calibration. Provider/header-derived timing is retained unless a saved setup explicitly
enables its timing override or **Manual time step** is active. Binning scales
the provider/setup-derived output step. Use an independently known acquisition
calibration as an explicit override when available; an unsaved legacy field
value is not acquisition provenance.

**Inter-photon filter** optionally keeps selected photons whose next selected
photon is within **Max gap [ticks]**, measured in macro-time ticks.
**Invert (isolated photons)** instead keeps gaps at least that large. The last
selected photon has no successor and is excluded in either filtered mode.

```{figure} figures/microtime_native_detector.png
:name: fig-microtime-native-detector
:width: 100%

The native Detector definition tab with reading, detector and LUT controls,
including Edit JSON and Preview G. The unsaved 50 ps reading initializer shown
here is not acquisition calibration; the input-state computation retains the
provider/header-derived step unless an explicit timing override is enabled.
```

## 4. Compute, save, transfer

**Compute** reads the selected files in the background (**Stop** appears while it runs) and draws the decays; the
**FWHM** of the combined trace is shown beneath the run buttons. **Save** writes the VV bins followed by the VH bins
when **Polarization resolved** is on, or one histogram of the selected channels when it is off, to
*Output* (the name is built from the file, detector and channels and can be edited); **Save as…** asks for another
name; with **Autosave after compute** the file is written as soon as the computation succeeds. **Transfer to ChiSurf**
saves and adds a TCSPC dataset (polarization from the **Polarization** choice, time step, G-factor). The plot
toggles above the decay show or hide each trace and switch the axis between logarithmic and linear; the wheel zooms
and a drag pans.

With the measured BH132 file and the green channel selection shown here, the
unshifted combined trace has FWHM **113 bins**, or **0.3724365234375 ns** using
the provider/header-derived timing. This time value is not an independently
validated instrument-response calibration. The export contains **8,192 integer rows**:
4,096 VV bins followed by 4,096 VH bins. Transfer supplies the effective time
step, G-factor, polarization choice and polarized/unpolarized layout to the
TCSPC reader. The one-column file itself does not carry a timing header, so
retain the acquisition calibration when reopening it independently.

## Headless

The computation has no GUI dependency:

```python
from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel

model = HistogramModel()
model.set_setup({"detectors": {"green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]], "g_factor": 1.0}},
                 "windows": {}, "tttr_reading": {}})
model.filetype = "SPC-130"
model.add_paths(["BH_SPC132.spc"])
model.auto_save = False
model.compute()
print(model.cumulative_parallel.sum(), model.cumulative_perpendicular.sum(), model.fwhm_ns)
model.save("decay.dat")
```

Run this example beside your input file, or replace `BH_SPC132.spc` with its
path. On the measured bundled fixture it yields 79,468 VV counts and 56,499 VH
counts with the provider/header-derived timing above. The Python model computes and saves a
histogram; it does not itself open a window or transfer a dataset.

The same synthetic demonstration can be generated and checked without a GUI:

```python
from chisurf.plugins.tttr.microtime_histogram.demo import SETUP, demo_folder, make_demo
from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel

source = make_demo()  # reuses a valid file + parameter/checksum cache
# make_demo(folder=demo_folder(), overwrite=True) explicitly regenerates it
demo_model = HistogramModel()
demo_model.set_setup(SETUP)
demo_model.filetype = "PTU"
demo_model.add_paths([source])
demo_model.auto_save = False
demo_model.compute()
print(demo_model.cumulative_parallel.sum(), demo_model.cumulative_perpendicular.sum(),
      demo_model.fwhm_bins, demo_model.fwhm_ns)  # 3000, 1500, 4, 0.128
```

## Using it well

- Check the channels of the detector against a quick intensity per channel before believing a VV/VH split: a swapped
  pair inverts the anisotropy.
- Histogram shifts do not wrap; if a decay starts before bin 0 use the photon Micro-time Shifter
  ({doc}`88_microtime_shifter`) instead.
- The combined trace needs the right G; a wrong G tilts it, it does not remove the polarization.

## Timing when comparing earlier results

The earlier window displayed an unsaved 50 ps setting for this SPC fixture;
that value was not a physically calibrated header measurement. The
workflow reads the provider/file-container timing. A validation-only comparison used
an explicitly declared **25 ps/bin** timing override in both implementations:
the same 113-bin width then reads **2.825 ns**, with identical histogram/export
values. That comparison establishes histogram/count and control parity, not
physical time calibration. Neither the 25 ps validation value nor the
provider-derived 3.2958984375 ps value substitutes for independently known
acquisition timing.

The earlier unpolarized path could include an extra all-source VH stream
when the perpendicular selection was empty. For this BH132 green selection,
that old export had 8,192 rows and 319,624 counts, including 183,657 unwanted
all-source counts. With **Polarization resolved** off, the native workflow
exports one chosen stream: 4,096 rows and 135,967 selected counts. This corrects
the extra-stream defect; the polarized export above still contains the normal
VV/VH pair.

```{figure} figures/microtime_native_unpolarized.png
:name: fig-microtime-native-unpolarized
:width: 100%

Polarization resolved is off: routes 8, 0 and 3 form one selected stream with
135,967 counts and a 4,096-row export. Its width is 116 bins (0.38232421875 ns
conditional on the same provider-derived timing), distinct from the polarized
combined-trace width. The unwanted all-source VH stream is absent.
```

## See also

{doc}`73_tttr_decay_and_correlation` · {doc}`88_microtime_shifter` · {doc}`87_channel_definition` ·
{doc}`/concepts/microtime_histogram`

The native Microtime Histogram tool starts at 1100×720 with saved custom
geometry taking precedence. The raw/gated photon histograms, physical clocks,
polarization curves and reported FWHM retain their values across geometry
restoration. Both detector and analysis pages remain reachable.
