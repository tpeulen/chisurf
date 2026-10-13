"""Capture genuine Qt plugin references, isolated in bounded subprocesses.

Run from the checkout with the GUI Python environment. Historical tool modules
are loaded without modifying the checkout; their relative imports/assets resolve
against the original package. Failed captures are recorded, never substituted
with screenshots of an EMTK adapter.
"""

from __future__ import annotations

import argparse
import faulthandler
import importlib
import io
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "okf/plugins/emtk-references"


def git(*args: str, repository: Path = ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=repository, text=True, timeout=15)


def native_source(module: str, repository: Path = ROOT) -> tuple[str, str]:
    def history(*args: str) -> str:
        return git(*args, repository=repository)

    path = module.replace(".", "/") + ".py"
    if (repository / module.replace(".", "/")).is_dir() or not history(
        "log", "-1", "--format=%H", "--", path
    ).strip():
        path = module.replace(".", "/") + "/__init__.py"
    # Help retains its original QTextBrowser-based HelpWidget alongside the
    # new adapter. The runtime child-widget check distinguishes the two.
    if module in {"chisurf.plugins.core.help.gui.tool", "chisurf.plugins.ndxplorer.window"}:
        return history("rev-parse", "HEAD").strip(), history("show", f"HEAD:{path}")
    # Prefer the first implementation: intermediate Qt shells can delegate to
    # declarative sections that have subsequently acquired EMTK hosts.
    revisions = [*reversed(history("log", "--format=%H", "--", path).splitlines()), "HEAD"]
    if os.environ.get("CHISURF_QT_REFERENCE_ORDER") == "latest":
        revisions = ["HEAD", *history("log", "--format=%H", "--", path).splitlines()]
    for revision in dict.fromkeys(revisions):
        try:
            source = history("show", f"{revision}:{path}")
        except subprocess.CalledProcessError:
            continue
        if module.endswith(".__init__") and '"plugin"' not in source and "'plugin'" not in source:
            continue
        # All existing adapter families explicitly reference EMTK or import app.
        if "emtk" not in source.lower() and "from .app import" not in source:
            return history("rev-parse", revision).strip(), source
    raise RuntimeError(f"No genuine Qt implementation in history for {module}")


def child(entrypoint: str, output: Path) -> None:
    faulthandler.enable()
    faulthandler.dump_traceback_later(
        max(0.05, float(os.environ.get("CHISURF_QT_REFERENCE_TIMEOUT", "40")) - 1)
    )
    # Older revisions predate CHISURF_SETTINGS_DIR. Bound their Path.home()
    # lookups to disposable storage without changing the process HOME variable.
    isolated_home = Path(os.environ["CHISURF_SETTINGS_DIR"]) / "home"
    isolated_home.mkdir()
    Path.home = classmethod(lambda cls: isolated_home)
    for companion_path in ("modules/chinet", "modules/imp-tricks/src", "modules/mmfdb/src"):
        if (ROOT / companion_path).exists():
            sys.path.insert(0, str(ROOT / companion_path))
    from qtpy.QtCore import QCoreApplication, QSettings, Qt
    from qtpy.QtWidgets import QApplication, QTabWidget, QWidget

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(isolated_home / "qt-settings"))
    app = QApplication.instance() or QApplication([])
    module_name, class_name = entrypoint.split(":")
    package_scope = module_name.partition(".")[0]
    source_repository = (
        ROOT if package_scope == "chisurf" else (ROOT / "modules" / package_scope).resolve()
    )
    revision, source = native_source(module_name, source_repository)
    print(f"source {revision}", flush=True)
    # Snapshot the entire historical first-party package: using a historical
    # tool with today's AutoForm would silently capture today's EMTK renderer.
    snapshot = Path(os.environ["CHISURF_SETTINGS_DIR"]) / "source"
    snapshot.mkdir()
    paths = [
        path
        for path in git(
            "ls-tree", "-r", "--name-only", revision, package_scope, repository=source_repository
        ).splitlines()
        if Path(path).suffix in {".py", ".json", ".ui", ".qss", ".md", ".svg", ".yaml", ".yml"}
    ]
    archive = subprocess.check_output(
        ["git", "archive", revision, *paths], cwd=source_repository, timeout=20
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as files:
        files.extractall(snapshot, filter="data")
    # Early category moves left some Qt .ui loaders pointing at the preceding
    # flat plugin directory. Alias assets to their same historical contents.
    aliases = []
    plugin_root = snapshot / "chisurf/plugins"
    for init in list(plugin_root.glob("*/*/__init__.py")):
        old_path = plugin_root / init.parent.name
        if not old_path.exists():
            old_path.symlink_to(init.parent, target_is_directory=True)
            aliases.append(str(old_path.relative_to(snapshot)))
    # This companion module is present in the checkout but absent from git;
    # historical experiment imports require it even for standalone calculators.
    companion = Path("chisurf/gui/widgets/experiments/pda")
    supplemented = []
    if not (snapshot / companion).exists() and (ROOT / companion).exists():
        shutil.copytree(
            ROOT / companion, snapshot / companion, ignore=shutil.ignore_patterns("__pycache__")
        )
        supplemented.append(str(companion))
    for companion in (
        Path("chisurf/core/support"),
        Path("chisurf/core/plugin"),
        Path("chisurf/gui/widgets/navigation.py"),
    ):
        if not (snapshot / companion).exists() and (ROOT / companion).exists():
            if (ROOT / companion).is_dir():
                shutil.copytree(
                    ROOT / companion,
                    snapshot / companion,
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
            else:
                (snapshot / companion).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / companion, snapshot / companion)
            supplemented.append(str(companion))
    (snapshot / "modules").symlink_to(ROOT / "modules", target_is_directory=True)
    for resource in ("docs", "okf"):
        if (ROOT / resource).exists():
            (snapshot / resource).symlink_to(ROOT / resource, target_is_directory=True)
            supplemented.append(resource)
    # Several otherwise native Qt tools already defaulted to EMTK plots before
    # their controls were ported. Select their supported native Qt plot backend
    # in scratch settings, keeping the strict no-EMTK-child check intact.
    defaults_path = snapshot / "chisurf/core/settings/settings_chisurf.yaml"
    if defaults_path.exists():
        import yaml

        defaults = yaml.safe_load(defaults_path.read_text()) or {}
        defaults.setdefault("gui", {}).setdefault("plot", {})["backend"] = "pyqtgraph"
        defaults["gui"]["plot"]["useOpenGL"] = False
        defaults["warn_missing_detector_setups"] = False
        for settings_path in (Path(os.environ["CHISURF_SETTINGS_DIR"]), isolated_home / ".chisurf"):
            settings_path.mkdir(parents=True, exist_ok=True)
            (settings_path / "settings_chisurf.yaml").write_text(yaml.safe_dump(defaults))
    sys.path.insert(0, str(snapshot))
    print("snapshot ready", flush=True)
    try:
        from chisurf.gui import chiplot
    except ImportError:
        pass  # Very early references predate chiplot entirely.
    else:
        chiplot.set_backend("pyqtgraph")
        chiplot.configure(useOpenGL=False)
    if class_name == "__legacy_window__":
        module = types.ModuleType("plugin")
        module.__file__ = str(snapshot / (module_name.replace(".", "/") + ".py"))
        module.__package__ = module_name.removesuffix(".__init__")
        exec(compile(source, module.__file__, "exec"), module.__dict__)
    else:
        module = importlib.import_module(module_name)
    print("module imported", flush=True)
    if class_name == "__legacy_window__":
        candidates = [value for value in module.__dict__.values() if isinstance(value, QWidget)]
        if not candidates:
            raise RuntimeError("Legacy script did not create a Qt widget")
        widget = candidates[-1]
    else:
        factory = getattr(module, class_name, None)
        if factory is None and class_name == "VvVhGFactorCalculator":
            factory = getattr(module, "JordiGFactorCalculator", None)
        if factory is None:
            raise AttributeError(f"Historical module has no factory {class_name}")
        if class_name in {"MMFDBWidget", "UserEditorWidget"}:
            # Exercise original client injection against a real isolated
            # database/RPC dispatcher rather than a missing external server.
            os.environ["MMFDB_DATABASE_URL"] = str(isolated_home / "reference.sqlite")
            from mmfdb.repository import MFDatabase

            from chisurf.core import settings as capture_settings
            from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

            capture_settings.cs_settings.setdefault("mmfdb", {})["default_user_id"] = (
                "qt-reference-admin"
            )
            client = MMFDBClient(inprocess=True)
            from mmfdb.admin.backend.password_services import hash_password

            capture_password = secrets.token_urlsafe(24)
            with MFDatabase(str(isolated_home / "reference.sqlite")) as database:
                if not any(
                    row.get("user_id") == "qt-reference-admin" for row in database.get_users()
                ):
                    database.add_user(
                        "qt-reference-admin",
                        "Isolated Qt capture account",
                        is_admin=1,
                        password_hash=hash_password(capture_password),
                        allow_passwordless_login=False,
                    )
            login = client.login(user_id="qt-reference-admin", password=capture_password)
            client.token = login.get("token")
            supplemented.append(
                "real isolated MMFDB dispatcher/database with temporary capture account"
            )
            if class_name == "MMFDBWidget":
                widget = factory(client=client)
            else:
                from chisurf.plugins.core.user_editor.gui.view_model import UserEditorViewModel

                widget = factory(view_model=UserEditorViewModel(client_factory=lambda: client))
        else:
            widget = factory()
        if class_name == "SMAcquisitionManager":
            # The manifest factory returns a real manager rather than its Qt
            # dock. Capture the manager's genuine control view, in default
            # simulation mode, without starting acquisition.
            widget = widget.acquisition_dock
    print("widget constructed", flush=True)
    if not isinstance(widget, QWidget):
        raise TypeError("Reference is not a Qt QWidget")
    document = os.environ.get("CHISURF_QT_REFERENCE_DOCUMENT")
    if document:
        if class_name != "HelpWidget":
            raise ValueError("Document fixture requires the original Qt HelpWidget")
        widget.navigate(Path(document))
    width = int(os.environ.get("CHISURF_QT_REFERENCE_WIDTH", "1000"))
    height = int(os.environ.get("CHISURF_QT_REFERENCE_HEIGHT", "700"))
    widget.resize(width, height)
    widget.show()
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    emtk_children = [
        f"{type(w).__module__}.{type(w).__name__}"
        for w in widget.findChildren(QWidget)
        if "emtk" in type(w).__module__.lower()
    ]
    if emtk_children:
        raise RuntimeError(
            "Qt window embeds EMTK; refusing misleading reference: "
            + ", ".join(sorted(set(emtk_children)))
        )
    image = output.with_suffix(".png")
    pixmap = widget.grab()
    pixels = pixmap.toImage()
    sampled_colors = {
        pixels.pixel(x, y)
        for x in range(0, pixels.width(), max(1, pixels.width() // 20))
        for y in range(0, pixels.height(), max(1, pixels.height() // 20))
    }
    if len(sampled_colors) < 2:
        raise RuntimeError(
            "Qt reference is a blank offscreen framebuffer; native display/GL context or initial data required"
        )
    if not pixmap.save(str(image)):
        raise RuntimeError("Qt image save failed")
    tab_pages = []
    if os.environ.get("CHISURF_QT_REFERENCE_TABS") == "1":
        for container_index, tabs in enumerate(widget.findChildren(QTabWidget)):
            original_index = tabs.currentIndex()
            for page_index in range(tabs.count()):
                tabs.setCurrentIndex(page_index)
                app.processEvents()
                page_image = output.with_name(
                    f"{output.stem}__tabs_{container_index}_{page_index}.png"
                )
                if not widget.grab().save(str(page_image)):
                    raise RuntimeError("Qt tab-page image save failed")
                tab_pages.append(
                    {
                        "image": page_image.name,
                        "container": container_index,
                        "page": page_index,
                        "label": tabs.tabText(page_index),
                    }
                )
            tabs.setCurrentIndex(original_index)
    controls = [
        {
            "class": type(w).__name__,
            "name": w.objectName(),
            "tooltip": w.toolTip(),
            "visible": w.isVisible(),
        }
        for w in widget.findChildren(QWidget)
    ]
    output.write_text(
        json.dumps(
            {
                "entrypoint": entrypoint,
                "source_revision": revision,
                "source_repository": str(source_repository),
                "status": "captured",
                "image": image.name,
                "width": widget.width(),
                "height": widget.height(),
                "checkout_supplements": supplemented,
                "historical_asset_aliases": aliases,
                "plot_backend": "pyqtgraph",
                "widget_class": type(widget).__name__,
                "document_fixture": document,
                "tab_pages": tab_pages,
                "controls": controls,
            },
            indent=2,
        )
    )
    # Some tools start Qt/server worker threads; process isolation owns cleanup.
    sys.stdout.flush()
    os._exit(0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", nargs="+", default=["all"])
    parser.add_argument("--jobs", type=int, choices=range(1, 4), default=3)
    parser.add_argument(
        "--prefer-latest",
        action="store_true",
        help="Try latest native Qt source instead of earliest",
    )
    parser.add_argument(
        "--tab-pages", action="store_true", help="Also screenshot each original Qt tab page"
    )
    parser.add_argument("--plugins", nargs="+", help="Plugin IDs to capture")
    parser.add_argument(
        "--document", type=Path, help="Open a rich-document fixture in original Qt HelpWidget"
    )
    parser.add_argument("--width", type=int, default=1000)
    parser.add_argument("--height", type=int, default=700)
    parser.add_argument(
        "--remaining", action="store_true", help="Retry failures/timeouts in canonical catalog"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=40)
    parser.add_argument("--child", nargs=2, metavar=("ENTRYPOINT", "METADATA"))
    args = parser.parse_args()
    if args.child:
        child(args.child[0], Path(args.child[1]))
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    cache = DEFAULT_OUTPUT / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    # Reuse read-only font discovery caches; macOS system_profiler can exceed
    # a GUI capture's timeout when every isolated child rediscovers all fonts.
    for user_cache in (Path.home() / ".matplotlib", Path.home() / ".cache/matplotlib"):
        if user_cache.exists():
            for font_cache in user_cache.glob("fontlist*.json"):
                if not (cache / font_cache.name).exists():
                    shutil.copy2(font_cache, cache / font_cache.name)
    tasks = []
    remaining = None
    if args.remaining:
        catalog = json.loads((DEFAULT_OUTPUT / "capture-index.json").read_text())
        remaining = {
            record["plugin"] for record in catalog if record["status"] in {"failed", "timeout"}
        }
    for manifest_path in sorted((ROOT / "chisurf/plugins").rglob("manifest.json")):
        relative = manifest_path.relative_to(ROOT / "chisurf/plugins")
        if any(
            part in {"test", "tests", "renders", "cookiecutter-chisurf-plugin"}
            for part in relative.parts
        ):
            continue
        if "all" not in args.groups and relative.parts[0] not in args.groups:
            continue
        manifest = json.loads(manifest_path.read_text())
        plugin_id = manifest.get("id", manifest_path.parent.name)
        if remaining is not None and plugin_id not in remaining:
            continue
        if args.plugins and plugin_id not in args.plugins:
            continue
        if plugin_id in ("code_editor", "help"):
            # Their Qt widgets were retired 2026-10-13; the Qt facts are frozen beside their tests
            # (qt_reference.json) and okf/plugins/emtk-ports/<id>/.
            continue
        entrypoint = manifest.get("entrypoints", {}).get("gui")
        if plugin_id == "tttr_splitter":
            entrypoint = "chisurf.plugins.tttr.tttr_splitter.wizard:PTUSplitter"
        elif plugin_id == "fcs_correlator":
            entrypoint = "chisurf.plugins.fcs.fcs_correlator.tool:FcsCorrelatorTool"
        elif plugin_id == "switch_user":
            # SwitchUserWidget is only a transient launcher whose showEvent
            # blocks in exec(); the original visible plugin is LoginDialog.
            entrypoint = "chisurf.gui:LoginDialog"
        if not entrypoint and manifest.get("entrypoints", {}).get("script"):
            init_path = manifest_path.parent / "__init__.py"
            if init_path.exists():
                entrypoint = (
                    ".".join(init_path.relative_to(ROOT).with_suffix("").parts)
                    + ":__legacy_window__"
                )
        output = args.output / ("__".join(relative.parts[:-1]) + ".json")
        tasks.append((plugin_id, entrypoint, output))

    def capture(task):
        plugin_id, entrypoint, output = task
        if not entrypoint:
            output.write_text(json.dumps({"status": "no_gui_entrypoint"}, indent=2))
            return {"plugin": plugin_id, "status": "no_gui_entrypoint", "metadata": output.name}
        with tempfile.TemporaryDirectory(prefix="chisurf-qt-reference-") as settings:
            env = dict(
                os.environ,
                QT_QPA_PLATFORM="offscreen",
                MPLBACKEND="Agg",
                CHISURF_SETTINGS_DIR=settings,
                MPLCONFIGDIR=str(cache.resolve()),
                XDG_CACHE_HOME=str(cache.resolve()),
                PYTHONPATH=str(ROOT),
                CHISURF_QT_REFERENCE_ORDER="latest" if args.prefer_latest else "earliest",
                CHISURF_QT_REFERENCE_TABS="1" if args.tab_pages else "0",
                CHISURF_QT_REFERENCE_TIMEOUT=str(args.timeout),
                CHISURF_QT_REFERENCE_DOCUMENT=str(args.document.resolve()) if args.document else "",
                CHISURF_QT_REFERENCE_WIDTH=str(args.width),
                CHISURF_QT_REFERENCE_HEIGHT=str(args.height),
            )
            try:
                run = subprocess.Popen(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--child",
                        entrypoint,
                        str(output.resolve()),
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                stdout, stderr = run.communicate(timeout=args.timeout)
                error = (stderr + stdout)[-12000:]
                status = "captured" if run.returncode == 0 and output.exists() else "failed"
            except subprocess.TimeoutExpired as exc:
                status = "timeout"
                error = (
                    str(exc)
                    + "\n"
                    + (exc.stdout or b"").decode(errors="replace")
                    + (exc.stderr or b"").decode(errors="replace")
                )
            finally:
                # Bound worker/server descendants as well as the Qt process.
                if "run" in locals():
                    try:
                        os.killpg(run.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    run.wait(timeout=5)
            if status != "captured":
                output.with_suffix(".png").unlink(missing_ok=True)
                output.write_text(
                    json.dumps(
                        {"entrypoint": entrypoint, "status": status, "error": error}, indent=2
                    )
                )
            print(f"{plugin_id}: {status}", flush=True)
            return {"plugin": plugin_id, "status": status, "metadata": output.name}

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        results = list(executor.map(capture, tasks))
    (args.output / "capture-index.json").write_text(json.dumps(results, indent=2))
    return int(any(result["status"] != "captured" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
