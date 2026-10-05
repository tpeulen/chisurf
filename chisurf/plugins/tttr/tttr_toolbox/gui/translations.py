"""Native toolbox additions for the six existing ChiSurf locales."""

from emtk.i18n import add_translations

ROWS = """TTTR Tools|TTTR-Werkzeuge|Outils TTTR|Herramientas TTTR|Ferramentas TTTR|Инструменты TTTR
Tool help|Werkzeughilfe|Aide de l’outil|Ayuda de la herramienta|Ajuda da ferramenta|Справка инструмента
Search…|Suchen…|Rechercher…|Buscar…|Pesquisar…|Поиск…
No matching tools.|Keine passenden Werkzeuge.|Aucun outil correspondant.|No hay herramientas coincidentes.|Nenhuma ferramenta correspondente.|Подходящие инструменты не найдены.
The selected tool could not be opened.|Das ausgewählte Werkzeug konnte nicht geöffnet werden.|Impossible d’ouvrir l’outil sélectionné.|No se pudo abrir la herramienta seleccionada.|Não foi possível abrir a ferramenta selecionada.|Не удалось открыть выбранный инструмент.
This tool has no native EMTK factory yet.|Dieses Werkzeug hat noch keine native EMTK-Oberfläche.|Cet outil n’a pas encore d’interface EMTK native.|Esta herramienta aún no tiene interfaz EMTK nativa.|Esta ferramenta ainda não tem interface EMTK nativa.|У этого инструмента пока нет собственного интерфейса EMTK.
Retry|Erneut versuchen|Réessayer|Reintentar|Tentar novamente|Повторить
Read the TTTR toolbox reference and photon-clock guidance.|TTTR-Hilfe und Erläuterungen der Photonenzeit lesen.|Lire la référence TTTR et les explications des horloges photoniques.|Leer la referencia TTTR y la guía de los tiempos de fotones.|Ler a referência TTTR e o guia dos relógios dos fótons.|Читать справку TTTR и руководство по времени фотонов.
Walk through the original TTTR tools and their workflows.|Die TTTR-Werkzeuge und Arbeitsabläufe kennenlernen.|Découvrir les outils TTTR et leurs flux de travail.|Recorrer las herramientas TTTR y sus flujos de trabajo.|Conhecer as ferramentas TTTR e seus fluxos de trabalho.|Обзор инструментов TTTR и рабочих процессов.
Find tools by name, description or route.|Werkzeuge nach Name, Beschreibung oder Route finden.|Rechercher les outils par nom, description ou destination.|Buscar herramientas por nombre, descripción o ruta.|Encontrar ferramentas por nome, descrição ou rota.|Поиск инструментов по имени, описанию или маршруту.
Read help for the selected TTTR tool.|Hilfe für das ausgewählte TTTR-Werkzeug lesen.|Lire l’aide de l’outil TTTR sélectionné.|Leer la ayuda de la herramienta TTTR seleccionada.|Ler a ajuda da ferramenta TTTR selecionada.|Читать справку выбранного инструмента TTTR.
Resolve this tool's current manifest again and retry its native factory.|Aktuelles Manifest erneut lesen und native Oberfläche laden.|Relire le manifeste actuel et réessayer l’interface native.|Volver a leer el manifiesto actual y abrir la interfaz nativa.|Reler o manifesto atual e tentar abrir a interface nativa.|Перечитать текущий манифест и повторить запуск интерфейса.
Native route not yet available.|Native Route noch nicht verfügbar.|Destination native encore indisponible.|Ruta nativa aún no disponible.|Rota nativa ainda não disponível.|Собственный маршрут пока недоступен.
Photon Table|Photonentabelle|Table des photons|Tabla de fotones|Tabela de fótons|Таблица фотонов
Inspect the photons of a TTTR file in a table: routing channel, micro-time and macro-time, one row per photon.|Die Photonen einer TTTR-Datei als Tabelle untersuchen: Routing-Kanal, Mikro- und Makrozeit, eine Zeile pro Photon.|Examiner les photons d’un fichier TTTR dans un tableau : canal, microtemps et macrotemps, une ligne par photon.|Inspeccionar los fotones de un archivo TTTR en una tabla: canal, microtiempo y macrotiempo, una fila por fotón.|Inspecionar os fótons de um arquivo TTTR em uma tabela: canal, microtempo e macrotempo, uma linha por fóton.|Просмотр фотонов TTTR-файла в таблице: канал, микро- и макровремя, одна строка на фотон.
Audifier|Audifier|Sonification|Sonificación|Sonificação|Озвучивание
TTTR Header Editor|TTTR-Kopfzeileneditor|Éditeur d’en-tête TTTR|Editor de cabecera TTTR|Editor de cabeçalho TTTR|Редактор заголовка TTTR
Convert ALEX macro-time modulation into micro-time so ALEX data runs through PIE pipelines.|ALEX-Makrozeitmodulation in Mikrozeit umwandeln, um ALEX-Daten mit PIE auszuwerten.|Convertir la modulation macrotemporelle ALEX en microtemps pour les traitements PIE.|Convertir la modulación de macrotiempo ALEX en microtiempo para procesarla con PIE.|Converter a modulação de macrotempo ALEX em microtempo para os fluxos PIE.|Преобразовать модуляцию макровремени ALEX в микровремя для обработки PIE.
Apply global and per-channel micro-time shifts to TTTR files.|Globale und kanalweise Mikrozeitverschiebungen auf TTTR-Dateien anwenden.|Appliquer des décalages de microtemps globaux ou par canal aux fichiers TTTR.|Aplicar desplazamientos de microtiempo globales y por canal a archivos TTTR.|Aplicar deslocamentos de microtempo globais e por canal a arquivos TTTR.|Применить общие и поканальные сдвиги микровремени к файлам TTTR.
View, edit, add and remove header tags in TTTR files (PTU/HT3/SPC/HDF5); saves as PTU.|Kopfzeilentags in TTTR-Dateien (PTU/HT3/SPC/HDF5) anzeigen, bearbeiten, hinzufügen und entfernen; als PTU speichern.|Afficher, modifier, ajouter et supprimer les tags TTTR (PTU/HT3/SPC/HDF5) ; enregistrer en PTU.|Ver, editar, añadir y eliminar etiquetas TTTR (PTU/HT3/SPC/HDF5); guardar en PTU.|Ver, editar, adicionar e remover tags TTTR (PTU/HT3/SPC/HDF5); salvar como PTU.|Просмотр, изменение, добавление и удаление тегов TTTR (PTU/HT3/SPC/HDF5); сохранение PTU.
Split large TTTR files into segments and convert between container formats.|Große TTTR-Dateien in Segmente teilen und Containerformate konvertieren.|Découper les grands fichiers TTTR et convertir les formats de conteneur.|Dividir archivos TTTR grandes en segmentos y convertir formatos.|Dividir arquivos TTTR grandes em segmentos e converter formatos.|Разделить большие файлы TTTR на сегменты и преобразовать форматы контейнеров.
Count rates per detector channel across many TTTR files, with mean/std and a per-file plot.|Zählraten je Detektorkanal über viele TTTR-Dateien mit Mittelwert, Standardabweichung und Einzeldateidiagramm.|Débits par détecteur sur plusieurs fichiers TTTR, avec moyenne, écart type et graphique par fichier.|Tasas por detector de varios archivos TTTR, con media, desviación y gráfico por archivo.|Taxas por detector de vários arquivos TTTR, com média, desvio e gráfico por arquivo.|Частоты счёта по детекторам в нескольких TTTR-файлах, среднее, отклонение и график каждого файла.
Convert TTTR photon streams to audio, with a live micro-time / lifetime waterfall preview.|TTTR-Photonenströme in Audio umwandeln, mit laufender Mikrozeit-/Lebensdauer-Wasserfallvorschau.|Convertir les photons TTTR en audio, avec aperçu en cascade des microtemps et durées de vie.|Convertir fotones TTTR en audio, con vista en cascada de microtiempo y tiempo de vida.|Converter fótons TTTR em áudio, com prévia em cascata de microtempo e tempo de vida.|Озвучить поток фотонов TTTR с текущей каскадной диаграммой микровремени и времени жизни.
Ready|Bereit|Prêt|Listo|Pronto|Готово
Back|Zurück|Retour|Atrás|Voltar|Назад
Next|Weiter|Suivant|Siguiente|Avançar|Далее
Go to the previous tool in the list.|Zum vorherigen Werkzeug der Liste gehen.|Aller à l’outil précédent de la liste.|Ir a la herramienta anterior de la lista.|Ir para a ferramenta anterior da lista.|Перейти к предыдущему инструменту списка.
Go to the next tool in the list.|Zum nächsten Werkzeug der Liste gehen.|Aller à l’outil suivant de la liste.|Ir a la siguiente herramienta de la lista.|Ir para a próxima ferramenta da lista.|Перейти к следующему инструменту списка.
ALEX Creator|ALEX-Ersteller|Créateur ALEX|Creador ALEX|Criador ALEX|Создатель ALEX
Count Rate Analysis|Zählratenanalyse|Analyse des taux de comptage|Análisis de tasas de recuento|Análise de taxas de contagem|Анализ скоростей счёта
Micro-time Shifter|Mikrozeit-Verschieber|Décaleur de microtemps|Desplazador de microtiempo|Deslocador de microtempo|Сдвиг микровремени
Split / Convert|Teilen / Konvertieren|Découper / Convertir|Dividir / Convertir|Dividir / Converter|Разделить / Преобразовать"""


def install_translations():
    rows = [line.split("|") for line in ROWS.splitlines()]
    for index, locale in enumerate(("en", "de", "fr", "es", "pt", "ru")):
        add_translations(locale, {row[0]: row[index] for row in rows})
