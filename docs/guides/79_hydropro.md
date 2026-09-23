---
type: Guide
title: 'HydroPro: diffusion coefficients from a structure'
description: Predicting the translational diffusion coefficient (and, from the report, the rotational relaxation times) of a rigid protein from its PDB file with the external HYDROPRO program, using T4 lysozyme as the example, and what the ChiSurf front-end does and does not do.
tags: [guides, structure, hydrodynamics, fcs, anisotropy]
---

# HydroPro: diffusion coefficients from a structure

How fast should this protein diffuse, and how fast should it tumble? HydroPro
answers from the structure alone. It writes the input file for the external
program **HYDROPRO**, runs it once for each PDB file, and collects the
translational diffusion coefficient $D_t$ into a table. The same run also
writes a report with the rotational diffusion tensor and relaxation times,
which is what an anisotropy measurement is compared with.

For the physics (Stokes–Einstein, bead and shell models, and what the numbers
mean for FCS and anisotropy), see {ref}`concept-hydrodynamics`.

```{important}
ChiSurf does not ship the calculation. HydroPro is a front-end to the HYDROPRO
executable from the García de la Torre group, which you download separately.
The distributed binaries are for Windows and Linux. There is no macOS build, so
on a Mac HydroPro can prepare the input but cannot run it (see
[Known defects](#known-defects)).
```

## Open the tool

**Structure → Structure Tools**, then **🌊 HydroPro** in the left list. The
entry sits below the separator, next to QuEst. It has no ribbon button of its
own.

```{figure} figures/hydropro_tool.png
:name: fig-hydropro-tool
:width: 80%

HydroPro with T4 lysozyme (PDB 148L) selected and its mass and partial
specific volume entered. The structure is listed in the table with an empty
result, because no executable is configured on this machine. **Run** would
open the dialog below.
```

## Set it up

**Executable & input**

1. **Executable**: the HYDROPRO 10 binary from the program's download
   archive (for example `hydropro10-lnx.exe` on Linux). Set it with **Executable…**. The file name
   decides which input format is written: a name containing `hydropro` gets a
   HYDROPRO `hydropro.dat`, and anything else is treated as HYDRO++ (see
   [Known defects](#known-defects)).
2. **Structures**: one or more PDB files, set with **Select files…**. Each
   one becomes a separate job. Remove crystal waters, ligands and alternate
   conformations first: HYDROPRO models every non-hydrogen `ATOM` and `HETATM`
   except water oxygens.

**Primary model** (HYDROPRO manual §3.a)

3. **INDMODE**: 1 builds a sphere around every atom, 2 one sphere per residue,
   both followed by a shell calculation. 4 uses one bead per residue. Mode 1
   is the reference, and the manual quotes under 20 s per structure. Mode 4 is for very large
   assemblies.
4. **AER**: the radius of the primary spheres. It includes the hydration layer
   and is calibrated per mode: **2.9 Å** (mode 1), **4.8 Å** (2), **6.1 Å**
   (4). Changing INDMODE does not change AER, so set both together.
5. **NSIG**, **SIGMIN**, **SIGMAX**: the number and range of minibead radii
   for the shell extrapolation (modes 1 and 2). NSIG = −1 lets HYDROPRO choose
   the range, and then SIGMIN and SIGMAX are not written. The defaults (6,
   1.0–2.0 Å) are the manual's.

**Solvent & macromolecule** (§3.b)

6. **T** (°C) and **ETA** (poise; water at 20 °C is 0.01 P = 1.0 mPa·s). These
   two set every diffusion coefficient, which scales as $T/\eta$. Enter the
   viscosity of your buffer, not of water, if they differ.
7. **RM** (Da), **VBAR** (cm³/g), **RHO** (g/cm³): the molecular mass,
   partial specific volume and solution density. They enter only the
   sedimentation coefficient and intrinsic viscosity, not $D_t$ or the
   rotational times. The default RM of 100 000 Da is a placeholder. For 148L,
   enter 18 700 Da and 0.73 cm³/g.

**Optional calculations** (§3.c)

8. **NQ** / **QMAX**: the scattering form factor (0 = skip, −1 = automatic).
   **NS** / **RMAX**: the distance distribution $p(r)$ (same convention).
   **NTRIALS**: Monte-Carlo trials for the covolume. It is slow, so 0 skips it.
9. **Full diffusion tensor** (IDIF = 1): writes the $6\times6$ diffusion
   tensor and the centre of diffusion into the report.

## Run and read the result

**Run** checks the settings (INDMODE must be 1, 2 or 4, NSIG > 2 or −1, QMAX
and RMAX > 0 when requested), stores them, and starts the jobs off the GUI
thread. A **HYDRO Output** window streams the program's console output and has
a **Cancel** button, which stops after the current job. Each structure runs in
its own folder, `~/.hydropp_gui/job_001`, `job_002`, …, and the table's second
column fills with $D_t$ in cm²/s. **Save CSV** writes the two columns.

If no executable is configured, **Run** opens this dialog instead:

```{figure} figures/hydropro_exe_dialog.png
:name: fig-hydropro-exe-dialog
:width: 60%

The dialog shown when the executable path is empty or does not exist.
**Select executable…** picks the binary, and **Open download page** opens
the program's web page.
```

The table shows only $D_t$. Everything else HYDROPRO computes is in the
report `<name>-res.txt` (the name the parser reads) inside the job folder, where `<name>` is the PDB file
name without extension. It contains the radius of gyration, the volume, the
rotational diffusion coefficient, the five rotational relaxation times, the
sedimentation coefficient, the intrinsic viscosity
and, with IDIF = 1, the full tensor. For an anisotropy comparison, read the
relaxation times from there.

## Where the numbers go next

- **FCS**: $\tau_D = w_{xy}^2/(4D_t)$. With a calibrated waist, the predicted
  $\tau_D$ is a check of the model, or of the oligomeric state, against the
  fitted diffusion time ({doc}`75_fcs_toolbox`).
- **Anisotropy**: the relaxation times are the global correlation times $\rho$
  to compare with the slow component of a rotation-spectrum fit
  ({ref}`concept-anisotropy`, {doc}`10_lifetime_anisotropy_fitting`).
- **Dye simulations**: the same relations give diffusion coefficients for
  QuEst's dye model ({doc}`80_quenching_estimator`).

## Headless

The input writer, the runner and the report parser do not need Qt. This was
run on 148L; it writes the job folder and the `hydropro.dat` HYDROPRO reads:

```python
from pathlib import Path
import shutil
from chisurf.plugins.modelling.hydropro.core import HydroProSettings, write_hydropro_input

job = Path("hp_job"); job.mkdir(exist_ok=True)
pdb = shutil.copy("test/data/atomic_coordinates/pdb_files/148l.pdb", job)
settings = HydroProSettings(rm=18700.0, vbar=0.73)
settings.validate()
name, dat = write_hydropro_input(Path(pdb), job, settings)
print(dat.read_text())
```

```text
148l                        !TITLE (CHAR*20)
148l                        !FILENAME (base for outputs)
148l.pdb        !INPUT PDB filename (relative)
1               !INDMODE: 1 atomic/shell, 2 residue/shell, 4 residue/bead
2.9,            !AER (Å) hydrodynamic radius of primary elements
6,              !NSIG (>=3 typical 5-8)
1.0,            !SIGMIN (Å) minibead radius
2.0,            !SIGMAX (Å) minibead radius
20.0,            !T (°C)
0.01,           !ETA (poise)
18700.0,        !RM (Da)
0.73,           !VBAR (cm3/g)
1.0,            !RHO (g/cm3)
-1              !NQ: 0 omit, -1 automatic, >0 specify QMAX
-1              !NS: 0 omit, -1 automatic, >0 specify RMAX
0,              !NTRIALS for covolume (MC)
1               !IDIF=1 for full diffusion tensors
*                                    !End of file
```

With an executable, `run_hydro` does the whole loop and returns one
`HydroResult(struct_file, diffusion_coefficient)` per structure:

```python
from chisurf.plugins.modelling.hydropro.core import run_hydro
results = run_hydro([Path("148l.pdb")], settings, Path("/opt/hydropro/hydropro10-lnx.exe"),
                    work_dir=Path("hp_runs"), on_log=print)
```

The same is on the command line, `csc hydropro run 148l.pdb -e <exe> --rm 18700
--vbar 0.73 --json`, with `csc hydropro parse-res <file>` to read $D_t$ from an
existing report. Over RPC the methods are `hydropro.run` and
`hydropro.parse_res`.

## Using it well

**Check the structure before the numbers.** A missing loop makes the molecule
smaller and faster, and a bound detergent or a crystallographic dimer makes it
larger. Look at the PDB file that goes in.

**Keep AER at the calibrated value.** It is the model of the hydration layer,
fitted once for all proteins. Adjusting it to match a measurement means
predicting a different molecule. The exception is low-resolution bead models,
for example from SAXS, as the HYDROPRO manual describes.

**Treat the prediction as a lower bound for flexible proteins.** The
calculation is for one rigid conformation. Disordered tails and linkers make
the real protein slower.

**Match the conditions.** Compare at the same temperature and viscosity, or
convert both to $D_{20,w}$. A buffer with 10 % glycerol is about 30 % more
viscous than water.

## Known defects

- **No executable on macOS.** HYDROPRO 10 is distributed as Windows and Linux
  binaries only, so on this machine (macOS, arm64) no calculation could be run
  and no value for 148L is shown here. The input file above was written and
  checked against the HYDROPRO 10 manual.
- **HYDRO++ ignores the form.** When the executable name does not contain
  `hydropro`, {src}`chisurf/plugins/modelling/hydropro/core/runner.py#construct_input_file`
  writes a fixed input (20 °C, 0.01 P, 100 000 Da, 0.74 cm³/g) and none of the
  settings in the form are used. Rename the binary so its name contains
  `hydropro`, or check the input written to the job folder.
- **Only $D_t$ reaches the table.** The rotational relaxation times, which the
  anisotropy comparison needs, have to be read from `<name>-res.txt` by hand.
- **Job folders are reused.** Every run writes to `~/.hydropp_gui/job_001` and
  so on, overwriting the reports of the previous run. Copy a report you want to
  keep.
- **Download page.** **Download page** and the dialog open the HYDRO++ page,
  not the HYDROPRO page
  (`https://leonardo.inf.um.es/macromol/programs/hydropro/hydropro.htm`). The
  dialog's *Don't show this on startup* check box is not stored.

## See also

- Concept: {ref}`concept-hydrodynamics`. Related: {ref}`concept-anisotropy`,
  {ref}`concept-fcs-correlation`, {ref}`concept-molecular-surfaces`.
- Tool: **HydroPro** (`chisurf/plugins/modelling/hydropro/`), reached through
  **Structure Tools**. Press **Guide** on its toolbar for a walk-through.
- Program: HYDROPRO 10 {cite}`ortega2011`; the method
  {cite}`garciadelatorre2000`.
