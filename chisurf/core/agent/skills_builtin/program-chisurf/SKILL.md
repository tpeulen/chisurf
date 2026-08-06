---
name: program-chisurf
description: >-
  Write code that belongs in ChiSurf — a plugin, a fitting model, a tool, a
  patch to existing code. Use when the user asks you to add a feature, write a
  plugin, implement a model, or change how the program works, rather than to
  analyse data with it.
triggers:
  - plugin
  - implement
  - add a feature
  - new model
  - write a model
  - extend
  - patch
  - refactor
  - source code
  - codebase
  - api
  - how does chisurf
  - modify chisurf
  - contribute
tools:
  - search_api
  - read_api_source
  - search_documentation
  - read_documentation
  - list_plugins
  - check_python
  - write_file
  - run_command
---

# Writing code for ChiSurf

You do not know this codebase from memory, and inventing an API is the single
most common way generated ChiSurf code fails. Everything you need is one
lookup away, and looking it up is much cheaper than the user discovering the
mistake.

## Before writing a line

1. **`search_documentation(..., scope="code")`** for the concept — the OKF
   concepts under `okf/` describe the architecture and *why* it is that way.
   `scope="user"` reaches the guides under `docs/`, which show the intended
   workflow. Read the one that governs what you are about to touch, with
   **`read_documentation`** (pass a `section` rather than pulling in a whole
   long page).
2. **`search_api`** for the symbols you intend to call, and
   **`read_api_source`** when the signature is not enough. The index is built
   from the source, so it is never out of date.
3. **`list_plugins`** and read the closest existing one. A new plugin is best
   written by following the nearest neighbour, not from first principles.

## The shape of the codebase

* `chisurf/core/` is the Qt-free domain layer: data, fitting, models,
  parameters, settings, actions. Anything that must work head-lessly lives
  here.
* `chisurf/gui/` is the Qt layer. **Core must never import from it.**
* `chisurf/plugins/<group>/<name>/` is a plugin: a `manifest.json` declaring
  its id, display name, entry points and any RPC methods, plus a `gui/`
  entry-point class. Forms are described by a `*.view.json` and rendered by
  AutoForm rather than hand-built where possible.
* State changes go through the **action layer** (`chisurf.core.actions`), and
  data and fits through the **API facade** (`ChiSurfAPI`), not through the
  process globals. The globals are legacy compatibility surface.

## Conventions that are enforced

* **Every function and method takes a NumPy-style docstring.** If a function's
  purpose is genuinely unclear, mark it `# TODO: needs docstring` rather than
  inventing one.
* Ruff with a 100-column line length, and mypy. Run `check_python` on
  anything you write before writing it to disk.
* Tests live in `test/` or a plugin's own `test/` directory; GUI tests are
  named so the non-GUI suite skips them.
* A material change updates the matching OKF concept **and** appends to
  `okf/log.md` in the same change. Say so when you hand work back — do not
  quietly skip it.

## Working method

Write the smallest thing that can be checked, check it, then extend. Prefer
`check_python` and a focused test run over a large unverified patch. When you
change existing behaviour, read the code you are changing first —
`read_api_source` — rather than pattern-matching from the name.

If the user asks for something the architecture forbids (a core module
importing Qt, a plugin reaching into another plugin's internals), say so and
propose the shape that fits. That is more useful than code that works once
and cannot be maintained.

## What not to do

Do not invent module paths, class names or keyword arguments — look them up.
Do not copy a pattern from another project; this codebase has its own. Do not
write a large file in one shot without checking it. And do not modify the
user's data, tests or unrelated modules to make something pass.
