"""`.pto` is ChiSurf's file type for photon data, not one option among several.

A vendor file — `.ptu`, `.spc`, `.ht3` — is a *recording*, in whatever the
instrument's software emits. Opening one produces the measurement's container,
inside which those exact bytes are kept and stay recoverable; everything
computed afterwards goes in the same file rather than into directories beside
it.

These tests pin the two halves of that. A writer's default must be the
container, and a file dialog must offer it — the second is not cosmetic: a
dialog listing a different set from the reader **hides files ChiSurf can open**,
and that is exactly how `.pto` came to be absent from every one of them while
being the format they all produced.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from chisurf.core.fio.staging import (
    TTTR_EXTENSIONS,
    TTTR_FILE_FILTER,
    VENDOR_EXTENSIONS,
)

ROOT = Path(__file__).resolve().parents[1] / "chisurf"

#: The parenthesised extension group of a Qt file-dialog filter.
#:
#: `[^()]*` and nothing nested, deliberately: the obvious spelling
#: (`(?:\s*\*\.[\w.-]+)+` behind a `[^"\';]*` prefix) backtracks
#: catastrophically on ordinary source and turns a two-second scan into a
#: two-minute one.
#: A group of *nothing but* extension globs, which is what a filter is. Anchored
#: so an ordinary tuple -- `(spc_output_path, "m*.spc")` -- is not mistaken for
#: one.
_GROUP = re.compile(r"\(\s*\*\.[\w.-]+(?:\s+\*\.[\w.-]+)*\s*\)")
_EXTENSION = re.compile(r"\*\.([\w.-]+)")

#: Formats a *photon* dialog names, and something else might too.
#:
#: `.h5`, `.hdf5`, `.set` and `.sm` are shared with images, settings files and
#: other things, so they do not make a filter a photon filter on their own.
_SHARED = {"h5", "hdf5", "set", "sm"}


#: A quoted string, and a run of adjacent ones (implicit concatenation) —
#: because a long filter is usually written across several source lines and the
#: dialog sees the joined result.
_LITERAL = re.compile(r"(?:\"[^\"\n]*\"|'[^'\n]*')(?:\s*(?:\"[^\"\n]*\"|'[^'\n]*'))*")


def _photon_filters(text: str) -> list[str]:
    """Return the dialog filters in *text* that name a vendor photon format.

    The unit is the **whole filter**, not one parenthesised group. A filter is
    a `;;`-joined list, and a per-format entry inside one — "PicoQuant PTU
    (*.ptu)" — hides nothing as long as the list also offers the container.
    Checking groups individually flags exactly the well-formed case.
    """
    vendors = {e.lstrip(".") for e in VENDOR_EXTENSIONS} - _SHARED
    out = []
    for literal in _LITERAL.finditer(text):
        spec = literal.group()
        groups = _GROUP.findall(spec)
        if not groups:
            continue
        listed = {e for g in groups for e in _EXTENSION.findall(g)}
        # More than one format, so it is claiming to offer "photon data" rather
        # than narrowing to one on purpose (a Save-As writes exactly one).
        if len(listed) > 1 and listed & vendors:
            out.append(spec)
    return out


def _sources() -> list[Path]:
    files = list(ROOT.rglob("*.py")) + list(ROOT.rglob("*.view.json"))
    return [p for p in files if "/test" not in str(p) and "/legacy/" not in str(p)]


def test_the_container_comes_first_in_the_reader_s_own_list():
    assert TTTR_EXTENSIONS[0] == ".pto"
    assert ".pto" not in VENDOR_EXTENSIONS, "the container is not a vendor format"
    assert set(VENDOR_EXTENSIONS) < set(TTTR_EXTENSIONS)


def test_the_shared_filter_offers_the_container_first():
    first = TTTR_FILE_FILTER.split(";;")[0]
    assert "*.pto" in first
    assert first.index("*.pto") < first.index("*.ptu")


def test_no_file_dialog_offers_photons_without_offering_the_container():
    offenders: list[str] = []
    for path in _sources():
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for spec in _photon_filters(text):
            if "*.pto" not in spec:
                offenders.append(f"{path.relative_to(ROOT.parent)}: {spec.strip()}")

    assert not offenders, (
        "these dialogs offer vendor photon files and not the container, so they "
        "hide the measurements ChiSurf writes. Use "
        "chisurf.core.fio.staging.TTTR_FILE_FILTER, or add *.pto:\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_a_burst_analysis_writes_the_container_by_default():
    from chisurf.plugins.burst.burst_selection.api.models import AnalysisSettings

    assert AnalysisSettings().output_formats == ["pto"]


def test_the_bid_converter_writes_the_container_by_default():
    """Read out of the source rather than run: the converter needs real data."""
    source = (ROOT / "plugins" / "burst" / "bid_to_analysis" / "__init__.py").read_text()
    assert 'output_types = {"bur"}' not in source
    assert 'output_types = {"pto"}' in source


@pytest.mark.parametrize("name", ["nb", "phasor", "mean_micro_time"])
def test_every_imaging_tool_declares_what_it_did(name: str):
    """The container records the operation, so a per-pixel lifetime and a
    per-pixel phasor are distinguishable as analyses rather than only as column
    names.
    """
    from chisurf.plugins.microscopy.imaging_common.base import ImagingMapViewModel

    subclasses = {
        cls.WINDOW_KIND: cls
        for cls in _all_subclasses(ImagingMapViewModel)
        if getattr(cls, "WINDOW_KIND", None)
    }
    cls = subclasses.get(name)
    if cls is None:
        pytest.skip(f"no imaging tool with WINDOW_KIND {name!r} is importable")
    assert cls.OPERATION_TYPE
    assert cls.ROW_GRAIN == "pixel"


def _all_subclasses(cls) -> set:
    # Import the tools so their subclasses exist before they are counted.
    for module in (
        "chisurf.plugins.microscopy.img_pixel_nb.gui.view_model",
        "chisurf.plugins.microscopy.img_pixel_phasor.gui.view_model",
        "chisurf.plugins.microscopy.img_pixel_micro_time.gui.view_model",
    ):
        try:
            __import__(module)
        except Exception:
            continue
    found = set(cls.__subclasses__())
    for sub in list(found):
        found |= _all_subclasses(sub)
    return found


# -- import ---------------------------------------------------------------------

SPC = (
    ROOT
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)


@pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")
def test_opening_a_vendor_file_produces_the_measurement(tmp_path: Path):
    """And the photons read out of it are the same photons."""
    import numpy as np

    from chisurf.core.fio.fluorescence.photons import Photons
    from chisurf.core.fio.staging import import_measurement

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())

    container = import_measurement(source)
    assert container == source.with_suffix(".pto")
    # The recording is left exactly where it was. Deleting it is the user's
    # decision, never the import's.
    assert source.exists()

    vendor = Photons([str(source)], None)
    contained = Photons([str(container)], None)
    np.testing.assert_array_equal(np.asarray(vendor.macro_times), np.asarray(contained.macro_times))
    np.testing.assert_array_equal(
        np.asarray(vendor.routing_channels), np.asarray(contained.routing_channels)
    )


@pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")
def test_importing_twice_does_not_make_a_second_container(tmp_path: Path):
    from chisurf.core.fio.staging import import_measurement

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())

    first = import_measurement(source)
    assert import_measurement(source) == first
    # A container asked to import is already one.
    assert import_measurement(first) == first
    assert len(list(tmp_path.glob("*.pto"))) == 1


def test_an_unwritable_location_still_reads(tmp_path: Path, monkeypatch):
    """Data on a read-only share must open, container or not.

    The import is a convenience; refusing to read a file because its folder
    cannot hold a container would make the format a requirement rather than
    the default.
    """
    from chisurf.core.fio import staging

    source = tmp_path / "m000.spc"
    source.write_bytes(b"not really a measurement")

    import chisurf.core.fio.pto as pto

    def _refuse(*args, **kwargs):
        raise PermissionError(tmp_path)

    monkeypatch.setattr(pto.Measurement, "create", staticmethod(_refuse))
    assert staging.import_measurement(source) == source
