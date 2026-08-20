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
import pathlib
import shutil
import tempfile
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
    for name in archive.namelist():
        target = pathlib.PurePosixPath(name)
        if target.is_absolute() or ".." in target.parts:
            raise ValueError(f"archive member escapes the destination: {name!r}")
        names.append(name)
    return names


def _plugin_root(tree: pathlib.Path) -> pathlib.Path | None:
    """The directory holding ``__init__.py`` within an extracted tree.

    Archives are commonly wrapped in one extra folder (``my-plugin-main/``), so
    the package is looked for at the top and one level down before giving up.
    """
    if (tree / "__init__.py").is_file():
        return tree
    children = [c for c in sorted(tree.iterdir()) if c.is_dir()]
    for child in children:
        if (child / "__init__.py").is_file():
            return child
    return None


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

    if not source.exists():
        return InstallPlan(source, "", destination_root, problems=[f"{source} does not exist"])

    if source.is_file():
        if source.suffix.lower() != ".zip":
            return InstallPlan(
                source, "", destination_root,
                problems=["only a plugin folder or a .zip archive can be installed"],
            )
        return _inspect_archive(source, destination_root)
    return _inspect_folder(source, source.name, destination_root)


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
                        source, "", destination_root,
                        problems=["the archive has no package with an __init__.py"],
                    )
                plan = _inspect_folder(root, root.name, destination_root)
                # The temporary tree is about to vanish; the caller re-extracts.
                plan.source = source
                return plan
    except zipfile.BadZipFile:
        return InstallPlan(source, "", destination_root, problems=["not a readable zip archive"])
    except ValueError as exc:
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
        except (OSError, json.JSONDecodeError) as exc:
            plan.problems.append(f"manifest.json is not readable JSON: {exc}")
            return plan
        from chisurf.core.plugin.manifest import validate_manifest

        errors = validate_manifest(data)
        if errors:
            plan.problems.append("manifest.json is invalid: " + "; ".join(errors))
            return plan
        if data.get("id"):
            plan.plugin_name = str(data["id"])
            plan.destination = destination_root / plan.plugin_name

    plan.overwrites = plan.destination.exists()
    return plan


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
    """Copy *source* over *destination*, replacing it atomically enough.

    The previous directory is moved aside first and only removed once the copy
    succeeded, so a failure part-way leaves the old plugin in place instead of
    a half-written one.
    """
    backup = None
    if destination.exists():
        backup = destination.with_name(destination.name + ".replacing")
        if backup.exists():
            shutil.rmtree(backup)
        destination.rename(backup)
    try:
        shutil.copytree(source, destination)
    except Exception:
        if backup is not None and not destination.exists():
            backup.rename(destination)
        raise
    else:
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)


def uninstall(package_dir: str | pathlib.Path) -> None:
    """Remove an installed **user** plugin.

    Raises
    ------
    ValueError
        If the directory is not inside the user plugin directory. Built-in
        plugins ship with the application and are disabled, never deleted.

    """
    package_dir = pathlib.Path(package_dir).resolve()
    root = user_plugin_dir().resolve()
    if root not in package_dir.parents:
        raise ValueError(
            "only plugins installed in the user plugin directory can be removed; "
            "switch a built-in plugin off instead"
        )
    shutil.rmtree(package_dir)

    from chisurf.plugins import invalidate_plugin_cache

    invalidate_plugin_cache()
