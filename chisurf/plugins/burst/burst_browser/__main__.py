"""Entry point for the Burst Browser: ``python -m chisurf.plugins.burst.burst_browser``."""

from __future__ import annotations


def main() -> None:
    """Launch the plugin as a native emtk application."""
    from chisurf.emtk.__main__ import main as launch

    launch(["--plugin", "burst_browser"])


if __name__ == "__main__":
    main()
