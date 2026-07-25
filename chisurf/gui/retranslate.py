"""Live retranslation of runtime-loaded ``.ui`` widgets.

ChiSurf loads its Qt Designer forms at runtime with :func:`uic.loadUi`, which
translates each string *once*, as the widget tree is built. Installing a new
:class:`~qtpy.QtCore.QTranslator` afterwards therefore only affects widgets built
*after* the switch — already-open windows keep their old-language text until they
are rebuilt.

:func:`retranslate_from_ui` closes that gap without destroying the live widget
(and thus without re-running any custom-widget ``__init__`` or dropping signal
connections and state): it parses the ``.ui`` XML for every translatable string,
re-translates it through the *currently installed* translator, and writes the
result straight onto the matching live child widget/action by ``objectName``.

The translation context is the form's ``<class>`` element — the same context Qt
Linguist / ``pylupdate5`` register the ``.ui`` strings under — so the lookup hits
the compiled ``.qm`` catalogue.
"""

from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET

from qtpy import QtCore

#: ``.ui`` ``<property name>`` → live-object setter for the translatable text
#: properties Qt Designer emits. ``text`` covers actions, buttons and labels;
#: ``title`` covers group boxes and menus; the rest are self-explanatory.
_SETTERS = {
    "text": "setText",
    "title": "setTitle",
    "windowTitle": "setWindowTitle",
    "toolTip": "setToolTip",
    "statusTip": "setStatusTip",
    "placeholderText": "setPlaceholderText",
    "whatsThis": "setWhatsThis",
}


def retranslate_from_ui(target: QtCore.QObject, ui_path: str | pathlib.Path) -> None:
    """Re-apply the current translation to ``target``'s widgets from its ``.ui``.

    Parameters
    ----------
    target
        The live widget originally populated from ``ui_path`` (e.g. the main
        window). Its child widgets and actions are matched to the ``.ui`` by
        ``objectName`` and their translatable text is refreshed in place.
    ui_path
        Path to the Qt Designer ``.ui`` file ``target`` was loaded from.

    Notes
    -----
    Silent on any error — retranslation is best-effort chrome polish and must
    never crash the UI. Elements marked ``notr="true"`` in the ``.ui`` are left
    untouched, matching Qt's own extraction rules.
    """
    try:
        root = ET.parse(str(ui_path)).getroot()
    except Exception:  # pragma: no cover - unreadable/absent .ui
        return

    context = (root.findtext("class") or type(target).__name__).strip()
    translate = QtCore.QCoreApplication.translate

    # Map every named child (and the target itself) so lookups are O(1).
    by_name: dict[str, QtCore.QObject] = {}
    for obj in target.findChildren(QtCore.QObject):
        name = obj.objectName()
        if name and name not in by_name:
            by_name[name] = obj
    if target.objectName():
        by_name.setdefault(target.objectName(), target)

    for element in root.iter():
        if element.tag not in ("widget", "action"):
            continue
        obj = by_name.get(element.get("name") or "")
        if obj is None:
            continue
        for prop in element.findall("property"):
            setter_name = _SETTERS.get(prop.get("name") or "")
            if setter_name is None:
                continue
            string_el = prop.find("string")
            if string_el is None or string_el.get("notr") == "true":
                continue
            source = string_el.text or ""
            if not source:
                continue
            setter = getattr(obj, setter_name, None)
            if setter is None:
                continue
            try:
                setter(translate(context, source))
            except Exception:  # pragma: no cover - defensive per-property
                pass
