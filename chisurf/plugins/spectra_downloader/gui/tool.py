"""Compatibility factory for the standalone native spectra tool."""

from .app import SpectraApp, create_app

SpectraTool = SpectraApp


def main():
    from emtk.native import main as launch

    launch(
        [
            "--app",
            "chisurf.plugins.spectra_downloader.gui.app:create_app",
            "--title",
            "Spectra",
            "--size",
            "1180x760",
        ]
    )


if __name__ == "__main__":
    main()
