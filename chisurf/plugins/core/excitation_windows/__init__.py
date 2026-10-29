"""Excitation Windows: detect PIE pulses / µs-ALEX alternation and check a setup's windows.

The method is :mod:`chisurf.core.fluorescence.excitation`; this plugin exposes it as RPC
methods (``excitation_windows.detect``, ``excitation_windows.check``), a ``csc windows`` CLI and a
small emtk tool. The setup editor, the Record tool and the burst / PIE analyses call the same core
check.
"""

from pathlib import Path as _Path

from chisurf.core.plugin import load_manifest as _load_manifest

_manifest = _load_manifest(_Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Setup:Excitation Windows"
