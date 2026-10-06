"""Plugin-owned labels and tooltips in the six supported host languages."""

from emtk import i18n

LOCALES = ("en", "de", "fr", "es", "pt", "ru")
STRINGS = {
    "Number Quest": (
        "Zahlenreise",
        "Quête du nombre",
        "Aventura numérica",
        "Aventura numérica",
        "Поиск числа",
    ),
    "Sound": ("Ton", "Son", "Sonido", "Som", "Звук"),
    "LIFETIME ESTIMATION": (
        "LEBENSDAUER SCHÄTZEN",
        "ESTIMATION DE DURÉE",
        "ESTIMACIÓN DE VIDA",
        "ESTIMATIVA DE VIDA",
        "ОЦЕНКА ВРЕМЕНИ ЖИЗНИ",
    ),
    "Turns left: {turns}    Score: {score}": (
        "Versuche: {turns}    Punkte: {score}",
        "Essais : {turns}    Score : {score}",
        "Intentos: {turns}    Puntos: {score}",
        "Tentativas: {turns}    Pontos: {score}",
        "Ходов: {turns}    Очки: {score}",
    ),
    "Dial an estimate, then confirm.": (
        "Schätzwert wählen, dann bestätigen.",
        "Choisissez une valeur, puis confirmez.",
        "Elige una estimación y confirma.",
        "Escolha uma estimativa e confirme.",
        "Выберите оценку и подтвердите.",
    ),
    "Longer lifetime.": (
        "Längere Lebensdauer.",
        "Durée de vie plus longue.",
        "Vida más larga.",
        "Vida mais longa.",
        "Большее время жизни.",
    ),
    "Shorter lifetime.": (
        "Kürzere Lebensdauer.",
        "Durée de vie plus courte.",
        "Vida más corta.",
        "Vida mais curta.",
        "Меньшее время жизни.",
    ),
    "You found it! The number was {target}.": (
        "Gefunden! Die Zahl war {target}.",
        "Trouvé ! Le nombre était {target}.",
        "¡Acertaste! El número era {target}.",
        "Acertou! O número era {target}.",
        "Найдено! Число: {target}.",
    ),
    "Out of turns — the number was {target}.": (
        "Keine Versuche mehr — die Zahl war {target}.",
        "Plus d'essais — le nombre était {target}.",
        "Sin intentos — el número era {target}.",
        "Sem tentativas — o número era {target}.",
        "Ходы закончились — число: {target}.",
    ),
    "Left/Right  dial      L/R  coarse": (
        "Links/Rechts wählen   Q/E grob",
        "Gauche/Droite choisir   Q/E rapide",
        "Izq./Der. elegir   Q/E rápido",
        "Esq./Dir. escolher   Q/E rápido",
        "Влево/Вправо выбор   Q/E крупно",
    ),
    "Confirm  submit      Cancel  new round": (
        "Enter bestätigen   R neue Runde",
        "Entrée confirmer   R rejouer",
        "Intro confirmar   R nueva ronda",
        "Enter confirmar   R nova rodada",
        "Enter подтвердить   R новый раунд",
    ),
    "Music and sound effects (off by default).": (
        "Musik und Effekte (standardmäßig aus).",
        "Musique et effets (désactivés au départ).",
        "Música y efectos (desactivados por defecto).",
        "Música e efeitos (desativados por padrão).",
        "Музыка и эффекты (по умолчанию выключены).",
    ),
    "Hold Left/Right or A/D for fine steps; Q/E for steps of ten.": (
        "Links/Rechts oder A/D halten; Q/E für Zehnerschritte.",
        "Maintenez Gauche/Droite ou A/D ; Q/E par dix.",
        "Mantén Izq./Der. o A/D; Q/E en pasos de diez.",
        "Segure Esq./Dir. ou A/D; Q/E em passos de dez.",
        "Удерживайте Влево/Вправо или A/D; Q/E с шагом десять.",
    ),
    "Submit with Enter/Space. Start a new round with R.": (
        "Mit Enter/Leertaste bestätigen. Neue Runde mit R.",
        "Confirmez avec Entrée/Espace. Nouvelle partie avec R.",
        "Confirma con Intro/Espacio. Nueva ronda con R.",
        "Confirme com Enter/Espaço. Nova rodada com R.",
        "Enter/Пробел: подтвердить. R: новый раунд.",
    ),
    "Click the plot to dial a lifetime between 0.1 and 10.0 ns.": (
        "Im Diagramm eine Lebensdauer von 0,1 bis 10,0 ns wählen.",
        "Cliquez pour choisir une durée de 0,1 à 10,0 ns.",
        "Haz clic para elegir una vida de 0,1 a 10,0 ns.",
        "Clique para escolher uma vida de 0,1 a 10,0 ns.",
        "Щёлкните график для выбора времени от 0,1 до 10,0 нс.",
    ),
}


def install_translations():
    for index, locale in enumerate(LOCALES[1:]):
        i18n.add_translations(
            locale,
            {source: values[index] for source, values in STRINGS.items()},
            context="NumberQuest",
        )
