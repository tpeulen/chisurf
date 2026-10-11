"""Executable regressions for plugin installation integrity; never touch real user plugins."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisurf.plugins.core.plugin_manager.api import install as installer


def _plugin(root: Path, name: str = "sample_tool", plugin_id: str | None = None) -> Path:
    tree = root / name
    tree.mkdir(parents=True)
    (tree / "__init__.py").write_text('name = "Tools:Sample"\n', encoding="utf-8")
    (tree / "manifest.json").write_text(
        json.dumps({"id": plugin_id or name, "version": "1.0", "display_name": "Sample"}),
        encoding="utf-8",
    )
    return tree


@pytest.mark.parametrize("existing", [False, True])
def test_failed_partial_copy_preserves_original_tree(tmp_path, monkeypatch, existing):
    user_root = tmp_path / "user"
    user_root.mkdir()
    source = _plugin(tmp_path / "source")
    destination = user_root / source.name
    if existing:
        destination.mkdir()
        (destination / "old.txt").write_bytes(b"original plugin\x00")
    unrelated = user_root / (source.name + ".replacing")
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("unrelated", encoding="utf-8")
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    plan = installer.inspect_source(source)
    assert plan.ok

    def partial_failure(src, dst, **kwargs):
        Path(dst).mkdir()
        (Path(dst) / "partial.txt").write_text("incomplete", encoding="utf-8")
        raise OSError("injected copy failure")

    monkeypatch.setattr(installer.shutil, "copytree", partial_failure)
    with pytest.raises(OSError, match="injected copy failure"):
        installer.install(plan)
    if existing:
        assert list(destination.iterdir()) == [destination / "old.txt"]
        assert (destination / "old.txt").read_bytes() == b"original plugin\x00"
    else:
        assert not destination.exists(), "failed fresh install was left discoverable"
    assert (unrelated / "keep.txt").read_text(encoding="utf-8") == "unrelated"
    assert set(user_root.iterdir()) == ({unrelated, destination} if existing else {unrelated})


@pytest.mark.parametrize(
    "source_kind",
    ["folder", "wrapped-zip", "flat-zip", "distribution-wrapper", "flat-distribution"],
)
def test_install_preserves_package_name_distinct_from_manifest_id(
    tmp_path, monkeypatch, source_kind
):
    import importlib
    import sys
    import zipfile

    import chisurf.plugins
    from chisurf.core.plugin.registry import PluginRegistry, _DefaultLoader

    user_root = tmp_path / "user"
    source = _plugin(tmp_path / "source", name="integrity_sample", plugin_id="different_plugin_id")
    (source / "__init__.py").write_text(
        "def factory(): return 'working entrypoint'\n", encoding="utf-8"
    )
    manifest_path = source / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["entrypoints"] = {"emtk": "chisurf.plugins.integrity_sample:factory"}
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    if source_kind != "folder":
        archive = tmp_path / (
            "release-bundle.zip" if source_kind == "flat-distribution" else "integrity_sample.zip"
        )
        with zipfile.ZipFile(archive, "w") as zf:
            for path in source.iterdir():
                prefix = Path("integrity_sample") if source_kind == "wrapped-zip" else Path()
                if source_kind == "distribution-wrapper":
                    prefix = Path("release-bundle-main")
                zf.write(path, (prefix / path.name).as_posix())
        source = archive
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    plan = installer.inspect_source(source)
    assert plan.ok, plan.problems
    assert plan.plugin_name == "integrity_sample", "manifest ID is not a Python package name"
    installed = installer.install(plan)
    assert installed == user_root / "integrity_sample"
    manifests = PluginRegistry().discover([user_root])
    assert [m.id for m in manifests] == ["different_plugin_id"]
    monkeypatch.setattr(chisurf.plugins, "__path__", [str(user_root)])
    module_name = "chisurf.plugins.integrity_sample"
    try:
        importlib.invalidate_caches()
        assert _DefaultLoader().load(data["entrypoints"]["emtk"])() == "working entrypoint"
    finally:
        sys.modules.pop(module_name, None)
        vars(chisurf.plugins).pop("integrity_sample", None)
    installer.uninstall(installed)
    assert not installed.exists()


@pytest.mark.parametrize(
    "boundary",
    [
        "outside",
        "symlink-destination",
        "symlink-source",
        "self-copy",
        "invalid-name",
        "stale-manifest",
        "new-destination",
    ],
)
def test_install_revalidates_plan_and_paths_before_mutating_existing_tree(
    tmp_path, monkeypatch, boundary
):
    user_root = tmp_path / "user"
    user_root.mkdir()
    source = _plugin(tmp_path / "source")
    destination = user_root / source.name
    destination.mkdir()
    (destination / "old.txt").write_text("original", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("outside", encoding="utf-8")
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    plan = installer.inspect_source(source)
    if boundary == "outside":
        plan.destination = outside
    elif boundary == "symlink-destination":
        (destination / "old.txt").unlink()
        destination.rmdir()
        destination.symlink_to(outside, target_is_directory=True)
    elif boundary == "symlink-source":
        (source / "linked.txt").symlink_to(outside / "keep.txt")
    elif boundary == "self-copy":
        plan.source = destination
    elif boundary == "invalid-name":
        plan.plugin_name = "../outside"
        plan.destination = outside
    elif boundary == "stale-manifest":
        (source / "manifest.json").write_text("[]", encoding="utf-8")
    elif boundary == "new-destination":
        plan.overwrites = False
    with pytest.raises(ValueError):
        installer.install(plan)
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "outside"
    if boundary == "symlink-destination":
        assert destination.is_symlink()
    else:
        assert (destination / "old.txt").read_text(encoding="utf-8") == "original"
    assert not list(user_root.glob(".plugin-install-*"))


def test_staged_manifest_is_validated_before_replacing_old_plugin(tmp_path, monkeypatch):
    user_root = tmp_path / "user"
    user_root.mkdir()
    source = _plugin(tmp_path / "source")
    destination = user_root / source.name
    destination.mkdir()
    (destination / "old.txt").write_text("original", encoding="utf-8")
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    plan = installer.inspect_source(source)
    copytree = installer.shutil.copytree

    def changed_during_copy(src, dst, **kwargs):
        result = copytree(src, dst, **kwargs)
        (Path(dst) / "manifest.json").write_text("[]", encoding="utf-8")
        return result

    monkeypatch.setattr(installer.shutil, "copytree", changed_during_copy)
    with pytest.raises(ValueError, match="manifest"):
        installer.install(plan)
    assert (destination / "old.txt").read_text(encoding="utf-8") == "original"
    assert set(user_root.iterdir()) == {destination}


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../escape.py",
        "/absolute.py",
        "..\\escape.py",
        "C:/escape.py",
        "sample_tool/./alias.py",
        "sample_tool//alias.py",
        "sample_tool/file:stream",
        "sample_tool/trailing.",
        "sample_tool/trailing ",
        "sample_tool/CON.py",
    ],
)
def test_unsafe_archive_paths_are_rejected_portably(tmp_path, monkeypatch, unsafe_name):
    import zipfile

    user_root = tmp_path / "user"
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    archive = tmp_path / "sample_tool.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("sample_tool/__init__.py", "")
        zf.writestr(unsafe_name, "unsafe")
    plan = installer.inspect_source(archive)
    assert not plan.ok, plan
    assert not user_root.exists()


@pytest.mark.parametrize("kind", ["duplicate", "case-alias", "symlink", "ambiguous-packages"])
def test_archive_identity_is_unambiguous(tmp_path, monkeypatch, kind):
    import stat
    import warnings
    import zipfile

    user_root = tmp_path / "user"
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    archive = tmp_path / "sample_tool.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("sample_tool/__init__.py", "")
        if kind == "duplicate":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                zf.writestr("sample_tool/__init__.py", "different")
        elif kind == "case-alias":
            zf.writestr("sample_tool/__INIT__.py", "different")
        elif kind == "symlink":
            info = zipfile.ZipInfo("sample_tool/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "../../outside")
        else:
            zf.writestr("other_tool/__init__.py", "")
    plan = installer.inspect_source(archive)
    assert not plan.ok, plan
    assert not user_root.exists()


def test_invalid_utf8_manifest_is_reported_as_a_plan_problem(tmp_path, monkeypatch):
    source = _plugin(tmp_path / "source")
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: tmp_path / "user")
    (source / "manifest.json").write_bytes(b"\xff")
    plan = installer.inspect_source(source)
    assert not plan.ok
    assert "manifest.json" in plan.problems[0]


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_promotion_failure_restores_or_preserves_old_tree(tmp_path, monkeypatch, rollback_fails):
    user_root = tmp_path / "user"
    user_root.mkdir()
    source = _plugin(tmp_path / "source")
    destination = user_root / source.name
    destination.mkdir()
    (destination / "old.txt").write_bytes(b"original")
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    plan = installer.inspect_source(source)
    rename = Path.rename

    def fail_promotion(path, target):
        if path.name == "package" or (rollback_fails and path.name == "previous"):
            raise OSError("injected rename failure")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_promotion)
    with pytest.raises(OSError) as exc:
        installer.install(plan)
    if rollback_fails:
        backups = list(user_root.glob(".plugin-install-*/previous"))
        assert len(backups) == 1
        assert (backups[0] / "old.txt").read_bytes() == b"original"
        assert str(backups[0]) in str(exc.value)
        assert not destination.exists()
    else:
        assert (destination / "old.txt").read_bytes() == b"original"
        assert set(user_root.iterdir()) == {destination}


@pytest.mark.parametrize("target_kind", ["root", "nested", "sibling-symlink"])
def test_uninstall_cannot_delete_another_tree_through_an_alias(tmp_path, monkeypatch, target_kind):
    user_root = tmp_path / "user"
    tree = _plugin(user_root)
    nested = tree / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    if target_kind == "root":
        target = user_root
    elif target_kind == "nested":
        target = nested
    else:
        target = user_root / "alias"
        target.symlink_to(tree, target_is_directory=True)
    with pytest.raises(ValueError, match="user plugin directory"):
        installer.uninstall(target)
    assert (tree / "__init__.py").exists()
    assert (nested / "keep.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("prefixes", [("data", "DATA"), ("café", "cafe\u0301")])
def test_archive_directory_prefix_aliases_are_rejected(tmp_path, monkeypatch, prefixes):
    import zipfile

    user_root = tmp_path / "user"
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    archive = tmp_path / "sample_tool.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("sample_tool/__init__.py", "")
        zf.writestr(f"sample_tool/{prefixes[0]}/first.py", "")
        zf.writestr(f"sample_tool/{prefixes[1]}/second.py", "")
    plan = installer.inspect_source(archive)
    assert not plan.ok, "directory prefixes with aliased identities must not be merged"
    assert not user_root.exists()


@pytest.mark.parametrize("stage", ["inspect", "mutated-plan"])
def test_zip_source_symlink_is_rejected(tmp_path, monkeypatch, stage):
    import zipfile

    user_root = tmp_path / "user"
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    archive = tmp_path / "sample_tool.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("sample_tool/__init__.py", "")
    alias = tmp_path / "aliases" / "sample_tool.zip"
    alias.parent.mkdir()
    alias.symlink_to(archive)
    if stage == "inspect":
        assert not installer.inspect_source(alias).ok
    else:
        plan = installer.inspect_source(archive)
        assert plan.ok
        plan.source = alias
        with pytest.raises(ValueError, match="symbolic link"):
            installer.install(plan)
    assert not user_root.exists()


@pytest.mark.parametrize("spellings", [("data", "data"), ("data", "DATA"), ("café", "cafe\u0301")])
@pytest.mark.parametrize("reverse", [False, True])
def test_file_directory_zip_identity_conflict_is_rejected_before_extraction(
    tmp_path, spellings, reverse
):
    import zipfile

    archive = tmp_path / "sample_tool.zip"
    members = [f"sample_tool/{spellings[0]}", f"sample_tool/{spellings[1]}/child.py"]
    if reverse:
        members.reverse()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("sample_tool/__init__.py", "")
        for member in members:
            zf.writestr(member, "regular file")
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(ValueError, match="file.*directory|directory.*file"):
            installer._safe_members(zf)


def test_interrupt_after_old_tree_move_restores_original(tmp_path, monkeypatch):
    user_root = tmp_path / "user"
    user_root.mkdir()
    source = _plugin(tmp_path / "source")
    destination = user_root / source.name
    destination.mkdir()
    (destination / "old.txt").write_bytes(b"original")
    monkeypatch.setattr(installer, "user_plugin_dir", lambda: user_root)
    plan = installer.inspect_source(source)
    rename = Path.rename

    def interrupted_move(path, target):
        result = rename(path, target)
        if path == destination and Path(target).name == "previous":
            raise KeyboardInterrupt("interrupted after old tree moved")
        return result

    monkeypatch.setattr(Path, "rename", interrupted_move)
    with pytest.raises(KeyboardInterrupt, match="after old tree"):
        installer.install(plan)
    assert (destination / "old.txt").read_bytes() == b"original"
    assert set(user_root.iterdir()) == {destination}


def test_zip_directory_mode_without_slash_uses_actual_extraction_identity(tmp_path):
    import stat
    import zipfile

    archive = tmp_path / "sample_tool.zip"
    advertised_directory = zipfile.ZipInfo("sample_tool/data")
    advertised_directory.create_system = 3
    advertised_directory.external_attr = (stat.S_IFDIR | 0o755) << 16
    assert not advertised_directory.is_dir(), "zipfile extracts this path as a file"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("sample_tool/__init__.py", "")
        zf.writestr(advertised_directory, "actually a file")
        zf.writestr("sample_tool/data/child.py", "")
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(ValueError, match="file.*directory|directory.*file"):
            installer._safe_members(zf)
