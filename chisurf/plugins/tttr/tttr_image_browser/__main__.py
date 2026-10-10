"""Entry point for running the TTTR Image Browser directly.

Usage:
  python -m chisurf.plugins.tttr.tttr_image_browser
"""


def main() -> None:
    """Launch the image browser as a native emtk application."""
    from chisurf.emtk.__main__ import main as launch

    launch(["--plugin", "tttr_image_browser"])


if __name__ == "__main__":
    main()
