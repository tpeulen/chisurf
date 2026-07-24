from __future__ import annotations

import os
import datetime
import json
import pathlib
import sys

# Initialize environment (PATH, Qt plugins, vispy, FreeType) as early as possible
from . import env_bootstrap  # noqa: F401

# Import utility functions
from .file_utils import safe_open_file
from .path_utils import get_path
from .settings_utils import (
    get_chisurf_settings,
    copy_settings_to_user_folder,
    copy_styles_to_user_folder
)
from .cleanup import clear_settings_folder, clear_logging_files, clear_user_plugins_folder
from .path_utils import get_path  # Needed early

# Define Chisurf cache path inside user settings folder
_chisurf_user_cache_dir = get_path('settings') / "cache"

# Set environment variables for Numba and Python bytecode cache
os.environ["NUMBA_CACHE_DIR"] = str(_chisurf_user_cache_dir)
os.environ["PYTHONPYCACHEPREFIX"] = str(_chisurf_user_cache_dir)

# Ensure the cache directory exists
_chisurf_user_cache_dir.mkdir(parents=True, exist_ok=True)

# Path constants
chisurf_settings_path = get_path('settings')
chisurf_root = get_path('chisurf')
macro_path = chisurf_root / "macros"
plugin_path = chisurf_root / "plugins"
_notebook_root = chisurf_root.parent / "notebooks"
notebook_path = _notebook_root if _notebook_root.is_dir() else (chisurf_root / "notebooks")

# Copy settings files if not already present
copy_settings_to_user_folder()

import chisurf.core.info
__version__ = chisurf.core.info.__version__

# Open chisurf settings file
chisurf_settings_file = chisurf_settings_path / 'settings_chisurf.yaml'
# To use the settings in the home folder set to false
# if set to true uses settings in source folder.
cs_settings = get_chisurf_settings(chisurf_settings_file, use_source_folder=False)

# MMFDB is vendored as a standalone package and must not import ChiSurf settings.
# Publish path-like runtime values through environment variables, and register a
# live resolver so runtime changes to the default user id propagate to MMFDB
# without MMFDB importing ChiSurf (the resolver reads cs_settings on each call).
os.environ.setdefault("MMFDB_SETTINGS_DIR", str(chisurf_settings_path))


def _mmfdb_default_user_id() -> str | None:
    mmfdb_cfg = cs_settings.get("mmfdb", {}) if isinstance(cs_settings, dict) else {}
    return mmfdb_cfg.get("default_user_id") if isinstance(mmfdb_cfg, dict) else None


try:
    from mmfdb.config import set_default_user_id_resolver as _set_mmfdb_user_resolver

    _set_mmfdb_user_resolver(_mmfdb_default_user_id)
except Exception:  # pragma: no cover - MMFDB always importable in supported envs
    pass
_mmfdb_settings = cs_settings.get("mmfdb", {}) if isinstance(cs_settings, dict) else {}
_object_store = _mmfdb_settings.get("object_store", {}) if isinstance(_mmfdb_settings, dict) else {}
_object_store_root = _object_store.get("root") if isinstance(_object_store, dict) else None
if _object_store_root:
    os.environ["MMFDB_OBJECT_STORE_ROOT"] = str(_object_store_root)

anisotropy = dict()
anisotropy_data = safe_open_file(
    file_path=get_path('chisurf') / "settings" / "anisotropy_corrections.json",
    processor=json.load,
    default_value={},
    error_message="Error opening anisotropy corrections file"
)
anisotropy.update(anisotropy_data)

verbose = False
gui = dict()
parameter = dict()
optimization = dict()
fret = dict()
tcspc = dict()
fps = dict()
locals().update(cs_settings)

# BETA OVERRIDES: Force Jupyter to start even if disabled in user settings
# to ensure connectivity for the Antigravity (v26.1) Beta release.
_gui_overrides = cs_settings.setdefault('gui', {})
_gui_overrides['start_jupyter_on_startup'] = True
# ZMQ server is always auto-started — no setting required.
gui.update(_gui_overrides)


def is_dev_mode() -> bool:
    """Return True if dev mode is enabled (experimental mode).

    Dev mode enables developer features like code badge buttons
    for jumping to source locations in the embedded editor.
    """
    return bool(cs_settings.get('enable_experimental', False))


def dev_mode_settings() -> dict:
    """Return dev_mode settings dict from gui.dev_mode."""
    gui_settings = cs_settings.get('gui', {})
    return gui_settings.get('dev_mode', {})

# Load help mappings from the program's settings folder only. These are not
# intended to be user-editable, so we always read them from the source folder
# and do not look at (or copy into) the user settings directory.
help_settings_file = chisurf_settings_path / 'help_mappings.yaml'
_help_settings = get_chisurf_settings(help_settings_file, use_source_folder=True)
if isinstance(_help_settings, dict):
    help = _help_settings.get('help', _help_settings)
else:
    help = {}

# Open color settings file
color_settings_file = chisurf_settings_path / 'settings_colors.yaml'
colors = get_chisurf_settings(color_settings_file)

package_directory = pathlib.Path(__file__).parent
chisurf_root = package_directory.parent.parent
style_sheet_file = chisurf_root / 'gui' / 'styles' / gui['style_sheet']
style_sheet = safe_open_file(
    file_path=style_sheet_file,
    default_value="",
    error_message=f"Error opening style sheet file {style_sheet_file}"
)
structure_data = safe_open_file(
    file_path=package_directory / 'constants' / 'structure.json',
    processor=json.load,
    default_value={},
    error_message="Error opening structure.json file"
)

# Optional registry of parameter metadata used to enrich parameter
# descriptions in the GUI. This is populated by the command
# ``python -m build_tools.dev_utils.export_fitting_parameters`` and can be
# edited by the user.
parameter_registry = safe_open_file(
    file_path=package_directory / 'constants' / 'parameter_registry.json',
    processor=json.load,
    default_value={},
    error_message="Error opening parameter_registry.json file"
)


def describe_parameter(name, owner=None, registry_id=None):
    """Look up a parameter's human-readable description in the registry.

    Resolves ``name`` against :data:`parameter_registry` using the same
    precedence as :class:`chisurf.core.parameter.Parameter`, so a description
    surfaced in a fitting widget and one surfaced in an AutoForm field agree:

    1. An explicit ``registry_id`` (e.g. ``"rics.D"``) wins, checked against the
       scoped ``by_qualified_id`` index first, then the legacy bare-name one.
    2. A class-scoped ``"<owner>.<name>"`` qualified id, so two unrelated
       classes reusing the same bare name never cross-contaminate.
    3. A non-ambiguous bare ``name`` (or a non-ambiguous entry listing ``name``
       among its ``aliases``).

    Parameters
    ----------
    name : str
        Bare parameter name (e.g. ``"D"``).
    owner : str, optional
        Class name owning the parameter, used to disambiguate a scoped id.
    registry_id : str, optional
        Fully-qualified registry id that takes precedence over ``name``.

    Returns
    -------
    str
        The description, or an empty string when no match is found.
    """
    meta = parameter_registry if isinstance(parameter_registry, dict) else {}
    params_meta = meta.get("parameters", meta) if isinstance(meta, dict) else {}
    qualified_meta = meta.get("by_qualified_id", {}) if isinstance(meta, dict) else {}
    entry = None
    # 1) Explicit registry id.
    if registry_id is not None:
        if isinstance(qualified_meta, dict):
            entry = qualified_meta.get(registry_id)
        if entry is None and isinstance(params_meta, dict):
            entry = params_meta.get(registry_id)
    # 2) Class-scoped qualified id.
    if entry is None and owner and isinstance(qualified_meta, dict):
        entry = qualified_meta.get(f"{owner}.{name}")
    # 3) Non-ambiguous bare name (then aliases).
    if entry is None and isinstance(params_meta, dict):
        candidate = params_meta.get(name)
        if isinstance(candidate, dict) and not candidate.get("ambiguous"):
            entry = candidate
        if entry is None:
            for _val in params_meta.values():
                if not isinstance(_val, dict) or _val.get("ambiguous"):
                    continue
                aliases = _val.get("aliases") or []
                if isinstance(aliases, list) and name in aliases:
                    entry = _val
                    break
    if isinstance(entry, dict):
        d = entry.get("description")
        if isinstance(d, str):
            return d
    return ""


eps = sys.float_info.epsilon
working_path = ''

session_str = datetime.datetime.now().strftime('session_%H_%M_%d_%m_%Y')
# Create logs subfolder
logs_folder = chisurf_settings_path / "logs"
logs_folder.mkdir(exist_ok=True)
session_file = logs_folder / str(session_str + ".py")
session_log = logs_folder / str(session_str + ".log")

try:
    import chisurf as _chisurf
    _chisurf._apply_logging_settings(sys.modules[__name__])
except Exception:
    pass
