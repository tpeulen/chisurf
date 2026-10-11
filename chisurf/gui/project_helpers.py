from __future__ import annotations

import os
import pathlib

import chisurf as cs
from chisurf import logging
from chisurf.gui import QtCore, QtWidgets, dialogs, run_on_gui_thread


def _recent_projects_file() -> pathlib.Path:
    """Return the path to the persisted recent-projects JSON file (shared with the emtk shell)."""
    from chisurf.core.project import recent

    return recent.recent_projects_file()


def load_recent_projects() -> list[str]:
    """The stored recent projects, newest first."""
    from chisurf.core.project import recent

    return recent.load()


def store_recent_projects(projects: list[str]) -> None:
    """Write the recent-projects list."""
    from chisurf.core.project import recent

    recent.store(projects)


def set_recent_projects(window, projects: list[str]) -> None:
    try:
        window._recent_projects = list(projects or [])
    except Exception:
        window._recent_projects = []


def add_recent_project(window, project_path) -> None:
    """Put *project_path* first in the window's recent list, store it and refresh the menu."""
    from chisurf.core.project import recent

    try:
        current = list(getattr(window, "_recent_projects", []) or [])
    except Exception:
        current = []
    new_list = recent.added(current, project_path)
    set_recent_projects(window, new_list)
    store_recent_projects(new_list)
    refresh_recent_projects_menu(window)


def clear_recent_projects(window) -> None:
    set_recent_projects(window, [])
    store_recent_projects([])
    refresh_recent_projects_menu(window)


def open_recent_project(window, project_path: str) -> None:
    try:
        path = pathlib.Path(project_path)
    except Exception:
        return False

    try:
        if path.is_dir():
            project_file = path / "project.cs.pto"
            if not project_file.is_file():
                dialogs.warning(
                    window,
                    "Invalid Project",
                    "The selected folder does not contain a project file (project.cs.pto).",
                )
                try:
                    current = list(getattr(window, "_recent_projects", []) or [])
                    current = [
                        p for p in current if os.path.normpath(p) != os.path.normpath(project_path)
                    ]
                    set_recent_projects(window, current)
                    store_recent_projects(current)
                    refresh_recent_projects_menu(window)
                except Exception:
                    pass
                return False
            path = project_file
        elif not str(path).lower().endswith(".cs.pto"):
            dialogs.warning(
                window,
                "Invalid Project",
                "Please select a ChiSurf project file (*.cs.pto).",
            )
            try:
                current = list(getattr(window, "_recent_projects", []) or [])
                current = [
                    p for p in current if os.path.normpath(p) != os.path.normpath(project_path)
                ]
                set_recent_projects(window, current)
                store_recent_projects(current)
                refresh_recent_projects_menu(window)
            except Exception:
                pass
                return False
        if not path.is_file():
            try:
                current = list(getattr(window, "_recent_projects", []) or [])
                current = [
                    p for p in current if os.path.normpath(p) != os.path.normpath(project_path)
                ]
                set_recent_projects(window, current)
                store_recent_projects(current)
                refresh_recent_projects_menu(window)
            except Exception:
                pass
                return False
    except Exception:
        return False

    # No guard here: `replace_project` asks the window's transition guard itself
    # (it is the one authority over replacing the live project). Asking here as
    # well put "Save changes?" on screen twice for one Open.

    # Validate and stage the document before asking the live application to
    # replace its current state. A malformed archive must not destroy it.
    try:
        from chisurf.core.project import storage
        from chisurf.core.project.transition import replace_project
        from chisurf.macros.core_fit import restore_gui_from_fits

        project = storage.load_file(path)
        document = window._get_project_document()
        staged_document = document.stage_file_save(project, path)
    except Exception as exc:
        try:
            logging.exception(f"Failed to load recent project: {path}")
        except Exception:
            pass
        dialogs.warning(window, "Open Project Failed", str(exc))
        return False

    try:
        restored = replace_project(
            project,
            gui=window,
            document=document,
            target_identity=staged_document,
            present=restore_gui_from_fits,
            confirmed=True,
        )
        if restored.get("ok") is not True:
            return False
        cs.working_path = path.parent
    except Exception as exc:
        try:
            logging.exception(f"Failed to restore recent project: {path}")
        except Exception:
            pass
        dialogs.warning(window, "Open Project Failed", str(exc))
        return False

    add_recent_project(window, path)
    return True


def refresh_recent_projects_menu(window) -> None:
    """Rebuild the hidden-menubar Recent Projects menu and sync the ribbon button.

    Parameters
    ----------
    window : QMainWindow
        The application main window.
    """
    # Widget access must happen on the GUI thread. If this function is called
    # from a worker thread (e.g. project auto-save during sampling), reschedule
    # it on the GUI thread and return immediately.
    try:
        app = QtWidgets.QApplication.instance()
        if app is not None and QtCore.QThread.currentThread() is not app.thread():
            run_on_gui_thread(refresh_recent_projects_menu, window)
            return
    except Exception:
        pass

    menu = getattr(window, "_menu_recent_projects", None)
    if menu is not None:
        try:
            menu.clear()
        except Exception:
            pass

        try:
            projects = list(getattr(window, "_recent_projects", []) or [])
        except Exception:
            projects = []

        if not projects:
            try:
                a = QtWidgets.QAction("No recent projects", window)
                a.setEnabled(False)
                menu.addAction(a)
            except Exception:
                pass
        else:
            for i, p in enumerate(projects):
                try:
                    label = f"&{i + 1} {p}"
                    a = QtWidgets.QAction(label, window)
                    a.triggered.connect(
                        lambda _checked=False, pp=p: open_recent_project(window, pp)
                    )
                    menu.addAction(a)
                except Exception:
                    continue

        try:
            menu.addSeparator()
        except Exception:
            pass
        try:
            clear_action = QtWidgets.QAction("Clear Recent Projects", window)
            clear_action.triggered.connect(lambda _checked=False: clear_recent_projects(window))
            menu.addAction(clear_action)
        except Exception:
            pass

    # Also refresh the ribbon's dedicated Recent Projects drop-down (if present).
    try:
        integration = getattr(window, "_ribbon_integration", None)
        if integration is not None and hasattr(integration, "_refresh_ribbon_recent_projects"):
            integration._refresh_ribbon_recent_projects()
    except Exception:
        pass


def init_recent_projects_menu(window) -> None:
    """Create and insert the Recent Projects submenu into the normal File menu.

    The submenu is inserted into ``menuFile`` before the Exit separator so it
    appears as ``File > Recent Projects`` in the traditional menu bar.  It is
    also refreshed whenever a project is opened/saved/cleared via
    :func:`refresh_recent_projects_menu`.

    Parameters
    ----------
    window : QMainWindow
        The application main window.
    """
    if getattr(window, "_menu_recent_projects", None) is not None:
        refresh_recent_projects_menu(window)
        return

    try:
        recent_menu = QtWidgets.QMenu("Recent Projects", window)
        window._menu_recent_projects = recent_menu
    except Exception:
        return

    # Insert into menuFile before the Exit separator so the item appears as
    # File > Recent Projects in the normal (non-ribbon) menu bar.
    inserted = False
    try:
        file_menu = window.menuFile
        exit_action = getattr(window, "actionExit_2", None)
        if exit_action is not None:
            # Find the separator that precedes Exit and insert before it.
            actions = file_menu.actions()
            target = None
            for i, a in enumerate(actions):
                if a.isSeparator():
                    # Check if Exit follows this separator
                    remaining = actions[i + 1 :]
                    if any(r is exit_action for r in remaining):
                        target = a
                        break
            if target is not None:
                file_menu.insertMenu(target, recent_menu)
                inserted = True
            else:
                file_menu.insertMenu(exit_action, recent_menu)
                inserted = True
    except Exception:
        pass

    if not inserted:
        # Fallback: append to whatever menu is available
        try:
            window.menuFile.addMenu(recent_menu)
        except Exception:
            try:
                window.menuProject.addMenu(recent_menu)
            except Exception:
                pass

    try:
        set_recent_projects(window, load_recent_projects())
    except Exception:
        set_recent_projects(window, [])

    refresh_recent_projects_menu(window)
