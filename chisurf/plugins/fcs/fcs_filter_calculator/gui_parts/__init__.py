"""Optional Qt compatibility export; native applications import without Qt."""

__all__ = ['FcsFilterCalculatorWidget']

def __getattr__(name):
    if name == "FcsFilterCalculatorWidget":
        from ..gui_parts.main_window import FcsFilterCalculatorWidget
        return FcsFilterCalculatorWidget
    if name == "FilterCalcClient":
        from ..gui.client import FilterCalcClient
        return FilterCalcClient
    raise AttributeError(name)
