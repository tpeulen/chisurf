"""Deprecated module: every PDA2c editor is described by JSON, not built by hand.

The seven PDA models under :mod:`chisurf.core.models.pda2c` and
:mod:`chisurf.core.models.pda3c` carry their own ``*.view.json`` and AutoForm
renders their editors (see ``okf/subsystems/gui-autoform.md``).

``widgets.py`` is deleted. Nine of its ten classes were unreferenced outside the
file once the models became data-described, and the tenth --
``FretRdaAxisSettingsWidget`` -- was never a model widget at all: the FRET
distance axis is one global setting, so it moved to
:mod:`chisurf.gui.widgets.fret_rda_axis_settings`.

The widget names stay importable because user copies of
``experiment_configs.yaml`` *replace* the bundled model list and pickled projects
pin class paths, so a path that no longer resolves drops the entry from the model
menu without saying so.
"""

from __future__ import annotations

from chisurf.core.models.pda2c.anisotropy import Pda2cAnisotropyModel
from chisurf.core.models.pda2c.pdagauss import Pda2cGaussianDistanceModel
from chisurf.core.models.pda2c.simple import Pda2cSimpleModel

#: Deprecated aliases of the pure compute models.
Pda2cSimpleModelWidget = Pda2cSimpleModel
Pda2cAnisotropyModelWidget = Pda2cAnisotropyModel
Pda2cGaussianDistanceModelWidget = Pda2cGaussianDistanceModel

__all__ = [
    "Pda2cAnisotropyModelWidget",
    "Pda2cGaussianDistanceModelWidget",
    "Pda2cSimpleModelWidget",
]
