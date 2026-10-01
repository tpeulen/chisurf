"""Plugin labels and control hints in all existing ChiSurf languages."""
from emtk import i18n

_CONTEXT = 'PtoInspector'
# English source identity is retained in saved state and scientific metadata.
_LABELS = {
'de': ['Container','Provenienz','Daten','Kurve','Details','Abstammung','Parameter','Text','Öffnen','Neu laden','Prüfen','Exportieren','Hilfe','Anleitung','Graph einpassen','Werkzeug öffnen','Zurück zum Inspektor','Fehler','Exportiert'],
'fr': ['Conteneur','Provenance','Données','Courbe','Détails','Lignée','Paramètres','Texte','Ouvrir','Recharger','Vérifier','Exporter','Aide','Guide','Ajuster le graphe','Ouvrir l’outil','Retour à l’inspecteur','Erreur','Exporté'],
'es': ['Contenedor','Procedencia','Datos','Curva','Detalles','Linaje','Parámetros','Texto','Abrir','Recargar','Verificar','Exportar','Ayuda','Guía','Ajustar grafo','Abrir herramienta','Volver al inspector','Error','Exportado'],
'pt': ['Contentor','Proveniência','Dados','Curva','Detalhes','Linhagem','Parâmetros','Texto','Abrir','Recarregar','Verificar','Exportar','Ajuda','Guia','Ajustar grafo','Abrir ferramenta','Voltar ao inspetor','Erro','Exportado'],
'ru': ['Контейнер','Происхождение','Данные','Кривая','Подробности','Цепочка','Параметры','Текст','Открыть','Перезагрузить','Проверить','Экспорт','Справка','Руководство','Вписать граф','Открыть инструмент','Назад к инспектору','Ошибка','Экспортировано'],
}
_SOURCES = ['Container','Provenance','Data','Curve','Details','Lineage','Parameters','Text','Open','Reload','Verify','Export','Help','Guide','Fit graph','Open tool','Back to inspector','Error','Exported']
_HINTS = {
'Open a photon container.': ['Photonencontainer öffnen.','Ouvrir un conteneur de photons.','Abrir un contenedor de fotones.','Abrir um contentor de fotões.','Открыть фотонный контейнер.'],
'Read changes from disk.': ['Änderungen von der Festplatte lesen.','Lire les modifications du disque.','Leer los cambios del disco.','Ler as alterações do disco.','Прочитать изменения с диска.'],
'Check every stored checksum.': ['Alle gespeicherten Prüfsummen prüfen.','Vérifier toutes les sommes de contrôle.','Verificar todas las sumas de comprobación.','Verificar todas as somas de controlo.','Проверить все сохранённые контрольные суммы.'],
'Export the selected payload.': ['Ausgewählte Nutzdaten exportieren.','Exporter les données sélectionnées.','Exportar los datos seleccionados.','Exportar os dados selecionados.','Экспортировать выбранные данные.'],
'Read the inspector help.': ['Hilfe zum Inspektor lesen.','Lire l’aide de l’inspecteur.','Leer la ayuda del inspector.','Ler a ajuda do inspetor.','Открыть справку инспектора.'],
'Start the guided tour.': ['Schrittweise Anleitung starten.','Démarrer la visite guidée.','Iniciar la visita guiada.','Iniciar a visita guiada.','Начать пошаговое руководство.'],
'Frame all provenance nodes.': ['Alle Provenienzknoten einpassen.','Afficher tous les nœuds de provenance.','Mostrar todos los nodos de procedencia.','Mostrar todos os nós de proveniência.','Вписать все узлы происхождения.'],
'Open the native tool for this operation.': ['EMTK-Werkzeug für diesen Vorgang öffnen.','Ouvrir l’outil EMTK de cette opération.','Abrir la herramienta EMTK de esta operación.','Abrir a ferramenta EMTK desta operação.','Открыть инструмент EMTK для этой операции.'],
'Choose the tool to open.': ['Zu öffnendes Werkzeug auswählen.','Choisir l’outil à ouvrir.','Elegir la herramienta que abrir.','Escolher a ferramenta a abrir.','Выбрать инструмент для открытия.'],
'Container path.': ['Pfad zum Container.','Chemin du conteneur.','Ruta del contenedor.','Caminho do contentor.','Путь к контейнеру.'],
'Select an artifact.': ['Artefakt auswählen.','Sélectionner un artefact.','Seleccionar un artefacto.','Selecionar um artefacto.','Выберите артефакт.'],
'The selected artifact is not a table.': ['Das Artefakt ist keine Tabelle.','L’artefact sélectionné n’est pas un tableau.','El artefacto seleccionado no es una tabla.','O artefacto selecionado não é uma tabela.','Выбранный артефакт не является таблицей.'],
'The selected artifact is not a curve.': ['Das Artefakt ist keine Kurve.','L’artefact sélectionné n’est pas une courbe.','El artefacto seleccionado no es una curva.','O artefacto selecionado não é uma curva.','Выбранный артефакт не является кривой.'],
'No settings recorded.': ['Keine Einstellungen gespeichert.','Aucun paramètre enregistré.','No hay parámetros registrados.','Sem parâmetros registados.','Параметры не записаны.'],
'No text payload.': ['Keine Textdaten.','Aucune donnée textuelle.','Sin datos de texto.','Sem dados de texto.','Текстовых данных нет.'],
'No tool for this operation.': ['Kein Werkzeug für diesen Vorgang.','Aucun outil pour cette opération.','No hay herramienta para esta operación.','Sem ferramenta para esta operação.','Нет инструмента для этой операции.'],
'This tool has not been ported to EMTK yet.': ['Dieses Werkzeug wurde noch nicht auf EMTK portiert.','Cet outil n’a pas encore été porté vers EMTK.','Esta herramienta aún no se ha adaptado a EMTK.','Esta ferramenta ainda não foi portada para EMTK.','Этот инструмент ещё не перенесён на EMTK.'],
'Stored curve; axes include units.': ['Gespeicherte Kurve; Achsen mit Einheiten.','Courbe enregistrée ; axes avec unités.','Curva almacenada; ejes con unidades.','Curva armazenada; eixos com unidades.','Сохранённая кривая; оси с единицами.'],
'Return to the container without closing the tool.': ['Zum Container zurückkehren.','Revenir au conteneur.','Volver al contenedor.','Voltar ao contentor.','Вернуться к контейнеру.'],
'Select a node; double-click to open its tool. Alt-drag pans; wheel zooms.': ['Knoten auswählen; Doppelklick öffnet das Werkzeug. Alt-Ziehen verschiebt, Mausrad zoomt.','Sélectionner un nœud ; double-clic pour ouvrir l’outil. Alt-glisser déplace ; molette zoome.','Seleccionar nodo; doble clic abre la herramienta. Alt-arrastrar desplaza; rueda amplía.','Selecionar nó; duplo clique abre a ferramenta. Alt-arrastar desloca; roda amplia.','Выберите узел; двойной щелчок открывает инструмент. Alt-перетаскивание перемещает; колесо масштабирует.'],
}

_HEADERS = {
'Name': ['Name','Nom','Nombre','Nome','Имя'],
'Kind': ['Art','Type','Tipo','Tipo','Тип'],
'Operation': ['Vorgang','Opération','Operación','Operação','Операция'],
'Grain': ['Zeilengranularität','Granularité','Granularidad','Granularidade','Гранулярность'],
'Rows': ['Zeilen','Lignes','Filas','Linhas','Строки'],
'Size': ['Größe','Taille','Tamaño','Tamanho','Размер'],
'Parents': ['Eltern','Parents','Padres','Ascendentes','Родители'],
'Database': ['Datenbank','Base de données','Base de datos','Base de dados','База данных'],
'Choose a container from MMFDB.': ['Container aus MMFDB auswählen.','Choisir un conteneur dans MMFDB.','Elegir un contenedor de MMFDB.','Escolher um contentor de MMFDB.','Выбрать контейнер из MMFDB.'],
'Artifact label; UID is the unique identity.': ['Artefaktname; UID ist die eindeutige Identität.','Étiquette ; UID est l’identifiant unique.','Etiqueta; UID es la identidad única.','Etiqueta; UID é a identidade única.','Метка; UID — уникальный идентификатор.'],
'Dictionary artifact kind.': ['Artefaktart aus dem Wörterbuch.','Type d’artefact du dictionnaire.','Tipo de artefacto del diccionario.','Tipo de artefacto do dicionário.','Тип артефакта из словаря.'],
'Recorded operation; empty means carried data.': ['Gespeicherter Vorgang; leer bedeutet übernommene Daten.','Opération enregistrée ; vide indique des données transférées.','Operación registrada; vacío indica datos transferidos.','Operação registada; vazio indica dados transferidos.','Записанная операция; пустое значение — исходные данные.'],
'What one table row represents.': ['Bedeutung einer Tabellenzeile.','Ce que représente une ligne.','Lo que representa una fila.','O que representa uma linha.','Что представляет одна строка.'],
'Number of stored rows.': ['Anzahl gespeicherter Zeilen.','Nombre de lignes enregistrées.','Número de filas almacenadas.','Número de linhas armazenadas.','Количество сохранённых строк.'],
'Stored payload size.': ['Größe gespeicherter Nutzdaten.','Taille des données enregistrées.','Tamaño de los datos almacenados.','Tamanho dos dados armazenados.','Размер сохранённых данных.'],
'Number of recorded parent artifacts.': ['Anzahl gespeicherter Elternartefakte.','Nombre d’artefacts parents enregistrés.','Número de artefactos padres registrados.','Número de artefactos ascendentes registados.','Количество записанных родительских артефактов.'],
}
_HINTS.update(_HEADERS)
_HINTS.update({
'Choose container folder': ['Containerordner wählen','Choisir le dossier du conteneur','Elegir carpeta del contenedor','Escolher pasta do contentor','Выбрать папку контейнера'],
'Pack instrument data': ['Instrumentdaten verpacken','Regrouper les données instrumentales','Empaquetar datos instrumentales','Empacotar dados instrumentais','Упаковать данные прибора'],
'Choose a folder for the new PTO container. Source files are preserved.': ['Ordner für den neuen PTO-Container wählen. Quelldateien bleiben erhalten.','Choisir un dossier pour le nouveau conteneur PTO. Les fichiers sources sont préservés.','Elegir carpeta para el nuevo contenedor PTO. Los archivos originales se conservan.','Escolher pasta para o novo contentor PTO. Os ficheiros originais são preservados.','Выберите папку для нового контейнера PTO. Исходные файлы сохраняются.'],
'Create a new container in the selected folder.': ['Neuen Container im ausgewählten Ordner erstellen.','Créer un conteneur dans le dossier choisi.','Crear un contenedor en la carpeta elegida.','Criar um contentor na pasta escolhida.','Создать контейнер в выбранной папке.'],
'Cancel': ['Abbrechen','Annuler','Cancelar','Cancelar','Отмена'],
'Cancel container creation.': ['Containererstellung abbrechen.','Annuler la création du conteneur.','Cancelar la creación del contenedor.','Cancelar a criação do contentor.','Отменить создание контейнера.'],
'No container open.': ['Kein Container geöffnet.','Aucun conteneur ouvert.','Ningún contenedor abierto.','Nenhum contentor aberto.','Контейнер не открыт.'],
'No container open. Drop a .pto on this window, or press Open. A container holds one measurement: the instrument file verbatim, and every result computed from it beside it.': ['Kein Container geöffnet. Eine .pto auf dieses Fenster ziehen oder Öffnen drücken. Ein Container enthält eine Messung: die Instrumentendatei unverändert und daneben jedes daraus berechnete Ergebnis.','Aucun conteneur ouvert. Déposez un .pto sur cette fenêtre ou appuyez sur Ouvrir. Un conteneur contient une mesure : le fichier instrument tel quel et, à côté, chaque résultat calculé.','Ningún contenedor abierto. Suelte un .pto en esta ventana o pulse Abrir. Un contenedor guarda una medición: el archivo del instrumento tal cual y, junto a él, cada resultado calculado.','Nenhum contentor aberto. Largue um .pto nesta janela ou prima Abrir. Um contentor guarda uma medição: o ficheiro do instrumento tal e qual e, ao lado, cada resultado calculado.','Контейнер не открыт. Перетащите .pto в это окно или нажмите «Открыть». Контейнер хранит одно измерение: файл прибора без изменений и рядом каждый вычисленный результат.'],
'A container already exists. Choose another folder.': ['Container existiert bereits. Anderen Ordner wählen.','Un conteneur existe déjà. Choisir un autre dossier.','Ya existe un contenedor. Elegir otra carpeta.','Já existe um contentor. Escolher outra pasta.','Контейнер уже существует. Выберите другую папку.'],
})


def install():
    from chisurf.emtk.i18n import install as install_chisurf
    install_chisurf()
    for i, (language, labels) in enumerate(_LABELS.items()):
        messages = dict(zip(_SOURCES, labels))
        messages.update({source: translated[i] for source, translated in _HINTS.items()})
        i18n.add_translations(language, messages, context=_CONTEXT)


def tr(text):
    return i18n.tr(text, context=_CONTEXT)
