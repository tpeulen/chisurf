"""Quenching Estimator (QuEst) — the ChiSurf-side shell.

The science is the `quest` package: PET quenching of a dye tethered by a
flexible linker, from the structure alone, plus optional FRET. See
Peulen, Opanasyuk & Seidel, *J. Phys. Chem. B* **2017**, 121, 8211
(https://doi.org/10.1021/acs.jpcb.7b03441).

# This package declares; it does not implement

`manifest.json` carries the identity, the entry points and the RPC method table
— **copied from `quest/manifest.json`**, so the host reads exactly what QuEst
offers and there is no second hand-maintained list to drift. `rpc/services.py`
hands ChiSurf's dispatcher to `quest.rpc.services.register_services`, which
was built duck-typed for that. `gui/tool.py` embeds `quest.gui`'s AutoForm in a
`ChisurfDockTool`. There is no `core/`: QuEst is the core.

# Nothing imports `quest` at module scope

ChiSurf's discovery imports every plugin at startup. The previous version of
this file did `from quest.gui import TransientDecayGenerator` at the top, so
launching ChiSurf pulled in QuEst, IMP and numba whether or not anyone opened
the tool — and a broken QuEst install became a broken ChiSurf startup. Every
`quest` import here is inside a function.
"""

from __future__ import annotations

from typing import Any

#: Plugin brand icon (unified emoji set).
icon = "💧"

name = "Structure:Computation:QuEst"
menu_hidden = True  # integrated into Structure Tools; hidden from the ribbon


def __getattr__(name: str) -> Any:
    """Resolve the GUI classes on first access.

    `QuEstWindow` is the name ChiSurf's legacy discovery and the plugin's own
    test use; `QuEstTool` is what the manifest points at. They are the same
    widget, and neither is imported until asked for.
    """
    if name in {"QuEstTool", "QuEstWindow"}:
        from .gui.tool import QuEstTool

        return QuEstTool
    raise AttributeError(name)
