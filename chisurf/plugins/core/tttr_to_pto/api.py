"""Qt-free conversion between a vendor photon file and its `.pto` container.

Two directions, both already implemented by
:class:`chisurf.core.fio.pto.Measurement` and both verified by checksum before
anything is ever deleted:

- :func:`convert` -- pack one or more vendor files (``.ptu``, ``.spc``,
  ``.ht3``, ...) into a single `.pto` container, e.g. a measurement split
  across several vendor files.
- :func:`extract` -- the reverse: recover the embedded vendor file(s) from an
  existing `.pto`.

This module is the thin, single call a GUI (the drop guard, the bare
drop-only tool) or a script uses to reach either one, so the conversion logic
exists exactly once.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from chisurf.core.fio.pto import Measurement, PtoMfdbError

__all__ = ["convert", "extract"]


def convert(
    path: str | Path | Sequence[str | Path], *, keep_original: bool = True, out_dir=None
) -> Path:
    """Import one or more vendor files into a single `.pto` container.

    Parameters
    ----------
    path : str or pathlib.Path, or a sequence of them
        The vendor photon file (``.ptu``, ``.spc``, ``.ht3``, ...), or several
        belonging to the same split measurement -- all embedded into the
        **same** container, in lexical order by file name
        (:meth:`chisurf.core.fio.pto.Measurement.create`).
    keep_original : bool
        When ``False``, every vendor file passed in is deleted -- but only
        once the freshly written container's own checksum verifies clean, so
        a corrupted write never costs a source.
    out_dir : str or pathlib.Path, optional
        Directory for the container. Defaults to beside the first
        (lexically) vendor file.

    Returns
    -------
    pathlib.Path
        The container.

    Raises
    ------
    PtoMfdbError
        If the container fails its own checksum verification. Every source
        is left untouched in that case, regardless of *keep_original*.
    """
    raw_paths = [Path(path)] if isinstance(path, (str, Path)) else [Path(p) for p in path]
    with Measurement.create(raw_paths, out_dir=out_dir) as measurement:
        target = measurement.path

    if not keep_original:
        with Measurement.open(target, writable=False) as check:
            problems = check.verify()
        if problems:
            sources = ", ".join(str(p) for p in raw_paths)
            raise PtoMfdbError(
                f"{target} failed verification, keeping {sources}: " + "; ".join(problems)
            )
        for raw in raw_paths:
            raw.unlink()
    return target


def extract(path: str | Path, *, out_dir=None, results: bool = True) -> list[Path]:
    """Unpack a `.pto` back into the files it was packed from, plus its results.

    The read half of :func:`convert`, and the whole of it: a container holds the
    instrument data *and* every analysis run against it, so unpacking one that
    returned only the vendor files would leave the results locked in the format
    they were meant to be recoverable from. What comes out is what a session
    working in folders would have on disk —

    ::

        m000.spc                                     the original, byte for byte
        countrate_All 0.2000#60/bi4_bur/m000.bur     one folder per analysis
        sliding_window_All 0.0101#60/bi4_bur/m000.bur

    — tab-separated text, the format the external tools read. Inside the
    container the same tables are stored as binary columns, which is what makes
    them cheap to open; text is for leaving.

    The vendor half delegates to :meth:`Measurement.disassemble`, which writes
    the instrument bytes back out exactly and verifies the checksum while doing
    it, so "the original is recoverable" stays a checked claim.

    Parameters
    ----------
    path : str or pathlib.Path
        A `.pto` container.
    out_dir : str or pathlib.Path, optional
        Directory to unpack into. Defaults to beside *path*.
    results : bool
        Write the analysis folders as well. ``False`` recovers only the
        instrument files -- for a caller that wants the original and nothing
        else, e.g. to hand it to an instrument's own software.

    Returns
    -------
    list of pathlib.Path
        Everything written: the instrument file(s) first -- normally one, but a
        container stacking several measurements writes each of them back out --
        then one `.bur` per analysis found.
    """
    from chisurf.core.fio.analysis_path import export_tree

    target_dir = Path(out_dir) if out_dir is not None else Path(path).parent
    with Measurement.open(path, writable=False) as measurement:
        written = list(measurement.disassemble(target_dir))
    if results:
        # One call, and it knows nothing about bursts: a container's analyses
        # are addressed and unpacked by one scheme, so an analysis that has
        # never heard of `.pto` is unpacked by it too.
        written.extend(export_tree(path, target_dir))
    return written
