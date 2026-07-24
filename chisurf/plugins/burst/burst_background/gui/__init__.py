"""GUI layer for Burst Background Estimation: custom AutoForm sections + view.json.

Importing this package registers the custom sections referenced by
``background.view.json``.
"""

from . import sections  # noqa: F401  (side effect: register custom sections)

__all__ = ["sections"]
