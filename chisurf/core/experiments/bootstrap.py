"""Headless registration of experiments, readers and model classes.

The GUI main window builds :data:`chisurf.experiment` from
``experiment_configs.yaml`` while it constructs its widgets
(:mod:`chisurf.gui.main_helper`).  Anything that runs without that window --
the LLM agent, the CLI, batch scripts, tests -- therefore used to see an
empty registry: no readers to load a file with and no model classes to fit
it with.

:func:`ensure_experiments_registered` performs the same registration from the
same configuration file, but without creating any controller widgets.  It is
idempotent and safe to call from a GUI session (where it is a no-op because
the window already registered everything).

Reader and model classes that are :class:`QWidget` subclasses can only be
instantiated once a ``QApplication`` exists.  When none does, those entries
are skipped and the remaining Qt-free classes are still registered, so a
truly headless process gets a usable -- if smaller -- registry.
"""

from __future__ import annotations

import importlib
import logging
import pathlib
from typing import Any

import chisurf as cs
import chisurf.core.experiments as experiments
from chisurf.core.experiments.core import Experiment

logger = logging.getLogger(__name__)

_SKIPPED_SECTIONS = {"experiment_types", "global"}


def _qt_widget_class(obj: Any) -> bool:
    """Return whether *obj* is a class deriving from ``QtWidgets.QWidget``.

    Parameters
    ----------
    obj : object
        Candidate reader or model class.

    Returns
    -------
    bool
        ``True`` when *obj* needs a running ``QApplication`` to instantiate.
    """
    if not isinstance(obj, type):
        return False
    try:
        from qtpy import QtWidgets
    except Exception:
        return False
    try:
        return issubclass(obj, QtWidgets.QWidget)
    except TypeError:
        return False


def qt_application_available() -> bool:
    """Return whether a ``QApplication`` instance currently exists."""
    try:
        from qtpy import QtWidgets
    except Exception:
        return False
    try:
        return QtWidgets.QApplication.instance() is not None
    except Exception:
        return False


#: The off-screen application created by :func:`ensure_qt_application`.
#: A ``QApplication`` that nothing references is garbage-collected the moment
#: the call returns, and ``QApplication.instance()`` goes back to ``None`` --
#: which silently costs the caller every Qt-only reader and model.
_QT_APPLICATION: Any = None


def ensure_qt_application() -> bool:
    """Create an off-screen ``QApplication`` when none exists yet.

    Several readers build Qt widgets deep inside ``get_data`` (detector-setup
    editors, channel pickers).  Without a ``QApplication`` those calls do not
    raise -- Qt aborts the whole process.  A head-less driver that wants the
    full reader and model set therefore has to own an application object,
    even though nothing is ever shown.

    Returns
    -------
    bool
        ``True`` when an application exists afterwards.
    """
    global _QT_APPLICATION
    try:
        from qtpy import QtWidgets
    except Exception:
        return False
    if QtWidgets.QApplication.instance() is not None:
        return True
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        _QT_APPLICATION = QtWidgets.QApplication([])
    except Exception:
        logger.warning("could not create an off-screen QApplication", exc_info=True)
        return False
    return QtWidgets.QApplication.instance() is not None


def resolve_class(class_path: str | None) -> type | None:
    """Import and return the class named by a dotted path.

    Parameters
    ----------
    class_path : str or None
        Dotted path such as ``"chisurf.core.experiments.tcspc.TCSPCReader"``.

    Returns
    -------
    type or None
        The resolved class, or ``None`` when the path is empty or the import
        fails.
    """
    if not class_path or not isinstance(class_path, str):
        return None
    module_name, _, attr = class_path.rpartition(".")
    if not module_name:
        return None
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        logger.debug("agent bootstrap: cannot import %s (%s)", module_name, exc)
        return None
    resolved = getattr(module, attr, None)
    if resolved is None:
        logger.debug("agent bootstrap: %s has no attribute %s", module_name, attr)
    return resolved


def _experiment_config() -> dict[str, Any]:
    """Return the merged packaged/user experiment configuration mapping."""
    from chisurf.core.experiments import _deep_merge_dicts, _load_yaml_config
    from chisurf.core.settings import get_path

    package_config = pathlib.Path(__file__).parent.parent / "settings" / "experiment_configs.yaml"
    user_config = pathlib.Path(get_path("settings")) / "experiment_configs.yaml"
    config = _load_yaml_config(package_config)
    if user_config.is_file():
        config = _deep_merge_dicts(config, _load_yaml_config(user_config))
    return config or {}


def _register_readers(
    experiment: Experiment,
    reader_configs: list[dict[str, Any]],
    allow_widgets: bool,
) -> list[str]:
    """Instantiate and attach the readers declared for one experiment.

    Parameters
    ----------
    experiment : Experiment
        Experiment the readers belong to.
    reader_configs : list of dict
        ``readers:`` entries from the configuration file.
    allow_widgets : bool
        Whether ``QWidget`` reader classes may be instantiated.

    Returns
    -------
    list of str
        Names of the readers that were registered.
    """
    # A reader declared without a ``name`` param is identified by its class,
    # otherwise a re-run appends a second copy of it.
    existing = {str(name) for name in experiment.reader_names}
    existing |= {type(reader).__name__ for reader in experiment.readers}
    added: list[str] = []
    for reader_config in reader_configs or []:
        reader_class = resolve_class(reader_config.get("reader_class"))
        if reader_class is None:
            continue
        if _qt_widget_class(reader_class) and not allow_widgets:
            logger.debug(
                "agent bootstrap: skipping widget reader %s (no QApplication)",
                reader_config.get("reader_class"),
            )
            continue
        params = dict(reader_config.get("reader_params", {}) or {})
        params["experiment"] = experiment
        identity = str(params.get("name") or reader_class.__name__)
        if identity in existing:
            continue
        existing.add(identity)
        try:
            experiment.add_reader(reader_class(**params))
        except Exception as exc:
            logger.warning(
                "agent bootstrap: reader %s failed to initialise: %s",
                reader_config.get("reader_class"),
                exc,
            )
            continue
        added.append(str(params.get("name", reader_class.__name__)))
    return added


def _register_models(
    experiment: Experiment,
    model_paths: list[str],
    allow_widgets: bool,
) -> list[str]:
    """Attach the model classes declared for one experiment.

    Parameters
    ----------
    experiment : Experiment
        Experiment the models belong to.
    model_paths : list of str
        ``models:`` entries from the configuration file.
    allow_widgets : bool
        Whether ``QWidget`` model classes may be registered.

    Returns
    -------
    list of str
        ``name`` attributes of the model classes that were registered.
    """
    added: list[str] = []
    for model_path in model_paths or []:
        model_class = resolve_class(model_path)
        if model_class is None:
            continue
        if _qt_widget_class(model_class) and not allow_widgets:
            logger.debug("agent bootstrap: skipping widget model %s (no QApplication)", model_path)
            continue
        experiment.add_model_class(model_class)
        added.append(str(getattr(model_class, "name", model_class.__name__)))
    return added


def ensure_experiments_registered(
    allow_widgets: bool | None = None,
    force: bool = False,
) -> dict[str, dict[str, list[str]]]:
    """Populate :data:`chisurf.experiment` from the experiment configuration.

    Parameters
    ----------
    allow_widgets : bool, optional
        Whether ``QWidget`` reader/model classes may be used.  Defaults to
        whether a ``QApplication`` currently exists.
    force : bool, default False
        Re-run the registration even when :data:`chisurf.experiment` already
        holds experiments with readers.

    Returns
    -------
    dict
        ``{experiment_name: {"readers": [...], "models": [...]}}`` describing
        what is registered after the call.

    Examples
    --------
    >>> registry = ensure_experiments_registered()
    >>> isinstance(registry, dict)
    True
    """
    if allow_widgets is None:
        allow_widgets = qt_application_available()

    already_populated = any(
        getattr(experiment, "readers", None) for experiment in cs.experiment.values()
    )
    if already_populated and not force:
        return describe_registry()

    config = _experiment_config()
    for section_name, section in config.items():
        if section_name in _SKIPPED_SECTIONS or not isinstance(section, dict):
            continue
        experiment = experiments.types.get(section_name)
        if experiment is None:
            experiment = Experiment(name=str(section.get("name", section_name)))
            experiments.types[section_name] = experiment
        _register_readers(experiment, section.get("readers", []), allow_widgets)
        _register_models(experiment, section.get("models", []), allow_widgets)
        cs.experiment[experiment.name] = experiment

    global_config = config.get("global", {}) or {}
    if global_config:
        global_experiment = Experiment(
            name=str(global_config.get("name", "Global")),
            hidden=bool(global_config.get("hidden", True)),
        )
        if cs.experiment.get(global_experiment.name) is None:
            _register_readers(global_experiment, global_config.get("readers", []), allow_widgets)
            _register_models(global_experiment, global_config.get("models", []), allow_widgets)
            cs.experiment[global_experiment.name] = global_experiment

    return describe_registry()


def describe_registry() -> dict[str, dict[str, list[str]]]:
    """Return the readers and models registered per experiment.

    Returns
    -------
    dict
        ``{experiment_name: {"readers": [...], "models": [...], "hidden": bool}}``.
    """
    registry: dict[str, dict[str, list[str]]] = {}
    for name, experiment in cs.experiment.items():
        registry[str(name)] = {
            "readers": [str(n) for n in experiment.reader_names],
            "models": [str(n) for n in experiment.model_names],
            "hidden": bool(getattr(experiment, "hidden", False)),
        }
    return registry


def find_reader(
    experiment_name: str | None = None,
    reader_name: str | None = None,
) -> Any | None:
    """Look up a registered reader by experiment and/or reader name.

    Parameters
    ----------
    experiment_name : str, optional
        Experiment to search (case-insensitive).  All experiments are searched
        when omitted.
    reader_name : str, optional
        Reader name to match (case-insensitive).  The first reader of the
        experiment is returned when omitted.

    Returns
    -------
    object or None
        The matching :class:`ExperimentReader`, or ``None``.
    """
    wanted_experiment = (experiment_name or "").strip().lower()
    wanted_reader = (reader_name or "").strip().lower()
    for name, experiment in cs.experiment.items():
        if wanted_experiment and str(name).lower() != wanted_experiment:
            continue
        readers = list(getattr(experiment, "readers", []) or [])
        if not readers:
            continue
        if not wanted_reader:
            if wanted_experiment:
                return readers[0]
            continue
        for reader in readers:
            if str(getattr(reader, "name", "")).lower() == wanted_reader:
                return reader
    return None
