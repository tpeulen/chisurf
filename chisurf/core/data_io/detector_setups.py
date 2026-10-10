from __future__ import annotations

import json
import logging
import pathlib
from typing import TYPE_CHECKING, Any

from chisurf.core.fio.setup_store import (
    SetupTypeConfig,
    close_owned_db,
    json_loads,
    load_json_setups,
    load_mmfdb_setups,
    resolve_active_user_id,
    save_setups,
)
from chisurf.core.fio.setup_store import save_setup_row as _save_row
from chisurf.core.settings.path_utils import get_path

if TYPE_CHECKING:
    from mmfdb.repository import MFDatabase

logger = logging.getLogger(__name__)

DETECTOR_SETUPS_FILE = get_path("settings") / "detector_setups.json"
DETECTOR_SETUP_TYPE = "tttr_detector_setup"
DETECTOR_SETUP_PREFS_ID = "tttr_detector_setup_preferences"

DETECTOR_CONFIG = SetupTypeConfig(
    setup_type=DETECTOR_SETUP_TYPE,
    id_prefix="tttr_detector_setup",
    prefs_id=DETECTOR_SETUP_PREFS_ID,
    canonical_file=DETECTOR_SETUPS_FILE,
    description="TTTR detector and PIE-window setup",
)


def setup_id_for_name(name: str, user_id: str = "") -> str:
    from chisurf.core.fio.setup_store import setup_id_for_name as _sifn

    return _sifn(name, user_id, "tttr_detector_setup")


def _db(db_path=None):
    from chisurf.core.fio.setup_store import get_db

    return get_db(db_path)


def _db_available(db_path=None) -> bool:
    """Whether MMFDB opens; the probe handle is closed again."""
    db = _db(db_path)
    if db is None:
        return False
    close_owned_db(db)
    return True


def _use_mmfdb(file_path=None) -> bool:
    from chisurf.core.fio.setup_store import use_mmfdb

    return use_mmfdb(file_path, DETECTOR_SETUPS_FILE)


def _setup_row_data(
    row: dict,
    detector_channels: list | None = None,
    pie_windows: list | None = None,
) -> dict:
    """Extract detector setup payload from an MMFDB row with child tables."""
    configuration = json_loads(row.get("configuration_json"))
    setup_data = configuration.get("setup_data")
    if isinstance(setup_data, dict):
        return setup_data
    data = dict(configuration)
    data.pop("setup_type", None)
    data.pop("setup_data", None)

    if detector_channels:
        dets = {}
        for ch in detector_channels:
            name = ch.get("name", "")
            if not name:
                continue
            entry: dict[str, Any] = {}
            chs = ch.get("channels")
            if chs:
                entry["chs"] = json_loads(chs) if isinstance(chs, str) else chs
            mtr = ch.get("micro_time_ranges")
            if mtr:
                entry["micro_time_ranges"] = json_loads(mtr) if isinstance(mtr, str) else mtr
            if ch.get("g_factor") is not None:
                entry["g_factor"] = ch["g_factor"]
            if ch.get("l1") is not None:
                entry["l1"] = ch["l1"]
            if ch.get("l2") is not None:
                entry["l2"] = ch["l2"]
            gfc = ch.get("g_factor_channels")
            if gfc:
                entry["g_factor_channels"] = json_loads(gfc) if isinstance(gfc, str) else gfc
            if ch.get("g_factor_decay_uuid") is not None:
                entry["g_factor_decay_uuid"] = ch["g_factor_decay_uuid"]
            if ch.get("g_factor_calibration_id") is not None:
                entry["g_factor_calibration_id"] = ch["g_factor_calibration_id"]
            dets[name] = entry
        if dets:
            data["detectors"] = dets
    elif row.get("detectors_json"):
        data["detectors"] = json_loads(row.get("detectors_json"))

    if pie_windows:
        wins = {}
        for pw in pie_windows:
            name = pw.get("name", "")
            if not name:
                continue
            start = pw.get("start")
            end = pw.get("end")
            if start is not None and end is not None:
                wins[name] = (int(start), int(end))
        if wins:
            data["windows"] = wins

    timing = {}
    mtr = row.get("macro_time_resolution")
    mir = row.get("micro_time_resolution")
    mib = row.get("micro_time_binning")
    if mtr is not None:
        timing["macro_time_resolution"] = mtr
    if mir is not None:
        timing["micro_time_resolution"] = mir
    if mib is not None:
        timing["micro_time_binning"] = mib
    if not timing:
        timing = json_loads(row.get("timing_resolution_json"))
    if timing:
        data["tttr_reading"] = timing
    burst_defaults = json_loads(row.get("burst_defaults_json"))
    if burst_defaults:
        data["burst_selection"] = burst_defaults
    owner = row.get("created_by_user_id")
    if owner is not None:
        data["_owner"] = owner
    if row.get("is_public") is not None:
        data["_is_public"] = bool(row["is_public"])
    return data


def _detector_row_to_data(row: dict, db: MFDatabase) -> dict:
    """Callback for ``load_mmfdb_setups`` to extract detector data with child
    table priority.
    """
    full = None
    dcs, pws = None, None
    if row.get("setup_id"):
        full = db.get_setup(row["setup_id"])
        if full:
            dcs = full.get("detector_channels")
            pws = full.get("pie_windows")
    return _setup_row_data(row, detector_channels=dcs, pie_windows=pws)


def _save_setup_row(
    db: MFDatabase,
    setup_name: str,
    data: dict,
    user_id: str | None = None,
    is_public: bool | int | None = None,
) -> None:
    _save_row(
        db,
        DETECTOR_CONFIG,
        setup_name,
        data,
        user_id=user_id,
        is_public=is_public,
        detectors=data.get("detectors") or {},
        windows=data.get("windows") or {},
        timing_resolution=data.get("tttr_reading") or {},
        burst_defaults=data.get("burst_selection") or {},
    )


def _detector_save_row_fn(
    db: MFDatabase,
    setup_name: str,
    data: dict,
    user_id: str | None = None,
    is_public: bool | int | None = None,
) -> None:
    _save_setup_row(db, setup_name, data, user_id=user_id, is_public=is_public)


def _load_mmfdb_detector_setups(db: MFDatabase, user_id: str | None = None) -> dict:
    from chisurf.core.fio.setup_store import load_mmfdb_setups

    return load_mmfdb_setups(db, DETECTOR_CONFIG, user_id, row_to_data=_detector_row_to_data)


def _migrate_json_setups_to_mmfdb(
    db: MFDatabase,
    path: pathlib.Path,
    user_id: str | None = None,
) -> bool:
    from chisurf.core.fio.setup_store import migrate_json_to_mmfdb

    return migrate_json_to_mmfdb(
        db, DETECTOR_CONFIG, path, user_id=user_id, save_row_fn=_detector_save_row_fn
    )


def load_detector_setups(
    file_path: str | pathlib.Path | None = None,
    db_path: str | None = None,
    skip_migration: bool = False,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Load detector setups from the one authoritative store.

    The canonical location (``file_path`` omitted or equal to
    :data:`DETECTOR_SETUPS_FILE`) is MMFDB when it is available, with a legacy
    ``detector_setups.json`` imported on first access unless
    ``skip_migration``; an explicit other ``file_path``, or no MMFDB, reads
    that JSON file. The RPC service, every setup picker and the wizard all read
    here, so a setup saved by one is visible to the others.

    Returns ``{"setups": {...}, "last_used": str}``; never raises for a missing
    or unreadable file (an empty ``setups`` mapping instead).
    """
    path = pathlib.Path(file_path or DETECTOR_SETUPS_FILE)
    if _use_mmfdb(file_path):
        db = _db(db_path)
        if db is not None:
            try:
                uid = user_id if user_id is not None else resolve_active_user_id()
                if not skip_migration and _migrate_json_setups_to_mmfdb(db, path, user_id=uid):
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Imported %s into MMFDB but could not remove it", path)
                return _load_mmfdb_detector_setups(db, user_id=uid)
            finally:
                close_owned_db(db)
    if not path.exists():
        logger.debug("Detector setups file not found: %s", path)
        return {"setups": {}}
    data = load_json_setups(path, file_path=file_path) or {}
    return {"setups": data.get("setups") or {}, "last_used": data.get("last_used") or ""}


def save_detector_setups(
    setups_data: dict[str, Any],
    file_path: str | pathlib.Path | None = None,
    replace: bool = False,
    is_public: bool | None = None,
    db_path: str | None = None,
    user_id: str | None = None,
) -> bool:
    """Save setups to the store :func:`load_detector_setups` reads.

    Parameters
    ----------
    setups_data : dict
        ``{"setups": {name: settings}, "last_used": name}``.
    file_path : str or Path, optional
        An explicit JSON file; omitted (or the canonical path) selects MMFDB
        when it is available and the canonical JSON file otherwise.
    replace : bool, optional
        Drop stored setups not named in ``setups_data``.
    is_public : bool, optional
        MMFDB visibility of the saved rows.
    db_path, user_id : str, optional
        Test seams for the database and the owning user.

    Returns
    -------
    bool
        Whether the setups were written; a rejected MMFDB write returns False.
    """
    if _use_mmfdb(file_path) and not _db_available(db_path):
        target = DETECTOR_SETUPS_FILE
        existing = {} if replace else load_detector_setups(target)
        setups = dict(existing.get("setups") or {})
        setups.update(setups_data.get("setups") or {})
        payload = {"setups": setups}
        last_used = setups_data.get("last_used") or existing.get("last_used")
        if last_used:
            payload["last_used"] = last_used
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=4))
        return True
    return save_setups(
        setups_data,
        DETECTOR_CONFIG,
        file_path=None if file_path is None else str(file_path),
        replace=replace,
        is_public=is_public,
        save_row_fn=_detector_save_row_fn,
        load_scoped_fn=lambda db, cfg, uid: load_mmfdb_setups(
            db, cfg, uid, row_to_data=_detector_row_to_data
        ),
        get_db_fn=lambda: _db(db_path),
        resolve_user_fn=(lambda: user_id) if user_id is not None else resolve_active_user_id,
    )


def setup_lut_open_kwargs(setup: dict[str, Any] | None) -> dict[str, Any]:
    """Return the ``open_tttr`` LUT/shift keyword arguments for a setup dict.

    The single adapter every setup-consuming reader uses to become LUT-aware:
    a plugin that has resolved its selected setup calls
    ``open_tttr(path, routine, **setup_lut_open_kwargs(setup))`` (or forwards the
    result to a reader). Returns ``{"channel_luts": {}, "channel_shifts": {},
    "apply_lut": False}`` for a missing/empty setup, so the open falls back to
    raw reading.

    Parameters
    ----------
    setup : dict or None
        A detector-setup dict (as stored under ``setups[name]``) carrying the
        inline ``channel_luts`` / ``channel_shifts`` / ``apply_lut`` keys.

    Returns
    -------
    dict
        ``{"channel_luts": {int: list}, "channel_shifts": {int: int},
        "apply_lut": bool}``.
    """
    if not isinstance(setup, dict):
        return {"channel_luts": {}, "channel_shifts": {}, "apply_lut": False}
    luts_raw = setup.get("channel_luts") or {}
    shifts_raw = setup.get("channel_shifts") or {}
    channel_luts: dict[int, Any] = {}
    for k, v in luts_raw.items():
        try:
            channel_luts[int(k)] = v
        except (TypeError, ValueError):
            continue
    channel_shifts: dict[int, int] = {}
    for k, v in shifts_raw.items():
        try:
            channel_shifts[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return {
        "channel_luts": channel_luts,
        "channel_shifts": channel_shifts,
        "apply_lut": bool(setup.get("apply_lut", False)),
    }


def get_setup_calibration(
    setup_name: str,
    file_path: str | pathlib.Path | None = None,
) -> dict[str, Any]:
    """Return the FRET calibration stored on a named detector setup.

    The read half of "calibrate once per instrument". A tool that already lets
    the user pick a detector setup gets the measured correction factors for
    free, instead of asking for them again or falling back to defaults.

    Parameters
    ----------
    setup_name : str
        Name of the setup, as shown in the setup picker.
    file_path : str or Path, optional
        Override the default setups file.

    Returns
    -------
    dict
        ``{"values": {...}, "uncertainties": {...}}``, or an empty dict when the
        setup is unknown or carries no calibration.
    """
    from chisurf.core.fluorescence.fret.calibration import SETUP_CALIBRATION_FIELD

    setups = (load_detector_setups(file_path) or {}).get("setups") or {}
    setup = setups.get(str(setup_name))
    if not isinstance(setup, dict):
        return {}
    payload = setup.get(SETUP_CALIBRATION_FIELD)
    return dict(payload) if isinstance(payload, dict) else {}


def set_setup_calibration(
    setup_name: str,
    payload: dict[str, Any],
    file_path: str | pathlib.Path | None = None,
) -> bool:
    """Store a FRET calibration on a named detector setup.

    Only the calibration field is touched: the setup's detectors, windows and
    LUTs are read back and written out unchanged, so this can never be the thing
    that loses a channel definition.

    Parameters
    ----------
    setup_name : str
        Name of the setup to annotate. It must already exist — this attaches a
        calibration to a setup, it does not create one.
    payload : dict
        As produced by
        :func:`chisurf.core.fluorescence.fret.calibration.calibration_to_setup`.
    file_path : str or Path, optional
        Override the default setups file.

    Returns
    -------
    bool
        Whether the setup existed and was updated.
    """
    from chisurf.core.fluorescence.fret.calibration import SETUP_CALIBRATION_FIELD

    data = load_detector_setups(file_path) or {}
    setups = data.get("setups") or {}
    setup = setups.get(str(setup_name))
    if not isinstance(setup, dict):
        logger.warning("Cannot store a calibration: no detector setup named %r", setup_name)
        return False
    setup[SETUP_CALIBRATION_FIELD] = dict(payload or {})
    save_detector_setups({"setups": setups, "last_used": data.get("last_used") or ""}, file_path)
    return True
