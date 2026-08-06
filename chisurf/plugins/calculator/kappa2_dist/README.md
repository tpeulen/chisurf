# Kappa2 Distribution Plugin

This plugin provides tools for calculating and visualizing the distribution of the orientation factor κ² for Förster 
Resonance Energy Transfer (FRET) experiments.

## Features

- Calculate κ² distributions using different models (Wobbling-in-Cone, Diffusion-during-Lifetime)
- Visualize the distribution of κ² values
- Calculate the effect of κ² uncertainty on apparent FRET distances
- Support for known and unknown donor-acceptor orientations
- Incorporate steady-state anisotropy measurements to estimate fluorophore mobility

## Background

The orientation factor κ² is a critical parameter in FRET that describes the relative orientation of the donor emission 
dipole and the acceptor absorption dipole. It affects the calculation of the Förster radius (R₀) and consequently the 
distance measurements derived from FRET experiments.

In most FRET applications, κ² is assumed to be 2/3 (≈0.667), which is valid only when both fluorophores undergo 
isotropic rotational diffusion that is much faster than the fluorescence lifetime. However, in many biological systems, 
this assumption may not hold due to restricted rotational mobility of the fluorophores.

This plugin allows researchers to model more realistic κ² distributions based on experimental anisotropy data, providing 
more accurate distance measurements in FRET experiments where the standard assumptions about fluorophore mobility may 
not apply.

## Requirements

- Python packages:
  - PyQt5
  - numpy
  - scipy
  - matplotlib (for plotting)

## Documentation

- **In the tool:** press **?** for the models and what to measure, and
  **Guide** for a six-step walk through the controls. Both come from
  `gui/help.md` and `gui/guide.json`; there is no hand-written help dialog.
- **Theory:** [The orientation factor κ² and what it costs](../../../../docs/concepts/kappa2_orientation.md)
- **Workflow:** [Guide 61](../../../../docs/guides/61_kappa2_distribution.md)

## Usage

1. Launch from *Tools ▸ Calculators ▸ Kappa2 Distribution*, or run
   `csg_kappa2_dist`.
2. Choose the model:
   - **WIC (Cone)** — each dye wobbles in a cone set by its order parameter.
   - **DWT (Diffusion)** — a trapped fraction plus a freely reorienting one.
     Needs the **FRET E** field, because it averages efficiencies rather than
     rates.
   - **Isotropic** — random but frozen dipoles; the worst-case reference.
3. Enter the anisotropies: `r₀`, `r_D∞`, `r_A∞`, and — only if you measured it —
   `r_AD∞` with **r_AD known** ticked. Without it the tool returns the wider,
   honest bound.
4. **Compute**, then read **SD R_app/R_DA**: the relative systematic
   uncertainty κ² puts on the distance. That, not the mean κ², is the output.
5. **Save** writes the histogram as CSV with the model and order parameters in
   the header.

Headless:

```python
from chisurf.plugins.calculator.kappa2_dist.core.algorithms import compute_kappa2_dist

result = compute_kappa2_dist(model_type="cone", r_0=0.38,
                             r_Dinf=0.15, r_Ainf=0.20, r_ADinf=0.005)
print(result["k2_mean"], result["RappSD"])
```

## Theory

The orientation factor κ² is given by:
κ² = (cos θT - 3 cos θD cos θA)²

Where:
- θT is the angle between the donor emission dipole and the acceptor absorption dipole
- θD is the angle between the donor emission dipole and the line connecting the donor and acceptor
- θA is the angle between the acceptor absorption dipole and the line connecting the donor and acceptor

The plugin implements various models to calculate the distribution of κ² values based on the rotational mobility of the 
fluorophores, which can be estimated from anisotropy measurements.

## Applications

- Improving the accuracy of FRET-derived distance measurements
- Estimating uncertainty in FRET measurements due to orientation effects
- Studying systems with restricted fluorophore mobility
- Validating the κ² = 2/3 assumption in specific experimental setups
- Educational tool for understanding the impact of orientation on FRET

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.