"""The Zenodo token as a Settings page: the deposit tool's token tab, on its own.

The token is set where the other settings are (Settings > Zenodo), and is the
same token the deposit tool uses: one model, one spec, the system keychain.
"""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.view_form import FormState, draw_sections

from .model import ZenodoDepositModel

HERE = Path(__file__).resolve().parent


def _token_sections() -> list:
    spec = json.loads((HERE / "zenodo_deposit_emtk.view.json").read_text(encoding="utf-8"))

    def find(x):
        # The token panel: titled "Token" since the deposit tabs were de-cluttered
        # (06a936f2e), "Zenodo token" before -- both spellings stay recognised so
        # the settings page does not depend on the deposit tab's caption.
        if isinstance(x, dict):
            if x.get("title") in ("Zenodo token", "Token") and x.get("sections"):
                return x
            return next((r for v in x.values() if (r := find(v))), None)
        if isinstance(x, list):
            return next((r for v in x if (r := find(v))), None)
        return None

    panel = find(spec)
    if panel is None:
        raise LookupError("the deposit spec has no 'Zenodo token' panel")
    sandbox = {"type": "toggle", "attr": "sandbox", "label": "Sandbox (sandbox.zenodo.org)",
               "description": "Show and set the token of the Zenodo sandbox instead of zenodo.org; "
                              "each has its own token."}
    sandbox = {"type": "row", "n_col": 1, "sections": [sandbox]}
    return [sandbox, *panel["sections"], {"type": "info", "source": "status_text",
                                          "description": "What the last action did."}]


class ZenodoTokenApp(ImApp):
    """Settings > Zenodo: store, test or remove the upload token."""

    def __init__(self, model: ZenodoDepositModel | None = None) -> None:
        self.model = model or ZenodoDepositModel()
        self.sections = _token_sections()
        self.form = FormState()
        self.window_size = (720, 420)
        # This page is about the token: say where it is from now, not "not looked up yet".
        # The keychain is read once, off the draw thread.
        self.model.lookup_token()
        super().__init__(self.render, continuous=True)

    def render(self) -> None:
        self.model.poll()
        vp = im.get_main_viewport()
        im.begin("Zenodo token", (*vp.pos, *vp.size))
        draw_sections(self.sections, self.model, self.form)
        im.end()

    # -- persistence ------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """Which Zenodo the page shows, and its folded sections; never the token (keychain)."""
        return {"sandbox": bool(self.model.sandbox), "folds": dict(self.form.folds)}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; a switched repository re-reads its token."""
        if not isinstance(settings, dict):
            return
        folds = settings.get("folds", {})
        if isinstance(folds, dict):
            self.form.folds.update({str(k): bool(v) for k, v in folds.items()})
        sandbox = bool(settings.get("sandbox", self.model.sandbox))
        if sandbox != self.model.sandbox:
            self.model.sandbox = sandbox
            self.model.lookup_token()

    def close(self) -> None:
        self.model.close()


def make_app() -> ZenodoTokenApp:
    return ZenodoTokenApp()
