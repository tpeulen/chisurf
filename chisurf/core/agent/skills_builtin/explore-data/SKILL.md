---
name: explore-data
description: >-
  Find out what data exists on disk or in the session and what kind of
  measurement it is, before committing to an analysis. Use when the user asks
  what is in a folder, what is loaded, or opens with a vague "have a look at
  my data".
triggers:
  - what is in
  - what's in
  - look at
  - explore
  - inspect
  - browse
  - available
  - my data
  - which files
  - overview
tools:
  - list_files
  - load_data
  - list_datasets
  - list_experiments
  - describe_session
  - get_curve
---

# Finding out what you are dealing with

Never guess file names, model names or what a measurement contains. Every one
of those is one cheap tool call away, and a wrong guess costs the user real
time.

## The order that works

1. `describe_session` — what is already loaded. If the user says "my data",
   they may mean data that is open, not data on disk.
2. `list_files` on the folder they mention. It reports the size of each file
   and the ChiSurf experiment type guessed from its extension. If a
   non-recursive listing finds only sub-directories, it says so — descend or
   use `recursive`.
3. `list_experiments` — which readers and which **exact** model names exist
   for that experiment type. Model names must match exactly later.
4. `load_data` for the files that matter, then `get_curve` if you need to see
   the numbers.

## Reading the file listing

* Extensions map to experiment types: `.dat`/`.txt`/`.csv`/`.pqres` are
  usually TCSPC decays, `.cor`/`.asc`/`.sin`/`.fcs` are correlation curves,
  `.ptu`/`.ht3`/`.spc` are raw photon streams, `.pdb`/`.cif` are structures.
* A file whose name contains `irf`, `prompt` or `lamp` is an instrument
  response — a reference measurement, not a sample.
* Names carry the experiment design: `D0`/`donly` is donor-only, `DA` is the
  FRET sample, `_ps`/`_ns` are time units, and numbers are often sample or
  position identifiers. Use them to pair samples with their references, and
  say what you assumed.

## Before you report

Say what you found in the user's terms — how many measurements, of what kind,
and which ones look like they belong together — and then propose the analysis
rather than silently starting one. If something is ambiguous (two IRFs, mixed
experiment types in one folder), ask; a wrong pairing invalidates everything
downstream.
