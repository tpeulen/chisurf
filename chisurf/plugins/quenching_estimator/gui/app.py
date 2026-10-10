"""The native QuEst window of this plugin: the QuEst card of Structure Tools, hosted on its own.

The card (``chisurf.plugins.modelling.structure_tools.cards.quest``) is the emtk counterpart of ``QuEstTool``: the project
form of ``quest.view.json``, the quenching table, the three result plots, a 3D trace of the structure and the project JSON.
It is reused here, not copied; the import is inside the factory so that importing this module pulls in neither IMP nor quest.

This window adds to the card's *3D Structure* tab what the Qt tool's molecule widget had: choose Donor or Acceptor, then
pick the attachment residue from the residue list of the loaded structure (the list stands in for the 3D click of the
legacy widget: the implot3d plot offers no ray pick), and an *Open Web UI* button for the local QuEst web interface.
"""

from __future__ import annotations

WEB_UI_URL = "http://localhost:3000"
_SITE_ATOMS = ("CB", "CA")


def pick_site(session, target: str, chain: str, residue: int) -> str:
    """Make ``chain:residue`` the *target* (``"donor"`` or ``"acceptor"``) attachment site; returns the status text.

    The atom is CB (CA for glycine), as the Qt widget's pick used CB. Choosing the acceptor switches FRET on.
    """
    model = session.model
    atoms = session.structure.atoms if session.structure is not None else None
    atom = "CB"
    if atoms is not None:
        here = (atoms["chain"] == str(chain)) & (atoms["res_id"] == int(residue))
        names = set(atoms["atom_name"][here])
        atom = next((a for a in _SITE_ATOMS if a in names), "CB")
    site = {"chain": str(chain), "residue": int(residue), "atom": atom}
    if target == "acceptor":
        fret = model.project.setdefault("fret", {})
        fret["enabled"] = True
        dyes = fret.setdefault("dyes", [])
        while len(dyes) < 2:
            dyes.append(
                {
                    "name": "acceptor",
                    "D": 7.5,
                    "attachment": dict(site),
                    "av_parameter": {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5},
                }
            )
        dyes[1]["attachment"] = dict(site)
    else:
        model.attachment_chain, model.attachment_residue, model.attachment_atom = (
            site["chain"],
            site["residue"],
            site["atom"],
        )
        dyes = model.project.get("fret", {}).get("dyes", [])
        if dyes:
            dyes[0]["attachment"] = dict(site)
    text = f"Selected {target}: {chain}:{residue}"
    session.say(text)
    return text


def residues(session) -> list[tuple[str, int, str]]:
    """``(chain, residue number, residue name)`` of the loaded structure, in file order, one per residue."""
    if session.backbone() is None or session.structure is None:
        return []
    atoms = session.structure.atoms
    seen, out = set(), []
    for chain, number, name in zip(atoms["chain"], atoms["res_id"], atoms["res_name"]):
        key = (str(chain), int(number))
        if key not in seen and str(name).strip() not in ("HOH", "WAT"):
            seen.add(key)
            out.append((str(chain), int(number), str(name).strip()))
    return out


def make_app():
    """Build the QuEst window (the card, as an app of its own, with site picking and the web UI link)."""
    from emtk import im

    from emtk.i18n import tr

    from chisurf.plugins.modelling.structure_tools.cards.quest import QuestCard

    class QuEstWindow(QuestCard):
        """The card plus attachment-site picking by residue and the web UI link."""

        pick_target = "donor"

        def pick(self, chain: str, residue: int) -> None:
            self.status = pick_site(self.session, self.pick_target, chain, residue)
            self.used("pick_site")
            self.sync()

        def open_web_ui(self) -> None:
            import webbrowser

            webbrowser.open(WEB_UI_URL)
            self.session.say(f"Opened {WEB_UI_URL}")
            self.sync()

        def _draw_structure(self) -> None:
            for target, caption in (("donor", "Donor"), ("acceptor", "Acceptor")):
                if im.radio_button(tr(caption) + f"##pick.{target}", self.pick_target == target):
                    self.pick_target = target
                im.set_item_tooltip(
                    tr(f"Choose the {caption.lower()} attachment site: pick its residue in the list below.")
                )
                self.remember(f"pick_{target}")
                im.same_line()
            if im.button(tr("Open Web UI")):
                self.open_web_ui()
            im.set_item_tooltip(tr(f"Open the local QuEst web interface ({WEB_UI_URL})."))
            self.remember("open_web_ui")
            rows = residues(self.session)
            if rows:
                project = self.session.model.project
                att = project.get("attachment", {})
                dyes = project.get("fret", {}).get("dyes", [])
                acc = dyes[1].get("attachment", {}) if len(dyes) > 1 else {}
                current = att if self.pick_target == "donor" else acc
                im.begin_child("##quest_residues", (-1, 130))
                for chain, number, name in rows:
                    on = str(current.get("chain")) == chain and current.get("residue") == number
                    if im.selectable(f"{chain}:{number} {name}##res.{chain}.{number}", on):
                        self.pick(chain, number)
                    im.set_item_tooltip(tr("Use this residue as the attachment site."))
                    self.item_rects[f"res.{chain}.{number}"] = im.get_item_rect()
                im.end_child()
            super()._draw_structure()

    from chisurf.emtk.i18n import install

    install()
    return QuEstWindow()
