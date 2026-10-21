"""Import a legacy burstwise analysis folder into a PTO.MFDB container.

The old layout — ``bi4_bur/*.bur`` merged by position with ``bg4``/``br4``
companions, ``BIDs/*.bst`` photon indices, an ``Info`` folder holding the
analysis settings, and an ``.mti`` file naming the raw TTTR each burst
search consumed — is the analysis output of the Paris/SoftCorr era. fdb4chembio
deposits need it as one ``.mmfdb.pto`` per measurement: the instrument file
verbatim at the front, the burst table and every companion as artifacts at
``burst`` grain, columns renamed to the dictionary's spelling, and the
provenance the folder could only carry in its name and its Info file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

__all__ = [
    "BurstwiseImportError",
    "ImportReport",
    "convert_folder",
    "parse_info",
    "read_legacy_table",
    "rename_columns",
    "scan_folder",
]

#: directory endings this importer knows, mapped to their table role.
COMPANION_DIRS = {
    "bi4_bur": "bursts",
    "bur": "bursts",
    "bg4": "mle_green",
    "br4": "mle_red",
    "bv4": "bva",
    "2c4": "kde_cde",
}

#: analysis parameters carried in the folder name, e.g. ``All 0.1066#60``.
_FOLDER_NAME_RE = re.compile(
    r"burstwise_(?P<selection>[^ ]+) (?P<threshold>[0-9.]+)#(?P<min_photons>\d+)",
    re.IGNORECASE,
)


class BurstwiseImportError(ValueError):
    """A folder that cannot be imported as-is — raised instead of guessing."""


# -- reading the legacy layout -------------------------------------------------


def scan_folder(folder: str | Path) -> dict:
    """Inventory a burstwise folder: tables found, per stem, plus provenance.

    Parameters
    ----------
    folder : path-like
        The ``burstwise_*`` directory.

    Returns
    -------
    dict
        ``{"tables": {stem: {role: file}}, "info": path|None, "mti": path|None,
        "parameters": {...from the folder name}}``
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise BurstwiseImportError(f"{folder} is not a directory")
    out: dict = {"tables": {}, "info": None, "mti": None, "parameters": {}}
    for sub in sorted(folder.iterdir()):
        if not sub.is_dir():
            continue
        role = COMPANION_DIRS.get(sub.name.lower())
        if role is None:
            continue
        for f in sorted(sub.iterdir()):
            if not f.is_file():
                continue
            stem = _stem_of(f.name)
            out["tables"].setdefault(stem, {})[role] = f
        # the BIDs directory holds .bst photon-index files, not tables
    info_dir = folder / "Info"
    if info_dir.is_dir():
        for f in sorted(info_dir.iterdir()):
            name = f.name.lower()
            if name.endswith(".txt"):
                out["info"] = f
            elif name.endswith(".bin"):
                out["info_bin"] = f
    for f in sorted(folder.rglob("*.mti")):
        out["mti"] = f
        break
    m = _FOLDER_NAME_RE.search(folder.name)
    if m:
        out["parameters"] = {
            "selection": m.group("selection"),
            "threshold": float(m.group("threshold")),
            "min_photons": int(m.group("min_photons")),
        }
    return out


def _stem_of(filename: str) -> str:
    """``Split_x-0000_0.bur`` -> ``Split_x-0000`` (drop _N measurement index)."""
    stem = Path(filename).stem
    return re.sub(r"_\d+$", "", stem)


def read_legacy_table(path: str | Path) -> dict[str, np.ndarray]:
    """Read one legacy ``.bur``/``.bg4``/``.br4`` file into name -> column.

    Applies the legacy contract: zero-interleaved rows (a zero row precedes
    every data row), trailing-tab header, numeric columns beside optional
    string columns (``First File``/``Last File`` hold file names).

    A column is numeric when every non-empty data value parses as a float;
    otherwise it is returned as a string array. Zero rows are dropped, so
    ``len(first column)`` equals the number of bursts.
    """
    path = Path(path)
    lines = path.read_text(errors="replace").split("\n")
    header = [c.strip() for c in lines[0].split("\t")]
    header = [c for c in header if c]
    data_rows: list[list[str]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("\t")][: len(header)]
        if len(parts) < len(header):
            parts = parts + [""] * (len(header) - len(parts))
        data_rows.append(parts)
    if not data_rows:
        return {c: np.zeros(0) for c in header}
    # de-interleave: drop the all-zero filler rows that precede each data row
    def _is_zero_row(parts: list[str]) -> bool:
        try:
            return all(float(p) == 0.0 for p in parts if p)
        except ValueError:
            return False

    data_rows = [r for r in data_rows if not _is_zero_row(r)]
    columns: dict[str, np.ndarray] = {}
    for i, name in enumerate(header):
        vals = [r[i] for r in data_rows]
        try:
            columns[name] = np.asarray([float(v) for v in vals], dtype=np.float64)
        except ValueError:
            columns[name] = np.asarray(vals, dtype=object)
    return columns


def parse_info(path: str | Path) -> dict:
    """Parse a ``Paris*info.txt`` into a flat parameter dict."""
    text = Path(path).read_text(errors="replace")
    params: dict[str, str] = {}
    for line in text.split("\n"):
        parts = [p.strip(" \t\u0000") for p in line.split("\t")]
        parts = [p for p in parts if p]
        if len(parts) >= 3:
            params[parts[1].rstrip(":")] = parts[2]
    # drop binary blobs early (TAC linearisation tables carry raw bytes)
    return {k: v for k, v in params.items() if len(str(v)) < 200}


def parse_mti(path: str | Path) -> dict[str, float]:
    """Parse an ``.mti`` file: original TTTR path -> duration (s)."""
    out: dict[str, float] = {}
    for line in Path(path).read_text(errors="replace").split("\n"):
        parts = line.split("\t")
        if len(parts) == 2 and parts[0].strip():
            try:
                out[parts[0].strip()] = float(parts[1])
            except ValueError:
                pass
    return out


# -- renaming to the dictionary ------------------------------------------------


def dictionary_columns() -> dict[str, dict]:
    """Return {legacy column name: {term, units, symbol}} from the dictionary.

    Loaded from mmfdb's ``mmfdb_workflow_ext.dic`` — never hardcoded, so a
    dictionary change moves this map with it.
    """
    try:
        from mmfdb.schema.pdbx_metadata import MmcifDictionary
    except ImportError:  # pragma: no cover - env without mmfdb
        return {}
    try:
        path = Path(MmcifDictionary._resolve_dic("mmfdb_workflow_ext"))
    except Exception:  # pragma: no cover - dict not installed
        return {}
    if not path.is_file():
        # _resolve_dic returns a name-relative path; .dic is appended on load
        cand = path.with_name(path.name + ".dic")
        path = cand if cand.is_file() else path
    if not path.is_file():
        return {}
    # The dictionary is a DDLm-style CIF; read the mmfdb_burst_column save
    # frames directly (the schema API shape varies across versions).
    import re as _re

    text = path.read_text(errors="replace")
    frame_pat = _re.compile(
        r"save__mmfdb_burst_column\.([a-z0-9_]+)(.*?)save_", _re.DOTALL
    )
    terms: dict[str, dict] = {}
    for m in frame_pat.finditer(text):
        term, body = m.group(1), m.group(2)
        col = _re.search(r'_mmfdb_burst_column\.column\s+"([^"]+)"', body)
        units = _re.search(r"_mmfdb_burst_column\.units\s+(\S+)", body)
        if col:
            terms[col.group(1)] = {
                "term": f"_mmfdb_burst_column.{term}",
                "units": units.group(1).strip() if units else "",
            }
    return terms


def rename_columns(
    columns: list[str], dictionary: dict[str, dict] | None = None
) -> tuple[dict[str, str], list[str]]:
    """Return ({old: new}, unmapped).

    Rules:
    - exact dictionary match -> keep (already conformant)
    - whitespace-normalised match (double spaces, Macrotime vs Macro Time)
      -> dictionary spelling
    - unknown -> kept verbatim and flagged, never silently renamed
    """
    if dictionary is None:
        dictionary = dictionary_columns()
    renames: dict[str, str] = {}
    unmapped: list[str] = []
    norm = {re.sub(r"\s+", " ", k).strip(): k for k in dictionary}
    for col in columns:
        if col in dictionary:
            continue
        n = re.sub(r"\s+", " ", col).strip()
        n2 = n.replace("Macrotime", "Macro Time")
        for cand in (n, n2):
            if cand in norm:
                renames[col] = norm[cand]
                break
        else:
            unmapped.append(col)
    return renames, unmapped


# -- conversion ----------------------------------------------------------------


@dataclass
class ImportReport:
    """What one folder import produced."""

    containers: list[str] = field(default_factory=list)
    stems: list[str] = field(default_factory=list)
    unmapped_columns: dict[str, list[str]] = field(default_factory=dict)
    parameters: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"containers written: {len(self.containers)}",
            f"measurements: {len(self.stems)}",
        ]
        if self.unmapped_columns:
            lines.append("unmapped columns: " + ", ".join(
                f"{k}: {v}" for k, v in self.unmapped_columns.items() if v
            ))
        return "\n".join(lines)


def convert_folder(
    folder: str | Path,
    source_resolver=None,
    out_dir: str | Path | None = None,
    *,
    dry_run: bool = False,
    raw_data: str = "embed",
) -> ImportReport:
    """Convert a legacy burstwise measurement into ONE ``.mmfdb.pto``.

    The deposition unit is the *measurement* — one folder of raw files with
    its ``burstwise_*`` analysis trees — so one container is written per
    measurement folder, holding every stem's burst tables and every tree's
    threshold settings, referencing all its raw files. A ``burstwise_*``
    folder given directly is normalized to its parent measurement; all trees
    of that measurement are converted (the other trees are beside it, and
    stopping at one would ship half the analysis).

    Parameters
    ----------
    folder : path-like
        The measurement folder, or one of its ``burstwise_*`` directories.
    source_resolver : callable, optional
        ``stem -> local path of the raw TTTR``; without it (or when it returns
        None) the stem is skipped and reported — never guessed.
    out_dir : path-like, optional
        Where to write ``<measurement>.mmfdb.pto`` (default: the measurement
        folder).
    dry_run : bool
        Report what would be written; write nothing.
    raw_data : {"embed", "sidecar"}, optional
        "embed": instrument files verbatim inside the container (default).
        "sidecar": analysis-only container; the raw files stay beside it and
        their identity (sha256, size, name, path) is recorded as container
        tags -- the deposition layout, where raw files ship alongside.

    Returns
    -------
    ImportReport
    """
    folder = Path(folder)
    if any(p.is_dir() for p in folder.glob("burstwise_*")):
        measurement = folder          # given the measurement itself
    elif folder.name.startswith("burstwise_"):
        measurement = folder.parent   # given one of its trees
    else:
        # a lone tree without the naming convention: its parent is the
        # measurement, the folder the only tree
        measurement = folder.parent
    return convert_measurement(
        measurement, source_resolver, out_dir, dry_run=dry_run, raw_data=raw_data
    )


def convert_measurement(
    folder: str | Path,
    source_resolver=None,
    out_dir: str | Path | None = None,
    *,
    dry_run: bool = False,
    raw_data: str = "embed",
) -> ImportReport:
    """Convert every burstwise tree of one measurement into one container.

    One raw-file set, one ``burstwise_*`` tree per threshold setting, one
    container: ``<measurement folder>.mmfdb.pto`` holds, for every stem, its
    ``<stem>/bursts`` selection and ``<stem>/mle_*`` companions from every
    tree (same object name, distinct settings hash — the run identity), and
    references each raw file exactly once (sidecar tags or embedded payload,
    per *raw_data*). Tables derive from their own stem's stream, so a reader
    can walk result -> raw without guessing among the measurement's files.
    """
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    folder = Path(folder)
    trees = sorted(
        p for p in folder.iterdir()
        # a tree is a folder that holds the legacy subfolders; the deposition
        # tree names them `burstwise_*`, fixtures and local copies may not
        if p.is_dir() and (p / "bi4_bur").is_dir()
    )
    if not trees:
        raise BurstwiseImportError(f"no burstwise analysis tree in {folder}")
    out_dir = Path(out_dir) if out_dir else folder
    dictionary = dictionary_columns()

    # resolve the union of raws across trees first: the container is created
    # once with every file of the measurement, not per stem or per tree
    raw_by_stem: dict[str, Path] = {}
    per_tree = []
    for tree in trees:
        inventory = scan_folder(tree)
        info_params = parse_info(inventory["info"]) if inventory["info"] else {}
        mti = parse_mti(inventory["mti"]) if inventory["mti"] else {}
        per_tree.append((tree, inventory, info_params, mti))
        for stem, roles in sorted(inventory["tables"].items()):
            if "bursts" not in roles or stem in raw_by_stem:
                continue
            raw = source_resolver(stem, mti) if source_resolver else None
            if raw is not None:
                raw_by_stem[stem] = Path(raw)

    report = ImportReport()
    container = out_dir / f"{folder.name}.mmfdb.pto"
    if not dry_run and raw_by_stem:
        _create_container(container, sorted(raw_by_stem.values(), key=lambda p: p.name),
                          folder.name, raw_data)
        report.containers.append(str(container))
    elif dry_run:
        report.containers.append(str(container))
    # keep per-tree folder parameters reachable for callers (GUI summary)
    report.parameters = {
        tree.name: inventory["parameters"] for tree, inventory, _i, _m in per_tree
    }

    # all rollover files of one acquisition are ONE measurement: per tree
    # (threshold setting) the stems' tables concatenate into ONE bursts table
    # and ONE table per companion -- rows carry their file origin in the legacy
    # First File/Last File columns -- instead of one table set per file
    wrote_any = False
    for tree, inventory, info_params, mti in per_tree:
        stems_here = []
        for stem, roles in sorted(inventory["tables"].items()):
            if "bursts" not in roles:
                continue
            report.stems.append(stem)
            if raw_by_stem.get(stem) is not None:
                stems_here.append((stem, roles))
            else:
                report.unmapped_columns.setdefault(stem, []).append("<no source TTTR>")
        if not stems_here or dry_run:
            continue
        _write_concatenated(
            container, stems_here, dictionary, info_params,
            inventory["parameters"], report, write_burst_artifact, raw_data,
        )
        wrote_any = True
    if wrote_any:
        _compact_container(container)
    return report


def _create_container(container, raws, title, raw_data):
    """Create the measurement's container referencing every raw file once.

    ``Measurement.create`` names its file after the first raw stem; the
    deposition unit is the measurement, so the file is renamed to
    ``<measurement>.mmfdb.pto`` after the handle is closed.
    """
    from chisurf.core.fio.pto import Measurement, is_measurement

    container = Path(container)
    if is_measurement(container):
        return
    with Measurement.create(
        raws, out_dir=container.parent, title=title, raw_data=raw_data
    ) as m:
        created = Path(m.path)
    if created != container:
        created.replace(container)


def _compact_container(container):
    """Rewrite the container without the void left by repeated commits.

    Every table write opens the container, appends its objects, and commits;
    a commit rewrites the tag block, and the block it replaces stays in the
    file as Void. A measurement with hundreds of stems leaves hundreds of
    dead copies — megabytes around a few hundred kilobytes of analysis.
    ``compact`` streams every payload into a fresh file and writes the tags
    once, so the result carries no dead space.
    """
    from chisurf.core.fio.pto import Measurement

    container = Path(container)
    target = container.with_name(container.name + ".compact")
    with Measurement.open(container, writable=True) as m:
        if not m._f.compact(str(target), False, 0.25):
            raise BurstwiseImportError(
                f"could not compact {container}: {m._f.error()}"
            )
    container.unlink()
    target.replace(container)

def _concat(tables: list[dict], dictionary, report, label):
    """Read, rename, and concatenate one role's tables across all stems.

    Row order follows stem order (lexical), and the legacy string columns
    ``First File``/``Last File`` carry each row's file origin, so the merged
    table stays traceable to its raw file without one table per file.
    """
    merged: dict[str, list] = {}
    unmapped: list[str] = []
    renames_all: dict[str, str] = {}
    for table_path in tables:
        table = read_legacy_table(table_path)
        renames, unm = rename_columns(list(table), dictionary)
        unmapped.extend(u for u in unm if u not in unmapped)
        renames_all.update(renames)
        if renames:
            table = {renames.get(k, k): v for k, v in table.items()}
        for col, vals in table.items():
            merged.setdefault(col, []).extend(np.asarray(vals).tolist())
    if unmapped:
        report.unmapped_columns[label] = unmapped
    return {c: np.asarray(v) for c, v in merged.items()}, renames_all


def _write_concatenated(
    container, stems_here, dictionary, info_params, folder_params, report,
    write_burst_artifact, raw_data,
):
    """Write one tree's analysis of the WHOLE measurement into the container.

    All rollover files of the acquisition are one measurement, so one
    ``bursts`` selection and one table per companion are written per threshold
    setting (tree) -- not one set per file. The container already references
    every raw; the merged tables derive from all of them.
    """
    import numpy as np  # local: keep module import cost off the scan path

    label = folder_params.get("label") or "measurement"
    burst_paths = [roles["bursts"] for _stem, roles in stems_here]
    burst_table, renames = _concat(burst_paths, dictionary, report, f"{label}/bursts")
    settings = {
        "source": "legacy burstwise folder",
        "folder_parameters": folder_params,
        "info": info_params,
        "column_renames": renames,
        "n_files": len(stems_here),
    }
    write_burst_artifact(
        Path(container),
        burst_table,
        name="bursts",
        artifact_kind="burst_table",
        operation_type="burst_selection",
        row_grain="burst",
        parameters=settings,
        out_dir=str(Path(container).parent),
        raw_data=raw_data,
    )
    # companion tables are per-burst analyses of the same search: bg4/br4 are
    # the burst-wise MLE lifetime fits. `burst_lifetime_fitting` is the
    # dictionary term AND what ndX's reader recognises as a companion.
    # folder_parameters is in the identity: one measurement has several trees
    # (thresholds); without it every tree's companions share one settings
    # hash and the second tree would REPLACE the first's fits.
    roles_present = sorted(
        {r for _stem, roles in stems_here for r in roles if r != "bursts"}
    )
    for role in roles_present:
        table, _ren = _concat(
            [roles[role] for _stem, roles in stems_here if role in roles],
            dictionary, report, f"{label}/{role}",
        )
        write_burst_artifact(
            Path(container),
            table,
            name=role,
            artifact_kind="burst_table",
            operation_type="burst_lifetime_fitting",
            row_grain="burst",
            parameters={
                "source_role": role,
                "info": info_params,
                "folder_parameters": folder_params,
                "n_files": len(stems_here),
            },
            derived_from="bursts",
            out_dir=str(Path(container).parent),
            raw_data=raw_data,
        )
