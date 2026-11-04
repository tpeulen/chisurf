# Data Selection — what the workflow works on

Step 1 of the Burst Analysis workflow. A session has more files than the sample, and each has a
role: the **measurements** are searched for bursts (step 2); the **buffer**, an **IRF** and a
**reference dye** calibrate.

## The two tables

- **Workspace data** (top) lists the photon streams in the Datasets workspace. A group of files
  dropped together is one row; unfold it for its files.
- **What this workflow works on** (bottom) has one row per role, made from the detector setup of
  step 0: **Measurement**, **Buffer**, then an **IRF** and a **Reference dye** row for every
  colour of the setup (green, red, … — named after its detectors in the tooltip). Without a
  setup only Measurement and Buffer are shown. Under each role is what is assigned to it.

## Assigning

- **Drag** a workspace row onto a role row; the row under the pointer lights up. A group goes
  as a whole.
- **Move** an entry: drag it onto another row, or right-click › *Move to*. Right-click a
  workspace row › *Add to* assigns without dragging.
- **Drop photon files** (`.ptu`, `.spc`, `.ht3`, …) on a role row: they are linked into the
  workspace, as any drop on ChiSurf is, and assigned to that row.
- *Use selected* and other hand-overs guess the role from the name (`buffer`, `bg` → Buffer;
  `irf`, `H2O`, `water`, `scatter` → IRF; `Rh110`, `A647`, `Cy5`, `dye`, `ref` → Reference dye
  of the dye's colour), else Measurement.
- **Found beside the measurement**: a new measurement brings the buffer, IRF and reference-dye
  files of its folder (else the folder above) into their rows by their names, marked **found**
  (where from in the tooltip): Rh110 to *Reference · green*, Alexa 647 to *Reference · red*, so
  G and the confocal volume are computed at once. Move one, or Delete it -- a removed proposal is
  not proposed again. This step is the one place the workflow's references come from: Burst MLE
  reads only what its rows hold, never files by name.
- **Remove** (or Delete) takes the selected file, group or row's files out; **Clear** all.
- A role the setup no longer has (a colour removed in step 0) shows its files as
  **Unassigned** — they are kept, and come back with the colour.

## What the calibration files give

Computed in the background as they are assigned (the step waits behind a progress card):

- **Buffer** — the background rate of every detector, `B_<detector>` in kHz; Burst MLE uses the
  buffer to correct a scatter IRF. The background of the lifetime fit stays the photons outside
  the bursts.
- **IRF** — Burst MLE's measured IRF of the colour's detectors.
- **Reference dye** — the **G factor** of the colour's detectors (the VV / VH tail ratio of a
  fast-rotating dye) and the **confocal volume** (w0, z0, V_eff) from the dye's correlation and
  its diffusion coefficient D. The **Dye** cell picks the dye from the dye database (found in
  the file's header or name, else the colour's usual dye); D is the database's value at 25 °C,
  corrected to the temperature in the Calibration window, or *Other (custom D)*.

Each role row shows its numbers — **G**, **V_eff** (fL), **τ_D** (µs), **w0** (µm), **s** and
**cpm** (brightness per molecule, kHz) of a reference dye, **B** (kHz) of the buffer, the **IRF**
width (ps) — and a one-word **Status** (*measured*, *estimated*, *hand-edited*). The headers'
tooltips say what a good value is; a row's tooltip says more. The G factors are written into the
setup as they are computed; a G you then edit in step 0 is kept. **Advanced** adds the
Calibration window: the temperature (or your own D), D with its source, and the fitted
correlation. The full record — files and hashes, fit parameters with uncertainties, D's
literature source — is the analysis report, written into each measurement's container with the
bursts.

## Without calibration files

Nothing but a measurement is needed. Without a buffer the background is estimated from the
photons outside the bursts, without an IRF from the non-burst photons (else blindly from the
burst decay), without a reference dye G is the setup's and there is no confocal volume. The
step says so in one line, and the workflow records what was estimated.

Each newly added local file is put into the MMFDB object store and registered as raw TTTR data
when you are signed in; **Details** (Advanced) shows the record, **Import again** repeats it.

Further reading: [Calibrating with a buffer, an IRF and a reference dye](docs/concepts/reference_dye_calibration.md),
[Photon burst identification](docs/guides/13_burst_identification.md).
