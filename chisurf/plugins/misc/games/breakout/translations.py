"""Breakout labels and control tooltips for the six supported locales."""
from emtk import i18n

LOCALES = ("en", "de", "fr", "es", "pt", "ru")
STRINGS = {
    "Breakout": ("Breakout", "Breakout", "Breakout", "Breakout", "Арканоид"),
    "Sound": ("Ton", "Son", "Sonido", "Som", "Звук"),
    "Counts: {score}": ("Zähler: {score}", "Comptes : {score}", "Cuentas: {score}", "Contagens: {score}", "Счёт: {score}"),
    "Scan: {level}": ("Scan: {level}", "Scan : {level}", "Barrido: {level}", "Varredura: {level}", "Скан: {level}"),
    "Pulses:": ("Pulse:", "Impulsions :", "Pulsos:", "Pulsos:", "Импульсы:"),
    "Confirm to fire": ("Enter zum Start", "Entrée pour tirer", "Intro para lanzar", "Enter para lançar", "Enter: запустить"),
    "HELD": ("PAUSE", "PAUSE", "PAUSA", "PAUSA", "ПАУЗА"),
    "Sample bleached": ("Probe gebleicht", "Échantillon blanchi", "Muestra blanqueada", "Amostra branqueada", "Образец выгорел"),
    "Confirm for a fresh sample": ("Enter für neue Probe", "Entrée : nouvel échantillon", "Intro: nueva muestra", "Enter: nova amostra", "Enter: новый образец"),
    "Left/Right detector": ("Pfeile Detektor", "Flèches détecteur", "Flechas detector", "Setas detector", "Стрелки: детектор"),
    "Confirm fire": ("Enter Start", "Entrée tirer", "Intro lanzar", "Enter lançar", "Enter пуск"),
    "Menu hold": ("P Pause", "P pause", "P pausa", "P pausa", "P пауза"),
    "Cancel reset": ("R Neustart", "R rejouer", "R reiniciar", "R reiniciar", "R сначала"),
    "R sound": ("M Ton", "M son", "M sonido", "M som", "M звук"),
    "   [muted]": ("   [stumm]", "   [muet]", "   [silenciado]", "   [silenciado]", "   [без звука]"),
    "Sound state only: EMTK audio is unavailable. M toggles mute.": (
        "Nur Tonstatus: EMTK unterstützt kein Audio. M schaltet stumm.", "État sonore uniquement : EMTK ne prend pas en charge l'audio. M coupe le son.", "Solo estado de sonido: EMTK no admite audio. M silencia.", "Apenas estado de som: EMTK não suporta áudio. M silencia.", "Только состояние звука: в EMTK нет аудио. M отключает звук."),
    "Drag the detector or hold Left/Right or A/D.": (
        "Detektor ziehen oder Links/Rechts bzw. A/D halten.", "Faites glisser le détecteur ou maintenez Gauche/Droite ou A/D.", "Arrastra el detector o mantén Izquierda/Derecha o A/D.", "Arraste o detector ou segure Esquerda/Direita ou A/D.", "Перетаскивайте детектор или удерживайте Влево/Вправо либо A/D."),
    "Launch the photon (Enter/Space).": (
        "Photon starten (Enter/Leertaste).", "Lancer le photon (Entrée/Espace).", "Lanza el fotón (Intro/Espacio).", "Lance o fóton (Enter/Espaço).", "Запустить фотон (Enter/Пробел)."),
    "Pause or resume (P).": (
        "Pause oder fortsetzen (P).", "Pause ou reprise (P).", "Pausar o continuar (P).", "Pausar ou continuar (P).", "Пауза или продолжение (P)."),
    "Start a fresh sample (Enter/Space or R).": (
        "Neue Probe starten (Enter/Leertaste oder R).", "Nouvel échantillon (Entrée/Espace ou R).", "Nueva muestra (Intro/Espacio o R).", "Nova amostra (Enter/Espaço ou R).", "Новый образец (Enter/Пробел или R)."),
    "Toggle mute state (M); EMTK audio is unavailable.": (
        "Stummstatus ändern (M); EMTK unterstützt kein Audio.", "Basculer l'état muet (M) ; EMTK ne prend pas en charge l'audio.", "Alternar silencio (M); EMTK no admite audio.", "Alternar silêncio (M); EMTK não suporta áudio.", "Переключить звук (M); в EMTK нет аудио."),
}


def install_translations():
    for index, locale in enumerate(LOCALES[1:]):
        i18n.add_translations(locale, {source: values[index] for source, values in STRINGS.items()}, context="Breakout")
