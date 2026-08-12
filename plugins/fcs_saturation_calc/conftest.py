"""Pytest fixtures for fcs_saturation_calc plugin helper tests."""

# Ensure plugin dir is importable
import sys
sys.path.insert(0, "/Users/tpeulen/dev/chisurf/plugins")

# Ensure we can import chisurf’s future plugin
try:
    import chisurf  # noqa: F401
    HAVE_CHISURF = True
except ImportError:
    HAVE_CHISURF = False
