"""Translations for the native flow-map tool."""

from emtk import i18n

_CATALOGS = {
    "de": {"Flow map": "Flusskarte", "Load demo": "Demo laden", "Map flow": "Fluss kartieren", "Parameters": "Parameter", "Velocity profile": "Geschwindigkeitsprofil", "Export CSV": "CSV exportieren"},
    "fr": {"Flow map": "Carte de flux", "Load demo": "Charger la démo", "Map flow": "Cartographier le flux", "Parameters": "Paramètres", "Velocity profile": "Profil de vitesse", "Export CSV": "Exporter CSV"},
    "es": {"Flow map": "Mapa de flujo", "Load demo": "Cargar demo", "Map flow": "Mapear flujo", "Parameters": "Parámetros", "Velocity profile": "Perfil de velocidad", "Export CSV": "Exportar CSV"},
    "pt": {"Flow map": "Mapa de fluxo", "Load demo": "Carregar demonstração", "Map flow": "Mapear fluxo", "Parameters": "Parâmetros", "Velocity profile": "Perfil de velocidade", "Export CSV": "Exportar CSV"},
    "ru": {"Flow map": "Карта потока", "Load demo": "Загрузить демо", "Map flow": "Картировать поток", "Parameters": "Параметры", "Velocity profile": "Профиль скорости", "Export CSV": "Экспорт CSV"},
}


def install_translations() -> None:
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="Flow map")


def tr(text: str) -> str:
    return i18n.tr(text, context="Flow map")

