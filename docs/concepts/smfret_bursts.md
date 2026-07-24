(concept-smfret-bursts)=
# Single-molecule FRET: burst analysis (E, S, corrections)

Confocal single-molecule FRET watches one labelled molecule at a time as it
diffuses through a tiny detection volume. Each transit produces a short, bright
**burst** of photons. Burst analysis finds those bursts and turns each one's
photon counts into two per-molecule numbers: the **FRET efficiency** $E$
(a distance proxy) and, when the acceptor is directly excited, the
**stoichiometry** $S$ (the donor:acceptor labelling ratio). The catch is that the
counts as detected are biased by the optics and the dyes — four **correction
factors** remove those biases so $E$ becomes *accurate* and comparable across
instruments.

This page is the theory. For the step-by-step ChiSurf workflow see the guides
{doc}`/guides/13_burst_identification`, {doc}`/guides/14_multiparameter_es`,
{doc}`/guides/15_background_rates`, and the end-to-end
{doc}`/guides/27_alex_smfret_workflow`.

## Finding bursts

A measurement is a long timestamp stream that is mostly background with
occasional bright bursts. The **sliding-window** search runs a window of $m$
consecutive photons along the stream and computes the instantaneous count rate
($m$ divided by the time those photons span). A burst opens where that rate rises
above a threshold set **relative to the local background** — typically $F\approx6$
times the background rate, with $m\approx10$ — and closes when it falls back. Tying
the threshold to the background (estimated in adjacent time windows, see
{doc}`/guides/15_background_rates`) lets it track slow drift in laser power or
buffer over a long acquisition.

The search can run on **all photons** (most sensitive) or, in ALEX, demand a
coincident rate rise in both excitation streams (dual-channel burst search, which
rejects singly-labelled species early). A found burst is kept only if its total
size exceeds a minimum $L$; best practice is to search permissively ($L=m$) and
impose the real size cut afterward on the background-corrected size, as an
unbiased selection step. See {doc}`/guides/13_burst_identification`.

## The photon channels

Each burst's photons are sorted by **which laser was on** × **which detector**.
The general convention is $I_{ij}$ = photons from chromophore $j$ while
chromophore $i$ is excited. For a two-colour donor/acceptor pair, three counts
matter:

- $I_{dd}$ ("green") — donor emission under donor excitation,
- $I_{da}$ ("red") — acceptor emission under donor excitation (the FRET signal),
- $I_{aa}$ ("yellow") — acceptor emission under acceptor excitation.

Single-laser FRET has only $I_{dd}$ and $I_{da}$. The third channel needs
**alternating excitation** — µs-ALEX (acceptor laser switched on a microsecond
schedule) or **PIE** (pulsed interleaved excitation, separated by the TCSPC
micro-time). $I_{aa}$ is what makes $S$ measurable. See
{doc}`/guides/27_alex_smfret_workflow`.

## Raw observables

With per-channel backgrounds removed ($F_{dd}=I_{dd}-B_{dd}$, …), the two
**apparent** quantities are

$$
E_\text{raw} = \frac{F_{da}}{F_{dd}+F_{da}},
\qquad
S_\text{raw} = \frac{F_{dd}+F_{da}}{F_{dd}+F_{da}+F_{aa}} .
$$

$E_\text{raw}$ is the **proximity ratio** — it tracks distance but its value is
instrument-specific. $S_\text{raw}$ is the fraction of photons from donor
excitation: FRET species sit near $S\approx0.5$, donor-only at $S\to1$,
acceptor-only at $S\to0$.

## The four correction factors

- **Leakage $\alpha$** — donor photons detected in the acceptor channel (spectral
  tail). Measured on a **donor-only** sample as $\alpha=F_{da}/F_{dd}$; a few
  percent.
- **Direct excitation $\delta$** — the donor laser also excites the acceptor
  directly. Measured on an **acceptor-only** sample as $\delta=F_{da}/F_{aa}$.

  Together these give the true FRET-sensitized emission

  $$
  F_A = F_{da} - \alpha\,F_{dd} - \delta\,F_{aa}.
  $$

- **Detection factor $\gamma$** — donor and acceptor photons are not detected
  equally: different channel efficiencies $g_D,g_A$ and dye quantum yields
  $\Phi_D,\Phi_A$,

  $$
  \gamma = \frac{g_A\,\Phi_A}{g_D\,\Phi_D}.
  $$

  It balances a donor photon lost against an acceptor photon gained, giving the
  **accurate efficiency**

  $$
  \boxed{\;E = \frac{F_A}{F_A + \gamma\,F_{dd}}\;}
  $$

- **Excitation factor $\beta$** — the two lasers deliver unequal effective
  excitation (power, overlap, absorption cross-sections),
  $\beta = \dfrac{I_\text{Aex}\,\sigma_A}{I_\text{Dex}\,\sigma_D}$. It rescales
  the acceptor-excited channel in the **accurate stoichiometry**

  $$
  \boxed{\;S = \frac{\gamma F_{dd}+F_A}{\gamma F_{dd}+F_A + F_{aa}/\beta}\;}
  $$

  $\beta$ shifts only $S$; $\gamma$ shifts both.

*Apply the full expression in one step.* Chaining single-factor corrections
(γ-only, then leakage-only, …) is **not** equal to the combined formula — it is
only approximate. See {doc}`/guides/14_multiparameter_es`.

## The E–S histogram and straightening the FRET line

Plotting every burst at its $(E, S)$ gives the 2-D **E–S histogram**. FRET
species form a horizontal band near $S\approx0.5$ (spread along $E$ resolving
conformational states); donor-only contamination sits at $S\to1$, acceptor-only
at $S\to0$. Gating the FRET band removes the singly-labelled corners.

On the *raw* plot the FRET species do **not** lie on a horizontal line —
$S_\text{raw}$ drifts with $E_\text{raw}$ because the detection imbalance changes
the photon budget as FRET moves photons from donor to acceptor. The population
centres follow a straight line

$$
\frac{1}{S_\text{raw}} = \Omega + \Sigma\,E_\text{raw},
$$

and fitting it across several FRET standards recovers the factors from the data,

$$
\gamma = \frac{\Omega-1}{\Omega+\Sigma-1},
\qquad
\beta = \Omega + \Sigma - 1
$$

(Lee 2005 / Hellenkamp 2018). Applying $\gamma$ and $\beta$ **straightens the
FRET line**: every species falls on the same horizontal $S\approx0.5$, and $E$ is
now accurate. It then maps to distance through Förster,
$E = 1/[1+(R/R_0)^6]$, i.e. $R = R_0\,(1/E - 1)^{1/6}$.

## See also

- Guides: {doc}`/guides/13_burst_identification` · {doc}`/guides/14_multiparameter_es`
  · {doc}`/guides/15_background_rates` · {doc}`/guides/27_alex_smfret_workflow`.
- Implementation: per-burst E/S `chisurf/core/fluorescence/burst/es.py`;
  correction algebra `chisurf/core/fluorescence/crosstalk.py`; calibration
  factors `chisurf/core/fluorescence/fret/calibration.py`; burst search &
  background `chisurf/core/fluorescence/burst/`; burst plugins
  `chisurf/plugins/burst/`.
