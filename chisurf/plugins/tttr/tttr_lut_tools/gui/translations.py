"""Supplement the existing six ChiSurf catalogs with native LUT vocabulary."""

from emtk import i18n

from chisurf.emtk.i18n import install as install_chisurf

# Columns: English, German, French, Spanish, Portuguese, Russian.
_ROWS = """
Advanced|Erweitert|Avancé|Avanzado|Avançado|Дополнительно
Show advanced calibration parameters.|Erweiterte Kalibrierparameter anzeigen.|Afficher les paramètres avancés d'étalonnage.|Mostrar parámetros avanzados de calibración.|Mostrar parâmetros avançados de calibração.|Показать дополнительные параметры калибровки.
Copy JSON|JSON kopieren|Copier JSON|Copiar JSON|Copiar JSON|Копировать JSON
Close|Schließen|Fermer|Cerrar|Fechar|Закрыть
Copy the complete correction settings to the clipboard.|Vollständige Korrektureinstellungen in die Zwischenablage kopieren.|Copier tous les paramètres de correction dans le presse-papiers.|Copiar todos los ajustes de corrección al portapapeles.|Copiar todas as configurações de correção para a área de transferência.|Скопировать все настройки коррекции в буфер обмена.
Close the JSON preview.|JSON-Vorschau schließen.|Fermer l'aperçu JSON.|Cerrar la vista previa JSON.|Fechar a prévia JSON.|Закрыть предпросмотр JSON.
Workflow|Arbeitsablauf|Flux de travail|Flujo de trabajo|Fluxo de trabalho|Рабочий процесс
Compute LUT|LUT berechnen|Calculer la LUT|Calcular LUT|Calcular LUT|Рассчитать LUT
Assign LUTs and shifts|LUTs und Verschiebungen zuweisen|Affecter LUT et décalages|Asignar LUT y desplazamientos|Atribuir LUT e deslocamentos|Назначить LUT и сдвиги
LUT controls|LUT-Steuerung|Commandes LUT|Controles LUT|Controles LUT|Управление LUT
TAC histograms|TAC-Histogramme|Histogrammes TAC|Histogramas TAC|Histogramas TAC|Гистограммы TAC
LUT Tools — help|LUT-Werkzeuge — Hilfe|Outils LUT — aide|Herramientas LUT — ayuda|Ferramentas LUT — ajuda|Инструменты LUT — справка
Add files|Dateien hinzufügen|Ajouter des fichiers|Añadir archivos|Adicionar arquivos|Добавить файлы
Folder|Ordner|Dossier|Carpeta|Pasta|Папка
Database|Datenbank|Base de données|Base de datos|Banco de dados|База данных
Clear files|Dateien entfernen|Vider les fichiers|Vaciar archivos|Limpar arquivos|Очистить файлы
Preview channel|Vorschaukanal|Canal de prévisualisation|Canal de vista previa|Canal de prévia|Канал предпросмотра
Linear start|Linearer Anfang|Début linéaire|Inicio lineal|Início linear|Начало линейной области
Linear stop|Lineares Ende|Fin linéaire|Fin lineal|Fim linear|Конец линейной области
TAC channels required|Benötigte TAC-Kanäle|Canaux TAC requis|Canales TAC requeridos|Canais TAC necessários|Число каналов TAC
Offset|Versatz|Décalage|Desfase|Deslocamento|Смещение
Preview photons|Vorschauphotonen|Photons de prévisualisation|Fotones de vista previa|Fótons da prévia|Фотоны предпросмотра
Low-count threshold|Schwelle kleiner Zählwerte|Seuil des faibles comptages|Umbral de cuentas bajas|Limiar de contagens baixas|Порог малых отсчётов
RNG seed|Zufallsstartwert|Graine aléatoire|Semilla aleatoria|Semente aleatória|Начальное число генератора
Wrap epsilon|Überlauf-Epsilon|Epsilon de bouclage|Épsilon de envoltura|Épsilon de retorno|Эпсилон циклического перехода
ε (wrap)|ε (Überlauf)|ε (bouclage)|ε (envoltura)|ε (retorno)|ε (цикл. переход)
Mitigate wrap spike (floor + ε)|Überlaufspitze reduzieren (Abrundung + ε)|Réduire le pic de bouclage (arrondi inf. + ε)|Reducir el pico de envoltura (redondeo inf. + ε)|Reduzir o pico de retorno (arredondamento inf. + ε)|Снизить пик циклического перехода (округление вниз + ε)
Normalize by region mean|Mit Bereichsmittelwert normieren|Normaliser par la moyenne de la région|Normalizar por la media de la región|Normalizar pela média da região|Нормировать по среднему области
Mitigate wrap spike|Überlaufspitze reduzieren|Réduire le pic de bouclage|Reducir el pico de envoltura|Reduzir o pico de retorno|Снизить пик циклического перехода
Auto-detect region|Bereich automatisch erkennen|Détecter automatiquement la région|Detectar región automáticamente|Detectar região automaticamente|Найти область автоматически
Add all channels to setup|Alle Kanäle zur Konfiguration hinzufügen|Ajouter tous les canaux à la configuration|Añadir todos los canales a la configuración|Adicionar todos os canais à configuração|Добавить все каналы в конфигурацию
Save LUT|LUT speichern|Enregistrer la LUT|Guardar LUT|Salvar LUT|Сохранить LUT
Export corrected|Korrigierte Daten exportieren|Exporter les données corrigées|Exportar datos corregidos|Exportar dados corrigidos|Экспорт исправленных данных
Reading routine|Leseformat|Format de lecture|Formato de lectura|Formato de leitura|Формат чтения
Load LUT|LUT laden|Charger la LUT|Cargar LUT|Carregar LUT|Загрузить LUT
Clear LUTs|LUTs entfernen|Vider les LUT|Vaciar LUT|Limpar LUT|Очистить LUT
Remove LUT|LUT entfernen|Supprimer la LUT|Eliminar LUT|Remover LUT|Удалить LUT
Assign selected|Ausgewählten Kanal zuweisen|Affecter au canal sélectionné|Asignar al canal seleccionado|Atribuir ao canal selecionado|Назначить выбранному каналу
Assign all|Allen zuweisen|Affecter à tous|Asignar a todos|Atribuir a todos|Назначить всем
Show channel|Kanal anzeigen|Afficher le canal|Mostrar canal|Mostrar canal|Показать канал
Channel|Kanal|Canal|Canal|Canal|Канал
Shift|Verschiebung|Décalage|Desplazamiento|Deslocamento|Сдвиг
Show LUT panel|LUT-Bereich anzeigen|Afficher le panneau LUT|Mostrar panel LUT|Mostrar painel LUT|Показать панель LUT
Log counts|Logarithmische Zählwerte|Comptages logarithmiques|Cuentas logarítmicas|Contagens logarítmicas|Логарифмические отсчёты
Show JSON|JSON anzeigen|Afficher JSON|Mostrar JSON|Mostrar JSON|Показать JSON
Load JSON|JSON laden|Charger JSON|Cargar JSON|Carregar JSON|Загрузить JSON
Save JSON|JSON speichern|Enregistrer JSON|Guardar JSON|Salvar JSON|Сохранить JSON
Help|Hilfe|Aide|Ayuda|Ajuda|Справка
Apply to detector setup|Auf Detektorkonfiguration anwenden|Appliquer à la configuration du détecteur|Aplicar a la configuración del detector|Aplicar à configuração do detector|Применить к конфигурации детектора
Working…|Verarbeitung…|Traitement…|Procesando…|Processando…|Обработка…
Select file|Datei auswählen|Sélectionner un fichier|Seleccionar archivo|Selecionar arquivo|Выбрать файл
Settings JSON preview|JSON-Einstellungsvorschau|Aperçu JSON des paramètres|Vista previa JSON de ajustes|Prévia JSON das configurações|Предпросмотр настроек JSON
Raw TAC|Unkorrigierter TAC|TAC brut|TAC sin corregir|TAC bruto|Исходный TAC
Corrected TAC preview|Korrigierte TAC-Vorschau|Aperçu du TAC corrigé|Vista previa TAC corregido|Prévia TAC corrigido|Предпросмотр исправленного TAC
Corrected|Korrigiert|Corrigé|Corregido|Corrigido|Исправленный
Raw|Unkorrigiert|Brut|Sin corregir|Bruto|Исходный
Counts|Zählwerte|Comptages|Cuentas|Contagens|Отсчёты
log10 Counts|log10 Zählwerte|log10 comptages|log10 cuentas|log10 contagens|log10 отсчётов
Microtime (bins)|Mikrozeit (Bins)|Microtemps (bins)|Microtiempo (bins)|Microtempo (bins)|Микровремя (бины)
Channel correction preview|Kanal-Korrekturvorschau|Aperçu de correction des canaux|Vista previa de corrección de canales|Prévia da correção dos canais|Предпросмотр коррекции каналов
Cumulative NTAC|Kumulativer NTAC|NTAC cumulatif|NTAC acumulado|NTAC acumulado|Накопленный NTAC
Bin increments|Bin-Inkremente|Incréments par bin|Incrementos por bin|Incrementos por bin|Приращения бинов
Drop photon files here or use Add files.|Photonendateien hier ablegen oder hinzufügen.|Déposez les fichiers de photons ici ou ajoutez-les.|Suelte aquí archivos de fotones o añádalos.|Solte aqui arquivos de fótons ou adicione-os.|Перетащите файлы фотонов сюда или добавьте их.
Load uniform-illumination files to inspect the TAC histogram.|Dateien mit gleichmäßiger Beleuchtung zur TAC-Prüfung laden.|Chargez des fichiers d'éclairage uniforme pour examiner le TAC.|Cargue archivos de iluminación uniforme para examinar el TAC.|Carregue arquivos de iluminação uniforme para examinar o TAC.|Загрузите файлы равномерного освещения для просмотра TAC.
Raw TAC — drag region boundaries, offset and threshold|TAC — Bereichsgrenzen, Versatz und Schwelle ziehen|TAC brut — déplacer les limites, le décalage et le seuil|TAC bruto — arrastre límites, desfase y umbral|TAC bruto — arraste limites, deslocamento e limiar|Исходный TAC — перетащите границы, смещение и порог
0: Compute per-channel LUTs. 1: Assign and preview correction.|0: Kanal-LUTs berechnen. 1: Zuweisen und Korrektur prüfen.|0 : Calculer les LUT par canal. 1 : Affecter et vérifier la correction.|0: Calcular LUT por canal. 1: Asignar y revisar la corrección.|0: Calcular LUT por canal. 1: Atribuir e revisar a correção.|0: Рассчитать LUT каналов. 1: Назначить и проверить коррекцию.
Load uniform-illumination or preview TTTR files.|TTTR-Dateien mit gleichmäßiger Beleuchtung oder zur Vorschau laden.|Charger les fichiers TTTR d'éclairage uniforme ou de prévisualisation.|Cargar archivos TTTR de iluminación uniforme o vista previa.|Carregar arquivos TTTR de iluminação uniforme ou prévia.|Загрузить TTTR равномерного освещения или предпросмотра.
Load supported photon files recursively from a folder.|Unterstützte Photonendateien rekursiv aus einem Ordner laden.|Charger récursivement les fichiers de photons d'un dossier.|Cargar recursivamente archivos de fotones de una carpeta.|Carregar recursivamente arquivos de fótons de uma pasta.|Загрузить файлы фотонов из папки и подпапок.
Select photon files from the MMFDB object store.|Photonendateien aus dem MMFDB-Objektspeicher auswählen.|Sélectionner les fichiers de photons dans MMFDB.|Seleccionar archivos de fotones de MMFDB.|Selecionar arquivos de fótons do MMFDB.|Выбрать файлы фотонов из хранилища MMFDB.
Unload input files; retain assigned LUTs.|Eingabedateien entfernen; zugewiesene LUTs behalten.|Vider les fichiers d'entrée ; conserver les LUT affectées.|Vaciar entradas; conservar LUT asignadas.|Limpar entradas; manter LUT atribuídas.|Очистить входные файлы, сохранив назначенные LUT.
Remove this input file.|Diese Eingabedatei entfernen.|Retirer ce fichier d'entrée.|Eliminar este archivo de entrada.|Remover este arquivo de entrada.|Удалить этот входной файл.
Read the complete LUT workflow and scientific notes.|Vollständigen LUT-Arbeitsablauf und wissenschaftliche Hinweise lesen.|Lire le flux LUT complet et les notes scientifiques.|Leer el flujo LUT completo y las notas científicas.|Ler o fluxo LUT completo e as notas científicas.|Открыть описание LUT и научные примечания.
Send assigned LUTs and shifts to the connected detector setup.|LUTs und Verschiebungen an die verbundene Detektorkonfiguration senden.|Envoyer les LUT et décalages à la configuration du détecteur.|Enviar LUT y desplazamientos a la configuración del detector.|Enviar LUT e deslocamentos à configuração do detector.|Передать LUT и сдвиги подключённой конфигурации детектора.
Select the routing channel to inspect and tune.|Routingkanal zur Prüfung und Anpassung auswählen.|Sélectionner le canal de routage à examiner et régler.|Seleccionar el canal de ruta para examinar y ajustar.|Selecionar o canal de roteamento para examinar e ajustar.|Выбрать канал для просмотра и настройки.
First bin of the flat linear region.|Erster Bin des flachen linearen Bereichs.|Premier bin de la région linéaire plate.|Primer bin de la región lineal plana.|Primeiro bin da região linear plana.|Первый бин плоской линейной области.
First bin after the flat linear region.|Erster Bin nach dem flachen linearen Bereich.|Premier bin après la région linéaire plate.|Primer bin tras la región lineal plana.|Primeiro bin após a região linear plana.|Первый бин после плоской линейной области.
Number of corrected TAC bins.|Anzahl korrigierter TAC-Bins.|Nombre de bins TAC corrigés.|Número de bins TAC corregidos.|Número de bins TAC corrigidos.|Число исправленных бинов TAC.
Offset subtracted from corrected TAC indices.|Von korrigierten TAC-Indizes abgezogener Versatz.|Décalage soustrait des indices TAC corrigés.|Desfase restado de índices TAC corregidos.|Deslocamento subtraído dos índices TAC corrigidos.|Смещение, вычитаемое из исправленных индексов TAC.
Maximum photons used for the corrected preview.|Maximale Photonenzahl für die korrigierte Vorschau.|Nombre maximal de photons pour l'aperçu corrigé.|Máximo de fotones para la vista previa corregida.|Máximo de fótons para a prévia corrigida.|Максимум фотонов исправленного предпросмотра.
Bins below this count are excluded from calibration.|Bins unter dieser Zählzahl werden von der Kalibrierung ausgeschlossen.|Exclure de l'étalonnage les bins sous ce comptage.|Excluir de calibración bins inferiores a esta cuenta.|Excluir da calibração bins abaixo desta contagem.|Исключить из калибровки бины ниже этого порога.
Seed for reproducible stochastic rebinning.|Startwert für reproduzierbare stochastische Umverteilung.|Graine pour un rééchantillonnage stochastique reproductible.|Semilla para redistribución estocástica reproducible.|Semente para redistribuição estocástica reproduzível.|Начальное число для воспроизводимой случайной перегруппировки.
Epsilon used with floor rounding to suppress wrap spikes.|Epsilon bei Abrundung zur Unterdrückung von Überlaufspitzen.|Epsilon d'arrondi inférieur pour supprimer les pics de bouclage.|Épsilon de redondeo inferior para suprimir picos de envoltura.|Épsilon com arredondamento inferior para suprimir picos de retorno.|Эпсилон округления вниз для подавления циклических пиков.
Normalize the displayed histogram by its plateau mean.|Angezeigtes Histogramm mit dem Plateaumittelwert normieren.|Normaliser l'histogramme affiché par la moyenne du plateau.|Normalizar el histograma por la media de su meseta.|Normalizar o histograma pela média do platô.|Нормировать гистограмму по среднему плато.
Use floor rounding and epsilon at the wrap boundary.|Abrundung und Epsilon an der Überlaufgrenze verwenden.|Utiliser l'arrondi inférieur et epsilon au bouclage.|Usar redondeo inferior y épsilon en el límite de envoltura.|Usar arredondamento inferior e épsilon no limite de retorno.|Использовать округление вниз и эпсилон на циклической границе.
Find the flat calibration plateau automatically.|Flaches Kalibrierplateau automatisch finden.|Trouver automatiquement le plateau d'étalonnage.|Encontrar automáticamente la meseta de calibración.|Encontrar automaticamente o platô de calibração.|Автоматически найти плоское плато калибровки.
Compute one LUT per routing channel and assign every result.|Eine LUT pro Routingkanal berechnen und alle Ergebnisse zuweisen.|Calculer une LUT par canal et affecter tous les résultats.|Calcular una LUT por canal y asignar todos los resultados.|Calcular uma LUT por canal e atribuir todos os resultados.|Рассчитать LUT каждого канала и назначить все результаты.
Export the selected channel LUT as JSON, NumPy, CSV or text.|LUT des ausgewählten Kanals als JSON, NumPy, CSV oder Text exportieren.|Exporter la LUT du canal en JSON, NumPy, CSV ou texte.|Exportar la LUT del canal como JSON, NumPy, CSV o texto.|Exportar a LUT do canal como JSON, NumPy, CSV ou texto.|Экспортировать LUT канала в JSON, NumPy, CSV или текст.
Export corrected microtimes for all selected-channel photons.|Korrigierte Mikrozeiten aller Photonen des gewählten Kanals exportieren.|Exporter les microtemps corrigés de tous les photons du canal.|Exportar microtiempos corregidos de todos los fotones del canal.|Exportar microtempos corrigidos de todos os fótons do canal.|Экспортировать исправленное микровремя всех фотонов канала.
Select the TTTR container format; Auto detects it from the file.|TTTR-Containerformat wählen; Auto erkennt es anhand der Datei.|Choisir le format TTTR ; Auto le détecte dans le fichier.|Elegir formato TTTR; Auto lo detecta del archivo.|Escolher formato TTTR; Auto detecta pelo arquivo.|Выбрать формат TTTR; Авто определяет его по файлу.
Import a cumulative LUT from JSON, NumPy, CSV or text.|Kumulative LUT aus JSON, NumPy, CSV oder Text importieren.|Importer une LUT cumulative depuis JSON, NumPy, CSV ou texte.|Importar LUT acumulada de JSON, NumPy, CSV o texto.|Importar LUT acumulada de JSON, NumPy, CSV ou texto.|Импортировать накопленную LUT из JSON, NumPy, CSV или текста.
Remove all loaded and assigned LUTs; retain shifts.|Alle geladenen und zugewiesenen LUTs entfernen; Verschiebungen behalten.|Supprimer toutes les LUT ; conserver les décalages.|Eliminar todas las LUT; conservar desplazamientos.|Remover todas as LUT; manter deslocamentos.|Удалить все LUT, сохранив сдвиги.
Select the LUT to assign to a channel.|Dem Kanal zuzuweisende LUT auswählen.|Sélectionner la LUT à affecter à un canal.|Seleccionar LUT para asignar a un canal.|Selecionar LUT para atribuir a um canal.|Выбрать LUT для назначения каналу.
Remove this LUT from the import list; retain assignments.|Diese LUT aus der Importliste entfernen; Zuweisungen behalten.|Retirer cette LUT de la liste ; conserver les affectations.|Eliminar LUT de la lista; conservar asignaciones.|Remover LUT da lista; manter atribuições.|Удалить LUT из списка, сохранив назначения.
Assign the selected LUT to the active routing channel.|Ausgewählte LUT dem aktiven Routingkanal zuweisen.|Affecter la LUT au canal de routage actif.|Asignar LUT al canal de ruta activo.|Atribuir LUT ao canal de roteamento ativo.|Назначить LUT активному каналу.
Assign the selected LUT to every routing channel in the preview.|Ausgewählte LUT jedem Routingkanal der Vorschau zuweisen.|Affecter la LUT à chaque canal de l'aperçu.|Asignar LUT a cada canal de la vista previa.|Atribuir LUT a cada canal da prévia.|Назначить LUT каждому каналу предпросмотра.
Show or hide this routing channel histogram.|Histogramm dieses Routingkanals anzeigen oder ausblenden.|Afficher ou masquer l'histogramme de ce canal.|Mostrar u ocultar el histograma de este canal.|Mostrar ou ocultar o histograma deste canal.|Показать или скрыть гистограмму канала.
Select the active channel for shifts and LUT inspection.|Aktiven Kanal für Verschiebungen und LUT-Prüfung auswählen.|Sélectionner le canal actif pour les décalages et la LUT.|Elegir canal activo para desplazamientos e inspección LUT.|Escolher canal ativo para deslocamentos e inspeção LUT.|Выбрать активный канал для сдвигов и просмотра LUT.
Photon-level shift of the active channel after LUT correction.|Photonenverschiebung des aktiven Kanals nach LUT-Korrektur.|Décalage des photons du canal actif après correction LUT.|Desplazamiento de fotones del canal activo tras corrección LUT.|Deslocamento dos fótons do canal ativo após correção LUT.|Сдвиг фотонов активного канала после коррекции LUT.
Inspect the active channel cumulative LUT and bin increments.|Kumulative LUT und Bin-Inkremente des aktiven Kanals prüfen.|Examiner la LUT cumulative et les incréments du canal actif.|Examinar LUT acumulada e incrementos del canal activo.|Examinar LUT acumulada e incrementos do canal ativo.|Просмотр накопленной LUT и приращений активного канала.
Use a logarithmic histogram count axis.|Logarithmische Zählachse verwenden.|Utiliser un axe de comptage logarithmique.|Usar eje de cuentas logarítmico.|Usar eixo de contagens logarítmico.|Использовать логарифмическую ось отсчётов.
Inspect the portable settings.tttr.json bundle.|Portables settings.tttr.json-Bündel prüfen.|Examiner le fichier portable settings.tttr.json.|Examinar el archivo portátil settings.tttr.json.|Examinar o arquivo portátil settings.tttr.json.|Просмотр переносимого файла settings.tttr.json.
Restore per-channel LUTs, shifts and reading routine.|Kanal-LUTs, Verschiebungen und Leseformat wiederherstellen.|Restaurer les LUT, décalages et format de lecture.|Restaurar LUT, desplazamientos y formato de lectura.|Restaurar LUT, deslocamentos e formato de leitura.|Восстановить LUT каналов, сдвиги и формат чтения.
Save the portable TTTR correction settings.|Portable TTTR-Korrektureinstellungen speichern.|Enregistrer les paramètres portables de correction TTTR.|Guardar ajustes portátiles de corrección TTTR.|Salvar configurações portáteis de correção TTTR.|Сохранить переносимые настройки коррекции TTTR.
"""


def install():
    install_chisurf()
    for row in _ROWS.strip().splitlines():
        source, *values = row.split("|")
        if len(values) != 5:
            raise ValueError(f"Invalid LUT translation: {source}")
        for locale, value in zip(("de", "fr", "es", "pt", "ru"), values):
            i18n.add_translations(locale, {source: value}, context="LutTools")


def tr(text):
    return i18n.tr(text, context="LutTools")
