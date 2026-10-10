"""Native anisotropy workflow: the emtk app (``app``), its model and the shared view-model."""

__all__ = ["AnisotropyViewModel"]


def __getattr__(name):
    if name == "AnisotropyViewModel":
        from .view_model import AnisotropyViewModel

        return AnisotropyViewModel
    raise AttributeError(name)
