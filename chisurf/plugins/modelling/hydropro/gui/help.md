# HydroPro — diffusion coefficients from a structure

HydroPro predicts how fast a rigid protein diffuses from its PDB file. It
writes the input for the external **HYDROPRO** program, runs it once per
structure, and collects the translational diffusion coefficient $D_t$
(cm²/s) into the table. The program is **not** part of ChiSurf: download it
from the García de la Torre group. Its binaries are for Windows and Linux; on
macOS the tool can prepare the input but cannot run it.

If you have never used it, press **Guide** in the toolbar.

## The settings that decide the answer

**INDMODE and AER go together.** Mode 1 (a sphere around every atom, shell
calculation) with AER = 2.9 Å is the reference. Mode 2 uses 4.8 Å and mode 4
uses 6.1 Å. AER already contains the hydration layer and was calibrated once
for all proteins, so keep it at these values. Changing INDMODE does not change
AER for you.

**T and ETA set every diffusion coefficient**, which scales as $T/\eta$. ETA is
in poise: water at 20 °C is 0.01 P. Enter your buffer's viscosity if it is not
water.

**RM, VBAR and RHO do not change $D_t$.** They enter only the sedimentation
coefficient and the intrinsic viscosity. The default RM of 100 000 Da is a
placeholder.

**The structure is the model.** HYDROPRO counts every non-hydrogen atom
except water oxygens, ligands and detergent included. A missing loop makes the
molecule smaller and faster.

## What comes out

The table shows $D_t$ only. Each structure runs in `~/.hydropp_gui/job_NNN`,
and the full report `<name>-res.txt` there holds the radius of gyration, the
rotational diffusion coefficient and the five rotational relaxation times you
compare with an anisotropy decay, plus the sedimentation coefficient and the
intrinsic viscosity. The job folders are reused, so the next run overwrites
them.

For FCS, $\tau_D = w_{xy}^2/(4D_t)$. For T4 lysozyme a Stokes–Einstein
sphere with 0.3 g/g hydration gives $D_t \approx 1.1\times10^{-6}$ cm²/s and
$\rho \approx 8$ ns at 20 °C.

## Pitfalls

* An executable whose file name does not contain `hydropro` is treated as
  HYDRO++, and then the form's settings are **not** used: a fixed input
  (20 °C, 0.01 P) is written instead.
* The calculation is for one rigid conformation. Flexible proteins are
  slower than predicted.
* The tool does not interpret the structure or build a bead model itself: it
  passes the file to the program, which expects a PDB file (HYDROPRO) or a
  bead coordinate file (HYDRO++). Supplying a suitable file and checking the
  result against the program's own report is up to you.

The GUI, the CLI (`csc hydropro run`) and the RPC service (`hydropro.run`) all
go through `chisurf.plugins.modelling.hydropro.core.run_hydro`.

## Further reading

Documentation links open in the ChiSurf documentation browser; the references
open in your web browser.

- [Hydrodynamics of rigid macromolecules — the theory](docs/concepts/hydrodynamics.md)
- [HydroPro — the workflow](docs/guides/79_hydropro.md)
- [Time-resolved fluorescence anisotropy](docs/concepts/anisotropy.md)
- {cite}`garciadelatorre2000` — HYDROPRO
- {cite}`ortega2011` — HYDROPRO 10
- {cite}`garciadelatorre2007` — HYDRO++: rotational diffusion and intrinsic viscosity of bead models
- {cite}`peulen2017` — where hydrodynamic and dye-diffusion estimates meet in the analysis of time-resolved FRET
- [HYDROPRO download page](https://leonardo.inf.um.es/macromol/programs/hydropro/hydropro.htm)
