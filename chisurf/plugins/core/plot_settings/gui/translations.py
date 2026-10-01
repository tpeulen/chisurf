"""Labels and help text for the six ChiSurf interface locales."""

from emtk import i18n

LOCALES = ("en", "de", "fr", "es", "pt", "ru")

# Every native control uses one of these stable English identities. Tooltip
# messages are kept here too, so changing locale covers help as well as labels.
ROWS = '''Plot Settings|Diagrammeinstellungen|Paramètres des graphiques|Ajustes de gráficos|Configurações de gráficos|Настройки графиков
Rendering Backend|Render-Backend|Moteur de rendu|Motor de renderizado|Motor de renderização|Движок отрисовки
Active backend|Aktives Backend|Moteur actif|Motor activo|Motor ativo|Активный движок
Colors|Farben|Couleurs|Colores|Cores|Цвета
Data curve|Datenkurve|Courbe de données|Curva de datos|Curva de dados|Кривая данных
Model curve|Modellkurve|Courbe du modèle|Curva del modelo|Curva do modelo|Кривая модели
Instrument response|Instrumentenantwort|Réponse instrumentale|Respuesta instrumental|Resposta instrumental|Отклик прибора
Residuals|Residuen|Résidus|Residuos|Resíduos|Остатки
Autocorrelation|Autokorrelation|Autocorrélation|Autocorrelación|Autocorrelação|Автокорреляция
Region selector|Bereichsauswahl|Sélection de plage|Selector de región|Seletor de região|Выбор области
Region alpha|Bereichsdeckkraft|Opacité de la plage|Opacidad de región|Opacidade da região|Прозрачность области
Active transparency|Aktive Transparenz|Transparence active|Transparencia activa|Transparência ativa|Активная прозрачность
Inactive transparency|Inaktive Transparenz|Transparence inactive|Transparencia inactiva|Transparência inativa|Неактивная прозрачность
Appearance|Darstellung|Apparence|Apariencia|Aparência|Внешний вид
Line width|Linienbreite|Épaisseur du trait|Grosor de línea|Espessura da linha|Толщина линии
Axis font size|Achsen-Schriftgröße|Taille des axes|Tamaño de fuente de ejes|Tamanho da fonte dos eixos|Размер шрифта осей
Enable grid|Raster aktivieren|Afficher la grille|Activar cuadrícula|Ativar grade|Показать сетку
Grid opacity|Rasterdeckkraft|Opacité de la grille|Opacidad de cuadrícula|Opacidade da grade|Непрозрачность сетки
Grid on data panel|Raster im Datenfeld|Grille des données|Cuadrícula de datos|Grade dos dados|Сетка данных
Grid on residuals|Raster bei Residuen|Grille des résidus|Cuadrícula de residuos|Grade dos resíduos|Сетка остатков
Grid on autocorrelation|Raster bei Autokorrelation|Grille d’autocorrélation|Cuadrícula de autocorrelación|Grade da autocorrelação|Сетка автокорреляции
Fit-range selector|Anpassungsbereich|Sélecteur de plage d’ajustement|Selector de rango de ajuste|Seletor do intervalo de ajuste|Выбор диапазона подгонки
Show legend by default|Legende standardmäßig anzeigen|Afficher la légende|Mostrar leyenda|Mostrar legenda|Показывать легенду
Hide titles|Titel ausblenden|Masquer les titres|Ocultar títulos|Ocultar títulos|Скрыть заголовки
Label axes|Achsen beschriften|Nommer les axes|Etiquetar ejes|Rotular eixos|Подписать оси
Advanced: pyqtgraph Configuration|Erweitert: pyqtgraph|Avancé : pyqtgraph|Avanzado: pyqtgraph|Avançado: pyqtgraph|Дополнительно: pyqtgraph
Antialiasing|Kantenglättung|Anticrénelage|Suavizado|Suavização|Сглаживание
Left button pans|Linke Taste verschiebt|Déplacement avec clic gauche|Desplazar con botón izquierdo|Mover com botão esquerdo|Перемещение левой кнопкой
Background|Hintergrund|Arrière-plan|Fondo|Fundo|Фон
Foreground|Vordergrund|Premier plan|Primer plano|Primeiro plano|Передний план
Preview|Vorschau|Aperçu|Vista previa|Prévia|Предпросмотр
Apply|Anwenden|Appliquer|Aplicar|Aplicar|Применить
Save|Speichern|Enregistrer|Guardar|Salvar|Сохранить
Reset|Zurücksetzen|Réinitialiser|Restablecer|Redefinir|Сбросить
Changes apply on next application start or when a new plot is created.|Änderungen gelten beim nächsten Start oder für neue Diagramme.|Les changements prennent effet au prochain démarrage ou nouveau graphique.|Los cambios se aplican al reiniciar o crear un gráfico.|As mudanças valem no próximo início ou novo gráfico.|Изменения применятся при новом запуске или создании графика.
Choose the rendering engine for new plots.|Render-Engine für neue Diagramme wählen.|Choisir le moteur des nouveaux graphiques.|Elegir el motor para gráficos nuevos.|Escolher o motor para novos gráficos.|Выбрать движок для новых графиков.
Choose the color used for this plot element.|Farbe dieses Diagrammelements wählen.|Choisir la couleur de cet élément.|Elegir el color de este elemento.|Escolher a cor deste elemento.|Выбрать цвет элемента графика.
Set the fit-range band opacity from 0 to 255.|Deckkraft des Anpassungsbereichs von 0 bis 255 festlegen.|Régler l’opacité de la plage de 0 à 255.|Ajustar opacidad del rango de 0 a 255.|Ajustar opacidade da faixa de 0 a 255.|Задать непрозрачность области от 0 до 255.
Set the transparency of active traces.|Transparenz aktiver Kurven festlegen.|Régler la transparence des courbes actives.|Ajustar transparencia de curvas activas.|Ajustar transparência de curvas ativas.|Задать прозрачность активных кривых.
Set the transparency of inactive traces.|Transparenz inaktiver Kurven festlegen.|Régler la transparence des courbes inactives.|Ajustar transparencia de curvas inactivas.|Ajustar transparência de curvas inativas.|Задать прозрачность неактивных кривых.
Set the width of newly drawn curves.|Breite neuer Kurven festlegen.|Régler l’épaisseur des nouvelles courbes.|Ajustar grosor de curvas nuevas.|Ajustar espessura das novas curvas.|Задать толщину новых кривых.
Set axis font size; zero follows the application font.|Achsen-Schriftgröße festlegen; null folgt der Anwendung.|Taille des axes ; zéro suit la police de l’application.|Tamaño de ejes; cero usa la fuente de la aplicación.|Tamanho dos eixos; zero usa a fonte do aplicativo.|Размер осей; ноль использует шрифт приложения.
Show grid lines on enabled panels.|Raster auf aktivierten Feldern anzeigen.|Afficher la grille dans les panneaux activés.|Mostrar cuadrícula en paneles activados.|Mostrar grade nos painéis ativos.|Показать сетку на выбранных панелях.
Set grid opacity from zero to full.|Deckkraft des Rasters festlegen.|Régler l’opacité de la grille.|Ajustar opacidad de cuadrícula.|Ajustar opacidade da grade.|Задать непрозрачность сетки.
Show grid on the data panel.|Raster im Datenfeld anzeigen.|Afficher la grille des données.|Mostrar cuadrícula de datos.|Mostrar grade dos dados.|Показать сетку данных.
Show grid on the residual panel.|Raster im Residuenfeld anzeigen.|Afficher la grille des résidus.|Mostrar cuadrícula de residuos.|Mostrar grade dos resíduos.|Показать сетку остатков.
Show grid on the autocorrelation panel.|Raster im Autokorrelationsfeld anzeigen.|Afficher la grille d’autocorrélation.|Mostrar cuadrícula de autocorrelación.|Mostrar grade da autocorrelação.|Показать сетку автокорреляции.
Draw the draggable fit-range band on the data panel.|Verschiebbaren Anpassungsbereich anzeigen.|Afficher la plage d’ajustement déplaçable.|Mostrar rango de ajuste arrastrable.|Mostrar faixa de ajuste arrastável.|Показать перемещаемую область подгонки.
Show legends on new plots.|Legenden auf neuen Diagrammen anzeigen.|Afficher les légendes des nouveaux graphiques.|Mostrar leyendas en gráficos nuevos.|Mostrar legendas em novos gráficos.|Показать легенды новых графиков.
Hide plot titles.|Diagrammtitel ausblenden.|Masquer les titres des graphiques.|Ocultar títulos de gráficos.|Ocultar títulos dos gráficos.|Скрыть заголовки графиков.
Show axis names and units.|Achsenname und Einheit anzeigen.|Afficher les noms et unités des axes.|Mostrar nombres y unidades de ejes.|Mostrar nomes e unidades dos eixos.|Показать названия и единицы осей.
Smooth pyqtgraph lines.|pyqtgraph-Linien glätten.|Lisser les lignes pyqtgraph.|Suavizar líneas pyqtgraph.|Suavizar linhas pyqtgraph.|Сгладить линии pyqtgraph.
Pan pyqtgraph plots with the left mouse button.|pyqtgraph mit linker Maustaste verschieben.|Déplacer avec le bouton gauche.|Desplazar con botón izquierdo.|Mover com botão esquerdo.|Перемещать левой кнопкой.
Choose the pyqtgraph canvas background.|pyqtgraph-Hintergrund wählen.|Choisir le fond pyqtgraph.|Elegir fondo de pyqtgraph.|Escolher fundo do pyqtgraph.|Выбрать фон pyqtgraph.
Choose contrasting axis and tick color.|Kontrastfarbe für Achsen wählen.|Choisir une couleur contrastée pour les axes.|Elegir color de contraste para ejes.|Escolher cor contrastante dos eixos.|Выбрать контрастный цвет осей.
Apply the current values to this session.|Aktuelle Werte in dieser Sitzung anwenden.|Appliquer les valeurs à cette session.|Aplicar valores a esta sesión.|Aplicar valores a esta sessão.|Применить значения в сеансе.
Save plot settings to the settings file.|Diagrammeinstellungen in der Datei speichern.|Enregistrer les paramètres dans le fichier.|Guardar ajustes en el archivo.|Salvar configurações no arquivo.|Сохранить настройки графика в файл.
Reload plot settings from the settings file.|Diagrammeinstellungen aus der Datei laden.|Recharger les paramètres du fichier.|Recargar ajustes desde el archivo.|Recarregar configurações do arquivo.|Загрузить настройки графика из файла.
Sample data, model and instrument response using the selected colors.|Beispiel für Daten, Modell und Instrumentenantwort in gewählten Farben.|Données, modèle et réponse instrumentale avec les couleurs choisies.|Datos, modelo y respuesta instrumental con colores elegidos.|Dados, modelo e resposta instrumental nas cores escolhidas.|Пример данных, модели и отклика прибора в выбранных цветах.'''

TRANSLATIONS = {locale: {} for locale in LOCALES}
for line in ROWS.splitlines():
    values = line.split("|")
    if len(values) != len(LOCALES):
        raise ValueError(f"Incomplete plot-settings translation: {values[0]}")
    for locale, value in zip(LOCALES, values):
        TRANSLATIONS[locale][values[0]] = value


def install():
    for locale, mapping in TRANSLATIONS.items():
        i18n.add_translations(locale, mapping)


def tr(message):
    return i18n.tr(message)
