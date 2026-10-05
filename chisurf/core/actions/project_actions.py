from __future__ import annotations

from typing import Any

import chisurf as cs
from chisurf import typing
from chisurf.core.actions._decorator import action


@action("experiment.set", schema={"name": str})
def set_experiment(name: str):
    """Switch the current experiment type and refresh the GUI."""
    gui = getattr(cs, "cs", None)
    if gui is None:
        return {}
    # Update combo selection without triggering a dispatch loop
    combo = getattr(gui, "comboBox_experimentSelect", None)
    if combo is not None:
        idx = combo.findText(name)
        if idx != -1 and combo.currentIndex() != idx:
            combo.blockSignals(True)
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)
            gui._current_experiment_idx = idx
    # Refresh GUI directly — no re-dispatch
    if hasattr(gui, "_refresh_experiment_ui"):
        gui._refresh_experiment_ui()
    return {}


@action("setup.select", schema={"name": str})
def select_setup(name: str):
    """Select a setup configuration and refresh the GUI."""
    gui = getattr(cs, "cs", None)
    if gui is None:
        return {}
    # Find the setup index from the current experiment's readers
    try:
        readers = gui.current_experiment.readers
        for j, s in enumerate(readers):
            if s.name == name:
                gui._current_setup_idx = j
                combo = getattr(gui, "comboBox_setupSelect", None)
                if combo is not None:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(j)
                    combo.blockSignals(False)
                break
    except Exception:
        pass
    # Refresh GUI directly — no re-dispatch
    if hasattr(gui, "_refresh_setup_ui"):
        gui._refresh_setup_ui()
    return {}


def _current_setup() -> typing.Any:
    """Return the reader of the currently selected setup, or ``None``.

    Returns
    -------
    object or None
        The active :class:`ExperimentReader`. ``None`` when ChiSurf runs
        without a main window (a plugin started standalone) or when no
        experiment is selected yet — ``Main.current_setup`` raises in that
        case, and a property raising :class:`AttributeError` is reported as
        "``Main`` has no attribute ``current_setup``", which hides the cause.
    """
    gui = getattr(cs, "cs", None)
    if gui is None:
        return None
    try:
        return gui.current_setup
    except (AttributeError, IndexError):
        return None


@action("setup.params.set", schema={"params": dict})
def set_setup_params(params: typing.Dict[str, typing.Any]):
    """Set parameters for the current setup.

    Parameters
    ----------
    params : dict
        Attribute names mapped to the values to assign. A dotted name
        (``"a.b"``) walks attributes on the setup before assigning the last
        component.

    Returns
    -------
    dict
        ``{"applied": [...]}`` — the keys that were written. Empty when no
        setup is reachable; the action logs a warning instead of raising, so a
        caller that dispatches from a Qt slot is not silently truncated.
    """
    setup = _current_setup()
    if setup is None:
        cs.logging.warning("setup.params.set: no setup is selected — parameters not applied")
        return {"applied": []}
    for key, value in params.items():
        if "." in key:
            parts = key.split(".")
            obj = setup
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], value)
        else:
            setattr(setup, key, value)
    return {"applied": list(params)}


@action("project.save", schema={"project_name": str})
def save_project(target_path: str, project_name: str):
    """Save the overall project and publish its verified file identity."""
    from pathlib import Path

    from chisurf.core.project import storage
    from chisurf.macros import core_fit

    saved_path = Path(core_fit.save_project(target_path=target_path, project_name=project_name))
    project = storage.load_file(saved_path)
    gui = getattr(cs, "cs", None)
    if gui is not None:
        document = gui._get_project_document()
        staged = document.stage_file_save(project, saved_path)
        document.adopt(staged)
        gui._current_project_path = saved_path
        gui._current_project_id = None
        gui._current_project_version_id = None
        gui._current_project_name = document.name
    return {"ok": True, "backend": "file", "file_path": str(saved_path)}


@action("project.load", schema={"project_path": str})
def load_project(project_path: str):
    """Guard and replace a file project through the authoritative runtime owner."""
    from chisurf.macros.core_fit import load_project

    result = load_project(project_path)
    if result.get("ok") is not True:
        return result
    return {**result, "backend": "file", "file_path": str(project_path)}


@action(
    "project.archive",
    schema={
        "project_id": str,
        "project_name": str,
        "experiment_id": None,
        "input_processed_data_ids": list,
        "notes": str,
    },
)
def archive_project(
    project_id: str,
    project_name: str,
    experiment_id: str | None = None,
    input_processed_data_ids: list[str] | None = None,
    notes: str | None = None,
):
    """Persist to the configured database, or a portable file when absent."""
    from chisurf.core.project import storage
    from chisurf.macros.core_fit import get_project_payload

    project = get_project_payload(project_name)
    if storage.select_backend() == "file":
        import pathlib

        path = pathlib.Path(cs.working_path) / f"{project_name}.cs.pto"
        saved_path = storage.save_file(project, path)
        return {"ok": True, "backend": "file", "file_path": str(saved_path)}
    document = getattr(getattr(cs, "cs", None), "_project_document", None)
    parent = getattr(document, "version_id", None)
    return storage.save_database(
        project,
        project_id=project_id or getattr(document, "project_id", None),
        parent_version_id=parent,
        notes=notes or "",
    )


def _project_counts_from_payload(payload: dict[str, Any] | None) -> tuple[int, int]:
    """Return fit and dataset counts from a project payload."""
    if not isinstance(payload, dict):
        return 0, 0
    datasets = payload.get("datasets", {})
    fits = payload.get("fits", [])
    return (
        len(fits) if hasattr(fits, "__len__") else 0,
        len(datasets) if hasattr(datasets, "__len__") else 0,
    )


@action("project.restore", schema={"project_id": str})
def restore_project(project_id: str):
    """Restore an exact version (or current project head) from a real store."""
    from chisurf.core.project import storage
    from chisurf.core.project.transition import replace_project
    from chisurf.macros.core_fit import restore_gui_from_fits

    if storage.select_backend() != "mmfdb":
        raise storage.ProjectStorageError(
            "No real MMFDB is configured; open a .cs.pto file instead"
        )
    gui = getattr(cs, "cs", None)
    guard = getattr(gui, "_guard_project_transition", None)
    if callable(guard) and not guard():
        return {"ok": False, "cancelled": True}
    client = storage._real_client(storage._settings(None))
    version_id = project_id
    if not project_id.startswith("ver_"):
        for project in client.list_projects(show_public=True):
            if project.get("project_id") == project_id:
                versions = project.get("versions") or []
                if not versions:
                    raise storage.ProjectStorageError(
                        f"Project has no saved versions: {project_id}"
                    )
                version_id = versions[0]["version_id"]
                break
    project, result = storage.load_database(version_id, client=client)
    result = {**result, "ok": True}
    document = gui._get_project_document() if gui is not None else None
    staged = document.stage_database_save(project, result) if document is not None else None
    transition = replace_project(
        project,
        gui=gui,
        document=document,
        target_identity=staged,
        present=restore_gui_from_fits if gui is not None else None,
        confirmed=True,
    )
    return result if transition.get("ok") is True else transition


@action("project.close")
def close_project(main_window: typing.Any = None, confirmed: bool = False):
    """Replace the active project with an empty session through its runtime owner."""
    from chisurf.core.project import capture_session
    from chisurf.core.project.lifecycle import ProjectDocument
    from chisurf.core.project.transition import replace_project
    from chisurf.macros.core_fit import restore_gui_from_fits

    main_window = main_window or getattr(cs, "cs", None)
    document = getattr(main_window, "_get_project_document", lambda: None)()
    if document is None:
        document = getattr(main_window, "_project_document", None)
    return replace_project(
        capture_session([], [], name="untitled"),
        gui=main_window,
        document=document,
        target_identity=ProjectDocument() if document is not None else None,
        present=restore_gui_from_fits if main_window is not None else None,
        confirmed=confirmed,
    )


@action("action.catalog.export")
def export_action_catalog(target_path: str, file_type: str = "yaml"):
    """Export the list of available actions to a file."""
    import yaml

    from chisurf.core.actions._infra import get_action_catalog

    catalog = get_action_catalog()
    with open(target_path, "w") as f:
        yaml.dump(catalog, f)
    return {"target_path": target_path}


@action("app.reinitialize.start")
def app_reinitialize_start():
    """Signify start of application reinitialization."""
    return {}


@action("app.reinitialize.finish")
def app_reinitialize_finish():
    """Signify finish of application reinitialization."""
    return {}


@action("run_command", replayable=False, side_effect_class="diagnostic")
def run_command(command: str):
    """Run a shell or macro command."""
    return cs.run(command)
