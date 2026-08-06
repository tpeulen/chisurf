"""Get ``sys.path`` right before ChiSurf imports anything.

Two corrections, both of which have to happen before the first compiled
extension is imported: adding the in-tree companion packages a source checkout
keeps below ``modules/``, and removing the runtime directories of *other* Python
environments that a launcher put on the path.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_BUNDLED_PACKAGE_PATHS = (
    ("mmfdb", "src"),
    ("chinet", None),
    ("ndxplorer", None),
    ("SARibbon-pyqt5", "src"),
)

#: Opt out of :func:`drop_foreign_environment_paths` (for the rare case where
#: another environment's *pure-Python* package really is what is wanted).
_ALLOW_FOREIGN_VAR = "CHISURF_ALLOW_FOREIGN_ENVIRONMENT_PATHS"

_TRUTHY = {"1", "true", "yes", "on"}


def bootstrap_bundled_packages() -> tuple[Path, ...]:
    """Prepend available in-tree package roots and return those added.

    Installed ChiSurf distributions contain ``mmfdb`` and ``chinet`` as normal
    packages, so their installation needs no path adjustment. A source checkout
    keeps those packages below ``modules/``; prepending their roots ensures the
    checkout consistently uses the matching bundled versions instead of a stale
    environment installation.
    """
    project_root = Path(__file__).resolve().parent.parent
    existing = {
        Path(entry).resolve()
        for entry in sys.path
        if entry
    }
    added: list[Path] = []

    for module_name, source_dir in _BUNDLED_PACKAGE_PATHS:
        package_root = project_root / "modules" / module_name
        if source_dir:
            package_root /= source_dir
        package_root = package_root.resolve()
        if package_root.is_dir() and package_root not in existing:
            added.append(package_root)
            existing.add(package_root)

    if added:
        sys.path[0:0] = [str(path) for path in added]
    return tuple(added)


def environment_prefix(entry: Path) -> Path | None:
    """Return the interpreter prefix *entry* is a runtime directory of.

    Parameters
    ----------
    entry : pathlib.Path
        A resolved ``sys.path`` entry.

    Returns
    -------
    pathlib.Path or None
        The environment prefix when *entry* is that environment's standard
        library or site-packages directory, otherwise ``None``. Only the layouts
        an interpreter itself produces are recognised — a directory merely
        *named* ``site-packages`` somewhere else is not one.
    """
    parent = entry.parent
    if entry.name in ("site-packages", "dist-packages"):
        if parent.name.startswith("python"):           # <prefix>/lib/python3.12/…
            return parent.parent.parent
        if parent.name in ("Lib", "lib"):              # <prefix>/Lib/… (Windows)
            return parent.parent
        return None
    if entry.name.startswith("python3") and parent.name == "lib":
        return parent.parent                           # the standard library itself
    return None


def drop_foreign_environment_paths() -> tuple[str, ...]:
    """Remove other environments' runtime directories from ``sys.path``.

    A ``site-packages`` directory belongs to exactly one interpreter, because
    the compiled extensions in it are linked against *that* environment's native
    libraries and are located through *that* interpreter's rpath. Put a second
    environment's site-packages on the path and the import succeeds while the
    load fails, in the loader, naming a library instead of a mistake::

        ImportError: dlopen(<other env>/site-packages/_tttrlib…so):
          Library not loaded: @rpath/libhdf5.320.dylib
          Reason: tried: '<this env>/bin/../lib/libhdf5.320.dylib' (no such file)

    Nobody puts it there on purpose. An IDE does: marking an environment's
    site-packages as a *source root* (or content root) makes the IDE prepend it
    to ``PYTHONPATH`` for every run configuration, whichever interpreter that
    configuration selects. The standard library directory is worse again, since
    it shadows the running interpreter's own modules.

    Directories under this interpreter's prefix — or its ``base_prefix``, which
    is how a virtual environment reaches the system packages it was created with
    — are its own and are kept.

    Returns
    -------
    tuple of str
        The entries removed, in the order they appeared.
    """
    if os.environ.get(_ALLOW_FOREIGN_VAR, "").strip().lower() in _TRUTHY:
        return ()

    own: set[Path] = set()
    for prefix in (sys.prefix, getattr(sys, "base_prefix", sys.prefix)):
        try:
            own.add(Path(prefix).resolve())
        except OSError:
            continue

    removed: list[str] = []
    for entry in list(sys.path):
        if not entry:
            continue
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        prefix = environment_prefix(resolved)
        if prefix is None or prefix in own:
            continue
        sys.path.remove(entry)
        removed.append(entry)

    if removed:
        log.warning(
            "Removed %d path entry/entries belonging to a different Python "
            "environment than the running interpreter (%s): %s. Compiled "
            "extensions there are linked against that environment's libraries "
            "and cannot be loaded here. This is usually an IDE run "
            "configuration with an environment's site-packages marked as a "
            "source root, or PYTHONPATH set for another environment. Set %s=1 "
            "to keep them.",
            len(removed), sys.prefix, ", ".join(removed), _ALLOW_FOREIGN_VAR,
        )
    return tuple(removed)
