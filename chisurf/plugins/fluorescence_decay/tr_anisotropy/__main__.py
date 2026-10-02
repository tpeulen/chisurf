"""Launch the native time-resolved anisotropy workflow."""


def main():
    from chisurf.emtk.__main__ import main as launch
    return launch(["--plugin","tr_anisotropy"])


if __name__=="__main__":
    raise SystemExit(main())
