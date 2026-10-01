"""Navigation labels for the six supported games-hub locales."""

from emtk import i18n

LOCALES = ("en", "de", "fr", "es", "pt", "ru")
STRINGS = {
    "Games": ("Spiele", "Jeux", "Juegos", "Jogos", "Игры"),
    "Number Quest": ("Zahlenquest", "Quête numérique", "Misión numérica", "Missão numérica", "Числовой квест"),
    "Minesweeper": ("Minesweeper", "Démineur", "Buscaminas", "Campo minado", "Сапёр"),
    "Tetris": ("Tetris", "Tetris", "Tetris", "Tetris", "Тетрис"),
    "Pong": ("Pong", "Pong", "Pong", "Pong", "Понг"),
    "Breakout": ("Breakout", "Breakout", "Breakout", "Breakout", "Арканоид"),
    "Available games": ("Verfügbare Spiele", "Jeux disponibles", "Juegos disponibles", "Jogos disponíveis", "Доступные игры"),
    "Coming soon": ("Demnächst", "Bientôt disponible", "Próximamente", "Em breve", "Скоро"),
    "Native version pending": ("Native Version ausstehend", "Version native en attente", "Versión nativa pendiente", "Versão nativa pendente", "Нативная версия в разработке"),
    "This game is available in the Qt hub. Its native version is pending.": (
        "Dieses Spiel ist im Qt-Hub verfügbar. Die native Version steht noch aus.",
        "Ce jeu est disponible dans le hub Qt. Sa version native est en attente.",
        "Este juego está disponible en el hub Qt. Su versión nativa está pendiente.",
        "Este jogo está disponível no hub Qt. Sua versão nativa está pendente.",
        "Эта игра доступна в центре Qt. Нативная версия находится в разработке."),
    "Game unavailable": ("Spiel nicht verfügbar", "Jeu indisponible", "Juego no disponible", "Jogo indisponível", "Игра недоступна"),
    "Select a game to play": ("Spiel zum Spielen auswählen", "Choisissez un jeu", "Selecciona un juego", "Selecione um jogo", "Выберите игру"),
    "Guess the hidden number in seven tries.": (
        "Errate die verborgene Zahl in sieben Versuchen.", "Devinez le nombre caché en sept essais.",
        "Adivina el número oculto en siete intentos.", "Adivinhe o número oculto em sete tentativas.",
        "Угадайте скрытое число за семь попыток."),
    "Clear a minefield without triggering a mine; board size is configurable.": (
        "Räume ein Minenfeld, ohne eine Mine auszulösen; die Feldgröße ist einstellbar.",
        "Déminage sans déclencher de mine ; la taille de la grille est réglable.",
        "Despeja un campo de minas sin activar ninguna; el tamaño es configurable.",
        "Limpe um campo minado sem acionar minas; o tamanho é configurável.",
        "Очистите минное поле; размер поля настраивается."),
    "Classic falling-block puzzle with line clearing and score tracking.": (
        "Klassisches Blockpuzzle mit gelöschten Reihen und Punktestand.",
        "Jeu de blocs classique avec lignes effacées et score.",
        "Clásico juego de bloques con líneas eliminadas y puntuación.",
        "Jogo clássico de blocos com linhas removidas e pontuação.",
        "Классическая игра с падающими блоками и подсчётом очков."),
    "Classic Pong against a CPU opponent, with sound and particle effects.": (
        "Klassisches Pong gegen den Computer, mit Ton und Partikeleffekten.",
        "Pong classique contre l'ordinateur, avec son et particules.",
        "Pong clásico contra el ordenador, con sonido y partículas.",
        "Pong clássico contra o computador, com som e partículas.",
        "Классический понг против компьютера, со звуком и эффектами."),
    "Classic Breakout with progressive difficulty and multiple brick types.": (
        "Klassisches Breakout mit steigendem Schwierigkeitsgrad und verschiedenen Steinen.",
        "Breakout classique avec difficulté progressive et plusieurs types de briques.",
        "Breakout clásico con dificultad progresiva y varios tipos de ladrillos.",
        "Breakout clássico com dificuldade progressiva e vários tipos de tijolos.",
        "Классический арканоид с растущей сложностью и разными кирпичами."),
}


def install_translations():
    for index, locale in enumerate(LOCALES[1:]):
        i18n.add_translations(locale, {source: values[index] for source, values in STRINGS.items()}, context="Games")
