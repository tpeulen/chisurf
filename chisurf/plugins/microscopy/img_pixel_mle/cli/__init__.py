"""CLI package for img_pixel_mle; re-exports the Click group at the package root."""

from __future__ import annotations

from .main import cli

__all__ = ["cli"]
