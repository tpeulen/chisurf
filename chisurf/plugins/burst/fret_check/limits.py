"""Sizes shared by the analysis and the page build -- no dependencies, so the
build host (plain Python, no numpy) can read them."""

#: Files above this many bytes are analysed in chunks (:mod:`chisurf.plugins.burst.fret_check.chunked`)
#: and, in a page, never copied into it: the worker reads them from disk.
LARGE_BYTES = 256 * 1024 * 1024
