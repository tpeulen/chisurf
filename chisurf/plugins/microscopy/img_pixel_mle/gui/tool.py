"""GUI entrypoint for the pixel-wise FLIM MLE tool (AutoForm + view.json).

``ImgPixelMleTool`` hosts an :class:`~chisurf.gui.autoform.AutoForm` bound to the
Qt-free :class:`~...gui.view_model.PixelMleViewModel`. The heavy analysis
(``view_model.run``) runs on a background thread so the UI never blocks, and the
fitted lifetime map refreshes when it finishes.

The window shell (AutoForm host, background run thread, the shared
``apply_setup_settings``/``apply_pipeline_context``/``apply_calibration``
forwarders) is provided by
:class:`~chisurf.plugins.microscopy.mle_common.tool_base.AutoFormMleTool`; ``embedded`` is
accepted for API uniformity.
"""

from __future__ import annotations

from chisurf.plugins.microscopy.mle_common.tool_base import AutoFormMleTool

from .view_model import PixelMleViewModel


class ImgPixelMleTool(AutoFormMleTool):
    """Pixel-wise MLE tool (AutoForm-hosted)."""

    def __init__(self, parent=None, embedded: bool = False, view_model=None):
        super().__init__(
            view_model or PixelMleViewModel(),
            "Pixel-wise MLE",
            parent=parent,
            embedded=embedded,
            min_size=(680, 460),
        )


__all__ = ["ImgPixelMleTool"]
