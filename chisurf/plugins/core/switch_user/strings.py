from emtk import i18n

_CATALOGS = {
    "de": {
        "Switch User": "Benutzer wechseln",
        "Sign in to the MMFDB workspace": "Am MMFDB-Arbeitsbereich anmelden",
        "Server": "Server",
        "Port": "Port",
        "User": "Benutzer",
        "Password": "Passwort",
        "Save selected user": "Benutzer merken",
        "Log in automatically": "Automatisch anmelden",
        "Login": "Anmelden",
        "Cancel": "Abbrechen",
        "Login succeeded.": "Anmeldung erfolgreich.",
        "Login failed.": "Anmeldung fehlgeschlagen.",
    },
    "fr": {
        "Switch User": "Changer d’utilisateur",
        "Sign in to the MMFDB workspace": "Se connecter à l’espace MMFDB",
        "Server": "Serveur",
        "Port": "Port",
        "User": "Utilisateur",
        "Password": "Mot de passe",
        "Save selected user": "Mémoriser l’utilisateur",
        "Log in automatically": "Connexion automatique",
        "Login": "Connexion",
        "Cancel": "Annuler",
        "Login succeeded.": "Connexion réussie.",
        "Login failed.": "Échec de la connexion.",
    },
    "es": {
        "Switch User": "Cambiar usuario",
        "Sign in to the MMFDB workspace": "Iniciar sesión en MMFDB",
        "Server": "Servidor",
        "Port": "Puerto",
        "User": "Usuario",
        "Password": "Contraseña",
        "Save selected user": "Guardar usuario",
        "Log in automatically": "Inicio automático",
        "Login": "Iniciar sesión",
        "Cancel": "Cancelar",
        "Login succeeded.": "Inicio de sesión correcto.",
        "Login failed.": "Error de inicio de sesión.",
    },
    "pt": {
        "Switch User": "Mudar utilizador",
        "Sign in to the MMFDB workspace": "Entrar no espaço MMFDB",
        "Server": "Servidor",
        "Porta": "Porta",
        "User": "Utilizador",
        "Password": "Palavra-passe",
        "Save selected user": "Guardar utilizador",
        "Log in automatically": "Início automático",
        "Login": "Entrar",
        "Cancel": "Cancelar",
        "Login succeeded.": "Autenticação concluída.",
        "Login failed.": "Falha na autenticação.",
    },
    "ru": {
        "Switch User": "Сменить пользователя",
        "Sign in to the MMFDB workspace": "Войти в рабочую область MMFDB",
        "Server": "Сервер",
        "Port": "Порт",
        "User": "Пользователь",
        "Password": "Пароль",
        "Save selected user": "Запомнить пользователя",
        "Log in automatically": "Входить автоматически",
        "Login": "Войти",
        "Cancel": "Отмена",
        "Login succeeded.": "Вход выполнен.",
        "Login failed.": "Ошибка входа.",
    },
}


def install_translations():
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="Switch User")


def tr(text):
    return i18n.tr(text, context="Switch User")
