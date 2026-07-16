---
type: Reference
title: VV/VH stacked-decay format (historically "jordi")
description: The descriptive name, layout, and API for the stacked polarization-resolved decay format that was historically called the "jordi" format.
resource: chisurf/core/fio/vv_vh.py
tags: [tcspc, polarization, anisotropy, file-format, jordi, vv-vh]
timestamp: '2026-07-16T00:00:00Z'
---

# Purpose

This concept is the single place that records the historic name **"jordi"** so the
term stays discoverable, while the codebase uses the descriptive name **`vv_vh`**
everywhere else. If you are reading old notes, external files, or git history that
say "jordi", they mean exactly the format described here.

# What the format is

A **VV/VH stacked-decay** file is a simple ASCII text file that stores one or more
polarization-resolved TCSPC decay channels **concatenated into a single column**:
the parallel (VV) channel followed by the perpendicular (VH) channel, optionally a
magic-angle (VM) channel. An optional `#`-prefixed footer carries key/value
metadata (`format_version`, `channels`, `g_factor`, …). The two-channel VV/VH stack
is the layout every `fit2x` maximum-likelihood estimator expects (see
[the fitting subsystem](/subsystems/fitting.md) and
[data I/O](/subsystems/data-io.md)).

# Descriptive naming (current)

- **Module:** `chisurf/core/fio/vv_vh.py`
- **API:** `read_vv_vh()`, `write_vv_vh()` (re-exported from `chisurf.core.fio`)
- **Assembly helper:** `chisurf.core.fluorescence.mle.assemble_vv_vh()` — stacks two
  channels into the two-channel VV/VH layout.
- **Reader flag:** `CsvTCSPC.is_vv_vh` (stacked VV/VH files have no header row and
  use the rebin-scaled `dt`).
- **Plugins:** `chisurf.plugins.vv_vh_g_factor` (G-factor via tail-matching,
  CLI `vv-vh-g-factor`, RPC namespace `vv_vh_g_factor.*`) and the deprecated
  `chisurf.plugins.vv_vh_anisotropy`.

# Historic name ("jordi")

"jordi" was an internal/legacy name for this format with no descriptive meaning.
As of 2026-07-16 it was renamed to `vv_vh` across the codebase (module, public API,
plugin ids, RPC method names, CLI entrypoints, state namespaces, display names,
tests, and docs). New code must use the descriptive `vv_vh` name; do not
reintroduce "jordi". Raw sample-data directories under `test/data/tcspc/Jordi*`
keep their original names as provenance and are intentionally not renamed.
