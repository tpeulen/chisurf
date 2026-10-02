"""Translations for native FRC resolution."""

from emtk import i18n

_CATALOGS = {"de": {"FRC resolution": "FRC-Auflösung", "Measure": "Messen", "FRC curve": "FRC-Kurve", "Export CSV": "CSV exportieren"}, "fr": {"FRC resolution": "Résolution FRC", "Measure": "Mesurer", "FRC curve": "Courbe FRC", "Export CSV": "Exporter CSV"}, "es": {"FRC resolution": "Resolución FRC", "Measure": "Medir", "FRC curve": "Curva FRC", "Export CSV": "Exportar CSV"}, "pt": {"FRC resolution": "Resolução FRC", "Measure": "Medir", "FRC curve": "Curva FRC", "Export CSV": "Exportar CSV"}, "ru": {"FRC resolution": "Разрешение FRC", "Measure": "Измерить", "FRC curve": "Кривая FRC", "Export CSV": "Экспорт CSV"}}

def install_translations() -> None:
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="FRC resolution")

def tr(text: str) -> str:
    return i18n.tr(text, context="FRC resolution")

