"""Hermetic environment for the light-path captures: temp settings, a generated spectra catalogue, an in-process RPC client.

Import before anything of chisurf. Never touches ~/.chisurf, the keyring or a network.
"""
import os, pathlib, sys, tempfile

TMP = pathlib.Path(tempfile.mkdtemp(prefix="lp_"))
# the easy mode writes under Path.home()/.chisurf: HOME points into the temp folder
(TMP / "home").mkdir()
os.environ["HOME"] = str(TMP / "home")
os.environ["CHISURF_SETTINGS_DIR"] = str(TMP / "settings")
os.environ["MMFDB_SETTINGS_DIR"] = str(TMP / "mmfdb")
DB = TMP / "spectra.sqlite"
os.environ["MMFDB_DATABASE_PATH"] = str(DB)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.plugins.core.lightpath_simulator.tests.catalog import build_catalogue  # noqa: E402

IDS = build_catalogue(DB)


def in_process_client(timeout_ms=0):
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.plugins.core.lightpath_simulator.api.client import LightPathClient
    from chisurf.plugins.core.lightpath_simulator.rpc.services import register_services
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    register_services(dispatcher)
    return LightPathClient(InProcessClient(dispatcher))


def patch_client():
    from chisurf.plugins.core.lightpath_simulator.api.client import LightPathClient

    LightPathClient.from_settings = classmethod(lambda cls, timeout_ms=0: in_process_client())
