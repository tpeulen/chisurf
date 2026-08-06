"""Deprecated module: this parse editor is described by JSON, not built by hand.

`ParsePCFModel` carries ``parse.view.json`` and AutoForm renders its editor. The equation catalogue
moved into the compute model (`ParseModel.catalogue`), so the picker is a plain
`choice` over `catalogue_names` and needed no bespoke widget. The widget name stays
importable because user copies of ``experiment_configs.yaml`` *replace* the bundled
model list and pickled projects pin class paths.
"""
from __future__ import annotations

from chisurf.core.models.pcf.parse import ParsePCFModel

#: Deprecated alias of the pure compute model.
ParsePCFWidget = ParsePCFModel
