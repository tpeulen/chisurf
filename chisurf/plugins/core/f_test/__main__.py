"""Launch the native F-test calculator."""


def main():
    from chisurf.emtk.__main__ import main as launch

    return launch(["--plugin", "f_test", "--size", "900x850"])


if __name__ == "__main__":
    raise SystemExit(main())
