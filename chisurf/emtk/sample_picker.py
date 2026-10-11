"""The MMFDB sample a file read in the emtk shell belongs to: asked after the file is chosen.

The Qt readers of FCS, PCH, TTTR and PDA files ask, right after their file
dialog, which MMFDB sample the measurement is of (``show_sample_picker_dialog``)
and store the answer on the reader as ``sample_id``; the dataset's provenance
then names the sample. This is that question in the shell, drawn by emtk: the
samples come from the MMFDB server (``mmfdb.samples.list``) on a worker, *OK*
writes the choice onto the reader, *Skip* leaves it unset. *New…* defines a
sample in place (:class:`NewSampleDialog`, the Qt "New Sample" dialog's fields:
entity, probes, buffer, UniProt / PDB references and mutations), creates it in
MMFDB (``mmfdb.samples.create_structured``) and selects it.
"""

from __future__ import annotations

from typing import Any, Callable

from emtk import im
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.emtk.background_build import BackgroundBuild
from chisurf.plugins.emtk_layout import action_button


class _Rows(list):
    """Table rows with a ``revision``, so an edit rebinds the table once."""

    revision = 0


class NewSample:
    """The fields of a new MMFDB sample and what *Fetch* / *Diff vs Reference* fill in (no toolkit)."""

    FIELDS = ("name", "description", "entity_name", "entity_sequence", "entity_type", "donor",
              "acceptor", "buffer", "uniprot", "pdb_id", "pdb_chain", "organism",
              "reference_sequence")

    def __init__(self) -> None:
        for field in self.FIELDS:
            setattr(self, field, "")
        self.mutations: list[dict] = []
        self.message = ""
        self._rows = _Rows()

    # -- the mutation table ------------------------------------------------- #
    def mutation_rows(self) -> _Rows:
        return self._rows

    def _changed(self) -> None:
        rows = _Rows(dict(m, row=i) for i, m in enumerate(self.mutations))
        rows.revision = self._rows.revision + 1
        self._rows = rows

    def add_mutation(self) -> None:
        self.mutations.append({"seq_id": "", "mut_comp_id": "", "wt_comp_id": "", "auth_name": "",
                               "kind": "engineered_mutation"})
        self._changed()

    def clear_mutations(self) -> None:
        self.mutations = []
        self._changed()

    def edit_mutation(self, record: Any, key: str, value: Any) -> None:
        index = int((record or {}).get("row", -1))
        if 0 <= index < len(self.mutations):
            self.mutations[index][key] = str(value)
            self._changed()

    def delete_mutation(self, record: Any) -> None:
        index = int((record or {}).get("row", -1))
        if 0 <= index < len(self.mutations):
            del self.mutations[index]
            self._changed()

    # -- references ------------------------------------------------------------ #
    def fetch_uniprot(self) -> None:
        """Organism and reference sequence of the UniProt accession (cached by MMFDB)."""
        accession = str(self.uniprot or "").strip()
        if not accession:
            self.message = tr("Enter a UniProt accession first.")
            return
        from mmfdb.samples.external_refs import fetch_uniprot

        result = fetch_uniprot(accession)
        if result is None:
            self.message = tr("Could not fetch UniProt entry {accession}. Check the accession and "
                              "network connectivity.").format(accession=accession)
            return
        self.organism = str(result.get("organism") or self.organism)
        self.reference_sequence = str(result.get("sequence") or self.reference_sequence)
        self.message = ""

    def diff_reference(self) -> None:
        """The construct's differences from the reference, as mutation rows."""
        construct = str(self.entity_sequence or "").strip()
        reference = str(self.reference_sequence or "").strip()
        if not construct:
            self.message = tr("Enter an entity sequence first.")
            return
        if not reference:
            self.message = tr("Enter a reference sequence first (or click Fetch).")
            return
        from mmfdb.samples.external_refs import diff_sequences

        try:
            found = diff_sequences(construct, reference)
        except ValueError as exc:
            self.message = str(exc)
            return
        self.mutations = [
            {"seq_id": str(m.seq_id), "mut_comp_id": m.mut_comp_id, "wt_comp_id": m.wt_comp_id,
             "auth_name": m.auth_name, "kind": m.kind}
            for m in found
        ]
        self._changed()
        self.message = (tr("Found {count} mutation(s); review them in the table.").format(count=len(found))
                        if found else tr("No differences found — construct matches reference."))

    # -- the definition ------------------------------------------------------- #
    def sample_data(self) -> dict:
        """The definition as ``mmfdb.samples.create_structured`` takes it.

        Raises
        ------
        ValueError
            Without a sample name.
        """
        name = str(self.name or "").strip()
        if not name:
            raise ValueError(tr("Sample name is required."))

        def text(value: Any) -> str | None:
            return str(value or "").strip() or None

        mutations = []
        for m in self.mutations:
            try:
                seq_id = int(str(m.get("seq_id", "")).strip())
            except ValueError:
                continue
            mutations.append({"seq_id": seq_id, "mut_comp_id": str(m.get("mut_comp_id", "")).strip(),
                              "wt_comp_id": str(m.get("wt_comp_id", "")).strip(),
                              "auth_name": str(m.get("auth_name", "")).strip(),
                              "kind": str(m.get("kind", "")).strip() or "engineered_mutation"})
        probes = [{"name": dye, "entity_index": 0} for dye in (text(self.donor), text(self.acceptor)) if dye]
        return {
            "name": name,
            "description": str(self.description or "").strip(),
            "entities": [{
                "name": text(self.entity_name) or name,
                "entity_type": text(self.entity_type) or "protein",
                "sequence": str(self.entity_sequence or "").strip(),
                "uniprot_accession": text(self.uniprot),
                "pdb_id": text(self.pdb_id),
                "pdb_chain_id": text(self.pdb_chain),
                "organism": text(self.organism),
                "reference_sequence": text(self.reference_sequence),
                "mutations": mutations,
            }],
            "probes": probes,
            "fret_pairs": [{"probe_1_index": 0, "probe_2_index": 1}] if len(probes) == 2 else [],
            "buffer_description": str(self.buffer or "").strip(),
        }


class NewSampleDialog:
    """*New…*: define a sample and create it in MMFDB; ``on_close(sample_id)`` (``None``: cancelled)."""

    TITLE = "New Sample"

    def __init__(self, client: Any, on_close: Callable[[str | None], None],
                 wake: Callable[[], None] | None = None) -> None:
        import json
        from pathlib import Path

        from emtk.dialog_window import DialogWindow

        self.client = client
        self.on_close = on_close
        self.model = NewSample()
        self.spec = json.loads((Path(__file__).parent / "views" / "new_sample.view.json")
                               .read_text(encoding="utf-8"))
        self.form = FormState()
        self.rects: dict[str, tuple] = {}
        self.window = DialogWindow(tr("New Sample"), size=(560, 680), key="new-sample", fit_height=True)
        self.window.show()
        self._creating = BackgroundBuild(wake=wake)

    @property
    def open(self) -> bool:
        return bool(self.window.open)

    def accept(self) -> bool:
        """*OK*: create the sample on a worker; the dialog closes with its id."""
        try:
            data = self.model.sample_data()
        except ValueError as exc:
            self.model.message = str(exc)
            return False
        client = self.client
        self._creating.start({"sample": lambda: client.create_structured_sample(data)},
                             name="chisurf-sample-create")
        self.model.message = tr("Creating the sample…")
        return True

    def _poll(self) -> None:
        results = self._creating.collect()
        if results is None:
            return
        made, error = results.get("sample", (None, None))
        if error is not None:
            self.model.message = tr("The sample could not be created ({error}).").format(error=error)
            return
        sample_id = str((made or {}).get("sample_id") or "")
        self.window.hide()
        self.on_close(sample_id or None)

    def draw(self, box) -> None:
        if not self.window.open:
            return
        self._poll()
        pressed = self.window.begin(box)
        draw_form(self.spec, self.model, self.form, titles=True)
        im.separator()
        im.begin_disabled(self._creating.busy)
        if im.button(tr("OK") + "##new-sample-ok"):
            self.accept()
        self.rects["ok"] = im.get_item_rect()
        im.set_item_tooltip(tr("Create the sample in MMFDB and use it for this file."))
        im.end_disabled()
        im.same_line()
        cancel = action_button("cancel", id="new-sample-cancel",
                               tooltip=tr("Close without creating a sample."))
        self.rects["cancel"] = im.get_item_rect()
        self.rects.update(self.form.rects)
        self.window.end()
        if cancel or pressed == "close":
            self.window.hide()
            self.on_close(None)


def sample_options(samples: list[dict]) -> list[tuple[str, str]]:
    """``(sample_id, name)`` of each sample, after the "no sample" entry."""
    out = [("", tr("(no sample)"))]
    for sample in samples or []:
        sample_id = str(sample.get("sample_id") or sample.get("id") or "")
        if sample_id:
            out.append((sample_id, str(sample.get("name") or sample.get("display_name") or sample_id)))
    return out


class SamplePickerDialog:
    """Which sample a just-chosen file is of; the answer goes to ``reader.sample_id``.

    Parameters
    ----------
    reader : object
        The reader that will read the file (it has a ``sample_id``).
    client : object, optional
        MMFDB client with ``list_samples()``; the shell's session client by default.
    on_close : callable, optional
        ``on_close(sample_id)`` once answered (``None`` for *Skip*).
    wake : callable, optional
        The host's frame request, run when the samples arrive.
    """

    TITLE = "Select sample"
    SPEC = {
        "sections": [
            {"type": "info", "source": "note"},
            {"type": "panel", "sections": [
                {"type": "choice", "attr": "sample_id", "label": "Sample", "options_source": "options",
                 "description": "The MMFDB sample this measurement is of; its provenance will name it."},
            ]},
        ]
    }

    def __init__(
        self,
        reader: Any,
        client: Any = None,
        on_close: Callable[[str | None], None] | None = None,
        wake: Callable[[], None] | None = None,
    ) -> None:
        from emtk.dialog_window import DialogWindow

        self.reader = reader
        self.on_close = on_close
        self.sample_id = str(getattr(reader, "sample_id", "") or "")
        self.samples: list[dict] = []
        self.error = ""
        self.form = FormState()
        self.rects: dict[str, tuple] = {}
        self.window = DialogWindow(tr(self.TITLE), size=(460, 200), fit_height=True)
        self.window.show()
        self.client = client
        self.wake = wake
        #: The *New…* form while it is open.
        self.new_dialog: NewSampleDialog | None = None
        self._loading = BackgroundBuild(wake=wake)
        self._loading.start({"samples": lambda: self._list(client)}, name="chisurf-sample-list")

    def new_sample(self) -> None:
        """*New…*: the sample definition form; the created sample is listed and selected."""
        client = self.client
        if client is None:
            from chisurf.emtk.dataset_picker import session_client

            client = session_client()

        def closed(sample_id: str | None) -> None:
            self.new_dialog = None
            if sample_id:
                self.sample_id = sample_id
                self._loading.start({"samples": lambda: self._list(client)},
                                    name="chisurf-sample-list")

        self.new_dialog = NewSampleDialog(client, on_close=closed, wake=self.wake)

    @staticmethod
    def _list(client: Any) -> list[dict]:
        if client is None:
            from chisurf.emtk.dataset_picker import session_client

            client = session_client()
        return list(client.list_samples() or [])

    @property
    def loading(self) -> bool:
        return self._loading.busy

    def options(self) -> list[tuple[str, str]]:
        return sample_options(self.samples)

    def note(self) -> str:
        if self.loading:
            return tr("Reading the samples…")
        if self.error:
            return tr("The samples could not be read ({error}); Skip reads the file without one.").format(
                error=self.error
            )
        return tr("Which sample is this measurement of? New… defines one.")

    def enabled(self, name: str) -> bool:
        return not self.loading

    def _poll(self) -> None:
        results = self._loading.collect()
        if results is None:
            return
        samples, error = results.get("samples", (None, None))
        if error is not None:
            self.error = str(error)
        else:
            self.samples = list(samples or [])

    def answer(self, sample_id: str | None) -> None:
        """*OK* with *sample_id* (``""``: no sample) or *Skip* (``None``)."""
        if sample_id is not None:
            self.reader.sample_id = sample_id or None
        self.window.hide()
        if self.on_close is not None:
            self.on_close(sample_id)

    def draw(self, box) -> None:
        if not self.window.open:
            return
        self._poll()
        pressed = self.window.begin(box)
        draw_form(self.SPEC, self, self.form)
        im.begin_disabled(self.loading or self.new_dialog is not None)
        if im.button(tr("New…") + "##sample-new"):
            self.new_sample()
        self.rects["new"] = im.get_item_rect()
        im.set_item_tooltip(tr("Define a new sample in MMFDB and use it."))
        im.end_disabled()
        im.separator()
        ok = im.button(tr("OK") + "##sample-ok")
        self.rects["ok"] = im.get_item_rect()
        im.set_item_tooltip(tr("Record the chosen sample with the file."))
        im.same_line()
        skip = im.button(tr("Skip") + "##sample-skip")
        self.rects["skip"] = im.get_item_rect()
        im.set_item_tooltip(tr("Read the file without naming a sample."))
        self.rects.update(self.form.rects)
        self.window.end()
        if self.new_dialog is not None:
            self.new_dialog.draw(box)
            return
        if ok and not self.loading:
            self.answer(self.sample_id)
        elif skip or pressed == "close":
            self.answer(None)


__all__ = ["NewSample", "NewSampleDialog", "SamplePickerDialog", "sample_options"]
