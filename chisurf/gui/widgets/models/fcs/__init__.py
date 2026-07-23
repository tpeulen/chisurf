from __future__ import annotations

import importlib

__all__ = [
    "ParseFCSWidget",
    "DyeShapeFCSWidget",
    "MdfFCSWidget",
    "MaxEntFCSWidget",
    "MaxEntRHWidget",
]

_EXPORTS = {
    "ParseFCSWidget": ".parse_fcs_widget",
    "DyeShapeFCSWidget": ".dye_volume_widget",
    "MdfFCSWidget": ".mdf_widget",
    "MaxEntFCSWidget": ".maxent_widget",
    "MaxEntRHWidget": ".maxent_widget",
}


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
