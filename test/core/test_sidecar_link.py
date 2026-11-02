"""A relative sidecar link is found whichever spelling of the container's folder reads it.

On macOS /var and /tmp are symlinks into /private: a link counted from /var/folders/... landed one
level off when read from /private/var/folders/... (or through Path.resolve), and a project's
analysis container then had no photons -- every step after Burst Selection failed to open them.
"""

import os
from pathlib import Path

from chisurf.core.fio.pto import _follow_link


def test_the_link_is_found_from_the_symlinked_and_the_real_folder(tmp_path):
    real = tmp_path / "private" / "var" / "folders" / "a"
    real.mkdir(parents=True)
    alias_root = tmp_path / "var"
    alias_root.symlink_to(tmp_path / "private" / "var")
    alias = alias_root / "folders" / "a"
    photons = tmp_path / "data" / "m.ptu"
    photons.parent.mkdir()
    photons.write_bytes(b"x")
    link = Path(os.path.relpath(photons, alias))  # made from the symlinked spelling
    assert _follow_link(alias, link) == photons


def test_a_link_made_from_var_is_read_from_private_var(tmp_path):
    """The macOS case itself: written from /var/folders/..., read from /private/var/folders/..."""
    import pytest

    if not str(tmp_path).startswith("/private/var/"):
        pytest.skip("needs macOS's /var -> /private/var")
    container = tmp_path / "analysis" / "uid"
    container.mkdir(parents=True)
    photons = Path("/private/tmp") / f"chisurf-link-test-{os.getpid()}.ptu"
    photons.write_bytes(b"x")
    try:
        written_from = Path(str(container)[len("/private"):])
        link = Path(os.path.relpath(photons, written_from))
        assert _follow_link(container, link) == photons
        assert _follow_link(written_from, link) == photons
    finally:
        photons.unlink()
