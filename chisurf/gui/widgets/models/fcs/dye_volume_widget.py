"""Deprecated module: the dye-shape FCS editor is described by JSON, not built by hand.

:class:`chisurf.core.models.fcs.dye_shape.DyeShapeFCSModel` carries
``dye_shape.view.json`` and AutoForm renders its editor. The dye picker is a plain
`choice` over the model's ``dye_names``, and the derived ``D`` / ``tauD`` / ``cpm``
outputs are written directly onto their parameters — the hand-written version
published them through the GUI fitting client inside a bare ``except``, so they
were never written at all when that client was absent (headless, or before the
editor had registered the fit).

The widget name stays importable because user copies of
``experiment_configs.yaml`` *replace* the bundled model list and pickled projects
pin class paths, so a path that no longer resolves drops the entry from the model
menu without saying so.
"""
from __future__ import annotations

from chisurf.core.models.fcs.dye_shape import DyeShapeFCSModel

#: Deprecated alias of the pure compute model.
DyeShapeFCSWidget = DyeShapeFCSModel
