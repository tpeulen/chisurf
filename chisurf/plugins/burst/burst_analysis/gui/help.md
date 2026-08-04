# Burst analysis — the whole pipeline in one window

A confocal single-molecule measurement is a long timestamp stream that is mostly
background with occasional bright **bursts** — one molecule crossing the focus.
Everything downstream is a number computed *per burst*, and this window is the
pipeline that produces them, in the order they have to happen.

If you have not run one before, press **Guide** beside this button. It walks the
numbered steps in the left list and says what each one decides.

## Why the steps are numbered

The order is not a suggestion. Each step consumes what the one before it wrote:

1. **Data selection** — the raw TTTR files. Nothing later re-opens anything else.
2. **Burst selection** — the detector channels and the burst search. This is the
   step that decides *what a burst is*; every later number is one row per burst
   found here.
3. **Burst fusion** (optional) — merges bursts the same molecule produced on a
   quick return to the focus. It is the only later step that changes what a burst
   *is*, which is why it sits before everything that measures one.
4.–6. **Burst-level features** — BVA, 2CDE, MLE. One number per burst.
7. **Segmentation (H2MM)** — cuts each burst into segments and gives every photon
   a state.
8. **Segment MLE** — the same fit one level down: one number per burst *and*
   state.

The split at step 7 is the thing to hold on to. Steps 4–6 ask "what was this
molecule doing, on average, while it crossed", step 8 asks "what was it doing in
each part of the crossing". A burst that visited two states has one blurred
lifetime at step 6 and two sharp ones at step 8.

## Where the results go

Every step writes a **burst companion** beside the bursts rather than a file of
its own, and the folder is merged back **column-wise by position** — row *n* of
every companion is burst *n*. That is why an analysis that skips a burst still
writes a row for it, with a sentinel value. A companion with a missing row does
not fail; it silently shifts one burst's results onto another.

You do not have to think about this while using the window — the steps write the
format themselves — but it is why the burst folder is the unit that gets copied,
archived and cited, not any single file inside it.

## The three settings that decide the answer

**The burst-search threshold and window** (step 2). The search slides a window of
*m* photons and opens a burst where the instantaneous rate rises some factor
above the *local* background. Tying it to the local background is what lets it
survive slow drift in laser power over a long acquisition. Search permissively
and impose the real size cut afterwards, on the background-corrected size — a
size cut applied inside the search biases the selection.

**The background** (side panel *Background*, and *IRF & Background*). Every
corrected quantity is a count minus a background, so an error here moves *E* for
the dim bursts and leaves the bright ones alone — which looks exactly like a real
sub-population. Estimate it from the measurement itself, not from a blank.

**The correction factors** (side panel *Accurate FRET*). α, β, γ and δ turn an
apparent *E* into an accurate one. Until they are set, *E* is an instrument
reading and is not comparable with anyone else's.

## Before you believe a burst histogram

1. **Does the burst count change sharply with the threshold?** A stable
   population survives a factor of two; an artefact does not.
2. **Is the donor-only peak where it should be?** It is the one population whose
   answer you know in advance. If it does not sit at *E* ≈ 0 after corrections,
   the corrections are wrong, not the sample.
3. **Does *S* separate the species?** Under ALEX/PIE, singly-labelled molecules
   have to leave the FRET population before anything is interpreted as a
   distance.
4. **Do the dim and bright bursts agree?** If *E* drifts with burst size, look at
   the background before the biophysics.

## Further reading

- [Single-molecule FRET: bursts, E, S and the corrections](docs/concepts/smfret_bursts.md)
- [Accurate FRET — the correction factors](docs/concepts/accurate_fret.md)
- [Burst fusion — when two bursts are one molecule](docs/concepts/burst_fusion.md)
- [Burst variance analysis](docs/concepts/bva.md)
- [Photon-by-photon kinetics (H2MM)](docs/concepts/h2mm.md)
- [Finding bursts, step by step](docs/guides/13_burst_identification.md)
- [Background rates](docs/guides/15_background_rates.md)
- [The end-to-end ALEX workflow](docs/guides/27_alex_smfret_workflow.md)
- [Selecting FRET populations](docs/guides/28_selecting_fret_populations.md)
