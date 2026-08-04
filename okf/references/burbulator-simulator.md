---
type: Reference
title: "Burbulator: the retired single-molecule diffusion simulator"
description: What the Burbulator C++ library (smdif_ov3 / data2spc132_tac) did, how ChiSurf drove it through a ctypes wrapper, and why it was removed once the TTTR library's photon simulator covered the same ground. Records the model, the parameterisation, its two-generator RNG discipline, and the traps in its interface, so nothing is lost by the deletion.
resource: okf/subsystems/compiled-modules.md
tags: [reference, simulation, retired, acquisition, tcspc, smfret, diffusion]
timestamp: '2026-08-04T00:00:00Z'
---

# Burbulator: the retired single-molecule diffusion simulator

Burbulator was ChiSurf's photon simulator before the TTTR library had one. It was
a small C++ library — the Seidel group's `smdif_ov3`, "diffusion of single
molecules + photon statistics, open volume version, 2006" — that lived beside the
acquisition plugin, was compiled by ChiSurf's own `setup.py`, and was reached from
Python through a ctypes wrapper.

It is **gone**. The simulated TCSPC device, the acquisition CLI and everything
else now run on the TTTR library's engine, which does all of the below and a good
deal more (see [driving the photon simulator](simengine-species-encoding.md)).
This page exists so that deleting ~460 lines of wrapper and a dozen C++ files does
not delete the knowledge of what they modelled.

## What it computed

Two entry points, used in sequence.

**`smdif_ov3`** — the simulation proper. Molecules of several species diffuse
through an **open** box (they enter and leave; the count is not conserved, which
is what "open volume" means), are excited by a focus, and emit photons into
detection channels:

| Parameter | Meaning |
|---|---|
| `N_species`, `M[i]` | species count and the initial molecule count of each |
| `D[i]` | diffusion coefficient per species |
| `N_channels`, `q[i][j]` | brightness of species *i* in channel *j* |
| `q_bg[j]` | background rate per channel |
| `k_rad[i][j]` | *i*→*j* rate **scaled by the local intensity** — photo-induced |
| `k_nrad[i][j]` | *i*→*j* spontaneous rate |
| `box_xy`, `box_z` | half-extents of the box |
| `focus_type`, `focus_param[6]` | the excitation profile and its parameters |
| `dt` | diffusion time step |
| `N_ph_max` | photon budget, and the size of every output buffer |

Outputs were flat arrays, one entry per photon: the macro-time window `data_T`,
the arrival time within it `data_t`, the channel `data_N`, and — the reason it
was useful as ground truth — the emitting **species** and emitting **molecule**.

The radiative/non-radiative rate split is the same idea the TTTR library's engine
uses, and the same names; that is not a coincidence, it is the inherited design.

**`data2spc132_tac`** — the encoder. It turned those arrays into Becker & Hickl
SPC-132 records with TAC micro-times, in a layout deliberately compatible with the
C# `BinaryWriter` that the original acquisition software used.

Supporting sources: `focus.cpp` (the excitation profile), `rotdiff.cpp`
(rotational diffusion, i.e. the anisotropy), `smdif_misc.cpp`, and
`mt19937cok.cpp` (Mersenne Twister).

## The two-generator discipline

Burbulator carried **two** independent generators — one for diffusion
(`rmt1seed`) and one for emission (`rmt2seed`) — and threaded their state in and
out of every call so a long run could be continued in batches without a seam.

That separation is worth naming because it survived: the TTTR library's engine
takes `seed_diffusion` and `seed_emission` for the same reason, and ChiSurf now
derives both from one caller seed in
`chisurf.core.fluorescence.simulation.rng.seeds`. Changing where the molecules go
must not change when they emit.

## Traps it had

* **Every output buffer was allocated at `N_ph_max * 2`** and the wrapper
  guessed the molecule-array size as `sum(ceil(M)) * 2 + 50`. Both are the caller
  guessing what the library will need; overrunning either was undefined
  behaviour, not an exception.
* **Short inputs were silently zero-padded** by the wrapper — a `q` with too few
  entries meant a dark species rather than an error.
* **It was a compiled artefact in the source tree.** `setup.py` invoked CMake to
  build `burbulator.dll` / `libburbulator.dylib` / `.so` *into the package
  directory*, and skipped the build when any file matching `*burbulator*` was
  already there. That made "is the library current?" unanswerable from the
  outside, and made the installer carry a platform-specific binary.
* The Python wrapper's import in `simulation_cli` was **unguarded in both
  branches** — the package-relative import and the script-mode fallback both named
  the same missing module — so its absence was an `ImportError` at CLI start
  rather than a missing feature.

## Why it went

`simulation/core/algorithms.py` had already replaced it: the acquisition
simulator's `run` command builds the TTTR library's engine and streams SPC files
through the shared backend, and its own docstring said so. What remained was the
wrapper, its C++ sources, the `setup.py` build step, and an import nothing used.

The engine that replaced it covers the same model — open-volume diffusion,
per-species brightness per channel, radiative and spontaneous rate matrices, a
focus, background, rotational diffusion — and adds what Burbulator never had:
measured PSFs, flow fields, occlusion, scanning, ALEX and PIE, arbitrary
micro-time patterns, and a per-photon state log. It is also tested and documented
in its own repository rather than being a binary this one builds.
