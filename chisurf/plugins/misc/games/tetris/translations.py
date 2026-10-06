"""Tetris labels and control tooltips for the six supported locales."""

from emtk import i18n

LOCALES = ("en", "de", "fr", "es", "pt", "ru")
STRINGS = {
    "Tetris": ("Tetris", "Tetris", "Tetris", "Tetris", "Тетрис"),
    "Sound": ("Ton", "Son", "Sonido", "Som", "Звук"),
    "COUNTS": ("ZÄHLER", "COMPTES", "CUENTAS", "CONTAGENS", "СЧЁТ"),
    "LINES": ("LINIEN", "LIGNES", "LÍNEAS", "LINHAS", "ЛИНИИ"),
    "GAIN": ("STUFE", "NIVEAU", "NIVEL", "NÍVEL", "УРОВЕНЬ"),
    "HELD": ("PAUSE", "PAUSE", "PAUSA", "PAUSA", "ПАУЗА"),
    "Channel full": ("Kanal voll", "Canal plein", "Canal lleno", "Canal cheio", "Канал заполнен"),
    "Confirm to reset": (
        "Bestätigen: Neustart",
        "Confirmer pour rejouer",
        "Confirmar: reiniciar",
        "Confirmar: reiniciar",
        "Подтвердить: сначала",
    ),
    "Move  Confirm rotate  Down soft  R drop": (
        "Bewegen  Drehen  Ab sanft  R fallen",
        "Bouger  Tourner  Bas doux  R chute",
        "Mover  Girar  Abajo suave  R caer",
        "Mover  Girar  Baixo suave  R cair",
        "Движение  Поворот  Вниз плавно  R сброс",
    ),
    "Menu hold  Cancel reset": (
        "Menü Pause  Abbruch Neustart",
        "Menu pause  Annuler rejouer",
        "Menú pausa  Cancelar reiniciar",
        "Menu pausa  Cancelar reiniciar",
        "Меню пауза  Отмена сначала",
    ),
    "Music and sound effects (off by default). EMTK audio is unavailable.": (
        "Musik und Effekte (standardmäßig aus). EMTK unterstützt kein Audio.",
        "Musique et effets (désactivés par défaut). EMTK ne prend pas en charge l'audio.",
        "Música y efectos (desactivados inicialmente). EMTK no admite audio.",
        "Música e efeitos (desativados inicialmente). EMTK não suporta áudio.",
        "Музыка и эффекты (по умолчанию выключены). В EMTK нет аудио.",
    ),
    "Restart after game over (Up/W or R).": (
        "Nach Spielende neu starten (Auf/W oder R).",
        "Rejouer après la fin (Haut/W ou R).",
        "Reiniciar al terminar (Arriba/W o R).",
        "Reiniciar ao terminar (Cima/W ou R).",
        "Начать после конца игры (Вверх/W или R).",
    ),
    "Left/Right or A/D: move. Up/W: rotate. Down/S: soft drop. Space: hard drop.": (
        "Links/Rechts oder A/D: bewegen. Auf/W: drehen. Ab/S: sanft fallen. Leertaste: sofort fallen.",
        "Gauche/Droite ou A/D : bouger. Haut/W : tourner. Bas/S : descente douce. Espace : chute immédiate.",
        "Izquierda/Derecha o A/D: mover. Arriba/W: girar. Abajo/S: caída suave. Espacio: caída rápida.",
        "Esquerda/Direita ou A/D: mover. Cima/W: girar. Baixo/S: queda suave. Espaço: queda rápida.",
        "Влево/Вправо или A/D: движение. Вверх/W: поворот. Вниз/S: плавный спуск. Пробел: быстрый сброс.",
    ),
    "P: pause/resume. R: restart.": (
        "P: Pause/fortsetzen. R: Neustart.",
        "P : pause/reprise. R : rejouer.",
        "P: pausa/continuar. R: reiniciar.",
        "P: pausa/continuar. R: reiniciar.",
        "P: пауза/продолжение. R: сначала.",
    ),
}


def install_translations():
    for index, locale in enumerate(LOCALES[1:]):
        i18n.add_translations(
            locale, {source: values[index] for source, values in STRINGS.items()}, context="Tetris"
        )
