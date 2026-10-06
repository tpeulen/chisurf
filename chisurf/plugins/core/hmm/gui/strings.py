from emtk import i18n

_CATALOGS = {
    "de": {
        "Hidden Markov model": "Hidden-Markov-Modell",
        "States": "Zustände",
        "Iterations": "Iterationen",
        "Minimum states": "Minimale Zustände",
        "Maximum states": "Maximale Zustände",
        "Accelerate": "Beschleunigen",
        "Fit": "Anpassen",
        "Scan states": "Zustände scannen",
        "Trace": "Spur",
        "Histogram": "Histogramm",
        "State scan": "Zustandsscan",
        "Fitted states": "Gefittete Zustände",
        "Transitions": "Übergänge",
    },
    "fr": {
        "Hidden Markov model": "Modèle de Markov caché",
        "States": "États",
        "Iterations": "Itérations",
        "Minimum states": "États minimum",
        "Maximum states": "États maximum",
        "Accelerate": "Accélérer",
        "Fit": "Ajuster",
        "Scan states": "Analyser les états",
        "Trace": "Trace",
        "Histogram": "Histogramme",
        "State scan": "Analyse des états",
        "Fitted states": "États ajustés",
        "Transitions": "Transitions",
    },
    "es": {
        "Hidden Markov model": "Modelo de Markov oculto",
        "States": "Estados",
        "Iterations": "Iteraciones",
        "Fit": "Ajustar",
        "Scan states": "Analizar estados",
        "Fitted states": "Estados ajustados",
        "Transitions": "Transiciones",
    },
    "pt": {
        "Hidden Markov model": "Modelo de Markov oculto",
        "States": "Estados",
        "Iterations": "Iterações",
        "Fit": "Ajustar",
        "Scan states": "Analisar estados",
        "Fitted states": "Estados ajustados",
        "Transitions": "Transições",
    },
    "ru": {
        "Hidden Markov model": "Скрытая марковская модель",
        "States": "Состояния",
        "Iterations": "Итерации",
        "Fit": "Подогнать",
        "Scan states": "Сканировать состояния",
        "Fitted states": "Подогнанные состояния",
        "Transitions": "Переходы",
    },
}


def install_translations():
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="HMM")


def tr(text):
    return i18n.tr(text, context="HMM")
