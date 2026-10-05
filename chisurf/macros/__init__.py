"""Public macro namespace with lazy module loading.

Keeping the package initializer free of GUI imports lets native EMTK and
headless services import individual macro modules without loading Qt. Existing
``chisurf.macros.<name>`` access continues to resolve through the legacy
submodules on demand.
"""

from __future__ import annotations

from importlib import import_module

_MODULES = ("model", "model_parse", "core_data", "core_fit")


def __getattr__(name: str):
    for module_name in _MODULES:
        module = import_module(f"{__name__}.{module_name}")
        try:
            value = getattr(module, name)
        except AttributeError:
            continue
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    names = set(globals())
    for module_name in _MODULES:
        module = import_module(f"{__name__}.{module_name}")
        names.update(name for name in vars(module) if not name.startswith("_"))
    return sorted(names)
