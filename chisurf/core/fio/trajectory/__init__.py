"""Trajectory file formats, read and written in-tree.

ChiSurf owns its trajectory I/O rather than depending on an MD library for it.
DCD is ported from VMD's molfile plugin, which is permissively licensed.

============ ========= =========== ==========
Format       Read      Write       Units
============ ========= =========== ==========
DCD          yes       yes         Ångström
============ ========= =========== ==========

**Nothing is rescaled behind the caller's back**: the reader returns what the
format stores, which for DCD is ångström, the unit the interior uses.

XTC was read here until 2026-08-11 and was dropped on the user's instruction --
DCD is enough, and it is lossless where XTC quantises. A trajectory that only
exists as ``.xtc`` has to be converted by the tool that wrote it.
"""

from __future__ import annotations

from .dcd import DCDHeader, DCDWriter, dcd_info, read_dcd, read_time_axis, read_times, write_dcd

__all__ = ["DCDHeader", "DCDWriter", "dcd_info", "read_dcd",
           "read_time_axis", "read_times", "write_dcd"]
