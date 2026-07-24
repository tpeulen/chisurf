"""GUI layer for the Burst Browser: custom AutoForm sections + view.json.

Importing this package registers the custom sections referenced by
``burst_browser.view.json``.
"""

from . import sections  # noqa: F401  (side effect: register custom sections)

__all__ = ["sections"]
