"""Deprecated module: the MaxEnt FCS editors are described by JSON, not built by hand.

:class:`chisurf.core.models.fcs.maxent_models.MaxEntFCSModel` and
:class:`~chisurf.core.models.fcs.maxent_models.MaxEntRHModel` carry
``maxent_fcs.view.json`` / ``maxent_rh.view.json`` and AutoForm renders their
editors.

The bespoke ``MaxEntFCSLCurvePlot`` and ``MaxEntFCSLCurveController`` this module
used to define are gone: the shared ``lcurve`` section now carries the sweep
window, the compute button, the detected corner and click-to-adopt, so the
L-curve sits *in* the editor beside the weight it selects rather than in a
separate plot tab, and every regularized model gets those controls by declaring
one section.

The widget names stay importable because user copies of
``experiment_configs.yaml`` *replace* the bundled model list and pickled projects
pin class paths, so a path that no longer resolves drops the entry from the model
menu without saying so.
"""

from __future__ import annotations

from chisurf.core.models.fcs.maxent_models import MaxEntFCSModel, MaxEntRHModel

#: Deprecated aliases of the pure compute models.
MaxEntFCSWidget = MaxEntFCSModel
MaxEntRHWidget = MaxEntRHModel
