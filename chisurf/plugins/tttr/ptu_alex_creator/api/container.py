"""ALEX→PIE straight into a ``.pto`` container: the one home for the packing.

The ALEX Creator is the one plugin that folds µs-ALEX macro-time modulation
into micro-time. Folding writes a TTTR file (``core.convert_file``); a
photon container (``.pto``) cannot embed a derived stream any other way --
it embeds instrument files verbatim -- so the container is packed from
intermediates in a temporary directory, deleted as soon as the container
verifies. The ALEX Suite's alternation step and this plugin share this
function; the suite does not keep its own copy.
"""
from __future__ import annotations

import pathlib
import tempfile
from typing import Sequence

from .. import core

#: The output-format choice that routes here (not a tttrlib container name).
CONTAINER_FORMAT = "PTO"


def convert_to_container(
    paths: Sequence[str | pathlib.Path],
    alex_period: int,
    period_shift: int,
    out_dir: str | pathlib.Path | None = None,
    suffix: str = "_alex",
    input_format: str = "Auto",
) -> pathlib.Path:
    """Fold every ALEX *path* to micro-time and pack them into one ``.pto``.

    One container for the whole list, beside the first source unless
    *out_dir* says otherwise. The intermediate PTUs are scaffolding: one per
    source, each the size of the source, written to a temporary directory --
    not the data folder, where a crash or a cancel left them looking like
    results -- and deleted as soon as the container has verified its own
    checksum (``keep_original=False``).
    """
    from chisurf.plugins.core.tttr_to_pto.api import convert as pack_container  # noqa: PLC0415

    sources = sorted((pathlib.Path(p) for p in paths), key=lambda p: p.name)
    if not sources:
        raise ValueError("no files to convert")
    target_dir = pathlib.Path(out_dir) if out_dir is not None else sources[0].parent
    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="alex_convert_") as scratch:
        staging = pathlib.Path(scratch)
        intermediates = []
        for source in sources:
            intermediate = staging / f"{source.stem}{suffix}.ptu"
            core.convert_file(
                str(source),
                str(intermediate),
                alex_period=int(alex_period),
                period_shift=int(period_shift),
                output_format="PTU",
                input_format=input_format,
            )
            intermediates.append(intermediate)
        return pack_container(intermediates, keep_original=False, out_dir=target_dir)
