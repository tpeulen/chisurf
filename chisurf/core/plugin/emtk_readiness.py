"""Which plugins may open their emtk window by default.

A plugin that declares ``entrypoints.emtk`` next to ``entrypoints.gui`` is *swapped* to emtk only
once it passes four checks -- it looks right, it matches the Qt tool's features, it works, and it
is tested -- and an accepted report says so (``okf/plugins/emtk-ports/<id>/``). Until then it is
listed in ``emtk_preview.json``: the default mode keeps the Qt tool, and the emtk window stays
reachable by choosing the ``emtk`` GUI mode, so it can be tested and compared.

Removing an id from the list is the swap. It is data, not code, so a port's last step is one
line in one file.
"""

from __future__ import annotations

import json
import pathlib
from functools import lru_cache

__all__ = ["PREVIEW_FILE", "is_preview", "preview_ids"]

#: The list of plugin ids whose emtk entrypoint is a preview, not yet the default.
PREVIEW_FILE = pathlib.Path(__file__).with_name("emtk_preview.json")


@lru_cache(maxsize=1)
def _read(path: str) -> frozenset[str]:
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    ids = data.get("preview", []) if isinstance(data, dict) else []
    return frozenset(str(i) for i in ids if isinstance(i, str))


def preview_ids() -> frozenset[str]:
    """Ids of the plugins whose emtk window is still a preview (they open Qt by default)."""
    return _read(str(PREVIEW_FILE))


def is_preview(plugin_id: str) -> bool:
    """Whether *plugin_id* keeps its Qt tool as the default until its emtk port is accepted."""
    return str(plugin_id) in preview_ids()
