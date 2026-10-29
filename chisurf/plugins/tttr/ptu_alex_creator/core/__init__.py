"""Qt-free core logic for the ALEX Creator plugin.

Every ALEX conversion (single-file, batch-convert and merge) plus the micro-time
histogram is implemented here as pure :mod:`tttrlib` functions, with no Qt, RPC
or CLI dependency. The GUI (:mod:`..gui`), CLI (:mod:`..cli`) and RPC backend
(:mod:`..backend`) are thin adapters over this module.
"""

from __future__ import annotations

import os
import pathlib

import numpy as np
import tttrlib

from chisurf.core.fluorescence.excitation.alex import (  # noqa: F401 - the detection lives in core
    MIN_PERIOD_CONFIDENCE,
    alex_stream_masks,
    auto_alex_windows,
    auto_excitation_regions,
    detect_alex_channels,
    detect_alex_period,
    measure_alex_period,
    validate_alex_period,
)

#: container name → (file-extension stem, record-type id, container id).
CONTAINER_INFO: dict[str, tuple[str, int, int]] = {
    "PTU": ("ptu", 4, 0),
    "HT3": ("ht3", 4, 1),
    "SPC-130": ("spc", 7, 2),
    "SPC-600_256": ("spc", 8, 3),
    "SPC-600_4096": ("spc", 9, 4),
    "PHOTON-HDF5": ("hdf", 4, 5),
    "CZ-RAW": ("raw", 10, 6),
    "SM": ("sm", 11, 7),
}

#: tttrlib tag value-type for the record-type tags (0x10000008 == Int8).
_TAG_INT8 = 268435464


def supported_containers() -> list[str]:
    """Return every tttrlib container name."""
    return list(tttrlib.TTTR.get_supported_container_names())


def input_format_options() -> list[str]:
    """Input container choices: ``Auto`` plus every tttrlib container name."""
    return ["Auto", *supported_containers()]


def resolve_filetype(input_format: str, path: str | None = None) -> str | None:
    """Resolve the tttrlib container name to read *path* with.

    ``input_format`` of ``"Auto"`` returns the inferred container name (or
    ``None`` to let tttrlib auto-detect); any other value is returned verbatim.
    """
    if input_format and input_format != "Auto":
        return input_format
    if path and os.path.exists(path):
        idx = tttrlib.inferTTTRFileType(path)
        names = supported_containers()
        if idx is not None and 0 <= idx < len(names):
            return names[idx]
    return None


def container_ext(output_format: str) -> str:
    """File-extension stem for *output_format* (defaults to ``ptu``)."""
    return CONTAINER_INFO.get(output_format, ("ptu", 0, 0))[0]


def default_output_name(in_path: str, output_format: str, suffix: str = "_alex") -> str:
    """Suggested output filename for *in_path* in *output_format*."""
    base = pathlib.Path(in_path).stem if in_path else "alex"
    return f"{base}{suffix}.{container_ext(output_format)}"


def load(path: str, filetype: str | None = None) -> tttrlib.TTTR:
    """Load a TTTR file (``filetype`` = ``None`` lets tttrlib auto-detect)."""
    return tttrlib.TTTR(path, filetype) if filetype else tttrlib.TTTR(path)




def apply_alex(tttr: tttrlib.TTTR, alex_period: int, period_shift: int) -> tttrlib.TTTR:
    """Map ALEX macro-time alternation into micro-time, in place, and return it."""
    period = validate_alex_period(alex_period)
    tttr.alex_to_microtime(period, int(period_shift))
    return tttr


def alex_histogram(
    path: str, alex_period: int, period_shift: int, filetype: str | None = None
) -> np.ndarray:
    """Return the micro-time histogram after ALEX conversion of *path*."""
    tttr = apply_alex(load(path, filetype), alex_period, period_shift)
    period = int(alex_period)
    return np.bincount(tttr.micro_times, minlength=period)[:period]




def _prepare_output_header(tttr: tttrlib.TTTR, output_format: str, input_format: str):
    """Return the header to write *tttr* with, transcoded when the container changes.

    Returns ``None`` when no container change is requested (write with the file's
    own header).
    """
    if output_format == input_format or output_format == "Auto":
        return None
    if output_format not in CONTAINER_INFO:
        raise ValueError(f"Unsupported ALEX output format: {output_format}")
    ext, rec, cont = CONTAINER_INFO[output_format]
    header = tttrlib.TTTRHeader(tttr.header)
    header.tttr_container_type = cont
    header.tttr_record_type = rec
    if output_format == "PTU":
        # PTU via HydraHarp wants the special tag group 0x00010304.
        header.set_tag("TTResultFormat_TTTRRecType", 0x00010304, _TAG_INT8)
        header.set_tag("TTResultFormat_BitsPerRecord", 32, _TAG_INT8)
        header.set_tag("MeasDesc_RecordType", rec, _TAG_INT8)
    else:
        header.set_tag("TTResultFormat_TTTRRecType", rec, _TAG_INT8)
        header.set_tag("MeasDesc_RecordType", rec, _TAG_INT8)
    return header


def _ensure_parent(out_path: str) -> None:
    """Create the output file's parent directory (tttrlib segfaults otherwise)."""
    parent = pathlib.Path(out_path).parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)


def _write(tttr: tttrlib.TTTR, out_path: str, output_format: str, input_format: str) -> None:
    """Write only when the target records preserve every excitation phase."""
    header = _prepare_output_header(tttr, output_format, input_format)
    _validate_output_microtimes(tttr, header if header is not None else tttr.header)
    _ensure_parent(out_path)
    if header is not None:
        written = tttr.write(out_path, header)
    else:
        written = tttr.write(out_path)
    if written is False:
        raise OSError(f"Could not write ALEX output: {out_path}")


def _validate_output_microtimes(tttr: tttrlib.TTTR, header) -> None:
    """Refuse phase truncation or loss in the effective output record type.

    Photon-HDF5 stores decoded uint16 arrays. Fixed-width photon records use
    the widths declared in tttrlib's TTTRRecordTypes.h; T2, SM and CZ have no
    microtime payload. Validate before opening or creating any output file.
    """
    phase = np.asarray(tttr.micro_times)
    if not phase.size or int(header.tttr_container_type) == 5:
        return
    limits = {
        3: 32767,
        4: 32767,
        5: 4095,
        7: 4095,
        8: 255,
        9: 4095,
        12: 32767,
        14: 32767,
        15: 4095,
        16: 4095,
        1: 0,
        2: 0,
        6: 0,
        10: 0,
        11: 0,
        13: 0,
    }
    record = int(header.tttr_record_type)
    limit = limits.get(record)
    if limit is None:
        raise ValueError(f"Cannot verify ALEX phase capacity for record type {record}.")
    largest = int(phase.max())
    if largest > limit:
        raise ValueError(
            f"Output record type {record} cannot preserve microtime phase {largest} "
            f"(maximum {limit}); choose a sufficiently wide T3 or Photon-HDF5 output."
        )


def convert_file(
    in_path: str,
    out_path: str,
    alex_period: int,
    period_shift: int,
    output_format: str = "PTU",
    input_format: str = "Auto",
) -> str:
    """Convert a single ALEX file: read → ALEX→µtime → write *out_path*.

    Returns the written path.
    """
    filetype = resolve_filetype(input_format, in_path)
    tttr = apply_alex(load(in_path, filetype), alex_period, period_shift)
    _write(tttr, out_path, output_format, input_format)
    return out_path


def merge_files(
    in_paths: list[str],
    out_path: str,
    alex_period: int,
    period_shift: int,
    output_format: str = "PTU",
    input_format: str = "Auto",
) -> str:
    """Merge several ALEX files into one, then ALEX→µtime → write *out_path*.

    Events are concatenated with a running macro-time offset so the merged stream
    is monotonic. Returns the written path.
    """
    if not in_paths:
        raise ValueError("No input files to merge.")
    merged = tttrlib.TTTR()
    running = 0
    first_header_src = None
    for in_path in in_paths:
        filetype = resolve_filetype(input_format, in_path)
        tttr = load(in_path, filetype)
        if first_header_src is None:
            first_header_src = tttr
        mt = tttr.macro_times
        if len(mt) == 0:
            continue
        offset = int(running) - int(mt[0])
        merged.append_events(
            mt, tttr.micro_times, tttr.routing_channels, tttr.event_types, True, offset
        )
        running = int(mt[-1]) + offset + 1
    assert first_header_src is not None  # Every nonempty input list loads a first header.
    apply_alex(merged, alex_period, period_shift)
    # Carry the first file's header (transcoded if the output container differs).
    header = _prepare_output_header(first_header_src, output_format, input_format)
    if header is None:
        header = first_header_src.header
    _validate_output_microtimes(merged, header)
    _ensure_parent(out_path)
    if merged.write(out_path, header) is False:
        raise OSError(f"Could not write ALEX output: {out_path}")
    return out_path


__all__ = [
    "CONTAINER_INFO",
    "supported_containers",
    "input_format_options",
    "resolve_filetype",
    "container_ext",
    "default_output_name",
    "load",
    "apply_alex",
    "validate_alex_period",
    "alex_histogram",
    "auto_alex_windows",
    "auto_excitation_regions",
    "detect_alex_period",
    "detect_alex_channels",
    "measure_alex_period",
    "MIN_PERIOD_CONFIDENCE",
    "alex_stream_masks",
    "convert_file",
    "merge_files",
]
