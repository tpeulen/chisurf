"""Public API of the burstwise_import plugin.

Thin, typed surface over the core importer so callers (CLI, GUI, RPC) share
one implementation: resolve the instrument file per stem, then hand the
folder to :func:`chisurf.core.fio.fluorescence.burstwise_import.convert_folder`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from chisurf.core.fio.fluorescence.burstwise_import import (
    ImportReport,
    convert_folder,
    parse_mti,
    scan_folder,
)

from .models import ImportSettings, settings_from_dict

__all__ = [
    "ImportSettings",
    "import_folder",
    "make_resolver",
    "settings_from_dict",
]

#: suffixes tried, in order, when resolving ``<stem>`` beside the folder
BESIDE_SUFFIXES = (".ht3", ".spc", ".ptu", ".sm", ".pt3", ".spc132")


def make_resolver(
    folder: str | Path,
    settings: ImportSettings,
    mti_paths: dict[str, float] | None = None,
) -> Callable[[str, dict], Path | None]:
    """Return ``stem -> instrument file`` for the configured source mode.

    ``mti_prefix`` remaps the original acquisition paths recorded in the
    ``.mti`` file; ``beside`` looks for ``<stem><suffix>`` next to the
    burstwise folder; ``none`` resolves nothing (stems are reported).
    """
    folder = Path(folder)

    def resolve(stem: str, mti: dict) -> Path | None:
        if settings.source_mode == "mti_prefix":
            source = _mti_path_for_stem(stem, mti or mti_paths or {})
            if source is None:
                return None
            return _remap(source, settings.mti_prefix_map)
        if settings.source_mode == "beside":
            # instrument files sit next to the burstwise folder (its parent),
            # occasionally inside it — check both
            for base in (folder.parent, folder):
                for suffix in BESIDE_SUFFIXES:
                    cand = base / f"{stem}{suffix}"
                    if cand.is_file():
                        return cand
            return None
        return None

    return resolve


def _mti_path_for_stem(stem: str, mti: dict[str, float]) -> str | None:
    """Return the .mti entry whose file name matches *stem*."""
    want = stem.lower()
    for path in mti:
        # .mti paths are Windows-shaped; split on both separators
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name.lower().startswith(want):
            return path
    return None


def _remap(path: str, prefix_map: dict[str, str]) -> Path | None:
    for old, new in prefix_map.items():
        if path.lower().startswith(old.lower()):
            # original .mti paths are Windows-shaped; normalise separators
            tail = path[len(old) :].replace("\\", "/")
            remapped = str(Path(new) / tail)
            return Path(remapped) if Path(remapped).is_file() else None
    return None


def import_folder(
    folder: str | Path,
    settings: ImportSettings | dict | None = None,
) -> ImportReport:
    """Convert one legacy burstwise folder; the plugin's main entry point."""
    if not isinstance(settings, ImportSettings):
        settings = settings_from_dict(settings)
    folder = Path(folder)
    inv = scan_folder(folder)
    mti_paths = parse_mti(inv["mti"]) if inv["mti"] else {}
    resolver = make_resolver(folder, settings, mti_paths)
    return convert_folder(
        folder,
        source_resolver=resolver,
        out_dir=settings.out_dir or (folder.parent if settings.out_dir is None else None),
        dry_run=settings.dry_run,
        raw_data=settings.raw_data,
    )
