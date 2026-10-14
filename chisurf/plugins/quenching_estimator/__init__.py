"""Quenching Estimator (QuEst): PET quenching and FRET of a dye tethered to a protein, from the structure alone.

Peulen, Opanasyuk & Seidel, *J. Phys. Chem. B* **2017**, 121, 8211
(https://doi.org/10.1021/acs.jpcb.7b03441).

# Layout

- ``core/`` -- the engine: accessible volume, Brownian walk, PET and FRET rates, photon Monte-Carlo,
  the project document and its validation, site scans, run artefacts. Numerics are IMP.bff's
  (``get_av``, ``simulate_probe_diffusion``, ``simulate_photon_trace``, ...).
- ``settings/`` -- the parameter catalogue, dye presets, locale files: what the engine computes is
  declared there, not in code.
- ``api/`` -- ``local`` is the facade every surface calls; ``client``/``contract`` for host code.
- ``rpc/`` -- the method table, handlers and the in-process dispatcher; the host registers them.
- ``cli/`` -- ``csc quest``.
- ``gui/`` -- the Qt-free project form model, its generated view spec (en/de/fr), the native emtk
  window.
- ``demo.py`` / ``examples/`` -- T4 lysozyme, so the guided tour runs without the user's files.

# Nothing heavy at import

ChiSurf's discovery imports every plugin at startup, and the engine reaches IMP. Every engine import
here is inside a function.
"""

from __future__ import annotations

#: Plugin brand icon (unified emoji set).
icon = "💧"

name = "Structure:Computation:QuEst"

