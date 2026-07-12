---
type: PRD
prd: "33"
title: "PRD-33: Acquisition-to-MMFDB Registration"
description: Adds a save mode that writes a newly acquired measurement directly into MMFDB with sample linkage and provenance.
status: planned
phase: "cross-cutting"
resource: chisurf/plugins/core/acq
tags: [prd, acquisition, mmfdb]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
Offers a second acquisition save mode: register a new measurement directly into MMFDB instead of, or in addition to, the file-system output folder, so measurements become first-class database objects the moment they are acquired. This path is more complex than file output because MMFDB needs a provenance and ownership answer: link to an existing sample, create a new sample during acquisition, or make sample selection explicit at save time. The raw measurement is registered as an MMFDB artifact preserving acquisition-settings and device metadata, while file-output mode remains available as a fallback.

# Status
Planned (Proposed).

# Goal

Offer a second acquisition save mode: write a new measurement directly to MMFDB
instead of, or in addition to, the file-system output folder.

# Why

The output-folder solution ([PRD-32](prd-32.md)) covers the immediate need, but
the acquisition system also needs a native MMFDB path for users who want
measurements registered as first-class database objects as soon as they are
acquired.

That path is more complex than file output because MMFDB needs a provenance and
ownership answer:

- Link the measurement to an existing sample.
- Or create a new sample as part of acquisition.
- Or make the sample selection explicit at save time.

# Scope

- Add an acquisition save mode for MMFDB registration.
- Let the user choose between an existing sample and a new sample.
- Register the raw measurement as an MMFDB artifact.
- Preserve provenance from acquisition settings and device metadata.
- Keep file-output mode available.

# Dependencies

- PRD-02 sample tracking and sample creation.
- PRD-03 result registration.
- PRD-32 acquisition output folder, which remains the default immediate path.

# Non-goals

- Redesigning the acquisition data model.
- Collapsing measurement registration into the burst pipeline.
- Replacing the output-folder mode.

# Definition of Done

- [ ] Acquisition can register a measurement directly to MMFDB.
- [ ] The user can attach the measurement to an existing sample.
- [ ] The user can create a new sample during registration.
- [ ] The MMFDB record keeps the acquisition metadata and provenance.
- [ ] File output still works as the fallback path.

# Notes

This PRD should stay separate from PRD-32. The implementation path and the
database path solve different problems and have different dependency chains.

# Relationships
- Depends on [PRD-02](prd-02.md) (sample tracking/creation), [PRD-03](prd-03.md) (result registration), and [PRD-32](prd-32.md) (output folder, which stays the default immediate path).
- Shares the "register, don't just write a file when connected" principle with [PRD-34](prd-34.md).
- Touches [MMFDB (current)](/architecture/mmfdb.md), acquisition/acq, and the [plugin system](/architecture/plugin-system.md).
