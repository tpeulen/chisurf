"""The OKF bundle is prose: no captures, archives or arrays are tracked under ``okf/``.

The Qt->emtk migration kept its evidence (before/after PNGs, zips of source snapshots, control
inventories, reports) in ``okf/validation/`` and ``okf/plugins/emtk-ports/`` -- about a gigabyte
that nobody read once the ports were accepted. The migration closed on 2026-10-20 and both trees
were removed; ``.gitignore`` keeps them out, and this guard fails if a binary is committed under
``okf/`` anyway (``git add -f`` passes the ignore file). A test that needs reference values keeps
them as text beside itself (``<plugin>/test/data/``), not in the knowledge bundle.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Extensions that are never knowledge: images, archives, arrays, raw data.
BINARY = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".pdf",
    ".zip", ".gz", ".tgz", ".xz", ".7z",
    ".npy", ".npz", ".dat", ".h5", ".hdf5", ".ptu", ".spc", ".sqlite",
}
#: Trees that held migration evidence; nothing may be tracked there again.
RETIRED_TREES = ("okf/validation/", "okf/plugins/emtk-ports/")
#: Paths under okf/ allowed to be binary. Empty: the bundle needs none. Never grow this to land
#: evidence; put reference data beside the test that reads it.
ALLOWED: frozenset[str] = frozenset()


def _tracked_okf_files() -> list[str]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "okf"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def test_no_binary_is_tracked_under_okf():
    found = sorted(
        p for p in _tracked_okf_files() if Path(p).suffix.lower() in BINARY and p not in ALLOWED
    )
    assert not found, f"binary files tracked under okf/ (keep evidence out of the bundle): {found[:20]}"


def test_the_retired_evidence_trees_stay_empty():
    found = sorted(p for p in _tracked_okf_files() if p.startswith(RETIRED_TREES))
    assert not found, f"files tracked in a retired evidence tree: {found[:20]}"


@pytest.mark.parametrize(
    "path", ["okf/validation/x.png", "okf/plugins/emtk-ports/x/REPORT.md", "okf/plans/x.zip"]
)
def test_the_ignore_file_keeps_the_evidence_out(path):
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path], cwd=ROOT, capture_output=True
    )
    assert ignored.returncode == 0, f".gitignore no longer covers {path}"
