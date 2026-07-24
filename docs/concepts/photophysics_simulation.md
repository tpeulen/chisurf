(concept-photophysics-simulation)=
# Simulating single-molecule photon streams

Every analysis in ChiSurf — an FCS correlation curve, a burst-wise FRET
histogram, a photon-by-photon hidden-Markov fit — is an *inverse* problem: it
infers hidden parameters (diffusion coefficients, brightnesses, FRET
efficiencies, transition rates) from a noisy photon record. The only rigorous way
to know that such an inference is correct is to run it on data whose answer you
already know. A **forward simulator** builds that ground truth: it generates a
realistic TTTR photon stream from an explicit physical model, so you can push the
simulated stream through the *same* pipeline you use on measurements and check
that the recovered parameters match the inputs.

This page explains what goes into a single-molecule photon simulation, how the
pieces map onto the physics of a confocal experiment, and why the resulting
stream can be correlated, burst-searched or Markov-fit exactly like real data.
For the workflows see {doc}`/guides/18_tttr_simulation` and
{doc}`/guides/31_h2mm_simulation_validation`.

## Why simulate

- **Validation.** Confirm that an FCS model recovers the diffusion time you put
  in, that a burst pipeline recovers the FRET efficiencies of your states, that
  H2MM selects the right number of states and the right transition rates.
- **Uncertainty & bias.** Repeat a simulation over seeds or bootstrap the bursts
  to turn "the fit returned $E=0.42$" into "$E=0.42\pm0.03$", and to expose
  systematic bias (e.g. a $\gamma$-distorted proximity ratio) that a single fit
  cannot reveal.
- **Teaching & method design.** A dial-a-parameter photon source is the fastest
  way to build intuition for how brightness, background, or a fast blinking
  process reshapes a correlation curve or a burst histogram.

## The ingredients

A confocal single-molecule simulator (ChiSurf drives `tttrlib.SimEngine`)
assembles the photon record from a small set of independent physical factors —
the same factorization that the forward *fit* models undo.

### 1 · Brownian trajectories

Each molecule performs a free 3-D random walk in a simulation box. Over a fixed
integration step $\Delta t$ its displacement is an isotropic Gaussian whose
variance is set by the translational diffusion coefficient $D$; the mean-squared
displacement grows linearly with time,

$$
\langle |\mathbf{r}(t+\tau)-\mathbf{r}(t)|^2\rangle = 6D\,\tau .
$$

Trajectories are built by cumulatively summing independent Gaussian steps
$\Delta\mathbf{r}\sim\mathcal{N}(0,\,2D\,\Delta t)$ per axis. At the box faces
molecules are reflected or re-injected from the opposite face (a
mirror/periodic boundary) so the mean occupancy stays constant. The occupancy
itself — the mean number $N$ of molecules in the box — sets the amplitude of the
fluctuations, exactly the $1/N$ that FCS reports as a concentration
(see {ref}`concept-fcs-correlation`).

### 2 · The detection / excitation profile

The confocal spot is a **molecule detection function** (MDF): the position-
dependent probability that an emitted photon is both excited and collected. It is
well approximated by a 3-D Gaussian centred on the origin, with lateral $1/e^2$
half-axis $w_{xy}$ and axial $w_z$,

$$
W(\mathbf{r}) = \exp\!\left(-\,\frac{2(x^2+y^2)}{w_{xy}^2}
                              -\,\frac{2 z^2}{w_z^2}\right),
$$

so the aspect ratio $\gamma=w_z/w_{xy}$ is the structure parameter that also
appears in the FCS diffusion model. A more faithful, numerically pre-computed
vectorial-PSF can be substituted for the Gaussian when the exact focus shape
matters, but the Gaussian is the natural match to the analytic FCS models.

### 3 · Position-dependent brightness and Poisson emission

As a molecule of species $s$ threads the spot, its instantaneous emission rate is
its peak molecular brightness $q_s$ (counts per second at the focus centre)
scaled by the local profile,

$$
\lambda_s(\mathbf{r}) = q_s\,W(\mathbf{r}).
$$

Because photon emission is a shot-noise process, the count in each time bin is a
**Poisson** draw with that mean,

$$
P(k\ \text{photons in}\ \Delta t) =
   \frac{(\lambda\,\Delta t)^k}{k!}\,e^{-\lambda\,\Delta t}.
$$

The time bin in which a photon is drawn becomes its macro-time stamp. Brightness
is what separates a real molecular transit from noise; the brightness *contrast*
between species is what lets FCS and burst analysis tell them apart.

### 4 · FRET partitioning between colour channels

For a FRET pair, the same transit is split across detectors. Encoding a state's
FRET efficiency $E$ as per-channel brightness,

$$
q_\text{green} = (1-E)\,q,\qquad q_\text{red} = \gamma_\text{det}\,E\,q,
$$

reproduces the anti-correlated donor/acceptor intensities of a real experiment;
the detection/quantum-yield ratio $\gamma_\text{det}$ can be baked in so that the
*uncorrected* proximity ratio is deliberately distorted and the calibration step
of the analysis has something real to recover. Leakage (spectral crosstalk) and
direct acceptor excitation are added the same way, as fixed fractions routed to
the "wrong" channel.

### 5 · Background and detector effects

- **Background** — a constant, molecule-independent Poisson process per channel
  (sample Raman/scatter plus detector dark counts) adds uncorrelated photons that
  dilute every FCS amplitude by $(1-B/I)^2$ and broaden burst histograms.
- **Micro-time / IRF** — each photon carries a TCSPC micro-time drawn from the
  emitting species' fluorescence-decay pattern (a mono- or multi-exponential of
  lifetime $\tau$), optionally convolved with an instrument response function.
  This is the axis that filtered-FCS and lifetime analyses read.
- **Detector artefacts** — dead time (a refractory gap after each count) and
  afterpulsing (a spurious correlated count) can be layered on to reproduce the
  short-lag distortions that real hardware imprints.

### 6 · State kinetics (a Markov process modulating E)

Conformational or photophysical dynamics are a continuous-time **Markov process**
over discrete states, each state carrying its own FRET efficiency (or brightness,
or lifetime). Off-diagonal rates $k_{ij}$ in the rate matrix drive spontaneous
$i\!\to\!j$ interconversion while a molecule diffuses, so a single transit can
switch states mid-burst — precisely the signal that dynamic-FCS relaxation terms
and H2MM ({ref}`concept-h2mm`) are built to detect. Setting all rates to zero
recovers static, independent species.

## From ingredients to a TTTR record

Running the engine interleaves all species and the background into one
time-ordered event list and encodes it as a real TTTR container (PTU/HT3/SPC), or
returns the native arrays directly:

- **macro-time** — the absolute arrival time (window index × step + within-window
  offset), the axis correlation and burst-search operate on;
- **micro-time** — the TCSPC/TAC channel, i.e. the lifetime axis;
- **channel** — the detector/colour routing;
- a ground-truth **species/state label** per photon (available in simulation
  only) that lets a recovered assignment be scored against the truth.

## Closing the loop

The essential property is that a simulated stream is **indistinguishable in form**
from a measured one: it is just macro-times, micro-times and channels. Nothing in
the correlator, the burst search, the FRET-histogram builder or the H2MM fitter
knows or cares that the photons were generated rather than detected. So the
simulated stream **correlates, bursts and Markov-fits exactly like real data** —
which is what makes it a valid test of the forward models. Put a diffusion time
in, get the same diffusion time back out of the FCS fit; put two FRET states and
an exchange rate in, watch the burst pipeline and H2MM recover them. When the
recovered numbers match the inputs across seeds, the analysis is trustworthy; when
they don't, the simulator has isolated the bias before it reaches real data.

## See also

- Guides: {doc}`/guides/18_tttr_simulation` (diffusing particles → TTTR) ·
  {doc}`/guides/31_h2mm_simulation_validation` (validating state recovery).
- Concepts: {ref}`concept-fcs-correlation` (the correlation curve the simulated
  stream must reproduce) · {ref}`concept-h2mm` (photon-by-photon HMM validated on
  simulated states).
- Engine & wrappers: `tttrlib.SimEngine` (the confocal Brownian/Poisson
  simulator); `chisurf/core/fluorescence/fcs/simulate.py` (lifetime-FCS wrapper);
  the burst-workflow `simulate()` in
  `chisurf/plugins/burst/burst_analysis/api/workflow.py`; the interactive
  lifetime-FCS simulator plugin `chisurf/plugins/fcs/fcs_lfcs_sim/`.
- Literature: Wohland, Rigler & Vogel, *Biophys. J.* **80**, 2987 (2001), the
  standard treatment of noise in FCS by Brownian-dynamics simulation;
  Ingargiola et al., *PLoS ONE* **11**, e0160716 (2016), the PyBroMo/FRETBursts
  confocal smFRET diffusion simulator; Gopich & Szabo, *J. Phys. Chem. B* **113**,
  10965 (2009), photon-by-photon FRET-trajectory theory underlying H2MM.
