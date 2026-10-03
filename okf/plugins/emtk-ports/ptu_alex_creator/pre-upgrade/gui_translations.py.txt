"""ALEX labels and control help for every bundled ChiSurf UI locale."""

from emtk.i18n import add_translations

# English | German | French | Spanish | Portuguese | Russian.
ROWS = """Database|Datenbank|Base de données|Base de datos|Banco de dados|База данных
Queue TTTR data from the session database.|TTTR-Daten aus der Sitzungsdatenbank einreihen.|Ajouter les données TTTR de la base de session.|Añadir datos TTTR de la base de la sesión.|Adicionar dados TTTR do banco da sessão.|Добавить данные TTTR из базы сеанса.
Conversion|Konvertierung|Conversion|Conversión|Conversão|Преобразование
Batch|Stapelverarbeitung|Traitement par lot|Procesamiento por lotes|Processamento em lote|Пакетная обработка
ALEX micro-time histogram|ALEX-Mikrozeit-Histogramm|Histogramme des microtemps ALEX|Histograma de microtiempo ALEX|Histograma de microtempo ALEX|Гистограмма микровремени ALEX
Open…|Öffnen…|Ouvrir…|Abrir…|Abrir…|Открыть…
Save as…|Speichern unter…|Enregistrer sous…|Guardar como…|Guardar como…|Сохранить как…
Guide|Anleitung|Guide|Guía|Guia|Руководство
Help|Hilfe|Aide|Ayuda|Ajuda|Справка
Input file|Eingabedatei|Fichier source|Archivo de entrada|Arquivo de entrada|Входной файл
Load|Laden|Charger|Cargar|Carregar|Загрузить
Input format|Eingabeformat|Format source|Formato de entrada|Formato de entrada|Входной формат
Output format|Ausgabeformat|Format de sortie|Formato de salida|Formato de saída|Выходной формат
Period|Periode|Période|Período|Período|Период
Shift|Verschiebung|Décalage|Desplazamiento|Deslocamento|Сдвиг
events|Ereignisse|événements|eventos|eventos|событий
Add files…|Dateien hinzufügen…|Ajouter des fichiers…|Añadir archivos…|Adicionar arquivos…|Добавить файлы…
Folder…|Ordner…|Dossier…|Carpeta…|Pasta…|Папка…
Clear|Leeren|Vider|Vaciar|Limpar|Очистить
Run batch|Stapel starten|Exécuter le lot|Ejecutar lote|Executar lote|Запустить пакет
Mode|Modus|Mode|Modo|Modo|Режим
Convert each|Einzeln konvertieren|Convertir chaque fichier|Convertir cada archivo|Converter cada arquivo|Преобразовать каждый
Merge into one|In eine Datei zusammenführen|Fusionner en un fichier|Combinar en uno|Combinar em um|Объединить в один
Output folder|Ausgabeordner|Dossier de sortie|Carpeta de salida|Pasta de saída|Выходная папка
Browse…|Durchsuchen…|Parcourir…|Examinar…|Procurar…|Обзор…
Remove|Entfernen|Retirer|Quitar|Remover|Удалить
Micro-time bin|Mikrozeit-Bin|Canal de microtemps|Intervalo de microtiempo|Intervalo de microtempo|Канал микровремени
Counts|Zählungen|Comptages|Recuentos|Contagens|Отсчёты
ALEX phase|ALEX-Phase|Phase ALEX|Fase ALEX|Fase ALEX|Фаза ALEX
Working…|Verarbeitung…|Traitement…|Procesando…|Processando…|Обработка…
Loading…|Laden…|Chargement…|Cargando…|Carregando…|Загрузка…
Loaded|Geladen|Chargé|Cargado|Carregado|Загружено
Written files|Geschriebene Dateien|Fichiers écrits|Archivos escritos|Arquivos gravados|Записанные файлы
TTTR files|TTTR-Dateien|Fichiers TTTR|Archivos TTTR|Arquivos TTTR|Файлы TTTR
Please choose an existing TTTR file.|Bitte eine vorhandene TTTR-Datei wählen.|Choisissez un fichier TTTR existant.|Elija un archivo TTTR existente.|Escolha um arquivo TTTR existente.|Выберите существующий файл TTTR.
Choose a different output file to preserve the source.|Andere Ausgabedatei wählen, um die Quelle zu erhalten.|Choisissez un autre fichier de sortie pour préserver la source.|Elija otro archivo de salida para conservar el original.|Escolha outro arquivo de saída para preservar a origem.|Выберите другой выходной файл, чтобы сохранить исходный.
Load a file to preview ALEX phase.|Datei laden, um die ALEX-Phase anzuzeigen.|Chargez un fichier pour afficher la phase ALEX.|Cargue un archivo para ver la fase ALEX.|Carregue um arquivo para ver a fase ALEX.|Загрузите файл для просмотра фазы ALEX.
Load a TTTR file and preview its folded ALEX phase.|TTTR-Datei laden und die gefaltete ALEX-Phase anzeigen.|Charger un fichier TTTR et afficher sa phase ALEX repliée.|Cargar un archivo TTTR y ver su fase ALEX plegada.|Carregar um arquivo TTTR e ver sua fase ALEX dobrada.|Загрузить файл TTTR и просмотреть свёрнутую фазу ALEX.
Write converted photon data without changing the input.|Konvertierte Photonendaten schreiben, ohne die Eingabe zu ändern.|Écrire les photons convertis sans modifier la source.|Escribir fotones convertidos sin modificar la entrada.|Gravar fótons convertidos sem alterar a entrada.|Записать преобразованные фотоны без изменения исходного файла.
Walk through loading, timing and conversion.|Anleitung für Laden, Zeitparameter und Konvertierung.|Guide du chargement, des paramètres temporels et de la conversion.|Guía de carga, tiempos y conversión.|Guia de carregamento, tempos e conversão.|Руководство по загрузке, времени и преобразованию.
Read ALEX conversion and batch workflow help.|Hilfe zur ALEX-Konvertierung und Stapelverarbeitung lesen.|Lire l’aide sur la conversion ALEX et les lots.|Leer ayuda de conversión ALEX y lotes.|Ler ajuda de conversão ALEX e lotes.|Прочитать справку о преобразовании ALEX и пакетах.
Enter a TTTR path, then press Load; dropping a file also loads it.|TTTR-Pfad eingeben, dann Laden drücken; Dateien können auch abgelegt werden.|Saisir un chemin TTTR puis Charger ; déposer un fichier le charge aussi.|Introduzca una ruta TTTR y pulse Cargar; también puede soltar un archivo.|Digite um caminho TTTR e pressione Carregar; também pode soltar um arquivo.|Введите путь TTTR и нажмите Загрузить; можно также перетащить файл.
Read the file entered above.|Die oben eingetragene Datei lesen.|Lire le fichier indiqué ci-dessus.|Leer el archivo indicado arriba.|Ler o arquivo indicado acima.|Прочитать указанный выше файл.
Auto detects the container; choose a format to override detection.|Auto erkennt den Container; ein gewähltes Format überschreibt die Erkennung.|Auto détecte le conteneur ; choisir un format impose ce choix.|Auto detecta el contenedor; elija un formato para forzarlo.|Auto detecta o contêiner; escolha um formato para forçá-lo.|Auto определяет контейнер; выберите формат для явного задания.
Select the file container used for single and batch output.|Dateicontainer für Einzel- und Stapelausgabe wählen.|Choisir le conteneur des sorties individuelles et par lot.|Elegir el contenedor para salidas individuales y por lotes.|Escolher o contêiner para saídas individuais e em lote.|Выберите контейнер для одиночного и пакетного вывода.
Alternation period in macro-time units; maps phase to micro-time.|Alternationsperiode in Makrozeit-Einheiten; bildet die Phase auf Mikrozeit ab.|Période d’alternance en unités de macrotemps ; transforme la phase en microtemps.|Período de alternancia en unidades de macrotiempo; transforma fase en microtiempo.|Período de alternância em unidades de macrotempo; transforma fase em microtempo.|Период чередования в единицах макровремени; переводит фазу в микровремя.
Phase offset applied before folding macro-time into micro-time.|Phasenverschiebung vor der Faltung von Makrozeit in Mikrozeit.|Décalage de phase avant le repliement du macrotemps en microtemps.|Desplazamiento de fase antes de plegar macrotiempo en microtiempo.|Deslocamento de fase antes de dobrar macrotempo em microtempo.|Сдвиг фазы перед свёрткой макровремени в микровремя.
Queue TTTR files; duplicate paths are ignored.|TTTR-Dateien einreihen; doppelte Pfade werden ignoriert.|Ajouter des fichiers TTTR ; les doublons sont ignorés.|Añadir archivos TTTR; se ignoran rutas duplicadas.|Adicionar arquivos TTTR; caminhos duplicados são ignorados.|Добавить файлы TTTR; повторные пути игнорируются.
Queue supported TTTR files recursively from a folder.|Unterstützte TTTR-Dateien rekursiv aus einem Ordner einreihen.|Ajouter les fichiers TTTR compatibles d’un dossier et ses sous-dossiers.|Añadir archivos TTTR compatibles de una carpeta y subcarpetas.|Adicionar arquivos TTTR compatíveis de uma pasta e subpastas.|Добавить поддерживаемые файлы TTTR из папки и подпапок.
Empty the queue without deleting files.|Warteschlange leeren, ohne Dateien zu löschen.|Vider la liste sans supprimer les fichiers.|Vaciar la cola sin borrar archivos.|Limpar a fila sem excluir arquivos.|Очистить очередь без удаления файлов.
Convert each file or merge the queue using the current timing.|Dateien einzeln konvertieren oder mit aktuellen Zeitparametern zusammenführen.|Convertir chaque fichier ou fusionner avec les paramètres temporels actuels.|Convertir cada archivo o combinar con los tiempos actuales.|Converter cada arquivo ou combinar com os tempos atuais.|Преобразовать каждый файл или объединить с текущими параметрами времени.
Choose separate output files or one merged photon stream.|Einzelne Ausgabedateien oder einen vereinten Photonenstrom wählen.|Choisir des sorties séparées ou un flux de photons fusionné.|Elegir archivos separados o un flujo de fotones combinado.|Escolher arquivos separados ou um fluxo de fótons combinado.|Выберите отдельные файлы или объединённый поток фотонов.
Convert requires a folder; merge defaults to the first input folder.|Konvertierung erfordert einen Ordner; Zusammenführung nutzt standardmäßig den ersten Eingabeordner.|La conversion exige un dossier ; la fusion utilise par défaut celui de la première source.|Convertir requiere carpeta; combinar usa por defecto la de la primera entrada.|Converter exige pasta; combinar usa por padrão a da primeira entrada.|Преобразование требует папку; объединение по умолчанию использует папку первого файла.
Choose the output directory.|Ausgabeordner wählen.|Choisir le dossier de sortie.|Elegir carpeta de salida.|Escolher pasta de saída.|Выберите выходную папку.
Remove this file from the queue; keep it on disk.|Diese Datei aus der Warteschlange entfernen, auf der Festplatte behalten.|Retirer ce fichier de la liste sans le supprimer du disque.|Quitar este archivo de la cola sin borrarlo del disco.|Remover este arquivo da fila sem excluí-lo do disco.|Удалить файл из очереди, сохранив его на диске.
Please load a TTTR file first.|Bitte zuerst eine TTTR-Datei laden.|Chargez d’abord un fichier TTTR.|Cargue primero un archivo TTTR.|Carregue primeiro um arquivo TTTR.|Сначала загрузите файл TTTR.
Add .sm (or other TTTR) files to the batch list first.|Zuerst .sm- oder andere TTTR-Dateien einreihen.|Ajoutez d’abord des fichiers .sm ou TTTR.|Añada primero archivos .sm u otros TTTR.|Adicione primeiro arquivos .sm ou outros TTTR.|Сначала добавьте файлы .sm или другие TTTR.
Choose an output folder for the converted files.|Ausgabeordner für konvertierte Dateien wählen.|Choisissez un dossier pour les fichiers convertis.|Elija carpeta para los archivos convertidos.|Escolha pasta para os arquivos convertidos.|Выберите папку для преобразованных файлов."""


def install_translations():
    for index, locale in enumerate(("en", "de", "fr", "es", "pt", "ru")):
        entries = [line.split("|") for line in ROWS.splitlines()]
        add_translations(locale, {row[0]: row[index] for row in entries})


HELP = {
    "de": """# ALEX Creator
Laden Sie eine TTTR-Datei, auch .sm. Wählen Sie Eingabe- und Ausgabeformat sowie Periode und Verschiebung in Makrozeit-Einheiten. Das Histogramm zeigt die gefaltete Mikrozeit-Phase und aktualisiert sich bei Änderungen.
Speichern unter schreibt eine neue Datei; die Quelle bleibt erhalten. Die gemeinsame Konvertierungs-API bestimmt die Regeln für Photonendaten und Metadaten.
Für Stapelverarbeitung Dateien oder Ordner hinzufügen. Konvertieren benötigt einen Ausgabeordner. Zusammenführen versetzt die Makrozeiten in einen monotonen Strom und faltet dann ALEX; ohne Ausgabeordner wird der erste Eingabeordner verwendet. Rechtsklick entfernt Dateien aus der Warteschlange. Datenbank lädt TTTR-Datensätze aus der Sitzung.
Eine abgelegte Datei wird geladen; mehrere Dateien oder Ordner werden eingereiht. Formate, Zeitparameter, Pfade, Stapeloptionen und Docklayout werden gespeichert. Eine gespeicherte Eingabe muss explizit geladen werden.""",
    "fr": """# ALEX Creator
Chargez un fichier TTTR, y compris .sm. Choisissez les formats source et sortie, la période et le décalage en unités de macrotemps. L’histogramme affiche la phase de microtemps repliée et se met à jour lors des changements.
Enregistrer sous écrit un nouveau fichier et préserve la source. L’API de conversion commune définit les règles pour les photons et les métadonnées.
Pour les lots, ajoutez des fichiers ou dossiers. Convertir exige un dossier de sortie. Fusionner décale les macrotemps en un flux monotone avant le repliement ALEX ; sans dossier de sortie, celui de la première source est utilisé. Un clic droit retire un fichier de la liste. Base de données charge les données TTTR de la session.
Déposer un fichier charge l’aperçu ; plusieurs fichiers ou dossiers remplissent la liste. Les formats, temps, chemins, options de lot et disposition sont mémorisés. Le fichier mémorisé doit être chargé explicitement.""",
    "es": """# ALEX Creator
Cargue un archivo TTTR, incluido .sm. Elija formatos de entrada y salida, período y desplazamiento en unidades de macrotiempo. El histograma muestra la fase de microtiempo plegada y se actualiza al cambiar parámetros.
Guardar como escribe un archivo nuevo y conserva el original. La API de conversión compartida define las reglas para fotones y metadatos.
Para lotes, añada archivos o carpetas. Convertir requiere carpeta de salida. Combinar desplaza macrotiempos a un flujo monótono antes de plegar ALEX; sin carpeta usa la de la primera entrada. El clic derecho quita un archivo de la cola. Base de datos carga datos TTTR de la sesión.
Soltar un archivo carga la vista previa; varios archivos o carpetas se añaden a la cola. Se guardan formatos, tiempos, rutas, opciones de lote y disposición. La entrada recordada debe cargarse explícitamente.""",
    "pt": """# ALEX Creator
Carregue um arquivo TTTR, incluindo .sm. Escolha formatos de entrada e saída, período e deslocamento em unidades de macrotempo. O histograma mostra a fase de microtempo dobrada e atualiza ao alterar parâmetros.
Guardar como grava um novo arquivo e preserva a origem. A API de conversão compartilhada define as regras para fótons e metadados.
Para lotes, adicione arquivos ou pastas. Converter exige pasta de saída. Combinar desloca macrotempos para um fluxo monótono antes de dobrar ALEX; sem pasta usa a da primeira entrada. O clique direito remove um arquivo da fila. Banco de dados carrega dados TTTR da sessão.
Soltar um arquivo carrega a visualização; vários arquivos ou pastas entram na fila. Formatos, tempos, caminhos, opções de lote e disposição são salvos. A entrada lembrada deve ser carregada explicitamente.""",
    "ru": """# ALEX Creator
Загрузите файл TTTR, включая .sm. Выберите входной и выходной форматы, период и сдвиг в единицах макровремени. Гистограмма показывает свёрнутую фазу микровремени и обновляется при изменении параметров.
Сохранить как записывает новый файл и сохраняет исходный. Общий API преобразования определяет правила для фотонов и метаданных.
Для пакетов добавьте файлы или папки. Преобразование требует выходную папку. Объединение сдвигает макровремя в монотонный поток перед свёрткой ALEX; без выходной папки используется папка первого файла. Правый щелчок удаляет файл из очереди. База данных загружает данные TTTR из сеанса.
Перетаскивание одного файла загружает просмотр; несколько файлов или папок добавляются в очередь. Форматы, время, пути, пакетные настройки и расположение сохраняются. Сохранённый входной файл следует загрузить явно.""",
}
