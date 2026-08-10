"""Shared base classes for the AutoForm-hosted MLE-lifetime imaging tools.

The pixel-wise (``img_pixel_mle``) and region-wise (``region_mle``) tools are
the same shape — an :class:`~chisurf.gui.autoform.AutoForm` bound to a Qt-free
view-model, a background run thread, and the shared
``apply_setup_settings``/``apply_pipeline_context``/``apply_calibration``
forwarders. They differ only in their view-model and a couple of extra UI-thread
events (preview/export). The common pieces live here so those ~90% are written
once:

- :mod:`tool_base` — the Qt host widget :class:`AutoFormMleTool`.
- :mod:`base` — the Qt-free view-model plumbing (:class:`MleObserverMixin`,
  :func:`scalar`).
- :mod:`contract` — the shared RPC envelope / contract-registration helpers.

These tools are a different shape from the per-pixel *map* tools that extend
:class:`imaging_common.tool_base.ImagingMapTool`, which is why they have their
own small base rather than reusing that one. The layout mirrors
``imaging_common`` (``base`` + ``tool_base``) so the two shared scaffolds read
the same way.
"""
