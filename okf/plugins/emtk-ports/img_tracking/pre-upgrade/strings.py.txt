"""Translations for native particle tracking."""

from emtk import i18n

_CATALOGS = {"de": {"Particle tracking": "Partikelverfolgung", "Simulate movie": "Film simulieren", "Track": "Verfolgen", "Trajectories": "Trajektorien", "Mean squared displacement": "Mittlere quadratische Verschiebung", "Export CSV": "CSV exportieren"}, "fr": {"Particle tracking": "Suivi de particules", "Simulate movie": "Simuler le film", "Track": "Suivre", "Trajectories": "Trajectoires", "Mean squared displacement": "Déplacement quadratique moyen", "Export CSV": "Exporter CSV"}, "es": {"Particle tracking": "Seguimiento de partículas", "Simulate movie": "Simular película", "Track": "Seguir", "Trajectories": "Trayectorias", "Mean squared displacement": "Desplazamiento cuadrático medio", "Export CSV": "Exportar CSV"}, "pt": {"Particle tracking": "Rastreamento de partículas", "Simulate movie": "Simular filme", "Track": "Rastrear", "Trajectories": "Trajetórias", "Mean squared displacement": "Deslocamento quadrático médio", "Export CSV": "Exportar CSV"}, "ru": {"Particle tracking": "Трекинг частиц", "Simulate movie": "Симулировать фильм", "Track": "Трек", "Trajectories": "Траектории", "Mean squared displacement": "Среднеквадратичное смещение", "Export CSV": "Экспорт CSV"}}

def install_translations() -> None:
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="Particle tracking")

def tr(text: str) -> str:
    return i18n.tr(text, context="Particle tracking")

