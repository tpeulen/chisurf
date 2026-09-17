"""ebFRET's file formats: raw traces, SF-Tracer, SMD, sessions, reports and exports.

A port of ebFRET's ``+ebfret/+io`` package together with the three places the
main window reads and writes files itself -- ``load_data.m`` (session and
trace import), ``save_data.m`` (the session ``.mat``) and ``export_traces.m``
(the ``.dat``/``.mat`` trace table). Every reader and writer here produces or
consumes the objects of :mod:`~chisurf.plugins.burst.burst_ebfret.core.model`.

The goal is that a file moves between ebFRET and ChiSurf in both directions:

* a session saved by ebFRET loads here, and a session saved here loads in
  ebFRET (the ``.mat`` variables, struct fields and array orientations are the
  ones ``save_data.m`` writes);
* an SMD written here is read by ebFRET's ``load_json``/``load`` and the
  other way round (JSON is laid out the way JSONlab's ``savejson`` lays it out:
  tab indentation, column vectors as ``[[v],[v]]``, ``%.10g`` numbers);
* the trace table and the analysis summary are byte-for-byte what MATLAB
  writes.

Where the reference has a bug that would corrupt a file, the port fixes it and
says so in the docstring of the function concerned; where a difference cannot
be avoided (the MD5 ids of an SMD), that is said too.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import warnings
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .core.model import COLORS, Analysis, Controls, Expect, HmmParams, Series, Viterbi

__all__ = [
    "EPS",
    "format_label",
    "file_base",
    "load_raw",
    "load_sf_tracer",
    "load_smd",
    "series_from_raw",
    "series_from_smd",
    "smd_create",
    "build_smd",
    "write_smd",
    "save_session",
    "load_session",
    "write_report",
    "format_report",
    "export_traces",
    "savejson",
    "load_stacked_dat",
    "fret_efficiency",
]

#: MATLAB's ``eps``, which ``load_data.m`` adds to numerator and denominator.
EPS = float(np.finfo(float).eps)

_HMM_FIELDS = ("pi", "A", "mu", "beta", "W", "nu")
_EXPECT_FIELDS = ("z", "z1", "zz", "x", "xx")
_SMD_COLUMNS = ("donor", "acceptor", "fret", "viterbi_state", "viterbi_mean")


# --------------------------------------------------------------------------- #
# MATLAB number formatting
# --------------------------------------------------------------------------- #
def _matlab_special(value: float) -> str | None:
    """MATLAB's spelling of a non-finite number, or ``None`` for a finite one."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Inf" if value > 0 else "-Inf"
    return None


def format_label(value: Any) -> str:
    """Format a numeric trace label the way MATLAB's ``sprintf('%d', l)`` does.

    ``load_data.m`` turns the numeric labels of raw data into strings with
    ``%d``. MATLAB prints an integer-valued double as an integer, and silently
    switches ``%d`` to ``%e`` for any other value -- which is why a session of
    ebFRET's own simulated dataset carries labels such as ``'1.760332e+02'``
    (the label row of a stacked file holds a donor intensity, not an id).
    GNU Octave prints those as ``'176.033'`` instead; this follows MATLAB, the
    program that wrote the sessions people have.

    Parameters
    ----------
    value : float or int
        The label.

    Returns
    -------
    str
    """
    if isinstance(value, str):
        return value
    value = float(value)
    special = _matlab_special(value)
    if special is not None:
        return special
    if value == int(value):
        return str(int(value))
    return f"{value:e}"


def _fmt_e(value: float, spec: str) -> str:
    """``spec % value`` with MATLAB's ``NaN``/``Inf`` spelling."""
    special = _matlab_special(float(value))
    if special is None:
        return spec % float(value)
    # MATLAB right-aligns NaN/Inf in a field of the conversion's width.
    width = re.match(r"%(\d*)", spec).group(1)
    return special.rjust(int(width)) if width else special


def file_base(path: str) -> str:
    """The ``name`` of MATLAB's ``[~, name] = fileparts(path)``.

    Only the **last** extension is removed, so ``'x.json.gz'`` gives
    ``'x.json'`` -- which is what ebFRET stores as ``series(n).file``.

    Parameters
    ----------
    path : str
        A file path.

    Returns
    -------
    str
    """
    return os.path.splitext(os.path.basename(str(path)))[0]


# --------------------------------------------------------------------------- #
# MAT-file helpers
# --------------------------------------------------------------------------- #
def _mat_to_py(value: Any) -> Any:
    """Turn a ``scipy.io.loadmat`` value into plain Python / NumPy.

    Structs become ``dict`` (1x1) or ``list`` of ``dict`` (struct arrays),
    cell arrays become ``list``, char arrays ``str`` and numeric arrays keep
    their MATLAB 2-D shape as ``float`` arrays (logical stays ``bool``).
    """
    if isinstance(value, np.ndarray):
        if value.dtype.names is not None:
            items = [
                {name: _mat_to_py(entry[name]) for name in value.dtype.names}
                for entry in value.ravel(order="F")
            ]
            return items[0] if value.size == 1 else items
        if value.dtype == object:
            return [_mat_to_py(entry) for entry in value.ravel(order="F")]
        if value.dtype.kind == "U":
            return "".join(value.ravel().tolist()) if value.size else ""
        if value.dtype.kind == "b":
            return value.astype(bool)
        return value.astype(float)
    return value


def _loadmat(path: str) -> dict:
    """Read a MAT-file into plain Python values, without the ``__`` entries."""
    import scipy.io as sio

    raw = sio.loadmat(path, squeeze_me=False, struct_as_record=True, mat_dtype=False)
    return {k: _mat_to_py(v) for k, v in raw.items() if not k.startswith("__")}


def _is_empty(value: Any) -> bool:
    """MATLAB's ``isempty`` for a converted MAT value."""
    if value is None:
        return True
    if isinstance(value, (str, list, tuple, dict)):
        return len(value) == 0
    return np.asarray(value).size == 0


def _scalar(value: Any, default: float = 0.0) -> float:
    """The single number of a MAT value, or *default* when it is empty."""
    if _is_empty(value):
        return default
    return float(np.asarray(value, dtype=float).ravel()[0])


def _vector(value: Any) -> np.ndarray:
    """A MAT vector as a 1-D float array."""
    if _is_empty(value):
        return np.zeros(0)
    return np.asarray(value, dtype=float).ravel(order="F")


def _col(values: Any) -> np.ndarray:
    """A 1-D array as a MATLAB column vector ``(n, 1)``."""
    return np.asarray(values, dtype=float).reshape(-1, 1)


def _struct_array(records: Sequence[Mapping], fields: Sequence[str]) -> np.ndarray:
    """A ``1 x N`` MATLAB struct array for ``scipy.io.savemat``."""
    out = np.empty((1, len(records)), dtype=[(name, object) for name in fields])
    for i, record in enumerate(records):
        for name in fields:
            out[0, i][name] = record[name]
    return out


def _empty() -> np.ndarray:
    """MATLAB's ``[]``."""
    return np.zeros((0, 0))


# --------------------------------------------------------------------------- #
# Raw and SF-Tracer traces
# --------------------------------------------------------------------------- #
def _load_matrix(path: str, variable: str = "") -> Any:
    """MATLAB ``load`` of an ASCII table or of one variable of a MAT-file."""
    if str(path).lower().endswith(".mat"):
        content = _loadmat(path)
        if variable:
            return content[variable]
        # MATLAB's ``load`` returns a struct here, which ``load_raw.m`` cannot
        # use; taking the file's only variable is what the caller meant.
        if len(content) != 1:
            raise ValueError(
                f"{path}: name the variable holding the traces (found {sorted(content)})"
            )
        return next(iter(content.values()))
    return np.loadtxt(path, ndmin=2)


def load_raw(
    paths: str | Sequence[str],
    has_labels: bool = True,
    strip_first: bool = False,
    variable: str = "",
) -> tuple[list[np.ndarray], list[np.ndarray], np.ndarray]:
    """Read donor/acceptor traces, as ebFRET's ``ebfret.io.load_raw``.

    Three layouts are accepted, told apart the way the reference does:

    * a **stacked** table ``[id, donor, acceptor]`` (exactly three columns),
      grouped by ``id``. The ids index the output as ``raw_data{id}`` does in
      MATLAB, so they must be positive integers; an id that does not occur
      leaves a gap, which is stripped like any empty trace;
    * an **unstacked** table with donor on odd and acceptor on even columns;
    * a MAT-file cell array whose entries are ``T x 2`` ``[donor, acceptor]``.

    With ``has_labels`` the **first row of every trace is consumed as its
    label** (``label = rw(1, 1)``) -- for the stacked layout too, where that
    row holds a donor intensity. That is the reference's behaviour, and
    ebFRET's own ``simulated-K04-N350-raw-stacked.dat`` relies on it: its
    exported trace table starts at the second row of each molecule.

    Parameters
    ----------
    paths : str or sequence of str
        One or more files; their traces are concatenated.
    has_labels : bool
        Take the first row of each trace as its label. When ``False`` traces
        are numbered ``1..N`` per file.
    strip_first : bool
        Discard the first remaining frame of each trace.
    variable : str
        For a MAT-file, the variable holding the data. When empty and the file
        holds exactly one variable, that one is used (MATLAB's ``load`` would
        return a struct the reference cannot use).

    Returns
    -------
    donors, acceptors : list of numpy.ndarray
        One 1-D intensity array per trace.
    labels : numpy.ndarray
        Numeric label per trace.
    """
    if isinstance(paths, (str, os.PathLike)):
        paths = [str(paths)]
    donors: list[np.ndarray] = []
    acceptors: list[np.ndarray] = []
    labels: list[float] = []
    for path in paths:
        dat = _load_matrix(str(path), variable)
        if isinstance(dat, np.ndarray) and dat.dtype != object:
            dat = np.asarray(dat, dtype=float)
            if dat.ndim != 2:
                raise ValueError(f"{path}: expected a 2-D table, got shape {dat.shape}")
            if dat.shape[1] == 3:
                ids = dat[:, 0]
                if np.any(ids != np.round(ids)) or np.any(ids < 1):
                    raise ValueError(f"{path}: stacked trace ids must be positive integers")
                raw_data: list[np.ndarray] = [np.zeros((0, 2))] * int(ids.max())
                for n in np.unique(ids):
                    raw_data[int(n) - 1] = dat[ids == n, 1:3]
            else:
                if dat.shape[1] % 2:
                    raise ValueError(f"{path}: an unstacked table needs an even column count")
                raw_data = [dat[:, 2 * i : 2 * i + 2] for i in range(dat.shape[1] // 2)]
        else:
            raw_data = [np.asarray(rw, dtype=float).reshape(-1, 2) for rw in dat]

        file_labels = []
        for n, rw in enumerate(raw_data):
            if rw.size:
                if has_labels:
                    file_labels.append(float(rw[0, 0]))
                    rw = rw[1:, :]
                else:
                    file_labels.append(float(n + 1))
                if strip_first:
                    rw = rw[1:, :]
                raw_data[n] = rw
            else:
                file_labels.append(math.nan)
        for rw, label in zip(raw_data, file_labels):
            if rw.size:
                donors.append(rw[:, 0].copy())
                acceptors.append(rw[:, 1].copy())
                labels.append(label)
    return donors, acceptors, np.asarray(labels, dtype=float)


def _importdata_block(path: str) -> np.ndarray:
    """The numeric block of a text file, as MATLAB's ``importdata(...).data``.

    Leading lines that are not all numbers are header; ragged rows are padded
    with ``NaN``, as ``importdata`` pads them.
    """
    rows: list[list[float]] = []
    with open(path) as handle:
        for line in handle:
            tokens = line.replace(",", " ").split()
            if not tokens:
                continue
            try:
                values = [float(tok) for tok in tokens]
            except ValueError:
                if rows:
                    break
                continue
            rows.append(values)
    width = max((len(r) for r in rows), default=0)
    block = np.full((len(rows), width), np.nan)
    for i, row in enumerate(rows):
        block[i, : len(row)] = row
    return block


def load_sf_tracer(paths: str | Sequence[str]) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Read SF-Tracer ``.tsv`` traces, as ebFRET's ``ebfret.io.load_sf_tracer``.

    Each data row is ``region channel area length background intensity_1 ...``
    with 0-based region (molecule) and channel numbers. A row's intensities
    minus its background become channel ``c``'s signal for molecule ``n``.

    Parameters
    ----------
    paths : str or sequence of str
        One or more files. As in the reference, a later file overwrites the
        molecules of an earlier one with the same region number.

    Returns
    -------
    donors, acceptors : list of numpy.ndarray
        Channel 0 and channel 1 per molecule, indexed by region number; a
        region that does not occur is an empty array.
    """
    if isinstance(paths, (str, os.PathLike)):
        paths = [str(paths)]
    channels: list[list[np.ndarray]] = [[], []]
    for path in paths:
        data = _importdata_block(str(path))
        for row in data:
            n = int(row[0])
            c = int(row[1])
            while len(channels) <= c:
                channels.append([])
            background = row[4]
            trace = channels[c]
            while len(trace) <= n:
                trace.append(np.zeros(0))
            trace[n] = row[5:] - background
    return channels[0], channels[1]


def series_from_raw(
    path: str,
    donors: Sequence[np.ndarray],
    acceptors: Sequence[np.ndarray],
    labels: Sequence[Any],
    group: str,
) -> list[Series]:
    """Build the time series of one raw or SF-Tracer file, as ``load_data.m``.

    Traces whose donor or acceptor is empty are dropped. The signal is
    ``(acceptor + eps) / (acceptor + donor + eps)``, the time axis ``1..T``,
    and the crop range the whole trace.

    Parameters
    ----------
    path : str
        The file the traces came from (its base name is stored).
    donors, acceptors : sequence of numpy.ndarray
        Intensities per trace.
    labels : sequence
        Numeric or string label per trace; numbers are formatted with
        :func:`format_label`.
    group : str
        The group every series of this load belongs to.

    Returns
    -------
    list of Series
    """
    out: list[Series] = []
    name = file_base(path)
    for donor, acceptor, label in zip(donors, acceptors, labels):
        donor = np.asarray(donor, dtype=float).ravel()
        acceptor = np.asarray(acceptor, dtype=float).ravel()
        if donor.size == 0 or acceptor.size == 0:
            continue
        signal = (acceptor + EPS) / (acceptor + donor + EPS)
        out.append(
            Series(
                file=name,
                label=format_label(label),
                group=group,
                time=np.arange(1, donor.size + 1, dtype=float),
                signal=signal,
                donor=donor,
                acceptor=acceptor,
                crop_min=1,
                crop_max=int(donor.size),
                exclude=False,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Single-molecule datasets (SMD)
# --------------------------------------------------------------------------- #
def _json_array(value: Any) -> Any:
    """Normalise a JSONlab number array: ``[[v],[v]]`` -> 1-D, rows -> 2-D."""
    if isinstance(value, list):
        if not value:
            return np.zeros(0)
        if all(isinstance(v, (int, float)) or v is None or isinstance(v, str) for v in value):
            if all(not isinstance(v, str) or v in ("_NaN_", "_Inf_", "-_Inf_") for v in value):
                return np.array([_json_number(v) for v in value], dtype=float)
            return value
        if all(isinstance(v, list) for v in value):
            try:
                arr = np.array([[_json_number(x) for x in row] for row in value], dtype=float)
            except (TypeError, ValueError):
                return [_json_value(v) for v in value]
            return arr.ravel() if arr.ndim == 2 and arr.shape[1] == 1 else arr
        return [_json_value(v) for v in value]
    return value


def _json_number(value: Any) -> float:
    """A JSONlab number, including its ``"_NaN_"``/``"_Inf_"`` strings."""
    if value is None:
        return math.nan
    if isinstance(value, str):
        return {"_NaN_": math.nan, "_Inf_": math.inf, "-_Inf_": -math.inf}[value]
    return float(value)


def _json_value(value: Any) -> Any:
    """Normalise one decoded JSON value into dicts, lists, str and arrays."""
    if isinstance(value, dict):
        return {k: _json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return _json_array(value)
    return value


def _normalise_mat_attr(value: Any) -> Any:
    """Normalise a MAT attribute like a JSON one: vectors 1-D, 1x1 scalar."""
    if isinstance(value, dict):
        return {k: _normalise_mat_attr(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise_mat_attr(v) for v in value]
    if isinstance(value, np.ndarray):
        if value.size == 1:
            return float(value.ravel()[0])
        if value.ndim == 2 and 1 in value.shape:
            return value.ravel()
    return value


def load_smd(path: str) -> dict:
    """Read a single-molecule dataset, as ``load_data.m`` does for SMD files.

    ``.json`` and ``.json.gz`` files are decoded like JSONlab's ``loadjson``
    (so ``"_NaN_"`` becomes NaN); any other extension is read as the ``.mat``
    written by ``save(filename, '-struct', 'smd')``.

    Parameters
    ----------
    path : str
        The file.

    Returns
    -------
    dict
        ``{"type", "id", "attr", "columns", "data"}`` where ``columns`` is a
        list of str and ``data`` a list of ``{"id", "index", "values",
        "attr"}``: ``index`` 1-D, ``values`` 2-D ``(T, D)``, attribute vectors
        1-D and matrices 2-D.
    """
    lower = str(path).lower()
    if lower.endswith(".gz"):
        with gzip.open(path, "rt") as handle:
            raw = _json_value(json.load(handle))
    elif lower.endswith(".json"):
        with open(path) as handle:
            raw = _json_value(json.load(handle))
    else:
        raw = _normalise_mat_attr(_loadmat(path))
    columns = raw.get("columns", [])
    if isinstance(columns, str):
        columns = [columns]
    data = raw.get("data", [])
    if isinstance(data, dict):
        data = [data]
    n_columns = len(columns)
    traces = []
    for entry in data:
        values = np.asarray(entry.get("values", np.zeros((0, n_columns))), dtype=float)
        if values.ndim < 2:
            # One frame (a row) or one column squeezed to a vector.
            values = (
                values.reshape(1, -1)
                if values.size == n_columns and n_columns > 1
                else values.reshape(-1, max(n_columns, 1))
            )
        index = np.atleast_1d(np.asarray(entry.get("index", []), dtype=float)).ravel()
        attr = entry.get("attr", {})
        traces.append(
            {
                "id": str(entry.get("id", "")),
                "index": index,
                "values": values,
                "attr": attr if isinstance(attr, dict) else {},
            }
        )
    return {
        "type": str(raw.get("type", "")),
        "id": str(raw.get("id", "")),
        "attr": raw.get("attr", {}) if isinstance(raw.get("attr", {}), dict) else {},
        "columns": [str(c) for c in columns],
        "data": traces,
    }


def series_from_smd(
    path: str,
    smd: Mapping,
    channels: Mapping[str, int | None],
    group: str,
) -> list[Series]:
    """Build the time series of one SMD file, as ``load_data.m`` does.

    ``channels`` is what the *Assign Channels* dialog returns: 1-based column
    numbers, ``None`` where the dialog has ``NaN``. The reference tests
    ``channels.fret == channels.fret``, i.e. "is a FRET column selected": then
    the signal is that column and donor/acceptor are zeros; otherwise the
    signal is computed from the donor and acceptor columns.

    The reference never sets ``group`` for SMD series, leaving it empty; the
    next load that appends then counts groups wrongly and the export dialogs
    list a nameless group. This port assigns *group* like the raw branch does
    -- a deliberate fix.

    Parameters
    ----------
    path : str
        The file (its base name is stored).
    smd : mapping
        As returned by :func:`load_smd`.
    channels : mapping
        ``{"donor": int|None, "acceptor": int|None, "fret": int|None}``.
    group : str
        The group of this load.

    Returns
    -------
    list of Series
    """
    out: list[Series] = []
    name = file_base(path)
    fret = channels.get("fret")
    for entry in smd["data"]:
        values = np.asarray(entry["values"], dtype=float)
        index = np.asarray(entry["index"], dtype=float).ravel()
        if fret is not None:
            signal = values[:, int(fret) - 1].copy()
            donor = np.zeros(index.shape)
            acceptor = np.zeros(index.shape)
        else:
            donor = values[:, int(channels["donor"]) - 1].copy()
            acceptor = values[:, int(channels["acceptor"]) - 1].copy()
            signal = (acceptor + EPS) / (acceptor + donor + EPS)
        out.append(
            Series(
                file=name,
                label=str(entry["id"]),
                group=group,
                time=index,
                signal=signal,
                donor=donor,
                acceptor=acceptor,
                crop_min=1,
                crop_max=int(index.size),
                exclude=False,
            )
        )
    return out


def _md5_values(values: np.ndarray) -> str:
    """MD5 hex digest of an array's float64 bytes (C order)."""
    return hashlib.md5(np.ascontiguousarray(values, dtype=float).tobytes()).hexdigest()


def smd_create(
    data: Any,
    columns: Sequence[str],
    index: Sequence[np.ndarray] | np.ndarray | None = None,
    type: str = "",  # noqa: A002 - the reference's argument name
    id: str = "",  # noqa: A002 - the reference's argument name
    attr: Mapping | None = None,
    data_ids: Sequence[str] | None = None,
    data_attrs: Sequence[Mapping] | None = None,
) -> dict:
    """Assemble an SMD structure, as ebFRET's ``ebfret.io.smd.create``.

    Parameters
    ----------
    data : list of numpy.ndarray or numpy.ndarray
        ``T{n} x D`` arrays per trace, one flat ``M x D`` table (split by an
        ``'id'`` column when there is one) or an ``N x T x D`` array.
    columns : sequence of str
        Column labels; ``'index'`` and ``'id'`` columns are taken out of the
        values and used as the trace's index and id.
    index : sequence of numpy.ndarray, optional
        Time index per trace, overriding any index column.
    type : str
        Dataset type; the column labels joined by ``-`` when empty.
    id : str
        Dataset id; a hash when empty.
    attr : mapping, optional
        Dataset attributes.
    data_ids : sequence of str, optional
        Trace ids; a hash of the values where missing.
    data_attrs : sequence of mapping, optional
        Per-trace attributes.

    Returns
    -------
    dict
        ``{"type", "id", "attr", "columns", "data"}``.

    Notes
    -----
    The reference derives missing ids with DataHash, an MD5 over MATLAB's
    in-memory serialisation of the struct, which cannot be reproduced outside
    MATLAB. Here a trace id is the MD5 of its values' float64 bytes and the
    dataset id the MD5 of the trace ids joined -- still 32 hex digits, still
    stable for the same data, but not equal to the ids ebFRET would assign.
    """
    lower = [str(c).lower() for c in columns]
    index_col = lower.index("index") if "index" in lower else -1
    id_col = lower.index("id") if "id" in lower else -1
    value_cols = [i for i in range(len(columns)) if i not in (index_col, id_col)]

    def parse(table: np.ndarray) -> list[dict]:
        table = np.asarray(table, dtype=float)
        if table.ndim == 1:
            table = table.reshape(-1, len(columns))
        if id_col >= 0:
            out = []
            ids = table[:, id_col]
            for trace_id in np.unique(ids):
                rows = table[ids == trace_id]
                out.append(
                    {
                        "id": format_label(trace_id),
                        "index": (
                            rows[:, index_col]
                            if index_col >= 0
                            else np.arange(1, rows.shape[0] + 1, dtype=float)
                        ),
                        "values": rows[:, value_cols],
                    }
                )
            return out
        return [
            {
                "id": "",
                "index": (
                    table[:, index_col]
                    if index_col >= 0
                    else np.arange(1, table.shape[0] + 1, dtype=float)
                ),
                "values": table[:, value_cols],
            }
        ]

    traces: list[dict] = []
    if isinstance(data, np.ndarray) and data.dtype != object and data.ndim == 3:
        for n in range(data.shape[0]):
            traces.extend(parse(data[n]))
    elif isinstance(data, np.ndarray) and data.dtype != object:
        traces = parse(data)
    else:
        for table in data:
            traces.extend(parse(table))

    if index is not None:
        index_list = list(index) if not isinstance(index, np.ndarray) else list(index)
        if len(index_list) != len(traces):
            raise ValueError(
                f"Number of specified index values ({len(index_list)}) does not match "
                f"number of series parsed from data ({len(traces)})"
            )
        for trace, idx in zip(traces, index_list):
            trace["index"] = np.asarray(idx, dtype=float).ravel()
    if data_ids:
        if len(data_ids) != len(traces):
            raise ValueError(
                f"Number of specified data_ids ({len(data_ids)}) does not match "
                f"number of time series parsed from data ({len(traces)})"
            )
        for trace, trace_id in zip(traces, data_ids):
            trace["id"] = str(trace_id)
    if data_attrs is not None and len(data_attrs) > 1:
        if len(data_attrs) != len(traces):
            raise ValueError(
                f"Number of specified data_attrs ({len(data_attrs)}) does not match "
                f"number of series parsed from data ({len(traces)})"
            )
        for trace, trace_attr in zip(traces, data_attrs):
            trace["attr"] = dict(trace_attr)
    else:
        # The reference discards a single data_attr as well (``length > 1``).
        for trace in traces:
            trace["attr"] = {}
    for trace in traces:
        if not trace["id"]:
            trace["id"] = _md5_values(trace["values"])
    set_id = id or hashlib.md5("".join(t["id"] for t in traces).encode()).hexdigest()
    return {
        "type": type or "-".join(str(c) for c in columns),
        "id": set_id,
        "attr": dict(attr or {}),
        "columns": [str(columns[i]) for i in value_cols],
        "data": traces,
    }


def build_smd(series: Sequence[Series], analysis: Analysis) -> dict:
    """The SMD structure ``write_smd.m`` saves for a set of series.

    Only series that are not excluded are written, over their crop range.
    Array orientations are MATLAB's (column vectors ``(K, 1)``) so the MAT and
    JSON writers reproduce the reference's layout.

    Reproduced as the reference has them:

    * ``attr.num_states`` is **not** written -- ``write_smd.m`` assigns it to a
      misspelt variable (``smn``);
    * the per-trace ``posterior_*`` attributes hold the **prior**, not the
      trace's posterior.

    Fixed deliberately: the reference reads the Viterbi path as
    ``viterbi(n).state(crop.min:crop.max)``, but the path already covers only
    the cropped frames, so any series cropped at the start is misaligned or
    raises. The whole stored path is written instead.

    Parameters
    ----------
    series : sequence of Series
        The series to write (already restricted to a group, if any).
    analysis : Analysis
        The analysis whose prior, paths and statistics are written, with
        per-series lists parallel to *series*.

    Returns
    -------
    dict
        As :func:`smd_create` returns.
    """
    prior = analysis.prior
    if prior is None:
        raise ValueError(f"the {analysis.states}-state analysis has no prior")
    attr = {
        "prior_mu": _col(prior.mu),
        "prior_beta": _col(prior.beta),
        "prior_W": _col(prior.W),
        "prior_nu": _col(prior.nu),
        "prior_A": np.asarray(prior.A, dtype=float),
        "prior_pi": _col(prior.pi),
    }
    values, indexes, data_attrs = [], [], []
    for n, s in enumerate(series):
        if s.exclude:
            continue
        crop = slice(int(s.crop_min) - 1, int(s.crop_max))
        vit = analysis.viterbi[n] if n < len(analysis.viterbi) else None
        exp = analysis.expect[n] if n < len(analysis.expect) else None
        if vit is None or exp is None:
            raise ValueError(f"series {n + 1} has not been analysed; run the analysis first")
        table = np.zeros((int(s.crop_max) - int(s.crop_min) + 1, len(_SMD_COLUMNS)))
        table[:, 0] = np.asarray(s.donor, dtype=float)[crop]
        table[:, 1] = np.asarray(s.acceptor, dtype=float)[crop]
        table[:, 2] = np.asarray(s.signal, dtype=float)[crop]
        table[:, 3] = np.asarray(vit.state, dtype=float).ravel()
        table[:, 4] = np.asarray(vit.mean, dtype=float).ravel()
        values.append(table)
        indexes.append(_col(np.asarray(s.time, dtype=float)[crop]))
        data_attrs.append(
            {
                "file": s.file,
                "label": s.label,
                "group": s.group,
                "crop_min": float(s.crop_min),
                "crop_max": float(s.crop_max),
                "restart": float(analysis.restart[n]),
                "lowerbound": float(analysis.lowerbound[n]),
                "posterior_mu": _col(prior.mu),
                "posterior_beta": _col(prior.beta),
                "posterior_W": _col(prior.W),
                "posterior_nu": _col(prior.nu),
                "posterior_A": np.asarray(prior.A, dtype=float),
                "posterior_pi": _col(prior.pi),
                "suff_stat_z": _col(exp.z),
                "suff_stat_z1": _col(exp.z1),
                "suff_stat_zz": np.asarray(exp.zz, dtype=float),
                "suff_stat_x": _col(exp.x),
                "suff_stat_xx": _col(exp.xx),
            }
        )
    smd = smd_create(
        values,
        list(_SMD_COLUMNS),
        index=indexes,
        type="ebFRET_v_1_1_analysis",
        attr=attr,
        data_attrs=data_attrs if len(data_attrs) > 1 else None,
    )
    if len(data_attrs) == 1:
        # ``create.m`` drops a single data_attr (``length(args.data_attrs) > 1``).
        smd["data"][0]["attr"] = {}
    for trace, idx in zip(smd["data"], indexes):
        trace["index"] = idx
    return smd


def _smd_to_mat(smd: Mapping) -> dict:
    """The variables ``save(filename, '-struct', 'smd')`` writes."""
    traces = []
    for trace in smd["data"]:
        traces.append(
            {
                "id": trace["id"],
                "index": _col(trace["index"]),
                "values": np.asarray(trace["values"], dtype=float),
                "attr": dict(trace.get("attr", {})),
            }
        )
    columns = np.empty((1, len(smd["columns"])), dtype=object)
    for i, name in enumerate(smd["columns"]):
        columns[0, i] = name
    return {
        "type": smd["type"],
        "id": smd["id"],
        "attr": dict(smd["attr"]),
        "columns": columns,
        "data": _struct_array(traces, ("id", "index", "values", "attr")),
    }


def write_smd(
    path: str, series: Sequence[Series], analysis: Analysis, fmt: str | None = None
) -> dict:
    """Write series and analysis as an SMD, as ebFRET's ``ebfret.io.write_smd``.

    Parameters
    ----------
    path : str
        Output file.
    series : sequence of Series
        Series to write.
    analysis : Analysis
        Analysis parallel to *series*.
    fmt : {'mat', 'json', 'gz'}, optional
        File format; guessed from the last extension when omitted, falling
        back to ``'mat'`` with a warning, as the reference does.

    Returns
    -------
    dict
        The SMD structure that was written.
    """
    if not fmt:
        fmt = os.path.splitext(str(path))[1][1:].lower()
        if fmt not in ("mat", "json", "gz"):
            warnings.warn(
                "Cannot detect SMD format from file extension. Must be one of "
                '{".mat", ".json", ".gz"}. Using ".mat".',
                stacklevel=2,
            )
            fmt = "mat"
    smd = build_smd(series, analysis)
    if fmt == "mat":
        import scipy.io as sio

        sio.savemat(path, _smd_to_mat(smd), long_field_names=True)
    elif fmt in ("json", "gz"):
        text = savejson(smd)
        if fmt == "gz":
            with gzip.open(path, "wt") as handle:
                handle.write(text)
        else:
            with open(path, "w") as handle:
                handle.write(text)
    else:
        raise ValueError(f"unknown SMD format {fmt!r}")
    return smd


# --------------------------------------------------------------------------- #
# JSONlab writer
# --------------------------------------------------------------------------- #
def _g10(value: float) -> str:
    """JSONlab's ``%.10g`` number, with its NaN/Inf strings."""
    value = float(value)
    if math.isnan(value):
        return '"_NaN_"'
    if math.isinf(value):
        return '"_Inf_"' if value > 0 else '"-_Inf_"'
    return f"{value:.10g}"


def _matdata2json(mat: np.ndarray, level: int) -> str:
    """JSONlab's ``matdata2json`` for a 2-D real array."""
    if mat.size == 0:
        return "null"
    tabs = "\t"
    if mat.shape[0] == 1:
        pre, post = "", ""
        row_indent = ""
    else:
        pre, post = "[\n", "\n" + tabs * (level - 1) + "]"
        row_indent = tabs * level
    rows = [row_indent + "[" + ",".join(_g10(v) for v in row) + "]" for row in mat]
    return pre + ",\n".join(rows) + post


def _as_matlab_array(value: Any) -> np.ndarray:
    """A number or array as MATLAB sees it: 1-D arrays are row vectors."""
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        return arr.reshape(1, 1)
    if arr.ndim == 1:
        return arr.reshape(1, -1)
    return arr


def _obj2json(name: str, item: Any, level: int) -> str:
    """JSONlab's ``obj2json`` over dicts, lists, strings and arrays."""
    tabs = "\t"
    if isinstance(item, Mapping):
        return _struct2json(name, [item], level)
    if isinstance(item, (list, tuple)) and item and all(isinstance(i, Mapping) for i in item):
        return _struct2json(name, list(item), level)
    if isinstance(item, (list, tuple)):
        # a cell array
        length = len(item)
        text = ""
        if length > 1:
            text = f'{tabs * level}"{name}": [\n' if name else f"{tabs * level}[\n"
            name = ""
        elif length == 0:
            return f'{tabs * level}"{name}": null' if name else f"{tabs * level}null"
        parts = [
            tabs * (level - 1) + _obj2json(name, entry, level + (length > 1)) for entry in item
        ]
        text += ",\n".join(parts)
        if length > 1:
            text += "\n" + tabs * level + "]"
        return text
    if isinstance(item, str):
        val = item.replace("\\", "\\\\").replace('"', '\\"')
        if name:
            return f'{tabs * level}"{name}": "{val}"'
        return f'{tabs * level}"{val}"'
    arr = _as_matlab_array(item)
    if not name:
        return tabs * level + _matdata2json(arr, level + 1)
    if arr.size == 1:
        body = _matdata2json(arr, level + 1)
        body = re.sub(r"^\[", "", body).replace("]", "")
        return f'{tabs * level}"{name}": {body}'
    return f'{tabs * level}"{name}": {_matdata2json(arr, level + 1)}'


def _struct2json(name: str, items: list, level: int) -> str:
    """JSONlab's ``struct2json`` for a struct (array)."""
    tabs = "\t"
    length = len(items)
    text = ""
    if length > 1:
        text = f'{tabs * level}"{name}": [\n' if name else f"{tabs * level}[\n"
    for e, item in enumerate(items):
        inner = level + (length > 1)
        if name and length == 1:
            text += f'{tabs * inner}"{name}": {{\n'
        else:
            text += f"{tabs * inner}{{\n"
        fields = list(item.keys())
        for i, field_name in enumerate(fields):
            text += _obj2json(field_name, item[field_name], level + 1 + (length > 1))
            if i < len(fields) - 1:
                text += ","
            text += "\n"
        text += tabs * inner + "}"
        if e < length - 1:
            text += ",\n"
    if length > 1:
        text += "\n" + tabs * level + "]"
    return text


def savejson(obj: Mapping) -> str:
    """Serialise a struct the way JSONlab's ``savejson('', obj)`` does.

    Tab indentation, ``%.10g`` numbers, a 1x1 array as a bare number, a row
    vector as ``[a,b]`` and every other matrix as one bracketed row per line
    -- so a column vector is ``[[a],[b]]``. NaN and Inf are written as the
    strings ``"_NaN_"``/``"_Inf_"``, which :func:`load_smd` and JSONlab's
    ``loadjson`` both turn back into numbers.

    Parameters
    ----------
    obj : mapping
        A struct: ``dict`` values may be dicts (structs), lists of dicts
        (struct arrays), lists of str (cell arrays), str, numbers or arrays.
        Pass column vectors as ``(n, 1)`` arrays; a 1-D array is a row.

    Returns
    -------
    str
    """
    return _struct2json("", [obj], 0) + "\n"


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
def _hmm_struct(params: HmmParams | None) -> Any:
    """A prior/posterior as the MATLAB struct ``{pi, A, mu, beta, W, nu}``."""
    if params is None:
        return {name: _empty() for name in _HMM_FIELDS}
    return {
        "pi": _col(params.pi),
        "A": np.asarray(params.A, dtype=float),
        "mu": _col(params.mu),
        "beta": _col(params.beta),
        "W": _col(params.W),
        "nu": _col(params.nu),
    }


def _expect_struct(expect: Expect | None) -> dict:
    """Expected statistics as the MATLAB struct ``{z, z1, zz, x, xx}``."""
    if expect is None:
        return {name: _empty() for name in _EXPECT_FIELDS}
    return {
        "z": _col(expect.z),
        "z1": _col(expect.z1),
        "zz": np.asarray(expect.zz, dtype=float),
        "x": _col(expect.x),
        "xx": _col(expect.xx),
    }


def _viterbi_struct(path: Viterbi | None) -> dict:
    """A Viterbi path as the MATLAB struct ``{state, mean}``."""
    if path is None:
        return {"state": _empty(), "mean": _empty()}
    return {"state": _col(path.state), "mean": _col(path.mean)}


def _row(values: Any) -> np.ndarray:
    """A 1-D array as a MATLAB row vector ``(1, n)``, ``[]`` when empty."""
    arr = np.asarray(values, dtype=float).ravel()
    return arr.reshape(1, -1) if arr.size else _empty()


def _analysis_record(analysis: Analysis | None, n_series: int) -> dict:
    """One ``analysis(k)`` entry of a session."""
    fields = ("dim", "prior", "posterior", "expect", "lowerbound", "viterbi", "restart")
    if analysis is None:
        return {name: _empty() for name in fields}
    posterior = list(analysis.posterior) + [None] * (n_series - len(analysis.posterior))
    expect = list(analysis.expect) + [None] * (n_series - len(analysis.expect))
    viterbi = list(analysis.viterbi) + [None] * (n_series - len(analysis.viterbi))
    have_series = analysis.prior is not None and n_series > 0
    return {
        "dim": {"states": float(analysis.states)},
        "prior": _hmm_struct(analysis.prior) if analysis.prior is not None else _empty(),
        "posterior": (
            _struct_array([_hmm_struct(p) for p in posterior[:n_series]], _HMM_FIELDS)
            if have_series
            else _empty()
        ),
        "expect": (
            _struct_array([_expect_struct(e) for e in expect[:n_series]], _EXPECT_FIELDS)
            if have_series
            else _empty()
        ),
        "lowerbound": _row(analysis.lowerbound),
        "viterbi": (
            _struct_array([_viterbi_struct(v) for v in viterbi[:n_series]], ("state", "mean"))
            if have_series
            else _empty()
        ),
        "restart": _row(analysis.restart),
    }


def _controls_struct(controls: Controls) -> dict:
    """``self.controls`` as ``save_data.m`` writes it."""
    return {
        "colors": {
            name: np.asarray(rgb, dtype=float).reshape(1, 3) for name, rgb in COLORS.items()
        },
        "show": {
            "viterbi": bool(controls.show_viterbi),
            "prior": bool(controls.show_prior),
            "posterior": bool(controls.show_posterior),
        },
        "series": {
            "value": float(controls.series_value),
            "min": float(controls.series_min),
            "max": float(controls.series_max),
        },
        "ensemble": {
            "min": float(controls.ensemble_min),
            "max": float(controls.ensemble_max),
            "value": float(controls.ensemble_value),
        },
        "min_states": float(controls.min_states),
        "max_states": float(controls.max_states),
        "clip": {"min": float(controls.clip_min), "max": float(controls.clip_max)},
        "restarts": float(controls.restarts),
        "run_analysis": bool(controls.run_analysis),
        "run_all": bool(controls.run_all),
        "run_precision": float(controls.run_precision),
        "scale_plots": bool(controls.scale_plots),
        "crop_margin": float(controls.crop_margin),
    }


def save_session(
    path: str, series: Sequence[Series], analysis: Mapping[int, Analysis], controls: Controls
) -> None:
    """Save a session ``.mat``, as ebFRET's ``save_data.m``.

    The file holds the variables ``controls``, ``series``, ``analysis`` and
    ``plots``. ``analysis`` is a struct array indexed by the number of states
    (entry ``k`` is the ``k``-state model; entries without a model have empty
    fields), exactly as the reference stores ``self.analysis``. ``plots``,
    which ebFRET saves but never reads back, is written as an empty struct.
    ``controls.redraw`` holds ``tic`` timer ids that mean nothing in another
    process and is not written; ebFRET keeps its own on load.

    Parameters
    ----------
    path : str
        Output ``.mat`` file.
    series : sequence of Series
        Time series.
    analysis : mapping of int to Analysis
        Models keyed by number of states.
    controls : Controls
        Control values.
    """
    import scipy.io as sio

    n_series = len(series)
    series_records = [
        {
            "file": s.file,
            "label": s.label,
            "group": s.group,
            "time": _col(s.time),
            "signal": _col(s.signal),
            "donor": _col(s.donor),
            "acceptor": _col(s.acceptor),
            "crop": {"min": float(s.crop_min), "max": float(s.crop_max)},
            "exclude": bool(s.exclude),
        }
        for s in series
    ]
    series_fields = (
        "file",
        "label",
        "group",
        "time",
        "signal",
        "donor",
        "acceptor",
        "crop",
        "exclude",
    )
    max_k = max((int(k) for k in analysis), default=0)
    analysis_records = [_analysis_record(analysis.get(k), n_series) for k in range(1, max_k + 1)]
    content = {
        "controls": _controls_struct(controls),
        "series": (_struct_array(series_records, series_fields) if series_records else _empty()),
        "analysis": (
            _struct_array(
                analysis_records,
                ("dim", "prior", "posterior", "expect", "lowerbound", "viterbi", "restart"),
            )
            if analysis_records
            else _empty()
        ),
        "plots": {},
    }
    sio.savemat(path, content, long_field_names=True, do_compression=True)


def _as_list(value: Any) -> list:
    """A struct array converted by :func:`_mat_to_py` as a list of dicts."""
    if _is_empty(value):
        return []
    if isinstance(value, dict):
        return [value]
    return list(value)


def _hmm_from(record: Any) -> HmmParams | None:
    """A prior/posterior struct, or ``None`` when its fields are empty."""
    if not isinstance(record, dict) or _is_empty(record.get("mu")):
        return None
    k = _vector(record["mu"]).size
    return HmmParams(
        mu=_vector(record["mu"]),
        beta=_vector(record["beta"]),
        W=_vector(record["W"]),
        nu=_vector(record["nu"]),
        A=np.asarray(record["A"], dtype=float).reshape(k, k, order="F"),
        pi=_vector(record["pi"]),
    )


def _expect_from(record: Any) -> Expect | None:
    """An expect struct, or ``None`` when its fields are empty."""
    if not isinstance(record, dict) or _is_empty(record.get("z")):
        return None
    k = _vector(record["z"]).size
    return Expect(
        z=_vector(record["z"]),
        z1=_vector(record["z1"]),
        zz=np.asarray(record["zz"], dtype=float).reshape(k, k, order="F"),
        x=_vector(record["x"]),
        xx=_vector(record["xx"]),
    )


def _viterbi_from(record: Any) -> Viterbi | None:
    """A viterbi struct, or ``None`` when it is empty."""
    if not isinstance(record, dict) or _is_empty(record.get("state")):
        return None
    return Viterbi(state=_vector(record["state"]).astype(int), mean=_vector(record["mean"]))


def _controls_from(record: Mapping) -> Controls:
    """``Controls`` from a session's ``controls`` struct.

    Unknown and deprecated fields (``init_restarts``, ``gmm_restarts``,
    ``colors``, ``redraw``) are ignored; ``all_restarts`` is read as
    ``restarts``, in field order, as ``set_control`` does.
    """
    controls = Controls()
    for name, value in record.items():
        if name in ("series", "ensemble") and isinstance(value, dict):
            for part in ("min", "max", "value"):
                if part in value:
                    setattr(controls, f"{name}_{part}", int(round(_scalar(value[part]))))
        elif name == "clip" and isinstance(value, dict):
            controls.clip_min = _scalar(value.get("min"), controls.clip_min)
            controls.clip_max = _scalar(value.get("max"), controls.clip_max)
        elif name == "show" and isinstance(value, dict):
            for part in ("viterbi", "prior", "posterior"):
                if part in value:
                    setattr(controls, f"show_{part}", bool(_scalar(value[part])))
        elif name in ("min_states", "max_states", "restarts", "crop_margin"):
            setattr(controls, name, int(round(_scalar(value))))
        elif name == "all_restarts":
            controls.restarts = int(round(_scalar(value)))
        elif name in ("run_analysis", "run_all", "scale_plots"):
            setattr(controls, name, bool(_scalar(value)))
        elif name == "run_precision":
            controls.run_precision = _scalar(value, controls.run_precision)
    return controls


def load_session(path: str) -> tuple[list[Series], dict[int, Analysis], Controls]:
    """Load a session ``.mat``, as the session branch of ``load_data.m``.

    Old sessions with numeric group labels have them renamed ``'group %d'``,
    as the reference does. ``run_analysis`` is read but a caller should not act
    on it: ``load_data.m`` resets it so a loaded session never starts running.

    Parameters
    ----------
    path : str
        A session saved by ebFRET or by :func:`save_session`.

    Returns
    -------
    series : list of Series
    analysis : dict of int to Analysis
        Only the entries that hold a model (``dim`` set).
    controls : Controls
    """
    content = _loadmat(path)
    raw_series = _as_list(content.get("series"))
    groups = [record.get("group") for record in raw_series]
    if groups and all(not isinstance(g, str) for g in groups):
        groups = [f"group {int(round(_scalar(g)))}" for g in groups]
    series: list[Series] = []
    for record, group in zip(raw_series, groups):
        crop = record.get("crop") or {}
        signal = _vector(record.get("signal"))
        series.append(
            Series(
                file=str(record.get("file") or ""),
                label=(
                    record["label"]
                    if isinstance(record.get("label"), str)
                    else format_label(_scalar(record.get("label")))
                ),
                group=str(group),
                time=_vector(record.get("time")),
                signal=signal,
                donor=_vector(record.get("donor")),
                acceptor=_vector(record.get("acceptor")),
                crop_min=int(round(_scalar(crop.get("min"), 1))),
                crop_max=int(round(_scalar(crop.get("max"), signal.size))),
                exclude=bool(_scalar(record.get("exclude"), 0.0)),
            )
        )

    n_series = len(series)
    analysis: dict[int, Analysis] = {}
    for k, record in enumerate(_as_list(content.get("analysis")), start=1):
        dim = record.get("dim")
        if not isinstance(dim, dict) or _is_empty(dim.get("states")):
            continue
        posterior = [_hmm_from(p) for p in _as_list(record.get("posterior"))]
        expect = [_expect_from(e) for e in _as_list(record.get("expect"))]
        viterbi = [_viterbi_from(v) for v in _as_list(record.get("viterbi"))]
        pad = [None] * n_series
        lowerbound = _vector(record.get("lowerbound"))
        restart = _vector(record.get("restart")).astype(int)
        analysis[k] = Analysis(
            states=int(round(_scalar(dim["states"]))),
            prior=_hmm_from(record.get("prior")),
            posterior=(posterior + pad)[:n_series] if posterior else [],
            expect=(expect + pad)[:n_series] if expect else [],
            viterbi=(viterbi + pad)[:n_series] if viterbi else [],
            lowerbound=lowerbound,
            restart=restart if restart.size else np.zeros(lowerbound.size, dtype=int),
        )
    controls_record = content.get("controls")
    controls = _controls_from(controls_record if isinstance(controls_record, dict) else {})
    return series, analysis, controls


# --------------------------------------------------------------------------- #
# Analysis summary report
# --------------------------------------------------------------------------- #
def _is_str_list(value: Any) -> bool:
    """A cell array of strings."""
    return isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value)


def _report_node_rows(
    nodes: Sequence[Mapping], level: int, separator: str, indent: str
) -> list[list[Any]]:
    """``parse`` of ``write_report.m``: rows of cells for a struct array."""
    lines: list[list[Any]] = []
    fields = list(nodes[0].keys())
    for field_name in fields:
        r0 = len(lines)
        lines.append([indent * level + field_name])
        first = nodes[0].get(field_name)
        if isinstance(first, Mapping):
            children = [n.get(field_name) for n in nodes if isinstance(n.get(field_name), Mapping)]
            lines.extend(_report_node_rows(children, level + 1, separator, indent))
        elif isinstance(first, str):
            parts = [n.get(field_name) for n in nodes]
            lines[r0].append("".join(separator + p for p in parts if isinstance(p, str)))
        elif _is_str_list(first):
            for n, node in enumerate(nodes):
                cells = node.get(field_name) or []
                _set_cell(lines[r0], 1 + n, "".join(separator + str(c) for c in cells))
        elif first is None:
            continue
        else:
            arr = np.asarray(first, dtype=float)
            is_vector = arr.ndim <= 1 or (arr.ndim == 2 and 1 in arr.shape)
            for n, node in enumerate(nodes):
                value = node.get(field_name)
                data = np.zeros((0, 0)) if value is None else np.asarray(value, dtype=float)
                if is_vector:
                    flat = data.ravel(order="F")
                    _set_cell(
                        lines[r0], 1 + n, "".join(separator + _fmt_e(v, "%.3e") for v in flat)
                    )
                else:
                    if data.ndim < 2:
                        data = data.reshape(1, -1) if data.size else np.zeros((0, 0))
                    for r in range(data.shape[0]):
                        while len(lines) <= r0 + r:
                            lines.append([None])
                        _set_cell(
                            lines[r0 + r],
                            1 + n,
                            "".join(separator + _fmt_e(v, "%.3e") for v in data[r]),
                        )
    return lines


def _set_cell(row: list, index: int, value: str) -> None:
    """``row{index+1} = value``, growing the cell row with empty cells."""
    while len(row) <= index:
        row.append(None)
    row[index] = value


def format_report(
    report: Sequence[Mapping] | Mapping, separator: str = ",", indent: str = "    "
) -> str:
    """The text ``write_report.m`` writes for a report struct array.

    Parameters
    ----------
    report : sequence of mapping or mapping
        One nested mapping per report column (``rep(s)``), fields in order.
        Values may be str, lists of str (cells), numbers, 1-D or column arrays
        (written on one line), 2-D arrays (one line per row), nested mappings
        or ``None`` (an empty field).
    separator : str
        Cell separator.
    indent : str
        Indentation per nesting level.

    Returns
    -------
    str

    Notes
    -----
    The reference passes each finished line to ``fprintf`` *as the format*,
    so a ``%%`` or a backslash escape inside a label is interpreted; ``%%``
    and ``\\n``/``\\t``/``\\\\`` are interpreted here the same way.
    """
    nodes = [report] if isinstance(report, Mapping) else list(report)
    lines = _report_node_rows(nodes, 0, separator, indent)

    def count_sep(elem: Any) -> int:
        return elem.count(separator) if isinstance(elem, str) else 0

    for li in range(1, len(lines)):
        for c in range(1, len(lines[li])):
            if not count_sep(lines[li][c]):
                previous = lines[li - 1]
                if c >= len(previous):
                    raise IndexError("report rows do not line up (index exceeds matrix dims)")
                lines[li][c] = separator * count_sep(previous[c])
    text = []
    for line in lines:
        joined = "".join(cell for cell in line if isinstance(cell, str))
        joined = (
            joined.replace("\\\\", "\0")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\0", "\\")
            .replace("%%", "%")
        )
        text.append(joined + "\n")
    return "".join(text)


def write_report(
    path: str, report: Sequence[Mapping] | Mapping, separator: str = ",", indent: str = "    "
) -> None:
    """Write an analysis summary CSV, as ebFRET's ``ebfret.io.write_report``.

    Parameters
    ----------
    path : str
        Output ``.csv`` file.
    report : sequence of mapping or mapping
        See :func:`format_report`.
    separator, indent : str
        See :func:`format_report`.
    """
    with open(path, "w", newline="") as handle:
        handle.write(format_report(report, separator, indent))


# --------------------------------------------------------------------------- #
# Trace export
# --------------------------------------------------------------------------- #
def export_traces(
    path: str,
    series: Sequence[Series],
    analysis: Analysis | None,
    channels: Mapping[str, bool],
    fmt: str | None = None,
) -> np.ndarray:
    """Export the trace table, as ebFRET's ``export_traces.m``.

    One row per frame of every series that is not excluded, over its crop
    range: ``[n, donor, acceptor, fret, viterbi_state, viterbi_mean]`` with the
    unselected channels left out, where ``n`` is the 1-based number of the
    series in *series*.

    Parameters
    ----------
    path : str
        Output file.
    series : sequence of Series
        Series to export (already restricted to a group, if any).
    analysis : Analysis or None
        Analysis parallel to *series*; needed only for Viterbi channels.
    channels : mapping of str to bool
        ``donor``, ``acceptor``, ``fret``, ``viterbi_state``, ``viterbi_mean``.
    fmt : {'dat', 'mat'}, optional
        ``'dat'`` writes MATLAB's ``save -ascii`` (``%16.7e`` per value,
        newline-terminated rows), ``'mat'`` a MAT-file with the variable
        ``traces``. Taken from the extension when omitted.

    Returns
    -------
    numpy.ndarray
        The table that was written.
    """
    if not fmt:
        fmt = os.path.splitext(str(path))[1][1:].lower()
    blocks = []
    for n, s in enumerate(series):
        if s.exclude:
            continue
        crop = slice(int(s.crop_min) - 1, int(s.crop_max))
        columns = []
        if channels.get("donor"):
            columns.append(np.asarray(s.donor, dtype=float)[crop])
        if channels.get("acceptor"):
            columns.append(np.asarray(s.acceptor, dtype=float)[crop])
        if channels.get("fret"):
            columns.append(np.asarray(s.signal, dtype=float)[crop])
        if channels.get("viterbi_state") or channels.get("viterbi_mean"):
            path_n = (
                analysis.viterbi[n] if analysis is not None and n < len(analysis.viterbi) else None
            )
            if path_n is None:
                raise ValueError(f"series {n + 1} has no Viterbi path; run the analysis first")
            if channels.get("viterbi_state"):
                columns.append(np.asarray(path_n.state, dtype=float).ravel())
            if channels.get("viterbi_mean"):
                columns.append(np.asarray(path_n.mean, dtype=float).ravel())
        if not columns:
            continue
        length = columns[0].size
        blocks.append(np.column_stack([np.full(length, n + 1.0)] + columns))
    traces = np.vstack(blocks) if blocks else np.zeros((0, 0))
    if fmt == "mat":
        import scipy.io as sio

        sio.savemat(path, {"traces": traces})
    elif fmt == "dat":
        with open(path, "w", newline="") as handle:
            for row in traces:
                handle.write("".join(_fmt_e(v, "%16.7e") for v in row) + "\n")
    else:
        raise ValueError(f"unknown trace export format {fmt!r}")
    return traces


# --------------------------------------------------------------------------- #
# Plain FRET traces for the headless command line
# --------------------------------------------------------------------------- #
def fret_efficiency(donor: np.ndarray, acceptor: np.ndarray) -> np.ndarray:
    """Uncorrected proximity ratio ``E = acceptor / (donor + acceptor)``.

    Parameters
    ----------
    donor, acceptor : numpy.ndarray
        Per-frame donor and acceptor intensities.

    Returns
    -------
    numpy.ndarray
        FRET efficiency per frame; frames with zero total intensity yield 0.
    """
    donor = np.asarray(donor, dtype=float)
    acceptor = np.asarray(acceptor, dtype=float)
    total = donor + acceptor
    out = np.zeros_like(total)
    nonzero = total != 0
    out[nonzero] = acceptor[nonzero] / total[nonzero]
    return out


def load_stacked_dat(path: str) -> list[np.ndarray]:
    """Load a stacked ``[id, donor, acceptor]`` table as one FRET trace per id.

    A convenience for the command line: every row is data (no label row is
    consumed, unlike :func:`load_raw`) and the signal is
    :func:`fret_efficiency`.

    Parameters
    ----------
    path : str
        Path to the ``.dat`` file.

    Returns
    -------
    list of numpy.ndarray
        One FRET-efficiency trace per unique id, in ascending id order.
    """
    raw = np.loadtxt(path)
    if raw.ndim != 2 or raw.shape[1] < 3:
        raise ValueError(f"expected a stacked [id, donor, acceptor] table, got shape {raw.shape}")
    ids = raw[:, 0].astype(int)
    donor = raw[:, 1]
    acceptor = raw[:, 2]
    traces: list[np.ndarray] = []
    for trace_id in np.unique(ids):
        mask = ids == trace_id
        traces.append(fret_efficiency(donor[mask], acceptor[mask]))
    return traces
