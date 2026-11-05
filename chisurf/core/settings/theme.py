"""The window's theme: ``gui.theme`` in ``settings_chisurf.yaml`` (``dark``, the default, or ``light``).

The colours themselves are emtk's (:mod:`emtk.theme`: a value for every palette name, for
windows, docks, tabs, tables, fields, menus, plots and the workspace). This module only keeps
which one the user chose: :func:`apply_stored` hands it to emtk at startup, :func:`choose`
switches the running window and writes the choice, so the next start opens in it too.
Qt-free: the emtk shell's Settings menu calls these.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

#: Key of the choice under ``gui``.
KEY = "theme"
#: The theme a missing or unknown setting falls back to.
DEFAULT = "dark"


def stored() -> str:
    """The stored theme name (``gui.theme``), or :data:`DEFAULT` when unset or unknown."""
    try:
        from chisurf.core.settings import cs_settings

        name = str((cs_settings.get("gui") or {}).get(KEY) or DEFAULT).strip().lower()
    except Exception:  # noqa: BLE001 - unreadable settings: the default look
        return DEFAULT
    from emtk.theme import THEMES

    return name if name in THEMES else DEFAULT


def apply_stored(styles=()) -> str:
    """Apply the stored theme or style sheet to emtk (and to *styles* that already exist); returns its name."""
    import pathlib

    from emtk import theme

    try:
        from chisurf.core.settings import cs_settings, get_path

        gui_cfg = cs_settings.get("gui") or {}
        sheet_name = gui_cfg.get("style_sheet")
        if sheet_name:
            user_sheet = get_path("settings") / "styles" / sheet_name
            if user_sheet.is_file():
                return theme.apply_stylesheet(user_sheet, name=user_sheet.stem, styles=styles)
            import chisurf

            pkg_sheet = pathlib.Path(chisurf.__file__).parent / "gui" / "styles" / sheet_name
            if pkg_sheet.is_file():
                return theme.apply_stylesheet(pkg_sheet, name=pkg_sheet.stem, styles=styles)
            try:
                return theme.apply_stylesheet(sheet_name, styles=styles)
            except Exception:
                pass
    except Exception:  # noqa: BLE001 - fallback to theme
        pass

    name = stored()
    try:
        theme.apply_theme(name, styles=styles)
    except Exception:  # noqa: BLE001 - a theme must never stop the window from starting
        _log.exception("Could not apply the theme %r; using the dark one", name)
        theme.apply_theme(DEFAULT, styles=styles)
        name = DEFAULT
    return name


def stored_style() -> str:
    """The stored style sheet file name, or default to ``dark_blue.css``."""
    try:
        from chisurf.core.settings import cs_settings

        name = str((cs_settings.get("gui") or {}).get("style_sheet") or "").strip()
        if name:
            return name
    except Exception:
        pass
    return f"{stored()}.css"


#: ``(directory stamps, names, when checked)`` of the last :func:`available_styles` listing.
_STYLES_CACHE: tuple | None = None
#: Seconds the listing is trusted before the folders' modification times are looked at again.
STYLES_RECHECK_S = 2.0


def _style_dirs() -> list:
    """The folders style sheets are listed from: emtk's, ChiSurf's, the user's."""
    import pathlib

    import chisurf
    from chisurf.core.settings import get_path

    dirs = [pathlib.Path(chisurf.__file__).parent / "gui" / "styles"]
    try:
        from emtk import styles as emtk_styles

        dirs.insert(0, pathlib.Path(emtk_styles.__file__).parent)
    except Exception:  # noqa: BLE001 - listed without emtk's
        pass
    try:
        dirs.append(get_path("settings") / "styles")
    except Exception:  # noqa: BLE001 - no settings folder: none of the user's
        pass
    return dirs


def available_styles() -> list[str]:
    """Return all available stylesheet names (.css).

    The shell builds its menus every frame and each asks for this list: it is listed again only
    when one of the style folders changed (their modification times, looked at every
    :data:`STYLES_RECHECK_S`), never per frame -- the globs cost 4-12 ms a frame.
    """
    global _STYLES_CACHE
    import time

    cached = _STYLES_CACHE
    now = time.monotonic()
    if cached is not None and now - cached[2] < STYLES_RECHECK_S:
        return list(cached[1])
    stamps = []
    for folder in _style_dirs():
        try:
            stamps.append((str(folder), folder.stat().st_mtime_ns))
        except OSError:
            stamps.append((str(folder), None))
    stamps = tuple(stamps)
    if cached is not None and cached[0] == stamps:
        _STYLES_CACHE = (stamps, cached[1], now)
        return list(cached[1])
    styles = _list_styles()
    _STYLES_CACHE = (stamps, tuple(styles), now)
    return styles


def _list_styles() -> list[str]:
    """The style sheet names, listed from the folders (:func:`available_styles` keeps them)."""
    import pathlib

    from emtk import theme as emtk_theme

    import chisurf
    from chisurf.core.settings import get_path

    preferred = [
        "dark_blue.css",
        "dark.css",
        "light.css",
        "dark_green.css",
        "dark_orange.css",
        "dark_violet.css",
    ]
    styles: list[str] = []
    seen_stems: set[str] = set()

    def _add(filename: str) -> None:
        stem = pathlib.Path(filename).stem
        if stem not in seen_stems:
            seen_stems.add(stem)
            styles.append(f"{stem}.css")

    for preferred_name in preferred:
        _add(preferred_name)

    try:
        for s in emtk_theme.available_stylesheets():
            _add(s)
    except Exception:
        pass

    try:
        pkg_dir = pathlib.Path(chisurf.__file__).parent / "gui" / "styles"
        if pkg_dir.is_dir():
            for sheet in sorted(pkg_dir.glob("*.css")):
                _add(sheet.name)
    except Exception:
        pass

    try:
        user_dir = get_path("settings") / "styles"
        if user_dir.is_dir():
            for sheet in sorted(user_dir.glob("*.css")):
                _add(sheet.name)
    except Exception:
        pass

    return styles


def choose(name: str, styles=()) -> bool:
    """Switch the running window to theme or style sheet *name* and keep it for the next start.

    Parameters
    ----------
    name : str
        A theme name (``"dark"``, ``"light"``) or style sheet file name (``"dark_blue.css"``).
    styles : iterable of emtk.im_core.Style
        Styles the caller keeps (an app with a style of its own) that should switch too.

    Returns
    -------
    bool
        True when the choice was written to the user's settings file.
    """
    import pathlib

    from emtk import theme

    import chisurf
    from chisurf.core.settings import get_path
    from chisurf.core.settings.settings_utils import update_settings_section

    applied = None
    sheet_name = name

    # Check candidates for stylesheet file
    stem = pathlib.Path(name).stem
    candidates = [f"{stem}.css", name] if not name.endswith(".css") else [name]

    for cand in candidates:
        user_sheet = get_path("settings") / "styles" / cand
        if user_sheet.is_file():
            applied = theme.apply_stylesheet(user_sheet, name=user_sheet.stem, styles=styles)
            sheet_name = cand
            break
        pkg_sheet = pathlib.Path(chisurf.__file__).parent / "gui" / "styles" / cand
        if pkg_sheet.is_file():
            applied = theme.apply_stylesheet(pkg_sheet, name=pkg_sheet.stem, styles=styles)
            sheet_name = cand
            break
        try:
            import emtk.styles

            p = emtk.styles.get_stylesheet_path(cand)
            if p and p.is_file():
                applied = theme.apply_stylesheet(p, name=p.stem, styles=styles)
                sheet_name = cand
                break
        except Exception:
            pass

    if applied is None:
        if name in theme.THEMES:
            theme.apply_theme(name, styles=styles)
            applied = name
            sheet_name = f"{name}.css"
        else:
            raise KeyError(
                f"{name!r} is not a theme or stylesheet ({', '.join(sorted(theme.THEMES))})"
            )

    base_theme = "light" if theme.is_light() else "dark"
    try:
        import chisurf.core.settings as settings

        settings.cs_settings.setdefault("gui", {})[KEY] = base_theme
        settings.cs_settings.setdefault("gui", {})["style_sheet"] = sheet_name
        if hasattr(settings, "gui") and isinstance(settings.gui, dict):
            settings.gui[KEY] = base_theme
            settings.gui["style_sheet"] = sheet_name
    except Exception:
        pass

    return update_settings_section("gui", {KEY: base_theme, "style_sheet": sheet_name})


__all__ = ["DEFAULT", "KEY", "apply_stored", "available_styles", "choose", "stored", "stored_style"]
