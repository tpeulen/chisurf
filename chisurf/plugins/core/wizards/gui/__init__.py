"""Lazy GUI layer for the Wizards hub."""

__all__ = ["WizardHub"]


def __getattr__(name):
    if name == "WizardHub":
        from .tool import WizardHub
        return WizardHub
    raise AttributeError(name)
