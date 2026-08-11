"""Serve the browser build, and assemble what it needs.

Two jobs, both small.

It **packs the engine**: chimol's Python, its eighteen WGSL shaders and the
baked glyph atlas go into one ``chimol.zip`` that the page unpacks onto
Pyodide's filesystem. A wheel would be tidier and needs a build step; a zip
needs none, and this is the development loader.

It **serves with the right headers**. Pyodide wants cross-origin isolation
(``COOP``/``COEP``) for its threading, and a browser will not enable WebGPU on a
page it considers insecure -- so ``localhost`` is the only origin this is useful
from. Getting the headers wrong produces a confusing load failure rather than a
clear one, which is the only reason this is a script instead of
``python -m http.server``.

Use
---
    python -m chisurf.plugins.chimol.chimol.web.serve

then open http://localhost:8765/. Pass ``--pyodide DIR`` to serve a local
Pyodide instead of fetching one.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import pathlib
import shutil
import zipfile

__all__ = ["pack", "serve", "WEB_DIR", "PACKAGE_DIR"]

#: This directory: the page, the loader and the demo.
WEB_DIR = pathlib.Path(__file__).resolve().parent

#: The package that gets zipped up.
PACKAGE_DIR = WEB_DIR.parent

#: What goes into the archive. Python, shaders, and the atlas -- and nothing
#: else, because everything else in the package is either the Qt host or test
#: data, and a browser that has to download a PDB file to draw a panel has been
#: mis-assembled.
INCLUDE_SUFFIXES = (".py", ".wgsl", ".json", ".png", ".pdb")

#: Directories not worth shipping to a browser.
EXCLUDE_DIRS = ("__pycache__", "app", "testing", "test")


def pack(destination: pathlib.Path | None = None) -> pathlib.Path:
    """Write ``chimol.zip`` for the page to unpack.

    Parameters
    ----------
    destination : pathlib.Path, optional
        Where to write. Defaults to beside the page.

    Returns
    -------
    pathlib.Path
        The archive.
    """
    destination = pathlib.Path(destination or WEB_DIR / "chimol.zip")
    root = PACKAGE_DIR
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in INCLUDE_SUFFIXES:
                continue
            relative = path.relative_to(root.parent)
            if any(part in EXCLUDE_DIRS for part in relative.parts):
                continue
            archive.write(path, str(relative))
    return destination


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Static files, cross-origin isolated."""

    #: Whether to send the cross-origin-isolation headers.
    #:
    #: Off by default, and that is a real trade rather than an oversight.
    #: ``Cross-Origin-Embedder-Policy: require-corp`` is what Pyodide's
    #: *threading* needs, and it also **blocks every cross-origin fetch that
    #: does not opt in** -- including the CDN this page loads Pyodide from. So
    #: turning it on without also serving Pyodide locally produces a page that
    #: fails to load its interpreter, which reads as a broken build rather than
    #: as a header choice. ``--isolate`` turns it on for a local Pyodide.
    isolate = False

    def end_headers(self) -> None:
        """Send no-store, and cross-origin isolation only when asked."""
        if self.isolate:
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args) -> None:
        """Quieter than the default, which logs every asset."""
        if "404" in (fmt % args):
            super().log_message(fmt, *args)


def serve(port: int = 8765, pyodide: pathlib.Path | None = None,
          open_browser: bool = False) -> None:
    """Pack the engine and serve the page.

    Parameters
    ----------
    port : int
        Port to listen on.
    pyodide : pathlib.Path, optional
        A local Pyodide distribution to copy in beside the page.
    """
    archive = pack()
    print(f"packed {archive.name}: {archive.stat().st_size / 1024:.0f} KB")

    if pyodide is not None:
        target = WEB_DIR / "pyodide"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(pyodide, target)
        print(f"copied Pyodide from {pyodide}")

    handler = functools.partial(_Handler, directory=str(WEB_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://localhost:{port}/"
    print(f"serving {WEB_DIR} at {url}  (ctrl-c to stop)")
    if open_browser:
        import threading
        import webbrowser

        # After the server is listening, or the browser races it to a refused
        # connection and shows its own error page instead of chimol.
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--pyodide", type=pathlib.Path, default=None,
        help="a local Pyodide distribution to serve alongside the page",
    )
    parser.add_argument(
        "--pack-only", action="store_true",
        help="write chimol.zip and exit",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="do not open a browser",
    )
    parser.add_argument(
        "--isolate", action="store_true",
        help="send COOP/COEP; needs --pyodide, since it blocks the CDN",
    )
    args = parser.parse_args(argv)
    if args.pack_only:
        archive = pack()
        print(archive)
        return
    _Handler.isolate = bool(args.isolate)
    serve(port=args.port, pyodide=args.pyodide,
          open_browser=not args.no_open)


if __name__ == "__main__":  # pragma: no cover - a dev server
    main()
