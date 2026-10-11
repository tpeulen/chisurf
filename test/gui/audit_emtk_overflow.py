"""Mechanical audit of every plugin that ships both a Qt tool and an emtk app.

For each plugin whose ``manifest.json`` declares ``entrypoints.gui`` *and*
``entrypoints.emtk`` (``cookiecutter`` excluded, as ``test_emtk_preview_gate`` does):

1. build the emtk app from its entrypoint, no arguments;
2. draw 3 frames through ``app.draw`` with a ``RecordingPainter`` at 1200x800 and 800x600;
3. overflow check -- content drawn below the viewport with no scrollbar track
   (``fill_rect(x, y, 8.0, h)``, ``h > 40``) anywhere in the frame is the defect
   the ``setup`` panel had (rows laid out to y=13501 in an 800 px window);
   ``end_child`` / ``end`` are spied so non-scrollable children and windows whose
   content outgrew them are listed as well;
4. drag-only numeric fields -- ``im.input_int(`` / ``im.input_float(`` calls in the
   plugin's GUI sources that are not inside a typed-field helper (the fixed pattern
   is ``acq/gui/app.py::_typed_field``);
5. click smoke -- ``imaging_emtk.testing.Driver(app, (1200, 800)).draw(3)``.

Every plugin runs in its own interpreter (a crash, hang or GL context cannot take
the rest down) with ``CHISURF_SETTINGS_DIR`` pointed at a scratch directory.

Command line::

    QT_QPA_PLATFORM=offscreen PYTHONPATH="modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \\
        python -m test.gui.audit_emtk_overflow --out audit.json [--only setup acq]

Writes ``audit.json`` (one row per plugin) and ``audit.md`` (ranked, worst first).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = pathlib.Path(__file__).resolve().parents[2]
#: Local sources that are not installed packages; added to the path of this process and the workers.
_LOCAL_PATHS = [
    str(REPO / p)
    for p in (
        "modules/chimol",
        "modules/mmfdb/src",
        "modules/chinet",
        "modules/imp-tricks/src",
        ".",
    )
]
for _p in reversed(_LOCAL_PATHS):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ["PYTHONPATH"] = os.pathsep.join(
    _LOCAL_PATHS + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
)
SIZES = ((1200, 800), (800, 600))
RENDER_GUARD_S = 20
PLUGIN_TIMEOUT_S = 150
SCROLLBAR_MIN_H = 40.0


# --------------------------------------------------------------------------- #
# enumeration
# --------------------------------------------------------------------------- #
def dual_plugins() -> list[dict]:
    """Every plugin with both entrypoints: ``{id, emtk, gui, dir}``, sorted by id."""
    found = {}
    for path in (REPO / "chisurf" / "plugins").rglob("manifest.json"):
        if "cookiecutter" in str(path):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not data.get("id"):
            continue
        entry = data.get("entrypoints") or {}
        if entry.get("gui") and entry.get("emtk"):
            found[data["id"]] = {
                "id": data["id"],
                "emtk": entry["emtk"],
                "gui": entry["gui"],
                "dir": str(path.parent),
            }
    return [found[k] for k in sorted(found)]


# --------------------------------------------------------------------------- #
# static scan: drag-only numeric fields
# --------------------------------------------------------------------------- #
_NUMERIC_CALLS = {"input_int", "input_float"}


def _gui_sources(plugin: dict) -> list[pathlib.Path]:
    """The plugin's ``gui/**/*.py`` plus the module the emtk entrypoint lives in."""
    root = pathlib.Path(plugin["dir"])
    files = set((root / "gui").rglob("*.py")) if (root / "gui").is_dir() else set()
    module = plugin["emtk"].split(":", 1)[0]
    entry_file = REPO / (module.replace(".", "/") + ".py")
    if entry_file.is_file():
        files.add(entry_file)

    def inside(f: pathlib.Path) -> bool:
        try:
            return "/test" not in str(f.relative_to(root))
        except ValueError:  # entry module outside the plugin dir (shared app)
            return True

    return sorted(f for f in files if inside(f))


def drag_only_fields(plugin: dict) -> tuple[int, list[str]]:
    """Count ``im.input_int(``/``im.input_float(`` calls outside a ``*typed*`` helper."""
    hits: list[str] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self, path):
            self.path = path
            self.stack: list[str] = []

        def _func(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_FunctionDef = visit_AsyncFunctionDef = _func

        def visit_Call(self, node):
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr in _NUMERIC_CALLS
                and isinstance(f.value, ast.Name)
                and f.value.id == "im"
                and not any("typed" in name for name in self.stack)
            ):
                hits.append(f"{self.path}:{node.lineno}")
            self.generic_visit(node)

    for path in _gui_sources(plugin):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        Visitor(str(path.relative_to(REPO))).visit(tree)
    return len(hits), hits


# --------------------------------------------------------------------------- #
# worker: runs inside the per-plugin interpreter
# --------------------------------------------------------------------------- #
class _Timeout(Exception):
    pass


def _alarm(_signum, _frame):
    raise _Timeout(f"render exceeded {RENDER_GUARD_S} s")


def _tail(exc: BaseException, lines: int = 6) -> str:
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return "\n".join(text.strip().splitlines()[-lines:])


class _Spy:
    """Wraps ``Context.end_child`` / ``Context.end`` to record what outgrew its box."""

    def __init__(self):
        self.children: list[dict] = []
        self.windows: list[dict] = []

    def install(self):
        from emtk import im_core

        ctx = im_core.Context
        orig_end_child, orig_end = ctx.end_child, ctx.end
        spy = self

        def end_child(this, *args, **kwargs):
            try:
                entry = this._child[-1]
                box = entry[1]
                scrollable = entry[6] if len(entry) > 6 else True
                content_h = float(this.layout.content_height())
                if content_h > float(box[3]) + 1.0:
                    spy.children.append(
                        {
                            "box": [round(float(v), 1) for v in box],
                            "content_h": round(content_h, 1),
                            "scrollable": bool(scrollable),
                        }
                    )
            except Exception:  # noqa: BLE001 -- a spy must never change behaviour
                pass
            return orig_end_child(this, *args, **kwargs)

        def end(this, *args, **kwargs):
            try:
                if this._window_stack:
                    window = this._window_stack[-1]
                    content_h = float(this.layout.content_height())
                    box_h = float(window.box[3])
                    if content_h > box_h + 1.0 and not getattr(window, "auto_resize", False):
                        spy.windows.append(
                            {
                                "name": str(getattr(window, "name", "?")),
                                "box_h": round(box_h, 1),
                                "content_h": round(content_h, 1),
                            }
                        )
            except Exception:  # noqa: BLE001
                pass
            return orig_end(this, *args, **kwargs)

        ctx.end_child, ctx.end = end_child, end

    def reset(self):
        self.children.clear()
        self.windows.clear()


def _measure(painter, size) -> dict:
    _w, h = size
    ys = [float(t[1]) for t in painter.texts]
    bars = [
        c
        for c in painter.calls
        if c[0] == "fill_rect" and abs(float(c[3]) - 8.0) < 1e-6 and float(c[4]) > SCROLLBAR_MIN_H
    ]
    max_y = max(ys) if ys else 0.0
    return {
        "max_text_y": round(max_y, 1),
        "viewport_h": h,
        "has_scrollbar": bool(bars),
        "painted_strings": len(painter.strings),
        "overflow_no_scrollbar": bool(max_y > h and not bars),
    }


def run_one(plugin_id: str) -> dict:
    """Audit one plugin in this interpreter; returns its row (minus the static scan)."""
    plugin = next(p for p in dual_plugins() if p["id"] == plugin_id)
    row: dict = {"id": plugin_id, "instantiate_ok": False, "error": None}
    errors: list[str] = []
    signal.signal(signal.SIGALRM, _alarm)
    spy = _Spy()
    app = None
    try:
        from emtk.testing import RecordingPainter

        spy.install()
        try:
            from chisurf.emtk.i18n import install

            install()
        except Exception:  # noqa: BLE001 -- the parity harness installs it; absence is not the plugin's fault
            pass
        try:
            from chisurf.core.plugin.registry import _DefaultLoader

            signal.alarm(RENDER_GUARD_S * 2)
            factory = _DefaultLoader().load(plugin["emtk"])
            app = factory()
            signal.alarm(0)
            row["instantiate_ok"] = True
        except BaseException as exc:  # noqa: BLE001
            signal.alarm(0)
            row["error"] = f"instantiate: {_tail(exc)}"
            return row

        for size in SIZES:
            tag = str(size[0])
            spy.reset()
            try:
                signal.alarm(RENDER_GUARD_S)
                painter = None
                for _ in range(3):
                    painter = RecordingPainter()
                    app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
                signal.alarm(0)
                m = _measure(painter, size)
                row[f"render_ok_{tag}"] = True
                row[f"max_text_y_{tag}"] = m["max_text_y"]
                row[f"scrollbar_{tag}"] = m["has_scrollbar"]
                row[f"painted_strings_{tag}"] = m["painted_strings"]
                row[f"overflow_{tag}"] = m["overflow_no_scrollbar"]
                # last frame only: the spy saw 3 frames, keep the distinct boxes
                row[f"clipped_children_{tag}"] = _dedupe(
                    [c for c in spy.children if not c["scrollable"]]
                )
                row[f"window_overflow_{tag}"] = _dedupe(spy.windows)
            except BaseException as exc:  # noqa: BLE001
                signal.alarm(0)
                row[f"render_ok_{tag}"] = False
                errors.append(f"render {size[0]}x{size[1]}: {_tail(exc)}")

        try:
            from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

            signal.alarm(RENDER_GUARD_S)
            Driver(app, (1200, 800)).draw(3)
            signal.alarm(0)
            row["click_smoke_ok"] = True
        except BaseException as exc:  # noqa: BLE001
            signal.alarm(0)
            row["click_smoke_ok"] = False
            errors.append(f"click smoke: {_tail(exc)}")
    finally:
        signal.alarm(0)
        if app is not None and hasattr(app, "close"):
            try:
                app.close()
            except BaseException as exc:  # noqa: BLE001
                errors.append(f"close: {_tail(exc, 3)}")
    if errors:
        row["error"] = "\n---\n".join(errors)
    return row


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for item in items:
        key = json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out[:10]


# --------------------------------------------------------------------------- #
# driver: one subprocess per plugin
# --------------------------------------------------------------------------- #
def _spawn(plugin_id: str, settings_dir: str) -> dict:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", CHISURF_SETTINGS_DIR=settings_dir)
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as fh:
        result_path = fh.name
    cmd = [
        sys.executable,
        "-m",
        "test.gui.audit_emtk_overflow",
        "--worker",
        plugin_id,
        "--result",
        result_path,
    ]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=PLUGIN_TIMEOUT_S
        )
        text = pathlib.Path(result_path).read_text() if os.path.getsize(result_path) else ""
        if text:
            row = json.loads(text)
        else:
            tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-8:])
            row = {
                "id": plugin_id,
                "instantiate_ok": False,
                "error": f"worker exited {proc.returncode} without a result:\n{tail}",
            }
    except subprocess.TimeoutExpired:
        row = {
            "id": plugin_id,
            "instantiate_ok": False,
            "error": f"worker timed out after {PLUGIN_TIMEOUT_S} s",
        }
    finally:
        try:
            os.unlink(result_path)
        except OSError:
            pass
    row["seconds"] = round(time.monotonic() - t0, 1)
    return row


def _finalise(row: dict, plugin: dict) -> dict:
    n, where = drag_only_fields(plugin)
    full = {
        "id": row["id"],
        "instantiate_ok": bool(row.get("instantiate_ok")),
        "render_ok_1200": row.get("render_ok_1200", False),
        "render_ok_800": row.get("render_ok_800", False),
        "max_text_y_1200": row.get("max_text_y_1200"),
        "max_text_y_800": row.get("max_text_y_800"),
        "scrollbar_1200": row.get("scrollbar_1200"),
        "scrollbar_800": row.get("scrollbar_800"),
        "overflow_no_scrollbar": bool(row.get("overflow_1200") or row.get("overflow_800")),
        "overflow_sizes": [s for s in ("1200", "800") if row.get(f"overflow_{s}")],
        "drag_only_fields": n,
        "drag_only_where": where,
        "click_smoke_ok": row.get("click_smoke_ok", False),
        "painted_strings_1200": row.get("painted_strings_1200"),
        "painted_strings_800": row.get("painted_strings_800"),
        "clipped_children_800": row.get("clipped_children_800", []),
        "window_overflow_800": row.get("window_overflow_800", []),
        "seconds": row.get("seconds"),
        "error": row.get("error"),
    }
    return full


def _severity(r: dict) -> tuple:
    render_fail = r["instantiate_ok"] and not (r["render_ok_1200"] and r["render_ok_800"])
    return (
        0 if r["overflow_no_scrollbar"] else 1,
        0 if not r["instantiate_ok"] else 1,
        0 if render_fail else 1,
        -r["drag_only_fields"],
        0 if (r["instantiate_ok"] and not r["click_smoke_ok"]) else 1,
        -(r["max_text_y_800"] or 0),
        r["id"],
    )


def summary(rows: list[dict]) -> dict:
    inst_fail = [r for r in rows if not r["instantiate_ok"]]
    render_fail = [
        r for r in rows if r["instantiate_ok"] and not (r["render_ok_1200"] and r["render_ok_800"])
    ]
    overflow = [r for r in rows if r["overflow_no_scrollbar"]]
    drag = [r for r in rows if r["drag_only_fields"]]
    click = [r for r in rows if r["instantiate_ok"] and not r["click_smoke_ok"]]
    bad = {r["id"] for r in inst_fail + render_fail + overflow + drag + click}
    return {
        "total": len(rows),
        "ok": len(rows) - len(bad),
        "overflow_no_scrollbar": len(overflow),
        "instantiate_fail": len(inst_fail),
        "render_fail": len(render_fail),
        "drag_only_affected": len(drag),
        "drag_only_calls": sum(r["drag_only_fields"] for r in rows),
        "click_fail": len(click),
    }


def _first_line(err: str | None) -> str:
    if not err:
        return ""
    lines = [ln.strip() for ln in err.splitlines() if ln.strip()]
    msg = lines[-1] if lines else ""
    return msg.replace("|", "\\|")[:140]


def _win(r: dict) -> str:
    """Windows whose laid-out content outgrew their box at 800x600 (a stricter, per-window signal)."""
    return ", ".join(
        f"{w['name'][:24]} {w['content_h']:.0f}>{w['box_h']:.0f}"
        for w in r["window_overflow_800"][:2]
    )


def write_markdown(rows: list[dict], path: pathlib.Path) -> None:
    s = summary(rows)
    out = [
        "# emtk all-plugin audit",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `test/gui/audit_emtk_overflow.py`.",
        "",
        f"- dual Qt/emtk plugins: **{s['total']}**, clean: **{s['ok']}**",
        f"- overflow without scrollbar: **{s['overflow_no_scrollbar']}**",
        f"- instantiate failures: **{s['instantiate_fail']}**",
        f"- render failures: **{s['render_fail']}**",
        f"- drag-only numeric fields: **{s['drag_only_affected']}** plugins, "
        f"{s['drag_only_calls']} call sites",
        f"- click-smoke failures: **{s['click_fail']}**",
        "",
        "Ranking: overflow-no-scrollbar > instantiate/render failure > drag-only fields > click failure.",
        "`max y` is the top of the lowest drawn string; viewport is 800 / 600 px high. "
        "`win ovf` lists windows whose content outgrew them without a scroll child (spy on `Context.end`).",
        "",
        "| # | plugin | overflow | inst | render 1200/800 | max y 1200 | max y 800 | sb 1200/800 "
        "| win ovf 800 | drag-only | click | strings | note |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    yn = {True: "✓", False: "✗", None: "–"}
    for i, r in enumerate(sorted(rows, key=_severity), 1):
        note = _first_line(r["error"])
        if not note and r["clipped_children_800"]:
            c = r["clipped_children_800"][0]
            note = f"non-scrollable child h={c['box'][3]} content={c['content_h']}"
        out.append(
            f"| {i} | `{r['id']}` | {'**YES** ' + '/'.join(r['overflow_sizes']) if r['overflow_no_scrollbar'] else ''} "
            f"| {yn[r['instantiate_ok']]} | {yn[r['render_ok_1200']]}/{yn[r['render_ok_800']]} "
            f"| {r['max_text_y_1200'] if r['max_text_y_1200'] is not None else '–'} "
            f"| {r['max_text_y_800'] if r['max_text_y_800'] is not None else '–'} "
            f"| {yn[r['scrollbar_1200']]}/{yn[r['scrollbar_800']]} "
            f"| {_win(r)} | {r['drag_only_fields'] or ''} | {yn[r['click_smoke_ok']] if r['instantiate_ok'] else '–'} "
            f"| {r['painted_strings_1200'] if r['painted_strings_1200'] is not None else '–'} | {note} |"
        )
    errs = [r for r in rows if r["error"]]
    if errs:
        out += ["", "## Error tails", ""]
        for r in sorted(errs, key=_severity):
            out += [f"### `{r['id']}`", "", "```", r["error"], "```", ""]
    drags = [r for r in rows if r["drag_only_where"]]
    if drags:
        out += ["", "## Drag-only call sites", ""]
        for r in sorted(drags, key=lambda r: -r["drag_only_fields"]):
            out.append(
                f"- `{r['id']}` ({r['drag_only_fields']}): " + ", ".join(r["drag_only_where"])
            )
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=pathlib.Path, help="JSON output; the .md goes beside it")
    parser.add_argument("--only", nargs="*", help="audit just these plugin ids")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--result", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.worker:
        try:
            row = run_one(args.worker)
        except BaseException as exc:  # noqa: BLE001
            row = {"id": args.worker, "instantiate_ok": False, "error": f"worker: {_tail(exc)}"}
        pathlib.Path(args.result).write_text(json.dumps(row, default=str), encoding="utf-8")
        sys.stdout.flush()
        os._exit(0)  # skip interpreter teardown: some native extensions crash on exit

    if not args.out:
        parser.error("--out is required")
    plugins = dual_plugins()
    if args.only:
        plugins = [p for p in plugins if p["id"] in set(args.only)]
    settings_dir = tempfile.mkdtemp(prefix="emtk_audit_settings_")
    rows = []
    for i, plugin in enumerate(plugins, 1):
        row = _finalise(_spawn(plugin["id"], settings_dir), plugin)
        rows.append(row)
        flag = "OVERFLOW" if row["overflow_no_scrollbar"] else ("FAIL" if row["error"] else "ok")
        print(
            f"[{i:3d}/{len(plugins)}] {plugin['id']:<28} {flag:<8} "
            f"y800={row['max_text_y_800']} drag={row['drag_only_fields']} {row['seconds']}s",
            flush=True,
        )
        args.out.write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    args.out.write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    write_markdown(rows, args.out.with_suffix(".md"))
    print(json.dumps(summary(rows), indent=1))
    print(
        f"settings written by plugins (scratch): {settings_dir} "
        f"-> {sorted(p.name for p in pathlib.Path(settings_dir).rglob('*'))[:20]}"
    )
    return 0


def _synthetic_app(scrolling: bool):
    """A window of 300 rows: drawn straight into the window (the defect) or into a child."""
    from emtk import im
    from emtk.app import ImApp

    def gui():
        vp = im.get_main_viewport()
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("synthetic", flags=im.WindowFlags.NO_RESIZE):
            if scrolling:
                w, h = im.get_content_region_avail()
                im.begin_child("##body", (float(w), float(h)))
            for i in range(300):
                im.text(f"row {i}")
            if scrolling:
                im.end_child()
        im.end()

    return ImApp(gui)


def self_check() -> dict:
    """The detector flags the unscrolled window and passes the scrolled one (the setup defect, in miniature)."""
    from emtk.testing import RecordingPainter

    _Spy().install()
    out = {}
    for scrolling in (False, True):
        app = _synthetic_app(scrolling)
        for _ in range(3):
            painter = RecordingPainter()
            app.draw(painter, 0.0, 0.0, 800.0, 600.0)
        out["scrolling" if scrolling else "flat"] = _measure(painter, (800, 600))
    return out


def test_detector_flags_the_unscrolled_window():
    result = self_check()
    assert result["flat"]["overflow_no_scrollbar"], result
    assert not result["scrolling"]["overflow_no_scrollbar"], result
    assert result["scrolling"]["has_scrollbar"], result


def test_dual_plugins_are_enumerated():
    """Collectable smoke test: the enumeration finds the plugins the audit runs on."""
    ids = {p["id"] for p in dual_plugins()}
    assert "setup" in ids and "acq" in ids


if __name__ == "__main__":
    raise SystemExit(main())
