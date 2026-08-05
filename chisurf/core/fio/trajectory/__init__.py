"""Trajectory file formats, read and written in-tree.

ChiSurf owns its trajectory I/O rather than depending on an MD library for it.
The formats here are the ones the MD world exchanges — DCD to begin with,
with XTC and TRR to follow — ported from the reference C implementations,
which are permissively licensed (VMD's molfile plugin for DCD, GROMACS'
``xdrfile`` for XTC/TRR). See PRD-80.

Everything in this package works in **Ångström** and degrees, as the files
store them; nothing is rescaled behind the caller's back.
"""

from __future__ import annotations

from .dcd import DCDHeader, dcd_info, read_dcd, write_dcd

__all__ = ["DCDHeader", "dcd_info", "read_dcd", "write_dcd"]
