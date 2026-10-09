from emtk import i18n

_CATALOGS = {
    "de": {
        "Wizards": "Assistenten",
        "Available wizards": "Verfügbare Assistenten",
        "No wizard selected.": "Kein Assistent ausgewählt.",
    },
    "fr": {
        "Wizards": "Assistants",
        "Available wizards": "Assistants disponibles",
        "No wizard selected.": "Aucun assistant sélectionné.",
    },
    "es": {
        "Wizards": "Asistentes",
        "Available wizards": "Asistentes disponibles",
        "No wizard selected.": "Ningún asistente seleccionado.",
    },
    "pt": {
        "Wizards": "Assistentes",
        "Available wizards": "Assistentes disponíveis",
        "No wizard selected.": "Nenhum assistente selecionado.",
    },
    "ru": {
        "Wizards": "Мастера",
        "Available wizards": "Доступные мастера",
        "No wizard selected.": "Мастер не выбран.",
    },
}


def install_translations():
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="Wizards")


def tr(text):
    return i18n.tr(text, context="Wizards")
