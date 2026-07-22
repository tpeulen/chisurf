---
type: Plugin Group
title: Sample, Spectra & Curation
description: Database and calibration-oriented tools for samples, spectra, PCH analysis, VV/VH files, and AI/provider settings.
resource: chisurf/plugins/
tags: [plugins, mmfdb, spectra, pch, calibration]
timestamp: '2026-07-05T00:00:00Z'
---

This group covers cross-cutting scientific utilities that do not fit cleanly
into one acquisition modality: sample/provenance databases, optical-component
spectra, photon-counting histograms, VV/VH calibration files, and AI/provider
configuration.

| Plugin dir | Display name | What it does |
| --- | --- | --- |
| `sample_database` | Legacy:Sample Database | Retired prerelease MMFDB surface; active work belongs in `core/mmfdb_admin` and canonical `mmfdb.*` services. |
| `spectra_downloader` | Spectra Downloader | Downloads, browses, stages, and pushes fluorophore/filter/dichroic/detector/light-source spectra to MMFDB endpoints. Includes `download/dedupe_spectra.py`, a headless curation utility that assesses spectra quality, merges duplicate probes and highlights borderline duplicates with a Bayesian classifier in a staging DB. |
| `pch` | Spectroscopy:Single-Molecule:PCH | Computes photon-counting histograms from TTTR files and fits multi-species brightness/occupancy models. |
| `vv_vh_g_factor` | Spectroscopy:Fluorescence decay:VV/VH G-Factor Calculator | Calculates detector G-factors from VV/VH-format decay files, with CLI and backend services. |
| `vv_vh_anisotropy` | Spectroscopy:Fluorescence decay:VV/VH Anisotropy Decay | Computes anisotropy decays from VV/VH files, including batch processing. |
| `ai_settings` | Tools:AI Settings | Configures API providers and backends for AI-assisted features. |

`sample_database` is legacy. ChiSurf is prerelease, so compatibility is not required:
ongoing work should converge on MMFDB admin, project-browser, and object-store paths
and remove old `sample_database.*` aliases instead of maintaining duplicate database
frontends. PCH has a clean GUI/CLI/service split (`pch.load_tttr`, `pch.compute`,
`pch.fit`) and is a good reference for keeping numerical code in `api/` with UI in
`gui/`.

See also [MMFDB](/architecture/mmfdb.md), [fluorescence domain](/subsystems/fluorescence-domain.md),
[TTTR tools](/plugins/tttr.md), and [fluorescence decay](/plugins/fluorescence-decay.md).
