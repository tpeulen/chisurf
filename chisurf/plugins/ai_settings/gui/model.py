"""GUI-free backing model for the AI Settings AutoForm view.

The model holds the live state for a single provider and exposes the zero/one-arg
methods the ``ai_settings.view.json`` sections invoke (choice ``call`` and
``button_row`` actions). It contains no Qt imports so it stays headlessly
testable; the tool wires :attr:`AISettingsModel.on_change` to refresh the form.
"""

from __future__ import annotations

import html
import logging
import pathlib
import typing
import webbrowser

from chisurf.core.dataspec import load_view_spec
from chisurf.core.settings import ai_settings
from chisurf.core.settings.ai_settings import DEFAULT_PROVIDER_SETTINGS, PROVIDERS

_LOG = logging.getLogger(__name__)

_VIEW = pathlib.Path(__file__).with_name("ai_settings.view.json")

#: Editable fields that are auto-persisted the moment they change. ``provider`` is
#: excluded on purpose: switching it *loads* another provider rather than editing
#: the current one, so it must not save the current fields under the new key.
_PERSIST_FIELDS = frozenset(
    {
        "base_url",
        "api_key",
        "text_model",
        "image_model",
        "temperature",
        "top_p",
        "max_tokens",
        "command",
        "acp_backend_provider",
    }
)


#: Seconds a ``/models`` request may take before it is given up.
REQUEST_TIMEOUT = 15


def describe_error(error: BaseException) -> str:
    """Return a readable one-line description of a failed request.

    A timeout is named as one (the transport's own text is a bare ``timed out``),
    and an exception with no message falls back to its class name instead of
    producing an empty status.
    """
    text = str(error).strip()
    if isinstance(error, TimeoutError) or "timed out" in text.lower():
        return f"timed out: the endpoint did not answer within {REQUEST_TIMEOUT} s"
    return text or type(error).__name__


class AISettingsModel:
    """Editable bag bound to the AI settings AutoForm scheme.

    Field edits auto-persist (:meth:`_persist`) so a pasted token is never lost,
    and pasting a token also verifies the endpoint (:meth:`apply_token`).
    """

    def __init__(self) -> None:
        # Guards read by __setattr__; set before any persisted attribute exists.
        self._ready = False
        self._loading = False
        self._saving = False
        #: Optional refresh callback, set by the tool (kept Qt-free here).
        self.on_change: typing.Callable[[], None] | None = None
        #: Optional off-thread runner injected by the tool: ``runner(work, done)``
        #: runs ``work()`` on a background thread and calls ``done(result)`` back on
        #: the GUI thread. ``None`` runs synchronously (headless/tests).
        self.async_runner: (
            typing.Callable[
                [typing.Callable[[], typing.Any], typing.Callable[[typing.Any], None]], None
            ]
            | None
        ) = None
        self.status_html: str = ""
        #: Plain-text twin of :attr:`status_html` (what the emtk result area draws).
        self.status_text: str = ""
        #: Whether the API key is shown in clear. Session only: never saved, and a
        #: provider switch (or a new model) hides the key again.
        self.show_key: bool = False
        #: Bumped when the provider changes or the fields reset, so the answer of a
        #: request started before that is dropped instead of filling the new provider's fields.
        self._epoch: int = 0
        #: True while a network request runs (set by the host that runs the jobs).
        self.busy: bool = False
        self._text_models: list[str] = []
        self._image_models: list[str] = []
        # Populate every attribute from the currently selected provider.
        self._apply_settings(ai_settings.get_api_settings())
        self._ready = True

    def __setattr__(self, name: str, value: typing.Any) -> None:
        """Set the attribute, then auto-persist when an editable field changes."""
        object.__setattr__(self, name, value)
        if (
            name in _PERSIST_FIELDS
            and getattr(self, "_ready", False)
            and not getattr(self, "_loading", False)
            and not getattr(self, "_saving", False)
        ):
            self._persist(silent=True)

    # -- view -----------------------------------------------------------------
    def view_spec(self):
        """Return the parsed ``ai_settings.view.json`` model view."""
        return load_view_spec(_VIEW)

    # -- option sources (editable combos) -------------------------------------
    def available_providers(self) -> list[tuple[str, str]]:
        """The providers, as ``(key, label)`` pairs for the choice widget.

        Read from :data:`~chisurf.core.settings.ai_settings.PROVIDERS` rather
        than restated in the view spec. The spec used to hardcode four of the
        five, so OpenRouter -- which has its own defaults, its own auth headers
        in ``core/agent/llm.py`` and its own tests -- could not be selected in
        the only UI that writes ``selected_provider``. Reading the table keeps
        the labels and the deliberate EU-first ordering in one place.
        """
        return [(key, label) for label, (key, *_rest) in PROVIDERS.items()]

    def available_text_models(self) -> list[str]:
        """Return the fetched text-capable model ids for the text-model combo."""
        return list(self._text_models)

    def available_image_models(self) -> list[str]:
        """Return the fetched image-capable model ids for the image-model combo."""
        return list(self._image_models)

    # -- emtk-facing members (the Qt tool ignores them) -------------------------
    @property
    def has_text_models(self) -> bool:
        """Whether a model list was fetched for the text-model pick list."""
        return bool(self._text_models)

    @property
    def has_image_models(self) -> bool:
        """Whether a model list was fetched for the image-model pick list."""
        return bool(self._image_models)

    @property
    def text_model_pick(self) -> str:
        """The text model, as the pick list shows it."""
        return self.text_model

    @text_model_pick.setter
    def text_model_pick(self, value: str) -> None:
        self.text_model = str(value)

    @property
    def image_model_pick(self) -> str:
        """The image model, as the pick list shows it."""
        return self.image_model

    @image_model_pick.setter
    def image_model_pick(self, value: str) -> None:
        self.image_model = str(value)

    def text_model_choices(self) -> list[str]:
        """Fetched text models, plus the current one when it is not among them."""
        return self._with_current(self._text_models, self.text_model)

    def image_model_choices(self) -> list[str]:
        """Fetched image models, plus the current one when it is not among them."""
        return self._with_current(self._image_models, self.image_model)

    @staticmethod
    def _with_current(fetched: list[str], current: str) -> list[str]:
        """Pick-list entries: the fetched ids, led by *current* when it is a custom id."""
        current = (current or "").strip()
        return [current, *fetched] if current and current not in fetched else list(fetched)

    def acp_backend_options(self) -> list[tuple[str, str]]:
        """``(key, label)`` pairs for the ACP server's HTTP provider; ``""`` follows the selected one."""
        return [("", "Selected HTTP provider")] + [
            (key, label) for key, label in self.available_providers() if key != "acp"
        ]

    def enabled(self, name: str) -> bool:
        """Whether the action *name* may start now: a request runs one at a time."""
        if name in ("fetch_models", "test_connection"):
            return not self.busy
        return True

    # -- status ---------------------------------------------------------------
    def status_source(self) -> str:
        """Live HTML for the status ``info`` section."""
        return self.status_html

    # -- provider -------------------------------------------------------------
    def set_provider(self, provider: str) -> None:
        """Load the saved settings for *provider* into the visible fields."""
        provider = ai_settings.normalize_provider_key(provider)
        self._epoch += 1
        self._apply_settings(ai_settings.get_api_settings(provider))
        # Fetched model lists belong to the previous endpoint — drop them.
        self._text_models = []
        self._image_models = []
        self.status_html = ""
        self.status_text = ""
        self.show_key = False
        self._notify()

    def sign_in(self) -> None:
        """Open the selected provider's API-key console in the browser."""
        for _display, (key, _url, api_url, _env) in PROVIDERS.items():
            if key == self.provider and api_url:
                webbrowser.open(api_url)
                self._set_status(f"Opened {api_url} in browser", "blue")
                return
        self._set_status("No browser sign-in available for this provider", "orange")

    # -- network (runs off the UI thread when an async_runner is injected) -----
    def fetch_models(self) -> None:
        """Query the endpoint's ``/models`` list and split it by capability."""
        base_url = (self.base_url or "").strip()
        if not base_url:
            self._set_status("Enter a base URL first.", "red")
            return
        self._set_status("Fetching models…", "blue")
        key = (self.api_key or "").strip()
        provider = self.provider
        epoch = self._epoch

        def work():
            try:
                return ("ok", self._get_models(base_url, key))
            except Exception as exc:  # network / parse errors are user-facing
                return ("error", describe_error(exc))

        def done(result):
            if epoch != self._epoch:
                return  # the provider changed while the request ran
            kind, payload = result
            if kind == "error":
                self._set_status(f"Failed: {payload}", "red")
                return
            model_data = payload.get("data", []) if isinstance(payload, dict) else []
            text_models, image_models = ai_settings.split_models_by_capability(
                model_data, provider=provider
            )
            all_models = sorted(
                {
                    str((m.get("id") or m.get("name") or "") if isinstance(m, dict) else m).strip()
                    for m in model_data
                }
                - {""}
            )
            self._text_models = text_models or all_models
            self._image_models = image_models
            self._set_status(
                f"Found {len(self._text_models)} text and {len(self._image_models)} image models.",
                "green",
            )

        self._run(work, done)

    def test_connection(self) -> None:
        """Check the endpoint answers a ``/models`` request."""
        base_url = (self.base_url or "").strip()
        if not base_url:
            self._set_status("No base URL provided.", "red")
            return
        self._set_status("Testing connection…", "blue")
        key = (self.api_key or "").strip()
        epoch = self._epoch

        def work():
            try:
                self._get_models(base_url, key)
                return ("Connection successful!", "green")
            except Exception as exc:
                return (f"Connection failed: {describe_error(exc)}", "red")

        def done(result):
            if epoch == self._epoch:
                self._set_status(*result)

        self._run(work, done)

    def apply_token(self, value: str | None = None) -> None:
        """Paste-and-go: the token is already auto-saved, so just verify it.

        Wired to the API-key field's ``call`` so entering/pasting a key (on
        focus-out or Enter) immediately tests the endpoint — no Save/Test clicks.
        """
        self.test_connection()

    # -- persistence ----------------------------------------------------------
    def save(self) -> None:
        """Persist the current provider's settings and report the outcome."""
        ok = self._persist(silent=False)
        if not ok:
            return

    def reset(self) -> None:
        """Reset the current provider's fields to their defaults, without saving."""
        # Fall back to the default provider's block, not openai's: the tree's
        # documented default is mistral (EU-first), and disagreeing here handed
        # a user of an unknown provider a US endpoint.
        defaults = DEFAULT_PROVIDER_SETTINGS.get(
            self.provider, DEFAULT_PROVIDER_SETTINGS[ai_settings.DEFAULT_PROVIDER]
        )
        self._epoch += 1
        self._apply_settings({**defaults, "provider": self.provider})
        self._text_models = []
        self._image_models = []
        # Deliberately *not* persisted: the button's own description says
        # "not saved until you press Save", and this used to write immediately
        # -- silently destroying a working API key with no undo.
        self._set_status("Fields reset to defaults. Press Save to keep them.", "blue")

    def _persist(self, silent: bool = False) -> bool:
        """Write the current provider's fields to the settings JSON.

        ``silent`` suppresses the status message (used by auto-save on every field
        change); the explicit Save button uses ``silent=False`` for feedback. The
        ``_saving`` guard stops the normalized ``base_url`` write-back from
        re-triggering :meth:`__setattr__` auto-save.
        """
        self._saving = True
        save_error = ""
        try:
            base_url = (self.base_url or "").strip()
            if self.provider != "custom" and not base_url:
                base_url = DEFAULT_PROVIDER_SETTINGS.get(self.provider, {}).get("base_url", "")
            ok = ai_settings.save_api_settings(
                {
                    "provider": self.provider,
                    "base_url": base_url,
                    "api_key": (self.api_key or "").strip(),
                    "text_model": (self.text_model or "").strip(),
                    "image_model": (self.image_model or "").strip(),
                    "temperature": float(self.temperature),
                    "top_p": float(self.top_p),
                    "max_tokens": int(self.max_tokens),
                    "command": str(self.command),
                    "acp_backend_provider": str(self.acp_backend_provider),
                }
            )
            if ok and base_url != self.base_url:
                self.base_url = base_url  # show the resolved URL (guarded: no re-save)
        except Exception as error:
            ok = False
            save_error = f"Failed to save settings: {error}"
        finally:
            self._saving = False
        if not silent or not ok:
            if ok:
                self._set_status("Settings saved.", "green")
            else:
                self._set_status(save_error or "Failed to save settings.", "red")
        return ok

    # -- internals ------------------------------------------------------------
    def _run(
        self, work: typing.Callable[[], typing.Any], done: typing.Callable[[typing.Any], None]
    ) -> None:
        """Run ``work`` off-thread via the injected runner, else synchronously.

        ``work`` must be self-contained (no ``self`` mutation, no Qt); ``done``
        receives its result on the GUI thread and performs the state/status update.
        """
        runner = self.async_runner
        if callable(runner):
            if runner(work, done) is False:  # the host runs one request at a time
                self._set_status(
                    "Another request is still running. Try again in a moment.", "orange"
                )
        else:
            done(work())

    def _apply_settings(self, settings: typing.Mapping[str, typing.Any]) -> None:
        """Copy a settings mapping onto the field attributes (no auto-save)."""
        self._loading = True
        try:
            self.provider = ai_settings.normalize_provider_key(settings.get("provider"))
            self.base_url = str(settings.get("base_url", "") or "")
            self.api_key = str(settings.get("api_key", "") or "")
            self.text_model = str(settings.get("text_model", settings.get("model", "")) or "")
            self.image_model = str(settings.get("image_model", "") or "")
            self.temperature = float(settings.get("temperature", 0.3))
            self.top_p = float(settings.get("top_p", 0.9))
            self.max_tokens = int(settings.get("max_tokens", 4096))
            self.command = str(settings.get("command", "") or "")
            self.acp_backend_provider = str(settings.get("acp_backend_provider", "") or "")
        finally:
            self._loading = False

    @staticmethod
    def _get_models(base_url: str, api_key: str) -> dict:
        """GET ``{base_url}/models`` and return the parsed JSON (raises on error)."""
        from chisurf.core.support import http

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = base_url.rstrip("/") + "/models"
        response = http.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            raise RuntimeError(f"API error {response.status_code}: {response.text[:100]}")
        return response.json()

    def _set_status(self, message: str, color: str = "black") -> None:
        """Record an HTML status message and refresh the view."""
        # Escaped: ``message`` carries str(exc), which carries the provider's
        # response body. A server answering with markup would otherwise have it
        # rendered as rich text in the status label.
        message = self._redact(str(message))
        self.status_html = f"<span style='color: {color};'>{html.escape(message)}</span>"
        self.status_text = message
        self._notify()

    def _redact(self, message: str) -> str:
        """Return *message* without the API key: a provider may echo the key in an error body."""
        key = (self.api_key or "").strip()
        return message.replace(key, "[redacted]") if len(key) >= 6 else message

    def _notify(self) -> None:
        """Invoke the tool-supplied refresh callback, if any."""
        if callable(self.on_change):
            try:
                self.on_change()
            except Exception:  # pragma: no cover - defensive
                _LOG.warning("AISettingsModel.on_change failed", exc_info=True)


class BackgroundCall:
    """One request, as the target of a :class:`~chisurf.emtk.jobs.SnapshotJob`.

    The job runs :meth:`run` on a copy of this object in a worker thread and
    copies the result back, then calls :meth:`notify`; the answer is handed to
    ``done`` there, on the thread that polls the job. The settings model itself
    is never copied, so an edit made while a request runs is not overwritten by
    the job's snapshot.
    """

    def __init__(self) -> None:
        self.work: typing.Callable[[], typing.Any] | None = None
        self.done: typing.Callable[[typing.Any], None] | None = None
        self.result: typing.Any = None
        self.status_text = ""
        self._observers: list = []

    def prepare(self, work, done) -> None:
        """Set what the next job runs and where its answer goes."""
        self.work, self.done, self.result = work, done, None

    def run(self) -> None:
        """Run the request (in the worker thread)."""
        self.result = self.work()

    def notify(self, event: str) -> None:
        """Deliver the answer once, when the job's result has been copied back."""
        if event == "updated" and self.result is not None and self.done is not None:
            result, done = self.result, self.done
            self.result = self.done = None
            done(result)
