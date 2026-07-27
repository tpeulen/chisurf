import copy
import pathlib
import yaml

import chisurf.core.experiments.fcs
import chisurf.core.experiments.tcspc
import chisurf.core.experiments.pda
import chisurf.core.experiments.deer
import chisurf.core.experiments.globalfit
import chisurf.core.experiments.modelling
from chisurf.core.experiments.core import Experiment
from chisurf.core.settings import get_path


def _load_yaml_config(path: pathlib.Path) -> dict:
    """Load a YAML configuration file and return its contents as a dict.

    Parameters
    ----------
    path : pathlib.Path
        Path to the YAML file.

    Returns
    -------
    dict
        Parsed YAML content, or an empty dict on failure.
    """
    try:
        with open(str(path), 'r', encoding='utf-8') as fp:
            return yaml.safe_load(fp) or {}
    except Exception:
        return {}


def _deep_merge_dicts(base: dict, override: dict) -> dict:
    """Recursively merge override into base without mutating the inputs."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if (
            isinstance(value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def get_experiment_config_files() -> tuple[pathlib.Path, pathlib.Path]:
    """Locate the packaged and the per-user experiment configuration file.

    Both files are named ``experiment_configs.yaml``. The packaged one is the
    read-only default shipped inside ``chisurf/core/settings``; the user one
    lives in the writable settings directory and overrides it. This is the one
    place the pair is resolved — the GUI, the agent bootstrap and
    :func:`load_experiment_types` all go through it so that a renamed or added
    experiment cannot reach some consumers and not others.

    Returns
    -------
    tuple of pathlib.Path
        ``(packaged, user)``. The user file need not exist.
    """
    packaged = pathlib.Path(__file__).parent.parent / 'settings' / 'experiment_configs.yaml'
    user = pathlib.Path(get_path('settings')) / 'experiment_configs.yaml'
    return packaged, user


def load_experiment_types():
    """Load experiment type registry from experiment_configs.yaml.

    The primary source is the user settings file
    ``get_path('settings') / 'experiment_configs.yaml'``; if that file does
    not exist, the packaged default under ``chisurf/core/settings`` is used.

    In addition to entries under the top-level ``experiment_types`` mapping,
    this function ensures that every top-level experiment section (except
    ``"experiment_types"`` and ``"global"``) receives an
    :class:`Experiment` instance. This makes the registry robust against
    partially updated user configuration files where a new experiment (e.g.
    ``pch``) has been added without a corresponding ``experiment_types``
    entry.
    """

    default_config_file, user_config_file = get_experiment_config_files()

    # Load packaged defaults and merge user overrides on top so that
    # previously hidden experiments (like "structure") become visible
    # unless the user explicitly hides them again.
    config = _load_yaml_config(default_config_file)
    if user_config_file.is_file():
        user_config = _load_yaml_config(user_config_file)
        config = _deep_merge_dicts(config, user_config)

    experiment_types: dict[str, Experiment] = {}

    # First, honor explicit experiment_types definitions when present.
    type_defs = config.get('experiment_types', {}) or {}
    if isinstance(type_defs, dict):
        for key, value in type_defs.items():
            if not isinstance(value, dict):
                value = {}
            name = value.get('name', key)
            hidden = bool(value.get('hidden', False))
            experiment_types[key] = Experiment(name, hidden)

    # Next, ensure that all top-level experiment sections have an Experiment
    # object, even if they are missing from experiment_types. This prevents
    # KeyError when new experiments are added only under their own section.
    for key in list(config.keys()):
        if key in ('experiment_types', 'global'):
            continue
        if key not in experiment_types:
            experiment_types[key] = Experiment(name=key, hidden=False)

    return experiment_types


# Load experiment types at import time so chisurf.core.experiments.types is ready
types = load_experiment_types()
