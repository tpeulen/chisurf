"""Before/after evidence for a Qt -> emtk plugin port, produced one way for every plugin.

The port reviewer cannot trust a claim ("all controls are there", "every control has
a tooltip") that the porter typed. This module *measures* those claims, writes them
to files a reviewer can diff, and is the only source of numbers allowed in a port
report.

Two halves, captured the same way
---------------------------------
``before``
    The legacy Qt widget of the plugin (``entrypoints.gui`` in its manifest), shown
    offscreen and grabbed. Capture this **before you change any code**: once the Qt
    widget is edited or removed the baseline is gone.
``after``
    The plugin's emtk app (``entrypoints.emtk``), drawn headlessly at the same
    sizes through ``app.draw(...)`` -- never ``app.gui()``, which skips the work
    hub apps do inside ``draw``.

Parity is judged on **control inventory, not pixels** (see ``migration_parity``): a
missing control is a blocker, a moved one is not.

Command line
------------
::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=. python -m test.gui.emtk_port_parity \\
        before <plugin_id> --out okf/plugins/emtk-ports/<plugin_id>
    QT_QPA_PLATFORM=offscreen PYTHONPATH=. python -m test.gui.emtk_port_parity \\
        after  <plugin_id> --out okf/plugins/emtk-ports/<plugin_id>
    PYTHONPATH=. python -m test.gui.emtk_port_parity \\
        compare <plugin_id> --out okf/plugins/emtk-ports/<plugin_id>

Files written to ``--out`` (all of them are committed with the port):

* ``before.png`` / ``after_1200x800.png`` / ``after_800x600.png`` -- screenshots.
* ``before.json`` / ``after.json`` -- control inventory (normalised text of every
  label, button and table cell) and, for ``after``, one row per interactive control
  with its tooltip (``controls_without_tooltip`` must be empty).
* ``compare.json`` -- ``lost`` (blocker), ``gained``, ``untooltipped``, and the
  Qt-free import check result.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import pathlib
import re
import subprocess
import sys
import typing

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = pathlib.Path(__file__).resolve().parents[2]

#: The two sizes every port is rendered at: a normal window and a narrow one.
SIZES = ((1200, 800), (800, 600))

#: emtk widget functions that are a control a user can operate. The recorder wraps
#: these so that a following ``set_item_tooltip`` can be attributed to the control.
_CONTROL_FUNCS = (
    "button", "small_button", "checkbox", "radio_button", "selectable", "combo",
    "input_text", "input_text_multiline", "input_float", "input_int", "input_double",
    "slider_float", "slider_int", "drag_float", "drag_int", "color_edit3",
    "color_edit4", "menu_item", "collapsing_header", "tree_node", "begin_tab_item",
    "list_box", "input_scalar",
)


# --------------------------------------------------------------------------- #
# locating a plugin
# --------------------------------------------------------------------------- #
def manifest_of(plugin_id: str) -> dict:
    """Return the manifest dict of *plugin_id* (its ``id`` field)."""
    for path in sorted((REPO / "chisurf" / "plugins").rglob("manifest.json")):
        if "cookiecutter" in str(path):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("id") == plugin_id:
            return data
    raise KeyError(f"no plugin with manifest id {plugin_id!r}")


def _resolve(spec: str) -> typing.Any:
    module, _, attr = spec.partition(":")
    return getattr(importlib.import_module(module), attr)


def _is_pictogram(token: str) -> bool:
    """Whether *token* is only emoji/symbol marks (``📁``, ``ℹ️``), not a name like ``χ²``."""
    import unicodedata

    return bool(token) and all(
        ch == "\u2139" or unicodedata.category(ch) in ("So", "Sk", "Sm", "Cf", "Mn")
        for ch in token
    )


def normalize(text: str) -> str:
    """Compare-key of a control's text: no markup, accelerators, ellipsis, emoji, case or space.

    ``&Open...`` and ``Open…`` are the same control, and so are ``📁 Folder`` and
    ``Folder``; ``χ² min`` keeps its ``χ²`` (a letter, not a pictogram).
    """
    out = re.sub(r"<[^>]*>", "", str(text)).strip()
    out = out.replace("&", "").replace("...", "").replace("\u2026", "")
    head, _, rest = out.partition(" ")
    if rest and _is_pictogram(head):
        out = rest
    elif _is_pictogram(out):
        out = ""
    out = re.sub(r"[:\s]+", "", out)
    return out.lower()


# --------------------------------------------------------------------------- #
# the emtk half
# --------------------------------------------------------------------------- #
class ControlRecorder:
    """Records every control an emtk app draws and the tooltip that follows it.

    A tooltip belongs to the *most recent* control, which is how every port in this
    repository writes it (``im.button(...)`` then ``im.set_item_tooltip(...)``).
    Controls drawn by ``emtk.view_form`` (spec-driven) call the same functions, so
    they are recorded too.
    """

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.texts: set[str] = set()

    # a control was drawn
    def control(self, kind: str, label: typing.Any) -> None:
        label = str(label) if isinstance(label, str) else ""
        shown = label.split("##", 1)[0]
        self.rows.append({"kind": kind, "label": shown, "id": label, "tooltip": ""})
        if shown:
            self.texts.add(normalize(shown))

    # a tooltip was set
    def tooltip(self, text: typing.Any) -> None:
        if self.rows and not self.rows[-1]["tooltip"]:
            self.rows[-1]["tooltip"] = str(text)

    @contextlib.contextmanager
    def installed(self):
        """Patch ``emtk.im`` / ``emtk.im_widgets`` so the app's calls are recorded."""
        from emtk import im, im_widgets

        undo: list[tuple[typing.Any, str, typing.Any]] = []
        for module in (im, im_widgets):
            for name in _CONTROL_FUNCS:
                original = getattr(module, name, None)
                if original is None:
                    continue
                undo.append((module, name, original))
                setattr(module, name, self._wrap(name, original))
            original = getattr(module, "set_item_tooltip", None)
            if original is not None:
                undo.append((module, "set_item_tooltip", original))
                setattr(module, "set_item_tooltip", self._tip(original))
        try:
            yield self
        finally:
            for module, name, original in reversed(undo):
                setattr(module, name, original)

    def _wrap(self, kind, func):
        recorder = self

        def wrapper(*args, **kwargs):
            label = args[0] if args else kwargs.get("label", "")
            recorder.control(kind, label)
            return func(*args, **kwargs)

        wrapper.__wrapped__ = func
        return wrapper

    def _tip(self, func):
        recorder = self

        def wrapper(text, *args, **kwargs):
            recorder.tooltip(text)
            return func(text, *args, **kwargs)

        wrapper.__wrapped__ = func
        return wrapper


def build_emtk_app(plugin_id: str) -> typing.Any:
    """Construct the plugin's emtk app from ``entrypoints.emtk`` (no Qt host, no state)."""
    spec = manifest_of(plugin_id).get("entrypoints", {}).get("emtk")
    if not spec:
        raise ValueError(f"{plugin_id}: manifest has no entrypoints.emtk")
    from chisurf.emtk.i18n import install

    install()
    return _resolve(spec)()


def draw_app(app: typing.Any, size: tuple[int, int], frames: int = 3):
    """Draw *app* ``frames`` times at *size* through ``app.draw``; return the last painter.

    The first frames open windows and settle layout; the last one is what a
    screenshot means.
    """
    from emtk.testing import PixelPainter

    width, height = size
    painter = None
    for _ in range(max(1, frames)):
        painter = PixelPainter(width, height)
        app.draw(painter, 0.0, 0.0, float(width), float(height))
    return painter


def emtk_inventory(app: typing.Any, size: tuple[int, int] = SIZES[0]) -> dict:
    """Draw *app* once and list what is on screen.

    ``controls`` is the union of normalised control labels and every string the app
    drew (labels, table cells, headings); ``interactive`` has one row per control
    with its tooltip; ``controls_without_tooltip`` is the list a reviewer checks is
    empty.
    """
    from emtk.testing import PixelPainter, RecordingPainter

    recorder = ControlRecorder()
    with recorder.installed():
        # frames 1-2 let windows open and layout settle; record on the settled frames
        for _ in range(3):
            recorder.rows.clear()
            painter = RecordingPainter()
            app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
    controls = set(recorder.texts) | {normalize(s) for s in painter.strings}
    controls.discard("")
    rows = [r for r in recorder.rows if r["label"]]
    return {
        "size": list(size),
        "controls": sorted(controls),
        "interactive": rows,
        "controls_without_tooltip": sorted(
            {f'{r["kind"]}: {r["label"]}' for r in rows if not r["tooltip"]}
        ),
    }


def emtk_screenshot(app: typing.Any, path: pathlib.Path, size: tuple[int, int]) -> pathlib.Path:
    """Render *app* to a PNG at *size*."""
    from emtk import testing

    painter = draw_app(app, size)
    path.write_bytes(testing.png_encode(painter.width, painter.height, painter.px))
    return path


def qt_free(plugin_id: str) -> dict:
    """Import and draw the emtk app in a fresh interpreter that forbids Qt.

    Returns ``{"ok": bool, "output": str}``. This is the proof that the port's
    production path does not need Qt: any ``qtpy`` / ``PyQt`` / ``PySide`` import
    and any import of ``chisurf.gui`` fails it.
    """
    script = f"""
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'qtpy','PyQt5','PyQt6','PySide2','PySide6'}}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from test.gui.emtk_port_parity import build_emtk_app, draw_app
app = build_emtk_app({plugin_id!r})
draw_app(app, (1200, 800))
bad = sorted(m for m in sys.modules if m == 'chisurf.gui' or m.startswith('chisurf.gui.'))
assert not bad, 'chisurf.gui imported: ' + ', '.join(bad[:5])
print('QT-FREE OK')
"""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO, env=env, capture_output=True, text=True
    )
    return {"ok": done.returncode == 0, "output": (done.stdout + done.stderr)[-2000:]}


# --------------------------------------------------------------------------- #
# the Qt half
# --------------------------------------------------------------------------- #
def qt_before(plugin_id: str, out: pathlib.Path) -> dict:
    """Show the legacy Qt widget offscreen; write ``before.png`` and ``before.json``."""
    from qtpy import QtWidgets

    from test.gui import migration_parity as mp

    manifest = manifest_of(plugin_id)
    spec = manifest.get("entrypoints", {}).get("gui")
    if not spec:
        raise ValueError(f"{plugin_id}: manifest has no entrypoints.gui to capture")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widget_class = _resolve(spec)
    widget = widget_class()
    widget.resize(*SIZES[0])
    widget.show()
    for _ in range(20):
        app.processEvents()
    widget.grab().save(str(out / "before.png"))
    inventory = mp.control_inventory(widget)
    inventory["entrypoint"] = spec
    inventory["size"] = list(SIZES[0])
    inventory["controls"] = sorted({normalize(c) for c in inventory["controls"]} - {""})
    widget.close()
    (out / "before.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False))
    return inventory


# --------------------------------------------------------------------------- #
# compare
# --------------------------------------------------------------------------- #
def compare(plugin_id: str, out: pathlib.Path) -> dict:
    """Diff ``before.json`` against ``after.json`` and write ``compare.json``.

    A non-empty ``lost`` or ``untooltipped`` list, or a failed Qt-free check, means
    the port is not done. Each deliberate loss must be listed by the porter in the
    report's "Deliberate differences" table; this function only measures.
    """
    before = json.loads((out / "before.json").read_text())
    after = json.loads((out / "after.json").read_text())
    lost = sorted(set(before["controls"]) - set(after["controls"]))
    gained = sorted(set(after["controls"]) - set(before["controls"]))
    result = {
        "plugin": plugin_id,
        "lost": lost,
        "gained": gained,
        "untooltipped": after.get("controls_without_tooltip", []),
        "qt_free": after.get("qt_free", {}),
        "before_controls": len(before["controls"]),
        "after_controls": len(after["controls"]),
    }
    (out / "compare.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def after(plugin_id: str, out: pathlib.Path) -> dict:
    """Render the emtk app at both sizes; write screenshots, ``after.json``."""
    app = build_emtk_app(plugin_id)
    try:
        for size in SIZES:
            emtk_screenshot(app, out / f"after_{size[0]}x{size[1]}.png", size)
        inventory = emtk_inventory(app, SIZES[0])
        inventory["qt_free"] = qt_free(plugin_id)
    finally:
        close = getattr(app, "close", None)
        if callable(close):
            with contextlib.suppress(Exception):
                close()
    (out / "after.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False))
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("phase", choices=("before", "after", "compare"))
    parser.add_argument("plugin_id")
    parser.add_argument("--out", required=True, help="evidence directory (created)")
    args = parser.parse_args(argv)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.phase == "before":
        data = qt_before(args.plugin_id, out)
        print(f"before: {len(data['controls'])} controls -> {out}")
        return 0
    if args.phase == "after":
        data = after(args.plugin_id, out)
        print(
            f"after: {len(data['controls'])} controls, "
            f"{len(data['controls_without_tooltip'])} without tooltip, "
            f"qt-free={'yes' if data['qt_free']['ok'] else 'NO'} -> {out}"
        )
        return 0
    result = compare(args.plugin_id, out)
    print(json.dumps({k: result[k] for k in ("lost", "untooltipped")}, indent=2))
    print("qt-free:", result["qt_free"].get("ok"))
    blocked = bool(result["lost"] or result["untooltipped"] or not result["qt_free"].get("ok"))
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
