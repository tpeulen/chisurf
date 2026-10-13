"""What the emtk shell does once its main window is up: the ``post_show`` startup stages.

The Qt window runs ``chisurf/startup/services.d/30_gui_post_show.json`` after it is shown; most of
those stages build Qt state the emtk shell makes for itself (history, autosave, plugin menus). Two
are not about the window: the startup update check and preloading the modules a first fit needs.
They are the ``surface="emtk"``, ``phase="post_show"`` set in
``chisurf/startup/services.d/35_emtk_post_show.json``, run by the same
:class:`~chisurf.startup.services.AppStartupServiceManager`, on a worker thread once the shell has
adopted its session, never on the frame loop.

A stage only *finds* things out; what it found travels in the manager's shared ``metadata``
(``update_offer``) and the shell acts on it on its own thread (:meth:`PostShow.poll`): the
*Update Available* question, whose *Yes* opens *Settings ▸ Updates*.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any

from chisurf.emtk.background_build import BackgroundBuild

_log = logging.getLogger(__name__)

#: Qt-free modules a first fit or fit window imports; preloaded so the first click does not wait.
#: Page classes are not in it: they still import Qt through chiplot (qt-retirement ledger item 6).
WARM_MODULES = (
    "chisurf.core.fitting",
    "chisurf.core.models",
    "chisurf.core.models.global_model.globalfit",
    "chisurf.core.structure",
    "chisurf.emtk.model_editor",
    "chisurf.emtk.fit_pages.surface",
)


def update_check_wanted(settings: dict | None = None) -> bool:
    """Whether the user lets ChiSurf look for a newer version on start.

    The same two preferences the Qt window reads (``plugins.updater.check_on_startup`` and
    ``plugins.updater.ignore_updates_on_startup``), so one setting governs both windows.
    """
    if settings is None:
        try:
            from chisurf.core.settings import cs_settings as settings
        except Exception:  # noqa: BLE001 - unreadable settings: the shipped default
            settings = {}
    updater = ((settings or {}).get("plugins") or {}).get("updater") or {}
    return bool(updater.get("check_on_startup", True)) and not bool(
        updater.get("ignore_updates_on_startup", False)
    )


# -- the stages (``services.d/35_emtk_post_show.json``) --------------------------------------- #


def stage_check_updates(context: Any) -> None:
    """Ask the update server for a newer ChiSurf; leave an ``update_offer`` when there is one."""
    if not update_check_wanted():
        _log.info("Startup update check suppressed by user settings.")
        return
    from chisurf.plugins.core.updater import updater

    available, latest, error = updater.check_for_updates()
    if error:
        _log.info("Update check skipped or failed: %s", error)
        return
    if not available:
        _log.info("ChiSurf is up to date.")
        return
    _log.info("Update available: %s", latest)
    try:
        installed, changes = updater.build_installed_vs_latest_changelog(str(latest))
    except Exception:  # noqa: BLE001 - the question is still worth asking without the list
        installed, changes = None, None
    context.metadata["update_offer"] = {
        "latest": str(latest),
        "installed": installed,
        "changes": changes,
    }


def stage_warmup_imports(context: Any) -> None:
    """Import :data:`WARM_MODULES`; a module that fails is logged, never stops the shell."""
    for name in WARM_MODULES:
        try:
            importlib.import_module(name)
        except Exception:  # noqa: BLE001 - a warm-up, not a requirement
            _log.debug("warm-up import of %s failed", name, exc_info=True)


def run_post_show(on_stage: Callable[[dict], None] | None = None) -> dict:
    """Run the ``surface="emtk"``, ``phase="post_show"`` stages in order; return what they left.

    Parameters
    ----------
    on_stage : callable, optional
        Called as each stage starts, with its payload (``id``, ``label``, ``progress``, …).

    Returns
    -------
    dict
        The stages' shared ``metadata`` (``update_offer`` when a newer version exists).
    """
    from chisurf.startup.services import AppStartupServiceManager

    metadata: dict[str, Any] = {}
    AppStartupServiceManager().start(
        surface="emtk", phase="post_show", on_stage_start=on_stage, metadata=metadata
    )
    return metadata


class PostShow:
    """The shell's post-show stages: started once the session is adopted, acted on as they end.

    Parameters
    ----------
    shell : EmtkShellApp
        The main window; its status strip shows the stage under way, its dialogs ask the question.
    runner : callable, optional
        ``runner(on_stage) -> metadata``; :func:`run_post_show` by default (tests pass a stand-in).
    """

    def __init__(self, shell: Any, runner: Callable[..., dict] | None = None) -> None:
        self.shell = shell
        self.runner = runner or run_post_show
        self.build = BackgroundBuild(wake=shell.request_frame)
        #: Whether the stages were started (they run once per shell).
        self.started = False
        #: The stage under way (``label`` / ``progress``), shown on the status strip.
        self.stage: dict = {}
        #: What the stages left, once they ended.
        self.result: dict | None = None

    @property
    def running(self) -> bool:
        """Whether the stages are under way (or their result waits for a frame)."""
        return self.build.busy

    def start(self) -> bool:
        """Run the stages on a worker thread; ``False`` when they ran already."""
        if self.started:
            return False
        self.started = True

        def on_stage(payload: dict) -> None:
            self.stage = dict(payload or {})
            self.shell.request_frame()

        runner = self.runner
        return self.build.start({"post_show": lambda: runner(on_stage)}, name="chisurf-post-show")

    def poll(self) -> None:
        """Once per frame: when the stages have ended, act on what they found."""
        results = self.build.collect()
        if results is None:
            return
        made, error = results.get("post_show", (None, None))
        self.stage = {}
        if error is not None:
            _log.warning("the post-show startup stages failed: %s", error)
        self.result = dict(made or {})
        offer = self.result.get("update_offer")
        if offer:
            self.offer_update(offer)

    def offer_update(self, offer: dict) -> None:
        """Ask whether to open the updater (the Qt window's *Update Available* question)."""
        from emtk.i18n import tr

        text = tr("A new version of ChiSurf ({version}) is available.").format(
            version=offer.get("latest", "")
        )
        changes = offer.get("changes")
        if changes:
            text += "\n\n" + tr("Changes since your installed version ({version}):").format(
                version=offer.get("installed") or "?"
            )
            text += "\n\n" + str(changes)
        text += "\n\n" + tr("Do you want to open the Updater now?")
        self.shell.project.dialogs.confirm(
            tr("Update Available"),
            text,
            lambda yes: bool(yes) and self.open_updates(),
            default=True,
        )

    def open_updates(self) -> bool:
        """Open *Settings* on its *Updates* page (the updater, which does not ask again)."""
        shell = self.shell
        if "setup" not in shell.by_id:
            return False
        hosted = shell.open_plugin("setup")
        if hosted is None:
            return False

        def show_updates() -> None:
            select = getattr(hosted.app, "select", None)
            if callable(select):
                select("updates")

        hosted.on_ready.append(show_updates)
        if hosted.app is not None and hosted.build is None:
            shell._run_ready(hosted)
        shell.request_frame()
        return True


__all__ = [
    "PostShow",
    "WARM_MODULES",
    "run_post_show",
    "stage_check_updates",
    "stage_warmup_imports",
    "update_check_wanted",
]
