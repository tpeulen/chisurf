import html
import os
import pathlib
import shutil
import subprocess
import sys

import chisurf as cs
import chisurf.core.settings


def open_in_file_manager(path: pathlib.Path) -> None:
    """Open *path* in the OS file manager (best-effort, never raises; no toolkit needed)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606 - the user asked to open this folder
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen(  # noqa: S603 - fixed program, the path is one argument
                [opener, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def import_check(module_name: str) -> tuple[bool, str]:
    """Return ``(importable, detail)`` for *module_name* without propagating errors."""
    try:
        __import__(module_name)
        return True, "ok"
    except Exception as e:
        return False, str(e)


def settings_paths() -> dict[str, pathlib.Path]:
    """Return the well-known ChiSurf user-settings paths keyed by short name."""
    user_dir = cs.core.settings.get_path("settings")
    return {
        "user_settings_dir": user_dir,
        "settings_chisurf_yaml": user_dir / "settings_chisurf.yaml",
        "settings_colors_yaml": user_dir / "settings_colors.yaml",
        "anisotropy_corrections_json": user_dir / "anisotropy_corrections.json",
        "detector_setups_json": user_dir / "detector_setups.json",
        "styles_dir": user_dir / "styles",
        "plugins_dir": user_dir / "plugins",
        "logs_dir": user_dir / "logs",
    }


def _html_code(text: str) -> str:
    return f"<code>{html.escape(str(text))}</code>"


def _close_db(db) -> None:
    """Best-effort close of an MMFDB handle opened for a read-only probe."""
    try:
        if db is not None and hasattr(db, "close"):
            db.close()
    except Exception:
        pass


def mmfdb_info() -> dict:
    """Return ``{'connected': bool, 'path': str}`` for the metadata database.

    The MMFDB is the authoritative store for detector/FCS setups (and more); when
    it is reachable, the legacy JSON files are expected to be absent, so their
    absence must not be reported as an error.
    """
    path = ""
    try:
        from mmfdb.store.database_resolver import resolve_database_path

        path = str(resolve_database_path())
    except Exception:
        path = ""
    db = None
    try:
        from chisurf.core.fio.setup_store import get_db

        db = get_db()
    except Exception:
        db = None
    connected = db is not None
    _close_db(db)
    return {"connected": connected, "path": path}


def detector_setups_summary() -> dict:
    """Return ``{'count', 'store', 'detail'}`` for detector setups (read-only).

    Prefers MMFDB (the authoritative store) and falls back to the legacy JSON
    file, counting quietly without triggering the file-missing warning dialog or
    any migration side effect.
    """
    try:
        from chisurf.core.fio.setup_store import get_db as _db
        from chisurf.core.fio.setup_store import load_mmfdb_setups
        from chisurf.core.setup_channel_definition import CONFIG, DETECTOR_SETUPS_FILE, _row_data
    except Exception:
        return {"count": None, "store": "unknown", "detail": ""}

    db = None
    try:
        db = _db()
    except Exception:
        db = None
    if db is not None:
        try:
            res = load_mmfdb_setups(db, CONFIG, row_to_data=_row_data)
            n = len((res or {}).get("setups", {}) or {})
            return {"count": n, "store": "mmfdb", "detail": "in MMFDB"}
        except Exception:
            pass
        finally:
            _close_db(db)

    p = DETECTOR_SETUPS_FILE
    if p.exists():
        try:
            import json

            with open(p, encoding="utf-8") as fh:
                n = len((json.load(fh) or {}).get("setups", {}) or {})
        except Exception:
            n = None
        return {"count": n, "store": "file", "detail": f"in {p}"}
    return {"count": 0, "store": "none", "detail": ""}


def fcs_setups_summary() -> dict:
    """Return ``{'count', 'store', 'detail'}`` for FCS channel setups (read-only)."""
    try:
        from chisurf.core.fluorescence.fcs.channel_setups import (
            FCS_CHANNEL_SETUPS_FILE,
            load_fcs_channel_setups,
        )
    except Exception:
        return {"count": None, "store": "unknown", "detail": ""}

    # The FCS loader is MMFDB-first with a quiet JSON fallback (no dialogs).
    try:
        data = load_fcs_channel_setups(skip_migration=True)
        n = len((data or {}).get("setups", {}) or {})
    except Exception:
        n = None

    if mmfdb_info()["connected"]:
        return {"count": n, "store": "mmfdb", "detail": "in MMFDB"}
    p = FCS_CHANNEL_SETUPS_FILE
    if p.exists():
        return {"count": n, "store": "file", "detail": f"in {p}"}
    return {"count": n or 0, "store": "none", "detail": ""}


#: Colours for the three-state status cells.
_OK_COLOR = "#2e7d32"
_MISSING_COLOR = "#c62828"
_NEUTRAL_COLOR = "#8a8a8a"


def _status_cells(label: str, status: str, color: str, detail: str = "") -> dict:
    """One status row as data: ``item``, ``status``, ``detail`` (native separators) and ``color``."""
    return {
        "item": str(label),
        "status": str(status),
        "detail": str(detail or "").replace("/", os.sep),
        "color": color,
    }


def _cells_html(cells: dict) -> str:
    """Render one status row (see :func:`_status_cells`) as an HTML table row."""
    detail_cell = _html_code(cells["detail"]) if cells["detail"] else ""
    return (
        "<tr>"
        f"<td style='padding:4px 10px 4px 0'>{html.escape(cells['item'])}</td>"
        f"<td style='padding:4px 10px 4px 0; color:{cells['color']}; font-weight:600'>"
        f"{html.escape(cells['status'])}</td>"
        f"<td style='padding:4px 0 4px 0'>{detail_cell}</td>"
        "</tr>"
    )


def _status_row(label: str, status: str, color: str, detail: str = "") -> str:
    """Render one table row with a coloured status word and an optional detail cell."""
    return _cells_html(_status_cells(label, status, color, detail))


def _file_cells(label: str, ok: bool, detail: str = "") -> dict:
    """An OK/MISSING row, as data, for a genuinely file-backed setting."""
    return _status_cells(
        label, "OK" if ok else "MISSING", _OK_COLOR if ok else _MISSING_COLOR, detail
    )


def _file_row(label: str, ok: bool, detail: str = "") -> str:
    """Render an OK/MISSING row for a genuinely file-backed setting."""
    return _cells_html(_file_cells(label, ok, detail))


def _setups_cells(label: str, summary: dict) -> dict:
    """An MMFDB-aware row, as data, for a setup type.

    A count > 0 is ``OK``; an empty store is a neutral "none yet" (not an error,
    since setups are created on demand); an unknown count is neutral too.
    """
    count = summary.get("count")
    store = summary.get("store", "unknown")
    where = summary.get("detail", "")
    if count is None:
        return _status_cells(label, "—", _NEUTRAL_COLOR, "could not be determined")
    if count > 0:
        noun = "setup" if count == 1 else "setups"
        return _status_cells(label, "OK", _OK_COLOR, f"{count} {noun} {where}".strip())
    # count == 0 → nothing defined yet; phrase by store so it never looks broken.
    if store == "mmfdb":
        return _status_cells(label, "none yet", _NEUTRAL_COLOR, "MMFDB connected — none defined yet")
    return _status_cells(label, "none yet", _NEUTRAL_COLOR, "define one when needed")


def _setups_row(label: str, summary: dict) -> str:
    """Render an MMFDB-aware row for a setup type."""
    return _cells_html(_setups_cells(label, summary))


def status_cells() -> list[dict]:
    """Return the settings-files and setup-store status as rows of data.

    Setup types that live in the MMFDB (detectors, FCS channels) are reported by
    their actual availability — not by the presence of a legacy JSON file — so a
    connected MMFDB with setups never shows a misleading "MISSING" file.
    """
    p = settings_paths()
    mmfdb = mmfdb_info()

    rows = [
        _file_cells(
            "User settings directory", p["user_settings_dir"].exists(), str(p["user_settings_dir"])
        ),
        _file_cells(
            "settings_chisurf.yaml",
            p["settings_chisurf_yaml"].is_file(),
            str(p["settings_chisurf_yaml"]),
        ),
        _file_cells(
            "settings_colors.yaml",
            p["settings_colors_yaml"].is_file(),
            str(p["settings_colors_yaml"]),
        ),
        _file_cells(
            "anisotropy_corrections.json",
            p["anisotropy_corrections_json"].is_file(),
            str(p["anisotropy_corrections_json"]),
        ),
        _file_cells("styles/", p["styles_dir"].is_dir(), str(p["styles_dir"])),
        _file_cells("plugins/", p["plugins_dir"].is_dir(), str(p["plugins_dir"])),
        _file_cells("logs/", p["logs_dir"].is_dir(), str(p["logs_dir"])),
    ]

    # Metadata store + the setup types it now backs (not plain files anymore).
    if mmfdb["connected"]:
        rows.append(_status_cells("Metadata store (MMFDB)", "connected", _OK_COLOR, mmfdb["path"]))
    else:
        rows.append(
            _status_cells("Metadata store (MMFDB)", "local files", _NEUTRAL_COLOR, "not connected")
        )
    rows.append(_setups_cells("Detector setups", detector_setups_summary()))
    rows.append(_setups_cells("FCS channel setups", fcs_setups_summary()))

    try:
        s = getattr(cs.core.settings, "cs_settings", None)
        ok = isinstance(s, dict) and bool(s)
    except Exception:
        ok = False

    rows.append(_file_cells("Runtime settings", ok, "loaded" if ok else "not loaded"))
    return rows


def build_status_html() -> str:
    """Return an HTML table describing the settings files and setup stores."""
    return (
        "<h3>Settings status</h3>"
        "<table style='border-collapse:collapse'>"
        + "".join(_cells_html(row) for row in status_cells())
        + "</table>"
    )


#: The optional dependencies the wizard reports: ``(module, what it is for)``.
OPTIONAL_DEPENDENCIES = (
    ("tttrlib", "TTTR reading and analysis"),
    ("pyqtgraph", "Plotting in the GUI"),
    ("markdown", "Rendering Markdown docs in Help"),
    ("pymol", "3D viewer (optional)"),
)


def deps_cells() -> list[dict]:
    """Return the optional-dependency status as rows of data (``module``, ``status``, ``purpose``)."""
    rows = []
    for mod, purpose in OPTIONAL_DEPENDENCIES:
        ok, detail = import_check(mod)
        rows.append(
            {
                "module": mod,
                "status": "OK" if ok else "MISSING",
                "purpose": purpose,
                "detail": "" if ok else str(detail or ""),
                "color": _OK_COLOR if ok else _MISSING_COLOR,
            }
        )
    return rows


def build_deps_html() -> str:
    """Return an HTML table describing which optional dependencies are importable."""
    rows = []
    for cell in deps_cells():
        extra = html.escape(cell["purpose"])
        if cell["detail"]:
            extra = f"{extra}<br/><span style='color:#666'>{html.escape(cell['detail'])}</span>"
        rows.append(
            "<tr>"
            f"<td style='padding:4px 10px 4px 0'><code>{html.escape(cell['module'])}</code></td>"
            f"<td style='padding:4px 10px 4px 0; color:{cell['color']}; font-weight:600'>"
            f"{cell['status']}</td>"
            f"<td style='padding:4px 0 4px 0'>{extra}</td>"
            "</tr>"
        )

    return (
        "<h3>Optional dependencies</h3>"
        "<table style='border-collapse:collapse'>" + "".join(rows) + "</table>"
        "<p style='color:#666'>Missing optional dependencies do not necessarily prevent ChiSurf from running, but some features may be disabled.</p>"
    )


def update_experiment_config() -> tuple[bool, str]:
    """Refresh the user ``experiment_configs.yaml`` from the packaged default.

    New or renamed fitting models (e.g. the AutoForm-ported PDA models) only
    appear once the user's copy of ``experiment_configs.yaml`` is re-synced with
    the version shipped in the package. This copies just that one file (leaving
    all other user settings untouched) and reports whether a restart is needed.

    Returns
    -------
    tuple of (bool, str)
        ``(ok, message)``.
    """
    try:
        user_dir = cs.core.settings.get_path("settings")
        pkg = pathlib.Path(cs.core.settings.__file__).resolve().parent / "experiment_configs.yaml"
        if not pkg.exists():
            return False, "Packaged experiment_configs.yaml not found."
        target = user_dir / "experiment_configs.yaml"
        if target.exists() and target.read_bytes() == pkg.read_bytes():
            return True, "Experiment configuration already up to date."
        shutil.copyfile(pkg, target)
        return True, (
            "Experiment configuration updated. Restart ChiSurf to load the new "
            "models (e.g. the AutoForm PDA models)."
        )
    except Exception as e:
        return False, str(e)


def copy_defaults(overwrite: bool) -> tuple[bool, str]:
    """Copy packaged default settings into the user folder; return ``(ok, message)``.

    When *overwrite* is ``False`` only missing files are written; when ``True`` the
    packaged defaults replace the user's current settings files.
    """
    try:
        user_dir = cs.core.settings.get_path("settings")
        pkg_dir = pathlib.Path(cs.core.settings.__file__).resolve().parent

        if overwrite:
            allowed = {".yaml", ".yml", ".json", ".qss", ".css"}
            for file in pkg_dir.iterdir():
                if not file.is_file():
                    continue
                if file.suffix.lower() not in allowed:
                    continue
                if file.name == "help_mappings.yaml":
                    continue
                shutil.copyfile(file, user_dir / file.name)
            try:
                from chisurf.core.settings.settings_utils import copy_styles_to_user_folder

                copy_styles_to_user_folder()
            except Exception:
                pass
            return True, "Defaults copied (overwrite)."

        cs.core.settings.copy_settings_to_user_folder()
        return True, "Defaults copied (missing files only)."
    except Exception as e:
        return False, str(e)
