"""Tests for Chimol mouse rotation modes."""

from __future__ import annotations

from chisurf.plugins.chimol.chimol import mouse_modes
from chisurf.plugins.chimol.chimol.renderer.view import MolView
from chisurf.plugins.chimol.chimol import config


def test_display_config_default_mouse_mode():
    """The shipped display config should default to PyMOL-style rotation."""
    assert config._DISPLAY_CONFIG["camera"]["mouse_mode"] == "pymol"


def test_normalize_mouse_mode():
    """The mode table should normalise mouse mode strings."""
    assert mouse_modes.normalize_mouse_mode("pymol") == "pymol"
    assert mouse_modes.normalize_mouse_mode("PyMOL") == "pymol"
    assert mouse_modes.normalize_mouse_mode("chimol") == "chimol"
    assert mouse_modes.normalize_mouse_mode("Chimol") == "chimol"
    assert mouse_modes.normalize_mouse_mode("unknown") == "pymol"
    assert mouse_modes.normalize_mouse_mode(None) == "pymol"


def test_rotation_delta_multiplier():
    """PyMOL mode inverts left-drag rotation deltas relative to Chimol mode."""
    assert mouse_modes.rotation_delta_multiplier("pymol") == -1.0
    assert mouse_modes.rotation_delta_multiplier("chimol") == 1.0


def test_pan_delta_multiplier():
    """PyMOL mode keeps pan deltas object-following; Chimol inverts them."""
    assert mouse_modes.pan_delta_multiplier("pymol") == 1.0
    assert mouse_modes.pan_delta_multiplier("chimol") == -1.0


def test_molview_normalize_mouse_mode():
    """MolView uses the same normalisation rules as the renderer."""
    assert MolView._normalize_mouse_mode("pymol") == "pymol"
    assert MolView._normalize_mouse_mode("chimol") == "chimol"
    assert MolView._normalize_mouse_mode("invalid") == "pymol"
