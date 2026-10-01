from emtk import i18n

_CATALOGS = {"de": {"Model Manager":"Modellverwaltung", "Models":"Modelle", "Details":"Details", "Show disabled models":"Deaktivierte Modelle anzeigen", "Reload":"Neu laden", "Save":"Speichern", "Revert":"Zurücksetzen", "Disabled":"Deaktiviert", "Drop stale entries":"Veraltete Einträge entfernen", "No model selected":"Kein Modell ausgewählt"}, "fr": {"Model Manager":"Gestionnaire de modèles", "Models":"Modèles", "Details":"Détails", "Show disabled models":"Afficher les modèles désactivés", "Reload":"Recharger", "Save":"Enregistrer", "Revert":"Annuler", "Disabled":"Désactivé", "Drop stale entries":"Supprimer les entrées obsolètes", "No model selected":"Aucun modèle sélectionné"}, "es": {"Model Manager":"Gestor de modelos", "Models":"Modelos", "Details":"Detalles", "Show disabled models":"Mostrar modelos desactivados", "Reload":"Recargar", "Save":"Guardar", "Revert":"Revertir", "Disabled":"Desactivado", "Drop stale entries":"Eliminar entradas obsoletas", "No model selected":"Ningún modelo seleccionado"}, "pt": {"Model Manager":"Gestor de modelos", "Models":"Modelos", "Details":"Detalhes", "Show disabled models":"Mostrar modelos desativados", "Reload":"Recarregar", "Save":"Guardar", "Revert":"Reverter", "Disabled":"Desativado", "Drop stale entries":"Remover entradas obsoletas", "No model selected":"Nenhum modelo selecionado"}, "ru": {"Model Manager":"Менеджер моделей", "Models":"Модели", "Details":"Детали", "Show disabled models":"Показывать отключённые модели", "Reload":"Обновить", "Save":"Сохранить", "Revert":"Отменить", "Disabled":"Отключено", "Drop stale entries":"Удалить устаревшие записи", "No model selected":"Модель не выбрана"}}

def install_translations():
    for locale, values in _CATALOGS.items():
        i18n.add_translations(locale, values, context="Model Manager")

def tr(text):
    return i18n.tr(text, context="Model Manager")
