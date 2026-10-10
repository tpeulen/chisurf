"""Entry point for the Burst Background Estimation plugin: ``python -m chisurf.plugins.burst.burst_background``."""

from __future__ import annotations


def main() -> None:
    """Launch the plugin as a native emtk application."""
    from chisurf.emtk.__main__ import main as launch

    launch(["--plugin", "burst_background"])


if __name__ == "__main__":  # pragma: no cover - manual GUI entry
    main()
