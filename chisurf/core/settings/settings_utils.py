from __future__ import annotations

import pathlib
import shutil
import copy
import logging
import yaml
import numpy as np

from .file_utils import safe_open_file
from .path_utils import get_path


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively overlay ``override`` onto ``base`` (override wins on leaves).

    Nested dicts are merged key-by-key; every other value (including lists) is
    replaced wholesale by ``override``.
    """
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_chisurf_settings(setting_file: pathlib.Path, use_source_folder: bool = False) -> dict:
    """Return the content of a settings file from the user settings path.

    If the user file does not exist it is copied from the package folder. The
    packaged (source) settings are always deep-merged *underneath* the user file,
    so keys added in newer releases resolve with their defaults on existing
    installs while any value the user has set still wins. Pass
    ``use_source_folder=True`` to read the packaged defaults directly.

    :param setting_file: path to settings file
    :param use_source_folder: if true use settings file in source code folder
    :return:
    """
    package_path = pathlib.Path(__file__).parent
    original_settings = package_path / setting_file.parts[-1]

    def _read(path: pathlib.Path) -> dict:
        return safe_open_file(
            file_path=path,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {path}",
        )

    if use_source_folder:
        return _read(original_settings)
    if not setting_file.is_file():
        shutil.copyfile(original_settings, setting_file)
    defaults = _read(original_settings)
    user = _read(setting_file)
    if isinstance(defaults, dict) and isinstance(user, dict):
        return _deep_merge(defaults, user)
    return user if user else defaults


def copy_settings_to_user_folder():
    """Copies all settings files from the package directory to the user folder,
    ensuring that existing files are not overwritten."""
    package_path = pathlib.Path(__file__).parent
    user_settings_path = get_path('settings')
    user_settings_path.mkdir(parents=True, exist_ok=True)

    for file in package_path.iterdir():
        if not file.is_file():
            continue
        # Help mappings are considered part of the application resources and are
        # not meant to be edited per-user, so we do not copy help_mappings.yaml
        # into the user settings directory.
        if file.name == "help_mappings.yaml":
            continue
        destination_file = user_settings_path / file.name
        if not destination_file.exists():  # Avoid overwriting existing files
            shutil.copyfile(file, destination_file)

    # Also copy style files
    copy_styles_to_user_folder()


def copy_styles_to_user_folder():
    """Copies all style files from the gui/styles directory to the user folder,
    updating existing files if their content differs from the package version."""
    # Navigate from core/settings/settings_utils.py up to chisurf/ then gui/styles
    package_path = pathlib.Path(__file__).resolve().parent.parent.parent / 'gui' / 'styles'
    user_settings_path = get_path('settings') / 'styles'
    user_settings_path.mkdir(parents=True, exist_ok=True)

    for file in package_path.iterdir():
        if file.is_file() and file.suffix == '.qss':
            destination_file = user_settings_path / file.name
            if destination_file.exists():
                try:
                    src_text = file.read_text(encoding="utf-8")
                    dst_text = destination_file.read_text(encoding="utf-8")
                    if src_text != dst_text:
                        shutil.copyfile(file, destination_file)
                except Exception:
                    pass
            else:
                shutil.copyfile(file, destination_file)


def update_settings_section(section: str, values: dict) -> bool:
    """Merge *values* into one top-level section of the user's settings file.

    The one place that writes ``settings_chisurf.yaml`` for a caller that owns a
    single section. Three things it gets right that hand-rolled writers in the
    tree did not:

    **It writes the user's file**, ``get_path('settings')/settings_chisurf.yaml``
    -- not the packaged defaults inside the installed package. Settings are
    loaded as *packaged defaults deep-merged with the user file, user wins*, so
    a write into the package directory is silently discarded on the next start
    (and may not even be writable on a pip/conda install).

    **It merges rather than dumps the whole tree.** Dumping the live
    ``cs_settings`` bakes every merged default into the user file and destroys
    the explanatory comments in it.

    **It uses ``safe_dump``**, so a stray non-plain object cannot write
    python-specific YAML tags that later fail to load.

    Parameters
    ----------
    section : str
        Top-level key, e.g. ``"plugins"``.
    values : dict
        Keys to set within that section. Keys absent here are left alone, so two
        tools owning different keys of the same section do not clobber each
        other.

    Returns
    -------
    bool
        True when the file was written.

    """
    settings_file = get_path('settings') / 'settings_chisurf.yaml'
    try:
        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}",
        )
        if not isinstance(data, dict):
            data = {}
        block = data.get(section)
        if not isinstance(block, dict):
            block = {}
        block.update(copy.deepcopy(values))
        data[section] = block
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)
        return True
    except Exception:
        logging.getLogger(__name__).exception(
            "Could not write section %r to %s", section, settings_file
        )
        return False


def set_warn_missing_detector_setups(show_warning: bool) -> bool:
    """Persist the warn_missing_detector_setups flag in the user's settings YAML.

    Args:
        show_warning: If True, the warning dialog will be shown when the setups file is missing.
                      If False, the warning will be suppressed in the future.
    Returns:
        True if the file was written successfully, False otherwise.
    """
    try:
        settings_file = get_path('settings') / 'settings_chisurf.yaml'
        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}"
        )
        if not isinstance(data, dict):
            data = {}
        data['warn_missing_detector_setups'] = bool(show_warning)
        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        return True
    except Exception:
        return False


def build_fret_rda_axis(
    rda_min: float,
    rda_max: float,
    rda_resolution: int,
    rda_scale: str | None = None,
) -> np.ndarray:
    if rda_resolution < 2:
        rda_resolution = 2
    scale = str(rda_scale or "log").lower()
    try:
        if scale.startswith("lin"):
            axis = np.linspace(
                float(rda_min),
                float(rda_max),
                int(rda_resolution),
                dtype=np.float64,
            )
        else:
            axis = np.logspace(
                start=np.log10(float(rda_min)),
                stop=np.log10(float(rda_max)),
                num=int(rda_resolution),
                dtype=np.float64,
            )
    except Exception:
        try:
            axis = np.linspace(
                float(rda_min),
                float(rda_max),
                int(rda_resolution),
                dtype=np.float64,
            )
        except Exception:
            axis = np.linspace(1.0, 130.0, 96, dtype=np.float64)
    return axis


def set_fret_rda_axis(
    rda_min: float,
    rda_max: float,
    rda_resolution: int,
    rda_scale: str | None = None,
) -> bool:
    """Persist global FRET R_DA axis settings in the user's settings YAML.

    The values are stored under the ``fret`` section as ``rda_min``,
    ``rda_max``, ``rda_resolution`` and optionally ``rda_scale`` ("log" or
    "lin") and are used to build the distance grid for FRET-related models.
    """
    try:
        settings_file = get_path('settings') / 'settings_chisurf.yaml'
        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}"
        )
        if not isinstance(data, dict):
            data = {}
        fret_cfg = data.get('fret')
        if not isinstance(fret_cfg, dict):
            fret_cfg = {}
            data['fret'] = fret_cfg
        fret_cfg['rda_min'] = float(rda_min)
        fret_cfg['rda_max'] = float(rda_max)
        fret_cfg['rda_resolution'] = int(rda_resolution)
        if rda_scale is not None:
            fret_cfg['rda_scale'] = str(rda_scale)
        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        return True
    except Exception:
        return False


def set_optimization_settings(
        sampling: dict = None,
        leastsq: dict = None,
) -> bool:
    """Persist optimisation settings in the user's settings YAML.

    The sampling settings are what a run is actually configured by -- which
    sampler, how long, how the chains are stored -- so a dialog that changed
    them only for the session would be a dialog that lies about what the next
    run does.

    Parameters
    ----------
    sampling : dict, optional
        Keys to merge into ``optimization.sampling``.
    leastsq : dict, optional
        Keys to merge into ``optimization.leastsq``.

    Returns
    -------
    bool
        Whether the file was written.
    """
    try:
        settings_file = get_path('settings') / 'settings_chisurf.yaml'
        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}"
        )
        if not isinstance(data, dict):
            data = {}
        optimization = data.get('optimization')
        if not isinstance(optimization, dict):
            optimization = {}
            data['optimization'] = optimization
        for key, values in (('sampling', sampling), ('leastsq', leastsq)):
            if not values:
                continue
            section = optimization.get(key)
            if not isinstance(section, dict):
                section = {}
                optimization[key] = section
            section.update(values)
        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        return True
    except Exception:
        return False


def set_check_experiment_config_updates_on_startup(check_updates: bool) -> bool:
    try:
        settings_file = get_path('settings') / 'settings_chisurf.yaml'
        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}"
        )
        if not isinstance(data, dict):
            data = {}
        data['check_experiment_config_updates_on_startup'] = bool(check_updates)
        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        return True
    except Exception:
        return False


def set_mmfdb_login_settings(mmfdb_settings: dict) -> bool:
    """Persist MMFDB login settings in the user's settings YAML.

    Parameters
    ----------
    mmfdb_settings : dict
        MMFDB settings to merge into the ``mmfdb`` section of
        ``settings_chisurf.yaml``.

    Returns
    -------
    bool
        ``True`` when the settings file was written successfully.
    """
    try:
        settings_file = get_path('settings') / 'settings_chisurf.yaml'
        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}"
        )
        if not isinstance(data, dict):
            data = {}
        mmfdb_cfg = data.get('mmfdb')
        if not isinstance(mmfdb_cfg, dict):
            mmfdb_cfg = {}
            data['mmfdb'] = mmfdb_cfg
        mmfdb_cfg.update(mmfdb_settings)
        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        return True
    except Exception:
        return False


def set_data_loading_settings(data_loading_settings: dict) -> bool:
    """Persist data-loading (slow-storage staging) settings in the user YAML.

    Merges *data_loading_settings* into the ``data_loading`` section of
    ``settings_chisurf.yaml`` and also updates the in-memory
    ``chisurf.core.settings.cs_settings`` so the change takes effect without a
    restart.

    Parameters
    ----------
    data_loading_settings : dict
        Keys understood by :func:`chisurf.core.fio.staging._settings`
        (``enabled``, ``threshold_mbps``, ``min_size``, ``chunk_bytes``,
        ``probe_bytes`` ...).

    Returns
    -------
    bool
        ``True`` when the settings file was written successfully.
    """
    try:
        settings_file = get_path('settings') / 'settings_chisurf.yaml'
        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}"
        )
        if not isinstance(data, dict):
            data = {}
        section = data.get('data_loading')
        if not isinstance(section, dict):
            section = {}
            data['data_loading'] = section
        section.update(data_loading_settings)
        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        # Reflect the change in the live settings dict.
        try:
            import chisurf.core.settings as _cs_settings

            live = _cs_settings.cs_settings.get('data_loading')
            if not isinstance(live, dict):
                live = {}
                _cs_settings.cs_settings['data_loading'] = live
            live.update(data_loading_settings)
        except Exception:
            pass
        return True
    except Exception:
        return False


def set_use_ribbon_interface(use_ribbon: bool) -> bool:
    """Persist the ribbon interface state in the user's settings YAML.

    Args:
        use_ribbon: If True, the ribbon interface will be enabled on startup.
                   If False, the traditional menu bar will be used.
    Returns:
        True if the setting was saved successfully, False otherwise.
    """
    try:
        settings_file = get_path('settings') / 'settings_chisurf.yaml'
        
        # Create settings file if it doesn't exist
        if not settings_file.is_file():
            # Copy from package settings if available
            package_path = pathlib.Path(__file__).parent
            original_settings = package_path / 'settings_chisurf.yaml'
            if original_settings.is_file():
                import shutil
                shutil.copyfile(original_settings, settings_file)
            else:
                # Create empty settings file
                settings_file.parent.mkdir(parents=True, exist_ok=True)
                with open(settings_file, 'w', encoding='utf-8') as fh:
                    yaml.safe_dump({}, fh)
        
        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}"
        )
        if not isinstance(data, dict):
            data = {}
        
        # Ensure gui section exists *and is the one attached to ``data``* — a
        # ``data.get('gui', {})`` default is an orphan dict, so the write would be
        # silently dropped for a settings file that has no ``gui:`` section yet.
        gui_cfg = data.get('gui')
        if not isinstance(gui_cfg, dict):
            gui_cfg = {}
        data['gui'] = gui_cfg

        gui_cfg['use_ribbon_interface'] = bool(use_ribbon)
        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)
        return True
    except Exception:
        return False


def set_language(code: str) -> bool:
    """Persist the UI language code in the user's settings YAML (``gui.language``).

    Parameters
    ----------
    code
        Two-letter locale code (e.g. ``"en"``, ``"de"``). The change takes effect
        on the next GUI start, when the ``QTranslator`` is installed.

    Returns
    -------
    bool
        True if the setting was saved successfully, False otherwise.
    """
    try:
        settings_file = get_path('settings') / 'settings_chisurf.yaml'

        # Create settings file if it doesn't exist
        if not settings_file.is_file():
            package_path = pathlib.Path(__file__).parent
            original_settings = package_path / 'settings_chisurf.yaml'
            if original_settings.is_file():
                import shutil
                shutil.copyfile(original_settings, settings_file)
            else:
                settings_file.parent.mkdir(parents=True, exist_ok=True)
                with open(settings_file, 'w', encoding='utf-8') as fh:
                    yaml.safe_dump({}, fh)

        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}"
        )
        if not isinstance(data, dict):
            data = {}

        # See the note in :func:`set_use_ribbon`: the section has to be attached
        # to ``data`` before it is written, or the language never persists.
        gui_cfg = data.get('gui')
        if not isinstance(gui_cfg, dict):
            gui_cfg = {}
        data['gui'] = gui_cfg

        gui_cfg['language'] = str(code).strip() or 'en'
        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)

        # Update the in-memory settings so a subsequent get_locale() is consistent.
        try:
            from chisurf.core.settings import cs_settings
            cs_settings.setdefault('gui', {})['language'] = gui_cfg['language']
        except Exception:
            pass
        return True
    except Exception:
        return False


def set_acquisition_settings(acquisition_settings: dict) -> bool:
    """Persist acquisition settings in the user's settings YAML.

    Writes the full ``gui.acquisition`` section to ``settings_chisurf.yaml``
    and updates the in-memory ``cs_settings`` / ``gui`` dicts so changes
    take effect immediately without a restart.

    Parameters
    ----------
    acquisition_settings : dict
        Acquisition settings dict to store under ``gui.acquisition``.

    Returns
    -------
    bool
        ``True`` when the settings file was written successfully.
    """
    try:
        settings_file = get_path('settings') / 'settings_chisurf.yaml'
        data = safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}"
        )
        if not isinstance(data, dict):
            data = {}

        # Ensure the gui section exists and is attached to ``data`` (see
        # :func:`set_use_ribbon`).
        gui_cfg = data.get('gui')
        if not isinstance(gui_cfg, dict):
            gui_cfg = {}
        data['gui'] = gui_cfg

        gui_cfg['acquisition'] = acquisition_settings

        with open(settings_file, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(data, fh, default_flow_style=False)

        # Also update the in-memory dicts so the change is immediate
        try:
            import chisurf.core.settings as _cs
            # gui is the same object as cs_settings['gui'], so updating one
            # updates both.  Use direct assignment to ensure the dict reference
            # is preserved.
            _cs.gui['acquisition'] = acquisition_settings
        except Exception:
            pass

        return True
    except Exception:
        return False
