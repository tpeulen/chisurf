"""Deprecated module: the FIDA editor is described by JSON.

`FidaModel` moved to :mod:`chisurf.core.models.pch.fida_model` and carries
``fida.view.json``. The extraction also dropped a call into the GUI fitting client
from inside ``update_model``: pushing the computed mean through the client was
presentation, and the parameter's own controller binding already repaints it.

The widget name stays importable because user copies of ``experiment_configs.yaml``
*replace* the bundled model list and pickled projects pin class paths.
"""
from __future__ import annotations

from chisurf.core.models.pch.fida_model import FidaModel

#: Deprecated aliases of the pure compute model.
FidaModelWidget = FidaModel
