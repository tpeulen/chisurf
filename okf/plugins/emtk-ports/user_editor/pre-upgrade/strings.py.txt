from emtk import i18n

_CATALOGS = {
    "de": {"User Editor":"Benutzerverwaltung", "Reload":"Neu laden", "New":"Neu", "Save":"Speichern", "Revert":"Zurücksetzen", "Delete":"Löschen", "No user selected":"Kein Benutzer ausgewählt", "Users":"Benutzer", "Details":"Details", "Password":"Passwort", "Confirm password":"Passwort bestätigen", "Stage password":"Passwort vormerken", "Password staged for Save.":"Passwort zum Speichern vorgemerkt."},
    "fr": {"User Editor":"Éditeur des utilisateurs", "Reload":"Recharger", "New":"Nouveau", "Save":"Enregistrer", "Revert":"Annuler", "Delete":"Supprimer", "No user selected":"Aucun utilisateur sélectionné", "Users":"Utilisateurs", "Details":"Détails", "Password":"Mot de passe", "Confirm password":"Confirmer le mot de passe", "Stage password":"Préparer le mot de passe", "Password staged for Save.":"Mot de passe préparé."},
    "es": {"User Editor":"Editor de usuarios", "Reload":"Recargar", "New":"Nuevo", "Save":"Guardar", "Revert":"Revertir", "Delete":"Eliminar", "No user selected":"Ningún usuario seleccionado", "Users":"Usuarios", "Details":"Detalles", "Password":"Contraseña", "Confirm password":"Confirmar contraseña", "Stage password":"Preparar contraseña", "Password staged for Save.":"Contraseña preparada."},
    "pt": {"User Editor":"Editor de utilizadores", "Reload":"Recarregar", "New":"Novo", "Save":"Guardar", "Revert":"Reverter", "Delete":"Eliminar", "No user selected":"Nenhum utilizador selecionado", "Users":"Utilizadores", "Details":"Detalhes", "Password":"Palavra-passe", "Confirm password":"Confirmar palavra-passe", "Stage password":"Preparar palavra-passe", "Password staged for Save.":"Palavra-passe preparada."},
    "ru": {"User Editor":"Редактор пользователей", "Reload":"Обновить", "New":"Новый", "Save":"Сохранить", "Revert":"Отменить", "Delete":"Удалить", "No user selected":"Пользователь не выбран", "Users":"Пользователи", "Details":"Детали", "Password":"Пароль", "Confirm password":"Подтвердите пароль", "Stage password":"Подготовить пароль", "Password staged for Save.":"Пароль подготовлен."},
}

def install_translations():
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="User Editor")

def tr(text):
    return i18n.tr(text, context="User Editor")
