Parameter registry and helper scripts
======================================

This page documents the small command-line tools that maintain the
*parameter registry* used by the chisurf GUI to display
consistent parameter descriptions.

Overview
--------

The registry lives in::

    chisurf/core/settings/constants/parameter_registry.json

The JSON structure is::

    {
      "version": 1,
      "parameters": {
        "<key>": {
          "description": "...",
          "keywords": ["..."],
          "aliases": ["..."],
          "label_texts": ["..."],
          "symbol": "...",          # optional, mainly for family-specific keys
          "sources": [                # provenance information
            {"module": "...", "file": "...", "line": N, ...},
            ...
          ]
        },
        ...
      }
    }

Keys follow two conventions:

- **Family-prefixed keys** like ``rics.n``, ``fcs.N``, ``tcspc.tau1``
  are used for parameters coming from model definition files
  (YAML/JSON) and for explicitly registry-bound parameters in the GUI.
- **Plain keys** like ``sc``, ``bg``, ``n0`` correspond to
  ``FittingParameter(name="...")`` instances created directly in the
  Python code.

The helper scripts below only *add* or *merge* information; they never
overwrite an existing non-empty ``description`` field.

Generic exporter: export_fitting_parameters
-------------------------------------------

Script::

    dev_tools/export_fitting_parameters.py

Purpose:

- Scan the Python codebase for calls to ``FittingParameter(...)``.
- Collect basic metadata (name, location, bounds, inline description, label_text).
- Merge this information into ``parameter_registry.json`` using the
  *plain* parameter name as key (for example ``"n0"``).

Typical usage (from the project root)::

    python dev_tools/export_fitting_parameters.py

Important details:

- Only constant string ``name=...`` values are recorded; dynamic names
  (e.g. ``"R(%s,%i)" % (...)``) are still included via their literal
  string, but without semantic understanding.
- Existing descriptions in the registry are preserved. If a parameter
  had no description yet, an inline ``description="..."`` argument in
  the code is used as a seed.
- The script records a ``sources`` list for each parameter so later
  tools can see *where* it was defined (e.g. TCSPC vs FCS vs RICS).

FCS parsed-model exporter: export_fcs_parameters
------------------------------------------------

Script::

    dev_tools/export_fcs_parameters.py

Purpose:

- Read ``chisurf/core/models/fcs/models.yaml``.
- For each parsed FCS model, collect the parameter names that appear in
  the ``initial`` block.
- Ensure there is a corresponding ``fcs.<symbol>`` entry in the
  registry with at least ``symbol`` and ``aliases`` filled.

Typical usage::

    python dev_tools/export_fcs_parameters.py

This script is idempotent and safe to re-run after editing
``core/models/fcs/models.yaml`` or adding new FCS models.

FCS description filler: fill_fcs_descriptions
---------------------------------------------

Script::

    dev_tools/fill_fcs_descriptions.py

Purpose:

- Fill **missing** descriptions and keywords for ``fcs.*`` registry
  entries using simple, FCS-aware heuristics.
- Never overwrite an existing non-empty description.

Typical usage::

    python dev_tools/fill_fcs_descriptions.py

This is meant as a bootstrap tool: it provides reasonable default
texts and keywords for common FCS parameters (``N``, ``b``, ``td1``,
triplet fractions, antibunching terms, etc.), while still allowing
manual refinement directly in ``parameter_registry.json``.

Recommended workflows
---------------------

A few typical maintenance workflows for developers:

1. **After adding or changing FittingParameter definitions in code**

   - Run the generic exporter to update registry entries for all
     in-code parameters::

         python dev_tools/export_fitting_parameters.py

   - Optionally refresh FCS descriptions::

         python dev_tools/fill_fcs_descriptions.py

2. **After editing FCS parsed models (core/models/fcs/models.yaml)**

   - Update FCS registry entries::

         python dev_tools/export_fcs_parameters.py

   - Fill descriptions (only for missing ones)::

         python dev_tools/fill_fcs_descriptions.py

Manual edits
------------

You can always edit ``parameter_registry.json`` by hand to refine
texts or add aliases/keywords. The helper scripts are designed to be
*additive*:

- They do **not** overwrite an existing non-empty ``description``.
- They only append keywords that are not already present.

This makes it safe to run the tools repeatedly during development
while still maintaining high-quality, hand-written documentation for
critical parameters.
