from __future__ import annotations

import importlib
import logging
import os

# Map chisurf.logging to the standard logging module to support
# "import chisurf.logging" throughout the codebase.
import sys
sys.modules['chisurf.logging'] = logging
import pathlib
import typing

# A source checkout keeps first-party companion packages below ``modules/``.
# Bootstrap them before importing any ChiSurf module that may depend on them --
# and first drop any *other* environment's site-packages a launcher put on the
# path, because a compiled extension imported from there fails in the dynamic
# loader rather than at the import (see the module).
from . import _bundled_packages as _sys_path_setup

_sys_path_setup.drop_foreign_environment_paths()
_sys_path_setup.bootstrap_bundled_packages()
del _sys_path_setup

import chisurf.core.info


__version__ = chisurf.core.info.__version__

fits: typing.List["chisurf.core.fitting.fit.FitGroup"] = list()
imported_datasets: typing.List["chisurf.core.data.DataGroup"] = list()


def registered_parameter_groups() -> typing.List[typing.Tuple[str, str, typing.Any]]:
    """Return parameter groups registered outside ``fits`` (e.g. by plugins).

    Thin re-export of
    :func:`chisurf.core.registry.parameter_groups.iter_registered_parameter_groups`
    so the Global View can enumerate out-of-fit groups the same way it reaches
    ``chisurf.fits``. Each item is ``(owner_id, label, group)``.
    """
    from chisurf.core.registry.parameter_groups import (
        iter_registered_parameter_groups,
    )

    return iter_registered_parameter_groups()
run = lambda x: x   # This is replaced during initialization to execute commands via a command line interface
cs = None         # The current instance of ChiSurf
console = None
experiment: typing.Dict[str, "chisurf.core.experiments.core.experiment.Experiment"] = dict()
working_path = pathlib.Path().home()
verbose = False  # Updated lazily when settings are loaded

import types

_SETTINGS_MODULE = None
_LOGGING_SETTINGS_APPLIED = False


class _LazySettingsModule(types.ModuleType):
    def __getattr__(self, item):
        mod = _load_settings_module()
        return getattr(mod, item)

    def __dir__(self):
        mod = _load_settings_module()
        return dir(mod)


class _LazySettingsSubmodule(types.ModuleType):
    def __init__(self, name, real_module_path):
        super().__init__(name)
        self.__real_module_path = real_module_path

    def __getattr__(self, item):
        mod = importlib.import_module(self.__real_module_path)
        sys.modules[self.__name__] = mod
        return getattr(mod, item)

    def __dir__(self):
        mod = importlib.import_module(self.__real_module_path)
        sys.modules[self.__name__] = mod
        return dir(mod)


sys.modules['chisurf.settings'] = _LazySettingsModule('chisurf.settings')
sys.modules['chisurf.settings.path_utils'] = _LazySettingsSubmodule('chisurf.settings.path_utils', 'chisurf.core.settings.path_utils')
sys.modules['chisurf.settings.ai_settings'] = _LazySettingsSubmodule('chisurf.settings.ai_settings', 'chisurf.core.settings.ai_settings')


def _load_settings_module():
    global _SETTINGS_MODULE
    if _SETTINGS_MODULE is None:
        _SETTINGS_MODULE = importlib.import_module("chisurf.core.settings")
        sys.modules['chisurf.settings'] = _SETTINGS_MODULE
    return _SETTINGS_MODULE



def _apply_logging_settings(settings_module) -> None:
    global _LOGGING_SETTINGS_APPLIED, verbose
    if _LOGGING_SETTINGS_APPLIED:
        return
    log_file = getattr(settings_module, "session_log", None)
    level = getattr(settings_module, "log_level", None)
    if not isinstance(level, int):
        # Same default as _initialize_logging: an unset level must not make
        # an importing process chatty. A settings file that states a level
        # is honoured above.
        level = logging.WARNING
    root = logging.getLogger()
    root.setLevel(level)

    has_file = False
    for handler in list(root.handlers):
        try:
            if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None) == (
                str(log_file) if log_file else None
            ):
                has_file = True
        except Exception:
            continue
    if log_file and not has_file:
        try:
            fh = logging.FileHandler(str(log_file), encoding="utf-8")
            fh.setLevel(level)
            fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
            root.addHandler(fh)
        except Exception:
            pass

    verbose = getattr(settings_module, "verbose", verbose)
    _LOGGING_SETTINGS_APPLIED = True


def _initialize_logging() -> None:
    if globals().get("__logging_initialized__", False):
        return

    env_level = os.environ.get("CHISURF_LOG_LEVEL")
    # WARNING, not INFO: the import-time default is what every embedding
    # process inherits (ndX prints INFO on every plot update and file
    # operation), and an import must not make the host chatty. The GUI's own
    # logging setup and `CHISURF_LOG_LEVEL` both still say otherwise
    # deliberately.
    level = logging.WARNING
    if env_level:
        if env_level.isdigit():
            level = int(env_level)
        else:
            level = getattr(logging, env_level.upper(), logging.WARNING)

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    root = logging.getLogger()
    root.setLevel(level)

    has_stream = any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers)
    if not has_stream:
        sh = logging.StreamHandler(stream=sys.stderr)
        sh.setLevel(level)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    globals()["__logging_initialized__"] = True
    logging.getLogger(__name__).debug("Logging initialized with level=%s (env)", level)


_initialize_logging()


def __getattr__(name: str):
    """Lazily resolve selected subpackages or settings on first access."""
    if name == "plots":
        mod = importlib.import_module("chisurf.gui.plots")
        globals()["plots"] = mod
        return mod
    if name == "settings":
        settings_module = _load_settings_module()
        _apply_logging_settings(settings_module)
        globals()["settings"] = settings_module
        return settings_module
    if name == "verbose":
        settings_module = _load_settings_module()
        _apply_logging_settings(settings_module)
        value = getattr(settings_module, "verbose", verbose)
        globals()["verbose"] = value
        return value
    if name == "history":
        mod = importlib.import_module("chisurf.history")
        # Return the package's shared singleton (not a fresh instance), so the
        # chisurf.history package-vs-singleton name collision is benign: the module
        # delegates OperationHistory members to this same object. See
        # chisurf/history/__init__.py.
        value = mod.get_history()
        globals()["history"] = value
        return value
    if name == "actions":
        mod = importlib.import_module("chisurf.core.actions")
        globals()["actions"] = mod
        return mod
    if name == "action_dispatcher":
        mod = importlib.import_module("chisurf.core.actions._infra")
        # The import above pulls in the ``chisurf.core.actions`` package, whose
        # ``@action`` decorators read ``cs.action_registry`` and therefore re-enter
        # this function: that nested frame already built *and cached* a dispatcher,
        # and the 60 actions registered into its registry. Building a second one
        # here would overwrite it with an empty registry, so every dispatch would
        # miss. Always hand back the cached instance if one appeared meanwhile.
        value = globals().get("action_dispatcher")
        if value is None:
            value = mod.build_default_dispatcher(
                history_provider=lambda: getattr(sys.modules[__name__], "history", None)
            )
            globals()["action_dispatcher"] = value
        return value
    if name == "action_registry":
        dispatcher = __getattr__("action_dispatcher")
        # Same re-entrancy: resolving the dispatcher may have cached the registry.
        value = globals().get("action_registry")
        if value is None:
            value = getattr(dispatcher, "registry", None)
            globals()["action_registry"] = value
        return value
    if name == "action_catalog":
        mod = importlib.import_module("chisurf.core.actions._infra")
        value = mod.get_action_catalog
        globals()["action_catalog"] = value
        return value
    if name == "action_execute":
        mod = importlib.import_module("chisurf.core.actions._infra")
        value = mod.invoke_action
        globals()["action_execute"] = value
        return value
    if name == "current_setup":
        _cs_instance = globals().get("cs")
        if _cs_instance is None:
            raise AttributeError(f"ChiSurf is not initialized — {name!r} is unavailable")
        return _cs_instance.current_setup
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
