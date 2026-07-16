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

# Diagnosing errors that mention "jordi"

Any error naming a `jordi*` symbol is almost always this rename. Map the old name
to the new one and, for persisted data, migrate the key or accept the default:

| Old name (error surface) | New name | Where it bites |
| --- | --- | --- |
| `read_jordi` / `write_jordi` / `assemble_jordi` (`ImportError`/`AttributeError`) | `read_vv_vh` / `write_vv_vh` / `assemble_vv_vh` | macros, notebooks, external scripts |
| module `chisurf.core.fio.jordi`; packages `chisurf.plugins.jordi_g_factor` / `jordi_anisotropy` | `…fio.vv_vh`; `…plugins.vv_vh_g_factor` / `vv_vh_anisotropy` | imports |
| RPC `jordi_g_factor.calculate` etc. ("unknown method") | `vv_vh_g_factor.*` | client/macro calls |
| CLI `jordi-g-factor` ("command not found") | `vv-vh-g-factor` | shell / gui-scripts |
| serialized key `"is_jordi"` in saved DataCurve/project JSON | `"is_vv_vh"` | old `.json` projects load with the flag silently defaulted, not applied |
| plugin `state_namespace` / settings key `jordi_g_factor`; help anchor `tcspc-jordi` | `vv_vh_g_factor`; `tcspc-vv_vh` | previously-saved GUI window state won't restore |

For old serialized state (`"is_jordi"`, `jordi_g_factor` state keys), either rewrite
the key to its `vv_vh` form or accept that the value falls back to its default —
the runtime no longer reads the `jordi` key.
