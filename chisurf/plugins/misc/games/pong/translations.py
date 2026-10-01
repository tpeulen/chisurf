"""Pong-owned catalogs for all six ChiSurf languages."""
from emtk import i18n

LOCALES = ("en", "de", "fr", "es", "pt", "ru")
STRINGS = {
    "Pong": ("Pong", "Pong", "Pong", "Pong", "Понг"),
    "Sound": ("Ton", "Son", "Sonido", "Som", "Звук"),
    "Donor": ("Donor", "Donneur", "Donante", "Doador", "Донор"),
    "Acceptor": ("Akzeptor", "Accepteur", "Aceptor", "Aceitador", "Акцептор"),
    "Optic 2": ("Optik 2", "Optique 2", "Óptica 2", "Ótica 2", "Оптика 2"),
    "Donor: {score}": ("Donor: {score}", "Donneur : {score}", "Donante: {score}", "Doador: {score}", "Донор: {score}"),
    "Acceptor: {score}": ("Akzeptor: {score}", "Accepteur : {score}", "Aceptor: {score}", "Aceitador: {score}", "Акцептор: {score}"),
    "Optic 2: {score}": ("Optik 2: {score}", "Optique 2 : {score}", "Óptica 2: {score}", "Ótica 2: {score}", "Оптика 2: {score}"),
    "Transfers: {count}": ("Transfers: {count}", "Transferts : {count}", "Transferencias: {count}", "Transferências: {count}", "Передачи: {count}"),
    "HELD": ("PAUSE", "PAUSE", "PAUSA", "PAUSA", "ПАУЗА"),
    "{winner} wins": ("{winner} gewinnt", "{winner} gagne", "{winner} gana", "{winner} vence", "{winner} побеждает"),
    "Confirm to run again": ("Enter zum Neustart", "Entrée pour rejouer", "Intro para repetir", "Enter para repetir", "Enter: играть снова"),
    "[muted]": ("[stumm]", "[muet]", "[silenciado]", "[silenciado]", "[без звука]"),
    "Up/Down optic": ("Pfeile Optik", "Flèches optique", "Flechas óptica", "Setas ótica", "Стрелки: оптика"),
    "Menu hold": ("P Pause", "P pause", "P pausa", "P pausa", "P пауза"),
    "Cancel reset": ("R Neustart", "R rejouer", "R reiniciar", "R reiniciar", "R сначала"),
    "L mode": ("M Modus", "M mode", "M modo", "M modo", "M режим"),
    "R sound": ("N Ton", "N son", "N sonido", "N som", "N звук"),
    "Music and sound effects (off by default). N toggles mute.": (
        "Musik und Effekte (standardmäßig aus). N schaltet stumm.", "Musique et effets (désactivés au départ). N coupe le son.", "Música y efectos (desactivados por defecto). N silencia.", "Música e efeitos (desativados por padrão). N silencia.", "Музыка и эффекты (по умолчанию выключены). N отключает звук."),
    "Drag the left paddle or hold Up/Down. In two-player mode hold W/S for the right paddle.": (
        "Linken Schläger ziehen oder Hoch/Runter halten. Zu zweit steuert W/S den rechten Schläger.", "Faites glisser la raquette gauche ou maintenez Haut/Bas. À deux, W/S contrôle la raquette droite.", "Arrastra la pala izquierda o mantén Arriba/Abajo. Con dos jugadores W/S mueve la pala derecha.", "Arraste a raquete esquerda ou segure Cima/Baixo. Com dois jogadores W/S move a raquete direita.", "Перетаскивайте левую ракетку или удерживайте Вверх/Вниз. В игре вдвоём W/S управляет правой."),
    "Pause or resume (P).": ("Pause oder fortsetzen (P).", "Pause ou reprise (P).", "Pausar o continuar (P).", "Pausar ou continuar (P).", "Пауза или продолжение (P)."),
    "Start a new round (Enter/Space or R).": ("Neue Runde starten (Enter/Leertaste oder R).", "Nouvelle partie (Entrée/Espace ou R).", "Nueva ronda (Intro/Espacio o R).", "Nova rodada (Enter/Espaço ou R).", "Новый раунд (Enter/Пробел или R)."),
    "Switch CPU and two-player mode (M).": ("Computer- und Zweispielermodus wechseln (M).", "Basculer entre ordinateur et deux joueurs (M).", "Cambiar entre CPU y dos jugadores (M).", "Alternar entre CPU e dois jogadores (M).", "Переключить компьютер и двух игроков (M)."),
    "Mute or unmute effects (N).": ("Effekte stummschalten oder aktivieren (N).", "Couper ou rétablir les effets (N).", "Silenciar o activar efectos (N).", "Silenciar ou ativar efeitos (N).", "Отключить или включить эффекты (N)."),
}


def install_translations():
    for index, locale in enumerate(LOCALES[1:]):
        i18n.add_translations(locale, {source: values[index] for source, values in STRINGS.items()}, context="Pong")
