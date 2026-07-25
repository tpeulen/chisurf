"""``python -m chisurf.core.agent`` — run the ChiSurf agent from a terminal."""

from __future__ import annotations

import sys

from chisurf.core.agent.cli import main

if __name__ == "__main__":
    sys.exit(main())
