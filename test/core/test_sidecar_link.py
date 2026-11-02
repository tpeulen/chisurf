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


def test_every_step_shares_one_read_of_the_linked_photons(tmp_path):
    """Each burst step writes into the analysis container; the photons it links do not change.

    The read cache was keyed on the container's mtime, so every step re-read the whole photon
    file (0.3 s for 300 MB, once per step). It is keyed on the linked file now.
    """
    import shutil

    from chisurf.core.fio.fluorescence.burst_container import open_measurement
    from chisurf.core.fio.staging import open_tttr

    data = (
        Path(__file__).resolve().parents[2]
        / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc"
    )
    photons = tmp_path / "raw" / "m000.spc"
    photons.parent.mkdir()
    shutil.copy(data, photons)
    with open_measurement(photons, tmp_path / "analysis", raw_data="sidecar"):
        pass
    container = tmp_path / "analysis" / "m000.pto"
    first = open_tttr(str(container))
    assert len(first) > 0
    stamp = container.stat().st_mtime_ns + 5_000_000_000
    os.utime(container, ns=(stamp, stamp))  # a step wrote its result into the container
    assert open_tttr(str(container)) is first
    assert open_tttr(str(photons)) is first  # and the raw file is the same reading
    assert open_tttr(str(photons), "SPC-130") is first  # naming the type the file has, too
