"""Deprecated module: the ProteinMC editor is described by JSON, not built by hand.

:class:`chisurf.core.models.structure.proteinmc_model.ProteinMCModel` carries
``proteinmc.view.json`` and AutoForm renders its editor.

The 1,984-line widget this replaces held the sampling settings behind a modal
dialog, each energy term's parameters behind a second one, a Qt worker thread,
two throttling timers and a progress dialog — none of which a script could
reach, so ProteinMC could only be run by clicking. The model owns all of that
state now and runs the sampler in a plain thread; the run *controls* are the
general ``background_run`` section, which owns the timer that repaints the
trajectory plots while sampling.

The widget name stays importable because user copies of
``experiment_configs.yaml`` *replace* the bundled model list and pickled projects
pin class paths, so a path that no longer resolves drops the entry from the model
menu without saying so.
"""
from __future__ import annotations

from chisurf.core.models.structure.proteinmc_model import POTENTIAL_SPECS, ProteinMCModel

#: Deprecated alias of the pure compute model.
ProteinMCModelWidget = ProteinMCModel

__all__ = ["POTENTIAL_SPECS", "ProteinMCModel", "ProteinMCModelWidget"]
