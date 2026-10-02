"""Launch a ChiSurf native EMTK plugin without starting the Qt application."""
from __future__ import annotations

import argparse

from .i18n import SUPPORTED_LOCALES, install
from .plugins import configure_launch, manifests, native_factory


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", help="Manifest plugin id")
    parser.add_argument("--list", action="store_true", help="List native factories and pending ports")
    parser.add_argument("--language", choices=SUPPORTED_LOCALES)
    parser.add_argument("--size", help="WIDTHxHEIGHT; otherwise restore the saved size")
    parser.add_argument("--path", help="Initial document for help/code_editor")
    parser.add_argument("--anchor", help="Documentation anchor or source line")
    args = parser.parse_args(argv)
    if args.list:
        for key, manifest in manifests().items():
            spec = manifest.get("entrypoints", {}).get("emtk")
            print(f"{key}: {spec or 'pending native port'}")
        return 0
    if not args.plugin:
        parser.error("--plugin or --list is required")
    try:
        native_factory(args.plugin)
    except (KeyError, ValueError) as error:
        parser.error(str(error))
    install(args.language)
    configure_launch(args.plugin, args.language, args.path, args.anchor)
    from emtk.native import main as run_native

    native_args = ["--app", "chisurf.emtk.plugins:make_selected_app"]
    if args.size:
        native_args += ["--size", args.size]
    run_native(native_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
