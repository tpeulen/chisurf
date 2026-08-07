---
type: Concept
title: 'The photon container: one measurement, one file'
description: A measurement used to be a folder of files related to each other only by being named alike. ChiSurf writes it as one .pto instead — the recording kept verbatim, every result beside it, and every relationship stated rather than implied.
tags: [concepts, data, provenance, container, pto]
anchor: concept-photon-container
---

(concept-photon-container)=
# The photon container: one measurement, one file

A measurement produces one photon stream and, over the following weeks, a
growing pile of things computed from it. The traditional arrangement puts each
of those in a file of its own: a burst search writes `bi4_bur/`, a lifetime fit
writes `bg4/`, `by4/` and `br4/`, a burst-wise correlation writes `td4/`, an
imaging tool writes `<name>.imaging.h5`, and settings, drift trajectories,
resolution curves and molecule tables land wherever each tool happened to put
them.

The arrangement has one property worth naming, because everything else follows
from it: **the files are related to each other only by being named alike.** A
`bg4/m001.bg4` belongs to `bi4_bur/m001.bur` because of the `m001`. Rename the
folder, copy half of it, or send a colleague "the results", and the relationship
is gone — not corrupted, just absent, with nothing to say it ever existed.

ChiSurf writes a measurement as **one file**: `<name>.pto`.

## What is in it

The recording, first and unchanged, and then everything computed from it.

**The instrument file is kept byte-for-byte.** Not converted, not normalised —
the exact bytes your microscope's software wrote. `disassemble` writes them back
out and verifies the SHA-256 while doing it, so "the original is recoverable" is
a checked claim rather than an intention. The photons are read *in place* out of
the container, so a `.pto` is the size of the raw data plus the results, not
twice the raw data.

It is also **immutable**. It is the first object in the file and nothing ever
rewrites it, so no amount of recomputation can disturb the data everything else
depends on.

**Every result says what one of its rows is.** This is the part that a folder of
tables cannot do, and it is worth being concrete about why.

A companion file in the legacy layout is merged onto the burst table *by
position*: row 7 of the lifetime file is burst 7 because it is the seventh row.
That works for exactly one shape — one row per burst — and it fails silently
for anything else, because a table with the wrong number of rows still merges
and simply attributes every value to the wrong burst.

So a result that is **finer** than a burst has nowhere to go. An H2MM dwell
subdivides a burst; a burst holding three dwells cannot be three rows in a table
that must have one. And a result that is **coarser** has nowhere to go either:
a fused burst is made of several source bursts, and there is no way to record
which. In practice both left the format — H2MM's dwells, state decays and
state-annotated photons lived in five files outside the companion system, and
burst fusion wrote its mapping back into *another analysis's* folder.

In a container each table declares its **grain** — what one row is — from a
fixed vocabulary: a photon, a burst, a dwell, a pixel, a frame, a molecule, a
track, a state, a species, a point on a curve. A dwell table says `dwell` and
carries the burst number it belongs to. The join is then a *declared key*, and a
burst the analysis skipped is simply an absent row, which says something true,
instead of a placeholder row, which destroys the information that it was
skipped.

**Every relationship is a statement.** A result records what it was computed
from, with which settings, by which version of ChiSurf, against which revision
of the vocabulary. A fused burst has several parents, and several parents is
what gets recorded — the arity is expressible, where a filename convention's was
not.

**Every column can say what it means.** A duration is milliseconds, a lifetime
is nanoseconds, a distance is ångström, and each column carries its unit rather
than relying on whoever reads it recognising the name. A column with no unit
means the unit is *unknown*, which is a different claim from *dimensionless* and
is written differently.

**The file explains itself.** The first object is plain ASCII describing the
format: that it is EBML (RFC 8794), how an element is framed, which element IDs
matter by number, and how to recover the instrument file. Find it with
`strings measurement.pto | head -40`. A file that needs a specific library
version to be intelligible is a file with an expiry date; this one can be taken
apart by hand.

## Re-running

The identity of a result is the hash of the settings that produced it. Run the
same analysis again with the same settings and it **replaces** the earlier
result in place; change a setting and you get a second result beside the first.

Nothing accumulates, and parameters never have to be encoded in a directory name
— which is what `countrate_All 0.0050#60/` was for.

## What this replaces, and what still works

The legacy layouts are still **read**. They are written when you ask for them:
in Burst Selection, tick **Seidel folder**.

Vendor files still open directly — nothing forces you through the container. But
opening one produces the `.pto`, because that is where the results of working on
it will go.

Your original file is never moved, altered or deleted. Deleting it once it is
inside a container is a decision the container makes *safe*, not one it makes
for you.

## The vocabulary is not ours

The names in a `.pto` — what kind of thing an artifact is, what operation
produced it, what a row is, what a unit is called — are **mmCIF dictionary
items**, from the wwPDB/PDB-IHM family plus the fluorescence extension
(flrCIF) and, where those lack a term, a local extension that declares it.

Nothing in ChiSurf invents a name. A writer that tries to use a term the
dictionaries do not declare fails at write time, rather than producing a file
that cannot be queried. The dictionary revision a file was written against is
recorded in the file, so a later vocabulary change is detectable instead of
silently re-interpreting old data.

## See also

- {doc}`Handling TTTR files </guides/12_handling_tttr_files>` — opening,
  importing and reading photon data in practice.
- {doc}`Burst fusion </concepts/burst_fusion>` and {doc}`H2MM </concepts/h2mm>`
  — the two analyses whose shapes the older format could not hold.
