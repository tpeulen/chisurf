from __future__ import annotations

from emtk import i18n

_CATALOGS = {
    "de": {
        "Number Quest": "Zahlenquest",
        "LIFETIME ESTIMATION": "LEBENSDAUER-SCHÄTZUNG",
        "Turns left": "Verbleibende Züge",
        "Score": "Punktzahl",
        "Estimate": "Schätzung",
        "Confirm": "Bestätigen",
        "New round": "Neue Runde",
        "Dial an estimate, then confirm.": "Schätzung einstellen und bestätigen.",
    },
    "fr": {
        "Number Quest": "Quête numérique",
        "LIFETIME ESTIMATION": "ESTIMATION DE DURÉE",
        "Turns left": "Tours restants",
        "Score": "Score",
        "Estimate": "Estimation",
        "Confirm": "Confirmer",
        "New round": "Nouvelle partie",
        "Dial an estimate, then confirm.": "Réglez une estimation puis confirmez.",
    },
    "es": {
        "Number Quest": "Misión numérica",
        "LIFETIME ESTIMATION": "ESTIMACIÓN DE VIDA",
        "Turns left": "Turnos restantes",
        "Score": "Puntuación",
        "Estimate": "Estimación",
        "Confirm": "Confirmar",
        "New round": "Nueva partida",
        "Dial an estimate, then confirm.": "Ajusta una estimación y confirma.",
    },
    "pt": {
        "Number Quest": "Missão numérica",
        "LIFETIME ESTIMATION": "ESTIMATIVA DE VIDA",
        "Turns left": "Jogadas restantes",
        "Score": "Pontuação",
        "Estimate": "Estimativa",
        "Confirm": "Confirmar",
        "New round": "Nova rodada",
        "Dial an estimate, then confirm.": "Ajuste uma estimativa e confirme.",
    },
    "ru": {
        "Number Quest": "Числовой квест",
        "LIFETIME ESTIMATION": "ОЦЕНКА ВРЕМЕНИ ЖИЗНИ",
        "Turns left": "Осталось ходов",
        "Score": "Счёт",
        "Estimate": "Оценка",
        "Confirm": "Подтвердить",
        "New round": "Новый раунд",
        "Dial an estimate, then confirm.": "Настройте оценку и подтвердите.",
    },
}


def install_translations() -> None:
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="Number Quest")
