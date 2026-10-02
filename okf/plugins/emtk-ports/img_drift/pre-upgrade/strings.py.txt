"""Translations for native drift correction."""

from emtk import i18n

_CATALOGS = {
    "de": {"Drift correction": "Driftkorrektur", "Measure": "Messen", "Parameters": "Parameter", "Measured drift": "Gemessener Drift", "Export shifts": "Verschiebungen exportieren", "Export stack": "Stapel exportieren"},
    "fr": {"Drift correction": "Correction de dérive", "Measure": "Mesurer", "Parameters": "Paramètres", "Measured drift": "Dérive mesurée", "Export shifts": "Exporter les déplacements", "Export stack": "Exporter la pile"},
    "es": {"Drift correction": "Corrección de deriva", "Measure": "Medir", "Parameters": "Parámetros", "Measured drift": "Deriva medida", "Export shifts": "Exportar desplazamientos", "Export stack": "Exportar pila"},
    "pt": {"Drift correction": "Correção de deriva", "Measure": "Medir", "Parameters": "Parâmetros", "Measured drift": "Deriva medida", "Export shifts": "Exportar deslocamentos", "Export stack": "Exportar pilha"},
    "ru": {"Drift correction": "Коррекция дрейфа", "Measure": "Измерить", "Parameters": "Параметры", "Measured drift": "Измеренный дрейф", "Export shifts": "Экспортировать смещения", "Export stack": "Экспортировать стек"},
}


def install_translations() -> None:
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="Drift correction")


def tr(text: str) -> str:
    return i18n.tr(text, context="Drift correction")

