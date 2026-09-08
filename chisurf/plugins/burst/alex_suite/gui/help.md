# ALEX Suite — the same workflow, in ChiSurf

If you used **ALEX-Suite**, this window is your program's workflow. Same order,
same vocabulary, mostly the same buttons — but each step is one of ChiSurf's own
tools underneath, so the result is a normal ChiSurf burst analysis that every
other tool can read.

Press **Guide** for the walk-through.

## Where everything went

| ALEX-Suite | here |
|---|---|
| *Select Directory* + file list | **1. Files** — drop files or folders; also reads MMFDB |
| *Burst Search Settings → Microscope* (period, shift, 4 laser edges, flip) | **2. Alternation** — one button, all of it measured from the data |
| *Burst Search → APBS / DCBS* | **3. Burst search** |
| the `bkg_DD` / `bkg_DA` / `bkg_AA` fields | **4. Background** — measured, not typed |
| *Accurate FRET* (`E_donly`, `S_aonly`, γ, β) | **5. Accurate FRET** — α, δ, γ, β found from your own populations |
| *E vs S Histogram* **and** *Dataset Viewer* | **6. E–S histogram** (ndX) |
| *Burst Properties* | **Burst properties** |
| *Titration* | **Titration** |
| *BVA* | **BVA** |
| *Trace Viewer* | **Trace viewer** |
| *Export* (five CSVs) | **Export (ALEX-Suite CSV)** |

Two things have no row because they are gone rather than moved: the **channel
flip** checkbox (the alternation step works out which detector is which from
which laser window it is brighter in) and the **`sm2burst` cache** (bursts are
kept in the measurement's own `.pto`, so nothing can go stale against a settings
change).

## Where the detector setup is chosen

**Step 2, the first control.** The setup says which routing channels are the
donor and the acceptor and which micro-time window is which excitation, and
everything after step 2 reads it — the burst search, Accurate FRET and BVA each
show the same setup in their own combo, already filled in.

* **µs-ALEX:** you do not choose it. *Detect alternation and convert* measures
  the channel assignment and the gates and writes a setup called
  **ALEX Suite (auto)**, then selects it. The two channel fields say `auto`
  until it has run and then show what was decided, so you can check it.
* **Already PIE / ns-ALEX:** pick your own setup in that combo and skip the
  detection. That is the only thing step 2 is for in your case.

The old *channel flip* checkbox is gone because the answer is in the data: under
acceptor excitation the donor detector sees essentially nothing, whatever the
sample's FRET efficiency or labelling. On the calibration file this was built
against, the donor is routing channel **1** and is 5 % as bright under acceptor
excitation — a flipped assignment that the old program needed a checkbox for.

## What comes out

The same thing the PIE burst workflow produces, because it is the same code: one
**`.pto` container per measurement**, holding the photons, the bursts found in
them, and the companion tables every later analysis writes beside them. Nothing
here has an ALEX-only format.

That matters in practice: an analysis started in this window can be continued in
**Burst Analysis** — which additionally offers 2CDE, burst-wise lifetime fits,
H2MM segmentation and burst fusion — and brought back, with no conversion.

## The three things worth doing carefully

**The alternation must look right.** Step 2 plots the folded phase for each
detector. You should see two plateaus with a gap between them, and the donor
detector brighter in one of them, the acceptor detector in the other. If the two
curves track each other, the period is wrong or the channels are swapped; the
"contrast" number below the button says the same thing (under ~50 is suspicious).

**Vary the burst threshold by a factor of two.** A real population survives it.
If the burst count and the histogram both move a lot, you are looking at your
threshold rather than at your sample.

**Check where donor-only lands.** After step 5, the donor-only population should
sit at S ≈ 1 and E ≈ 0. If it does not, the channel assignment is wrong, and
nothing downstream will tell you — a swapped assignment produces a complete,
plausible analysis with *E* reflected about ½.

## Titration

The one analysis with no equivalent elsewhere in ChiSurf. Give it one burst file
per ligand concentration; it histograms all of them, fits them **together** with
the population positions and widths shared, and fits a binding isotherm to the
amount of the population that changes.

Sharing the shape is the point. Fitting each histogram on its own lets a noisy
condition move a peak by more than the amplitude change you are trying to
measure, and the isotherm then reports that noise as affinity.

If the series does not reach saturation, treat the fitted *K*<sub>d</sub> with
suspicion: an unsaturated curve lets *K*<sub>d</sub> and the plateau trade off
against each other, and both come back precise and wrong.

## Headless

```
csc alex-suite alternation *.sm --donor 0 --acceptor 1
csc burst-selection ...            # the ordinary burst search
csc alex-suite titration series.csv --populations 2
```

## Further reading

- [Single-molecule FRET: bursts, E, S and the corrections](docs/concepts/smfret_bursts.md)
- [Coming from ALEX-Suite](docs/guides/66_alex_suite.md)
- [µs-ALEX and the titration it enables](docs/concepts/us_alex.md)
- [A complete µs-ALEX smFRET workflow](docs/guides/27_alex_smfret_workflow.md)
- [Finding bursts, step by step](docs/guides/13_burst_identification.md)
- [Accurate FRET](docs/guides/41_accurate_fret.md)
- [Selecting FRET populations](docs/guides/28_selecting_fret_populations.md)
- [Burst variance analysis](docs/guides/08_burst_variance_analysis.md)
- Kapanidis *et al.*, PNAS **101**, 8936 (2004) — [10.1073/pnas.0401690101](https://doi.org/10.1073/pnas.0401690101)
- Hellenkamp *et al.*, Nat. Methods **15**, 669 (2018) — [10.1038/s41592-018-0085-0](https://doi.org/10.1038/s41592-018-0085-0)
