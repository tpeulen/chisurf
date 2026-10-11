"""Native About labels and guided actions in the six supported UI locales."""

import json
from pathlib import Path

from emtk import i18n

LOCALES = ("de", "fr", "es", "pt", "ru")
STRINGS = {
    "Result of the most recent attempt to copy application details.": (
        "Ergebnis des letzten Kopierversuchs.",
        "Résultat de la dernière tentative de copie.",
        "Resultado del último intento de copia.",
        "Resultado da última tentativa de cópia.",
        "Результат последней попытки копирования.",
    ),
    "About ChiSurf": (
        "Über ChiSurf",
        "À propos de ChiSurf",
        "Acerca de ChiSurf",
        "Sobre o ChiSurf",
        "О ChiSurf",
    ),
    "About ChiSurf — Help": (
        "Über ChiSurf — Hilfe",
        "À propos de ChiSurf — Aide",
        "Acerca de ChiSurf — Ayuda",
        "Sobre o ChiSurf — Ajuda",
        "О ChiSurf — Справка",
    ),
    "Fluorescence Data Analysis": (
        "Analyse von Fluoreszenzdaten",
        "Analyse de données de fluorescence",
        "Análisis de datos de fluorescencia",
        "Análise de dados de fluorescência",
        "Анализ данных флуоресценции",
    ),
    "Version: {version}": (
        "Version: {version}",
        "Version : {version}",
        "Versión: {version}",
        "Versão: {version}",
        "Версия: {version}",
    ),
    "Development: Thomas-Otavio Peulen": (
        "Entwicklung: Thomas-Otavio Peulen",
        "Développement : Thomas-Otavio Peulen",
        "Desarrollo: Thomas-Otavio Peulen",
        "Desenvolvimento: Thomas-Otavio Peulen",
        "Разработка: Thomas-Otavio Peulen",
    ),
    "Repository: github.com/fluorescence-tools/chisurf": (
        "Repository: github.com/fluorescence-tools/chisurf",
        "Dépôt : github.com/fluorescence-tools/chisurf",
        "Repositorio: github.com/fluorescence-tools/chisurf",
        "Repositório: github.com/fluorescence-tools/chisurf",
        "Репозиторий: github.com/fluorescence-tools/chisurf",
    ),
    "Help": ("Hilfe", "Aide", "Ayuda", "Ajuda", "Помощь"),
    "Copy details": (
        "Infos kopieren",
        "Copier infos",
        "Copiar datos",
        "Copiar dados",
        "Копировать",
    ),
    "Guide": ("Tour", "Visite", "Guía", "Guia", "Обзор"),
    "Close": ("Schließen", "Fermer", "Cerrar", "Fechar", "Закрыть"),
    "Application information, clipboard details, guided help and window closure.": (
        "Programminformationen, Zwischenablage, Anleitung und Schließen.",
        "Informations, copie, visite guidée et fermeture de la fenêtre.",
        "Información, copia, guía y cierre de la ventana.",
        "Informações, cópia, guia e fechamento da janela.",
        "Сведения, копирование, обзор и закрытие окна.",
    ),
    "Explain the version, developer and contact details shown here.": (
        "Version, Entwicklung und Kontaktdaten erläutern.",
        "Expliquer la version, le développeur et les coordonnées affichés.",
        "Explicar la versión, el desarrollador y los datos de contacto.",
        "Explicar a versão, o desenvolvedor e os dados de contato.",
        "Объяснить версию, сведения о разработчике и контакты.",
    ),
    "Copy the displayed application details to the system clipboard.": (
        "Die angezeigten Programminformationen in die Zwischenablage kopieren.",
        "Copier les informations affichées dans le presse-papiers système.",
        "Copiar la información mostrada al portapapeles del sistema.",
        "Copiar as informações exibidas para a área de transferência do sistema.",
        "Скопировать показанные сведения в системный буфер обмена.",
    ),
    "Follow the real Help, Copy details and Close controls.": (
        "Die echten Schaltflächen Hilfe, Infos kopieren und Schließen kennenlernen.",
        "Utiliser les vrais boutons Aide, Copier infos et Fermer.",
        "Seguir los botones reales Ayuda, Copiar datos y Cerrar.",
        "Usar os botões reais Ajuda, Copiar dados e Fechar.",
        "Пройти по настоящим кнопкам Помощь, Копировать и Закрыть.",
    ),
    "Close the About ChiSurf window.": (
        "Das Fenster Über ChiSurf schließen.",
        "Fermer la fenêtre À propos de ChiSurf.",
        "Cerrar la ventana Acerca de ChiSurf.",
        "Fechar a janela Sobre o ChiSurf.",
        "Закрыть окно О ChiSurf.",
    ),
    "Application details copied.": (
        "Programminformationen kopiert.",
        "Informations copiées.",
        "Información copiada.",
        "Informações copiadas.",
        "Сведения скопированы.",
    ),
    "Clipboard unavailable. Try another host or copy the displayed details.": (
        "Zwischenablage nicht verfügbar. Anderen Host nutzen oder Angaben selbst kopieren.",
        "Presse-papiers indisponible. Essayez un autre hôte ou copiez les informations affichées.",
        "Portapapeles no disponible. Pruebe otro host o copie los datos mostrados.",
        "Área de transferência indisponível. Tente outro host ou copie os dados exibidos.",
        "Буфер обмена недоступен. Используйте другой хост или скопируйте показанные данные.",
    ),
    "Read help": ("Hilfe lesen", "Lire l’aide", "Leer ayuda", "Ler ajuda", "Прочитать справку"),
    "Open Help, then close it to return to this guide.": (
        "Hilfe öffnen und schließen, um zur Tour zurückzukehren.",
        "Ouvrez puis fermez l’aide pour revenir à cette visite.",
        "Abra y cierre Ayuda para volver a esta guía.",
        "Abra e feche Ajuda para voltar ao guia.",
        "Откройте и закройте справку, чтобы вернуться к обзору.",
    ),
    "Copy the application details for a support request. No analysis data is included.": (
        "Programminformationen für eine Supportanfrage kopieren. Keine Analysedaten.",
        "Copiez les informations pour une demande d’aide, sans données d’analyse.",
        "Copie los datos del programa para pedir ayuda. No incluye datos de análisis.",
        "Copie os dados do programa para pedir suporte, sem dados de análise.",
        "Скопируйте сведения для обращения в поддержку. Данные анализа не включены.",
    ),
    "Close About": (
        "Info schließen",
        "Fermer À propos",
        "Cerrar Acerca de",
        "Fechar Sobre",
        "Закрыть сведения",
    ),
    "Close the About window when you have the information you need.": (
        "Das Infofenster schließen, wenn Sie alle Angaben haben.",
        "Fermez À propos lorsque vous avez les informations nécessaires.",
        "Cierre Acerca de cuando tenga la información necesaria.",
        "Feche Sobre quando tiver as informações necessárias.",
        "Закройте окно сведений, когда получите нужную информацию.",
    ),
}


def install_translations():
    """Register About labels and only its authored tour prose in the shared context."""
    steps = json.loads(Path(__file__).with_name("guide.json").read_text(encoding="utf-8"))["steps"]
    tour_sources = {step[key] for step in steps for key in ("title", "text")}
    tour_sources.add("Clipboard unavailable. Try another host or copy the displayed details.")
    for index, locale in enumerate(LOCALES):
        i18n.add_translations(
            locale, {source: values[index] for source, values in STRINGS.items()}, context="About"
        )
        i18n.add_translations(
            locale, {source: STRINGS[source][index] for source in tour_sources}, context="default"
        )


def tr(source):
    """Translate a visible About label while keeping its stable control identity."""
    return i18n.tr(source, context="About")
