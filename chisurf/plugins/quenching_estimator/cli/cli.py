"""The `quest` command, reached through the host's entry point.

It *is* QuEst's CLI — `quest.cli:cli` — not a reimplementation. The plugin
declares the entry point so a ChiSurf install exposes the command; the commands
themselves stay where every other surface can see them.
"""

from __future__ import annotations

from typing import Any


def cli(*args: Any, **kwargs: Any) -> Any:
    from quest.cli import cli as _cli

    return _cli(*args, **kwargs)
