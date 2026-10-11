"""What the PDA reader reads: detector rows, time windows, burst tables and input files.

Everything here is plain data in, plain data out -- no widget, no window. The
reader (:class:`~chisurf.core.experiments.pda2c.Pda2cReader`) resolves its
inputs with it, :class:`~chisurf.core.experiments.pda2c.settings.PdaReaderSettings`
binds a settings form to it, and both the Qt panel and the emtk form draw that.

Three things decide which photons become a PDA histogram:

* **the detector rows** -- one routing-channel group per colour, and a
  micro-time window per detector (two colours) or per excitation period of the
  PIE cycle (three colours);
* **the time windows** -- ``(minimum photons, minimum duration)`` pairs; each
  one is read as a dataset of its own;
* **the inputs** -- TTTR files, ``.bur`` burst tables, or burst-analysis
  folders. A ``.bur`` names, per burst, the measurement file and its first and
  last photon, so it selects exactly those photons; a TTTR file with a
  ``bi4_bur`` (or ``bur``) folder beside it is read burst-wise from the tables
  in that folder.
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

import numpy as np

from chisurf import logging

#: Row label per detection colour, by colour count. Two-colour PDA counts a
#: green and a red channel; three-colour adds the blue donor.
COLOUR_LABELS = {2: ("Green", "Red"), 3: ("Blue", "Green", "Red")}

#: Detector name preferred for each row when the selected setup defines one.
COLOUR_DEFAULTS = {2: ("green", "red"), 3: ("blue", "green", "red")}

#: Default routing channels per row, used when the reader has none.
COLOUR_CHANNELS = {2: ("0,3", "1,2"), 3: ("0", "1", "2")}

#: Default micro-time windows per row (two colours) and the two excitation
#: periods of the PIE cycle (three colours).
COLOUR_WINDOWS = {2: ("1-16000", "1-16000"), 3: ("0-8000", "8000-16000")}

#: Labels of the two excitation periods of a three-colour PIE cycle.
EXCITATION_LABELS = ("Blue", "Green")

#: Burst tables and burst-identifier files a file list accepts beside TTTR files.
BURST_EXTENSIONS = frozenset({".bid", ".bur", ".bst"})

#: TTTR extensions assumed when tttrlib cannot be asked.
FALLBACK_TTTR_EXTENSIONS = frozenset({".ptu", ".ht3", ".spc", ".h5", ".hdf5"})

#: Folder names a burst analysis writes its ``.bur`` tables to.
BUR_FOLDERS = ("bi4_bur", "bur")

#: The most ``.bur`` tables, and TTTR files, one read takes. More is refused
#: (tables) or cut (files): reading thousands of measurements in one go is a
#: batch job, not a read.
MAX_FILES = 1024

#: The time windows a new PDA reader starts with: ``(minimum photons, seconds)``.
DEFAULT_TW_CONFIGS = ((10, 1e-3), (20, 2e-3), (30, 3e-3))

#: The four ``.bur`` columns a burst slice needs, lower-cased. A burst table's
#: header capitalisation varies between the programs that write one, so every
#: lookup here is case-insensitive.
_BUR_REQUIRED = ("first photon", "last photon", "first file", "last file")


class PdaInputError(ValueError):
    """The inputs cannot be read as they are; ``title`` names the problem, the message explains it."""

    def __init__(self, title: str, message: str) -> None:
        super().__init__(message)
        self.title = title


# ── detector rows ────────────────────────────────────────────────────────────


def colour_count(value: Any) -> int:
    """Return 3 for a three-colour setting and 2 for anything else."""
    try:
        return 3 if int(value or 2) >= 3 else 2
    except (TypeError, ValueError):
        return 2


def parse_micro_time_ranges(text: str) -> list:
    """Parse ``"start-end;start-end"`` into a list of ``[start, end]`` pairs.

    Parameters
    ----------
    text : str
        Field content. Empty or unparsable segments are skipped.

    Returns
    -------
    list of list of int
        The parsed windows, in the order they were written.
    """
    text = (text or "").strip()
    if not text:
        return []
    windows = []
    for segment in text.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        try:
            bounds = [int(j) for j in segment.split("-")]
        except ValueError:
            continue
        if len(bounds) >= 2:
            windows.append([bounds[0], bounds[1]])
    return windows


def format_micro_time_ranges(value: Any) -> str:
    """Render a micro-time window as the ``"start-end;start-end"`` a field shows.

    Accepts a single ``(start, stop)`` pair, a list of them, or a bare integer
    (mirroring ``PhotonFilter.update_pie_windows``).

    Parameters
    ----------
    value : tuple or list or int
        The window(s) to render.

    Returns
    -------
    str
        Field text; empty when *value* describes no window.
    """
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and all(isinstance(x, (int, np.integer)) for x in value):
            return f"{int(value[0])}-{int(value[1])}"
        parts = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                parts.append(f"{int(item[0])}-{int(item[1])}")
            elif isinstance(item, (int, np.integer)):
                parts.append(f"{int(item)}-{int(item)}")
        return ";".join(parts)
    if isinstance(value, (int, np.integer)):
        return f"{int(value)}-{int(value)}"
    return ""


def parse_channels(text: str) -> list[int]:
    """Parse ``"0, 3"`` into routing channels; tokens that are not integers are skipped."""
    channels = []
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            channels.append(int(part))
        except ValueError:
            continue
    return channels


def format_channels(group: Any) -> str:
    """Render a routing-channel group as the ``"0, 3"`` a field shows."""
    try:
        return ", ".join(str(int(c)) for c in list(group or []))
    except (TypeError, ValueError):
        return ""


def preferred_detectors(detectors: Mapping, n_colors: int) -> list[str]:
    """Choose one detector of a setup per colour row.

    A row takes the detector named after its colour (``green``, ``red``,
    ``blue``) when the setup has one, else the setup's detectors in their
    declared order -- so two rows never silently point at the same channels.

    Parameters
    ----------
    detectors : mapping
        The setup's detectors by name.
    n_colors : int
        2 or 3.

    Returns
    -------
    list of str
        One detector name per row; empty strings when the setup has none.
    """
    names = [str(n) for n in detectors]
    rows = COLOUR_DEFAULTS[colour_count(n_colors)]
    if not names:
        return ["" for _ in rows]
    return [
        wanted if wanted in names else names[min(index, len(names) - 1)]
        for index, wanted in enumerate(rows)
    ]


# ── time windows ─────────────────────────────────────────────────────────────


def tw_label(n_ph: int, tw_s: float) -> str:
    """The text of one time-window entry: ``"10 ph @ 1 ms"``."""
    return f"{int(n_ph)} ph @ {float(tw_s) * 1e3:g} ms"


def valid_tw_configs(configs: Iterable | None) -> list[tuple[int, float]]:
    """Return the usable ``(photons, seconds)`` pairs of *configs*, in order.

    An entry that is not a pair of numbers, or has a photon count or duration
    that is not positive, is dropped: the reader would skip it anyway.
    """
    out = []
    for cfg in configs or ():
        try:
            n_ph, tw_s = int(cfg[0]), float(cfg[1])
        except (TypeError, ValueError, IndexError):
            continue
        if n_ph > 0 and tw_s > 0.0:
            out.append((n_ph, tw_s))
    return out


def add_tw_config(configs: Iterable | None, n_ph: int, tw_s: float) -> list[tuple[int, float]]:
    """Return *configs* with ``(n_ph, tw_s)`` appended unless it is already there or not valid."""
    out = valid_tw_configs(configs)
    entry = valid_tw_configs([(n_ph, tw_s)])
    if entry and entry[0] not in out:
        out.append(entry[0])
    return out


# ── input files ──────────────────────────────────────────────────────────────


def tttr_extensions() -> frozenset[str]:
    """The lower-case, dot-prefixed file extensions tttrlib reads."""
    exts = set()
    try:
        import tttrlib

        if hasattr(tttrlib, "get_supported_filetypes"):
            for ext in tttrlib.get_supported_filetypes():
                text = str(ext).strip().lower()
                if text:
                    exts.add(text if text.startswith(".") else "." + text)
    except Exception:  # noqa: BLE001 - no tttrlib: the fallback list
        exts = set()
    return frozenset(exts or FALLBACK_TTTR_EXTENSIONS)


def accepted_extensions(tttr_exts: Iterable[str] | None = None) -> frozenset[str]:
    """The extensions a PDA file list takes: TTTR files and burst tables."""
    exts = tttr_extensions() if tttr_exts is None else tttr_exts
    return frozenset(e.lower() for e in exts) | BURST_EXTENSIONS


def accepts_path(path: str | pathlib.Path, accepted: Iterable[str] | None = None) -> bool:
    """Whether a file list takes *path*: a folder, or a file with an accepted extension."""
    p = pathlib.Path(path)
    if p.is_dir():
        return True
    if not p.is_file():
        return False
    exts = accepted_extensions() if accepted is None else accepted
    return not exts or p.suffix.lower() in exts


def split_filenames(filename: Any) -> list[str]:
    """Return the paths in *filename*: a path, a ``|``-joined list of paths, or a sequence."""
    if filename is None:
        return []
    if isinstance(filename, (str, pathlib.Path)):
        return [part for part in str(filename).split("|") if part.strip()]
    return [str(p) for p in filename if str(p).strip()]


def expand_burst_folder(base_dir: str | pathlib.Path) -> list[str]:
    """Return the ``.bur`` tables of a burst-analysis folder, sorted.

    Tables directly in the folder win; without any, the folder is searched
    recursively. The paths are not resolved: on Windows that would turn a
    mapped drive (``P:\\``) into a UNC path the user never typed.
    """
    base = pathlib.Path(base_dir)
    try:
        if not base.is_dir():
            return []
        found = [p for p in base.glob("*.bur") if p.is_file()]
        if not found:
            found = [p for p in base.rglob("*.bur") if p.is_file()]
        return [str(p) for p in sorted(found)]
    except OSError:
        logging.warning("PDA: Error expanding burst folder: %s", str(base), exc_info=True)
        return []


def classify_inputs(
    paths: Iterable[str], tttr_exts: Iterable[str] | None = None
) -> tuple[list[str], list[str]]:
    """Split inputs into ``.bur`` tables and TTTR files; a folder contributes its tables.

    Parameters
    ----------
    paths : iterable of str
        Files and folders, as a file list holds them.
    tttr_exts : iterable of str, optional
        TTTR extensions; tttrlib's by default.

    Returns
    -------
    tuple of (list of str, list of str)
        The burst tables and the TTTR files, each sorted and unique. Anything
        else (a ``.bid``, an unknown extension, a path that does not exist) is
        neither.
    """
    exts = tttr_extensions() if tttr_exts is None else frozenset(tttr_exts)
    bur_files, tttr_files = set(), set()
    for path in paths:
        p = pathlib.Path(path)
        if p.is_dir():
            bur_files.update(expand_burst_folder(p))
        elif not p.is_file():
            continue
        elif p.suffix.lower() == ".bur":
            bur_files.add(str(p))
        elif p.suffix.lower() in exts:
            tttr_files.add(str(p))
    return sorted(bur_files), sorted(tttr_files)


def read_bur_bursts(path):
    """Return ``(file names, starts, stops)`` for the usable bursts of a ``.bur``.

    One reader for every caller, and the only place that knows the format's
    quirks:

    * the header's capitalisation is not fixed, so columns are matched
      lower-cased;
    * a burst whose ``First File`` and ``Last File`` disagree spans two
      measurements and has no single photon stream to slice, so it is dropped --
      as is a burst naming no file at all;
    * the interleaved separator rows (and the sentinel row of a skipped burst)
      are all zeros -- ``First File`` and ``Last File`` both read ``0`` -- so
      they name a "file" and would slice photon 0 as a one-photon burst. A row
      whose ``Number of Photons`` is not positive is no burst and is dropped;
    * ``Last Photon`` is inclusive in the format and exclusive in a Python
      slice, hence ``stop = last + 1``.

    Parameters
    ----------
    path : pathlib.Path
        The ``.bur`` file.

    Returns
    -------
    tuple of (numpy.ndarray, numpy.ndarray, numpy.ndarray) or None
        File names as text, and integer start/stop photon indices. ``None`` when
        the file cannot be read or does not carry the four columns.
    """
    from chisurf.core.datastore import column_values, read_csv_table

    store = read_csv_table(path, delimiter="\t")
    if store is None:
        return None
    # np.array, not np.asarray: these outlive the store, which dies here.
    columns = {
        str(store[i].name()).strip().lower(): np.array(column_values(store, i))
        for i in range(store.n_columns())
    }
    if not all(name in columns for name in _BUR_REQUIRED):
        return None

    first_file = np.array([str(v).strip() for v in columns["first file"]], dtype=object)
    last_file = np.array([str(v).strip() for v in columns["last file"]], dtype=object)
    keep = (first_file == last_file) & (first_file != "")
    if "number of photons" in columns:
        try:
            n_photons = np.asarray(columns["number of photons"], dtype=float)
        except (TypeError, ValueError):
            n_photons = None
        if n_photons is not None:
            keep &= n_photons > 0
    if not keep.any():
        return None

    try:
        starts = np.asarray(columns["first photon"], dtype=float)[keep].astype(np.int64)
        stops = np.asarray(columns["last photon"], dtype=float)[keep].astype(np.int64) + 1
    except (TypeError, ValueError):
        return None
    return first_file[keep], starts, stops


def merge_intervals(mapping: Mapping | None) -> dict:
    """Merge overlapping or touching ``[start, stop)`` intervals per key.

    Parameters
    ----------
    mapping : mapping of str to sequence of (int, int)
        Photon intervals per file.

    Returns
    -------
    dict
        The same keys, each with sorted, disjoint intervals; keys without any
        interval are dropped.
    """
    merged = {}
    for key, intervals in (mapping or {}).items():
        if not intervals:
            continue
        ordered = sorted(intervals, key=lambda x: (int(x[0]), int(x[1])))
        out = []
        start, stop = ordered[0]
        for s, e in ordered[1:]:
            if s <= stop:  # overlap or directly adjacent (exclusive stop)
                stop = max(stop, e)
            else:
                out.append((start, stop))
                start, stop = s, e
        out.append((start, stop))
        merged[key] = out
    return merged


def find_bur_dir(tttr_path: str | pathlib.Path) -> pathlib.Path | None:
    """The burst-table folder of a TTTR file: ``bi4_bur`` or ``bur``, up to three levels up."""
    path = pathlib.Path(tttr_path)
    for up in (path.parent, path.parent.parent, path.parent.parent.parent):
        for name in BUR_FOLDERS:
            if (up / name).is_dir():
                return up / name
        # the TTTR file may sit in the burst folder itself
        if up.name.lower() in BUR_FOLDERS:
            return up
    return None


def burst_slices_near(tttr_files: Sequence[str]) -> dict:
    """Photon intervals of the bursts the tables beside *tttr_files* name.

    Every ``.bur`` of each file's burst folder (:func:`find_bur_dir`) is read;
    a burst is kept for the TTTR file whose name -- or, failing that, stem --
    its ``First File`` names. Bursts spanning two files are dropped by
    :func:`read_bur_bursts`.

    Returns
    -------
    dict
        ``{tttr path: [(start, stop), ...]}`` with merged intervals; empty when
        no burst folder is found.
    """
    tables: dict[str, list[pathlib.Path]] = {}
    for f in tttr_files:
        bur_dir = find_bur_dir(f)
        if bur_dir is not None and str(bur_dir) not in tables:
            tables[str(bur_dir)] = sorted(bur_dir.glob("*.bur"))
    if not tables:
        return {}
    by_name = {pathlib.Path(f).name: f for f in tttr_files}
    by_stem: dict[str, str] = {}
    for known in by_name:
        by_stem.setdefault(pathlib.Path(known).stem, known)
    slices: dict[str, list] = {}
    for bur_list in tables.values():
        for bur_path in bur_list:
            bursts = read_bur_bursts(bur_path)
            if bursts is None:
                continue
            for first_file, start, stop in zip(*bursts):
                name: str | None = (
                    first_file
                    if first_file in by_name
                    else by_stem.get(pathlib.Path(first_file).stem)
                )
                if name is None:
                    logging.debug(
                        "PDA: TTTR file referenced in BUR not among the selected files: %s (BUR: %s)",
                        first_file,
                        str(bur_path),
                    )
                    continue
                slices.setdefault(by_name[name], []).append((int(start), int(stop)))
    return merge_intervals(slices)


def _analysis_root(bur_path: pathlib.Path) -> pathlib.Path:
    """One level above ``bi4_bur``/``bur``, else the table's own folder."""
    return (
        bur_path.parent.parent if bur_path.parent.name.lower() in BUR_FOLDERS else bur_path.parent
    )


def _search_roots(root_hint: pathlib.Path) -> list[pathlib.Path]:
    """Where the TTTR files of an analysis root may be: it and two ancestors, an ``hdf5`` sibling first."""
    roots, seen = [], set()
    for base in (root_hint, root_hint.parent, root_hint.parent.parent):
        if not base.exists():
            continue
        hdf5 = base / "hdf5"
        if hdf5.is_dir() and str(hdf5) not in seen:
            roots.append(hdf5)
            seen.add(str(hdf5))
        if str(base) not in seen:
            roots.append(base)
            seen.add(str(base))
    return roots


def _resolve_name(name: str, roots: Sequence[pathlib.Path], exts) -> pathlib.Path | None:
    """A TTTR file named in a table: absolute, joined to a root, or the same stem with a TTTR extension."""
    if not name:
        return None
    candidate = pathlib.Path(name)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    stem = candidate.stem
    for root in roots:
        if (root / name).is_file():
            return root / name
        for ext in exts:
            if (root / f"{stem}{ext}").is_file():
                return root / f"{stem}{ext}"
    return None


def resolve_bur_files(
    bur_files: Sequence[str],
    tttr_exts: Iterable[str] | None = None,
    progress: Callable[[int, int, str], Any] | None = None,
) -> tuple[list[str], dict]:
    """The TTTR files and photon intervals selected burst tables name.

    A table is matched first by its own stem (``m000.bur`` → ``m000.spc``, the
    usual MFD layout), else by the ``First File`` of each burst. The TTTR files
    are searched near the table only -- its analysis root (one level above
    ``bi4_bur``/``bur``) and two ancestors, an ``hdf5`` sibling first -- never
    recursively; once one table of an analysis root resolved, the others reuse
    that folder. A ``First File`` that is a bare number is an index some tools
    write, not a file name, and is not resolved.

    Parameters
    ----------
    bur_files : sequence of str
        The tables.
    tttr_exts : iterable of str, optional
        TTTR extensions; tttrlib's by default.
    progress : callable, optional
        ``progress(i, total, path)`` before each table; returning ``False``
        stops resolving (a cancelled progress dialog).

    Returns
    -------
    tuple of (list of str, dict)
        The TTTR files in the order first resolved, and
        ``{tttr path: [(start, stop), ...]}`` with merged intervals.
    """
    exts = tuple(sorted(tttr_extensions() if tttr_exts is None else tttr_exts))
    files: list[str] = []
    slices: dict[str, list] = {}
    roots_cache: dict[str, list[pathlib.Path]] = {}
    preferred: dict[str, pathlib.Path] = {}

    def add(path: pathlib.Path, starts, stops) -> None:
        key = str(path)
        pairs = list(zip(np.asarray(starts).tolist(), np.asarray(stops).tolist()))
        if not pairs:
            return
        slices.setdefault(key, []).extend(pairs)
        if key not in files:
            files.append(key)

    total = len(bur_files)
    for index, bur in enumerate(bur_files, start=1):
        if callable(progress) and progress(index, total, bur) is False:
            break
        bur_path = pathlib.Path(bur)
        if not bur_path.is_file():
            continue
        bursts = read_bur_bursts(bur_path)
        if bursts is None:
            continue
        names, starts, stops = bursts
        root = _analysis_root(bur_path)
        key = str(root)
        if key in preferred:
            roots = [preferred[key]]
        else:
            roots = roots_cache.setdefault(key, _search_roots(root))
        if not roots:
            logging.warning("PDA: No TTTR search roots for BUR file %s; skipping it.", bur)
            continue

        candidates = (r / f"{bur_path.stem}{e}" for r in roots for e in exts)
        own = next((c for c in candidates if c.is_file()), None)
        if own is not None:
            preferred.setdefault(key, own.parent)
            add(own, starts, stops)
            continue

        resolved: dict[str, str | None] = {}
        for name in dict.fromkeys(names):
            path = None if str(name).strip().isdigit() else _resolve_name(name, roots, exts)
            resolved[name] = str(path) if path is not None else None
            if path is not None:
                preferred.setdefault(key, path.parent)
        targets = np.array([resolved.get(n) for n in names], dtype=object)
        valid = np.array([t is not None for t in targets], dtype=bool)
        if not valid.any():
            for name, found in resolved.items():
                if found is None and name and not str(name).strip().isdigit():
                    logging.warning(
                        "PDA: TTTR file '%s' named in BUR '%s' was not found; skipping its bursts.",
                        name,
                        bur,
                    )
            continue
        for target in dict.fromkeys(targets[valid]):
            group = targets == target
            add(pathlib.Path(target), starts[group], stops[group])
    return files, merge_intervals(slices)


@dataclasses.dataclass
class ResolvedInputs:
    """The TTTR files a read takes and the photon intervals of each, with what was cut or ignored.

    Attributes
    ----------
    tttr_files : list of str
        The measurements to read.
    burst_slices : dict
        ``{tttr path: [(start, stop), ...]}``; empty to read the whole files.
    warnings : list of (str, str)
        ``(title, message)`` of every limit that cut the inputs.
    """

    tttr_files: list[str]
    burst_slices: dict
    warnings: list[tuple[str, str]] = dataclasses.field(default_factory=list)


def check_input_counts(
    bur_files: Sequence[str], tttr_files: Sequence[str], limit: int = MAX_FILES
) -> tuple[list[str], list[tuple[str, str]]]:
    """Refuse too many tables or nothing to read; cut too many TTTR files.

    Returns
    -------
    tuple of (list of str, list of (str, str))
        The TTTR files kept, and a ``(title, message)`` for a cut.

    Raises
    ------
    PdaInputError
        For more than *limit* tables, or neither a table nor a TTTR file.
    """
    warnings = []
    if len(bur_files) > limit:
        raise PdaInputError(
            "Too many BUR files",
            f"You selected {len(bur_files)} BUR files. For stability, please process them in "
            f"smaller batches (<= {limit} at once).",
        )
    tttr_files = list(tttr_files)
    if len(tttr_files) > limit:
        warnings.append(
            (
                "Too many files",
                f"You selected {len(tttr_files)} TTTR files. For stability, only the first "
                f"{limit} will be loaded.\n\nConsider using BUR tables or smaller batches if you "
                "need to process more files.",
            )
        )
        tttr_files = tttr_files[:limit]
    if not bur_files and not tttr_files:
        raise PdaInputError(
            "No files",
            "Please drop .bur burst files or TTTR files (e.g., .ptu, .ht3, .spc, .sdt, .t3r, "
            ".t2r, .phu, .phd) to load.",
        )
    return tttr_files, warnings


def resolve_classified(
    bur_files: Sequence[str],
    tttr_files: Sequence[str],
    tttr_exts: Iterable[str] | None = None,
    progress: Callable[[int, int, str], Any] | None = None,
    limit: int = MAX_FILES,
) -> ResolvedInputs:
    """Resolve classified inputs: tables name their files; without tables, look beside the files.

    With any ``.bur`` table, the TTTR files the tables name are read and the
    TTTR files given directly are not (the tables say which photons). Without
    one, each TTTR file is read burst-wise from the tables of its burst folder
    (:func:`burst_slices_near`), or whole when it has none.

    Raises
    ------
    PdaInputError
        When tables were given but name no TTTR file that exists.
    """
    warnings: list[tuple[str, str]] = []
    if bur_files:
        files, slices = resolve_bur_files(bur_files, tttr_exts, progress)
        if len(files) > limit:
            warnings.append(
                (
                    "Too many files",
                    f"Burst tables reference {len(files)} TTTR files. For stability, only the "
                    f"first {limit} will be loaded.",
                )
            )
            files = files[:limit]
            slices = {k: v for k, v in slices.items() if k in set(files)}
        if not files:
            raise PdaInputError(
                "No TTTR files found",
                "Could not resolve any TTTR files from the selected BUR files.",
            )
        return ResolvedInputs(list(files), slices, warnings)
    files = list(tttr_files)
    return ResolvedInputs(files, burst_slices_near(files), warnings)


def resolve_inputs(
    paths: Iterable[str],
    tttr_exts: Iterable[str] | None = None,
    progress: Callable[[int, int, str], Any] | None = None,
    limit: int = MAX_FILES,
) -> ResolvedInputs:
    """Resolve files and folders into the TTTR files and photon intervals a PDA read takes.

    :func:`classify_inputs`, :func:`check_input_counts` and
    :func:`resolve_classified` in one call.

    Raises
    ------
    PdaInputError
        When there is nothing to read, too many tables, or tables that name no
        existing measurement.
    """
    exts = tttr_extensions() if tttr_exts is None else frozenset(tttr_exts)
    bur_files, tttr_files = classify_inputs(paths, exts)
    tttr_files, warnings = check_input_counts(bur_files, tttr_files, limit)
    resolved = resolve_classified(bur_files, tttr_files, exts, progress, limit)
    resolved.warnings[:0] = warnings
    for title, message in resolved.warnings:
        logging.warning("PDA: %s: %s", title, message)
    return resolved


__all__ = [
    "BURST_EXTENSIONS",
    "BUR_FOLDERS",
    "COLOUR_CHANNELS",
    "COLOUR_DEFAULTS",
    "COLOUR_LABELS",
    "COLOUR_WINDOWS",
    "DEFAULT_TW_CONFIGS",
    "EXCITATION_LABELS",
    "MAX_FILES",
    "PdaInputError",
    "ResolvedInputs",
    "accepted_extensions",
    "accepts_path",
    "add_tw_config",
    "burst_slices_near",
    "check_input_counts",
    "classify_inputs",
    "colour_count",
    "expand_burst_folder",
    "find_bur_dir",
    "format_channels",
    "format_micro_time_ranges",
    "merge_intervals",
    "parse_channels",
    "parse_micro_time_ranges",
    "preferred_detectors",
    "read_bur_bursts",
    "resolve_bur_files",
    "resolve_classified",
    "resolve_inputs",
    "split_filenames",
    "tttr_extensions",
    "tw_label",
    "valid_tw_configs",
]
