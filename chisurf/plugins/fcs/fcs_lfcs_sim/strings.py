"""Translations for the native lifetime-FCS simulator."""

from emtk import i18n


def install_translations() -> None:
    catalog = {
        "de": {
            "Lifetime-FCS simulator": "Lifetime-FCS-Simulator",
            "Set parameters and simulate.": "Parameter setzen und simulieren.",
            "Simulate + Correlate": "Simulieren + korrelieren",
            "Filtered correlations": "Gefilterte Korrelationen",
            "Species": "Spezies",
            "Kinetics / statistics": "Kinetik / Statistik",
        },
        "fr": {
            "Lifetime-FCS simulator": "Simulateur FLCS",
            "Set parameters and simulate.": "Définissez les paramètres et simulez.",
            "Simulate + Correlate": "Simuler + corréler",
            "Filtered correlations": "Corrélations filtrées",
            "Species": "Espèces",
            "Kinetics / statistics": "Cinétique / statistiques",
        },
        "es": {
            "Lifetime-FCS simulator": "Simulador FLCS",
            "Set parameters and simulate.": "Defina parámetros y simule.",
            "Simulate + Correlate": "Simular + correlacionar",
            "Filtered correlations": "Correlaciones filtradas",
            "Species": "Especies",
            "Kinetics / statistics": "Cinética / estadísticas",
        },
        "pt": {
            "Lifetime-FCS simulator": "Simulador FLCS",
            "Set parameters and simulate.": "Defina parâmetros e simule.",
            "Simulate + Correlate": "Simular + correlacionar",
            "Filtered correlations": "Correlações filtradas",
            "Species": "Espécies",
            "Kinetics / statistics": "Cinética / estatísticas",
        },
        "ru": {
            "Lifetime-FCS simulator": "Симулятор FLCS",
            "Set parameters and simulate.": "Задайте параметры и запустите симуляцию.",
            "Simulate + Correlate": "Симулировать + коррелировать",
            "Filtered correlations": "Фильтрованные корреляции",
            "Species": "Виды",
            "Kinetics / statistics": "Кинетика / статистика",
        },
    }
    for locale, values in catalog.items():
        i18n.add_translations(locale, values, context="Lifetime-FCS simulator")
