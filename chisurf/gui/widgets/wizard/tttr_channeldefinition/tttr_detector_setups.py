"""GUI entry to the detector-setup store: the store itself is ``chisurf.core.data_io.detector_setups``.

Only the interactive "setups file not found" prompt lives here; Qt is imported
lazily inside it, so the module stays import-time Qt-free.
"""

from __future__ import annotations

import pathlib

from chisurf.core.data_io.detector_setups import (
    DETECTOR_SETUPS_FILE,
    _db_available,
    _use_mmfdb,
)
from chisurf.core.data_io.detector_setups import load_detector_setups as _load


def load_detector_setups(file_path=None, db_path=None, skip_migration=False, user_id=None):
    """Load setups from :mod:`chisurf.core.data_io.detector_setups`, offering the wizard when none exist.

    The data comes from the one shared store; this GUI variant only adds the
    "setups file not found" prompt for an interactive session with no MMFDB and
    no canonical JSON file.
    """
    path = pathlib.Path(file_path or DETECTOR_SETUPS_FILE)
    if _use_mmfdb(file_path) and _db_available(db_path):
        return _load(file_path, db_path=db_path, skip_migration=skip_migration, user_id=user_id)

    try:
        import chisurf.core.settings

        show_warning = bool(
            chisurf.core.settings.cs_settings.get("warn_missing_detector_setups", True)
        )
    except Exception:
        show_warning = True

    if not path.exists():
        is_default = (file_path is None) or (path == DETECTOR_SETUPS_FILE)
        # A modal box blocks until a button is pressed, so "a QApplication
        # exists" is not enough — offscreen there is nobody to press it and this
        # loader would hang every headless run that has no setups file.
        try:
            from chisurf.gui.dialogs import is_interactive

            app_running = is_interactive()
        except Exception:
            app_running = False

        try:
            import chisurf as _chisurf_mod

            if is_default and getattr(_chisurf_mod, "__startup_in_progress__", False):
                try:
                    _chisurf_mod.__pending_startup_onboarding__ = True
                except Exception:
                    pass
                return {"setups": {}}
        except Exception:
            pass

        if (
            show_warning
            and is_default
            and app_running
            and not _module_warning_shown("detector_setups_file")
        ):
            from chisurf.gui import dialogs

            _mark_warning_shown("detector_setups_file")
            answer = dialogs.choice(
                None,
                "Detector setups file not found",
                f"Detector setups file was not found:\n{str(path)}",
                {"wizard": "Open Detector Wizard", "ok": "OK"},
                default="ok",
                kind="warning",
                informative=(
                    "You can create it by saving a setup from the Detector Wizard.\n"
                    "Use the 'Save Settings' button to store your configuration.\n"
                    "Alternatively, choose an existing JSON with the '...' button."
                ),
                checkbox="Don't show this warning again",
            )

            try:
                if answer.checked:
                    from chisurf.core.settings.settings_utils import (
                        set_warn_missing_detector_setups as _set_w,
                    )

                    _set_w(False)
                    try:
                        import chisurf.core.settings

                        chisurf.core.settings.cs_settings["warn_missing_detector_setups"] = False
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                if answer.key == "wizard":
                    from . import DetectorWizard

                    wiz = DetectorWizard()
                    wiz.exec_()
                    if path.exists():
                        return _load(file_path)
            except Exception:
                pass

        return {"setups": {}}

    return _load(file_path)


def _module_warning_shown(key: str) -> bool:
    from chisurf.gui.widgets.warning_once import was_warning_shown

    return was_warning_shown(key)


def _mark_warning_shown(key: str) -> None:
    from chisurf.gui.widgets.warning_once import mark_warning_shown

    mark_warning_shown(key)
