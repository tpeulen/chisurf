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
    "Confirm to reset": ("Bestätigen: Neustart", "Confirmer pour rejouer", "Confirmar: reiniciar", "Confirmar: reiniciar", "Подтвердить: сначала"),
    "Move  Confirm rotate  Down soft  R drop": (
        "Bewegen  Drehen  Ab sanft  R fallen", "Bouger  Tourner  Bas doux  R chute", "Mover  Girar  Abajo suave  R caer", "Mover  Girar  Baixo suave  R cair", "Движение  Поворот  Вниз плавно  R сброс"),
    "Menu hold  Cancel reset": ("Menü Pause  Abbruch Neustart", "Menu pause  Annuler rejouer", "Menú pausa  Cancelar reiniciar", "Menu pausa  Cancelar reiniciar", "Меню пауза  Отмена сначала"),
    "Music and sound effects (off by default). EMTK audio is unavailable.": (
        "Musik und Effekte (standardmäßig aus). EMTK unterstützt kein Audio.", "Musique et effets (désactivés par défaut). EMTK ne prend pas en charge l'audio.", "Música y efectos (desactivados inicialmente). EMTK no admite audio.", "Música e efeitos (desativados inicialmente). EMTK não suporta áudio.", "Музыка и эффекты (по умолчанию выключены). В EMTK нет аудио."),
    "Restart after game over (Up or R).": (
        "Nach Spielende neu starten (Auf oder R).", "Rejouer après la fin (Haut ou R).", "Reiniciar al terminar (Arriba o R).", "Reiniciar ao terminar (Cima ou R).", "Начать заново после конца игры (Вверх или R)."),
    "Left/Right: move. Up: rotate. Down: soft drop. Space: hard drop.": (
        "Links/Rechts: bewegen. Auf: drehen. Ab: sanft fallen. Leertaste: sofort fallen.", "Gauche/Droite : bouger. Haut : tourner. Bas : descente douce. Espace : chute immédiate.", "Izquierda/Derecha: mover. Arriba: girar. Abajo: caída suave. Espacio: caída rápida.", "Esquerda/Direita: mover. Cima: girar. Baixo: queda suave. Espaço: queda rápida.", "Влево/Вправо: движение. Вверх: поворот. Вниз: плавный спуск. Пробел: быстрый сброс."),
    "P: pause/resume. R: restart.": (
        "P: Pause/fortsetzen. R: Neustart.", "P : pause/reprise. R : rejouer.", "P: pausa/continuar. R: reiniciar.", "P: pausa/continuar. R: reiniciar.", "P: пауза/продолжение. R: сначала."),
}


def install_translations():
    for index, locale in enumerate(LOCALES[1:]):
        i18n.add_translations(locale, {source: values[index] for source, values in STRINGS.items()}, context="Tetris")
