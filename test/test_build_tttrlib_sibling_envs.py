"""Extra developer environments get their own tttrlib build, never a symlink.

``build-tttrlib`` used to *symlink* the pixi environment's tttrlib into the
``arm64`` conda env. The pixi environment is detached into
``~/Library/Caches/rattler``, which macOS purges under disk pressure — and when
it did (2026-10-05), every chisurf process in ``arm64`` lost tttrlib mid-run
(``FileNotFoundError: .../site-packages/tttrlib/__init__.py``). A link is also
only loadable while both envs agree on native libraries (HDF5), which they
need not. So each extra env gets a build against its own libraries, installed
as real files.
"""
import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location(
    "build_tttrlib",
    pathlib.Path(__file__).resolve().parents[1] / "build_tools" / "build_tttrlib.py",
)
build_tttrlib = importlib.util.module_from_spec(spec)
sys.modules["build_tttrlib"] = build_tttrlib
spec.loader.exec_module(build_tttrlib)


def _fake_env(root: pathlib.Path) -> pathlib.Path:
    prefix = root / "envs" / "dev"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / "python").write_text("")
    (prefix / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    return prefix


def test_every_extra_env_gets_its_own_build(tmp_path, monkeypatch):
    prefix = _fake_env(tmp_path)
    built = []
    monkeypatch.setattr(build_tttrlib, "_link_targets", lambda: [prefix])
    monkeypatch.setattr(build_tttrlib, "_build_into", lambda p: built.append(p) or True)
    assert build_tttrlib.link_build() is True
    assert built == [prefix]
    assert not hasattr(build_tttrlib, "_link_into"), "no symlink path may remain"


def test_a_failed_env_build_fails_the_task(tmp_path, monkeypatch):
    prefix = _fake_env(tmp_path)
    monkeypatch.setattr(build_tttrlib, "_link_targets", lambda: [prefix])
    monkeypatch.setattr(build_tttrlib, "_build_into", lambda p: False)
    assert build_tttrlib.link_build() is False


def test_dangling_links_from_the_old_scheme_are_cleared(tmp_path):
    sp = _fake_env(tmp_path) / "lib" / "python3.12" / "site-packages"
    gone = tmp_path / "purged-cache" / "tttrlib"
    for name in ("tttrlib", "tttrlib-0.27.0.dist-info", "tttrlib.py", "_tttrlib.cpython-312-darwin.so"):
        (sp / name).symlink_to(gone / name)
    (sp / "numpy").mkdir()
    build_tttrlib._clear_tttrlib(sp)
    assert sorted(p.name for p in sp.iterdir()) == ["numpy"]
