"""
Lazy Lifetime Fitter (lltf) package.

This package provides tools for fitting fluorescence lifetime data.
"""

from .fitter import Decay, fit_lifetime

__all__ = ["fit_lifetime", "Decay"]
