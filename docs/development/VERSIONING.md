---
type: Development Note
title: Versioning
description: ChiSurf uses a simplified versioning scheme that remains PEP 440 compatible for pip/conda.
tags: [development, versioning]
audience: developer
---

# Versioning

ChiSurf uses a simplified versioning scheme that remains **PEP 440** compatible for pip/conda.

## Public Version Format

Stable releases use a two-segment `YY.X` format:

- `YY` = release year (e.g., `26` for 2026)
- `X` = sequential release within that year (0, 1, 2, ...)

Examples:

- `26.1` — first stable release in 2026
- `26.2` — the next release in 2026 (bugfixes + features)

There are no point releases (no `26.1.1`). Bugfixes go into the next release
(`26.2`).

The tags before this scheme (`v24.02.14`, `v25.04.07`) are dated
`YY.MM.DD`. They are history, not a second scheme: everything from the first
`26` release on is `YY.X`.

## Pre-Release Versions

Pre-release builds use PEP 440 pre-release suffixes:

- `26.1a1` — alpha 1
- `26.1b1` — beta 1
- `26.1rc1` — release candidate 1

PEP 440 sort order: `26.1a1 < 26.1b1 < 26.1rc1 < 26.1`

## Dev Versions

Dev builds are derived from git metadata (unique per commit):

- `YY.devZZZ`

Where `ZZZ` is the number of commits since the last matching tag.

Notes:

- A tagged commit builds exactly the tag version (e.g., `26.1`).
- A non-tagged commit builds a dev version (e.g., `26.dev123`).

## Tag Naming

- Tags use a leading `v`: `v26.1`, `v26.1a1`, `v26.1b1`, `v26.1rc1`
- Hyphenated GitHub-style tags are also supported (mapped to PEP 440):
  - `v26.1-alpha.1` → `26.1a1`
  - `v26.1-beta.2` → `26.1b2`
  - `v26.1-rc.1` → `26.1rc1`

## Overrides

- Set `CHISURF_VERSION` to force a specific version string during builds.
