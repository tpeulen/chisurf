#!/usr/bin/env python3
"""Entry point of PhAcq, ChiSurf's acquisition: its window on its own, or the simulation CLI.

This module starts the plugin's native window on its own (``phacq``; ``--fullscreen`` for an
instrument PC), or forwards ``--cli`` to the simulation CLI.
"""

import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_standalone(fullscreen: bool = False) -> int:
    """Run the native PhAcq window as its own application (*fullscreen*: cover the monitor)."""
    from emtk.native import NativeHost

    from .gui.record_app import make_app

    app = make_app()
    host = NativeHost(app, title="PhAcq", fullscreen=fullscreen)
    try:
        host.run()
    finally:
        host.close()
    return 0


def main() -> int:
    """Main entry point.

    Modes:

    - **CLI mode**: if ``--cli`` is present in the arguments, the remaining
      arguments are forwarded to the simulation CLI (config/run) and no GUI
      is started.
    - **GUI mode** (default, also ``--standalone``): the native PhAcq window;
      ``--fullscreen`` covers the whole monitor.
    """
    args = sys.argv[1:]
    if "--cli" not in args and ("-h" in args or "--help" in args):
        # Reachable as `csc phacq --help`, where silently opening a
        # window instead of answering would be the wrong move. With `--cli` the
        # flag belongs to the simulation CLI below, not to this wrapper.
        print(
            "Usage: phacq [--standalone] [--fullscreen] [--cli SUBCOMMAND ...]\n\n"
            "  (no arguments)   open the PhAcq window\n"
            "  --standalone     the same, spelled out\n"
            "  --fullscreen     the window covers the whole monitor (instrument PC)\n"
            "  --cli ...        forward to the simulation CLI (try: --cli --help)"
        )
        return 0
    if "--cli" in args:
        cli_args = args[args.index("--cli") + 1 :]

        # Import here to avoid unnecessary Click/CLI setup when running GUI.
        from .tcspc_devices.simulation.simulation_cli import main as simulation_cli_main

        # Synthesize argv for Click so that subcommands (config/run) see a
        # clean argument list. Example usage:
        #   python standalone.py --cli config --output ...
        sys.argv = [sys.argv[0]] + cli_args
        return simulation_cli_main()
    return run_standalone(fullscreen="--fullscreen" in args)


if __name__ == "__main__":
    sys.exit(main())
