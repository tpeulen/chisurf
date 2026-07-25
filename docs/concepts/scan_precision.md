(concept-scan-precision)=
# Scan precision: choosing a dwell time before you measure

A raster-scan correlation measurement (RICS and its relatives) has a free
parameter that nobody can set from first principles at the microscope: the
**pixel dwell time**. It is not a quality knob where more is better. Scan too
fast and the measurement carries almost no information about $D$; scan too
slowly and it carries almost none either, for a different reason. Between the
two there is an optimum, and where it sits depends on the answer you do not have
yet.

This page is about why that optimum exists and how far it can be predicted in
advance. For the analysis it plans, see {ref}`concept-image-correlation`; for
the workflow, {doc}`the scan-precision guide </guides/45_scan_precision>`.

## Where the information about $D$ actually lives

A raster scan writes time into space. The pixel at fast-axis lag $\xi$ and
slow-axis lag $\psi$ from a reference pixel was recorded at a delay

$$\tau(\xi, \psi, \Delta) = |\xi\, t_\mathrm{p} + \psi\, t_\mathrm{l} + \Delta\, t_\mathrm{f}|,$$

with $t_\mathrm{p}$, $t_\mathrm{l}$ and $t_\mathrm{f}$ the pixel, line and frame
times. The correlation carpet $G(\xi, \psi, \Delta)$ is therefore a correlation
*in time*, sampled on a grid whose spacing is set entirely by the scanner. This
is the identity that makes RICS, STICS, TICS and iMSD one method
({ref}`concept-image-correlation`), and it is also what makes the dwell time a
physics parameter rather than a convenience.

The fit learns $D$ from how quickly $G$ falls along that axis. The molecule's
own clock is the diffusion time across the focus,

$$\tau_D = \frac{w_r^2}{4D},$$

so what matters is not $t_\mathrm{p}$ in absolute terms but $t_\mathrm{p}$
measured against $\tau_D$ — and, because the fit uses a finite number of lags
$n$, the window $n\, t_\mathrm{p}$ that the fast axis actually spans.

**Too fast** ($n\,t_\mathrm{p} \ll \tau_D$). Every fitted lag sits on the flat
top of the decay. The values of $G$ do change with $D$, but only in the fourth
decimal; the derivative $\partial G/\partial D$ over the fitted window is nearly
zero, so ordinary shot noise maps onto an enormous spread in the fitted $D$.
Nothing is wrong with the data — it simply does not contain the answer.

**Too slow** ($t_\mathrm{p} \gg \tau_D$). The molecule has fully decorrelated
before the neighbouring pixel is read. Every fitted lag sits in the floor, and
the derivative vanishes again.

**In between**, the fitted window straddles the decay, $\partial G/\partial D$
is large, and the same shot noise costs far less precision. That is the minimum
the planner looks for.

Two secondary effects shift it from the naive $t_\mathrm{p} \approx \tau_D / n$:

* **Photons.** A longer dwell collects $\varepsilon t_\mathrm{p}$ photons per
  molecule per pixel, so the correlation itself is less noisy. This pushes the
  optimum later than the pure-information argument would.
* **Correlated noise.** Correlation values at different lags are built from the
  same pixels and are *not* independent. The estimator's covariance is a full
  matrix; treating it as a set of per-lag variances understates the error
  substantially.

## What the predictor computes

The prediction follows Sanguigno et al.'s analysis of RICS estimator noise, in
three steps:

1. **Covariance.** The covariance of the correlation estimator over the fitted
   lag range is computed analytically — a shot-noise term involving the
   three-point correlation on the diagonal, plus terms that sum products of
   two-point correlations over every pixel pair, weighted by how many pairs
   share each separation.
2. **Realisations.** Noise is drawn from that covariance, added to the noiseless
   correlation, and the result is fitted for $D$ exactly as a measurement would
   be.
3. **Spread.** The scatter of the fitted values across many realisations gives
   the mean squared relative error.

Reading a single number off this is straightforward: below about 5 % relative
error the acquisition is good, 5–20 % usable, above 50 % not worth recording.

### Agreement with the reference implementation

This is a port of an established implementation, and it is checked against it
numerically: the shape factors, the dwell-time brightness correction, the ideal
correlation grid and **every entry of the estimator covariance** agree with the
reference to about $5\times10^{-13}$ — double precision.

One kernel deviates on purpose. The reference's three-point correlation
converts its lag vectors to microns before forming the time lag, so its $\tau$
carries a factor of the pixel size; the two-point function built a few lines
away in the same reference file does not. The two therefore disagree about what
$\tau$ means, and the consequence is visible in a limit: shrink the pixel size
at a fixed line lag and the reference's three-point correlation tends to 1, so
two time points many diffusion times apart would correlate perfectly. ChiSurf
forms $\tau$ from the raw lag. The difference moves the predicted error by well
under its own Monte-Carlo uncertainty and does not change which dwell time is
recommended.

## The honest caveats

**The prediction is itself a Monte-Carlo quantity.** With $N$ realisations it
carries a relative uncertainty of roughly $1/\sqrt{2N}$ — about 10 % at the
default 40. The consequence matters: **the position of the minimum is not
resolved to one step of a dwell scan**. Along a flat stretch the argmin moves
between neighbouring points from noise alone. Read the optimum as an order of
magnitude, compare error *values* rather than trusting an argmin, or raise the
repeat count.

**It needs the answer to predict how well you can measure it.** $D$ enters the
prediction. In practice this is less circular than it sounds — a literature
value or an order-of-magnitude guess is enough, because the optimum moves
logarithmically — but it does mean the sensible use is to try a plausible range
of $D$ and check that your chosen dwell is tolerable across all of it, rather
than optimising against one guessed number.

**Precision is quoted per frame count, not per unit time.** The frame count is
held fixed while the dwell is swept, so a slower scan in the comparison is also
a *longer* acquisition. A dwell time that predicts 3 % error in 100 frames of
40 ms each is not obviously better than one predicting 4 % in 100 frames of
10 ms. This is why the planner reports the implied frame time next to each
error: the trade-off against total acquisition time is yours to make, and the
tool deliberately does not make it for you.

**The model is pure diffusion.** One freely diffusing species in a Gaussian
focus. No triplet blinking, no immobile fraction, no photobleaching, no flow.
Each of those degrades a real measurement further, so a prediction should be
read as a bound on what the acquisition can do, not a promise.

**Precision is not accuracy.** Everything here is about scatter. A wrong beam
waist, an uncorrected drift ({ref}`concept-drift-correction`) or an unmodelled
immobile fraction produce a *bias*, which this analysis says nothing about and
which no amount of averaging removes.

## Practical consequences

* The dwell time should bracket $\tau_D$ over the fitted lag window. Fast
  samples (free dye, $D \sim 100\ \mu\mathrm{m^2/s}$) want microseconds; slow
  ones (membrane proteins, $D < 1$) want tens to hundreds.
* One dwell time cannot serve two species that differ by orders of magnitude in
  $D$. If you need both, that is an argument for two acquisitions, not a
  compromise setting — and the planner shows the cost of the compromise
  directly.
* Brightness is the dominant lever after frame count. A dim label cannot be
  rescued by scanning cleverly.
* Precision improves as the square root of the frame count: halving the error
  costs four times the acquisition.

## References

* Sanguigno, L., De Santo, I., Causa, F., Netti, P. *A closed form for
  fluorescence correlation spectroscopy experiments in submicrometer
  structures.* Analytical Chemistry **82**, 9663–9670 (2010).
* Digman, M. A., Brown, C. M., Sengupta, P., Wiseman, P. W., Horwitz, A. R.,
  Gratton, E. *Measuring fast dynamics in solutions and cells with a laser
  scanning microscope.* Biophysical Journal **89**, 1317–1327 (2005).
