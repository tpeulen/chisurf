from emtk import i18n

_CATALOGS = {
    "de": {
        "Steps": "Schritte",
        "Help": "Hilfe",
        "Guide": "Führung",
        "Restore defaults": "Standards wiederherstellen",
        "Welcome to ChiSurf": "Willkommen bei ChiSurf",
        "Welcome": "Willkommen",
        "Repair settings": "Einstellungen reparieren",
        "Status": "Status",
        "Finish": "Fertig",
        "Create missing files": "Fehlende Dateien erstellen",
        "Restore defaults": "Standards wiederherstellen",
        "Open settings folder": "Einstellungsordner öffnen",
    },
    "fr": {
        "Steps": "Étapes",
        "Help": "Aide",
        "Guide": "Visite guidée",
        "Restore defaults": "Restaurer les valeurs par défaut",
        "Welcome to ChiSurf": "Bienvenue dans ChiSurf",
        "Welcome": "Bienvenue",
        "Repair settings": "Réparer les réglages",
        "Status": "État",
        "Finish": "Terminer",
        "Create missing files": "Créer les fichiers manquants",
        "Restore defaults": "Restaurer les valeurs par défaut",
        "Open settings folder": "Ouvrir le dossier des réglages",
    },
    "es": {
        "Steps": "Pasos",
        "Help": "Ayuda",
        "Guide": "Guía",
        "Restore defaults": "Restaurar valores predeterminados",
        "Welcome to ChiSurf": "Bienvenido a ChiSurf",
        "Welcome": "Bienvenida",
        "Repair settings": "Reparar ajustes",
        "Status": "Estado",
        "Finish": "Finalizar",
        "Create missing files": "Crear archivos faltantes",
        "Restore defaults": "Restaurar valores predeterminados",
        "Open settings folder": "Abrir carpeta de ajustes",
    },
    "pt": {
        "Steps": "Passos",
        "Help": "Ajuda",
        "Guide": "Guia",
        "Restore defaults": "Restaurar predefinições",
        "Welcome to ChiSurf": "Bem-vindo ao ChiSurf",
        "Welcome": "Boas-vindas",
        "Repair settings": "Reparar definições",
        "Status": "Estado",
        "Finish": "Concluir",
        "Create missing files": "Criar ficheiros em falta",
        "Restore defaults": "Restaurar predefinições",
        "Open settings folder": "Abrir pasta de definições",
    },
    "ru": {
        "Steps": "Шаги",
        "Help": "Справка",
        "Guide": "Обзор",
        "Restore defaults": "Восстановить значения по умолчанию",
        "Welcome to ChiSurf": "Добро пожаловать в ChiSurf",
        "Welcome": "Обзор",
        "Repair settings": "Восстановить настройки",
        "Status": "Состояние",
        "Finish": "Завершение",
        "Create missing files": "Создать недостающие файлы",
        "Restore defaults": "Восстановить значения по умолчанию",
        "Open settings folder": "Открыть папку настроек",
    },
}


def install_translations():
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="Boarding")


def tr(text):
    return i18n.tr(text, context="Boarding")
