"""Qt-free conversion between a vendor photon file and its `.pto` container.

Two directions, both already implemented by
:class:`chisurf.core.fio.pto.Measurement` and both verified by checksum before
anything is ever deleted:

- :func:`convert` -- pack a vendor file (``.ptu``, ``.spc``, ``.ht3``, ...)
  into a `.pto` container.
- :func:`extract` -- the reverse: recover the embedded vendor file(s) from an
  existing `.pto`.

This module is the thin, single call a GUI (the drop guard, the bare
drop-only tool) or a script uses to reach either one, so the conversion logic
exists exactly once.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.fio.pto import Measurement, PtoMfdbError

__all__ = ["convert", "extract"]


def convert(path: str | Path, *, keep_original: bool = True, out_dir=None) -> Path:
    """Import *path* into a `.pto` container beside it.

    Parameters
    ----------
    path : str or pathlib.Path
        The vendor photon file (``.ptu``, ``.spc``, ``.ht3``, ...).
    keep_original : bool
        When ``False``, the vendor file is deleted -- but only once the
        freshly written container's own checksum verifies clean, so a
        corrupted write never costs the source.
    out_dir : str or pathlib.Path, optional
        Directory for the container. Defaults to beside *path*.

    Returns
    -------
    pathlib.Path
        The container.

    Raises
    ------
    PtoMfdbError
        If the container fails its own checksum verification. The source is
        left untouched in that case, regardless of *keep_original*.
    """
    raw = Path(path)
    with Measurement.create(raw, out_dir=out_dir) as measurement:
        target = measurement.path

    if not keep_original:
        with Measurement.open(target, writable=False) as check:
            problems = check.verify()
        if problems:
            raise PtoMfdbError(
                f"{target} failed verification, keeping {raw}: " + "; ".join(problems)
            )
        raw.unlink()
    return target


def extract(path: str | Path, *, out_dir=None) -> list[Path]:
    """Recover the embedded vendor file(s) from a `.pto` container.

    The read half of :func:`convert` -- the other direction of the same
    conversion. Delegates to :meth:`Measurement.disassemble`, which writes the
    instrument bytes back out exactly and verifies the checksum while doing
    it, so "the original is recoverable" is a checked claim rather than an
    intention.

    Parameters
    ----------
    path : str or pathlib.Path
        A `.pto` container.
    out_dir : str or pathlib.Path, optional
        Directory to write the recovered file(s) into. Defaults to beside
        *path*.

    Returns
    -------
    list of pathlib.Path
        The recovered instrument file(s) -- normally one, but a container
        that stacks more than one measurement writes each of them back out.
    """
    target_dir = Path(out_dir) if out_dir is not None else Path(path).parent
    with Measurement.open(path, writable=False) as measurement:
        return measurement.disassemble(target_dir)
