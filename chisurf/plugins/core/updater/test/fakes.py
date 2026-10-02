"""Stand-ins for everything the updater can do to the machine or the network.

SAFETY (hard rule of the port): nothing in the tests or in the evidence scripts may run a real update, install, remove or
environment change, nor reach the network. :class:`Fakes` replaces, on the classes, every method that would:

``ChiSurfUpdater._run_command``, ``_run_with_elevation``, ``_run_update_in_separate_process``, ``_schedule_restart``,
``_list_remote_versions`` and ``PackageManager._popen``; ``urllib.request.urlopen`` / ``urlretrieve`` (a canned GitHub
commit list for the changelog, an error for anything else) and ``subprocess.Popen`` / ``subprocess.run`` (an assertion:
no process may ever be started). Every command line that reached a fake is recorded, so a test asserts that the line the
real code would have run is the one seen.

The module is used as a pytest fixture (``conftest.py``) and, with a ``pytest.MonkeyPatch``, by the capture scripts.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

#: The releases the fake download server lists, newest first (``_list_remote_versions`` returns them).
RELEASES = [
    {"version": "26.10.02", "file_path": "https://downloads.invalid/chisurf/conda/macos/chisurf-macos-26.10.02.tar.bz2",
     "file_name": "chisurf-macos-26.10.02.tar.bz2"},
    {"version": "26.09.20", "file_path": "https://downloads.invalid/chisurf/conda/macos/chisurf-macos-26.09.20.tar.bz2",
     "file_name": "chisurf-macos-26.09.20.tar.bz2"},
    {"version": "26.08.01", "file_path": "https://downloads.invalid/chisurf/conda/macos/chisurf-macos-26.08.01.conda",
     "file_name": "chisurf-macos-26.08.01.conda"},
]

#: What the fake GitHub commits API returns (``_build_changelog`` reads author, date and the first message line).
COMMITS = [
    {"commit": {"message": "Add the updater tour\n\nbody text", "author": {"name": "Ada", "date": "2026-10-01T10:00:00Z"}}},
    {"commit": {"message": "Merge branch 'x'", "author": {"name": "Bob", "date": "2026-09-30T10:00:00Z"}}},
    {"commit": {"message": "Fix <b>bold</b> & ampersand handling", "author": {"name": "Cy", "date": "2026-09-25T08:00:00Z"}}},
]

#: What the fake solver lists as installed (``list --json``: name, version, channel, as conda prints them).
INSTALLED = [
    {"name": "numpy", "version": "1.26.4", "channel": "conda-forge", "build_string": "py311_0"},
    {"name": "scipy", "version": "1.13.1", "channel": "conda-forge", "build_string": "py311_0"},
    {"name": "python", "version": "3.11.9", "channel": "conda-forge", "build_string": "h1_0"},
    {"name": "chisurf", "version": "26.09.20", "channel": "chisurf-local", "build_string": "py_0"},
    {"name": "Numba", "version": "0.59.1", "channel": "defaults", "build_string": "py311_0"},
]

#: ``search numpy --json`` as conda prints it: a mapping from the package name to its builds.
SEARCH_CONDA = {
    "numpy": [
        {"name": "numpy", "version": "1.26.3", "build": "py311_0", "channel": "https://conda.anaconda.org/conda-forge/osx-arm64"},
        {"name": "numpy", "version": "1.26.4", "build": "py311_0", "channel": "https://conda.anaconda.org/conda-forge/osx-arm64"},
        {"name": "numpy", "version": "1.26.4", "build": "py312_0", "channel": "https://conda.anaconda.org/conda-forge/osx-arm64"},
        {"name": "numpy", "version": "2.0.1", "build": "py312_0", "channel": "https://conda.anaconda.org/conda-forge/osx-arm64"},
    ],
}
#: The same search as micromamba prints it.
SEARCH_MICROMAMBA = {"result": {"pkgs": [dict(p, channel="conda-forge") for p in SEARCH_CONDA["numpy"]]}, "status": "OK"}

ENVS = ["/fake/mambaforge", "/fake/mambaforge/envs/arm64", "/fake/mambaforge/envs/analysis"]
CHANNELS = ["conda-forge", "defaults"]


class NetworkBlocked(AssertionError):
    """Raised by every fake that guards the network or a process."""


class _Response:
    """A minimal ``urlopen`` result."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class Fakes:
    """The recorded stand-ins; ``install(monkeypatch)`` puts them in place."""

    def __init__(self, *, search: Any = None, installed: list | None = None, releases: list | None = None,
                 commits: list | None = None, solver_fails: bool = False) -> None:
        self.releases = [dict(r) for r in (RELEASES if releases is None else releases)]
        self.commits = COMMITS if commits is None else commits
        self.installed = [dict(p) for p in (INSTALLED if installed is None else installed)]
        self.search_payload = SEARCH_CONDA if search is None else search
        self.envs = list(ENVS)
        self.channels = list(CHANNELS)
        self.solver_fails = solver_fails
        #: ``(kind, command line)`` of everything the update path tried to run.
        self.update_commands: list[tuple[str, list[str]]] = []
        #: every command line the package manager would have run.
        self.solver_commands: list[list[str]] = []
        self.restarts = 0
        self.http_requests: list[str] = []
        self.downloads: list[tuple[str, str]] = []
        self.remote_listings = 0
        self.process_attempts: list[Any] = []

    # -- the update path ---------------------------------------------------------------------------------------------- #
    def run_command(self, updater, cmd):
        self.update_commands.append(("run_command", list(cmd)))
        return True, None

    def run_with_elevation(self, updater, cmd):
        self.update_commands.append(("run_with_elevation", list(cmd)))
        return True, None

    def run_update_in_separate_process(self, updater, cmd, callback=None):
        self.update_commands.append(("separate_process", list(cmd)))
        if callback:
            callback("Update process started in a separate window.")
        return True, None

    def schedule_restart(self, updater):
        self.restarts += 1

    def list_remote_versions(self, updater):
        self.remote_listings += 1
        return [dict(r) for r in self.releases]

    # -- the package manager -------------------------------------------------------------------------------------------- #
    def popen(self, manager, cmd):
        """The scripted answer of the solver to *cmd* (``ok, stdout, stderr, returncode``)."""
        cmd = list(cmd)
        self.solver_commands.append(cmd)
        if self.solver_fails and any(c in cmd for c in ("install", "remove", "update", "create", "--add", "--remove")):
            return False, "", "fake solver: the operation is refused", 1
        words = cmd[1:]
        if words[:1] == ["list"]:
            return True, json.dumps(self.installed), "", 0
        if words[:1] == ["search"]:
            return True, json.dumps(self.search_payload), "", 0
        if words[:2] == ["env", "list"]:
            return True, json.dumps({"envs": self.envs}), "", 0
        if words[:2] == ["env", "export"]:
            return True, "name: fake\nchannels:\n  - conda-forge\ndependencies:\n  - numpy=1.26.4\n", "", 0
        if words[:1] == ["config"] and "--show" in words:
            return True, json.dumps({"channels": self.channels}), "", 0
        return True, f"fake solver ran: {' '.join(words)}", "", 0

    # -- the network and processes -------------------------------------------------------------------------------------- #
    def urlopen(self, req, *args, **kwargs):
        url = getattr(req, "full_url", req)
        self.http_requests.append(str(url))
        if str(url).startswith("https://api.github.com/repos/"):
            return _Response(json.dumps(self.commits).encode("utf-8"))
        raise NetworkBlocked(f"the network is blocked: {url}")

    def urlretrieve(self, url, filename=None, reporthook=None, *args, **kwargs):
        """A download: the file appears (a few bytes) and the hook sees one block."""
        self.downloads.append((str(url), str(filename)))
        if not str(url).startswith("https://downloads.invalid/"):
            raise NetworkBlocked(f"the network is blocked: {url}")
        with open(filename, "wb") as handle:
            handle.write(b"fake package")
        if reporthook:
            reporthook(1, 12, 12)
        return filename, None

    def no_process(self, *args, **kwargs):
        self.process_attempts.append(args)
        raise NetworkBlocked(f"no process may be started: {args[:1]}")

    # -- wiring -------------------------------------------------------------------------------------------------------- #
    def install(self, patcher) -> "Fakes":
        """Put every fake in place with *patcher* (a ``pytest.MonkeyPatch``)."""
        import subprocess
        import urllib.request

        from chisurf.plugins.core.updater import updater as up

        fakes = self
        Updater, Manager = up.ChiSurfUpdater, up.PackageManager
        patcher.setattr(Updater, "_run_command", lambda s, cmd: fakes.run_command(s, cmd))
        patcher.setattr(Updater, "_run_with_elevation", lambda s, cmd: fakes.run_with_elevation(s, cmd))
        patcher.setattr(Updater, "_run_update_in_separate_process",
                        lambda s, cmd, callback=None: fakes.run_update_in_separate_process(s, cmd, callback))
        patcher.setattr(Updater, "_schedule_restart", lambda s: fakes.schedule_restart(s))
        patcher.setattr(Updater, "_list_remote_versions", lambda s: fakes.list_remote_versions(s))
        patcher.setattr(Manager, "_popen", lambda s, cmd: fakes.popen(s, cmd))
        # a solver path that does not depend on the machine
        patcher.setattr(Manager, "pkg_exe", lambda s: "/fake/bin/micromamba")
        patcher.setattr(urllib.request, "urlopen", fakes.urlopen)
        patcher.setattr(urllib.request, "urlretrieve", fakes.urlretrieve)
        patcher.setattr(subprocess, "Popen", fakes.no_process)
        patcher.setattr(subprocess, "run", fakes.no_process)
        return self

    # -- what a test asserts ------------------------------------------------------------------------------------------- #
    @property
    def mutating_solver_commands(self) -> list[list[str]]:
        """The solver command lines that would change an environment or a channel list (not the read-only ones)."""
        read_only = (["list"], ["search"], ["env", "list"], ["env", "export"], ["info"])
        out = []
        for cmd in self.solver_commands:
            words = cmd[1:]
            if words[:1] == ["config"] and "--show" in words:
                continue
            if any(words[: len(r)] == r for r in read_only):
                continue
            out.append(cmd)
        return out

    def expected_update_commands(self, file_path_or_name: str, *, sys_prefix: str | None = None) -> list[str]:
        """The line ``update_to_version`` builds for a package file (written out, not derived from the code under test)."""
        return ["/fake/bin/micromamba", "install", "--yes", "--update-deps", "--force-reinstall", "--prefix",
                sys_prefix or sys.prefix, file_path_or_name]

    @staticmethod
    def expected_latest_command(sys_prefix: str | None = None) -> list[str]:
        """The line ``update`` builds when it has no package file."""
        return ["/fake/bin/micromamba", "install", "-y", "--update-deps", "--prefix", sys_prefix or sys.prefix,
                "chisurf", "-c", "conda-forge", "-c", "defaults"]


def hermetic_environment(tmp_path, patcher) -> None:
    """Settings, MMFDB and HOME in a temporary folder: the user's own are never read or written."""
    patcher.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    patcher.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    patcher.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    patcher.setenv("HOME", str(tmp_path / "home"))
    os.makedirs(tmp_path / "settings", exist_ok=True)
    os.makedirs(tmp_path / "home", exist_ok=True)
