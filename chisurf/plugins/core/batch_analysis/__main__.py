"""Standalone launcher for the Batch-Analysis app (``csg_batch_analysis``)."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Forward standalone launch options to the shared native plugin launcher."""
    from chisurf.emtk.__main__ import main as launch

    return launch(["--plugin", "batch_analysis", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())
