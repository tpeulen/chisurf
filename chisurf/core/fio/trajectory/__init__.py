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

**The reader itself now lives in chimol** (``chimol.io.dcd``), and this module
re-exports it. ChiSurf does not own structures -- only what is specific to
experimental data -- and takes the rest from chimol; chimol is packaged to run
with no ChiSurf on the path at all, so a format reader it needs cannot live
here. See ``okf/plugins/chimol-relocation.md``. Every existing caller of
``chisurf.core.fio.trajectory`` is unchanged.
"""

from __future__ import annotations

from chisurf.plugins.chimol.chimol.io.dcd import (
    DCDHeader,
    DCDWriter,
    dcd_info,
    read_dcd,
    read_time_axis,
    read_times,
    write_dcd,
)

__all__ = ["DCDHeader", "DCDWriter", "dcd_info", "read_dcd",
           "read_time_axis", "read_times", "write_dcd"]
