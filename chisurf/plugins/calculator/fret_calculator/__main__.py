"""Standalone entry point for the FRET / HomoFRET calculator.

The ``csg_calculator`` console script names this module;
``test/test_rattler_recipe.py`` checks that every packaged entry point resolves.

GUI usage
---------

::

    csg_calculator
    python -m chisurf.plugins.calculator.fret_calculator
"""

from __future__ import annotations


def main() -> None:
    """Launch the calculator as a native emtk application."""
    from chisurf.emtk.__main__ import main as launch

    launch(["--plugin", "fret_calculator"])


if __name__ == "__main__":
    main()
