"""Deprecated module: the global-fit editor is described by JSON.

`GlobalFitModel` carries ``globalfit.view.json`` and AutoForm renders its editor,
using the shared ``global_parameter_table`` -- which spans every fit *and* every
registered out-of-fit group, so it shows strictly more than the hand-written table
did. The widget names stay importable because user copies of
``experiment_configs.yaml`` *replace* the bundled model list and pickled projects
pin class paths.
"""

from __future__ import annotations

from chisurf.core.models.global_model.globalfit import GlobalFitModel

#: Deprecated alias of the pure compute model. ``ParameterTransformWidget`` is
#: *not* aliased here: that model is still hand-written (its catalogue holds Python
#: ``code:`` rather than equations, so it needs its own catalogue API), and
#: ``global_model/__init__`` re-exports the real widget for it.
GlobalFitModelWidget = GlobalFitModel
