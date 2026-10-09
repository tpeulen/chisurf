"""ChiSurf version, logo, developer and contact information."""

name = "Help:About ChiSurf"
icon = "ℹ"
__all__ = ["AboutDialog"]


def __getattr__(attribute):
    if attribute == "AboutDialog":
        from .qt_dialog import AboutDialog
        return AboutDialog
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")


if __name__ == "plugin":
    from chisurf.plugins.core.about.qt_dialog import AboutDialog
    window = AboutDialog()
    window.show()
