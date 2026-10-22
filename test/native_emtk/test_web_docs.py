"""The web release's documentation: it ships, and the page's help lists it.

The desktop help browser reads the checkout's ``docs/``; a page has no
checkout -- its Python is the unpacked archive. Two gates:

* the *bundle* -- the user-facing markdown rides in ``app.zip`` under its
  ``docs/...`` paths (:mod:`chisurf.web.docs`), and the maintainer material
  and figures stay behind;
* the *page* -- a subprocess that imports the UNPACKED archive (the page's
  Python, no checkout anywhere) and asks the help plugin's own tree builder
  what it lists: a shipped guide must be listed and must open. This is the
  shape the browser runs -- the repo's ``docs/`` cannot leak in because the
  archive's ``chisurf`` package is imported from the unpacked directory.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: A guide every page must carry, and the address a help link uses for it.
GUIDE_REL = "docs/guides/09_diffusion_fcs.md"
GUIDE_TITLE = "Diffusion FCS"


def _bundle():
    from chisurf.web import bundle

    return bundle()


def _front_matter_title(markdown: str) -> str:
    """The ``title:`` of the MyST front-matter, else the first heading."""
    if markdown.startswith("---"):
        block = markdown.split("---", 2)[1]
        for line in block.splitlines():
            if line.startswith("title:"):
                return line.split(":", 1)[1].strip().strip("'\"")
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


# -- the bundle --------------------------------------------------------------- #

def test_bundle_ships_the_user_facing_documentation(tmp_path):
    from emtk.web.serve import pack_zip

    names = set(zipfile.ZipFile(pack_zip(_bundle(), tmp_path / "app.zip")).namelist())
    docs = sorted(n for n in names if n.startswith("docs/"))

    # The known guide, its neighbours, and the top-level pages.
    assert GUIDE_REL in names, "the diffusion-FCS guide does not ship"
    assert "docs/concepts/fcs_correlation.md" in names
    assert "docs/getting_started/index.md" in names
    assert "docs/manual/data_import.md" in names
    assert "docs/index.md" in names and "docs/licensing.md" in names
    # The review registry rides beside the pages, so badges stay truthful.
    assert "docs/guides/review_status.json" in names

    md = [n for n in docs if n.endswith(".md")]
    assert len(md) >= 400, f"only {len(md)} documentation pages shipped"

    # Maintainer material and what a page cannot show stay behind.
    assert not [n for n in docs if n.startswith("docs/development/")], (
        "maintainer docs shipped"
    )
    assert not [n for n in docs if "_old_manual" in n or "_build" in n]
    binaries = [n for n in docs if n.endswith((".png", ".jpg", ".pdf", ".py", ".yaml"))]
    assert not binaries, f"non-page files shipped: {binaries[:5]}"


def test_the_shipped_split_is_user_facing_and_lean():
    from chisurf.web.docs import DOC_SIDECAR, USER_DOC_ROOTS, doc_files

    files = doc_files()
    assert files, "no documentation collected from the checkout"

    roots = set()
    for name in files:
        parts = pathlib.PurePosixPath(name).parts
        assert parts[0] == "docs", name
        if len(parts) == 2:  # docs/index.md, docs/licensing.md
            continue
        roots.add(parts[1])
        assert parts[-1].endswith(".md") or parts[-1] == DOC_SIDECAR, name
    assert roots == set(USER_DOC_ROOTS), (
        f"shipped roots drifted from the user-facing split: {sorted(roots)}"
    )

    total = sum(len(data) for data in files.values())
    assert total < 6 * 1024 * 1024, (
        f"{total / 1e6:.1f} MB of documentation: too much for the bundle"
    )


# -- the page: the unpacked archive's own help -------------------------------- #

_PROBE = r"""
import json, pathlib, sys

page = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(page))

import chisurf

unpacked = pathlib.Path(chisurf.__file__).resolve().parent.parent
assert unpacked == page, f"imported {chisurf.__file__}, not the unpacked archive"

# The help plugin's own resolution and listing, exactly as the model runs them.
from chisurf.plugins.core.help.api import toc

root = toc.docs_root()
assert root == page / "docs", f"docs_root() resolved to {root}, not the shipped tree"

tree = toc.build_toc()
pages = [n for n in tree.walk() if n.path]
titles = {n.title for n in pages}

guide = json.loads(sys.argv[2])
assert guide["title"] in titles, (
    f"{guide['title']!r} is not listed; the first titles: {sorted(titles)[:15]}"
)
text = (root / "guides" / "09_diffusion_fcs.md").read_text(encoding="utf-8")
assert "# Diffusion FCS" in text

maintainer = [n for n in pages if "development" in n.path.parts]
assert not maintainer, f"maintainer pages listed: {maintainer[:3]}"

print(json.dumps({"pages": len(pages), "docs_root": str(root)}))
"""


def test_page_help_lists_a_shipped_guide(tmp_path):
    """The page's Python is the unpacked archive: its help must list the
    shipped guides from the shipped tree."""
    from emtk.web.serve import pack_zip

    page = tmp_path / "page"
    with zipfile.ZipFile(pack_zip(_bundle(), tmp_path / "app.zip")) as archive:
        archive.extractall(page)

    probe_env = {
        **os.environ,
        "CHISURF_SETTINGS_DIR": str(tmp_path / "settings"),
        "MMFDB_SETTINGS_DIR": str(tmp_path / "settings"),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE,
            str(page),
            json.dumps({"rel": GUIDE_REL, "title": GUIDE_TITLE}),
        ],
        cwd=str(tmp_path),
        env=probe_env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["pages"] >= 300, f"the page's help lists only {out['pages']} pages"
    assert out["docs_root"] == str(page / "docs")


# -- the surface: the help plugin's model ------------------------------------- #

def test_help_surface_lists_and_opens_a_shipped_guide_title():
    """The help plugin's model (what the page's Help menu opens) lists the
    shipped guide by its title and opens it by its docs address."""
    from chisurf.plugins.core.help.gui.help_app import HelpModel
    from chisurf.web.docs import doc_files

    files = doc_files()
    assert GUIDE_REL in files
    assert _front_matter_title(files[GUIDE_REL].decode("utf-8")) == GUIDE_TITLE

    model = HelpModel()
    assert model.toc is not None
    assert GUIDE_TITLE in {n.title for n in model.toc.walk() if n.path}, (
        "the help surface does not list the shipped guide"
    )
    assert model.open_page(GUIDE_REL), "the guide did not open by its docs address"
    assert model.current_title == GUIDE_TITLE
    assert model.current_path is not None
    assert model.current_path.name == "09_diffusion_fcs.md"
    assert "# Diffusion FCS" in model.current_content
