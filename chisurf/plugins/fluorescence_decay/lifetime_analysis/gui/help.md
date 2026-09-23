# Decay analysis — five tools, one order

A TCSPC decay is a histogram of *how long each photon waited* after its
excitation pulse. Fitting it gives fluorescence lifetimes, and lifetimes are what
make FRET a distance rather than a ratio of intensities. This window holds the
five tools that produce and calibrate them, in the order they depend on each
other.

Press **Guide** for the walk-through.

## Why the order matters

**1. IRF estimation** comes first because the measured decay is not the molecule's
decay — it is the molecule's decay *convolved with the instrument response*. The
IRF is the detector and electronics answering an infinitely short flash. Below
about a nanosecond, what you fit is mostly the IRF, so a wrong one does not
produce a bad fit: it produces a good fit to the wrong lifetime.

**2. MaxEnt (MEM)** asks how many lifetimes there are without you having to say.
A multi-exponential fit needs the number of components declared in advance, and
that choice usually decides the answer. MEM returns a *distribution* and lets the
data say whether it has one peak or three.

**3. Lazy Lifetime Analysis** fits one decay file with a few exponentials and
makes the surrounding choices by rule — fit range, background, IRF shift and,
if asked, the number of components. Its settings live in a file, so the same
rules can be reapplied file after file; check them on a synthetic decay first,
because the automatic component count is not reliable.

**4. Micro-time histograms** build the decay itself out of a raw photon stream —
the step before everything above, when you are starting from TTTR rather than
from an already-binned decay.

**5. VV/VH G-factor** calibrates the polarization channels against each other.
Anisotropy is a *ratio* of two detectors, so their unequal efficiency enters it
directly. Without *G*, an anisotropy is an instrument reading.

## The three things that decide the answer

**The IRF, and its timing.** A shift of a single TCSPC channel between the IRF
and the decay propagates straight into the short lifetime. If a fitted lifetime
moves when you shift the IRF by one channel, the shift is a parameter of the
measurement and has to be treated as one.

**The background.** Scattered excitation light arrives at the same time as the
IRF and looks exactly like a very short lifetime component. A decay with
unaccounted scatter grows a fast component that is not the sample.

**How many components you allowed.** A three-exponential fit will always beat a
two-exponential one. The question is never "does it fit better" but "does the
extra component survive a change of starting values, and does it appear in MEM
without being asked for".

## Before you believe a lifetime

1. **Look at the weighted residuals, not χ².** A χ² near 1 with structured
   residuals means the model is wrong in a way the single number hid.
2. **Refit from different starting values.** Multi-exponential fits have shallow,
   correlated minima; a component that moves a lot is not determined.
3. **Does MEM agree?** It reaches the answer without being told the number of
   components. If MEM shows one broad peak where your fit has two sharp
   lifetimes, the two are a parameterization, not a finding.
4. **Check the tail.** The longest lifetime is set by the last decade of counts,
   which is where the statistics are worst and the background matters most.

## Further reading

- [TCSPC and fluorescence lifetimes](docs/concepts/tcspc_lifetime.md)
- [Fluorescence anisotropy](docs/concepts/anisotropy.md)
- [Decay Analysis, Lazy Lifetime Analysis and synthetic decays](docs/guides/76_decay_analysis_tools.md)
- [How many components?](docs/concepts/tcspc_lifetime.md)
- [Lifetime and anisotropy fitting, step by step](docs/guides/10_lifetime_anisotropy_fitting.md)
- [Lifetimes from bursts](docs/guides/21_lifetime_from_bursts.md)
- [nsALEX lifetimes](docs/guides/32_nsalex_lifetime.md)
