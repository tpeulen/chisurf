"""Plugin-owned catalogs for the six ChiSurf languages."""
from emtk import i18n

LOCALES = ("en", "de", "fr", "es", "pt", "ru")
STRINGS = {
    "Sound": ("Ton", "Son", "Sonido", "Som", "Звук"),
    "Music and sound effects (off by default). Native audio requires a host audio adapter.": (
        "Musik und Klangeffekte (standardmäßig aus). Native Audiowiedergabe benötigt einen Audioadapter des Hosts.",
        "Musique et effets sonores (désactivés par défaut). Le son natif nécessite un adaptateur audio de l'hôte.",
        "Música y efectos (desactivados por defecto). El audio nativo requiere un adaptador de audio del anfitrión.",
        "Música e efeitos (desativados por padrão). O áudio nativo requer um adaptador de áudio do anfitrião.",
        "Музыка и эффекты (по умолчанию выключены). Для звука нужен аудиоадаптер приложения."),
    "Minesweeper": ("Minesweeper", "Démineur", "Buscaminas", "Campo minado", "Сапёр"),
    "Beginner": ("Anfänger", "Débutant", "Principiante", "Iniciante", "Новичок"),
    "Intermediate": ("Fortgeschritten", "Intermédiaire", "Intermedio", "Intermédio", "Средний"),
    "Expert": ("Experte", "Expert", "Experto", "Especialista", "Эксперт"),
    "Hot pixels: {count}": ("Heiße Pixel: {count}", "Pixels chauds : {count}", "Píxeles calientes: {count}", "Pixels quentes: {count}", "Горячие пиксели: {count}"),
    "Array mapped": ("Raster kartiert", "Matrice cartographiée", "Matriz explorada", "Matriz mapeada", "Массив исследован"),
    "Detector saturated": ("Detektor gesättigt", "Détecteur saturé", "Detector saturado", "Detetor saturado", "Детектор насыщен"),
    "Move   Confirm scan   Menu flag": ("Bewegen   Enter scannen   F markieren", "Déplacer   Entrée scanner   F drapeau", "Mover   Intro explorar   F marcar", "Mover   Enter explorar   F marcar", "Движение   Enter открыть   F флаг"),
    "Cancel reset   L/R preset": ("R Neustart   Q/E Schwierigkeit", "R recommencer   Q/E difficulté", "R reiniciar   Q/E dificultad", "R reiniciar   Q/E dificuldade", "R сначала   Q/E сложность"),
    "Start a new game to play again.": ("Zum Weiterspielen neu starten.", "Recommencez pour rejouer.", "Reinicia para volver a jugar.", "Reinicie para jogar novamente.", "Начните новую игру."),
    "Remove the flag before revealing this cell.": ("Vor dem Aufdecken die Markierung entfernen.", "Retirez le drapeau avant de révéler cette case.", "Quita la bandera antes de explorar esta celda.", "Remova a bandeira antes de abrir esta célula.", "Уберите флаг перед открытием клетки."),
    "That cell is already revealed.": ("Dieses Feld ist bereits aufgedeckt.", "Cette case est déjà révélée.", "Esta celda ya está descubierta.", "Esta célula já está aberta.", "Эта клетка уже открыта."),
    "Boom! You found a mine.": ("Bumm! Eine Mine gefunden.", "Boum ! Vous avez trouvé une mine.", "¡Bum! Encontraste una mina.", "Bum! Encontrou uma mina.", "Бум! Вы нашли мину."),
    "You cleared the board! Victory!": ("Alle Felder aufgedeckt! Sieg!", "Vous avez nettoyé la grille ! Victoire !", "¡Tablero despejado! ¡Victoria!", "Tabuleiro limpo! Vitória!", "Поле очищено! Победа!"),
    "Keep searching.": ("Weiter suchen.", "Continuez à chercher.", "Sigue buscando.", "Continue a procurar.", "Продолжайте поиск."),
    "Revealed cells cannot be flagged.": ("Aufgedeckte Felder können nicht markiert werden.", "Les cases révélées ne peuvent pas être marquées.", "No se pueden marcar las celdas descubiertas.", "Não é possível marcar células abertas.", "Нельзя поставить флаг на открытую клетку."),
    "No flags remaining.": ("Keine Markierungen übrig.", "Aucun drapeau restant.", "No quedan banderas.", "Não restam bandeiras.", "Флагов больше нет."),
    "Flag placed.": ("Markierung gesetzt.", "Drapeau placé.", "Bandera colocada.", "Bandeira colocada.", "Флаг установлен."),
    "Flag removed.": ("Markierung entfernt.", "Drapeau retiré.", "Bandera retirada.", "Bandeira removida.", "Флаг убран."),
    "Left click: scan. Right click: flag. Arrow keys: move. Enter/Space: scan. F: flag.": (
        "Linksklick: scannen. Rechtsklick: markieren. Pfeiltasten: bewegen. Enter/Leertaste: scannen. F: markieren.",
        "Clic gauche : scanner. Clic droit : drapeau. Flèches : déplacer. Entrée/Espace : scanner. F : drapeau.",
        "Clic izquierdo: explorar. Clic derecho: marcar. Flechas: mover. Intro/Espacio: explorar. F: marcar.",
        "Clique esquerdo: explorar. Clique direito: marcar. Setas: mover. Enter/Espaço: explorar. F: marcar.",
        "Левый щелчок: открыть. Правый щелчок: флаг. Стрелки: движение. Enter/Пробел: открыть. F: флаг."),
    "Scan the selected cell (Enter/Space). Flag it with F or right click.": (
        "Ausgewähltes Feld scannen (Enter/Leertaste). F oder Rechtsklick zum Markieren.",
        "Scanner la case sélectionnée (Entrée/Espace). Marquer avec F ou un clic droit.",
        "Explorar la celda seleccionada (Intro/Espacio). Marcar con F o clic derecho.",
        "Explorar a célula selecionada (Enter/Espaço). Marcar com F ou clique direito.",
        "Открыть выбранную клетку (Enter/Пробел). Поставить флаг: F или правый щелчок."),
    "Restart with R. Change board size with Q/E or click the difficulty name.": (
        "R startet neu. Q/E oder Klick auf die Schwierigkeit ändert die Feldgröße.",
        "R recommence. Q/E ou un clic sur la difficulté change la grille.",
        "R reinicia. Q/E o un clic en la dificultad cambia el tablero.",
        "R reinicia. Q/E ou um clique na dificuldade altera o tabuleiro.",
        "R: начать сначала. Q/E или щелчок по сложности меняет размер поля."),
    "Cycle Beginner, Intermediate and Expert boards (Q/E).": (
        "Zwischen Anfänger, Fortgeschritten und Experte wechseln (Q/E).",
        "Changer entre Débutant, Intermédiaire et Expert (Q/E).",
        "Alternar entre Principiante, Intermedio y Experto (Q/E).",
        "Alternar entre Iniciante, Intermédio e Especialista (Q/E).",
        "Переключить поля Новичок, Средний и Эксперт (Q/E)."),
}


def install_translations():
    for index, locale in enumerate(LOCALES[1:]):
        i18n.add_translations(locale, {source: translations[index] for source, translations in STRINGS.items()}, context="Minesweeper")
