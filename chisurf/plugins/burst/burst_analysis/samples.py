"""What each file of a burst workflow is, and the calibrations the non-measurement files give.

A burst session measures more than the sample: the **buffer** (the background, the buffer
without dye), an **IRF** (a scatter / water measurement) and a **reference dye** (a free,
fast-rotating dye such as Rhodamine 110). Data Selection labels every file with one of these
sample types (:data:`SAMPLE_TYPES`), guessed from its name (:func:`guess_sample_type`) and
always the user's to change. Only measurements are searched for bursts; the others are
calibration inputs:

* a buffer gives the background rate of every detector, ``Bg_<detector>`` in kHz
  (:func:`buffer_rates`), and corrects a scatter IRF in Burst MLE;
* an IRF measurement is Burst MLE's measured IRF;
* a reference dye gives the **G factor** of every detector with a parallel and a
  perpendicular channel, the tail ratio of its VV / VH decays
  (:func:`reference_g_factors`, the VV/VH G-factor core), and the **confocal volume**: the
  dye's photons are correlated and a 3-D diffusion model fitted with the dye's known
  diffusion coefficient gives ``w0``, ``z0`` and ``V_eff`` (:func:`confocal_volume`).

Formulas, assumptions and citations: ``docs/concepts/reference_dye_calibration.md``. Nothing
here imports a GUI toolkit.
"""

from __future__ import annotations

import contextlib
import json
import math
import re
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

__all__ = [
    "COLOUR_DYE",
    "CUSTOM_DYE",
    "DEFAULT_TEMPERATURE_C",
    "colour_groups",
    "default_dye",
    "dye_choice",
    "dye_colour",
    "dye_diffusion",
    "infer_dye",
    "guess_colour",
    "resolve_row",
    "row_keys",
    "row_label",
    "SAMPLE_LABELS",
    "SAMPLE_TYPES",
    "buffer_rates",
    "calibrate",
    "confocal_volume",
    "diffusion_3d",
    "guess_sample_type",
    "reference_g_factors",
    "sample_summary",
]

#: The sample types, in the order the selector lists them.
SAMPLE_TYPES = ("measurement", "buffer", "irf", "reference")
#: What the selector shows for each type.
SAMPLE_LABELS = {
    "measurement": "Measurement",
    "buffer": "Buffer",
    "irf": "IRF",
    "reference": "Reference dye",
}
#: The role's name in a table row (its colour follows): short, the full name is in the tooltip.
_SHORT_LABELS = {"reference": "Reference"}

def dye_label(name: str) -> str:
    """A dye's short name for a table cell: its longest alias of up to eight characters
    (``Rh110``, ``Alexa647``), else its database name."""
    from chisurf.core.fluorescence.dyes import get_dye

    entry = get_dye(name) or {}
    short = [a for a in entry.get("aliases") or [] if len(a) <= 8 and " " not in a]
    return max(short, key=len) if short else str(name)


#: Singular and plural nouns of the summary line ("3 measurements · 1 buffer").
_NOUNS = {
    "measurement": ("measurement", "measurements"),
    "buffer": ("buffer", "buffers"),
    "irf": ("IRF", "IRFs"),
    "reference": ("reference dye", "reference dyes"),
}

#: The database dye a colour is calibrated with when nothing names one (if the dye database
#: has it): Rhodamine 110 for green, Rhodamine 6G for yellow, Alexa Fluor 647 for red.
COLOUR_DYE = {"B": "Rhodamine 110", "G": "Rhodamine 110", "Y": "Rhodamine 6G", "R": "Alexa Fluor 647"}
#: The temperature a reference dye is assumed measured at until the user enters another [°C].
DEFAULT_TEMPERATURE_C = 22.5
#: The choice of a reference row that is no database dye: the user's own D.
CUSTOM_DYE = "Other (custom D)"
#: Header tags whose text may name the sample (PTU comments, TTResult fields, ...).
_HEADER_HINTS = ("comment", "sample", "dye", "title", "description", "note", "label", "ttresult")
#: Names of a measurement made for one colour.
_COLOUR_TOKENS = {
    "B": re.compile(r"(?<![a-z0-9])(blue|405|440|450)(?![a-z0-9])", re.I),
    "G": re.compile(r"(?<![a-z0-9])(green|485|488|490|blue[-_ ]?green)(?![a-z0-9])", re.I),
    "Y": re.compile(r"(?<![a-z0-9])(yellow|532|561|565)(?![a-z0-9])", re.I),
    "R": re.compile(r"(?<![a-z0-9])(red|635|640|647)(?![a-z0-9])", re.I),
}

#: Names of a reference-dye measurement beyond the dyes of ``reference_dyes.yaml``.
REFERENCE_PATTERN = re.compile(
    r"(?<![a-z])(rh\d+[a-z]?|rhodamine|r6g|dye|ref|reference)(?![a-z])", re.I
)

#: Avogadro's number, 1/mol.
AVOGADRO = 6.02214076e23


def guess_sample_type(path: str | Path) -> str:
    """The sample type *path* is, by its name: ``irf``, ``buffer``, ``reference`` or ``measurement``.

    A scatter / water measurement (``irf``, ``scatter``, ``ludox``, ``water``, ``H2O``,
    ``prompt``) is the IRF; ``buffer``, ``bg``, ``blank``, ``background`` (and buffer names such
    as ``PBS``) the buffer; a dye of ``reference_dyes.yaml`` (Rh110, Rh6G, Alexa488, ...) or a
    name with ``rh110``, ``rhodamine``, ``r6g``, ``dye``, ``ref`` the reference dye. Anything
    else is a measurement. The rules are those Burst MLE uses to find such files beside a
    measurement (:mod:`chisurf.core.fio.reference_files`); a guess is only a start.
    """
    from chisurf.core.fio.reference_files import BACKGROUND_PATTERN, IRF_PATTERN, reference_dye

    stem = Path(str(path)).stem
    if IRF_PATTERN.search(stem):
        return "irf"
    if BACKGROUND_PATTERN.search(stem):
        return "buffer"
    if reference_dye(stem) is not None or REFERENCE_PATTERN.search(stem) or dye_in_name(stem):
        return "reference"
    return "measurement"


def guess_colour(path: str | Path) -> str | None:
    """The colour (``"G"``, ``"R"``, ...) a reference or IRF measurement is for, by its name: the
    colour of the dye it names (Rh110 green, Alexa647 red; :func:`dye_colour`), else a colour
    word or laser line in the name (``red``, ``640``); ``None`` when the name does not say."""
    stem = Path(str(path)).stem
    dye = dye_in_name(stem)
    if dye:
        return dye_colour(dye)
    for colour, pattern in _COLOUR_TOKENS.items():
        if pattern.search(stem):
            return colour
    return None


# -- the reference dye of a measurement: the dye database ---------------------------------------- #
def _tokens(text: str) -> list[str]:
    """Words of *text* and every run of two or three neighbours (``Rhodamine_110`` ->
    ``rhodamine``, ``110``, ``rhodamine110``), longest first."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", str(text)) if w]
    runs = []
    for size in (3, 2, 1):
        runs += ["".join(words[i:i + size]) for i in range(len(words) - size + 1)]
    return runs


def dye_in_name(text: str) -> str | None:
    """The database dye *text* names (a file name, a header comment), by its name or an alias,
    case- and punctuation-insensitive (``Rh110``, ``rhodamine110``, ``A647``, ``Atto655``,
    ``Cy5``); ``None`` when it names none. The names and aliases are those of the dye database
    (:mod:`chisurf.core.fluorescence.dyes`), never a table of this module."""
    from chisurf.core.fluorescence.dyes import get_dye

    for token in _tokens(text):
        if len(token) < 2 or token.isdigit():
            continue
        entry = get_dye(token)
        if entry is not None and entry.get("category", "organic_dye") == "organic_dye":
            return str(entry["name"])
    return None


def dye_colour(name: str) -> str:
    """The emission colour of a database dye by its name: red for Cy5 and the 6xx dyes, yellow for
    Rhodamine 6G / B and the 5xx dyes, else green (Rhodamine 110 / 123, fluorescein, the 4xx dyes)."""
    text = str(name).lower()
    if "cy5" in text:
        return "R"
    if "6g" in text or "rhodamine b" in text or "cy3" in text:
        return "Y"
    numbers = [int(n) for n in re.findall(r"\d{3}", text)]
    if any(n >= 600 for n in numbers):
        return "R"
    if any(530 <= n < 600 for n in numbers):
        return "Y"
    return "G"


def _nearest(colour: str, colours: list[str]) -> str | None:
    """The colour of *colours* nearest *colour* in wavelength (bluer on a tie)."""
    from chisurf.core.fluorescence import detector_names as dn

    order = {letter: i for i, (letter, _w) in enumerate(dn.COLOURS)}
    if colour in colours or not colours or colour not in order:
        return colour if colour in colours else None
    known = [c for c in colours if c in order]
    return min(known, key=lambda c: (abs(order[c] - order[colour]), order[c])) if known else None


def header_text(path: str | Path) -> str:
    """The text of the header tags of *path* that may name its sample (comments, sample,
    TTResult fields, ...); empty when the header cannot be read."""
    if not Path(str(path)).is_file():
        return ""
    try:
        import tttrlib

        header = tttrlib.TTTRHeader(str(path))
        tags = json.loads(header.json).get("tags", [])
    except Exception:  # noqa: BLE001 - no header: nothing to read
        return ""
    texts = [
        str(tag.get("value"))
        for tag in tags
        if isinstance(tag.get("value"), str)
        and any(hint in str(tag.get("name", "")).lower() for hint in _HEADER_HINTS)
    ]
    return " ".join(texts)


def infer_dye(
    paths: Iterable[str | Path], colour: str | None = None, colours: Iterable[str] = ()
) -> tuple[str, str]:
    """``(dye name, where from)`` of reference measurements *paths*: a dye named in the header
    (``"header"``), else in a file name (``"file name"``), else the *colour*'s default
    (``"default"``). A dye of another colour than *colour* (a green row cannot hold Alexa 647)
    is not taken -- unless the setup's *colours* have none nearer (Rhodamine 6G in the green row
    of a green / red setup)."""
    paths = list(paths)
    colours = list(colours)

    def fits(name: str | None) -> bool:
        if not name:
            return False
        own = dye_colour(name)
        return colour is None or own == colour or (bool(colours) and _nearest(own, colours) == colour)

    for path in paths:
        name = dye_in_name(header_text(path))
        if fits(name):
            return str(name), "header"
    for path in paths:
        name = dye_in_name(Path(str(path)).stem)
        if fits(name):
            return str(name), "file name"
    return default_dye(colour), "default"


def default_dye(colour: str | None) -> str:
    """The database dye a colour is calibrated with by default (:data:`COLOUR_DYE`; the custom
    choice when the database has none)."""
    from chisurf.core.fluorescence.dyes import get_dye

    entry = get_dye(COLOUR_DYE.get(colour or "G", "Rhodamine 110"))
    return str(entry["name"]) if entry else CUSTOM_DYE


def dye_choice(choice: Mapping | None, colour: str | None = None) -> dict[str, Any]:
    """A reference row's dye with every field: ``dye`` (database name or :data:`CUSTOM_DYE`),
    ``how`` (``"user"``, ``"header"``, ``"file name"``, ``"default"``), ``temperature_c``,
    ``custom_D``."""
    choice = dict(choice or {})
    return {
        "dye": str(choice.get("dye") or default_dye(colour)),
        "how": str(choice.get("how") or "default"),
        "temperature_c": float(choice.get("temperature_c", DEFAULT_TEMPERATURE_C)),
        "custom_D": float(choice.get("custom_D") or 0.0),
    }


def dye_diffusion(choice: Mapping | None, colour: str | None = None) -> tuple[float, str]:
    """``(D [µm²/s], where it came from)`` of a reference row's dye: the database entry's
    ``D(25 °C, water)`` corrected to the row's temperature with the water viscosity
    (:func:`chisurf.core.fluorescence.diffusion.diffusion_at_temperature`, what the FCS
    calculator applies), or the user's custom D."""
    from chisurf.core.fluorescence.diffusion import diffusion_at_temperature
    from chisurf.core.fluorescence.dyes import get_dye

    c = dye_choice(choice, colour)
    if c["dye"] == CUSTOM_DYE:
        return c["custom_D"], "custom D"
    entry = get_dye(c["dye"])
    if entry is None:
        return float("nan"), f"{c['dye']} is not in the dye database"
    d25 = float(entry["d25_um2_s"])
    d = diffusion_at_temperature(d25, c["temperature_c"])
    citation = dye_citation(entry)
    return d, (
        f"{entry['name']}: {d25:.0f} µm²/s at 25 °C in water"
        + (f" ({citation})" if citation else "")
        + f", {d:.0f} µm²/s at {c['temperature_c']:.1f} °C"
    )


def dye_citation(entry: Mapping | None) -> str:
    """The literature source of a dye database entry's D (its first source), "" without one."""
    sources = (entry or {}).get("sources") or []
    if not sources:
        return ""
    first = sources[0]
    return " ".join(x for x in (str(first.get("citation", "")), str(first.get("url", ""))) if x)


def colour_groups(setup: Mapping | None) -> list[dict[str, Any]]:
    """The colours of *setup*: ``[{"colour", "word", "detectors"}]`` in wavelength order.

    A colour is a detector's emission colour (``R`` for ``R|G`` and ``R|R``: the same red
    detectors, under another excitation), so one reference dye and one IRF per colour calibrate
    all its detectors. A detector without an ``emission|excitation`` name is a colour of its own.
    """
    from chisurf.core.fluorescence import detector_names as dn

    words = dict(dn.COLOURS)
    order = {letter: i for i, (letter, _w) in enumerate(dn.COLOURS)}
    groups: dict[str, list[str]] = {}
    for det in (setup or {}).get("detectors") or {}:
        groups.setdefault(dn.emission(det) or str(det), []).append(str(det))
    return [
        {"colour": c, "word": words.get(c, c), "detectors": dets}
        for c, dets in sorted(groups.items(), key=lambda kv: (order.get(kv[0], 99), kv[0]))
    ]


def row_keys(setup: Mapping | None) -> list[str]:
    """The rows of Data Selection's assignment table for *setup*: ``measurement`` and
    ``buffer``, then ``irf:<colour>`` and ``reference:<colour>`` for every colour."""
    colours = [g["colour"] for g in colour_groups(setup)]
    return (
        ["measurement", "buffer"]
        + [f"irf:{c}" for c in colours]
        + [f"reference:{c}" for c in colours]
    )


def row_label(key: str, setup: Mapping | None = None, *, short: bool = False) -> str:
    """``"Reference dye — red (R|G, R|R)"`` for ``reference:R`` (*short*: ``"Reference dye · red"``)."""
    from emtk.i18n import tr

    kind, _, colour = str(key).partition(":")
    base = tr(SAMPLE_LABELS.get(kind, "Unassigned" if kind == "unassigned" else kind))
    if not colour:
        return base
    group = next((g for g in colour_groups(setup) if g["colour"] == colour), None)
    word = tr(group["word"]) if group else colour
    if short:
        return f"{tr(_SHORT_LABELS.get(kind, base))} · {word}"
    detectors = f" ({', '.join(group['detectors'])})" if group else ""
    return f"{base} — {word}{detectors}"


def kind_of(key: str) -> str:
    """The sample type of a row key (``reference:R`` -> ``reference``)."""
    return str(key).partition(":")[0]


def resolve_row(stored: str, setup: Mapping | None, path: str | Path | None = None) -> str:
    """The row a file assigned *stored* is shown in with *setup*.

    An IRF or reference dye guessed without a colour goes to the colour its name says, else the
    first colour; a colour the setup no longer has, or an IRF / reference without any setup, is
    ``"unassigned"`` -- shown, never lost (the stored assignment stays as it was)."""
    keys = row_keys(setup)
    if stored in keys:
        return stored
    kind, _, colour = str(stored).partition(":")
    if kind in ("measurement", "buffer"):
        return kind
    if kind in ("irf", "reference") and not colour:
        colours = [g["colour"] for g in colour_groups(setup)]
        if not colours:
            return "unassigned"
        wanted = guess_colour(path) if path is not None else None
        wanted = _nearest(wanted, colours) if wanted else None
        return f"{kind}:{wanted or colours[0]}"
    return "unassigned"


def sample_summary(types: Iterable[str]) -> str:
    """``"3 measurements · 1 buffer · 1 IRF · 1 reference dye"`` (types without files left out)."""
    from emtk.i18n import tr

    counts = {kind: 0 for kind in SAMPLE_TYPES}
    for key in types:
        kind = kind_of(key)
        counts[kind if kind in counts else "measurement"] += 1
    parts = []
    for kind in SAMPLE_TYPES:
        n = counts[kind]
        if n:
            one, many = _NOUNS[kind]
            parts.append(f"{n} {tr(one if n == 1 else many)}")
    return " · ".join(parts)


# -- reading ------------------------------------------------------------------------------------- #
def _file_type(setup: Mapping) -> str | None:
    file_type = str((setup.get("tttr_reading") or {}).get("file_type") or "")
    return None if not file_type or file_type.lower() == "auto" else file_type


#: The reads of the :func:`calibrate` running on this thread (``{path: TTTR}``), else unset.
_READS = threading.local()


@contextlib.contextmanager
def _one_read_per_file():
    """Inside, :func:`_open` reads each file once: a calibration asks for a reference dye's
    photons per detector (its G factors), again for its confocal volume and its count rate.
    Nothing here changes the photons it is handed. Released when the block ends."""
    outer = getattr(_READS, "memo", None)
    if outer is None:
        _READS.memo = {}
    try:
        yield
    finally:
        if outer is None:
            _READS.memo = None


def _open(path: str | Path, setup: Mapping) -> Any:
    """The photons of *path*, read with the corrections of *setup* itself (its LUTs and channel
    shifts) -- never those of whichever setup another tool published last."""
    from chisurf.core.data_io.detector_setups import setup_lut_open_kwargs
    from chisurf.core.fio.staging import open_tttr

    memo = getattr(_READS, "memo", None)
    key = (str(path), json.dumps(setup_lut_open_kwargs(dict(setup)), sort_keys=True, default=str))
    if memo is not None and key in memo:
        return memo[key]
    tttr = open_tttr(Path(path), _file_type(setup), cache=False, **setup_lut_open_kwargs(dict(setup)))
    if memo is not None:
        memo[key] = tttr
    return tttr


def _binning(setup: Mapping) -> int:
    return max(1, int((setup.get("tttr_reading") or {}).get("micro_time_binning", 1) or 1))


def _gate(info: Mapping, binning: int, n_bins: int) -> tuple[int, int]:
    """The detector's first micro-time gate in bins of *binning* (the whole period without one)."""
    gates = [g for g in (info.get("micro_time_ranges") or []) if g and len(g) >= 2]
    if not gates:
        return 0, n_bins
    lo, hi = int(gates[0][0]) // binning, int(gates[0][1]) // binning
    lo, hi = max(0, min(lo, n_bins)), max(0, min(hi, n_bins))
    return (lo, hi) if hi > lo else (0, n_bins)


def _seconds(tttr: Any) -> float:
    from chisurf.core.fio.photon_views import photon_column

    macro = photon_column(tttr, "macro_times")
    if macro.size < 2:
        return 0.0
    return float((int(macro[-1]) - int(macro[0])) * float(tttr.header.macro_time_resolution))


def _in_gate_mask(tttr: Any, info: Mapping, binning: int, n_raw: int) -> np.ndarray:
    """Photons of *info*'s channels inside its first micro-time gate."""
    from chisurf.core.fio.photon_views import photon_column

    chs = [int(c) for c in info.get("chs", [])]
    mask = np.isin(photon_column(tttr, "routing_channels"), chs)
    lo, hi = _gate(info, 1, n_raw)
    micro = photon_column(tttr, "micro_times")
    return mask & (micro >= lo) & (micro < hi)


def _n_raw(tttr: Any) -> int:
    from chisurf.core.fio.micro_time import channels_per_period

    return int(channels_per_period(tttr))


# -- buffer --------------------------------------------------------------------------------------- #
def buffer_rates(paths: Iterable[str | Path], setup: Mapping) -> dict[str, dict[str, float]]:
    """``{detector: {"B_kHz", "counts", "seconds"}}``: the photons of each detector's channels in
    its gate, per second of the buffer measurements *paths* (summed over the files)."""
    detectors = dict(setup.get("detectors") or {})
    out = {det: {"counts": 0.0, "seconds": 0.0} for det in detectors}
    for path in paths:
        tttr = _open(path, setup)
        seconds = _seconds(tttr)
        n_raw = _n_raw(tttr)
        for det, info in detectors.items():
            out[det]["counts"] += float(np.count_nonzero(_in_gate_mask(tttr, info, 1, n_raw)))
            out[det]["seconds"] += seconds
    for row in out.values():
        row["B_kHz"] = row["counts"] / row["seconds"] / 1e3 if row["seconds"] > 0 else float("nan")
    return out


# -- G factor ------------------------------------------------------------------------------------- #
def _vv_vh(paths: Iterable[str | Path], setup: Mapping, info: Mapping) -> tuple[np.ndarray, np.ndarray, float]:
    """Summed VV and VH micro-time histograms of *info*'s channels (at the setup's binning) and
    the width of one bin [ns]."""
    from chisurf.plugins.burst.burst_mle_analysis.engine import vv_vh_histogram

    binning = _binning(setup)
    vv = vh = None
    dt_ns = 0.0
    for path in paths:
        tttr = _open(path, setup)
        row = np.asarray(
            vv_vh_histogram(
                tttr, list(info.get("chs", [])), (0, 0), binning,
                normalize_counts=0, apply_vh_shift=False, cut=False,
            ),
            dtype=float,
        )
        half = row.size // 2
        vv = row[:half] if vv is None else vv + row[:half]
        vh = row[half:] if vh is None else vh + row[half:]
        dt_ns = float(tttr.header.micro_time_resolution) * 1e9 * binning
    if vv is None:
        return np.zeros(0), np.zeros(0), 0.0
    return vv, vh, dt_ns


def _tail_region(
    vv: np.ndarray, gate: tuple[int, int], dt_ns: float, tail_offset_ns: float
) -> tuple[list[float], list[float] | None]:
    """The tail-matching region (bins) of a reference decay and the background region before
    its rise (``None`` when the gate leaves too little room before the pulse)."""
    lo, hi = gate
    part = vv[lo:hi]
    peak = lo + int(np.argmax(part))
    step = max(1, int(math.ceil(tail_offset_ns / max(dt_ns, 1e-9))))
    background = None
    floor = 0.0
    pre_end = peak - max(2, int(math.ceil(1.0 / max(dt_ns, 1e-9))))
    if pre_end - lo >= 10:
        background = [float(lo), float(pre_end)]
        floor = float(np.mean(vv[lo:pre_end]))
    start = min(peak + step, hi - 2)
    # the tail ends where the decay above the floor fell to 2 % of its peak (the rest is noise)
    above = vv[start:hi] - floor
    level = 0.02 * max(float(vv[peak]) - floor, 1.0)
    low = np.nonzero(above < level)[0]
    stop = start + int(low[0]) if low.size else hi - 1
    stop = max(stop, min(start + 5, hi - 1))
    return [float(start), float(stop)], background


def reference_g_factors(
    paths: Iterable[str | Path],
    setup: Mapping,
    *,
    detectors: Iterable[str] | None = None,
    tail_offset_ns: float = 1.5,
) -> dict[str, dict[str, Any]]:
    """The G factor of every detector with a parallel and a perpendicular channel, from a
    fast-rotating reference dye.

    The dye depolarises long before it emits, so its VV / VH decays differ in the tail only by
    the detection efficiencies: ``G = VV / VH`` there (the convention of the VV/VH G-factor tool
    and of the setup's G-Factor column). The tail starts *tail_offset_ns* after the peak and
    ends where the decay fell to 2 % of the peak; a background level is taken from the bins
    before the rise when the gate has room for it. The arithmetic is
    :func:`chisurf.plugins.vv_vh_g_factor.core.calculations.calculate_g_factor_core`.

    *detectors* (default: all) are those of one colour. The G factor is a property of the
    channels, so detectors on the same channels (``R|G`` and ``R|R``: one red detector pair,
    two PIE windows) share one value, computed in the window that saw the dye best.

    Returns
    -------
    dict
        ``{detector: {"g", "std", "sem", "region", "background_region", "counts", "dt_ns",
        "from"}}``; ``from`` is the detector whose window gave the value.
    """
    from chisurf.plugins.vv_vh_g_factor.core.calculations import calculate_g_factor_core

    paths = list(paths)
    all_detectors = dict(setup.get("detectors") or {})
    wanted = list(all_detectors) if detectors is None else [d for d in detectors if d in all_detectors]
    best: dict[tuple, tuple[float, str, dict]] = {}
    for det in wanted:
        info = all_detectors[det]
        if len(info.get("chs", [])) < 2:
            continue
        vv, vh, dt_ns = _vv_vh(paths, setup, info)
        if vv.size == 0 or vv.sum() <= 0 or vh.sum() <= 0:
            continue
        result = _g_of(vv, vh, dt_ns, info, setup, tail_offset_ns, calculate_g_factor_core)
        if result is None:
            continue
        key = tuple(int(c) for c in info.get("chs", []))
        if key not in best or result["gated_counts"] > best[key][0]:
            best[key] = (result["gated_counts"], det, result)
    out: dict[str, dict[str, Any]] = {}
    for det in wanted:
        key = tuple(int(c) for c in all_detectors[det].get("chs", []))
        if key in best:
            _n, source, result = best[key]
            out[det] = {**result, "from": source}
    return out


def _g_of(vv, vh, dt_ns, info, setup, tail_offset_ns, calculate_g_factor_core) -> dict | None:
    """The tail-ratio G of one detector's VV / VH decays (``None``: none could be estimated)."""
    gate = _gate(info, _binning(setup), vv.size)
    if vv[gate[0]:gate[1]].sum() <= 0:
        return None
    region, background = _tail_region(vv, gate, dt_ns, tail_offset_ns)
    result = calculate_g_factor_core(
        vv, vh, region, use_bg=background is not None, bg_region_bounds=background
    )
    value = result.get("g_factor")
    if value is None or not np.isfinite(value) or value <= 0:
        return None
    std = result.get(
        "g_factor_stddev_corrected" if background is not None else "g_factor_stddev_uncorrected"
    )
    n = max(1, int(region[1] - region[0]))
    from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import reference_anisotropy

    return {
        # the dye's anisotropy right after the pulse with this G: below -0.05 the detector's VV
        # and VH channels are swapped in the setup (a free dye starts positive)
        "r_peak": float(reference_anisotropy(vv, vh, float(value), window=gate)),
        "g": float(value),
        # the spread of the per-bin ratios over the tail, and the error of their mean
        "std": float(std) if std is not None else float("nan"),
        "sem": float(std) / math.sqrt(n) if std is not None else float("nan"),
        "region": region,
        "background_region": background,
        "counts": float(vv.sum() + vh.sum()),
        "gated_counts": float(vv[gate[0]:gate[1]].sum() + vh[gate[0]:gate[1]].sum()),
        "dt_ns": dt_ns,
    }


# -- confocal volume ------------------------------------------------------------------------------ #
def diffusion_3d(tau_ms: np.ndarray, n: float, tau_d_ms: float, s: float, offset: float) -> np.ndarray:
    r"""Free 3-D diffusion through a Gaussian detection volume (the ``3D Gauss`` FCS model):

    .. math:: G(\tau) = b + \frac{1}{N}\,\Bigl(1+\frac{\tau}{\tau_D}\Bigr)^{-1}
                         \Bigl(1+\frac{\tau}{s^2\tau_D}\Bigr)^{-1/2}
    """
    t = np.asarray(tau_ms, dtype=float)
    return offset + 1.0 / abs(n) / (1.0 + t / tau_d_ms) / np.sqrt(1.0 + t / (s * s * tau_d_ms))


def _correlate(tttr: Any, info: Mapping, n_chunks: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The mean correlation of *info*'s photons over *n_chunks* equal parts of the measurement
    and its standard error: the cross-correlation of the parallel and the perpendicular channels
    (free of dead time and afterpulsing), else the autocorrelation of the one channel.

    The channels' masks are made once for the whole measurement and each part is a view of the
    arrays (no photon stream cut out per part); the correlator walks only the channels' photons
    (:func:`..burst_fcs_correlator.core.algorithms.correlate_masked`, the same curve)."""
    from tttrlib import micro_time_mask

    from chisurf.core.fluorescence.channels import channel_mask
    from chisurf.plugins.burst.burst_fcs_correlator.core.algorithms import correlate_masked

    chs = [int(c) for c in info.get("chs", [])]
    a, b = (chs[::2], chs[1::2]) if len(chs) >= 2 else (chs, chs)
    gates = [list(g) for g in (info.get("micro_time_ranges") or []) if g and len(g) >= 2]
    n = len(tttr)
    from chisurf.core.fio.photon_views import photon_column

    macro = photon_column(tttr, "macro_times")
    routing = photon_column(tttr, "routing_channels")
    in_gate = micro_time_mask(photon_column(tttr, "micro_times"), gates) if gates else None
    masks = []
    for group in (a, b):
        mask = channel_mask(routing, group)
        masks.append(np.logical_and(mask, in_gate) if in_gate is not None else mask)
    dt_ms = float(tttr.header.macro_time_resolution) * 1000.0
    edges = np.linspace(0, n, max(1, int(n_chunks)) + 1).astype(int)
    curves = []
    tau = None
    for start, stop in zip(edges[:-1], edges[1:]):
        if stop - start < 1000:
            continue
        part = slice(int(start), int(stop))
        lags, g = correlate_masked(macro[part], masks[0][part], masks[1][part], 8, 22)
        if lags is None:
            continue
        tau = np.asarray(lags, dtype=float) * dt_ms
        curves.append(np.asarray(g, dtype=float))
    if tau is None or not curves:
        return np.zeros(0), np.zeros(0), np.zeros(0)
    stack = np.vstack(curves)
    mean = stack.mean(axis=0)
    sem = stack.std(axis=0, ddof=1) / math.sqrt(len(curves)) if len(curves) > 1 else np.abs(mean) * 0.01
    return np.asarray(tau, dtype=float), mean, sem


def confocal_volume(
    paths: Iterable[str | Path],
    setup: Mapping,
    diffusion_um2_s: float,
    *,
    detector: str | None = None,
    detectors: Iterable[str] | None = None,
    fit_start_ms: float = 0.002,
    n_chunks: int = 10,
) -> dict[str, Any]:
    """The confocal volume from a reference dye of known diffusion coefficient.

    The dye's photons on *detector* (default: the detector of *detectors*, a colour's, with the
    most photons in its gate)
    are correlated (:func:`_correlate`) and :func:`diffusion_3d` is fitted, weighted by the
    standard error between the parts of the measurement, from *fit_start_ms* (past triplet and
    antibunching) to a twentieth of a part's duration. With the dye's ``D``:

    ``w0 = sqrt(4 D tau_D)``, ``z0 = s w0``, ``V_eff = pi^(3/2) w0^2 z0``, and the mean number
    of molecules ``N`` gives the dye's concentration ``N / (V_eff N_A)``.

    Returns
    -------
    dict
        ``detector``, ``D_um2_s``, ``N``, ``tau_d_ms``, ``s``, ``offset``, ``w0_um``, ``z0_um``,
        ``veff_fl``, ``concentration_nM``, ``chi2r``, ``counts`` and the curve (``tau_ms``,
        ``g``, ``sem``, ``model``).
    """
    from scipy.optimize import least_squares

    from chisurf.core.fluorescence.diffusion import effective_volume, lateral_waist

    paths = list(paths)
    subset = None if detectors is None else list(detectors)
    detectors = dict(setup.get("detectors") or {})
    if not paths or not detectors:
        raise ValueError("A reference-dye measurement and a detector setup are needed.")
    tttrs = [_open(p, setup) for p in paths]
    if detector is None:
        candidates = list(detectors) if subset is None else [d for d in subset if d in detectors]
        if not candidates:
            raise ValueError("No detector of this colour in the setup.")
        counts = {
            det: sum(int(np.count_nonzero(_in_gate_mask(t, detectors[det], 1, _n_raw(t)))) for t in tttrs)
            for det in candidates
        }
        detector = max(counts, key=counts.get)
    info = detectors[detector]
    taus, gs, sems = [], [], []
    seconds = 0.0
    for tttr in tttrs:
        tau, g, sem = _correlate(tttr, info, n_chunks)
        if tau.size:
            taus.append(tau)
            gs.append(g)
            sems.append(sem)
            seconds += _seconds(tttr)
    if not taus:
        raise ValueError(f"Too few photons of the reference dye on {detector} to correlate.")
    tau = taus[0]
    g = np.mean(gs, axis=0)
    sem = np.sqrt(np.sum(np.square(sems), axis=0)) / len(sems)
    part_ms = seconds / len(taus) / max(1, n_chunks) * 1e3
    keep = (tau >= fit_start_ms) & (tau <= part_ms / 20.0) & np.isfinite(g) & (sem > 0)
    if np.count_nonzero(keep) < 8:
        raise ValueError("The reference-dye correlation has too few points to fit.")
    t, y, e = tau[keep], g[keep], sem[keep]
    amplitude = max(float(np.median(y[:3])) - 1.0, 1e-3)
    half = t[np.argmin(np.abs(y - (1.0 + amplitude / 2.0)))]
    start = [1.0 / amplitude, float(half), 5.0, 1.0]

    def residual(p):
        return (diffusion_3d(t, *p) - y) / e

    fit = least_squares(
        residual, start, bounds=([1e-4, 1e-5, 1.0, 0.5], [1e5, 1e3, 30.0, 2.0])
    )
    n, tau_d, s, offset = (float(v) for v in fit.x)
    dof = max(1, t.size - 4)
    chi2r = float(np.sum(fit.fun ** 2) / dof)
    # standard errors from the curvature at the minimum, scaled by the reduced chi-square
    try:
        cov = np.linalg.inv(fit.jac.T @ fit.jac) * max(chi2r, 1.0)
        errors = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    except np.linalg.LinAlgError:
        errors = np.full(4, np.nan)
    e_n, e_tau, e_s, e_offset = (float(v) for v in errors)
    rate_khz = (
        sum(int(np.count_nonzero(_in_gate_mask(tt, info, 1, _n_raw(tt)))) for tt in tttrs) / seconds / 1e3
        if seconds > 0
        else float("nan")
    )
    tau_d_s = tau_d * 1e-3
    w0 = lateral_waist(tau_d_s, float(diffusion_um2_s))
    veff_m3 = effective_volume(tau_d_s, float(diffusion_um2_s) * 1e-12, s)
    veff_fl = veff_m3 * 1e18
    concentration = abs(n) / (veff_fl * 1e-15 * AVOGADRO) * 1e9 if veff_fl > 0 else float("nan")
    rel_tau = e_tau / tau_d if tau_d > 0 else float("nan")
    rel_s = e_s / s if s > 0 else float("nan")
    return {
        "detector": detector,
        "D_um2_s": float(diffusion_um2_s),
        "N": abs(n),
        "N_err": e_n,
        "tau_d_ms": tau_d,
        "tau_d_ms_err": e_tau,
        "s": s,
        "s_err": e_s,
        "offset": offset,
        "offset_err": e_offset,
        "w0_um": w0,
        "w0_um_err": w0 * rel_tau / 2.0,
        "z0_um": s * w0,
        "z0_um_err": s * w0 * math.hypot(rel_tau / 2.0, rel_s),
        "veff_fl": veff_fl,
        "veff_fl_err": veff_fl * math.hypot(1.5 * rel_tau, rel_s),
        "concentration_nM": concentration,
        # the count rate of the detector and the brightness of one molecule: setup quality
        "count_rate_khz": rate_khz,
        "brightness_khz": rate_khz / abs(n) if n else float("nan"),
        "chi2r": chi2r,
        "fit_range_ms": [float(t[0]), float(t[-1])],
        "tau_ms": tau.tolist(),
        "g": g.tolist(),
        "sem": sem.tolist(),
        "model": diffusion_3d(tau, n, tau_d, s, offset).tolist(),
    }


# -- IRF ---------------------------------------------------------------------------------------- #
def irf_fwhm(paths: Iterable[str | Path], setup: Mapping, *, detectors: Iterable[str] | None = None) -> dict[str, Any]:
    """The width of a scatter IRF: the full width at half maximum [ps] of the VV + VH decay of the
    detector (of *detectors*) with the most photons in its gate, at the full micro-time resolution,
    above the median floor of the gate."""
    from chisurf.plugins.burst.burst_mle_analysis.engine import vv_vh_histogram

    paths = list(paths)
    all_detectors = dict(setup.get("detectors") or {})
    wanted = list(all_detectors) if detectors is None else [d for d in detectors if d in all_detectors]
    best: tuple[float, str, np.ndarray, float] | None = None
    for det in wanted:
        info = all_detectors[det]
        total = None
        dt_ps = 0.0
        for path in paths:
            tttr = _open(path, setup)
            row = np.asarray(
                vv_vh_histogram(tttr, list(info.get("chs", [])), (0, 0), 1,
                                normalize_counts=0, apply_vh_shift=False, cut=False),
                dtype=float,
            )
            half = row.size // 2
            decay = row[:half] + row[half:] if len(info.get("chs", [])) >= 2 else row[:half]
            total = decay if total is None else total + decay
            dt_ps = float(tttr.header.micro_time_resolution) * 1e12
        if total is None:
            continue
        lo, hi = _gate(info, 1, total.size)
        gated = float(total[lo:hi].sum())
        if best is None or gated > best[0]:
            best = (gated, det, total[lo:hi], dt_ps)
    if best is None or best[0] <= 0:
        return {}
    _n, det, decay, dt_ps = best
    y = decay - float(np.median(decay))
    peak = int(np.argmax(y))
    half = y[peak] / 2.0
    if half <= 0:
        return {}
    left = peak
    while left > 0 and y[left - 1] > half:
        left -= 1
    right = peak
    while right < y.size - 1 and y[right + 1] > half:
        right += 1
    # linear interpolation of the two half-maximum crossings
    x_left = left - (y[left] - half) / (y[left] - y[left - 1]) if left > 0 and y[left] != y[left - 1] else float(left)
    x_right = (
        right + (y[right] - half) / (y[right] - y[right + 1])
        if right < y.size - 1 and y[right] != y[right + 1]
        else float(right)
    )
    return {"detector": det, "fwhm_ps": float((x_right - x_left) * dt_ps), "counts": float(decay.sum())}


# -- everything a set of samples gives ---------------------------------------------------------- #
def calibrate(
    rows: Mapping[str, str],
    setup: Mapping,
    *,
    dyes: Mapping[str, Mapping] | None = None,
    progress=None,
) -> dict[str, Any]:
    """The calibrations the files of *rows* (``{path: row key}``, :func:`row_keys`) give with the
    detector *setup*.

    Returns
    -------
    dict
        ``buffer`` (:func:`buffer_rates` of every detector, with its ``files``) and ``colours``:
        per colour with reference-dye files, ``g_factor`` (:func:`reference_g_factors` of its
        detectors), ``volume`` (:func:`confocal_volume` with the ``D`` of the colour's dye in
        *dyes*, :func:`dye_diffusion`), the ``dye`` and the ``D_source``, and its ``files``; what
        could not be computed is said in ``errors``. *progress* is told what is being computed.
    """
    with _one_read_per_file():
        return _calibrate(rows, setup, dyes=dyes, progress=progress)


def _calibrate(rows, setup, *, dyes=None, progress=None) -> dict[str, Any]:
    """:func:`calibrate`, each file read once."""
    say = progress if callable(progress) else (lambda _text: None)
    dyes = dict(dyes or {})
    groups = {g["colour"]: g for g in colour_groups(setup)}
    shown = {path: resolve_row(key, setup, path) for path, key in rows.items()}
    buffers = [p for p, key in shown.items() if key == "buffer"]
    out: dict[str, Any] = {"errors": [], "colours": {}}
    if not groups:
        if any(kind_of(k) != "measurement" for k in rows.values()):
            out["errors"].append("Choose a detector setup (step 0) to calibrate with these files.")
        return out
    if buffers:
        say("Background rates from the buffer …")
        try:
            out["buffer"] = {"files": [str(p) for p in buffers], "rates": buffer_rates(buffers, setup)}
        except Exception as exc:  # noqa: BLE001 - reported beside the other results
            out["errors"].append(f"Buffer: {exc}")
    out["irf"] = {}
    for colour, group in groups.items():
        irf_files = [p for p, key in shown.items() if key == f"irf:{colour}"]
        if irf_files:
            say("Width of the IRF …")
            try:
                out["irf"][colour] = {"files": [str(p) for p in irf_files],
                                      **irf_fwhm(irf_files, setup, detectors=group["detectors"])}
            except Exception as exc:  # noqa: BLE001
                out["errors"].append(f"IRF ({group['word']}): {exc}")
    for colour, group in groups.items():
        files = [p for p, key in shown.items() if key == f"reference:{colour}"]
        if not files:
            continue
        word = group["word"]
        choice = dyes.get(colour) or dict(
            zip(("dye", "how"), infer_dye(files, colour, list(groups)))
        )
        d, source = dye_diffusion(choice, colour)
        entry: dict[str, Any] = {
            "files": [str(p) for p in files],
            "dye": dye_choice(choice, colour),
            "D_um2_s": d,
            "D_source": source,
        }
        say(f"G factor of the {word} detectors from the reference dye …")
        try:
            entry["g_factor"] = reference_g_factors(files, setup, detectors=group["detectors"])
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"G factor ({word}): {exc}")
        say(f"Correlating the {word} reference dye, fitting its confocal volume …")
        try:
            if not (d == d and d > 0):
                raise ValueError(f"no diffusion coefficient ({source})")
            entry["volume"] = confocal_volume(files, setup, d, detectors=group["detectors"])
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"Confocal volume ({word}): {exc}")
        out["colours"][colour] = entry
    return out
