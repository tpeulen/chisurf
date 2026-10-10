"""ALEX Suite — the classic ALEX-Suite workflow, as a ChiSurf pipeline.

The plugin is a *shell* (the native emtk hub in :mod:`.gui.native`): every analysis step hosts a tool that
already exists (ALEX Creator, Burst Selection, Background, Accurate FRET, ndX, Burst Browser, BVA, Trace
Browser). What it adds is the **order** those tools are used in, the names the old program used for them, and
the two things the old program had that ChiSurf did not: a titration / stack-plot analysis and an export that
writes the CSV files ALEX-Suite wrote.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

#: Plugin brand icon (unified emoji set).
icon = "🚦"

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest else "Spectroscopy:Single-Molecule:ALEX Suite"
description = "The ALEX-Suite workflow, as a linear ChiSurf pipeline."
