"""Allocate image and associated point recordings without replacing existing data."""
import logging
from pathlib import Path

_log = logging.getLogger(__name__)

def validate_name(name: str) -> str:
    """A recording name is a single portable path component, not a path."""
    if not name or name in (".", "..") or any(c in name for c in "/\\:\x00"):
        raise ValueError("Recording name must be a single filename without path separators.")
    return name


def allocate_image(root: Path, name: str) -> tuple[str, Path]:
    """Reserve a new image directory atomically, including on repeated names."""
    name = validate_name(name)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1000000):
        stem = name if number == 1 else f"{name}_{number}"
        folder = root / stem
        try:
            folder.mkdir()
        except FileExistsError:
            continue
        return stem, folder / f"{stem}.ptu"
    raise OSError("could not allocate an image folder")


def point_paths(directories: list[Path], name: str) -> list[Path]:
    """Prepare destination directories; publication chooses a non-existing name atomically."""
    name = validate_name(name)
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    return [directory / f"{name}_p{i:03d}.ptu" for i, directory in enumerate(directories)]


def publish_point(staged: Path, target: Path) -> Path:
    """Link a completed recording into place without replacing a destination."""
    import os

    for number in range(1, 1000000):
        candidate = target if number == 1 else target.with_name(
            f"{target.stem}_{number}{target.suffix}")
        try:
            os.link(staged, candidate)
        except FileExistsError:
            continue
        try:
            staged.unlink()
            staged.parent.rmdir()
        except OSError:
            _log.warning("Published %s but could not remove staging %s", candidate, staged,
                         exc_info=True)
        return candidate
    raise OSError(f"could not publish recording; retained at {staged}")
