"""Pure, Qt-free API for TTTR microtime LUT tools.

Layers: :mod:`.lut` (pure math), :mod:`.io` (file/tttrlib IO), :mod:`.compute`
(orchestration), :mod:`.settings` (settings.tttr.json + correction application),
:mod:`.contract` (RPC method names + JSON-Schemas). Shared by the cli, backend
(rpc) and gui layers.
"""

from __future__ import annotations

from . import compute, contract, io, lut, settings  # noqa: F401

__all__ = ["compute", "contract", "io", "lut", "settings"]
