"""Deprecated module: the PCH editor is described by JSON.

`PchMultiComponentModel` moved to :mod:`chisurf.core.models.pch.pch_model` and the
histogram maths it used -- which was defined here, in a Qt module -- to
:mod:`chisurf.core.models.pch.pch`, so a PCH distribution can now be computed and
checked without importing the GUI.

The extraction also stopped routing component add/remove through the GUI fitting
client: those writes did nothing whenever the client was absent, and the bare
``except`` around them said nothing.

The widget name stays importable because user copies of ``experiment_configs.yaml``
*replace* the bundled model list and pickled projects pin class paths.
"""
from __future__ import annotations

from chisurf.core.models.pch.pch_model import PchMultiComponentModel

#: Deprecated alias of the pure compute model.
PchMultiComponentModelWidget = PchMultiComponentModel
