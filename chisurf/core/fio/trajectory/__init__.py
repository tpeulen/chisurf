"""Trajectory file formats, read and written in-tree.

ChiSurf owns its trajectory I/O rather than depending on an MD library for it.
The formats here are the ones the MD world exchanges, ported from the
reference C implementations, which are permissively licensed (VMD's molfile
plugin for DCD, GROMACS' ``xdrfile`` for XTC). See PRD-80.

============ ========= =========== ==========
Format       Read      Write       Units
============ ========= =========== ==========
DCD          yes       yes         Ångström
XTC          yes       no          nanometres
============ ========= =========== ==========

**Nothing is rescaled behind the caller's back**, which is why the unit column
is not uniform: each reader returns what its format stores. XTC is nanometres
because that is GROMACS' unit, and converting on the way through would blur the
quantisation the format applied. Multiply by ten to compare with DCD.

XTC is read-only on purpose: ChiSurf writes DCD, which is lossless, so an XTC
encoder would only be needed to hand files to other tools — and it would have
to reproduce the quantisation ladder exactly to be worth having.
"""

from __future__ import annotations

from .dcd import DCDHeader, DCDWriter, dcd_info, read_dcd, write_dcd
from .xtc import XTCHeader, read_xtc, xtc_info

__all__ = ["DCDHeader", "DCDWriter", "XTCHeader", "dcd_info", "read_dcd",
           "read_xtc", "write_dcd", "xtc_info"]
