---
type: Concept
title: 'Quenching inference: stickiness and quench strength from measured lifetimes'
description: How free-dye titrations, H2O/D2O series and lifetimes of a dye at many protein sites are joined in one Bayesian model that estimates where the dye sticks and how strongly contact quenches it, with the equilibrium ensemble, water exposure, the Laplace approximation and leave-one-out.
tags: [concepts, structure, quenching, inference, fitting]
anchor: concept-quenching-inference
---

(concept-quenching-inference)=
# Quenching inference: stickiness and quench strength from measured lifetimes

{ref}`concept-dye-quenching` explains PET at contact and how QuEst predicts a
lifetime from a structure. This page is the inverse: given measured lifetimes
of one dye at many sites, which stickiness and quench strength explain them,
and how well are they determined. The method is the MalE analysis (three dyes,
AF488, Cy3B and Atto655, nine sites, apo 1OMP and holo 1ANF, 0–100 % D₂O);
its numbers below are from the stored 64-start run.

The data enter at three levels, joined in one graph:

| level | data | gives |
|---|---|---|
| titrations | free dye + free amino acid, $\tau$ vs $[Q]$ | $K_{SV}$, $k_q$ per dye and residue |
| solvent series | each site at several % D₂O | $\tau$ in H₂O and D₂O, $\sigma_\text{meas}$, $k_{q,w}$ |
| site lifetimes | $\tau_X$ per dye, site, apo/holo | stickiness, quench scale, contact offset, ... |

## Stern–Volmer titrations

For collisional quenching of the free dye by an amino acid {cite}`sternvolmer1919`,

$$
\frac{\tau_0}{\tau} = 1 + K_{SV}[Q], \qquad k_q = \frac{K_{SV}}{\tau_0}.
$$

Each titration day $d$ gives a slope $y_d$ with regression error $\mathrm{se}_d$
(a line through $\tau_0/\tau - 1$ vs $[Q]$). Days scatter more than one day's
points suggest, so every slope is modelled as

$$
y_d \sim \mathcal{N}\!\left(K_{SV},\ \mathrm{se}_d^2 + a^2 + (r\,|\hat K|)^2\right),
$$

with a day-to-day error of absolute part $a$ and relative part $r$ **shared by
all titrations**. $\hat K$ is a plug-in size (the weighted mean of the days).
With a flat prior on $K_{SV}$ the Gaussian integral is closed-form: for
$v_d = \mathrm{se}_d^2 + a^2 + (r|\hat K|)^2$,

$$
V = \Big(\sum_d v_d^{-1}\Big)^{-1},\quad m = V\sum_d \frac{y_d}{v_d},\quad
\ln Z = -\tfrac12\sum_d \ln v_d + \tfrac12\ln V - \tfrac12\Big(\sum_d \frac{y_d^2}{v_d} - \frac{m^2}{V}\Big)
- \tfrac{n-1}{2}\ln 2\pi .
$$

$\ln Z$ summed over all titrations is evaluated on a 60 × 60 log-uniform grid
($a$ 0.005–3 M⁻¹, $r$ 0.1–100 %). The posterior of each $K_{SV}$ is the
grid-weighted mixture of the Gaussians $\mathcal N(m, V)$. Nothing is sampled;
"exact" means exact on the grid. MalE: $a$ = 0.01 (0.01–0.03) M⁻¹, $r$ = 2 %
(1–3 %), grid-edge mass < 0.05. Example: AF488 + Trp $K_{SV}$ = 14.44 ± 0.22 M⁻¹,
$k_q$ = 3.51 × 10⁹ M⁻¹ s⁻¹.

A slope can come out negative (Atto655 + Phe −1.28 M⁻¹). Only its positive part
counts as quenching. There is no 2σ significance cut.

## Contact rates per dye

The contact rate table $k_Q$ (textbook values for a xanthene dye, {ref}`concept-dye-quenching`)
is transferred to each dye by its titration ratio to AF488:

$$
k_Q(\text{dye}, q) = k_Q^\text{ref}(q)\,
\frac{\max(K_{\text{dye},q}, 0)/\tau_{0,\text{dye}}}{\max(K_{\text{AF488},q}, 0)/\tau_{0,\text{AF488}}} .
$$

Pro was not titrated and takes the Trp ratio. AF488 is the reference, so its
ratios are exactly 1 and its lifetimes depend on no titration. MalE (ns⁻¹; TRP
TYR MET HIS PRO): AF488 3.50 2.00 1.67 1.00 2.00; Cy3B 4.63 0 0.02 0 2.64;
Atto655 3.03 5.40 0 0 1.73. The protein data may rescale a whole row by one
**quench scale**; the ratios stay those of the titrations, up to the $K_{SV}$
uncertainty, which the graph carries (below).

## Water quenching and lifetime errors

Water quenches some dyes; D₂O does not. Per site, $1/\tau$ is linear in the H₂O
fraction $x$:

$$
\frac1\tau = \frac1{\tau_{D_2O}} + x\,k_{q,w}.
$$

The line gives the site's $\tau$ at $x = 1$ (H₂O) and, for Atto655, extrapolated
to $x = 0$ (D₂O). Its scatter is the measurement error, read from the data:
pooled regression scatter, leave-one-out scatter (exact for a line through the
leverage $h_i$: $r_i/(1-h_i)$), and a robust "typical" value
$1.4826\,\mathrm{median}|\cdot|$. Each site's relative error mixes its own
scatter with the typical one, weighted as two points:

$$
\sigma_\text{rel}^2 = \frac{\sum_i r_i^2 + 2\,\sigma_\text{typ}^2}{n - 2 + 2},\qquad
\sigma_\text{meas}(x_0) = \tau(x_0)\,\sigma_\text{rel}\sqrt{\tfrac1n + \tfrac{(x_0-\bar x)^2}{S_{xx}}} .
$$

Leave-one-out coverage of the 1σ bars is 57 % (AF488), 61 % (Cy3B), 69 % (Atto655),
against 68 % nominal. The free Atto655 gives
$k_{q,w,\text{free}} = 1/\tau_0(\text{H}_2\text{O}) - 1/\tau_0(\text{D}_2\text{O})$ = 0.271 ns⁻¹
(τ₀ 1.846 and 3.69 ns). On MalE, $k_{q,w}$ is 0.16 ns⁻¹ for Atto655 (median)
and near 0 for AF488 and Cy3B, which is why Atto655 is analysed in D₂O first.

## Where the dye sits: three ensembles

The accessible volume (AV, {ref}`concept-accessible-volume`) is computed on a
grid; for the MalE analysis $L$ = 20.4 / 19.74 / 20.12 Å (AF488 / Cy3B / Atto655,
stretched linkers), width 0.5 Å, dye radius 3.5 Å, grid 0.5 Å. These are the
analysis' own settings; the generic AV defaults differ (width 4.5 Å, grid
0.9 Å). Every voxel $x$ carries
$n_g(x)$, the number of residues of chemical group $g$ within 8.5 Å
(aromatic TRP TYR HIS; hydrophobic PHE LEU ILE VAL MET ALA PRO; basic LYS ARG;
acidic ASP GLU; polar SER THR ASN GLN GLY CYS). A group's slow factor
$s_g \le 1$ is its stickiness: smaller is stickier.

QuEst describes the dye's position in three ways. They are not rival
models, but three views of one diffusion problem:

1. **Equilibrium ensemble.** The stationary occupancy
   $$
   p(x) \propto \prod_g s_g^{-n_g(x)},
   $$
   with no motion during the excited state (static limit). This serves the
   static $\tau_X$ / QY of a site and the inverse fit. It is fast, deterministic,
   and does not depend on whether a walk would equilibrate.
2. **Diffusion PDE.** Smoluchowski diffusion on the AV grid with the
   stickiness as a potential ($U/k_BT = -\ln p$) and quenching as a sink,
   $\partial_t n = \nabla\!\cdot\! D\left(\nabla n + n\nabla U/k_BT\right) - k(x)\,n$.
   Its stationary state without the sink is the equilibrium ensemble. With
   the sink it gives the decay including motion during the excited state. It
   is the fix for the walk's sticky-regime defect, solved by IMP.bff's grid
   diffusion solver (example 05 uses the same solver for the 1-D
   Haas–Steinberg equation).
3. **Brownian walk.** A stochastic realisation of the PDE (trajectories plus
   a photon race). This is the straightforward path for FRET, where donor and
   acceptor dynamics and the per-frame transfer rate matter
   ({ref}`concept-dye-quenching`). Each walker starts from $p(x)$, so every
   frame is already an equilibrium sample and nothing has to equilibrate. A
   walker started on a uniform voxel does not reach the sticky voxels within a
   run at slow factors ≤ 0.1, and its decay then reports where it began
   (example 04 shows 50 Å vs 58 Å for a T4L pair with that start).

The walk's slow factor scales the local mobility, and its equilibrium is
$p \propto 1/D$ (the Itô flux form $D_ip_i - D_jp_j$), so a friction field acts
as the attraction $p \propto 1/s$ that the equilibrium ensemble writes down
directly. The PDE keeps the mobility $D_0\prod s^{n}$ and the weight
$w = \prod s^{-n}$ as separate inputs (a detailed-balance flux), so its
stationary state is $w$ exactly.

**The three, measured** (QuEst forward simulator, MalE APO site 95, AF488
reference $k_Q$ table, one slow factor $s$ for every residue, τ₀ = 4.2 ns,
$D_0$ = 7 Å²/ns, grid 0.9 Å; `test/test_equilibrium_ensemble.py`):

| $s$ | equilibrium (static) | PDE | walk from $p(x)$ | fast exchange |
|---|---|---|---|---|
| 1 | 4.084 ns | 3.637 ns | 3.638 ± 0.007 ns | 3.335 ns |
| 0.3 | 2.872 ns | 2.494 ns | 2.487 ± 0.014 ns | 1.057 ns |
| 0.1 | 0.897 ns | 0.890 ns | 0.876 ± 0.008 ns | 0.500 ns |

The walk (3 seeds, template run: 8 × 16 µs at 32 ps) agrees with the PDE at $s$ = 1 and 0.3 and is 1.6 % (1.9σ) low at 0.1; the
equilibrium value is longer because it leaves out transport into contact during
the excited state, and the two meet as the dye stops moving (at $s$ = 0.1 the
mobility $D_0 s^{n}$ is nearly zero). The walk started on a uniform voxel gave
2.18 ns at $s$ = 0.1, the defect the $p(x)$ start removes. In the site-table
geometry (APO 233, $s$ = 0.3, $L$ = 21.5 Å) the direct (static) value is
2.832 ns and the walk 2.76 ± 0.10 ns (the notebook's 2.59 ns was a voxel-frame
error).

## The site model

Per voxel, with quench scale $\kappa$, contact offset $\delta$, rotamer weight
$\lambda$, static strength $\gamma$ and its offset $\delta_s$:

$$
k(x) = \kappa\sum_q k_Q(q)\,c_q(x;\delta,\lambda) + w\,k_{q,w,\text{free}}\,e(x),
\qquad
\tau(x) = \Big[\frac{1}{\tau_0 + \Delta\tau_\text{shield}(1-e(x))} + k(x)\Big]^{-1}.
$$

- $c_q(x;\delta,\lambda) = (1-\lambda)\,c_q^\text{crystal} + \lambda\,c_q^\text{rotamer}$
  counts quencher centres (redox-active atoms) within $R_q + \delta$. The site
  table holds these counts at $\delta \in \{-4,\dots,+5\}$ Å; between them
  ChiSurf reads them with the uniform cubic B-spline that has the tabulated
  counts as control points:
  $c(\delta) = \sum_k C_k\,B_3(\delta - \delta_k)$. The curve is twice
  differentiable, never negative, and grows with $\delta$. At a tabulated
  offset it is the 1–4–1 mean of three neighbours, a smoothing of about one
  grid step. The MalE prototype interpolated linearly. That puts a kink at
  every offset, and the fit stopped on them (δ = −1.0 exactly). A monotone
  cubic (PCHIP) was tried and dropped: it needs zero slope at an offset next to
  a flat stretch, so τ(δ) became a staircase with nearly flat steps at every
  offset. Rotamer centres are weighted by probability.
- $w$ = 1 on the Atto655 H₂O rows of Stage C, else 0 (AF488 and Cy3B neglect
  water quenching, D₂O has none). The water term
  has **no free parameter**: a position half covered by protein ($e$ = 0.5) is
  quenched by water half as much as the free dye.
- $\Delta\tau_\text{shield}$ (Cy3B and Atto655 only, 0–2 ns): these dyes live
  longer on MalE than free (Cy3B up to 2.94 vs 2.39 ns). Quenching cannot do
  that, so a shielded position is allowed a longer τ₀. τ₀ itself stays the free
  dye's.

Visibility and the observable:

$$
v(x) = \frac{1}{1 + (\tau_\text{min}/\tau(x))^4}\;
e^{-\gamma\sum_q k_Q(q)\,c_q(x;\delta_s,\lambda)}, \qquad
\tau_X = \frac{\sum_x p\,v\,\tau}{\sum_x p\,v},
$$

with $\tau_\text{min}$ = 0.10 ns. A position decaying faster than the instrument
resolves, or held in a dark complex (the static channel), emits no light the
lifetime can see. It lowers the brightness instead: dark fraction
$1 - \sum p\,v$. The visible water exposure is $\sum p\,v\,e / \sum p\,v$.
Voxels identical in all features ($n_g$, $c_q$, $e$) are merged with their
count, which makes the model about 15× faster without changing it.

**Water exposure.** $e(x)$ is the Shrake–Rupley fraction {cite}`shrake1973` of a
dye sphere at $x$ that water can reach: 64 golden-spiral points on a sphere of
radius $R_\text{dye}$ + 1.4 = 4.9 Å, a point blocked when closer to any protein
atom than its radius + 1.4 Å (C 1.70, N 1.55, O 1.52, S 1.80 Å). It treats the
dye as a ball, ignores its own linker, and uses the rigid crystal structure
({ref}`concept-molecular-surfaces`). Almost every reachable position has
$e \approx 1$; the exposure that matters is the one weighted by $p\,v$, which
depends on the fitted stickiness.

**Rotamers.** Quencher side chains (TRP, TYR, HIS, MET) are rebuilt from the
backbone-dependent rotamer library (Dunbrack;
[10.1016/j.str.2011.03.019](https://doi.org/10.1016/j.str.2011.03.019), in the
copy distributed with FASPR,
[10.1093/bioinformatics/btaa234](https://doi.org/10.1093/bioinformatics/btaa234))
at the residue's φ/ψ (−60°/−45° at chain ends). χ1 and χ2 are set by rotation,
rotamers with a side-chain heavy atom closer than 2.8 Å to any other heavy atom
are dropped, and the rest are renormalised. With none left the crystal centre
is used. PRO stays at its crystal position. The labelled residue is cut to
backbone + Cβ.

## Priors and parameters

Parameters per dye: $\ln s_\text{common}$, $\ln s_g$ (five groups),
$\ln\kappa$, $\delta$, $\lambda$, $\ln\gamma$, $\delta_s$, $\Delta\tau_\text{shield}$,
inside physical bounds ($s$ 0.001–1, κ 0.01–100, δ −4…+5 Å (the tabulated
offsets), γ 0.001–100, δ_s −4…0 Å). The stored run used κ ≤ 10, δ −3…+2 Å,
γ ≤ 10 and δ_s ≥ −3 Å. Those bounds bind on the corrected grid frame (see the
refit below), so ChiSurf widened them to what the tables support.
Parameters these data cannot determine are fixed: λ = 1 for Cy3B and Atto655,
no static channel for AF488 and Cy3B.

The **ridge prior** keeps each group near the dye's common stickiness:

$$
\frac{\ln s_g - \ln s_\text{common}}{\ln 10} \sim \mathcal N(0, 1).
$$

$s_\text{common}$ enters only here, as the centre the groups shrink to. It does
not act on the lifetime itself.

## The Bayesian graph and its solution

The likelihood links the titration slopes $K$ (through $k_Q$) to every
predicted $\tau_X$, so Cy3B and Atto655 depend on the AF488 titrations
({ref}`concept-factor-graphs`). MalE: 3 blocks (AF488 H₂O, Cy3B H₂O, Atto655
D₂O + H₂O), 41 parameters, 12 titration slopes. IMP.bff's `InferenceFactorGraph`
describes it as 48 variables, 20 likelihoods, 3 priors, treewidth 18, in two
components (AF488 alone; Atto655 + Cy3B through 17 slopes). That description
includes the titration factors with $a$, $r$. The fit itself holds those at
their grid posterior and enters each $K$ as a Gaussian prior
$\mathcal N(K_\text{mean}, K_\text{sd})$.

1. **Search per block.** 64 L-BFGS-B starts (8 in the quick preset; the
   prototype's prose says 16, its code runs 64), uniform in the bounds, on a
   Student-t likelihood ($\nu$ = 3) with the model error $s$ free, plus the
   ridge. A site the model cannot explain cannot drag the search. Declared
   starts (the stored run's best fits) are searched as well. The landscape has
   narrow basins, so which optimum 64 random starts reach depends on the
   optimiser: with IMP.bff's L-BFGS-B the stored seeds miss the stored
   Cy3B and Stage B basins (Cy3B best log posterior 25.0 against 32.4 at the
   stored point).
2. **Model error.** The measurement error alone is too small for a model with
   grid and side-chain approximations. $s$ solves
   $$
   \operatorname{median}_i \frac{r_i^2}{\sigma_{\text{meas},i}^2 + s^2} = 0.455 ,
   $$
   the median of $\chi^2_1$, with a floor of 0.05 ns. Lifetimes with
   $|r_i|/\sigma_i > 3$ are outliers; $s$ is then recomputed without them.
3. **Joint fit.** All blocks and all $K$ together, Gaussian likelihood,
   outliers left out, as a bounded least-squares problem in scaled
   coordinates $u \in [0,1]$ (0 = lower, 1 = upper bound of each parameter).
   The full preset runs MINPACK first, then a projected Levenberg–Marquardt
   polish in the box. The quick preset runs the polish alone. The polish
   evaluates its Jacobian in worker processes that stay alive for the whole
   fit, and quick also polishes the profile-likelihood points. That takes the
   shipped MalE quick run from 1277 s to 685 s on 6 workers. The 9 searches per
   block are now most of the time.
4. **Laplace.** The covariance in $u$ is the Gauss–Newton inverse of
   $J^\top J$ with eigenvalues clipped: a direction whose variance would
   exceed 0.25 (half the range as one sd) gets 0.25. Intervals are
   $u \pm \sigma_u$ mapped back through the bounds and, for $\ln$ parameters,
   through $\exp$, so they are asymmetric. A prediction's error is
   $\sqrt{j_p^\top C j_p}$; any derived quantity is propagated the same way.
   An interval over more than 60 % of its range is reported as "not
   determined"; a best fit within 2 % of a bound as "at the edge".

The Laplace intervals hold to the extent the posterior is Gaussian in $u$. An
optional check samples the same local posterior with IMP.bff's stretch-move
sampler ({ref}`concept-parameter-uncertainty`).

**The prototype's "profile" of the quench scale is not a profile likelihood.**
Its histogram is $\exp$ of draws from the Laplace Gaussian of $\ln\kappa$,
clipped to its bounds, and cannot show more than the Laplace sd already does.
ChiSurf reports both: the Laplace draws, and a real profile likelihood. For the
profile, the block's sub-graph (the block and the slopes it reads) is refitted
at fixed $\kappa$ values, and the 68 % interval is where the deviance
$2(\text{cost}-\text{cost}_\text{min})$ reaches 1.

The joint fit runs MINPACK's Levenberg–Marquardt first. Its bounds transform
can stop a parameter on a bound (Atto655's static strength at 0.001: cost
26.609 against 26.601 at the stored optimum), so a projected
Levenberg–Marquardt polish in the unit box finishes the fit.

## Leave-one-site-out

Leaving out site $j$ (all of its rows: apo, holo, both solvents) moves the
optimum by one Newton step on the curvature, with no refit:

$$
\Delta u = \big(H - J_j^\top J_j\big)^{-1} J_j^\top r_j,\qquad
z = \frac{\hat\tau + j_p^\top\Delta u - \tau}{\sqrt{\sigma_\text{meas}^2 + s^2 + j_p^\top C_{-j}\, j_p}} .
$$

$|z| > 3$ marks a site that the others cannot predict: something
site-specific (a dye–residue complex) that a residue-type model cannot contain.

## Stages

| stage | data | role |
|---|---|---|
| A | AF488, Cy3B in H₂O | stickiness and quench scale where water does not quench |
| B | Atto655 in D₂O alone (own graph: 1 block, 19 parameters, 8 slopes) | same model without water |
| naive test | Stage B fit + $k_{q,w,\text{free}}$ everywhere | predicts H₂O; expected to fail |
| C | Atto655 D₂O + H₂O jointly, $w\,k_{q,w,\text{free}}\,e$ on the H₂O rows | water constrains where the dye sits |

Stage A and Stage C are views of the one graph solved for all three blocks.

The naive test fails because $k_{q,w,\text{free}}$ applied everywhere caps every
H₂O prediction at τ₀(H₂O) = 1.85 ns, while 16 of 18 sites measure longer
(median |dev| 0.48 ns). The protein shields the dye from water.

## MalE results (stored run)

| dye | quench scale κ (68 %) | stickiest group | model error | outlier sites | rms / median \|dev\| |
|---|---|---|---|---|---|
| AF488 H₂O | 6.2 (4.6–8.2) | basic, s = 0.13 | 0.050 ns | 92, 219, 233 | 0.62 / 0.047 ns |
| Cy3B H₂O | 1.1 (0.19–6.7) | polar, s = 0.08 | 0.050 ns | none | 0.02 / 0.010 ns |
| Atto655 D₂O (B) | 0.111 (0.080–0.154) | aromatic, s = 0.001 | 0.065 ns | 211, 219, 322 | 0.63 / 0.061 ns |
| Atto655 D₂O + H₂O (C) | 0.112 (0.080–0.157) | basic, s = 0.003 | 0.108 ns | 322 | 0.52 / 0.094 ns |

What the numbers say, and what they do not:

- **AF488's rms is one site.** Site 233 apo (measured 1.339 ns, LOO $z$ = 15.3)
  makes the rms 0.62 ns while the median deviation is 0.047 ns.
- **Cy3B is barely quenched.** Its lifetimes are explained by τ₀ and the
  shielding term; most of its stickiness values are not determined, and κ
  spans a factor 35.
- **Stage C does not narrow the quench scale.** κ is 0.111 (0.080–0.154) in
  Stage B and 0.112 (0.080–0.157) in Stage C. What adding H₂O changes is the
  stickiness pattern (polar 0.019 → 0.17, aromatic 0.001 → 0.011,
  $\Delta\tau_\text{shield}$ 0.061 → 0.021 ns) and the model error (0.065 →
  0.108 ns): the H₂O data are explained, at the cost of a larger model error.
  The prototype's "key figure" shows two distributions of nearly the same
  width.
- **Atto655's contact offset leans on its bound:** δ = −2.8 Å (B) and −2.6 Å
  (C), both intervals reaching the −3 Å limit. Its static offset is not
  determined.
- **Water access per site is only moderately predicted.** The model gets the
  overall shielding (about half the free dye's exposure, because the dye
  spends its time on the surface) but not which site is more shielded.
- Few sites, many parameters: 9 sites × 2 structures leave several parameters
  not determined. That is a property of the data. Brightness (FCS) data would
  measure the dark fraction directly.

## MalE refit on the corrected geometry

The stored run's site tables came from an older accessible volume, in a grid
frame that was off by up to 0.5 Å. On today's tables (current IMP.bff
accessible volume, corrected frame), the stored parameters fit worse. For
example, AF488's median |dev| rises from 0.047 to 0.165 ns. ChiSurf therefore
refits. On the prototype's own tables, it reproduces the stored optimum
(`test_male_reproduction.py`).

**The frame correction is right.** On today's tables every feature (quencher
contacts, residue counts, water exposure) sits on the voxels of the accessible
volume itself. A brute-force count equals the stamped maps voxel for voxel. The
change from the stored tables is mostly the frame: at the stored parameters,
Atto655 D₂O's median |dev| goes from 0.061 ns (old frame) to 0.203 ns (corrected
frame, same volume) and to 0.242 ns (today's volume). The stored Atto655 fit
sat at δ = −2.8 Å. There a contact is a handful of voxels, so a 0.3 Å
registration shift decides it.

The first refit on these tables put κ and δ on the stored run's bounds. With
the bounds widened and δ read through a B-spline, the quick preset gives (κ, 68 %
Laplace interval):

| data set | stored run (old tables) | refit, `quick` preset | δ (Å) |
|---|---|---|---|
| AF488 H₂O | 6.2 (4.6–8.2), s 0.050, outliers 92 219 233 | 42 (36–49), s 0.154, 211 219 | −1.9 |
| Cy3B H₂O | 1.1 (0.19–6.7), s 0.050, none | 0.070 (0.028–0.18), s 0.050, none | 1.3 (0.9–1.7) |
| Atto655 D₂O (B) | 0.111 (0.080–0.154), s 0.065, 211 219 322 | 9.5 (0.24–100), s 0.128, 322 | −3.1 |
| Atto655 D₂O + H₂O (C) | 0.112 (0.080–0.157), s 0.108, 322 | 38 (7–100), s 0.237, 322 | 4.2 (3.5–4.9) |

**There is no clean interior optimum yet:**

- Only Cy3B has one: its profiles in κ and δ have their minimum inside the
  range.
- AF488's κ profile has its minimum at 32–46 and rises at 100. A second search
  within 2 log-posterior units sits at κ = 0.012, δ = +5: a few strong contacts
  explain the data as well as many weak ones.
- Atto655 in D₂O does not determine κ: the profile deviance stays below 1.5
  from 0.3 to 100. Above about 10, a contact makes the dye dark, and κ only
  rescales the fractional rotamer contacts.
- Stage C's δ profile has its minimum at the +5 Å end of the tables.
- Strong stickiness (s ≈ 0.001) collapses an ensemble onto one voxel. Atto655
  HOLO 72, 92 and 95 all put 99.999 % of the weight on one voxel next to two
  aromatic residues, so which voxels are reachable decides the optimum.

A reparametrisation is proposed in the migration plan but not implemented: fit
κ times the mean contact count at δ, use a distance-continuous rate kernel, and
put a floor on s. The full-preset refit with the widened settings replaces the
one quoted before (κ 10.0 on its old bound for AF488 and Atto655).

The naive H₂O test is unchanged (median |dev| 0.48 ns, 16 of 18 sites above
τ₀(H₂O)). Stage C still does not narrow the scale. Water-access r is 0.49 with
all sites and −0.29 without 322; the stored run did not print it.

## Assumptions

The dye is one sphere on a stretched-linker AV; the protein is one rigid
structure per state (side chains through rotamers only); stickiness is per
residue type and group, additive in $\ln s$; contact quenching is a step at
$R_q + \delta$; the water term assumes quenching proportional to exposed dye
surface; the lifetime model is the static (equilibrium) limit; the linker
models in IMP.bff (C1R/C2R maleimides) are assumed to match the reagents.

## See also

- Guide: {doc}`/guides/111_quenching_analysis` (this analysis on the QuEst Analysis page,
  `csc quest analyse`, the Python API).
- Guide: {doc}`/guides/80_quenching_estimator` (the QuEst tool and its examples).
- {ref}`concept-dye-quenching`: PET at contact and the forward simulation.
- {ref}`concept-accessible-volume`, {ref}`concept-molecular-surfaces`.
- {ref}`concept-factor-graphs`, {ref}`concept-parameter-uncertainty`,
  {ref}`concept-fitting-objectives`.
- Fundamentals: {ref}`fundamentals-quenching-mechanisms` (Stern–Volmer,
  free-partner quenching).
- Code for the titrations, water quenching, lifetime errors and kQ per dye:
  `chisurf/plugins/quenching_estimator/core/inference/` (`titration.py`,
  `lifetime_errors.py`, `kq_scaling.py`); their output tables and the selections
  they make are declared in `settings/analysis/measurement_columns.yaml`.
- Examples: `chisurf/plugins/quenching_estimator/examples/` (01 donor
  quenching, 02 FRET pair, 03 site scan, 04 E(t) → p(R), 05 Haas–Steinberg).

## References

- {cite}`peulen2017`: QuEst, dynamic quenching in time-resolved FRET,
  [10.1021/acs.jpcb.7b03441](https://doi.org/10.1021/acs.jpcb.7b03441).
- {cite}`sternvolmer1919`: the Stern–Volmer relation.
- {cite}`shrake1973`: dot-sampling solvent exposure,
  [10.1016/0022-2836(73)90011-9](https://doi.org/10.1016/0022-2836(73)90011-9).
- Shapovalov & Dunbrack, *Structure* **19**, 844 (2011): the backbone-dependent
  rotamer library,
  [10.1016/j.str.2011.03.019](https://doi.org/10.1016/j.str.2011.03.019).
- Huang, Pearce & Zhang, *Bioinformatics* **36**, 3758 (2020): FASPR, whose
  copy of the library IMP.bff reads,
  [10.1093/bioinformatics/btaa234](https://doi.org/10.1093/bioinformatics/btaa234).
- Tierney & Kadane, *J. Am. Stat. Assoc.* **81**, 82 (1986): Laplace
  approximation of posterior moments,
  [10.1080/01621459.1986.10478240](https://doi.org/10.1080/01621459.1986.10478240).
