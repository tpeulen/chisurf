"""Launch the native VV/VH G-factor calculator."""


def main():
    """Use the shared native plugin launcher."""
    from chisurf.emtk.__main__ import main as launch

    return launch(["--plugin", "vv_vh_g_factor", "--size", "1600x1000"])


if __name__ == "__main__":
    raise SystemExit(main())
