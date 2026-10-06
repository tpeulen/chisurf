"""Subprocess-native startup validation, independent of the Qt application."""

from __future__ import annotations

import argparse
import importlib
import importlib.abc
import json
import logging
import sys
import time
import traceback

QT_ROOTS = {"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6", "pyqtgraph"}


class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in QT_ROOTS:
            raise ImportError(f"Native plugin attempted Qt dependency: {fullname}")
        return None


def check_factory(spec: str, screenshot: str | None = None) -> dict:
    """Construct, render and close in a fresh subprocess; not workflow proof."""
    blocker = BlockQt()
    sys.meta_path.insert(0, blocker)
    started = time.monotonic()
    errors = []

    class DrawErrors(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                errors.append(record.getMessage())

    handler = DrawErrors()
    logging.getLogger().addHandler(handler)
    app = None
    try:
        module, attribute = spec.split(":", 1)
        app = getattr(importlib.import_module(module), attribute)()
        from emtk.testing import RecordingPainter

        for width, height in ((1200, 800), (800, 600)):
            painter = RecordingPainter()
            for _ in range(2):
                app.draw(painter, 0, 0, width, height)
            if not painter.strings:
                raise AssertionError("Native control rendered no text")
        if screenshot:
            from emtk.pil_painter import PilPainter

            painter = PilPainter(1200, 800)
            app.draw(painter, 0, 0, 1200, 800)
            painter.frame.save(screenshot)
        if errors:
            raise AssertionError(f"Native drawing logged errors: {errors}")
        qt_modules = sorted(name for name in sys.modules if name.split(".", 1)[0] in QT_ROOTS)
        if qt_modules:
            raise AssertionError(f"Qt modules loaded: {qt_modules}")
        return {
            "factory": spec,
            "status": "pass",
            "seconds": round(time.monotonic() - started, 3),
            "qt_modules": qt_modules,
            "sizes": [[1200, 800], [800, 600]],
            "parity_verified": False,
            "tooltips_verified": False,
        }
    finally:
        try:
            close = getattr(app, "close", None)
            if callable(close):
                close()
        finally:
            logging.getLogger().removeHandler(handler)
            sys.meta_path.remove(blocker)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", required=True)
    parser.add_argument("--screenshot")
    args = parser.parse_args(argv)
    try:
        result = check_factory(args.factory, args.screenshot)
    except Exception as error:
        result = {
            "factory": args.factory,
            "status": "fail",
            "error": str(error),
            "error_type": type(error).__name__,
            "traceback": traceback.format_exc(),
        }
    print(json.dumps(result))
    return int(result["status"] != "pass")


if __name__ == "__main__":
    raise SystemExit(main())
