"""Native anisotropy model with lazy legacy Qt exports."""

__all__ = ["AnisotropyWizard", "ChisurfWizard", "AnisotropyViewModel"]


def __getattr__(name):
    if name == "AnisotropyViewModel":
        from .view_model import AnisotropyViewModel

        return AnisotropyViewModel
    if name in {"AnisotropyWizard", "ChisurfWizard"}:
        from . import tool

        return getattr(tool, name)
    raise AttributeError(name)
