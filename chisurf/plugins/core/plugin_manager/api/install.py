"""Install a plugin from a folder or a zip archive.

Three deliberate departures from what this replaced.

**It installs into the user directory.** The old importer copied into
``chisurf/plugins/`` -- the *shipped* tree, which on a packaged install is
root-owned. That is why it grew an OS-specific privilege-elevation path that
shelled out to ``osascript``/``pkexec``/``sudo`` with
``subprocess.Popen(..., shell=True)`` and an f-string holding a user-chosen
directory name: a folder called ``foo'; rm -rf ~;'`` executed. ``~/.chisurf/
plugins`` is already on ``chisurf.plugins.__path__``, is writable, and needs no
elevation -- so none of that machinery is needed and none of it is kept.

**Archives are extracted safely.** A zip entry named ``../../etc/thing`` escapes
the destination; every member is checked before anything is written.

**The manifest is validated before installing**, so a broken plugin is refused
with a reason instead of being copied in and then silently dropped by discovery.
"""

from __future__ import annotations

import json
import keyword
import pathlib
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, field


@dataclass
class InstallPlan:
    """What installing a source would do, and why it might not work.

    Attributes
    ----------
    source : pathlib.Path
        The folder or archive chosen.
    plugin_name : str
        Directory name the plugin will take.
    destination : pathlib.Path
        Where it will land.
    overwrites : bool
        Whether an existing plugin of that name will be replaced.
    problems : list of str
        Blocking reasons. Empty means installable.
    warnings : list of str
        Non-blocking notes (a missing manifest, say).

    """

    source: pathlib.Path
    plugin_name: str
    destination: pathlib.Path
    overwrites: bool = False
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the install can proceed."""
        return not self.problems


def user_plugin_dir() -> pathlib.Path:
    """The writable plugin directory (``~/.chisurf/plugins``)."""
    from chisurf.plugins import user_plugins_dir

    return pathlib.Path(user_plugins_dir)


def _safe_members(archive: zipfile.ZipFile) -> list[str]:
    """Archive members that stay inside the extraction root.

    Raises
    ------
    ValueError
        If any member would escape, naming it. Refusing the whole archive is
        the right call: a zip containing a traversal entry is not one a user
        meant to install.

    """
    names = []
    seen: set[str] = set()
    file_identities: set[str] = set()
    directory_spellings: dict[str, str] = {}
    for info in archive.infolist():
        name = info.orig_filename
        target = pathlib.PurePosixPath(name)
        parts = name.rstrip("/").split("/")
        if target.is_absolute() or ".." in parts:
            raise ValueError(f"archive member escapes the destination: {name!r}")
        if any(
            part in {"", "."}
            or part.endswith((".", " "))
            or pathlib.PureWindowsPath(part).is_reserved()
            or any(ord(c) < 32 or c in '<>:"|?*\\' for c in part)
            for part in parts
        ):
            raise ValueError(f"archive member has an unsafe or aliased path: {name!r}")
        mode = stat.S_IFMT(info.external_attr >> 16)
        if mode not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise ValueError(f"archive member is a link or special file: {name!r}")
        # Match zipfile extraction: directory paths end in a slash, regardless of mode bits.
        is_directory = info.is_dir()
        directory_parts = parts if is_directory else parts[:-1]
        for length in range(1, len(directory_parts) + 1):
            spelling = "/".join(directory_parts[:length])
            directory_identity = unicodedata.normalize("NFC", spelling).casefold()
            if directory_identity in file_identities:
                raise ValueError(f"archive contains a file/directory identity conflict: {name!r}")
            previous = directory_spellings.get(directory_identity)
            if previous is not None and previous != spelling:
                raise ValueError(f"archive contains aliased directory prefixes: {name!r}")
            directory_spellings[directory_identity] = spelling
        identity = unicodedata.normalize("NFC", name.rstrip("/")).casefold()
        if not is_directory:
            if identity in directory_spellings:
                raise ValueError(f"archive contains a file/directory identity conflict: {name!r}")
            file_identities.add(identity)
        if identity in seen:
            raise ValueError(f"archive contains duplicate or aliased members: {name!r}")
        seen.add(identity)
        names.append(info.filename)
    return names


def _plugin_root(tree: pathlib.Path) -> pathlib.Path | None:
    """The directory holding ``__init__.py`` within an extracted tree.

    Archives are commonly wrapped in one extra folder (``my-plugin-main/``), so
    the package is looked for at the top and one level down before giving up.
    """
    if (tree / "__init__.py").is_file():
        return tree
    candidates = [
        child
        for child in sorted(tree.iterdir())
        if child.is_dir() and (child / "__init__.py").is_file()
    ]
    if len(candidates) > 1:
        raise ValueError("archive contains multiple plugin packages; choose one package")
    return candidates[0] if candidates else None


def inspect_source(source: str | pathlib.Path) -> InstallPlan:
    """Work out what installing *source* would do, without doing it.

    Parameters
    ----------
    source : str or pathlib.Path
        A plugin folder, or a ``.zip`` containing one.

    Returns
    -------
    InstallPlan
        Always returned -- check :attr:`InstallPlan.ok`. Nothing is written.

    """
    source = pathlib.Path(source)
    destination_root = user_plugin_dir()

    if source.is_symlink():
        return InstallPlan(
            source,
            "",
            destination_root,
            problems=["plugin source must not be a symbolic link"],
        )
    if not source.exists():
        return InstallPlan(source, "", destination_root, problems=[f"{source} does not exist"])

    if source.is_file():
        if source.suffix.lower() != ".zip":
            return InstallPlan(
                source,
                "",
                destination_root,
                problems=["only a plugin folder or a .zip archive can be installed"],
            )
        return _inspect_archive(source, destination_root)
    return _inspect_folder(source, source.name, destination_root)


def _archive_package_name(tree: pathlib.Path, candidate: str) -> str:
    """Keep importable package names; infer identity only for distribution wrappers."""
    if candidate.isidentifier() and not keyword.iskeyword(candidate):
        return candidate
    from chisurf.core.plugin.manifest import load_manifest

    manifest = load_manifest(tree / "manifest.json")
    if manifest is None:
        return candidate
    names: set[str] = set()
    for entrypoint in (
        manifest.entrypoints.gui,
        manifest.entrypoints.cli,
        manifest.entrypoints.services,
        manifest.entrypoints.emtk,
    ):
        if not entrypoint:
            continue
        module = entrypoint.split("=", 1)[-1].split(":", 1)[0].strip()
        prefix = "chisurf.plugins."
        if module.startswith(prefix):
            name = module[len(prefix) :].split(".", 1)[0]
            if name.isidentifier() and not keyword.iskeyword(name):
                names.add(name)
    if len(names) > 1:
        raise ValueError("archive wrapper has ambiguous plugin package identities")
    if names:
        return next(iter(names))
    if manifest.id.isidentifier() and not keyword.iskeyword(manifest.id):
        return manifest.id
    return candidate


def _inspect_archive(source: pathlib.Path, destination_root: pathlib.Path) -> InstallPlan:
    """Plan an install from a zip, without extracting it for real."""
    try:
        with zipfile.ZipFile(source) as archive:
            _safe_members(archive)
            with tempfile.TemporaryDirectory() as tmp:
                archive.extractall(tmp)
                root = _plugin_root(pathlib.Path(tmp))
                if root is None:
                    return InstallPlan(
                        source,
                        "",
                        destination_root,
                        problems=["the archive has no package with an __init__.py"],
                    )
                candidate = source.stem if root == pathlib.Path(tmp) else root.name
                package_name = _archive_package_name(root, candidate)
                plan = _inspect_folder(root, package_name, destination_root)
                if package_name != candidate:
                    plan.warnings.append(
                        f"distribution wrapper {candidate!r} installs as package {package_name!r}"
                    )
                # The temporary tree is about to vanish; the caller re-extracts.
                plan.source = source
                return plan
    except zipfile.BadZipFile:
        return InstallPlan(source, "", destination_root, problems=["not a readable zip archive"])
    except (ValueError, OSError, RuntimeError, NotImplementedError) as exc:
        return InstallPlan(source, "", destination_root, problems=[str(exc)])


def _inspect_folder(
    tree: pathlib.Path, plugin_name: str, destination_root: pathlib.Path
) -> InstallPlan:
    """Plan an install from an unpacked plugin directory."""
    plan = InstallPlan(
        source=tree,
        plugin_name=plugin_name,
        destination=destination_root / plugin_name,
    )

    if not plugin_name.isidentifier() or keyword.iskeyword(plugin_name):
        plan.problems.append(
            "plugin package name must be a Python identifier, not a manifest id or path"
        )
        return plan
    if tree.is_symlink() or any(path.is_symlink() for path in tree.rglob("*")):
        plan.problems.append("plugin source must not contain symbolic links")
        return plan
    if not (tree / "__init__.py").is_file():
        plan.problems.append("not a plugin: no __init__.py in the chosen folder")
        return plan

    manifest_path = tree / "manifest.json"
    if not manifest_path.is_file():
        plan.warnings.append(
            "no manifest.json -- the plugin will be read through the legacy "
            "__init__.py scan and cannot declare dependencies or maturity"
        )
    else:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            plan.problems.append(f"manifest.json is not readable JSON: {exc}")
            return plan
        from chisurf.core.plugin.manifest import validate_manifest

        errors = validate_manifest(data)
        if errors:
            plan.problems.append("manifest.json is invalid: " + "; ".join(errors))
            return plan

    plan.overwrites = plan.destination.exists()
    try:
        _validate_destination(plan.destination, plugin_name)
    except ValueError as exc:
        plan.problems.append(str(exc))
    return plan


def _validate_destination(destination: pathlib.Path, package_name: str) -> None:
    """A mutable install plan never grants authority outside the user root."""
    root = user_plugin_dir().resolve()
    if (
        not package_name.isidentifier()
        or keyword.iskeyword(package_name)
        or destination.name != package_name
        or destination.parent.resolve() != root
        or destination.is_symlink()
        or (destination.exists() and not destination.is_dir())
    ):
        raise ValueError(
            "destination must be a real package directory directly inside the user plugin directory"
        )


def install(plan: InstallPlan) -> pathlib.Path:
    """Carry out *plan*.

    Parameters
    ----------
    plan : InstallPlan
        A plan whose :attr:`~InstallPlan.ok` is true.

    Returns
    -------
    pathlib.Path
        The installed plugin directory.

    Raises
    ------
    ValueError
        If the plan is not installable -- the problems are in the message.

    """
    if not plan.ok:
        raise ValueError("; ".join(plan.problems))

    _validate_destination(plan.destination, plan.plugin_name)
    current = inspect_source(plan.source)
    if not current.ok:
        raise ValueError("; ".join(current.problems))
    if (
        current.plugin_name != plan.plugin_name
        or current.destination.resolve() != plan.destination.resolve()
        or current.overwrites != plan.overwrites
    ):
        raise ValueError("install plan is stale; inspect the source and confirm replacement again")
    source = plan.source.resolve()
    destination = plan.destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("source and destination must not overlap")
    plan.destination.parent.mkdir(parents=True, exist_ok=True)

    if plan.source.is_file():
        with zipfile.ZipFile(plan.source) as archive:
            _safe_members(archive)
            with tempfile.TemporaryDirectory() as tmp:
                archive.extractall(tmp)
                root = _plugin_root(pathlib.Path(tmp))
                if root is None:
                    raise ValueError("the archive has no package with an __init__.py")
                _replace(root, plan.destination)
    else:
        _replace(plan.source, plan.destination)

    from chisurf.plugins import invalidate_plugin_cache

    invalidate_plugin_cache()
    return plan.destination


def _replace(source: pathlib.Path, destination: pathlib.Path) -> None:
    """Stage a complete copy before replacing an installed tree.

    The staging and backup directories are unique and hidden from discovery.
    Copy errors cannot alter an existing plugin or leave a partial new plugin.
    """
    staging = pathlib.Path(tempfile.mkdtemp(prefix=".plugin-install-", dir=destination.parent))
    staged_tree = staging / "package"
    backup = staging / "previous"
    preserve_backup = False
    try:
        shutil.copytree(source, staged_tree, symlinks=True)
        staged_plan = _inspect_folder(staged_tree, destination.name, destination.parent)
        if not staged_plan.ok:
            raise ValueError("; ".join(staged_plan.problems))
        _validate_destination(destination, destination.name)
        if destination.exists():
            destination.rename(backup)
        staged_tree.rename(destination)
    except BaseException:
        if backup.exists():
            try:
                backup.rename(destination)
            except BaseException as exc:
                preserve_backup = True
                raise OSError(
                    f"Plugin rollback failed; original tree retained at {backup}"
                ) from exc
        raise
    finally:
        if not preserve_backup:
            shutil.rmtree(staging, ignore_errors=True)


def uninstall(package_dir: str | pathlib.Path) -> None:
    """Remove an installed **user** plugin.

    Raises
    ------
    ValueError
        If the directory is not inside the user plugin directory. Built-in
        plugins ship with the application and are disabled, never deleted.

    """
    package_dir = pathlib.Path(package_dir)
    if package_dir.parent.resolve() != user_plugin_dir().resolve():
        raise ValueError(
            "only plugins directly inside the user plugin directory can be uninstalled; "
            "switch a built-in plugin off instead"
        )
    _validate_destination(package_dir, package_dir.name)
    shutil.rmtree(package_dir)

    from chisurf.plugins import invalidate_plugin_cache

    invalidate_plugin_cache()
