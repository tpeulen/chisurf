"""Shared native game chrome catalogs; specialized game contexts stay local."""

from emtk import i18n

LOCALES = ("de", "fr", "es", "pt", "ru")
STRINGS = {
    "Game help": (
        "Spielhilfe",
        "Aide du jeu",
        "Ayuda del juego",
        "Ajuda do jogo",
        "Помощь по игре",
    ),
    "Help": ("Hilfe", "Aide", "Ayuda", "Ajuda", "Помощь"),
    "Restart": ("Neustart", "Recommencer", "Reiniciar", "Reiniciar", "Заново"),
    "Guide": ("Anleitung", "Visite", "Guía", "Guia", "Обучение"),
    "Help, restart and a guided tour of the current game.": (
        "Hilfe, Neustart und eine Anleitung für das aktuelle Spiel.",
        "Aide, nouvelle partie et visite guidée du jeu actuel.",
        "Ayuda, reinicio y una visita guiada del juego actual.",
        "Ajuda, reinício e uma visita guiada do jogo atual.",
        "Помощь, новая партия и обучение в текущей игре.",
    ),
    "Explain the rules, controls and sound support for this game.": (
        "Regeln, Steuerung und Tonunterstützung dieses Spiels erklären.",
        "Expliquer les règles, les commandes et le son de ce jeu.",
        "Explicar las reglas, los controles y el sonido de este juego.",
        "Explicar as regras, os controles e o som deste jogo.",
        "Объяснить правила, управление и поддержку звука в этой игре.",
    ),
    "Start a new round of the current game.": (
        "Eine neue Runde des aktuellen Spiels starten.",
        "Commencer une nouvelle partie du jeu actuel.",
        "Iniciar una nueva ronda del juego actual.",
        "Iniciar uma nova rodada do jogo atual.",
        "Начать новую партию текущей игры.",
    ),
    "Walk through the real Restart and Help buttons without changing the round automatically.": (
        "Die echten Schaltflächen Neustart und Hilfe kennenlernen, ohne die Runde automatisch zu ändern.",
        "Découvrir les boutons Recommencer et Aide sans changer automatiquement la partie.",
        "Conocer los botones Reiniciar y Ayuda sin cambiar la ronda automáticamente.",
        "Conhecer os botões Reiniciar e Ajuda sem alterar a rodada automaticamente.",
        "Познакомиться с кнопками Заново и Помощь без автоматического изменения партии.",
    ),
    "Step {step} of {total}: {title}": (
        "Schritt {step} von {total}: {title}",
        "Étape {step} sur {total} : {title}",
        "Paso {step} de {total}: {title}",
        "Etapa {step} de {total}: {title}",
        "Шаг {step} из {total}: {title}",
    ),
    "Close Tour": (
        "Anleitung schließen",
        "Fermer la visite",
        "Cerrar guía",
        "Fechar guia",
        "Закрыть обучение",
    ),
    "◄ Prev": ("◄ Zurück", "◄ Précédent", "◄ Anterior", "◄ Anterior", "◄ Назад"),
    "Next ►": ("Weiter ►", "Suivant ►", "Siguiente ►", "Próximo ►", "Далее ►"),
    "Finish ✓": ("Fertig ✓", "Terminer ✓", "Finalizar ✓", "Concluir ✓", "Готово ✓"),
    "Close the guided tour and return to the tool.": (
        "Die Anleitung schließen und zum Werkzeug zurückkehren.",
        "Fermer la visite guidée et revenir à l’outil.",
        "Cerrar la guía y volver a la herramienta.",
        "Fechar a visita guiada e voltar à ferramenta.",
        "Закрыть обучение и вернуться к инструменту.",
    ),
    "Go to the previous tour step.": (
        "Zum vorherigen Schritt der Anleitung wechseln.",
        "Passer à l’étape précédente de la visite.",
        "Ir al paso anterior de la guía.",
        "Ir à etapa anterior da visita.",
        "Перейти к предыдущему шагу обучения.",
    ),
    "This is the first tour step.": (
        "Dies ist der erste Schritt der Anleitung.",
        "C’est la première étape de la visite.",
        "Este es el primer paso de la guía.",
        "Esta é a primeira etapa da visita.",
        "Это первый шаг обучения.",
    ),
    "Use the highlighted control to continue.": (
        "Das markierte Bedienelement verwenden, um fortzufahren.",
        "Utiliser la commande mise en évidence pour continuer.",
        "Usar el control resaltado para continuar.",
        "Usar o controle destacado para continuar.",
        "Используйте выделенный элемент управления для продолжения.",
    ),
    "Finish the guided tour.": (
        "Die Anleitung abschließen.",
        "Terminer la visite guidée.",
        "Finalizar la guía.",
        "Concluir a visita guiada.",
        "Завершить обучение.",
    ),
    "Go to the next tour step.": (
        "Zum nächsten Schritt der Anleitung wechseln.",
        "Passer à l’étape suivante de la visite.",
        "Ir al siguiente paso de la guía.",
        "Ir à próxima etapa da visita.",
        "Перейти к следующему шагу обучения.",
    ),
    "Guided Tour": ("Anleitung", "Visite guidée", "Visita guiada", "Visita guiada", "Обучение"),
    "drag here to move": (
        "Hier ziehen",
        "Déplacer ici",
        "Arrastrar aquí",
        "Arrastar aqui",
        "Перетащить",
    ),
    "💡 {hint}": ("💡 {hint}", "💡 {hint}", "💡 {hint}", "💡 {hint}", "💡 {hint}"),
}


def install_translations() -> None:
    """Register shared chrome in the default native translation context."""
    for index, locale in enumerate(LOCALES):
        i18n.add_translations(
            locale, {source: values[index] for source, values in STRINGS.items()}, context="default"
        )
