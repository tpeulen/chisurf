"""``sys.path`` must not carry another Python environment's runtime directories.

A second environment's ``site-packages`` on the path makes ``import`` succeed and
the *load* fail: the extension found there is linked against that environment's
native libraries, which the running interpreter's rpath cannot resolve. The
failure surfaces in the dynamic loader, naming a library rather than the
misconfiguration, so it is caught here instead.
"""

import subprocess
import sys
from pathlib import Path

from chisurf._bundled_packages import (
    _ALLOW_FOREIGN_VAR,
    drop_foreign_environment_paths,
    environment_prefix,
)

_REPO = Path(__file__).resolve().parents[1]


def _make_env(root: Path, py: str = "python3.12") -> Path:
    """Create an environment-shaped tree and return its site-packages."""
    site_packages = root / "lib" / py / "site-packages"
    site_packages.mkdir(parents=True)
    return site_packages


def test_environment_prefix_recognises_the_interpreter_layouts(tmp_path):
    """Only directories an interpreter itself produces count as runtime dirs."""
    prefix = tmp_path / "env"
    assert environment_prefix(_make_env(prefix)) == prefix
    assert environment_prefix(prefix / "lib" / "python3.12") == prefix
    win = prefix / "Lib" / "site-packages"
    assert environment_prefix(win) == prefix

    # A directory that merely has the name is not an environment.
    assert environment_prefix(tmp_path / "vendor" / "site-packages") is None
    assert environment_prefix(tmp_path / "src") is None


def test_foreign_site_packages_is_dropped(tmp_path, monkeypatch):
    foreign = str(_make_env(tmp_path / "other-env"))
    monkeypatch.delenv(_ALLOW_FOREIGN_VAR, raising=False)
    monkeypatch.setattr(sys, "path", [foreign, *sys.path])

    assert drop_foreign_environment_paths() == (foreign,)
    assert foreign not in sys.path


def test_foreign_standard_library_is_dropped(tmp_path, monkeypatch):
    """The worse case: another environment's stdlib shadows the running one's."""
    foreign = tmp_path / "other-env" / "lib" / "python3.12"
    foreign.mkdir(parents=True)
    monkeypatch.delenv(_ALLOW_FOREIGN_VAR, raising=False)
    monkeypatch.setattr(sys, "path", [str(foreign), *sys.path])

    assert drop_foreign_environment_paths() == (str(foreign),)


def test_this_interpreters_own_paths_are_kept(monkeypatch):
    """Whatever the running interpreter put there is its own and must survive."""
    monkeypatch.delenv(_ALLOW_FOREIGN_VAR, raising=False)
    before = list(sys.path)

    assert drop_foreign_environment_paths() == ()
    assert sys.path == before


def test_the_escape_hatch_keeps_everything(tmp_path, monkeypatch):
    foreign = str(_make_env(tmp_path / "other-env"))
    monkeypatch.setenv(_ALLOW_FOREIGN_VAR, "1")
    monkeypatch.setattr(sys, "path", [foreign, *sys.path])

    assert drop_foreign_environment_paths() == ()
    assert foreign in sys.path


def test_importing_chisurf_survives_a_foreign_environment_on_pythonpath(tmp_path):
    """The end-to-end shape of the real failure, as a subprocess.

    ``import chisurf`` has to clear the path itself: by the time any ChiSurf
    module is imported it is too late, since the first compiled extension has
    already been resolved against the wrong environment.
    """
    foreign = _make_env(tmp_path / "other-env")
    # Something an unrelated environment would provide, poisoned so that using it
    # is unambiguous — the real case is a linked extension, which cannot be faked.
    (foreign / "tttrlib.py").write_text(
        "raise ImportError('imported from the foreign environment')\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c",
         "import chisurf, sys;"
         f"assert {str(foreign)!r} not in sys.path;"
         "print('ok')"],
        capture_output=True, text=True, cwd=_REPO,
        env={"PYTHONPATH": str(foreign), "PATH": "/usr/bin:/bin",
             "HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout
