"""Standalone launcher for the Calculators hub (``csg_calculators``)."""

from __future__ import annotations


def main() -> None:
    """Launch the Calculators hub as a native emtk application."""
    from chisurf.emtk.__main__ import main as launch

    launch(["--plugin", "calculators"])


if __name__ == "__main__":
    main()
