"""Regenerate the MalE prototype golden file (``male_prototype.json``) and the shipped CSV tables.

    QT_QPA_PLATFORM=offscreen <arm64>/bin/python \\
        chisurf/plugins/quenching_estimator/test/baselines/make_male_prototype.py [--convert]

The reference is the MalE quenching-analysis notebook
(``~/dev/quest/prototype/male_quenching_analysis.ipynb``), which is scientifically the newest
statement of the method. This script does **not** copy numbers from it. It *executes* the
notebook's deterministic code cells -- settings, Steps 0-3, the site tables of cell 25 (read
from the prototype's own ``cache/``), the ``Site`` model of cell 29 -- and records what they
compute at full precision. The notebook's printed tables are rounded to 2-4 digits, and the
CSVs in ``prototype/output/`` partly come from an older model; neither is a fit reference.

What is *not* executed is the 64-start graph fit (cell 33 onwards, ~25 min on 44 cores). Its
printed estimates are parsed from the notebook's stored outputs (section ``printed``), and the
``Site`` model is evaluated at those printed parameter sets (section ``site_lifetimes``), so a
port of ``Site`` can be checked row by row without re-running the fit.

Changes made to the executed cells, and nothing else:

- the settings cell's folders point at absolute paths (data, cache, a scratch output folder);
- cell 23 reads the two structures from ``examples/male/*.cif`` instead of downloading them;
- matplotlib draws to the Agg backend and ``plt.show`` does nothing.

Every site table must already be in the cache: a table built here would come from this
machine's IMP.bff, not the one the notebook ran on, so a missing table stops the script.

``--convert`` first rewrites ``examples/male/*.csv`` and ``provenance.json`` from the two
workbooks in ``~/dev/quest/data`` (needs openpyxl; one-off, not a runtime dependency). Either
way the script checks that the shipped CSVs, read by
:mod:`~chisurf.plugins.quenching_estimator.core.inference.measurements`, give exactly the
frames the notebook reads from the workbooks.

Running it needs the prototype's own environment: pandas, scipy, biopython, matplotlib,
openpyxl and IMP.bff (all present in the ``arm64`` env). None of them is a ChiSurf runtime
dependency; this file is test tooling.

The rule for regenerating: a commit that changes ``male_prototype.json`` says in ``okf/log.md``
which numbers moved and why.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import platform
import re
import shutil
import sys
import tempfile
from pathlib import Path

BASELINE_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[5]
EXAMPLES = PLUGIN_DIR / "examples" / "male"
GOLDEN = BASELINE_DIR / "male_prototype.json"
SITE_FIXTURE = PLUGIN_DIR / "test" / "data" / "male_site_1omp72_L20.12.npz"

FITS_WORKBOOK = "260929_All fits MalE.xlsx"
TITRATION_WORKBOOK = "amino acids dynamic quenching.xlsx"

#: The workbook columns kept in the shipped CSVs (sheet name -> columns, CSV file).
LIFETIME_COLUMNS = ["Date", "D2O %", "Variant", "Dye", "Condition", "tauX", "Data path name"]
FLT_COLUMNS = ["Date", "Dye", "Amino acid", "Concentration, mM", "tauX0, ns", "tauX"]
#: The summary workbook has two columns named "+/-"; the CSV uses the notebook's names.
SUMMARY_COLUMNS = [
    ("Dye", "dye"),
    ("Quencher", "quencher"),
    ("n dates", "n_dates"),
    ("n points", "n_points"),
    ("tau0, ns", "tau0_ns"),
    ("KSV, 1/M", "KSV_per_M"),
    ("+/-", "KSV_err_per_M"),
    ("kq, 1/(M s)", "kq_per_M_s"),
    ("+/-", "kq_err_per_M_s"),
]

#: Code cells executed, with a fragment each must contain (guards against a renumbered notebook).
CELLS = {
    2: "DATA_FOLDER",
    4: "def save_table",
    6: "LINKER_LENGTH",
    8: "def load_lifetimes",
    10: "def titration_posterior",
    13: "def water_quenching",
    15: "def series_fits",
    17: "def lifetimes_per_site",
    19: "def kq_vector",
    21: "def stretched_linker_length",
    23: "def accessible_volume",
    25: "def site_table",
    27: "chapter5_water_exposure",
    29: "class Site",
    31: "def sites_for",
}
#: Stored outputs that are parsed (cell -> what).
PRINTED_CELLS = {
    "estimates": 58,
    "k_graph": 33,
    "loo": {
        "AF488 in H2O": 37,
        "Cy3B in H2O": 42,
        "Atto655 in D2O": 45,
        "Atto655 in D2O and H2O": 55,
    },
    "text": [8, 10, 13, 15, 17, 21, 23, 33, 35, 39, 42, 45, 46, 48, 55],
}
#: Stage label -> (dye, rows variable, tau0 key) as in cells 33 and 45.
STAGES = {
    "AF488 in H2O": ("AF488", "rows_af488", ("AF488", "H2O")),
    "Cy3B in H2O": ("Cy3B", "rows_cy3b", ("Cy3B", "H2O")),
    "Atto655 in D2O": ("Atto655", "rows_d2o", ("Atto655", "D2O")),
    "Atto655 in D2O and H2O": ("Atto655", "rows_joint", ("Atto655", "D2O")),
}


def sha256(path):
    """Hex SHA-256 of a file.

    Parameters
    ----------
    path : pathlib.Path
        The file.

    Returns
    -------
    str
        The digest.
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(value):
    """Make a value JSON-safe at full precision.

    Parameters
    ----------
    value : object
        A number, numpy scalar/array, mapping or sequence.

    Returns
    -------
    object
        Plain Python; NaN and infinities become ``None``.
    """
    import numpy as np

    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        value = float(value)
        return value if math.isfinite(value) else None
    return value


def records(frame, columns=None):
    """Rows of a pandas frame as JSON-safe dicts.

    Parameters
    ----------
    frame : pandas.DataFrame
        The table.
    columns : list of str, optional
        Columns to keep; all by default.

    Returns
    -------
    list of dict
        One dict per row, in frame order.
    """
    frame = frame if columns is None else frame[columns]
    return [clean(dict(zip(frame.columns, row))) for row in frame.itertuples(index=False)]


# ----------------------------------------------------------------------------- conversion


def _cell(value):
    """Write one workbook cell as CSV text that reads back to the same value.

    Parameters
    ----------
    value : object
        The openpyxl value.

    Returns
    -------
    str
        ``""`` for empty, ``repr`` for floats (round-trips exactly), ``str`` otherwise.
    """
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _sheet(path, sheet=None):
    """Header and rows of one sheet.

    Parameters
    ----------
    path : pathlib.Path
        Workbook.
    sheet : str, optional
        Sheet name; the active sheet by default.

    Returns
    -------
    tuple
        ``(header, rows)``; rows are tuples of raw values, fully empty rows dropped.
    """
    import openpyxl

    book = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = book[sheet] if sheet else book.active
    rows = list(ws.iter_rows(values_only=True))
    book.close()
    header = list(rows[0])
    body = [row for row in rows[1:] if any(v is not None and v != "" for v in row)]
    return header, body


def _write_csv(path, header, rows):
    """Write rows as UTF-8 CSV with a header line.

    Parameters
    ----------
    path : pathlib.Path
        Target file.
    header : list of str
        Column names.
    rows : list of list
        Raw values, written with :func:`_cell`.
    """
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow([_cell(v) for v in row])


def convert(data_folder):
    """Rewrite the shipped CSVs and ``provenance.json`` from the two workbooks.

    Parameters
    ----------
    data_folder : pathlib.Path
        Folder with the two MalE workbooks.
    """
    fits, titr = data_folder / FITS_WORKBOOK, data_folder / TITRATION_WORKBOOK
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    files = {}

    header, body = _sheet(fits, "TCSPC fit results")
    keep = [header.index(c) for c in LIFETIME_COLUMNS]
    body = [row for row in body if row[header.index("Dye")] not in (None, "")]
    _write_csv(
        EXAMPLES / "tcspc_fit_results.csv", LIFETIME_COLUMNS, [[r[i] for i in keep] for r in body]
    )
    files["tcspc_fit_results.csv"] = dict(
        workbook=FITS_WORKBOOK, sheet="TCSPC fit results", rows=len(body), columns=LIFETIME_COLUMNS
    )

    header, body = _sheet(fits, "amino acid quenching FLT")
    keep = [header.index(c) for c in FLT_COLUMNS]
    _write_csv(
        EXAMPLES / "amino_acid_quenching_flt.csv", FLT_COLUMNS, [[r[i] for i in keep] for r in body]
    )
    files["amino_acid_quenching_flt.csv"] = dict(
        workbook=FITS_WORKBOOK,
        sheet="amino acid quenching FLT",
        rows=len(body),
        columns=FLT_COLUMNS,
    )

    header, body = _sheet(titr)
    expected = [c for c, _ in SUMMARY_COLUMNS]
    if header[: len(expected)] != expected:
        raise SystemExit(f"unexpected titration summary header {header}")
    names = [n for _, n in SUMMARY_COLUMNS]
    _write_csv(EXAMPLES / "titration_summary.csv", names, [list(r[: len(names)]) for r in body])
    files["titration_summary.csv"] = dict(
        workbook=TITRATION_WORKBOOK,
        sheet="Sheet1",
        rows=len(body),
        columns=names,
        renamed_from=expected,
    )

    for name, entry in files.items():
        entry["sha256"] = sha256(EXAMPLES / name)
    provenance = {
        "dataset": "MalE (maltose-binding protein) labelled with AF488, Cy3B and Atto655 at nine sites, "
        "apo (PDB 1OMP) and holo (PDB 1ANF), in H2O/D2O mixtures; free-dye amino-acid titrations",
        "owner": "Thomas-Otavio Peulen (own measurements)",
        "date": "2026-09-29",
        "source_workbooks": {
            FITS_WORKBOOK: {"sha256": sha256(fits), "bytes": fits.stat().st_size},
            TITRATION_WORKBOOK: {"sha256": sha256(titr), "bytes": titr.stat().st_size},
        },
        "converted_by": "chisurf/plugins/quenching_estimator/test/baselines/make_male_prototype.py --convert",
        "conversion": "cell values copied verbatim (floats written with repr, so they read back bit-exact); "
        "only the listed columns are kept; rows without a dye are dropped from the lifetime table",
        "files": files,
        "structures": {
            "1OMP.cif": {
                "pdb": "1OMP",
                "state": "APO",
                "source": "~/dev/imp.bff/examples/structure/MBP/1OMP.cif",
                "license": "PDB data, CC0 1.0",
                "sha256": sha256(EXAMPLES / "1OMP.cif"),
            },
            "1ANF.cif": {
                "pdb": "1ANF",
                "state": "HOLO",
                "source": "~/dev/imp.bff/examples/structure/MBP/1ANF.cif",
                "license": "PDB data, CC0 1.0",
                "sha256": sha256(EXAMPLES / "1ANF.cif"),
            },
        },
        "site_number_rule": "the site is taken from the data file name (MalE<site><dye>) where it differs from Variant",
    }
    (EXAMPLES / "provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"converted {', '.join(files)} into {EXAMPLES}")


# ----------------------------------------------------------------------------- the notebook


#: First line of the markdown notes added when the prototype was marked as migrated (quest
#: ``prototype/MIGRATED.md``). They are dropped on reading, so every index in this file keeps
#: meaning the cell of the stored run.
MIGRATION_NOTE = re.compile(r"^> \*\*(This notebook has been m|M)igrated to ChiSurf")


def notebook_cells(path):
    """Code cell sources and stored outputs of the notebook, without the migration notes.

    Parameters
    ----------
    path : pathlib.Path
        The ``.ipynb`` file.

    Returns
    -------
    list of dict
        The notebook's cells as stored, minus the markdown cells that mark it as migrated.
    """
    cells = json.loads(Path(path).read_text())["cells"]
    return [
        c
        for c in cells
        if not (c["cell_type"] == "markdown" and MIGRATION_NOTE.match("".join(c["source"])))
    ]


def source(cells, index):
    """Source of one code cell, checked against :data:`CELLS`.

    Parameters
    ----------
    cells : list of dict
        Notebook cells.
    index : int
        Cell index.

    Returns
    -------
    str
        The cell's source.
    """
    cell = cells[index]
    text = "".join(cell["source"])
    if cell["cell_type"] != "code" or CELLS.get(index, "") not in text:
        raise SystemExit(f"cell {index} is not the expected code cell: the notebook changed")
    return text


def replace_once(text, old, new, count=1):
    """Replace a fragment that must occur exactly ``count`` times.

    Parameters
    ----------
    text, old, new : str
        Source, fragment, replacement.
    count : int, optional
        Required number of occurrences.

    Returns
    -------
    str
        The patched source.
    """
    if text.count(old) != count:
        raise SystemExit(f"patch target {old!r} found {text.count(old)}x, expected {count}")
    return text.replace(old, new)


def outputs_text(cell, kinds=("stream",)):
    """Stored text output of one cell.

    Parameters
    ----------
    cell : dict
        Notebook cell.
    kinds : tuple of str
        ``stream`` and/or ``execute_result``.

    Returns
    -------
    str
        Concatenated text, without "figure saved"/"table saved" lines.
    """
    out = []
    for o in cell.get("outputs", []):
        if o["output_type"] not in kinds:
            continue
        text = o.get("text") or o.get("data", {}).get("text/plain") or ""
        out.append("".join(text))
    lines = [
        ln
        for ln in "".join(out).splitlines()
        if "figure saved" not in ln and "table saved" not in ln
    ]
    return "\n".join(lines).strip("\n")


ESTIMATE_LINE = re.compile(
    r"^\s*\d+\s+(?P<stage>.+?)\s+(?P<parameter>s_\w+|scale|delta_static|delta|lam|static|dtau_shield|model_error)"
    r"\s+(?P<value>-?[\d.]+)\s+(?P<low>-?[\d.]+)\s+(?P<high>-?[\d.]+)\s*(?P<note>.*)$"
)


def printed_section(cells):
    """Parse the rounded numbers the stored notebook run printed for the fit stages.

    Parameters
    ----------
    cells : list of dict
        Notebook cells with outputs.

    Returns
    -------
    dict
        ``estimates`` (stage -> rows), ``k_graph`` rows, ``loo`` (stage -> site -> |z|),
        ``text`` (cell -> stream text), ``run_stamp``.
    """
    estimates = {}
    for line in outputs_text(cells[PRINTED_CELLS["estimates"]], ("execute_result",)).splitlines()[
        1:
    ]:
        m = ESTIMATE_LINE.match(line)
        if not m:
            raise SystemExit(f"cannot parse estimate line {line!r}")
        estimates.setdefault(m["stage"], []).append(
            dict(
                parameter=m["parameter"],
                value=float(m["value"]),
                low_68=float(m["low"]),
                high_68=float(m["high"]),
                note=m["note"].strip(),
            )
        )
    k_graph = []
    for line in outputs_text(cells[PRINTED_CELLS["k_graph"]], ("execute_result",)).splitlines()[1:]:
        parts = line.split()
        k_graph.append(
            dict(
                dye=parts[1],
                amino_acid=parts[2],
                K_titration=float(parts[3]),
                sd_titration=float(parts[4]),
                K_graph=float(parts[5]),
                low_68=float(parts[6]),
                high_68=float(parts[7]),
            )
        )
    loo = {}
    for stage, index in PRINTED_CELLS["loo"].items():
        text = outputs_text(cells[index])
        block = text.split("site\n", 1)[1]
        loo[stage] = {}
        for line in block.splitlines():
            m = re.match(r"^(\d+)\s+([\d.]+)$", line.strip())
            if not m:
                break
            loo[stage][m[1]] = float(m[2])
    text = {str(i): outputs_text(cells[i]) for i in PRINTED_CELLS["text"]}
    stamp = re.search(r"prefix (\d{8}-\d{6})", outputs_text(cells[4]))
    return dict(
        run_stamp=stamp[1] if stamp else None,
        estimates=estimates,
        k_graph=k_graph,
        loo=loo,
        text=text,
        note="rounded as printed by the stored notebook run; not full precision",
    )


def stage_theta(ns, stage, printed_rows):
    """The parameter dict ``Site`` takes, built from one stage's printed estimates.

    Parameters
    ----------
    ns : dict
        Namespace of the executed notebook.
    stage : str
        Stage label.
    printed_rows : list of dict
        That stage's printed estimate rows.

    Returns
    -------
    dict
        ``ln_*`` / linear parameters as the notebook's ``Block.theta`` builds them, ``ln_tau0``
        from the block's tau0, and ``kq`` from the titration posterior means (``K_MEAN``).
    """
    import numpy as np

    dye, _, tau0_key = STAGES[stage]
    th = {}
    for row in printed_rows:
        p = row["parameter"]
        if p == "model_error":
            continue
        log = p.startswith("s_") or p in ("scale", "static")
        th[("ln_" + p) if log else p] = float(np.log(row["value"])) if log else float(row["value"])
    th["ln_tau0"] = float(np.log(ns["TAU0"][tau0_key]))
    th["kq"] = ns["kq_vector"](dye, ns["K_MEAN"])
    return th


def run_notebook(quest, cells, run_walk):
    """Execute the deterministic cells and return their namespace.

    Parameters
    ----------
    quest : pathlib.Path
        The quest checkout.
    cells : list of dict
        Notebook cells.
    run_walk : bool
        Run cell 23's random-walk validation (about 2 min).

    Returns
    -------
    dict
        The namespace after cell 31 plus the row selections of cell 33.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.show = lambda *a, **k: None
    prototype = quest / "prototype"
    output = Path(tempfile.mkdtemp(prefix="male_prototype_output_"))
    os.environ.setdefault("IMP_BFF_GPU", "off")
    ns = {"__name__": "male_prototype", "display": lambda *a, **k: None}
    for index in CELLS:
        text = source(cells, index)
        if index == 2:
            exec(compile(text, f"cell{index}", "exec"), ns)
            ns.update(
                DATA_FOLDER=str(quest / "data"),
                CACHE_FOLDER=str(prototype / "cache"),
                OUTPUT_FOLDER=str(output),
                QUICK=False,
                RUN_VALIDATION=bool(run_walk),
                RUN_SAMPLER_CHECK=False,
            )
            continue
        if index == 23:
            text = replace_once(
                text,
                'for folder in [CACHE, Path("../../imp.bff")]:',
                "for folder in [STRUCTURE_FOLDER]:",
            )
            text = replace_once(text, 'f"{code_}.cif"', 'f"{code_.upper()}.cif"', count=3)
            ns["STRUCTURE_FOLDER"] = EXAMPLES
        if index == 25:
            head, tail = text.split("started = time.time()", 1)
            exec(compile(head, f"cell{index}", "exec"), ns)
            for L in sorted(set(ns["LINKER_LENGTH"].values())):
                for state in ns["STRUCTURES"]:
                    for site in ns["SITES"]:
                        if not table_path(ns, state, site, L).exists():
                            raise SystemExit(f"site table {state} {site} {L} is not in the cache")
            text = "started = time.time()" + tail
        print(f"--- cell {index}", flush=True)
        exec(compile(text, f"cell{index}", "exec"), ns)
        plt.close("all")
    selection = "".join(cells[33]["source"])
    head = selection.split('print("--- solving', 1)[0]
    if "rows_joint" not in head or "points_joint" not in head:
        raise SystemExit("cell 33 no longer starts with the row selection: the notebook changed")
    exec(compile(head, "cell33-rows", "exec"), ns)
    return ns


def table_path(ns, state, site, linker_length):
    """Cache path of one site table, keyed exactly as cell 25 keys it.

    Parameters
    ----------
    ns : dict
        Notebook namespace (settings defined).
    state : str
        ``APO`` or ``HOLO``.
    site : int
        Labelled residue.
    linker_length : float
        Linker length in Å.

    Returns
    -------
    pathlib.Path
        ``cache/site_<sha1[:16]>.npz``.
    """
    key = json.dumps(
        [
            "nb-v1",
            state,
            site,
            linker_length,
            ns["GRID"],
            ns["SLOW_RADIUS"],
            ns["RADIUS_OFFSETS"],
            ns["CLASH"],
            ns["QUENCHERS"],
            ns["RESIDUES"],
        ]
    )
    return Path(ns["CACHE"]) / f"site_{hashlib.sha1(key.encode()).hexdigest()[:16]}.npz"


def check_csv_reader(ns):
    """The shipped CSVs, read by the plugin, must equal what the notebook read from the workbooks.

    Parameters
    ----------
    ns : dict
        Notebook namespace after cell 10.

    Returns
    -------
    dict
        Row counts and corrections, for the golden file.
    """
    import numpy as np

    sys.path.insert(0, str(REPO_ROOT))
    from chisurf.plugins.quenching_estimator.core.inference import measurements as m

    data = m.load_measurements(EXAMPLES)
    fits, raw, titr = ns["lifetimes"], ns["raw"], ns["titrations"]

    def same(a, b, what):
        a, b = np.asarray(a, float), np.asarray(b, float)
        if a.shape != b.shape or not np.array_equal(a, b, equal_nan=True):
            raise SystemExit(f"CSV reader differs from the workbook in {what}")

    lt = data.lifetimes
    if len(lt) != len(fits):
        raise SystemExit(f"{len(lt)} lifetime rows from CSV, {len(fits)} from the workbook")
    same(lt["date"], fits["Date"], "Date")
    same(lt["d2o_percent"], fits["D2O %"], "D2O %")
    same(lt["variant"], fits["Variant"], "Variant")
    same(lt["tau_x"], fits["tauX"], "tauX")
    same(lt["site"], fits["site"], "site (corrected)")
    if (
        list(lt["dye"]) != list(fits["Dye"])
        or list(lt["condition"]) != list(fits["Condition"])
        or list(lt["data_path"]) != [str(v) for v in fits["Data path name"]]
    ):
        raise SystemExit("CSV reader differs from the workbook in a text column")

    tp = data.titration_points
    same(tp["date"], raw["Date"], "titration Date")
    same(tp["concentration_mM"], raw["conc_mM"], "concentration")
    same(tp["tau0_ns"], raw["tau0"], "tauX0")
    same(tp["tau_x"], raw["tauX"], "titration tauX")
    if list(tp["dye"]) != list(raw["Dye"]) or list(tp["amino_acid"]) != list(raw["amino_acid"]):
        raise SystemExit("CSV reader differs from the workbook in the titration text columns")

    ts = data.titration_summary
    for field, col in [
        ("tau0_ns", "tau0"),
        ("ksv_per_M", "KSV"),
        ("ksv_err_per_M", "KSV_err"),
        ("kq_per_M_s", "kq"),
        ("kq_err_per_M_s", "kq_err"),
        ("n_dates", "n_dates"),
        ("n_points", "n_points"),
    ]:
        same(ts[field], titr[col], f"summary {col}")
    print("CSV reader reproduces the workbook frames exactly")
    return dict(
        lifetime_rows=int(len(lt)),
        titration_points=int(len(tp)),
        titration_results=int(len(ts)),
        corrections=[
            dict(
                row=c.row,
                dye=c.dye,
                condition=c.condition,
                d2o_percent=c.d2o_percent,
                variant=c.variant,
                site=c.site,
            )
            for c in data.corrections
        ],
    )


def build_golden(ns, cells, quest, measurement_counts, run_walk):
    """Collect every recorded quantity.

    Parameters
    ----------
    ns : dict
        Executed notebook namespace.
    cells : list of dict
        Notebook cells.
    quest : pathlib.Path
        The quest checkout.
    measurement_counts : dict
        From :func:`check_csv_reader`.
    run_walk : bool
        Whether the random walk ran.

    Returns
    -------
    dict
        The golden document.
    """
    import IMP.bff as bff
    import numpy as np

    notebook = quest / "prototype" / "male_quenching_analysis.ipynb"
    printed = printed_section(cells)
    golden = {
        "about": {
            "what": "MalE quenching analysis prototype, deterministic cells executed at full precision",
            "regenerate": "QT_QPA_PLATFORM=offscreen <arm64>/bin/python "
            "chisurf/plugins/quenching_estimator/test/baselines/make_male_prototype.py",
            "generated": datetime.date.today().isoformat(),
            "notebook": {
                "path": "~/dev/quest/prototype/male_quenching_analysis.ipynb",
                "sha256": sha256(notebook),
            },
            "executed_cells": sorted(CELLS) + ["33 (row selection only)"],
            "imp_bff": getattr(bff, "__version__", None) or str(bff.get_module_version()),
            "numpy": np.__version__,
            "platform": f"{platform.system()} {platform.machine()} python {platform.python_version()}",
            "settings": {
                k: clean(ns[k])
                for k in (
                    "QUICK",
                    "RUN_VALIDATION",
                    "SITES",
                    "LINKER_LENGTH",
                    "LINKER_WIDTH",
                    "DYE_RADIUS",
                    "GRID",
                    "QUENCHERS",
                    "GROUPS",
                    "SLOW_RADIUS",
                    "RADIUS_OFFSETS",
                    "CLASH",
                    "TAU_MIN",
                    "PRIOR_POINTS",
                    "RIDGE",
                    "NU",
                    "MODEL_ERROR_FLOOR",
                    "OUTLIER_LIMIT",
                    "MAX_VARIANCE",
                    "N_STARTS",
                    "FIXED",
                    "BRIGHTENS",
                    "NAMES",
                )
            },
            "bounds": {"lower": clean(ns["LOWER"]), "upper": clean(ns["UPPER"])},
        }
    }
    golden["measurements"] = measurement_counts

    # Chapter 1: titrations
    per_day = ns["per_day"]
    golden["per_day"] = records(per_day)
    golden["K_POSTERIOR"] = records(ns["K_POSTERIOR"])
    hw, quantile = ns["hyper_weight"], ns["quantile"]
    abs_marg, rel_marg = hw.sum(1), hw.sum(0)
    golden["hyper"] = {
        "DAY_ABS": clean(ns["DAY_ABS"]),
        "DAY_REL": clean(ns["DAY_REL"]),
        "abs_marginal": clean(abs_marg),
        "rel_marginal": clean(rel_marg),
        "abs_quantiles": {
            q: quantile(ns["DAY_ABS"], abs_marg, float(q)) for q in ("0.16", "0.5", "0.84")
        },
        "rel_quantiles": {
            q: quantile(ns["DAY_REL"], rel_marg, float(q)) for q in ("0.16", "0.5", "0.84")
        },
        "edge_mass": float(hw[[0, -1], :].sum() + hw[:, [0, -1]].sum()),
        "argmax": [int(i) for i in np.unravel_index(np.argmax(hw), hw.shape)],
    }
    # Chapter 2: water, scatter, per-site lifetimes
    golden["water"] = records(ns["water"])
    w = ns["water"].groupby("dye").kq_w
    golden["water_summary"] = {
        d: {"median": float(g.median()), "min": float(g.min()), "max": float(g.max())} for d, g in w
    }
    scatter = ns["scatter"]
    golden["scatter"] = {d: clean(dict(scatter.loc[d])) for d in scatter.index}
    data = ns["data"]
    golden["data"] = records(
        data,
        [
            "dye",
            "solvent",
            "state",
            "site",
            "n",
            "tauX",
            "sigma_meas",
            "point_error_pct",
            "water_slope",
            "water_slope_err",
        ],
    )
    golden["coverage"] = {d: float(v) for d, v in ns["covered"].items()}
    golden["median_sigma_meas"] = {
        f"{d} {s}": float(v)
        for (d, s), v in data.groupby(["dye", "solvent"]).sigma_meas.median().items()
    }
    golden["TAU0"] = {f"{d} {s}": float(v) for (d, s), v in ns["TAU0"].items()}
    golden["KQW_FREE"] = float(ns["KQW_FREE"])
    # Chapter 3
    golden["KQ_TEXTBOOK"] = clean(ns["KQ_TEXTBOOK"])
    kq, kq_sd = ns["KQ_TABLE"], ns["KQ_TABLE_SD"]
    golden["KQ_TABLE"] = {d: {r: float(kq.loc[d, r]) for r in ns["QUENCHERS"]} for d in ns["DYES"]}
    golden["KQ_TABLE_SD"] = {
        d: {r: float(kq_sd.loc[d, r]) for r in ns["QUENCHERS"]} for d in ns["DYES"]
    }
    golden["stretched_linker_AF488"] = float(ns["L"])
    # Chapter 4: direct vs walk
    if run_walk:
        golden["direct_vs_walk"] = {
            "state": "APO",
            "site": 233,
            "slow_factor": 0.3,
            "linker_length": 21.5,
            "tau0": 4.108,
            "direct": float(ns["direct"]),
            "walks": clean(ns["walks"]),
            "walk_mean": float(np.mean(ns["walks"])),
            "walk_std": float(np.std(ns["walks"])),
            "note": "the walk depends on the platform's random numbers (+-0.3 ns); the direct value does not. "
            "Stored notebook (cordeshub): walk 2.31 +- 0.03, direct 2.59",
        }
    # Chapter 5: site tables
    tables = {}
    for (L, state, site), path in ns["TABLES"].items():
        tables[f"{state} {site} {L}"] = {"file": Path(path).name, "sha256": sha256(path)}
    golden["site_tables"] = tables
    exposure_mean = {}
    for site in (72, 186):
        e = np.load(ns["TABLES"][(ns["LINKER_LENGTH"]["Atto655"], "APO", site)])["exposure"]
        exposure_mean[str(site)] = float(e.mean())
    golden["atto655_apo_reachable_exposure_mean"] = exposure_mean
    fixture = ns["TABLES"][(20.12, "APO", 72)]
    golden["site_fixture"] = {
        "file": SITE_FIXTURE.name,
        "cache_file": Path(fixture).name,
        "sha256": sha256(fixture),
        "key": [
            "nb-v1",
            "APO",
            72,
            20.12,
            ns["GRID"],
            ns["SLOW_RADIUS"],
            ns["RADIUS_OFFSETS"],
            ns["CLASH"],
            ns["QUENCHERS"],
            ns["RESIDUES"],
        ],
    }

    # Chapter 6: the Site model at the printed stage parameters
    TAU0, KQW_FREE = ns["TAU0"], ns["KQW_FREE"]
    sites_for = ns["sites_for"]
    stage_points = {
        "AF488 in H2O": sites_for("AF488", ns["rows_af488"]),
        "Cy3B in H2O": sites_for("Cy3B", ns["rows_cy3b"]),
        "Atto655 in D2O": sites_for("Atto655", ns["rows_d2o"]),
        "Atto655 in D2O and H2O": ns["points_joint"],
    }
    site_lifetimes, thetas = {}, {}
    for stage, (dye, rows_name, tau0_key) in STAGES.items():
        th = stage_theta(ns, stage, printed["estimates"][stage])
        thetas[stage] = th
        rows = ns[rows_name]
        tau0 = float(np.exp(th["ln_tau0"]))
        out = []
        for (site_model, water), (_, r) in zip(stage_points[stage], rows.iterrows()):
            tau, dark, seen_e = site_model.lifetime(th, tau0, water)
            out.append(
                clean(
                    dict(
                        dye=dye,
                        solvent=r.get("solvent", "H2O"),
                        state=r.state,
                        site=int(r.site),
                        linker_length=ns["LINKER_LENGTH"][dye],
                        water=water,
                        tau0=tau0,
                        tauX=float(r.tauX),
                        sigma_meas=float(r.sigma_meas),
                        lifetime=tau,
                        dark_fraction=dark,
                        visible_exposure=seen_e,
                    )
                )
            )
        d = np.array([o["lifetime"] - o["tauX"] for o in out])
        site_lifetimes[stage] = {
            "theta": clean(th),
            "rows": out,
            "rms": float(np.sqrt((d**2).mean())),
            "median_abs_dev": float(np.median(np.abs(d))),
            "mean_dark_fraction": float(np.mean([o["dark_fraction"] for o in out])),
        }
    golden["site_lifetimes"] = {
        "note": "Site.lifetime(theta, tau0, water) -> (lifetime, dark_fraction, visible_exposure) at the printed "
        "(rounded) stage estimates; kq from K_MEAN (titration posterior means), not from the graph's K. "
        "theta is the full input; rms/median are at these rounded parameters, not the notebook's best fit.",
        **site_lifetimes,
    }

    # Naive H2O transfer test (cell 48) at the Stage B parameters, without propagated errors
    th_b = thetas["Atto655 in D2O"]
    rows_h2o = ns["rows_h2o"]
    h2o_points = sites_for("Atto655", rows_h2o)
    naive = [site.lifetime(th_b, TAU0[("Atto655", "H2O")])[0] for site, _ in h2o_points]
    golden["naive_h2o_test"] = {
        "predictions": clean(naive),
        "median_abs_dev": float(np.median(np.abs(np.array(naive) - rows_h2o.tauX.to_numpy()))),
        "sites_above_free_tau0": int((rows_h2o.tauX > TAU0[("Atto655", "H2O")]).sum()),
        "n": int(len(rows_h2o)),
    }

    # Water access (cell 51): measured is data only; model at the printed Stage C parameters
    rows_d2o, points_joint = ns["rows_d2o"], ns["points_joint"]
    pairs = []
    for j_h, (_, r_h) in enumerate(rows_h2o.iterrows()):
        j_d = rows_d2o[(rows_d2o.site == r_h.site) & (rows_d2o.state == r_h.state)].index
        if len(j_d):
            pairs.append((j_h, int(j_d[0])))
    th_c = thetas["Atto655 in D2O and H2O"]
    p = ns["predict"](points_joint, th_c, float(np.exp(th_c["ln_tau0"])))
    access = []
    for j_h, j_d in pairs:
        r_h = rows_h2o.iloc[j_h]
        access.append(
            dict(
                site=int(r_h.site),
                state=r_h.state,
                measured=float((1 / r_h.tauX - 1 / rows_d2o.tauX[j_d]) / KQW_FREE),
                measured_err=float(r_h.water_slope_err / KQW_FREE),
                model=float((1 / p[len(rows_d2o) + j_h] - 1 / p[j_d]) / KQW_FREE),
            )
        )
    meas = np.array([a["measured"] for a in access])
    mod = np.array([a["model"] for a in access])
    keep = np.array([a["site"] != 322 for a in access])
    golden["water_access"] = {
        "rows": access,
        "r_all_at_printed_stage_c": float(np.corrcoef(meas, mod)[0, 1]),
        "r_without_322_at_printed_stage_c": float(np.corrcoef(meas[keep], mod[keep])[0, 1]),
        "note": "measured is data only (exact); model and r are at the printed Stage C parameters, so they "
        "approximate cell 51's title, which the stored run does not record",
    }
    # Time-weighted visible exposure (cell 53) at the printed Stage C parameters
    tw = {}
    rows_joint = ns["rows_joint"]
    for site in (72, 186):
        here = [
            pt[0]
            for pt, (_, r) in zip(points_joint, rows_joint.iterrows())
            if r.site == site and r.state == "APO" and r.solvent == "D2O"
        ][0]
        time_w = here.weights(th_c)
        _, seen = here.seen(th_c, TAU0[("Atto655", "D2O")])
        weight = time_w * seen / (time_w * seen).sum()
        tw[str(site)] = {
            "visible_time_weighted_e": float((weight * here.exposure).sum()),
            "reachable_count_weighted_e": float(np.average(here.exposure, weights=here.count)),
            "dark_fraction": float(1 - (time_w * seen).sum()),
            "unique_rows": int(len(here.count)),
            "positions": int(here.count.sum()),
        }
    golden["time_weighted_exposure_stage_c"] = tw
    golden["printed"] = printed
    return golden


def main(argv=None):
    """Command line entry.

    Parameters
    ----------
    argv : list of str, optional
        Arguments; ``sys.argv[1:]`` by default.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--quest", type=Path, default=Path.home() / "dev" / "quest")
    parser.add_argument(
        "--convert", action="store_true", help="rewrite examples/male/*.csv from the workbooks"
    )
    parser.add_argument(
        "--no-walk", action="store_true", help="skip cell 23's random-walk validation"
    )
    parser.add_argument("--output", type=Path, default=GOLDEN)
    args = parser.parse_args(argv)
    if args.convert:
        convert(args.quest / "data")
    cells = notebook_cells(args.quest / "prototype" / "male_quenching_analysis.ipynb")
    ns = run_notebook(args.quest, cells, run_walk=not args.no_walk)
    try:
        counts = check_csv_reader(ns)
        golden = build_golden(ns, cells, args.quest, counts, run_walk=not args.no_walk)
    finally:
        shutil.rmtree(ns["OUTPUT"], ignore_errors=True)
    args.output.write_text(json.dumps(golden, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
