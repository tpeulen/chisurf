"""Shared Qt-free scaffolding of the MLE-lifetime imaging tools.

The pixel-wise (``img_pixel_mle``) and region-wise (``region_mle``) tools (and the
spot finder) are the same shape: a Qt-free view-model drawn by a native emtk app,
a background run, and the shared
``apply_setup_settings``/``apply_pipeline_context``/``apply_calibration``
forwarders. The common pieces live here so they are written once:

- :mod:`base` — the Qt-free view-model plumbing (:class:`MleObserverMixin`,
  :func:`scalar`).
- :mod:`contract` — the shared RPC envelope / contract-registration helpers.

The per-pixel *map* tools use the sibling scaffold :mod:`imaging_common.base`.
"""
