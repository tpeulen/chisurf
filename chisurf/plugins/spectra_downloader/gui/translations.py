"""Plugin-local translations for all ChiSurf locales, including control help."""

from emtk import i18n

LOCALES = ("en", "de", "fr", "es", "pt", "ru")
# English identities remain stable across locale switches and persisted state.
_ROWS = [
    ("Guide", "Anleitung", "Guide", "Guía", "Guia", "Руководство"),
    ("Spectra", "Spektren", "Spectres", "Espectros", "Espectros", "Спектры"),
    ("Overview", "Übersicht", "Vue d’ensemble", "Resumen", "Visão geral", "Обзор"),
    ("Browse", "Durchsuchen", "Parcourir", "Explorar", "Explorar", "Просмотр"),
    ("Download", "Herunterladen", "Télécharger", "Descargar", "Descarregar", "Загрузка"),
    (
        "Add to MMFDB",
        "Zu MMFDB hinzufügen",
        "Ajouter à MMFDB",
        "Añadir a MMFDB",
        "Adicionar a MMFDB",
        "Добавить в MMFDB",
    ),
    (
        "Staging database overview",
        "Übersicht der Zwischendatenbank",
        "Vue de la base intermédiaire",
        "Resumen de la base temporal",
        "Visão da base temporária",
        "Обзор промежуточной базы",
    ),
    (
        "Staging DB",
        "Zwischendatenbank",
        "Base intermédiaire",
        "Base temporal",
        "Base temporária",
        "Промежуточная база",
    ),
    (
        "Total components",
        "Komponenten gesamt",
        "Total des composants",
        "Total de componentes",
        "Total de componentes",
        "Всего компонентов",
    ),
    (
        "With spectra",
        "Mit Spektren",
        "Avec spectres",
        "Con espectros",
        "Com espectros",
        "Со спектрами",
    ),
    ("Fluorophores", "Fluorophore", "Fluorophores", "Fluoróforos", "Fluoróforos", "Флуорофоры"),
    ("Filters", "Filter", "Filtres", "Filtros", "Filtros", "Фильтры"),
    ("Dichroics", "Dichroiten", "Dichroïques", "Dicroicos", "Dicróicos", "Дихроики"),
    ("Detectors", "Detektoren", "Détecteurs", "Detectores", "Detetores", "Детекторы"),
    (
        "Light sources",
        "Lichtquellen",
        "Sources lumineuses",
        "Fuentes de luz",
        "Fontes de luz",
        "Источники света",
    ),
    ("Refresh", "Aktualisieren", "Actualiser", "Actualizar", "Atualizar", "Обновить"),
    (
        "By category / source (JSON)",
        "Nach Kategorie / Quelle (JSON)",
        "Par catégorie / source (JSON)",
        "Por categoría / fuente (JSON)",
        "Por categoria / fonte (JSON)",
        "По категории / источнику (JSON)",
    ),
    ("Filter", "Suchfilter", "Filtrer", "Filtro", "Filtro", "Фильтр"),
    ("Source", "Quelle", "Source", "Fuente", "Fonte", "Источник"),
    ("Category", "Kategorie", "Catégorie", "Categoría", "Categoria", "Категория"),
    ("All", "Alle", "Tous", "Todos", "Todos", "Все"),
    ("Name", "Name", "Nom", "Nombre", "Nome", "Имя"),
    ("Status", "Status", "État", "Estado", "Estado", "Состояние"),
    ("Properties", "Eigenschaften", "Propriétés", "Propiedades", "Propriedades", "Свойства"),
    (
        "Metadata (JSON)",
        "Metadaten (JSON)",
        "Métadonnées (JSON)",
        "Metadatos (JSON)",
        "Metadados (JSON)",
        "Метаданные (JSON)",
    ),
    (
        "Select components to inspect their metadata and spectra.",
        "Komponenten zur Anzeige von Metadaten und Spektren wählen.",
        "Sélectionnez des composants pour examiner leurs métadonnées et spectres.",
        "Seleccione componentes para ver sus metadatos y espectros.",
        "Selecione componentes para ver metadados e espectros.",
        "Выберите компоненты для просмотра метаданных и спектров.",
    ),
    (
        "Push selected",
        "Auswahl übertragen",
        "Transférer la sélection",
        "Transferir selección",
        "Transferir seleção",
        "Передать выбранные",
    ),
    (
        "Push all",
        "Alle übertragen",
        "Tout transférer",
        "Transferir todo",
        "Transferir tudo",
        "Передать все",
    ),
    (
        "Confirm import",
        "Import bestätigen",
        "Confirmer l’import",
        "Confirmar importación",
        "Confirmar importação",
        "Подтвердить импорт",
    ),
    ("Cancel", "Abbrechen", "Annuler", "Cancelar", "Cancelar", "Отмена"),
    (
        "Import these staging components into the connected MMFDB?",
        "Diese Zwischenkomponenten in die verbundene MMFDB importieren?",
        "Importer ces composants dans la MMFDB connectée ?",
        "¿Importar estos componentes a la MMFDB conectada?",
        "Importar estes componentes na MMFDB ligada?",
        "Импортировать эти компоненты в подключённую MMFDB?",
    ),
    (
        "Available sources",
        "Verfügbare Quellen",
        "Sources disponibles",
        "Fuentes disponibles",
        "Fontes disponíveis",
        "Доступные источники",
    ),
    (
        "Run selected script",
        "Gewähltes Skript starten",
        "Exécuter le script choisi",
        "Ejecutar script seleccionado",
        "Executar script selecionado",
        "Запустить выбранный скрипт",
    ),
    (
        "Browse this source",
        "Diese Quelle durchsuchen",
        "Parcourir cette source",
        "Explorar esta fuente",
        "Explorar esta fonte",
        "Просмотреть источник",
    ),
    (
        "Already scraped",
        "Bereits erfasst",
        "Déjà collectés",
        "Ya recopilados",
        "Já recolhidos",
        "Уже загружено",
    ),
    ("Endpoint", "Ziel", "Destination", "Destino", "Destino", "Назначение"),
    (
        "Local file",
        "Lokale Datei",
        "Fichier local",
        "Archivo local",
        "Ficheiro local",
        "Локальный файл",
    ),
    (
        "Server (ZMQ)",
        "Server (ZMQ)",
        "Serveur (ZMQ)",
        "Servidor (ZMQ)",
        "Servidor (ZMQ)",
        "Сервер (ZMQ)",
    ),
    (
        "Local MMFDB",
        "Lokale MMFDB",
        "MMFDB locale",
        "MMFDB local",
        "MMFDB local",
        "Локальная MMFDB",
    ),
    (
        "Replace existing reference set",
        "Referenzbestand ersetzen",
        "Remplacer les références",
        "Reemplazar referencias",
        "Substituir referências",
        "Заменить набор данных",
    ),
    (
        "Mark imported as approved",
        "Import als genehmigt markieren",
        "Marquer l’import comme approuvé",
        "Marcar importación como aprobada",
        "Marcar importação como aprovada",
        "Отметить импорт как одобренный",
    ),
    (
        "Advanced — connection & authentication",
        "Erweitert — Verbindung und Anmeldung",
        "Avancé — connexion et authentification",
        "Avanzado — conexión y autenticación",
        "Avançado — ligação e autenticação",
        "Дополнительно — подключение и вход",
    ),
    ("Host", "Host", "Hôte", "Host", "Host", "Хост"),
    (
        "Command port",
        "Befehlsport",
        "Port de commande",
        "Puerto de comandos",
        "Porta de comandos",
        "Порт команд",
    ),
    (
        "Publish port",
        "Publikationsport",
        "Port de publication",
        "Puerto de publicación",
        "Porta de publicação",
        "Порт публикаций",
    ),
    ("User", "Benutzer", "Utilisateur", "Usuario", "Utilizador", "Пользователь"),
    ("Password", "Passwort", "Mot de passe", "Contraseña", "Palavra-passe", "Пароль"),
    (
        "Check session",
        "Sitzung prüfen",
        "Vérifier la session",
        "Comprobar sesión",
        "Verificar sessão",
        "Проверить сеанс",
    ),
    (
        "Add all to MMFDB",
        "Alle zu MMFDB hinzufügen",
        "Tout ajouter à MMFDB",
        "Añadir todo a MMFDB",
        "Adicionar tudo a MMFDB",
        "Добавить всё в MMFDB",
    ),
    (
        "Administrator",
        "Administrator",
        "Administrateur",
        "Administrador",
        "Administrador",
        "Администратор",
    ),
    (
        "Not authorized",
        "Nicht autorisiert",
        "Non autorisé",
        "No autorizado",
        "Não autorizado",
        "Нет доступа",
    ),
    (
        "Wavelength (nm)",
        "Wellenlänge (nm)",
        "Longueur d’onde (nm)",
        "Longitud de onda (nm)",
        "Comprimento de onda (nm)",
        "Длина волны (нм)",
    ),
    ("Intensity", "Intensität", "Intensité", "Intensidad", "Intensidade", "Интенсивность"),
    ("Language", "Sprache", "Langue", "Idioma", "Idioma", "Язык"),
    ("Help", "Hilfe", "Aide", "Ayuda", "Ajuda", "Справка"),
]


_MORE = """
127.0.0.1|127.0.0.1|127.0.0.1|127.0.0.1|127.0.0.1|127.0.0.1
A component category of the staging database.|Eine Komponentenkategorie der Zwischendatenbank.|Une catégorie de composants de la base intermédiaire.|Una categoría de componentes de la base temporal.|Uma categoria de componentes da base temporária.|Категория компонентов промежуточной базы.
Abs max|Abs.-Max.|Abs max|Abs máx|Abs máx|Макс. погл.
Absorption maximum (nm).|Absorptionsmaximum (nm).|Maximum d’absorption (nm).|Máximo de absorción (nm).|Máximo de absorção (nm).|Максимум поглощения (нм).
Add every staging component to the chosen MMFDB (the result is logged below).|Alle Zwischenkomponenten zur gewählten MMFDB hinzufügen (das Ergebnis steht unten im Protokoll).|Ajouter tous les composants intermédiaires à la MMFDB choisie (le résultat est consigné ci-dessous).|Añadir todos los componentes temporales a la MMFDB elegida (el resultado queda en el registro de abajo).|Adicionar todos os componentes temporários à MMFDB escolhida (o resultado fica no registro abaixo).|Добавить все промежуточные компоненты в выбранную MMFDB (результат записывается в журнал ниже).
Add staging components to the MMFDB|Zwischenkomponenten zur MMFDB hinzufügen|Ajouter les composants intermédiaires à la MMFDB|Añadir componentes temporales a la MMFDB|Adicionar componentes temporários à MMFDB|Добавить промежуточные компоненты в MMFDB
Authenticate as this user. Defaults to the current session user.|Als dieser Benutzer anmelden. Standard ist der aktuelle Sitzungsbenutzer.|S’authentifier comme cet utilisateur. Par défaut l’utilisateur de la session.|Autenticarse como este usuario. Por defecto, el usuario de la sesión.|Autenticar como este usuário. O padrão é o usuário da sessão.|Войти как этот пользователь. По умолчанию — пользователь сеанса.
Back|Zurück|Retour|Atrás|Voltar|Назад
Cameras / SPADs / PMTs (quantum-efficiency curves).|Kameras / SPADs / PMTs (Quanteneffizienzkurven).|Caméras / SPAD / PMT (courbes de rendement quantique).|Cámaras / SPAD / PMT (curvas de eficiencia cuántica).|Câmeras / SPADs / PMTs (curvas de eficiência quântica).|Камеры / SPAD / ФЭУ (кривые квантовой эффективности).
Chromophore / fluorophore name.|Name des Chromophors / Fluorophors.|Nom du chromophore / fluorophore.|Nombre del cromóforo / fluoróforo.|Nome do cromóforo / fluoróforo.|Название хромофора / флуорофора.
Components|Komponenten|Composants|Componentes|Componentes|Компоненты
Components per category.|Komponenten pro Kategorie.|Composants par catégorie.|Componentes por categoría.|Componentes por categoria.|Компоненты по категориям.
Components per source.|Komponenten pro Quelle.|Composants par source.|Componentes por fuente.|Componentes por fonte.|Компоненты по источникам.
Components that carry at least one spectrum.|Komponenten mit mindestens einem Spektrum.|Composants ayant au moins un spectre.|Componentes con al menos un espectro.|Componentes com pelo menos um espectro.|Компоненты хотя бы с одним спектром.
Description|Beschreibung|Description|Descripción|Descrição|Описание
Dichroic beamsplitters / mirrors.|Dichroitische Strahlteiler / Spiegel.|Séparateurs dichroïques / miroirs.|Divisores de haz dicroicos / espejos.|Divisores de feixe dicroicos / espelhos.|Дихроичные светоделители / зеркала.
D₂₅|D₂₅|D₂₅|D₂₅|D₂₅|D₂₅
Em max|Em.-Max.|Em max|Em máx|Em máx|Макс. исп.
Emission maximum (nm).|Emissionsmaximum (nm).|Maximum d’émission (nm).|Máximo de emisión (nm).|Máximo de emissão (nm).|Максимум испускания (нм).
Extinction|Extinktion|Extinction|Extinción|Extinção|Экстинкция
Fluorescence lifetime (ns).|Fluoreszenzlebensdauer (ns).|Durée de vie de fluorescence (ns).|Tiempo de vida de fluorescencia (ns).|Tempo de vida de fluorescência (ns).|Время жизни флуоресценции (нс).
Fluorescence quantum yield.|Fluoreszenzquantenausbeute.|Rendement quantique de fluorescence.|Rendimiento cuántico de fluorescencia.|Rendimento quântico de fluorescência.|Квантовый выход флуоресценции.
Fluorophore, filter, dichroic, detector or light source.|Fluorophor, Filter, Dichroit, Detektor oder Lichtquelle.|Fluorophore, filtre, dichroïque, détecteur ou source lumineuse.|Fluoróforo, filtro, dicroico, detector o fuente de luz.|Fluoróforo, filtro, dicróico, detetor ou fonte de luz.|Флуорофор, фильтр, дихроик, детектор или источник света.
Free-text probe description.|Freitextbeschreibung der Sonde.|Description libre de la sonde.|Descripción libre de la sonda.|Descrição livre da sonda.|Произвольное описание зонда.
Go to the next panel.|Zum nächsten Bereich gehen.|Aller au panneau suivant.|Ir al panel siguiente.|Ir para o painel seguinte.|Перейти к следующей панели.
Go to the previous panel.|Zum vorherigen Bereich gehen.|Aller au panneau précédent.|Ir al panel anterior.|Ir para o painel anterior.|Перейти к предыдущей панели.
How many components are in it.|Wie viele Komponenten darin sind.|Combien de composants elle contient.|Cuántos componentes contiene.|Quantos componentes contém.|Сколько в ней компонентов.
How many components came from it.|Wie viele Komponenten daher stammen.|Combien de composants en proviennent.|Cuántos componentes provienen de ella.|Quantos componentes vieram dela.|Сколько компонентов получено оттуда.
ID|ID|ID|ID|ID|ID
Keep one category of component (All shows every category).|Eine Komponentenkategorie behalten (Alle zeigt jede Kategorie).|Garder une catégorie de composants (Tout affiche toutes les catégories).|Mantener una categoría de componentes (Todas muestra todas).|Manter uma categoria de componentes (Todas mostra todas).|Оставить одну категорию компонентов (Все показывает все).
Keep the components from one source (All shows every source).|Komponenten einer Quelle behalten (Alle zeigt jede Quelle).|Garder les composants d’une source (Tout affiche toutes les sources).|Mantener los componentes de una fuente (Todas muestra todas).|Manter os componentes de uma fonte (Todas mostra todas).|Оставить компоненты одного источника (Все показывает все).
Keep the components whose name contains this text.|Komponenten behalten, deren Name diesen Text enthält.|Garder les composants dont le nom contient ce texte.|Mantener los componentes cuyo nombre contiene este texto.|Manter os componentes cujo nome contém este texto.|Оставить компоненты, в названии которых есть этот текст.
Lamps / LEDs / lasers.|Lampen / LEDs / Laser.|Lampes / LED / lasers.|Lámparas / LED / láseres.|Lâmpadas / LEDs / lasers.|Лампы / светодиоды / лазеры.
Lifetime|Lebensdauer|Durée de vie|Tiempo de vida|Tempo de vida|Время жизни
MMFDB password. Not needed when the session user is already an administrator.|MMFDB-Passwort. Nicht nötig, wenn der Sitzungsbenutzer schon Administrator ist.|Mot de passe MMFDB. Inutile si l’utilisateur de la session est déjà administrateur.|Contraseña de MMFDB. No hace falta si el usuario de la sesión ya es administrador.|Senha da MMFDB. Desnecessária se o usuário da sessão já for administrador.|Пароль MMFDB. Не нужен, если пользователь сеанса уже администратор.
MMFDB probe identifier.|MMFDB-Sondenkennung.|Identifiant de sonde MMFDB.|Identificador de sonda de MMFDB.|Identificador de sonda da MMFDB.|Идентификатор зонда MMFDB.
MMFDB server host (server mode).|MMFDB-Serverhost (Servermodus).|Hôte du serveur MMFDB (mode serveur).|Host del servidor MMFDB (modo servidor).|Host do servidor MMFDB (modo servidor).|Хост сервера MMFDB (серверный режим).
Molar extinction coefficient (M^-1 cm^-1).|Molarer Extinktionskoeffizient (M^-1 cm^-1).|Coefficient d’extinction molaire (M^-1 cm^-1).|Coeficiente de extinción molar (M^-1 cm^-1).|Coeficiente de extinção molar (M^-1 cm^-1).|Молярный коэффициент экстинкции (M^-1 cm^-1).
Next|Weiter|Suivant|Siguiente|Seguinte|Далее
No|Nein|Non|No|Não|Нет
No components selected.|Keine Komponenten ausgewählt.|Aucun composant sélectionné.|Ningún componente seleccionado.|Nenhum componente selecionado.|Компоненты не выбраны.
Number of components in the staging database.|Anzahl der Komponenten in der Zwischendatenbank.|Nombre de composants de la base intermédiaire.|Número de componentes de la base temporal.|Número de componentes da base temporária.|Число компонентов в промежуточной базе.
OK|OK|OK|OK|OK|OK
Open Browse filtered to this source.|Durchsuchen auf diese Quelle gefiltert öffnen.|Ouvrir Parcourir filtré sur cette source.|Abrir Explorar filtrado por esta fuente.|Abrir Explorar filtrado por esta fonte.|Открыть просмотр с фильтром по этому источнику.
Optical filters.|Optische Filter.|Filtres optiques.|Filtros ópticos.|Filtros ópticos.|Оптические фильтры.
Path to the staging spectra database being summarised.|Pfad der zusammengefassten Zwischen-Spektrendatenbank.|Chemin de la base de spectres intermédiaire résumée.|Ruta de la base de espectros temporal resumida.|Caminho da base de espectros temporária resumida.|Путь к обобщаемой промежуточной базе спектров.
Probe ID|Sonden-ID|ID de la sonde|ID de la sonda|ID da sonda|ID зонда
Probe category (organic_dye, protein, nucleic_acid, ...).|Sondenkategorie (organic_dye, protein, nucleic_acid, ...).|Catégorie de sonde (organic_dye, protein, nucleic_acid, ...).|Categoría de sonda (organic_dye, protein, nucleic_acid, ...).|Categoria da sonda (organic_dye, protein, nucleic_acid, ...).|Категория зонда (organic_dye, protein, nucleic_acid, ...).
Probe id in the staging database.|Sonden-ID in der Zwischendatenbank.|Identifiant de la sonde dans la base intermédiaire.|ID de la sonda en la base temporal.|ID da sonda na base temporária.|ID зонда в промежуточной базе.
Probe type.|Sondentyp.|Type de sonde.|Tipo de sonda.|Tipo de sonda.|Тип зонда.
Property|Eigenschaft|Propriété|Propiedad|Propriedade|Свойство
Property name.|Name der Eigenschaft.|Nom de la propriété.|Nombre de la propiedad.|Nome da propriedade.|Название свойства.
Property value.|Wert der Eigenschaft.|Valeur de la propriété.|Valor de la propiedad.|Valor da propriedade.|Значение свойства.
Proteins + organic dyes + other fluorophores.|Proteine + organische Farbstoffe + andere Fluorophore.|Protéines + colorants organiques + autres fluorophores.|Proteínas + colorantes orgánicos + otros fluoróforos.|Proteínas + corantes orgânicos + outros fluoróforos.|Белки + органические красители + прочие флуорофоры.
Provenance source (fpbase, atto, spectra_db, user, ...).|Herkunftsquelle (fpbase, atto, spectra_db, user, ...).|Source de provenance (fpbase, atto, spectra_db, user, ...).|Fuente de procedencia (fpbase, atto, spectra_db, user, ...).|Fonte de proveniência (fpbase, atto, spectra_db, user, ...).|Источник происхождения (fpbase, atto, spectra_db, user, ...).
Purge the existing reference probes before importing (a backup is made for local files).|Vorhandene Referenzsonden vor dem Import löschen (für lokale Dateien wird eine Sicherung angelegt).|Purger les sondes de référence existantes avant l’import (une sauvegarde est faite pour les fichiers locaux).|Purgar las sondas de referencia existentes antes de importar (se hace una copia para archivos locales).|Eliminar as sondas de referência existentes antes de importar (é feita uma cópia para arquivos locais).|Удалить существующие эталонные зонды перед импортом (для локальных файлов делается резервная копия).
Push|Senden|Envoyer|Enviar|Enviar|Отправить
Push complete|Senden abgeschlossen|Envoi terminé|Envío completado|Envio concluído|Отправка завершена
Push every component of this staging database into the connected MMFDB (asks first).|Alle Komponenten dieser Zwischendatenbank an die verbundene MMFDB senden (fragt vorher).|Envoyer tous les composants de cette base intermédiaire à la MMFDB connectée (demande confirmation).|Enviar todos los componentes de esta base temporal a la MMFDB conectada (pregunta antes).|Enviar todos os componentes desta base temporária à MMFDB conectada (pergunta antes).|Отправить все компоненты этой промежуточной базы в подключённую MMFDB (сначала спрашивает).
Push failed|Senden fehlgeschlagen|Échec de l’envoi|Falló el envío|Falha no envio|Не удалось отправить
Push the ticked components into the connected MMFDB (asks first).|Die angehakten Komponenten an die verbundene MMFDB senden (fragt vorher).|Envoyer les composants cochés à la MMFDB connectée (demande confirmation).|Enviar los componentes marcados a la MMFDB conectada (pregunta antes).|Enviar os componentes marcados à MMFDB conectada (pergunta antes).|Отправить отмеченные компоненты в подключённую MMFDB (сначала спрашивает).
Push to MMFDB|An MMFDB senden|Envoyer à la MMFDB|Enviar a la MMFDB|Enviar à MMFDB|Отправить в MMFDB
QY|QY|QY|QY|QY|КВ
Quality|Qualität|Qualité|Calidad|Qualidade|Качество
Quality grade: unknown / low / medium / high.|Qualitätsstufe: unknown / low / medium / high.|Niveau de qualité : unknown / low / medium / high.|Grado de calidad: unknown / low / medium / high.|Grau de qualidade: unknown / low / medium / high.|Степень качества: unknown / low / medium / high.
Re-check whether the current session may add to the MMFDB.|Erneut prüfen, ob die aktuelle Sitzung zur MMFDB hinzufügen darf.|Revérifier si la session actuelle peut ajouter à la MMFDB.|Volver a comprobar si la sesión actual puede añadir a la MMFDB.|Verificar de novo se a sessão atual pode adicionar à MMFDB.|Повторно проверить, может ли текущий сеанс добавлять в MMFDB.
Re-read the counts from the staging database.|Die Zahlen aus der Zwischendatenbank neu einlesen.|Relire les totaux de la base intermédiaire.|Releer los totales de la base temporal.|Reler os totais da base temporária.|Заново прочитать числа из промежуточной базы.
Ready|Bereit|Prêt|Listo|Pronto|Готово
Reload the component list from the staging database.|Die Komponentenliste aus der Zwischendatenbank neu laden.|Recharger la liste des composants de la base intermédiaire.|Recargar la lista de componentes de la base temporal.|Recarregar a lista de componentes da base temporária.|Перезагрузить список компонентов из промежуточной базы.
Run the selected scraper into the staging database (one at a time).|Den gewählten Scraper in die Zwischendatenbank ausführen (einer nach dem anderen).|Lancer le scraper choisi vers la base intermédiaire (un à la fois).|Ejecutar el scraper elegido hacia la base temporal (de uno en uno).|Executar o scraper escolhido para a base temporária (um de cada vez).|Запустить выбранный скрейпер в промежуточную базу (по одному).
Shown components / all components.|Angezeigte Komponenten / alle Komponenten.|Composants affichés / tous les composants.|Componentes mostrados / todos los componentes.|Componentes mostrados / todos os componentes.|Показано компонентов / всего компонентов.
Source ref|Quellenverweis|Réf. de source|Ref. de fuente|Ref. da fonte|Ссылка на источник
Source reference / URL / accession.|Quellenverweis / URL / Zugangsnummer.|Référence de source / URL / numéro d’accès.|Referencia de fuente / URL / número de acceso.|Referência da fonte / URL / número de acesso.|Ссылка на источник / URL / номер доступа.
Stamp imported components as approved instead of unverified.|Importierte Komponenten als genehmigt statt ungeprüft markieren.|Marquer les composants importés comme approuvés plutôt que non vérifiés.|Marcar los componentes importados como aprobados en lugar de no verificados.|Marcar os componentes importados como aprovados em vez de não verificados.|Помечать импортированные компоненты как одобренные, а не непроверенные.
Target MMFDB SQLite path (local mode). Blank = the resolved live MMFDB.|SQLite-Pfad der Ziel-MMFDB (lokaler Modus). Leer = die aufgelöste aktive MMFDB.|Chemin SQLite de la MMFDB cible (mode local). Vide = la MMFDB active résolue.|Ruta SQLite de la MMFDB de destino (modo local). Vacío = la MMFDB activa resuelta.|Caminho SQLite da MMFDB de destino (modo local). Vazio = a MMFDB ativa resolvida.|Путь SQLite целевой MMFDB (локальный режим). Пусто = определённая действующая MMFDB.
The component's name.|Der Name der Komponente.|Le nom du composant.|El nombre del componente.|O nome do componente.|Название компонента.
The component's optical properties.|Die optischen Eigenschaften der Komponente.|Les propriétés optiques du composant.|Las propiedades ópticas del componente.|As propriedades ópticas do componente.|Оптические свойства компонента.
The probe row, its properties and a spectrum summary as JSON.|Die Sondenzeile, ihre Eigenschaften und eine Spektrenzusammenfassung als JSON.|La ligne de sonde, ses propriétés et un résumé des spectres en JSON.|La fila de la sonda, sus propiedades y un resumen de espectros en JSON.|A linha da sonda, suas propriedades e um resumo dos espectros em JSON.|Строка зонда, её свойства и сводка спектров в JSON.
The scraper to run into the staging database.|Der Scraper, der in die Zwischendatenbank ausgeführt wird.|Le scraper à lancer vers la base intermédiaire.|El scraper que se ejecutará hacia la base temporal.|O scraper a executar para a base temporária.|Скрейпер, запускаемый в промежуточную базу.
The scraper's output.|Die Ausgabe des Scrapers.|La sortie du scraper.|La salida del scraper.|A saída do scraper.|Вывод скрейпера.
The staging components. Tick the box of the ones to push, click a row to inspect it; the wheel scrolls.|Die Zwischenkomponenten. Kästchen der zu sendenden anhaken, Zeile anklicken zum Prüfen; das Mausrad scrollt.|Les composants intermédiaires. Cochez ceux à envoyer, cliquez une ligne pour l’examiner ; la molette fait défiler.|Los componentes temporales. Marque los que enviar, pulse una fila para inspeccionarla; la rueda desplaza.|Os componentes temporários. Marque os que enviar, clique numa linha para inspecioná-la; a roda rola.|Промежуточные компоненты. Отметьте нужные для отправки, щёлкните строку для просмотра; колесо прокручивает.
Tick to include the component in Push selected.|Anhaken, um die Komponente in „Ausgewählte senden“ einzuschließen.|Cocher pour inclure le composant dans « Envoyer la sélection ».|Marcar para incluir el componente en «Enviar seleccionados».|Marcar para incluir o componente em «Enviar selecionados».|Отметьте, чтобы включить компонент в «Отправить выбранные».
Timestamp of the verification decision.|Zeitstempel der Prüfentscheidung.|Horodatage de la décision de vérification.|Marca de tiempo de la decisión de verificación.|Carimbo de data/hora da decisão de verificação.|Время решения о проверке.
Translational diffusion coefficient in water at 25 °C (µm²/s); used by the FCS diffusion/volume calculator.|Translationaler Diffusionskoeffizient in Wasser bei 25 °C (µm²/s); vom FCS-Diffusions-/Volumenrechner verwendet.|Coefficient de diffusion translationnelle dans l’eau à 25 °C (µm²/s) ; utilisé par le calculateur FCS diffusion/volume.|Coeficiente de difusión traslacional en agua a 25 °C (µm²/s); lo usa la calculadora FCS de difusión/volumen.|Coeficiente de difusão translacional em água a 25 °C (µm²/s); usado pela calculadora FCS de difusão/volume.|Коэффициент поступательной диффузии в воде при 25 °C (мкм²/с); используется калькулятором диффузии/объёма FCS.
Type|Typ|Type|Tipo|Tipo|Тип
User who approved/rejected this probe.|Benutzer, der diese Sonde genehmigt/abgelehnt hat.|Utilisateur qui a approuvé/rejeté cette sonde.|Usuario que aprobó/rechazó esta sonda.|Usuário que aprovou/rejeitou esta sonda.|Пользователь, одобривший/отклонивший этот зонд.
Value|Wert|Valeur|Valor|Valor|Значение
Verification status.|Prüfstatus.|Statut de vérification.|Estado de verificación.|Estado de verificação.|Статус проверки.
Verification status: unverified / needs_review / approved / rejected.|Prüfstatus: unverified / needs_review / approved / rejected.|Statut de vérification : unverified / needs_review / approved / rejected.|Estado de verificación: unverified / needs_review / approved / rejected.|Estado de verificação: unverified / needs_review / approved / rejected.|Статус проверки: unverified / needs_review / approved / rejected.
Verified at|Geprüft am|Vérifié le|Verificado el|Verificado em|Проверено
Verified by|Geprüft von|Vérifié par|Verificado por|Verificado por|Проверил
What the import did.|Was der Import getan hat.|Ce que l’import a fait.|Lo que hizo la importación.|O que a importação fez.|Что сделал импорт.
What this source already put into the staging database.|Was diese Quelle bereits in die Zwischendatenbank gebracht hat.|Ce que cette source a déjà mis dans la base intermédiaire.|Lo que esta fuente ya puso en la base temporal.|O que esta fonte já colocou na base temporária.|Что этот источник уже поместил в промежуточную базу.
Where it was scraped from.|Woher sie bezogen wurde.|D’où elle a été récupérée.|De dónde se obtuvo.|De onde foi obtida.|Откуда получена.
Where the components were scraped from.|Woher die Komponenten bezogen wurden.|D’où les composants ont été récupérés.|De dónde se obtuvieron los componentes.|De onde os componentes foram obtidos.|Откуда получены компоненты.
Where to add the staging components: a local MMFDB file, or a running MMFDB server.|Wohin die Zwischenkomponenten hinzugefügt werden: eine lokale MMFDB-Datei oder ein laufender MMFDB-Server.|Où ajouter les composants intermédiaires : un fichier MMFDB local ou un serveur MMFDB en marche.|Dónde añadir los componentes temporales: un archivo MMFDB local o un servidor MMFDB en marcha.|Onde adicionar os componentes temporários: um arquivo MMFDB local ou um servidor MMFDB em execução.|Куда добавлять промежуточные компоненты: локальный файл MMFDB или работающий сервер MMFDB.
Whether the current session may add to the MMFDB.|Ob die aktuelle Sitzung zur MMFDB hinzufügen darf.|Si la session actuelle peut ajouter à la MMFDB.|Si la sesión actual puede añadir a la MMFDB.|Se a sessão atual pode adicionar à MMFDB.|Может ли текущий сеанс добавлять в MMFDB.
Yes|Ja|Oui|Sí|Sim|Да
ZMQ command port (server mode).|ZMQ-Befehlsport (Servermodus).|Port de commande ZMQ (mode serveur).|Puerto de comandos ZMQ (modo servidor).|Porta de comandos ZMQ (modo servidor).|Командный порт ZMQ (серверный режим).
ZMQ publish port (server mode).|ZMQ-Veröffentlichungsport (Servermodus).|Port de publication ZMQ (mode serveur).|Puerto de publicación ZMQ (modo servidor).|Porta de publicação ZMQ (modo servidor).|Порт публикации ZMQ (серверный режим).
leave blank for the resolved/connected MMFDB|leer lassen für die aufgelöste/verbundene MMFDB|laisser vide pour la MMFDB résolue/connectée|dejar vacío para la MMFDB resuelta/conectada|deixar vazio para a MMFDB resolvida/conectada|оставьте пустым для определённой/подключённой MMFDB
none yet|noch nichts|rien pour l’instant|aún nada|ainda nada|пока ничего
only needed if the session is not already authorized|nur nötig, wenn die Sitzung noch nicht autorisiert ist|nécessaire seulement si la session n’est pas déjà autorisée|solo hace falta si la sesión aún no está autorizada|necessário só se a sessão ainda não estiver autorizada|нужен, только если сеанс ещё не авторизован
session user|Sitzungsbenutzer|utilisateur de la session|usuario de la sesión|usuário da sessão|пользователь сеанса
Pushed {} component(s) into the MMFDB.|{} Komponente(n) an die MMFDB gesendet.|{} composant(s) envoyé(s) à la MMFDB.|{} componente(s) enviado(s) a la MMFDB.|{} componente(s) enviado(s) à MMFDB.|В MMFDB отправлено компонентов: {}.
Consolidated: {}|Konsolidiert: {}|Consolidés : {}|Consolidados: {}|Consolidados: {}|Объединено: {}
Push {} selected component(s) from this staging database into the connected MMFDB?|{} ausgewählte Komponente(n) aus dieser Zwischendatenbank an die verbundene MMFDB senden?|Envoyer {} composant(s) sélectionné(s) de cette base intermédiaire à la MMFDB connectée ?|¿Enviar {} componente(s) seleccionado(s) de esta base temporal a la MMFDB conectada?|Enviar {} componente(s) selecionado(s) desta base temporária à MMFDB conectada?|Отправить выбранные компоненты ({}) из этой промежуточной базы в подключённую MMFDB?
Push all {} component(s) from this staging database into the connected MMFDB?|Alle {} Komponente(n) dieser Zwischendatenbank an die verbundene MMFDB senden?|Envoyer les {} composant(s) de cette base intermédiaire à la MMFDB connectée ?|¿Enviar los {} componente(s) de esta base temporal a la MMFDB conectada?|Enviar os {} componente(s) desta base temporária à MMFDB conectada?|Отправить все компоненты ({}) этой промежуточной базы в подключённую MMFDB?
"""
_ROWS += [tuple(line.split("|")) for line in _MORE.strip().splitlines()]


def install():
    for idx, locale in enumerate(LOCALES):
        i18n.add_translations(locale, {r[0]: r[idx] for r in _ROWS}, context="spectra_downloader")


def tr(text):
    return i18n.tr(text, context="spectra_downloader")


# Control purposes are separate from labels so a tooltip explains the action.
_HELP_ROWS = [
    (
        "Inspect staging counts before importing.",
        "Zwischenbestand vor dem Import prüfen.",
        "Examiner les totaux avant l’import.",
        "Revise los totales antes de importar.",
        "Verifique os totais antes de importar.",
        "Проверьте данные перед импортом.",
    ),
    (
        "Filter components and inspect spectra.",
        "Komponenten filtern und Spektren prüfen.",
        "Filtrer les composants et examiner les spectres.",
        "Filtre componentes y examine espectros.",
        "Filtre componentes e examine espectros.",
        "Фильтруйте компоненты и просматривайте спектры.",
    ),
    (
        "Run a source scraper into this staging database.",
        "Quellenskript in diese Zwischendatenbank ausführen.",
        "Collecter une source dans cette base intermédiaire.",
        "Recopile una fuente en esta base temporal.",
        "Recolha uma fonte nesta base temporária.",
        "Загрузите источник в промежуточную базу.",
    ),
    (
        "Configure the import endpoint and administrator session.",
        "Importziel und Administratorsitzung konfigurieren.",
        "Configurer la destination et la session administrateur.",
        "Configure el destino y la sesión de administrador.",
        "Configure o destino e a sessão de administrador.",
        "Настройте назначение и сеанс администратора.",
    ),
    (
        "Reload the current staging database.",
        "Aktuelle Zwischendatenbank neu laden.",
        "Recharger la base intermédiaire.",
        "Recargue la base temporal.",
        "Recarregue a base temporária.",
        "Обновите промежуточную базу.",
    ),
    (
        "Match a component name, ignoring case.",
        "Komponentennamen ohne Groß-/Kleinschreibung suchen.",
        "Chercher un nom sans distinction de casse.",
        "Busque un nombre sin distinguir mayúsculas.",
        "Procure um nome sem distinguir maiúsculas.",
        "Ищите имя без учёта регистра.",
    ),
    (
        "Select one provenance source, including combined sources.",
        "Eine Herkunftsquelle auswählen, auch kombinierte Quellen.",
        "Choisir une provenance, y compris les sources combinées.",
        "Seleccione una procedencia, incluso fuentes combinadas.",
        "Selecione uma origem, incluindo fontes combinadas.",
        "Выберите источник, включая объединённые источники.",
    ),
    (
        "Restrict the list to one component category.",
        "Liste auf eine Komponentenkategorie begrenzen.",
        "Limiter la liste à une catégorie.",
        "Limite la lista a una categoría.",
        "Limite a lista a uma categoria.",
        "Ограничьте список одной категорией.",
    ),
    (
        "Import only the checked component IDs after confirmation.",
        "Nach Bestätigung nur markierte Komponenten importieren.",
        "Importer uniquement les composants cochés après confirmation.",
        "Importe solo componentes marcados tras confirmar.",
        "Importe apenas componentes marcados após confirmar.",
        "После подтверждения импортируйте только отмеченные компоненты.",
    ),
    (
        "Import every staging component after confirmation.",
        "Nach Bestätigung alle Zwischenkomponenten importieren.",
        "Importer tous les composants après confirmation.",
        "Importe todos los componentes tras confirmar.",
        "Importe todos os componentes após confirmar.",
        "После подтверждения импортируйте все компоненты.",
    ),
    (
        "Choose the registered scraper to run.",
        "Registriertes Quellenskript auswählen.",
        "Choisir le collecteur enregistré.",
        "Seleccione el recopilador registrado.",
        "Selecione o coletor registado.",
        "Выберите зарегистрированный скрипт загрузки.",
    ),
    (
        "Open the browser with this source selected.",
        "Browser mit dieser Quelle öffnen.",
        "Ouvrir le navigateur sur cette source.",
        "Abra el explorador con esta fuente.",
        "Abra o explorador com esta fonte.",
        "Откройте просмотр с этим источником.",
    ),
    (
        "Choose a local SQLite file or a ZMQ server.",
        "Lokale SQLite-Datei oder ZMQ-Server wählen.",
        "Choisir un fichier SQLite local ou un serveur ZMQ.",
        "Seleccione un archivo SQLite local o un servidor ZMQ.",
        "Selecione um ficheiro SQLite local ou um servidor ZMQ.",
        "Выберите локальный файл SQLite или сервер ZMQ.",
    ),
    (
        "Blank uses the connected MMFDB path.",
        "Leer verwendet den verbundenen MMFDB-Pfad.",
        "Vide utilise le chemin MMFDB connecté.",
        "Vacío usa la ruta MMFDB conectada.",
        "Vazio usa o caminho MMFDB ligado.",
        "Пустое поле использует путь подключённой MMFDB.",
    ),
    (
        "Purge old references before importing; local files receive a backup.",
        "Alte Referenzen vor dem Import löschen; lokale Dateien werden gesichert.",
        "Purger les anciennes références ; sauvegarder le fichier local.",
        "Borre referencias anteriores; el archivo local se guarda como copia.",
        "Apague referências anteriores; o ficheiro local recebe uma cópia.",
        "Удалите старые данные; для локального файла создаётся резервная копия.",
    ),
    (
        "Approve imported components instead of leaving them unverified.",
        "Importierte Komponenten genehmigen statt ungeprüft lassen.",
        "Approuver les composants importés au lieu de les laisser non vérifiés.",
        "Apruebe componentes importados en vez de dejarlos sin verificar.",
        "Aprove componentes importados em vez de deixá-los por verificar.",
        "Одобрите импортированные компоненты вместо статуса непроверенных.",
    ),
    (
        "Reuse a cached session or authenticate with these credentials.",
        "Gespeicherte Sitzung nutzen oder mit diesen Zugangsdaten anmelden.",
        "Réutiliser une session ou authentifier ces identifiants.",
        "Reutilice una sesión o autentique estas credenciales.",
        "Reutilize uma sessão ou autentique estas credenciais.",
        "Используйте сохранённый сеанс или эти учётные данные.",
    ),
    (
        "Recheck administrator permission for the configured endpoint.",
        "Administratorrechte für das gewählte Ziel erneut prüfen.",
        "Revérifier les droits administrateur pour cette destination.",
        "Compruebe los permisos de administrador para el destino.",
        "Verifique permissões de administrador para o destino.",
        "Проверьте права администратора для назначения.",
    ),
    (
        "Import the staging database using the endpoint and flags above.",
        "Zwischendatenbank mit obigem Ziel und Optionen importieren.",
        "Importer la base avec la destination et les options ci-dessus.",
        "Importe la base con el destino y opciones anteriores.",
        "Importe a base com o destino e opções acima.",
        "Импортируйте базу с указанным назначением и параметрами.",
    ),
    (
        "Change interface language without changing scientific data.",
        "Sprache ändern, ohne wissenschaftliche Daten zu ändern.",
        "Changer la langue sans modifier les données scientifiques.",
        "Cambie el idioma sin modificar datos científicos.",
        "Mude o idioma sem alterar dados científicos.",
        "Смените язык интерфейса без изменения научных данных.",
    ),
]
TOOLTIPS = dict(
    zip(
        (
            "Overview",
            "Browse",
            "Download",
            "Add to MMFDB",
            "Refresh",
            "Filter",
            "Source",
            "Category",
            "Push selected",
            "Push all",
            "Available sources",
            "Browse this source",
            "Endpoint",
            "Local MMFDB",
            "Replace existing reference set",
            "Mark imported as approved",
            "Advanced — connection & authentication",
            "Check session",
            "Add all to MMFDB",
            "Language",
        ),
        (r[0] for r in _HELP_ROWS),
    )
)
TOOLTIPS["Run selected script"] = TOOLTIPS["Download"]
for _index, _locale in enumerate(LOCALES):
    i18n.add_translations(
        _locale, {r[0]: r[_index] for r in _HELP_ROWS}, context="spectra_downloader"
    )
