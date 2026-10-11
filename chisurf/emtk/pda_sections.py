"""The PDA reader's settings sections, drawn natively: detector rows, time windows, the file list.

``pda.view.json`` declares three ``custom`` sections the Qt panel fills with
hand-built widgets: ``pda_detector`` (Setup, Routine and one row per colour),
``pda_tw`` (the time-window list) and ``pda_files`` (the files a read takes).
Here each one is a view spec of its own beside the reader
(``pda_detector.view.json``, ``pda_tw.view.json``, ``pda_files.view.json`` in
``chisurf/core/experiments/pda2c/``) drawn by :func:`emtk.view_form.draw_sections`
over :class:`PdaSectionsModel` -- the reader's
:class:`~chisurf.core.experiments.pda2c.settings.PdaReaderSettings`, which writes
every change onto the reader, plus the two things only a host can do: read the
ticked files, and take dropped ones.

Reading goes through the host: :class:`~chisurf.emtk.reader_settings.ReaderSettingsApp`
carries a ``load_files(filename)`` callable the Read data dock sets, so the read
runs on the dock's worker like *+ Data*. Without one, *+ Data* with an empty
*File* field reads the ticked files too (the reader's ``filename`` is the list).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.view_form import FormState, draw_sections

from chisurf.core.experiments.pda2c.settings import PdaReaderSettings
from chisurf.core.support.i18n import tr

#: Where the section specs live: beside the reader and its ``pda.view.json``.
SPEC_DIR = Path(__file__).resolve().parents[1] / "core" / "experiments" / "pda2c"

#: The custom section keys of ``pda.view.json`` drawn here, and the spec each one draws.
SECTION_SPECS = {
    "pda_detector": "pda_detector.view.json",
    "pda_tw": "pda_tw.view.json",
    "pda_files": "pda_files.view.json",
}


def load_spec(key: str) -> dict:
    """The parsed spec of custom section *key*."""
    return json.loads((SPEC_DIR / SECTION_SPECS[key]).read_text(encoding="utf-8"))


class PdaSectionsModel(PdaReaderSettings):
    """What the three PDA specs bind: the reader's settings, the load and the drop.

    Parameters
    ----------
    reader : Pda2cReader
        The reader every write lands on.
    host : object, optional
        The settings app; its ``load_files`` reads a filename on the host's worker.
    setups : mapping, optional
        Saved detector setups by name; read from the store when omitted.
    last_used : str, optional
        The setup chosen when the reader has none yet.
    """

    def __init__(self, reader: Any, host: Any = None, setups=None, last_used=None) -> None:
        super().__init__(reader, setups=setups, last_used=last_used)
        self.host = host
        self.status = ""

    def enabled(self, name: str) -> bool:
        """*Load dropped files* needs a ticked entry; a row needs a setup detector to pick from."""
        if name == "load":
            return bool(self.checked_paths())
        if name == "clear_files":
            return bool(self.reader.files)
        if name.startswith("detector_"):
            return bool(self.detector_names())
        return True

    def load(self) -> bool:
        """Read the ticked files with the reader, on the host's worker; with *Auto load*, empty the list.

        Returns
        -------
        bool
            Whether the read was handed to the host.
        """
        filename = self.load_filename()
        if not filename:
            self.status = tr("No dropped files are checked to load.")
            return False
        hook = getattr(self.host, "load_files", None)
        if not callable(hook):
            self.status = tr("Press + Data with an empty File field to read the checked files.")
            return False
        hook(filename)
        n = len(self.checked_paths())
        self.status = tr("Reading {n} checked entries…").format(n=n)
        if self.auto_load:
            self.clear_files()
        return True

    def files_dropped(self, paths) -> bool:
        """Files dropped onto the form join the list (and are read at once with *Auto load*).

        Returns
        -------
        bool
            Whether any was taken; ``False`` leaves the drop to the host.
        """
        added = self.add_paths(str(p) for p in paths or ())
        if not added:
            return False
        self.status = tr("{n} entries added.").format(n=added)
        if self.auto_load and callable(getattr(self.host, "load_files", None)):
            self.load()
        return True


class PdaSections:
    """Draw the three PDA sections over one :class:`PdaSectionsModel`, built at the first draw."""

    def __init__(self, reader: Any, host: Any = None, setups=None, last_used=None) -> None:
        self.reader = reader
        self.host = host
        self._setups = setups
        self._last_used = last_used
        self._model: PdaSectionsModel | None = None
        self.specs = {key: load_spec(key) for key in SECTION_SPECS}
        self.forms = {key: FormState() for key in SECTION_SPECS}

    @property
    def model(self) -> PdaSectionsModel:
        """The bound model (made on first use, so a form that never draws reads no setups)."""
        if self._model is None:
            from chisurf.emtk import detector_cascade

            setups = detector_cascade.detector_setups() if self._setups is None else self._setups
            last = (
                detector_cascade.last_used_setup() if self._last_used is None else self._last_used
            )
            self._model = PdaSectionsModel(self.reader, self.host, setups, last)
        return self._model

    def drawer(self, key: str):
        """The custom-section draw callback for *key*."""

        def draw(section: dict, model: Any, state: FormState, width: float) -> None:
            bound = self.model
            if key == "pda_detector":
                bound.sync()
            form = self.forms[key]
            form.rects.clear()
            im.push_id(key)
            try:
                draw_sections(self.specs[key]["sections"], bound, form)
            finally:
                im.pop_id()
            for name, rect in form.rects.items():
                state.rects[f"{key}.{name}"] = rect

        return draw

    def files_dropped(self, paths) -> bool:
        """Route a drop onto the reader form to the file list."""
        return self.model.files_dropped(paths)


def register(reader: Any, form: FormState, host: Any = None, setups=None, last_used=None):
    """Draw the PDA sections natively on *form* when *reader* is the PDA TTTR reader.

    Returns
    -------
    PdaSections or None
        The sections (their ``files_dropped`` takes drops), ``None`` for any other reader.
    """
    from chisurf.core.experiments.pda2c import Pda2cReader

    if not isinstance(reader, Pda2cReader):
        return None
    sections = PdaSections(reader, host, setups, last_used)
    for key in SECTION_SPECS:
        form.custom.setdefault(key, sections.drawer(key))
    return sections


__all__ = ["PdaSections", "PdaSectionsModel", "SECTION_SPECS", "load_spec", "register"]
