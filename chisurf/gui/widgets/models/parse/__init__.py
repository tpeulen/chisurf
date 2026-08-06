"""Deprecated module: the parse editors are described by JSON, not built by hand.

The four parse models (TCSPC / FCS / PCF / stopped-flow) carry their own
``parse.view.json`` and AutoForm renders their editors (see
``okf/subsystems/gui-autoform.md``). The equation
catalogue moved into the compute model (``ParseModel.catalogue``), so the picker
is a plain ``choice`` over ``catalogue_names``.

``widget.py`` and ``parseWidget.ui`` are deleted. They were kept only for the
equation field's **validity badge** and **LaTeX preview**, which are now what a
``value`` section of ``kind: "expression"`` renders — through the shared
:class:`~chisurf.gui.widgets.expression_input.ExpressionInput`, so the safe-AST
check, the badge, the typeset preview, the names-and-functions reference and
parameter discovery are one implementation rather than two.

``latex.py`` stays: it is the LaTeX conversion those previews use, shared with
the equation editor.

The widget names stay importable because user copies of
``experiment_configs.yaml`` *replace* the bundled model list and pickled projects
pin class paths.
"""
from __future__ import annotations

from chisurf.core.models.parse import ParseModel

#: Deprecated alias of the pure compute model.
ParseModelWidget = ParseModel

__all__ = ["ParseModelWidget"]
