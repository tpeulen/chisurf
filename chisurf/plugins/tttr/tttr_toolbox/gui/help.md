# TTTR Tools — working on the photon stream itself

Every confocal analysis in ChiSurf starts from a **TTTR** file: one record per
detected photon, carrying which detector saw it, when it arrived on the
experiment clock (the *macro time*) and how long after the excitation pulse
(the *micro time*). This window holds the tools that operate on that stream
before any analysis interprets it.

Press **Guide** for the walk-through.

## The two clocks

Almost everything here comes down to keeping the two times straight.

The **macro time** is the coarse, free-running clock — nanoseconds to hours. It
is what bursts, correlation curves and count-rate traces are built from.

The **micro time** is the fine time since the last laser pulse — picoseconds
across one pulse period. It is what lifetimes and TCSPC decays are built from,
and it wraps every pulse period.

A tool that moves a photon in one of them leaves the other untouched, which is
exactly why these operations are safe *and* why they are easy to misread.

## What each tool is for

**ALEX Creator** converts alternating excitation encoded in the *macro* time into
a *micro*-time encoding. That sounds like a formality and is not: PIE pipelines
identify the excitation source from the micro time, so ALEX data cannot run
through them until this is done. Afterwards the same file works with every
PIE-based analysis.

**Micro-time Shifter** applies a global or per-detector offset to the micro time.
Detectors and their cables do not have identical delays, so two channels of the
same measurement can have their IRFs offset by hundreds of picoseconds. Left
uncorrected that offset lands directly in any lifetime fitted across channels.

**Header Editor** reads and edits the metadata tags. Useful when an acquisition
recorded a wrong repetition rate or a missing dead time — values every later
conversion trusts without checking.

**Split / Convert** cuts long acquisitions into segments and moves between
container formats. Splitting is the practical answer to a measurement that
drifted: analyse the segments separately and compare, rather than averaging over
a change you did not intend to include.

**Count Rate Analysis** reports per-detector rates across many files. This is the
fastest possible sanity check on a dataset — a detector that died mid-session, a
sample that photobleached, a file recorded with the shutter closed.

**Audifier** plays the photon stream. Not a joke: bursts, blinking and afterpulsing
have distinct sounds, and some artefacts are easier to notice by ear than in a
plot.

## Before you overwrite anything

1. **These tools write new files; keep the originals.** A micro-time shift is not
   invertible once you have forgotten what it was.
2. **Check the count rates first.** Most problems that look like analysis
   problems are visible here in seconds.
3. **After a shift, re-look at the IRF.** That is the only thing that tells you
   the shift went the way you meant.

## Further reading

- [Handling TTTR files](docs/guides/12_handling_tttr_files.md)
- [Timestamps and bursts](docs/guides/33_timestamps_and_bursts.md)
- [Micro-time linearization (LUTs)](docs/guides/37_tttr_microtime_lut.md)
- [The ALEX / smFRET workflow](docs/guides/27_alex_smfret_workflow.md)
