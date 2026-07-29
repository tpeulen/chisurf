---
type: Subsystem
title: Core
description: Domain objects, fitting, data, models, math, settings, actions, and the API facade.
resource: chisurf/core/
tags: [core, fitting, models, domain]
timestamp: '2026-07-05T00:00:00Z'
---

# Scope

`chisurf/core/` holds the domain layer that is independent of Qt:

- Domain objects, data structures, and fitting models.
- The [action layer](/architecture/action-layer.md) (`chisurf/core/actions/`).
- The [API facade](/architecture/api-facade.md) (`chisurf/core/api/`).
- The [MMFDB metadata store](/architecture/mmfdb.md), imported as the
  standalone `mmfdb` package (`modules/mmfdb/src/mmfdb/`); the prerelease
  `chisurf/core/mmfdb/` facade is removed.
- Data specifications (`chisurf/core/dataspec/`) that drive the PRD-40
  model/UI split consumed by [AutoForm](/subsystems/gui-autoform.md).
- Plugin infrastructure (`chisurf/core/plugin/`).

Because the core is Qt-free where possible, it is reusable from the GUI,
the [server](/architecture/server.md), the CLI, and headless tests.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
