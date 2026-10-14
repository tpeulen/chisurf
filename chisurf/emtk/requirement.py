"""The emtk ChiSurf needs, checked before any window opens.

ChiSurf follows emtk's ``main`` closely: a release of one calls API the other
added days before. Run against an older emtk, the app does not fail to start --
it opens a window whose every frame raises ``AttributeError`` and shows
nothing. So the minimum is declared once, here, and checked at startup;
``pyproject.toml`` carries the same bound (a guard test keeps them equal).

Raise :data:`EMTK_MIN_VERSION` -- and emtk's own ``__version__`` -- in the
change that starts using an emtk API newer than the current minimum.
"""

from __future__ import annotations

#: The oldest emtk this tree runs against.
EMTK_MIN_VERSION = "0.1.19"


class EmtkTooOld(RuntimeError):
    """The installed emtk is older than :data:`EMTK_MIN_VERSION` (or missing)."""


def installed_emtk() -> dict:
    """``{"version", "commit", "path"}`` of the emtk that ``import emtk`` finds."""
    import emtk

    info_fn = getattr(emtk, "version_info", None)
    info = dict(info_fn()) if callable(info_fn) else {
        "version": getattr(emtk, "__version__", "unknown"), "commit": None}
    info["path"] = getattr(emtk, "__file__", None)
    return info


def check_emtk(minimum: str = EMTK_MIN_VERSION) -> dict:
    """Return the installed emtk's info, or raise :class:`EmtkTooOld` naming both versions.

    Parameters
    ----------
    minimum : str
        The oldest acceptable emtk version.

    Raises
    ------
    EmtkTooOld
        emtk is missing or older than *minimum*; the message says what is
        installed (version, commit, path), what is required, and how to update.
    """
    from packaging.version import InvalidVersion, Version

    try:
        info = installed_emtk()
    except ImportError as error:
        raise EmtkTooOld(
            f"ChiSurf needs emtk >= {minimum}, but emtk cannot be imported ({error}).\n"
            "Install it: pip install --no-deps git+https://github.com/tpeulen/emtk.git"
        ) from error
    try:
        too_old = Version(str(info["version"])) < Version(minimum)
    except InvalidVersion:
        too_old = True
    if too_old:
        commit = f" (commit {info['commit']})" if info.get("commit") else ""
        raise EmtkTooOld(
            f"ChiSurf needs emtk >= {minimum}, but emtk {info['version']}{commit} is installed "
            f"at {info.get('path')}.\n"
            "Update it: pip install --no-deps --upgrade git+https://github.com/tpeulen/emtk.git "
            "(or `pixi install`), then start ChiSurf again."
        )
    return info
