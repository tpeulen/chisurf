"""
Entry point for running the Trace Browser directly.

Usage:
  python -m chisurf.plugins.tttr.trace_browser
"""

from chisurf.emtk.__main__ import main as run_emtk


def main():
    """Open the native Trace Browser (``python -m chisurf.emtk --plugin trace_browser``)."""
    raise SystemExit(run_emtk(["--plugin", "trace_browser"]))


if __name__ == "__main__":
    main()
