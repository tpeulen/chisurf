---
type: Development Note
title: Maintaining the release plugin inventory
description: Regenerate the committed plugin checklist without importing GUI code or crediting unfinished local ports.
tags: [development, plugins, gui]
audience: developer
---

# Maintaining the release plugin inventory

Run `pixi run -e test python build_tools/dev_utils/plugin_inventory.py --write`,
then `pixi run -e test python -m pytest test/test_plugin_inventory_current.py -q`.
The generator updates the owning release appendix and writes JSON/Markdown
receipts under `okf/validation/release-readiness-w6g/`.

The release checklist measures committed HEAD through an isolated Git archive.
The separate working-tree receipt exposes unfinished local ports; it is a dated
measurement, not a release claim. After committing a plugin change, regenerate
and commit its inventory change. Use `--json` to inspect the current tree or
`--revision <commit> --json` to compare a historical committed source state.

Each file belongs to its nearest plugin manifest; parent hubs do not inherit
nested tools' controls, help, demos or Qt imports. Tests and templates are
excluded. Malformed JSON or Python raises an error rather than lowering the
reported defect count. AST scanning includes imports inside functions and
ignores documentation mentions.

A checked flag proves only source presence. `Cond.ALWAYS` references include
legitimate viewport sizing; setup and `.native` references require code review.
Neither the inventory nor its freshness guard replaces actual click, scientific,
headless render, tour or migration-control parity verification.
