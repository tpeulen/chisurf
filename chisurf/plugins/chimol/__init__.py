"""Chimol plugin -- molecular structure viewer for ChiSurf.

Importing this package costs **no GUI toolkit**, and the plugin has no Qt
window: both ChiSurf shells open the emtk app (``app.make_app``), the
``--qt`` shell by hosting its surface. This file only places chimol's settings
and hands it ChiSurf's structure reader. The Qt window it used to open
(``chimol.hosts.qt.MolViewPluginWindow``) was retired at control parity; the
before/after evidence is ``okf/plugins/emtk-ports/chimol/retire_*`` and the
recorded facts ``test/qt_reference.json``.

The manifest, the display name and the version stay eager: the plugin loader
reads them, and none of them touches a toolkit.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from chisurf.core.plugin import load_manifest


def _place_chimol_settings_beside_chisurf_s() -> None:
    """Tell chimol to keep its settings where ChiSurf keeps everything else.

    chimol resolves its own settings directory and defaults to ``~/.chimol``,
    because it is packaged to run with no ChiSurf on the path. Inside ChiSurf
    that default is wrong: the plugin and the application should share one
    directory, so a user has one place to look and the standalone and plugin
    runs see the same configuration.

    Injected rather than asked for. chimol used to import
    ``chisurf.core.settings`` itself inside a ``try`` -- which worked, and put
    the dependency in the wrong direction and out of sight: nothing on this
    side said the plugin owned that decision. Here it is a single call at the
    only moment the answer is both known and correct, and chimol names nobody.

    A failure is not fatal. chimol falls back to its own directory, which is a
    working viewer whose settings live somewhere unexpected -- much better than
    a plugin that will not load because a settings path could not be resolved.
    """
    try:
        from chimol.core.settings.dirs import set_settings_dir

        import chisurf.core.settings as _cs_settings

        set_settings_dir(_cs_settings.get_path("settings"))

        # chimol's log file follows its settings directory (just injected
        # above), so the plugin's log lands beside the host's -- one place to
        # look. Called *after* the injection for exactly that reason, and it
        # adds no console handler of its own: the root logger is already
        # configured here, so chimol's records reach the host's session log
        # and console through propagation and are not printed twice. That
        # propagation is the whole of "chimol logs into chisurf"; no chimol
        # module names the host.
        from chimol.core.settings.logging import configure_logging

        configure_logging()

    except Exception:  # noqa: BLE001 - a partial install, or a settings backend that moved
        logging.getLogger(__name__).debug(
            "chimol keeps its own settings directory; ChiSurf's was not resolvable",
            exc_info=True,
        )


_place_chimol_settings_beside_chisurf_s()


def _chisurf_structure(path: str, **options):
    """Read *path* with ChiSurf's ``Structure`` (imported on the first load).

    Parameters
    ----------
    path : str
        A structure file.
    **options
        Passed to ``Structure`` (``keep_water``, ``radii``, ...).

    Returns
    -------
    chisurf.core.structure.Structure
    """
    from chisurf.core.structure import Structure

    return Structure(path, **options)


def _give_chimol_chisurfs_structure_reader() -> None:
    """Make ChiSurf's ``Structure`` the reader every chimol host loads with.

    chimol reads a file with its own parsers unless an embedder hands it a
    full reader (residues, sequence, radius of gyration); injected here, for
    the same reason as the settings directory above, so chimol names nobody.
    The reader is imported lazily: building ``Structure`` pulls IMP in, and a
    plugin import should not.
    """
    try:
        from chimol.io.structure import set_structure_factory

        set_structure_factory(_chisurf_structure)
    except Exception:  # noqa: BLE001 - a chimol without the hook reads with its own parser
        logging.getLogger(__name__).debug(
            "chimol keeps its own structure reader", exc_info=True
        )


_give_chimol_chisurfs_structure_reader()

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Structure:Modelling:ChiMOL"

__version__ = "0.2.0"

__all__ = ["main", "name"]


def main() -> None:
    """Launch chimol's own toolkit-free window (:func:`chimol.hosts.native.app.main`).

    Inside ChiSurf the plugin is the emtk app (``app.make_app``): the emtk shell
    docks it and the ``--qt`` shell only hosts that surface. There is no Qt
    window of the plugin's own any more.
    """
    from chimol.hosts.native.app import main as native_main

    raise SystemExit(native_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
