"""Drop what the app keeps for its own lifetime, which in a test run is every later module.

A GUI process holds opened measurements so the next step of a workflow does not read the
file again; a pytest process imports hundreds of modules in a row, so the same caches hold
each module's photon files for the rest of the run. The root ``conftest.py`` calls
:func:`release_process_caches` after every module.
"""

from __future__ import annotations

import ctypes
import gc
import sys


def release_process_caches() -> None:
    """Stop the imaging worker, clear the TTTR/CLSM caches and give the freed pages back."""
    pixel_maps = sys.modules.get("chisurf.core.fluorescence.imaging.pixel_maps")
    if pixel_maps is not None:
        pixel_maps.shutdown_proc_pool()
        pixel_maps.clear_imaging_cache()
    # The shared reader cache behind ``staging.open_tttr`` (CLSM, drift, calibration, ...):
    # up to 512 MB plus the newest file, whatever its size (2026-10-20 resource record:
    # +514 MB from one img_drift test, still resident in the next module).
    staging = sys.modules.get("chisurf.core.fio.staging")
    if staging is not None:
        staging.clear_tttr_cache()
    gc.collect()
    if sys.platform == "darwin":
        # macOS keeps freed malloc pages resident (and compresses, then swaps, them) until
        # asked; the resource guard counts that swap against the run.
        try:
            ctypes.CDLL("/usr/lib/libSystem.B.dylib").malloc_zone_pressure_relief(None, 0)
        except (OSError, AttributeError):
            pass
