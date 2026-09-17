"""What the viewer says when it holds nothing, and what ``fetch`` says when it fails.

Both were reported from one session. After ``delete all`` the viewer kept a
*placeholder* object, and every command then answered as though that placeholder
were a real molecule that happened to be broken::

    > spectrum count, rainbow
    spectrum: that object has no atoms to colour
    > zoom all
    zoom: 'all' matched no atoms
    > color red
    Object obj1 does not expose atom-level coordinates for coloring

Three different explanations, none of them true, one of them naming an internal
object the user never created. The honest answer is that nothing is loaded.

In the same session ``fetch`` failed with a raw
``CERTIFICATE_VERIFY_FAILED ... unable to get local issuer certificate``, which
tells the person at the keyboard nothing about what to do.
"""

from __future__ import annotations

import ssl
import urllib.error

import pytest
from chimol.commands.builtin.selection import _NOTHING_LOADED


@pytest.fixture(scope="session")
def qapp_empty():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp_empty):
    """A plugin window with the shared command object attached to it."""
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(600, 400)
    errors: list[str] = []
    messages: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)
    yield win, shared, errors, messages
    win.close()


# --------------------------------------------------------------------------- #
# The viewer knows it is empty
# --------------------------------------------------------------------------- #
def test_a_fresh_viewer_is_empty(session):
    win, _shared, _errors, _messages = session
    assert win.viewer.is_empty() is True


def test_a_placeholder_does_not_count_as_content(session):
    """It exists so pre-load settings survive; it is not a molecule."""
    win, shared, _errors, _messages = session
    shared.do("delete all")
    assert win.viewer.objects, "the placeholder is the thing under test"
    assert all(e.placeholder for e in win.viewer.objects.values())
    assert win.viewer.is_empty() is True


def test_a_loaded_object_makes_it_not_empty(session, tmp_path):
    win, _shared, _errors, _messages = session
    pdb = tmp_path / "two.pdb"
    pdb.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\n"
        "ATOM      2  CA  ALA A   2       3.800   0.000   0.000  1.00  0.00           C\n"
        "END\n"
    )
    win.load_structure_from_path(pdb)
    assert win.viewer.is_empty() is False


# --------------------------------------------------------------------------- #
# ...and says so, once, instead of describing a molecule that is not there
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "line",
    [
        "spectrum count, rainbow",
        "zoom all",
        "color red",
        "spectrum b, blue_white_red, all",
    ],
)
def test_an_empty_viewer_says_nothing_is_loaded(session, line):
    win, shared, errors, _messages = session
    shared.do("delete all")
    errors.clear()
    shared.do(line)
    assert errors, f"{line!r} said nothing at all"
    assert _NOTHING_LOADED in errors[0], errors


def test_no_internal_object_id_is_leaked(session):
    """`color red` used to answer with `obj1` -- an object nobody created."""
    win, shared, errors, _messages = session
    shared.do("delete all")
    errors.clear()
    shared.do("color red")
    assert errors and "obj" not in errors[0].replace("object", "")


def test_the_message_names_the_way_out(session):
    """A dead end is worse when it does not say which door to try."""
    assert "load" in _NOTHING_LOADED and "fetch" in _NOTHING_LOADED


# --------------------------------------------------------------------------- #
# fetch does not depend on whatever CA store the interpreter happens to have
# --------------------------------------------------------------------------- #
def test_the_tls_context_verifies_and_has_certificates():
    from chimol.commands.builtin.loader import _tls_context

    context = _tls_context()
    if context is None:
        pytest.skip("certifi is not installed in this environment")
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    # An empty store is the failure being defended against.
    assert context.cert_store_stats()["x509_ca"] > 0


@pytest.fixture
def scratch_downloads(tmp_path, monkeypatch):
    """Point `fetch` at an empty directory.

    `fetch` re-uses a copy it has already downloaded, so a test that expects the
    download to fail has to start from a directory where the entry is absent --
    otherwise it exercises the cache and never reaches the network at all.
    """
    from chimol.commands.builtin import loader as loader_mod

    monkeypatch.setattr(loader_mod, "_download_dir", lambda: tmp_path)
    return tmp_path


def test_a_certificate_failure_is_explained(session, scratch_downloads, monkeypatch):
    """Not by quoting OpenSSL at someone who cannot act on it."""
    from chimol.commands.builtin import loader as loader_mod

    def _boom(*_args, **_kwargs):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))

    monkeypatch.setattr(loader_mod.urllib.request, "urlopen", _boom)
    _win, shared, errors, _messages = session
    errors.clear()
    shared.do("fetch PDBDEV_00000010, type=pdb-ihm")
    assert errors, "a failed fetch must say something"
    assert "certificate" in errors[0].lower()
    assert "certifi" in errors[0]


def test_a_missing_entry_is_not_reported_as_a_network_problem(
    session, scratch_downloads, monkeypatch
):
    from chimol.commands.builtin import loader as loader_mod

    def _missing(*_args, **_kwargs):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)

    monkeypatch.setattr(loader_mod.urllib.request, "urlopen", _missing)
    _win, shared, errors, _messages = session
    errors.clear()
    shared.do("fetch 9zzz, type=pdb-ihm")
    assert errors and "no entry" in errors[0]


# --------------------------------------------------------------------------- #
# ...and the reader does not describe itself as a reader that gave up
# --------------------------------------------------------------------------- #
_MINIMAL_MMCIF = """data_test
_entry.id TEST
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.auth_seq_id
_atom_site.pdbx_PDB_model_num
ATOM 1 N N ALA A 1 0.000 0.000 0.000 1 1
ATOM 2 C CA ALA A 1 1.458 0.000 0.000 1 1
ATOM 3 C C ALA A 1 2.009 1.420 0.000 1 1
ATOM 4 O O ALA A 1 1.251 2.390 0.000 1 1
ATOM 5 N N GLY A 2 3.332 1.540 0.000 2 1
ATOM 6 C CA GLY A 2 4.000 2.830 0.000 2 1
ATOM 7 C C GLY A 2 5.510 2.700 0.000 2 1
ATOM 8 O O GLY A 2 6.030 1.590 0.000 2 1
"""


def test_an_mmcif_is_read_by_the_mmcif_reader_not_a_fallback(tmp_path):
    """Routing a `.cif` to the mmCIF reader is a choice, not a failure."""
    from chimol.io.structure import load_structure_payload

    cif = tmp_path / "t.cif"
    cif.write_text(_MINIMAL_MMCIF)
    structure, backbone = load_structure_payload(cif, structure_factory=None)
    assert structure is None
    assert backbone.reader == "mmcif"


def test_reading_an_mmcif_does_not_warn_about_a_missing_reader(tmp_path, caplog):
    """Every `fetch` of a `.cif` used to warn that it fell back to the PDB parser."""
    from chimol.io.structure import load_structure_payload

    cif = tmp_path / "t.cif"
    cif.write_text(_MINIMAL_MMCIF)
    with caplog.at_level("WARNING"):
        load_structure_payload(cif, structure_factory=None)
    assert not [r for r in caplog.records if "No structure factory" in r.message]


def test_a_pdb_without_a_reader_still_says_so(tmp_path, caplog):
    """The warning is right for the case it was written for; keep it."""
    from chimol.io.structure import load_structure_payload

    pdb = tmp_path / "t.pdb"
    pdb.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\n"
        "ATOM      2  CA  ALA A   2       3.800   0.000   0.000  1.00  0.00           C\n"
        "END\n"
    )
    with caplog.at_level("WARNING"):
        _structure, backbone = load_structure_payload(pdb, structure_factory=None)
    assert backbone.reader == "pdb"
    assert [r for r in caplog.records if "No structure factory" in r.message]


def test_the_repository_url_is_the_one_that_serves_the_file():
    """A wrong template fails as a network error and reads as one."""
    from chimol.commands.builtin.loader import LoaderCommands

    ihm = LoaderCommands.REPOSITORIES["pdb-ihm"]
    assert ihm["url"].format(id="pdbdev_00000010", num="") == (
        "https://pdb-ihm.org/cif/pdbdev_00000010.cif"
    )


def test_a_downloaded_entry_is_not_downloaded_again(
    session, scratch_downloads, monkeypatch, tmp_path
):
    """The eight-spoke pore is 31.5 MB; the demo should not re-fetch it each run."""
    from chimol.commands.builtin import loader as loader_mod

    cached = tmp_path / "chimol_pdb_ihm_pdbdev_00000010.cif"
    cached.write_text(_MINIMAL_MMCIF)

    def _must_not_be_called(*_args, **_kwargs):
        raise AssertionError("fetch went to the network for a file it already had")

    monkeypatch.setattr(loader_mod.urllib.request, "urlopen", _must_not_be_called)
    _win, shared, errors, messages = session
    errors.clear()
    messages.clear()
    shared.do("fetch PDBDEV_00000010, type=pdb-ihm")
    assert errors == []
    assert any("cached" in m for m in messages), messages


def test_an_empty_cached_file_is_not_trusted(session, scratch_downloads, tmp_path):
    """A zero-byte leftover from an interrupted download is not a cache hit."""
    from chimol.commands.builtin import loader as loader_mod

    (tmp_path / "chimol_pdb_ihm_pdbdev_00000010.cif").write_bytes(b"")
    calls: list = []

    def _record(*args, **kwargs):
        calls.append(args)
        raise urllib.error.URLError("no network in this test")

    original = loader_mod.urllib.request.urlopen
    loader_mod.urllib.request.urlopen = _record
    try:
        _win, shared, errors, _messages = session
        errors.clear()
        shared.do("fetch PDBDEV_00000010, type=pdb-ihm")
    finally:
        loader_mod.urllib.request.urlopen = original
    assert calls, "an empty file must not stand in for the entry"


def test_a_failed_download_leaves_nothing_behind(session, scratch_downloads, monkeypatch, tmp_path):
    """A half-written entry in the cache is worse than no cache at all.

    Writing straight to the destination left a zero-byte file wherever a
    download failed part-way -- in the user's own cache directory, where the
    next run would find it sitting where the entry should be.
    """
    from chimol.commands.builtin import loader as loader_mod

    class _HalfResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, *_args):
            raise OSError("connection reset half way through")

    monkeypatch.setattr(loader_mod.urllib.request, "urlopen", lambda *a, **k: _HalfResponse())
    _win, shared, errors, _messages = session
    errors.clear()
    shared.do("fetch PDBDEV_00000010, type=pdb-ihm")
    assert errors, "the failure must be reported"
    assert list(tmp_path.iterdir()) == [], "no debris, not even an empty file"
