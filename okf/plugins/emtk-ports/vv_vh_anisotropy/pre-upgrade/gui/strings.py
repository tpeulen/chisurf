"""Six-locale labels and tooltips for the native calculator."""

from emtk import i18n

LANGUAGES = ("en", "de", "fr", "es", "pt", "ru")
_ROWS = """
VV/VH anisotropy|VV/VH-Anisotropie|Anisotropie VV/VH|Anisotropía VV/VH|Anisotropia VV/VH|Анизотропия VV/VH
No file loaded|Keine Datei geladen|Aucun fichier chargé|Ningún archivo cargado|Nenhum arquivo carregado|Файл не загружен
VV/VH Anisotropy Decay is deprecated/obsolete. Use the VV/VH G-Factor plugin and reader-integrated anisotropy workflow instead.|VV/VH-Anisotropiezerfall ist veraltet. Stattdessen den VV/VH-G-Faktor und den integrierten Anisotropieablauf verwenden.|Le calcul de l’anisotropie VV/VH est obsolète. Utilisez le facteur G VV/VH et l’analyse intégrée au lecteur.|El cálculo de anisotropía VV/VH está obsoleto. Use el factor G VV/VH y el flujo integrado del lector.|O cálculo de anisotropia VV/VH está obsoleto. Use o fator G VV/VH e o fluxo integrado no leitor.|Расчёт анизотропии VV/VH устарел. Используйте G-фактор VV/VH и встроенный анализ в загрузчике.
Load VV/VH file…|VV/VH-Datei laden…|Charger un fichier VV/VH…|Cargar archivo VV/VH…|Carregar arquivo VV/VH…|Загрузить файл VV/VH…
Load a paired parallel/perpendicular decay.|Gepaarte parallele/senkrechte Zerfälle laden.|Charger les décroissances parallèle et perpendiculaire.|Cargar decaimientos paralelo y perpendicular.|Carregar decaimentos paralelo e perpendicular.|Загрузить параллельный и перпендикулярный спады.
Save outputs…|Ergebnisse speichern…|Enregistrer les résultats…|Guardar resultados…|Salvar resultados…|Сохранить результаты…
Save shifted VV/VH, anisotropy trace and r∞ metadata.|Verschobene VV/VH, Anisotropiekurve und r∞-Metadaten speichern.|Enregistrer VV/VH décalés, trace d’anisotropie et métadonnées r∞.|Guardar VV/VH desplazados, traza de anisotropía y metadatos r∞.|Salvar VV/VH deslocados, curva de anisotropia e metadados r∞.|Сохранить сдвинутые VV/VH, кривую анизотропии и данные r∞.
G-factor|G-Faktor|Facteur G|Factor G|Fator G|G-фактор
Detector sensitivity correction applied to VH.|Detektorempfindlichkeitskorrektur für VH.|Correction de sensibilité du détecteur appliquée à VH.|Corrección de sensibilidad del detector aplicada a VH.|Correção da sensibilidade do detector aplicada a VH.|Коррекция чувствительности детектора для VH.
Apply backgrounds|Untergründe abziehen|Soustraire les fonds|Restar fondos|Subtrair fundos|Вычесть фон
Subtract constant VV and VH backgrounds before calculation.|Konstante VV- und VH-Untergründe vor der Berechnung abziehen.|Soustraire les fonds constants VV et VH avant le calcul.|Restar fondos constantes VV y VH antes del cálculo.|Subtrair fundos constantes VV e VH antes do cálculo.|Вычесть постоянный фон VV и VH перед расчётом.
BG VV|Untergrund VV|Fond VV|Fondo VV|Fundo VV|Фон VV
Constant background to subtract from VV.|Konstanter Untergrund für VV.|Fond constant à soustraire de VV.|Fondo constante que se resta de VV.|Fundo constante subtraído de VV.|Постоянный фон, вычитаемый из VV.
BG VH|Untergrund VH|Fond VH|Fondo VH|Fundo VH|Фон VH
Constant background to subtract from VH.|Konstanter Untergrund für VH.|Fond constant à soustraire de VH.|Fondo constante que se resta de VH.|Fundo constante subtraído de VH.|Постоянный фон, вычитаемый из VH.
Flip VV↔VH|VV↔VH tauschen|Inverser VV↔VH|Intercambiar VV↔VH|Trocar VV↔VH|Поменять VV↔VH
Swap channels when the source file has reversed polarization.|Kanäle bei vertauschter Polarisation in der Datei tauschen.|Inverser les canaux si les polarisations du fichier sont inversées.|Intercambiar canales si la polarización del archivo está invertida.|Trocar canais se a polarização do arquivo estiver invertida.|Поменять каналы, если поляризация в файле перепутана.
Shift VH (channels)|VH verschieben (Kanäle)|Décaler VH (canaux)|Desplazar VH (canales)|Deslocar VH (canais)|Сдвиг VH (каналы)
Shift VH by a fractional channel using interpolation.|VH um einen Bruchteil eines Kanals interpoliert verschieben.|Décaler VH par interpolation d’une fraction de canal.|Desplazar VH una fracción de canal por interpolación.|Deslocar VH por fração de canal usando interpolação.|Сдвинуть VH на долю канала интерполяцией.
Region start|Bereichsanfang|Début de région|Inicio de región|Início da região|Начало области
First channel in the r∞ averaging region.|Erster Kanal des r∞-Mittelungsbereichs.|Premier canal de la région de moyenne r∞.|Primer canal de la región para promediar r∞.|Primeiro canal da região média de r∞.|Первый канал области усреднения r∞.
Region end|Bereichsende|Fin de région|Fin de región|Fim da região|Конец области
Last boundary of the r∞ averaging region.|Letzte Grenze des r∞-Mittelungsbereichs.|Dernière limite de la région de moyenne r∞.|Límite final de la región para promediar r∞.|Limite final da região média de r∞.|Конечная граница области усреднения r∞.
Batch files|Batch-Dateien|Fichiers du lot|Archivos por lote|Arquivos em lote|Пакетные файлы
Close batch|Batch schließen|Fermer le lot|Cerrar lote|Fechar lote|Закрыть пакет
Close the batch panel and retain its queued files and results.|Batch-Fenster schließen; Dateien und Ergebnisse behalten.|Fermer le lot et conserver les fichiers et résultats.|Cerrar el lote y conservar archivos y resultados.|Fechar o lote mantendo arquivos e resultados.|Закрыть панель, сохранив файлы и результаты.
Add batch files…|Batch-Dateien hinzufügen…|Ajouter des fichiers au lot…|Añadir archivos al lote…|Adicionar arquivos ao lote…|Добавить файлы в пакет…
Queue VV/VH decays for the same current settings.|VV/VH-Zerfälle für die aktuellen Einstellungen einreihen.|Ajouter des décroissances VV/VH avec les paramètres actuels.|Añadir decaimientos VV/VH con los ajustes actuales.|Adicionar decaimentos VV/VH com as configurações atuais.|Добавить спады VV/VH с текущими параметрами.
Run batch|Batch starten|Exécuter le lot|Procesar lote|Executar lote|Обработать пакет
Compute r∞ for each queued VV/VH file.|r∞ für jede eingereihte VV/VH-Datei berechnen.|Calculer r∞ pour chaque fichier VV/VH du lot.|Calcular r∞ para cada archivo VV/VH del lote.|Calcular r∞ para cada arquivo VV/VH do lote.|Вычислить r∞ для каждого файла VV/VH.
Save batch CSV…|Batch-CSV speichern…|Enregistrer le CSV du lot…|Guardar CSV del lote…|Salvar CSV do lote…|Сохранить CSV пакета…
Export filenames, r∞, settings and per-file errors.|Dateinamen, r∞, Einstellungen und Dateifehler exportieren.|Exporter les noms, r∞, paramètres et erreurs par fichier.|Exportar nombres, r∞, ajustes y errores por archivo.|Exportar nomes, r∞, configurações e erros por arquivo.|Экспортировать имена, r∞, настройки и ошибки файлов.
Decays (VV, VH)|Zerfälle (VV, VH)|Décroissances (VV, VH)|Decaimientos (VV, VH)|Decaimentos (VV, VH)|Спады (VV, VH)
Anisotropy r(t)|Anisotropie r(t)|Anisotropie r(t)|Anisotropía r(t)|Anisotropia r(t)|Анизотропия r(t)
Channel|Kanal|Canal|Canal|Canal|Канал
Intensity|Intensität|Intensité|Intensidad|Intensidade|Интенсивность
Drag the green lines to choose the r∞ region.|Grüne Linien ziehen, um den r∞-Bereich zu wählen.|Déplacer les lignes vertes pour choisir la région r∞.|Arrastrar líneas verdes para elegir la región r∞.|Arrastar linhas verdes para escolher a região r∞.|Перетащите зелёные линии для выбора области r∞.
Background-corrected VV and shifted VH on a logarithmic intensity scale.|Untergrundkorrigiertes VV und verschobenes VH auf logarithmischer Intensitätsskala.|VV corrigé du fond et VH décalé sur une échelle logarithmique.|VV corregido de fondo y VH desplazado en escala logarítmica.|VV corrigido do fundo e VH deslocado em escala logarítmica.|VV с вычетом фона и сдвинутый VH в логарифмической шкале.
"""
TRANSLATIONS = {row[0]: dict(zip(LANGUAGES, row)) for row in
                (line.split("|") for line in _ROWS.strip().splitlines())}


def tr(source):
    locale = i18n.get_locale().split("_")[0].split("-")[0]
    return TRANSLATIONS.get(source, {}).get(locale, source)
