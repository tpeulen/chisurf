"""Persistence for instrument setups: MMFDB rows, with a JSON fallback.

TTTR detector setups and FCS channel setups are the same document under two
``setup_type`` keys, stored either as ``mmfdb_setup`` rows or as JSON on disk;
this module is the store both go through, so neither duplicates the logic.

**It used to live under** ``chisurf/gui/widgets/wizard/tttr_channeldefinition/``
**as** ``tttr_setup_utils``, and moving it here is the point rather than
tidiness. It contains no Qt and never did -- 300 lines of persistence sitting
in the presentation layer, which
:mod:`chisurf.core.fluorescence.fcs.channel_setups` then had to reach *up*
into, inverting the dependency the whole architecture rests on. A model that
imports a widget package cannot be used headlessly, cannot be tested without
one, and cannot be reasoned about as a model. The wizard that edits these
setups is a view over this store; the store is not part of the wizard.

See ``test/architecture/test_model_ui_boundary.py``, which now fails on a
core module that imports a GUI toolkit or ``chisurf.gui`` -- this file is why
that test could be widened from two packages to the whole of ``chisurf.core``.
"""

import json
import pathlib
import re
from collections.abc import Callable
from dataclasses import dataclass

from mmfdb.repository import MFDatabase
from mmfdb.store.database_resolver import resolve_database_path

from chisurf.core.settings.file_utils import safe_open_file


@dataclass
class SetupTypeConfig:
    """Configuration that distinguishes one setup type from another."""

    setup_type: str
    id_prefix: str
    prefs_id: str
    canonical_file: pathlib.Path
    description: str


def setup_id_for_name(name: str, user_id: str, prefix: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    if user_id:
        uslug = re.sub(r"[^a-z0-9]+", "_", str(user_id).strip().lower()).strip("_")
        return f"{prefix}:{uslug}:{slug or 'unnamed'}"
    return f"{prefix}:{slug or 'unnamed'}"


def resolve_active_user_id() -> str:
    try:
        import chisurf.core.settings

        uid = chisurf.core.settings.cs_settings.get("mmfdb", {}).get("default_user_id")
        if uid:
            return uid
    except Exception:
        pass
    return "user_default"


def use_mmfdb(file_path: str | None, canonical: pathlib.Path) -> bool:
    if file_path is None:
        return True
    try:
        return pathlib.Path(file_path).expanduser().resolve() == canonical.expanduser().resolve()
    except Exception:
        return False


def get_db(db_path: str | None = None) -> MFDatabase | None:
    """Open the MMFDB. ``db_path`` overrides the resolved default (test seam)."""
    try:
        db = MFDatabase(db_path or resolve_database_path())
        db._chisurf_setup_owned = True
        return db
    except Exception:
        return None


def close_owned_db(db: MFDatabase) -> None:
    """Close only database handles opened by :func:`get_db`.

    Injected handles are borrowed.  This keeps test seams and long-lived GUI
    repositories usable while ensuring production calls release their handles.
    """
    if getattr(db, "_chisurf_setup_owned", False):
        db.close()


def json_loads(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def save_setup_row(
    db: MFDatabase,
    config: SetupTypeConfig,
    setup_name: str,
    data: dict,
    user_id: str | None = None,
    is_public: bool | int | None = None,
    **extra_kwargs,
) -> None:
    if user_id is None:
        user_id = resolve_active_user_id()
    if is_public is None:
        is_public = False
    db.save_setup(
        setup_id=setup_id_for_name(setup_name, user_id, config.id_prefix),
        name=setup_name,
        description=config.description,
        configuration={"setup_type": config.setup_type, "setup_data": data},
        created_by_user_id=user_id or None,
        is_public=is_public,
        **extra_kwargs,
    )


def load_mmfdb_setups(
    db: MFDatabase,
    config: SetupTypeConfig,
    user_id: str | None = None,
    row_to_data: Callable[[dict, MFDatabase], dict] | None = None,
) -> dict:
    """Load setups from MMFDB, scoped by user and visibility.

    Parameters
    ----------
    db : MFDatabase
        Active database connection.
    config : SetupTypeConfig
        Type configuration.
    user_id : str or None
        Active user.  Resolved from settings when ``None``.
    row_to_data : callable or None
        Optional callback ``(row_dict, db) -> data_dict`` to extract the
        setup payload from a raw row (which already includes child-table
        keys like ``detector_channels``, ``fcs_pairs``, etc.).
        When ``None``, the raw ``configuration.setup_data`` is returned.
    """
    if user_id is None:
        user_id = resolve_active_user_id()
    setups = {}
    for row in db.list_setups():
        cfg = json_loads(row.get("configuration_json"))
        if cfg.get("setup_type") != config.setup_type:
            continue
        owner = row.get("created_by_user_id")
        is_pub = row.get("is_public", 0)
        if owner is None:
            pass
        elif not (is_pub or owner == user_id):
            continue
        if row_to_data:
            setups[row["name"]] = row_to_data(row, db)
        else:
            sd = cfg.get("setup_data", {})
            if isinstance(sd, dict):
                setups[row["name"]] = dict(sd)
            else:
                setups[row["name"]] = dict(cfg)
    prefs = db.get_setup(config.prefs_id) or {}
    lu = json_loads(prefs.get("configuration_json")).get("last_used", "")
    if lu not in setups:
        lu = ""
    return {"setups": setups, "last_used": lu}


def set_last_used(db: MFDatabase, config: SetupTypeConfig, setup_name: str) -> None:
    db.save_setup(
        setup_id=config.prefs_id,
        name=config.prefs_id,
        description="Setup UI preferences",
        configuration={"setup_type": f"{config.setup_type}_preferences", "last_used": setup_name},
    )


def migrate_json_to_mmfdb(
    db: MFDatabase,
    config: SetupTypeConfig,
    path: pathlib.Path,
    user_id: str | None = None,
    save_row_fn: Callable | None = None,
) -> bool:
    """Per-user idempotent migration from a legacy JSON file.

    Returns ``True`` when at least one setup was imported, ``False`` when
    nothing was imported (file missing, user already migrated, empty data).
    """
    if user_id is None:
        user_id = resolve_active_user_id()
    if not path.exists():
        return False
    owned = [s for s in db.list_setups() if s.get("created_by_user_id") == user_id]
    if owned:
        return False
    legacy = safe_open_file(file_path=path, processor=json.load, default_value={"setups": {}})
    setup_count = 0
    for name, data in (legacy.get("setups") or {}).items():
        if isinstance(data, dict):
            if save_row_fn:
                save_row_fn(db, name, data, user_id=user_id)
            else:
                save_setup_row(db, config, name, data, user_id=user_id)
            setup_count += 1
    if legacy.get("last_used"):
        set_last_used(db, config, str(legacy["last_used"]))
    return setup_count > 0


def save_setups(
    setups_data: dict,
    config: SetupTypeConfig,
    file_path: str | None = None,
    replace: bool = False,
    is_public: bool | int | None = None,
    save_row_fn: Callable | None = None,
    load_scoped_fn: Callable | None = None,
    get_db_fn: Callable | None = None,
    resolve_user_fn: Callable | None = None,
) -> bool:
    """Save setups to MMFDB or JSON fallback.

    This is the generic version of ``save_detector_setups``.
    ``save_row_fn`` and ``load_scoped_fn`` default to the generic
    ``save_setup_row`` / ``load_mmfdb_setups`` when not provided.
    ``get_db_fn`` / ``resolve_user_fn`` let callers inject the DB and
    active-user resolution seams (used by tests and per-setup-type modules);
    they default to the shared ``get_db`` / ``resolve_active_user_id``.
    """
    if use_mmfdb(file_path, config.canonical_file):
        db = (get_db_fn or get_db)()
        if db is None:
            print(f"Error: MMFDB unavailable for {config.description}; nothing was saved.")
            return False
        try:
            user_id = (resolve_user_fn or resolve_active_user_id)()
            payloads = (setups_data or {}).get("setups") or {}
            if replace:
                desired = set(payloads)
                loader = load_scoped_fn or load_mmfdb_setups
                for en in loader(db, config, user_id).get("setups", {}):
                    if en not in desired:
                        db.delete_setup(setup_id_for_name(en, user_id, config.id_prefix))
            for name, data in payloads.items():
                if isinstance(data, dict):
                    row_data = dict(data)
                    sp = row_data.pop("_is_public", is_public)
                    if save_row_fn:
                        save_row_fn(db, name, row_data, user_id=user_id, is_public=sp)
                    else:
                        save_setup_row(db, config, name, row_data, user_id=user_id, is_public=sp)
            if isinstance(setups_data, dict) and "last_used" in setups_data:
                set_last_used(db, config, str(setups_data.get("last_used") or ""))
            return True
        except Exception as e:
            print(f"Error saving {config.setup_type} setups to MMFDB: {e}")
            return False
        finally:
            close_owned_db(db)

    save_path = pathlib.Path(file_path)
    try:
        if replace:
            updated = setups_data
        elif save_path.exists() and save_path.stat().st_size > 0:
            with open(save_path) as f:
                existing = json.load(f) or {}
            updated = dict(existing)
            if isinstance(setups_data, dict):
                for k, v in setups_data.items():
                    if k == "setups":
                        updated.setdefault("setups", {})
                        if isinstance(v, dict):
                            updated["setups"].update(v)
                    else:
                        updated[k] = v
        else:
            updated = setups_data
    except Exception:
        updated = setups_data
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w") as f:
        json.dump(updated, f, indent=4)
    return True


def load_json_setups(path: pathlib.Path, file_path=None) -> dict:
    return safe_open_file(file_path=path, processor=json.load, default_value={"setups": {}})


def load_setups(
    file_path: str | None,
    config: SetupTypeConfig,
    file_path_override: pathlib.Path | None = None,
    row_to_data: Callable[[dict, MFDatabase], dict] | None = None,
) -> dict:
    """Main load entry point — MMFDB first, JSON fallback.

    When using MMFDB, automatically migrates legacy JSON data on first access.
    """
    path = pathlib.Path(file_path or config.canonical_file)
    if use_mmfdb(file_path, config.canonical_file):
        db = get_db()
        if db is not None:
            try:
                user_id = resolve_active_user_id()
                migrate_json_to_mmfdb(db, config, path, user_id=user_id)
                return load_mmfdb_setups(db, config, user_id, row_to_data=row_to_data)
            finally:
                close_owned_db(db)
    return load_json_setups(path, file_path=file_path)
