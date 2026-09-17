"""Deprecated package: the parameter-transform editor is described by JSON.

`ParameterTransformModel` carries ``parameter_transform.view.json``. The name stays
importable because user copies of ``experiment_configs.yaml`` *replace* the bundled
model list and pickled projects pin class paths.
"""

from __future__ import annotations

from chisurf.core.models.parameter_transform.model import ParameterTransformModel

#: Deprecated alias of the pure compute model.
ParameterTransformWidget = ParameterTransformModel
