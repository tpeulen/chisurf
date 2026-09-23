# FCS confocal calculator

Seven quantities — τ, D, rₕ, S, V_eff, N, c — that are not independent. Fix the
ones you know, and this reads off the rest.

It takes no data. It is a calculator over the relations an FCS fit leaves you
holding, and it exists because the conversions in the middle are where FCS
numbers usually go wrong.

Press **Guide** for the walk-through.

## The relations

**τ_D = w_xy² / (4·D)** — diffusion time from the beam waist.

**V_eff = π^{3/2} · w_xy³ · S**, with **S = w_z/w_xy** the axial-to-lateral
aspect ratio of the focus.

**D = k_B·T / (6·π·η·rₕ)** — Stokes–Einstein, which turns a diffusion
coefficient into a hydrodynamic radius given the temperature and the viscosity.

**N = 1/G(0)** and **c = N / (V_eff · N_A)** — the amplitude gives the mean
number of molecules in the volume, and the concentration follows only once
V_eff is known.

Pin one of *D*, *rₕ* or *V_eff* with the constraint radios; the others are then
determined. That is the whole design: the calculator has one degree of freedom
and you choose which.

## The thing that actually decides your numbers

**FCS measures τ. It does not measure D.** Converting one to the other needs
w_xy, and w_xy comes from a **calibration measurement on a dye of known D** —
which is what the reference-dye panel is for. Every quantity downstream of that
calibration inherits its error:

- **rₕ** scales as 1/D, so a 10 % error in the calibration is 10 % in rₕ;
- **V_eff** goes as **w_xy³**, so the same 10 % is **33 %** in V_eff;
- **c** is proportional to 1/V_eff, so concentrations from FCS carry that 33 %
  too — before any other source of error.

That cubic is the reason FCS concentrations are routinely quoted with more
confidence than they deserve. If the number that matters is a concentration,
the calibration is the measurement, not a preliminary.

**S is the other half of V_eff, and it is usually a guess.** A typical confocal
S is 3–6, and the fitted value is poorly determined because the axial dimension
barely shows in the correlation curve. V_eff is linear in S, so choosing 5 when
the truth is 3 is a 67 % error in every volume and concentration that follows.
Fit it if the data support it, use a calibrated value if not, and quote it.

## Temperature and viscosity

D scales as **T/η**, and η itself depends strongly on T — water roughly halves
in viscosity between 10 °C and 40 °C. So a D measured at room temperature and a
literature D at 20 °C are not comparable numbers.

*Use water η(T)* takes the viscosity from an empirical relation. Override it
when the sample is not water: glycerol, a crowded lysate, or a membrane all have
an effective viscosity that is not water's, and no amount of temperature
correction will find it for you.

The reference-dye panel stores D at 25 °C in water, and can scale that reference
to your (T, η) before it is used — which is the correct order. Comparing an
uncorrected reference against a corrected measurement is a silent systematic.

## Shape: rₕ is not a radius

Stokes–Einstein gives the radius of the **sphere that would diffuse the way your
molecule does**. For anything elongated, that number is larger than the
molecule's own dimensions — an extended protein reports an rₕ far above the
radius of gyration of its own structure, and reading it as "size" overstates the
molecule.

The shape panel inverts the relation properly for the case you name:

- **Sphere** — Stokes–Einstein as it stands.
- **Ellipsoid** — the Perrin friction factor, which is the honest correction for
  an axial ratio you can state.
- **Cylinder** — the Hansen (2004) approximation, for rods.

None of these is a measurement of shape. They convert a measured D into a size
*given* a shape you assumed; the assumption stays yours.

## Before believing the result

- **Which constraint is active?** The value you think you are reading may be one
  the calculator just computed from the other two.
- **Is the calibration current?** Beam waists drift with alignment, cover-glass
  thickness and immersion oil. A calibration from last month is a number, not a
  measurement of today's focus.
- **Is S honest, or inherited?** See above; it is linear in every volume.
- **Was the reference dye scaled to your conditions?** 25 °C water is rarely
  where you are working.
- **Does the shape assumption match the molecule?** For anything non-globular,
  the sphere model overstates the size, and it does so silently.

Export the state to JSON when a number goes into a figure. The relations are
cheap to recompute; the assumptions behind them are what you will want back in
six months.

## Further reading

- [FCS correlation](docs/concepts/fcs_correlation.md) — where τ_D and V_eff come from.
- [Diffusion by FCS, step by step](docs/guides/09_diffusion_fcs.md)
- [FCS saturation](docs/concepts/fcs_saturation.md) — what excitation power does
  to the effective volume, which this calculator assumes is fixed.
- [Two-focus FCS](docs/guides/05_enderlein_mdf_two_focus_fcs.md) — the
  calibration-free alternative, when the calibration is the problem.
- Kapusta, *Absolute diffusion coefficients: compilation of reference data for
  FCS calibration*, PicoQuant application note (2010).
- {cite}`perrin1936` — translation of ellipsoidal molecules: the friction
  factor behind the *Ellipsoid* shape.
- {cite}`hansen2004` — the cylinder approximation for rods.