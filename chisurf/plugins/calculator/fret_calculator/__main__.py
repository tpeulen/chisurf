"""Standalone entry point for the FRET / HomoFRET calculator.

The ``csg_calculator`` console script has named this module since the plugin
existed, but the module itself never moved here when the plugin was reorganised
under ``chisurf/plugins/calculator/`` -- so the packaged command failed with
``ModuleNotFoundError``. ``test/test_rattler_recipe.py`` now checks that every
packaged entry point resolves.

GUI usage
---------

::

    csg_calculator
    python -m chisurf.plugins.calculator.fret_calculator
"""

from __future__ import annotations

import sys


def main() -> None:
    """Launch the calculator in its own Qt application."""
    from qtpy import QtWidgets

    from .gui.tool import FretCalculatorTool

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = FretCalculatorTool()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
