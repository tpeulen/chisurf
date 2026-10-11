"""The MMFDB sample a file read in the emtk shell belongs to: asked after the file is chosen.

The Qt readers of FCS, PCH, TTTR and PDA files ask, right after their file
dialog, which MMFDB sample the measurement is of (``show_sample_picker_dialog``)
and store the answer on the reader as ``sample_id``; the dataset's provenance
then names the sample. This is that question in the shell, drawn by emtk: the
samples come from the MMFDB server (``mmfdb.samples.list``) on a worker, *OK*
writes the choice onto the reader, *Skip* leaves it unset. New samples are made
in MMFDB Admin.
"""

from __future__ import annotations

from typing import Any, Callable

from emtk import im
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.emtk.background_build import BackgroundBuild


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
        self._loading = BackgroundBuild(wake=wake)
        self._loading.start({"samples": lambda: self._list(client)}, name="chisurf-sample-list")

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
        return tr("Which sample is this measurement of? New samples are made in MMFDB Admin.")

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
        im.separator()
        ok = im.button(tr("OK") + "##sample-ok")
        self.rects["ok"] = im.get_item_rect()
        im.same_line()
        skip = im.button(tr("Skip") + "##sample-skip")
        self.rects["skip"] = im.get_item_rect()
        self.rects.update(self.form.rects)
        self.window.end()
        if ok and not self.loading:
            self.answer(self.sample_id)
        elif skip or pressed == "close":
            self.answer(None)


__all__ = ["SamplePickerDialog", "sample_options"]
