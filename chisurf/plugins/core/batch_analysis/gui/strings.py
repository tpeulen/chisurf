from emtk import i18n

_CATALOGS = {
    "de": {
        "Batch Analysis": "Stapelverarbeitung",
        "Selection": "Auswahl",
        "Template fit": "Vorlagenfit",
        "CSV output": "CSV-Ausgabe",
        "Run batch": "Stapel ausführen",
        "Results": "Ergebnisse",
    },
    "fr": {
        "Batch Analysis": "Analyse par lots",
        "Selection": "Sélection",
        "Template fit": "Ajustement modèle",
        "CSV output": "Sortie CSV",
        "Run batch": "Exécuter le lot",
        "Results": "Résultats",
    },
    "es": {
        "Batch Analysis": "Análisis por lotes",
        "Selection": "Selección",
        "Template fit": "Ajuste plantilla",
        "CSV output": "Salida CSV",
        "Run batch": "Ejecutar lote",
        "Results": "Resultados",
    },
    "pt": {
        "Batch Analysis": "Análise em lote",
        "Selection": "Seleção",
        "Template fit": "Ajuste modelo",
        "CSV output": "Saída CSV",
        "Run batch": "Executar lote",
        "Results": "Resultados",
    },
    "ru": {
        "Batch Analysis": "Пакетный анализ",
        "Selection": "Выбор",
        "Template fit": "Шаблонная подгонка",
        "CSV output": "Вывод CSV",
        "Run batch": "Запустить пакет",
        "Results": "Результаты",
    },
}


def install_translations():
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="Batch Analysis")


def tr(text):
    return i18n.tr(text, context="Batch Analysis")
