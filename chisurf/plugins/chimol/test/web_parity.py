"""A/B the browser against the desktop: every command, every control.

What this answers
-----------------
"chimol runs in a browser" is settled by a screenshot; *"chimol is fully
functional in a browser"* is not. The page draws a molecule and a panel, and so
does the desktop, and the difference between them -- which of the hundred-odd
commands behaves differently, which controls cannot be reached, which gestures
the page never delivers -- is invisible in both pictures.

So both halves run :mod:`chimol.testing.parity`, which is **engine code shipped
to the page**: the desktop imports it and the browser unpacks it from
``chimol.zip``. A comparison whose two halves are written twice compares the two
scripts as much as the two hosts, and the first thing to drift is the argument
some command is probed with.

The reference half
------------------
:class:`~chimol.hosts.native.app.ChimolApp` on the offscreen canvas -- chimol's own
toolkit-free desktop entry point, not the Qt plugin window. That is the
like-for-like comparison: both hosts are a canvas, a command layer and the
in-viewport chrome, and neither has a ``QPainter``. Judging the page against the
Qt widget would charge it for the two overlays that are still rasterised with
one (3-D labels and a traced frame), which the toolkit-free desktop host does
not have either.

Use
---
    python -m chisurf.plugins.chimol.test.web_parity

writes ``renders/web_parity/`` -- ``desktop.json``, ``browser.json``,
``report.md`` and a PNG of each host. ``--desktop-only`` skips the browser half,
which needs Playwright and a minute of Pyodide.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import socket
import subprocess
import sys
import time
from typing import Any, Optional

__all__ = [
    "OUT_DIR",
    "SIZE",
    "browser_report",
    "capture",
    "desktop_report",
    "render_report",
]

#: Where the A/B lands.
OUT_DIR = pathlib.Path(__file__).resolve().parent / "renders" / "web_parity"

#: The viewport both halves are measured at, in logical pixels. One size, or a
#: re-flowed panel is indistinguishable from a missing control.
SIZE = (1280, 860)

#: Chromium flags. ``--enable-unsafe-webgpu`` is what makes ``navigator.gpu``
#: exist in a headless build.
CHROMIUM_FLAGS = [
    "--enable-unsafe-webgpu",
    "--enable-features=Vulkan,WebGPU",
    "--enable-gpu",
    "--ignore-gpu-blocklist",
]

_PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]


def _demo_pdb() -> str:
    """The structure both halves open, so they compare the same molecule."""
    return str(pathlib.Path(__import__("chimol").__file__).resolve().parent / "data" / "demos" / "148l.pdb")


# -- the desktop half --------------------------------------------------------


def desktop_report(size: tuple[int, int] = SIZE) -> tuple[dict[str, Any], Any]:
    """Run the report against the toolkit-free desktop host.

    Parameters
    ----------
    size : tuple of int, optional
        Canvas size in logical pixels.

    Returns
    -------
    tuple
        ``(report, image)`` -- the image is whatever the offscreen canvas
        returns for one forced frame, or ``None`` if it returns nothing.
    """
    from chimol.hosts.native.app import ChimolApp
    from chimol.hosts.toolkit import HAS_QT
    from chimol.testing import parity

    if HAS_QT:
        # `MolView` is a real ``QWidget`` on any machine where Qt *imports*, and
        # a QWidget needs an application object before it can be constructed.
        # The browser takes `host.widget`'s stand-ins instead, which is the one
        # difference this line papers over -- and it papers over nothing that is
        # measured: the chrome, the commands and the scene are the same objects
        # either way. Run this with ``QT_QPA_PLATFORM=offscreen``.
        from qtpy import QtWidgets

        if QtWidgets.QApplication.instance() is None:
            QtWidgets.QApplication([])

    app = ChimolApp(size=size, backend="offscreen")
    pdb = _demo_pdb()

    def reload() -> None:
        """Rebuild the session after a destructive probe."""
        app.cmd.do(f"load {pdb}")
        app.cmd.do("as cartoon")

    reload()
    image = app.draw_frame()
    gui = app.renderer._internal_gui
    report = parity.report(
        gui=gui, cmd=app.cmd, host=app.renderer, reload=reload, size=size
    )
    report["role"] = "desktop"
    # After the probes the session is whatever the last one left; put it back
    # so the PNG beside the report is the molecule and not the debris.
    reload()
    image = app.draw_frame()
    app.close()
    return report, image


# -- the browser half --------------------------------------------------------


def _free_port() -> int:
    """Return a port nothing is listening on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def browser_report(
    size: tuple[int, int] = SIZE,
    out_dir: Optional[pathlib.Path] = None,
    timeout_ms: int = 600_000,
) -> tuple[dict[str, Any], Optional[pathlib.Path]]:
    """Run the same report inside a real page, on the browser's own WebGPU.

    Parameters
    ----------
    size : tuple of int, optional
        Viewport size in CSS pixels.
    out_dir : pathlib.Path, optional
        Where the screenshot goes.
    timeout_ms : int, optional
        How long to wait for the page to draw. Pyodide plus the probes is a
        minute or two.

    Returns
    -------
    tuple
        ``(report, screenshot_path)``.

    Raises
    ------
    RuntimeError
        If the page never reports a drawn frame; the page's own error is
        included, because a traceback that reaches the console is truncated and
        the useful line is the innermost one.
    """
    from playwright.sync_api import sync_playwright

    out_dir = pathlib.Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    shot = out_dir / "browser.png"

    port = _free_port()
    root = _PLUGIN_DIR.parents[2]
    server = subprocess.Popen(
        [sys.executable, "-m", "chimol.hosts.web.serve",
         "--port", str(port), "--no-open"],
        cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(200):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("the dev server did not start")

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=CHROMIUM_FLAGS)
            page = browser.new_page(
                viewport={"width": size[0], "height": size[1] + 28}
            )
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            if not page.evaluate("() => !!navigator.gpu"):
                browser.close()
                raise RuntimeError("this Chromium has no WebGPU")
            page.wait_for_function(
                "() => { const s = document.getElementById('status');"
                " return s && (s.textContent.includes('drawn')"
                " || s.textContent.includes('failed')); }",
                timeout=timeout_ms,
            )
            status = page.evaluate(
                "() => document.getElementById('status')?.textContent || ''"
            )
            if "drawn" not in status:
                failure = page.evaluate("() => globalThis.chimolError || ''")
                browser.close()
                raise RuntimeError(f"the page did not draw: {status}\n{failure}")
            page.screenshot(path=str(shot))
            raw = page.evaluate(
                "() => globalThis.chimolViewer.parity_report()",
            )
            browser.close()
    finally:
        server.kill()
        server.wait(timeout=10)

    report = json.loads(raw)
    report["role"] = "browser"
    if errors:
        report["page_errors"] = errors[:10]
    return report, shot


# -- the write-up ------------------------------------------------------------


def render_report(desktop: dict[str, Any], browser: dict[str, Any]) -> str:
    """Turn a comparison into something a person reads.

    Parameters
    ----------
    desktop, browser : dict
        Two :func:`chimol.testing.parity.report` results.

    Returns
    -------
    str
        Markdown.
    """
    from chimol.testing import parity

    diff = parity.compare(desktop, browser)
    probes = {p["name"]: p for p in desktop.get("probes", [])}
    ran = [p for p in probes.values() if p["outcome"] != "skipped"]
    lines = [
        "# chimol: the browser against the desktop",
        "",
        f"- backend: desktop `{desktop['backend']}`, browser `{browser['backend']}`",
        f"- commands registered: {len(desktop['commands'])} / "
        f"{len(browser['commands'])}",
        f"- commands probed: {len(ran)} "
        f"({len(probes) - len(ran)} skipped, see `parity.SKIP`)",
        f"- controls reachable: {len(desktop['chrome']['reachable'])} / "
        f"{len(browser['chrome']['reachable'])}",
        "",
        "## Verdict",
        "",
    ]
    totals = [
        ("commands missing in the browser", diff["commands_missing"]),
        ("commands the browser has and the desktop does not", diff["commands_extra"]),
        ("commands that behave differently", diff["probe_differences"]),
        ("controls the browser cannot reach", diff["chrome_missing"]),
        ("controls only the browser has", diff["chrome_extra"]),
        ("menus that differ", diff["menu_differences"]),
        ("host gestures the browser does not deliver", diff["host_missing"]),
    ]
    for title, items in totals:
        mark = "✅" if not items else "❌"
        lines.append(f"- {mark} {title}: **{len(items)}**")
    if diff["bands_differ"]:
        lines.append(f"- ❌ chrome bands that differ: **{len(diff['bands_differ'])}**")
    lines.append("")

    if diff["host_missing"]:
        lines += ["## Gestures the page never delivers", ""]
        why = dict(parity.HOST_FEATURES)
        for key in diff["host_missing"]:
            lines.append(f"- `{key}` — {why.get(key, '')}")
        lines.append("")

    if diff["commands_missing"]:
        lines += ["## Commands missing in the browser", "",
                  ", ".join(f"`{n}`" for n in diff["commands_missing"]), ""]

    if diff["probe_differences"]:
        lines += ["## Commands that behave differently", "",
                  "| command | desktop | browser |", "|---|---|---|"]
        for entry in diff["probe_differences"]:
            lines.append(
                f"| `{entry['line']}` | {entry['desktop'][:160]} "
                f"| {entry['browser'][:160]} |"
            )
        lines.append("")

    if diff["chrome_missing"]:
        lines += ["## Controls the browser cannot reach", "",
                  ", ".join(f"`{c}`" for c in diff["chrome_missing"]), ""]

    if diff["menu_differences"]:
        lines += ["## Menus", ""]
        for entry in diff["menu_differences"]:
            lines.append(
                f"- **{entry['title']}** — desktop only: "
                f"{', '.join(entry['desktop_only']) or '—'}; browser only: "
                f"{', '.join(entry['browser_only']) or '—'}"
            )
        lines.append("")

    if diff["bands_differ"]:
        lines += ["## Chrome bands (logical pixels)", "",
                  "| band | desktop | browser |", "|---|---:|---:|"]
        for band, (left, right) in diff["bands_differ"].items():
            lines.append(f"| {band} | {left} | {right} |")
        lines.append("")

    if browser.get("page_errors"):
        lines += ["## Errors raised in the page", ""]
        lines += [f"- {e}" for e in browser["page_errors"]]
        lines.append("")
    return "\n".join(lines)


def capture(
    out_dir: Optional[pathlib.Path] = None, desktop_only: bool = False
) -> dict[str, Any]:
    """Run both halves and write the A/B.

    Parameters
    ----------
    out_dir : pathlib.Path, optional
        Where to write. Defaults to :data:`OUT_DIR`.
    desktop_only : bool, optional
        Skip the browser half.

    Returns
    -------
    dict
        The comparison, as :func:`chimol.testing.parity.compare` returns it, or
        ``{}`` when only the desktop half ran.
    """
    out_dir = pathlib.Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    desktop, image = desktop_report()
    (out_dir / "desktop.json").write_text(json.dumps(desktop, indent=1))
    if image is not None:
        try:
            import numpy as np
            from PIL import Image

            Image.fromarray(np.asarray(image)[..., :3]).save(out_dir / "desktop.png")
        except Exception as exc:  # noqa: BLE001 - the report is the deliverable
            print(f"could not write the desktop PNG: {exc}")
    if desktop_only:
        print(f"desktop half written to {out_dir}")
        return {}

    browser, _shot = browser_report(out_dir=out_dir)
    (out_dir / "browser.json").write_text(json.dumps(browser, indent=1))

    from chimol.testing import parity

    text = render_report(desktop, browser)
    (out_dir / "report.md").write_text(text)
    print(text)
    return parity.compare(desktop, browser)


def main(argv: Optional[list[str]] = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=pathlib.Path, default=None)
    parser.add_argument("--desktop-only", action="store_true")
    args = parser.parse_args(argv)
    capture(args.out, desktop_only=args.desktop_only)


if __name__ == "__main__":  # pragma: no cover - a capture script
    main()
