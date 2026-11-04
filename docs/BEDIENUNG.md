# Bedienungsanleitung oneSCM-360

Version **0.5.0 · 04.11.2026**. Lokaler Einzelarbeitsplatz. Installation und Sicherung:
[README](../README.md). Der [Funktionsstand](../FUNKTIONSSTATUS.md) unterscheidet
umgesetzte Funktionen und verbleibende Grenzen. Für eine bereits installierte
Version zuerst die [Updateanleitung](AKTUALISIERUNG.md) verwenden.

## 1. Start und Orientierung

ZIP vollständig entpacken und unter Windows `start.bat` starten. Python 3.11 oder
neuer mit `py`-Launcher muss installiert sein. Die Versionsnummer mit Datum steht
oben rechts im Frontend. Die linke Bibliothek enthält Gliederungen und zentrale
Werkzeuge für Quellen, Markdown-Konvertierung, Agenten und internes Wissen.

Fachliche Version und technische Revision unterscheiden sich: Die **Version** wird
frei gepflegt, beispielsweise `2026.11`. Jede Speicherung erzeugt automatisch eine
**Revision**. Vergangene Revisionen und erzeugte Ausgaben bleiben nachvollziehbar.
Gliederungsänderungen ausdrücklich mit **Speichern** sichern.

## 2. Gliederungen zentral pflegen

**Gliederung anlegen** erstellt Einleitung, Glossar und FAQ als Pflichtvorgaben.
Diese redaktionellen Kapitel benötigen keine externe Quelle. Titel, Kapitelziel,
Hierarchie, Status und Pflichtregeln bleiben editierbar. Mit **+** Kapitel ergänzen;
Pfeile verschieben ganze Teilbäume oder ändern die Ebene. Bäume lassen sich auf- und
zuklappen. Automatische Nummerierung folgt der tatsächlich verwendeten Struktur.

Unter **Version & Metadaten** Titel, Dokumentart, Version, Status, Verantwortliche
und Tags pflegen. Das Ausgabeprofil legt Rolle, Umfang, Markt, Sparte, Sprache,
Release, Stichtag und Prod/Preprod fest. Rollen: Retailer, Markt, MO, HQ, intern.
Sparten: Van, PC oder beide. Sprachen: de/en/fr/it; sk/ko sind vorgesehen.
Malaysia und Indien bleiben zurückgestellt.

**Alle Gliederungen** bietet Suche, Filter und Sortierung. Zwei Gliederungen oder
gespeicherte Stände können in parallelen Ordnerbäumen verglichen werden. Kopieren
erstellt eine unabhängige Gliederung mit Vergleichsherkunft. Archivierung erfolgt
über den Status. Die Wiederherstellung eines alten Stands als neue Revision ist
noch offen.

## 3. Gliederungen importieren und erneut einlesen

Zwischenablage, TXT, Markdown und DOCX können eine Struktur liefern. DOCX verwendet
Überschriftformatvorlagen; bei rein visuell formatierten Überschriften zuerst die
Word-Formatvorlagen korrigieren. Titel und Ebenen in der Importvorschau prüfen.

Für einen Reimport die bestehende Zielgliederung wählen. Zuordnungsvorschläge
kontrollieren und unklare Zeilen ausdrücklich einem bestehenden Kapitel zuordnen
oder als neu markieren. Stabile Kapitelkennungen erhalten zugewiesene Inhalte und
Chunks. Im Import fehlende alte Kapitel werden ausgewiesen und behalten; sie
werden nicht stillschweigend entfernt.

## 4. Domänen, Matrix und Kapitelregeln

Die acht Hauptdomänen sind Product Management, Contract Generation, Contract
Management, Customer Management, Finance Management, Market Setting, Admin Section
und ein Platzhalter. **Unterdomänen verwalten** ergänzt die gemeinsame Taxonomie.

Je Kapitel sind mehrere Domänen und Unterdomänen möglich; jede Domäne kann mehrere
Kapitel referenzieren. Mapping lässt sich insgesamt und je Verbindung deaktivieren.
Die Baumansicht wechselt zwischen Kapiteln und Domänen. Zähler zeigen bestätigte,
eindeutige Chunks direkt und einschließlich Unterkapiteln, mit Rollenfilter.

Die Matrix **Kapitel · Rolle · Domäne** bietet Stichwort-, Label-, Rollen- und
Themensuche. Farbige Bemerkungen erläutern Entscheidungen und erscheinen in keiner
Dokumentausgabe. Kapitelbedingungen steuern Rollen, Länder, Sparten, Sprachen und
Release; eine ausgeschlossene Kapitelgruppe schließt ihre Unterkapitel aus.

Kapiteltypen: redaktionell, fachlich, automatisch oder zusammengestellt. Pflicht-,
bedingte und manuelle Aufnahme sind getrennt steuerbar. Erwartete Texte, Bilder,
Klickstrecken und FAQ erzeugen Prüfpunkte, wenn sie fehlen. Leere Pflichtkapitel
blockieren die Veröffentlichung. Das Inhaltsverzeichnis verwendet die sichtbaren
Kapitel; Word-Seitenzahlen werden noch nicht automatisch berechnet.

## 5. Quellen und geprüfte Chunks

Unter **Quellen & Chunks** Dateien hochladen und Quellenart, Herkunft und Release
angeben. Unterstützt: HTML, TXT, MD, DOCX, PPTX, PDF, CSV, JSON. HTML-basierte
Word-`.doc`-Exporte werden direkt verarbeitet. Binäres altes DOC benötigt Antiword;
alternativ vorher in Word als DOCX speichern. Gescannte PDFs liefern ohne OCR keine
zuverlässigen Texte. Rasterbilder aus Office/PDF können separat extrahiert werden.

Unter **Quelle aus Zwischenablage anlegen** Text, HTML oder Markdown einfügen.
Im HTML-Modus kann formatiertes HTML aus der Zwischenablage übernommen werden.
Es gibt keine direkte Jira-/Confluence-Verbindung oder automatische Synchronisation.
Neue Release-Exporte müssen erneut eingelesen und geprüft werden.

**KI Triage** erzeugt Vorschläge für Kapitel, Domänen, Rollen, Stichwörter und Labels.
Standard ist **Lokale Regeln (keine KI)**. Für Ollama muss ein lokales Modell bereits
installiert sein. Erst **Triage-Vorschlag prüfen** und **Labels & Zuordnungen
speichern** bestätigen die Zuordnung. Quellen/Chunks sind durchsuchbar. Löschen
entfernt Quelle, Chunks und ihre Zuordnungen; bereits extrahierte Medien und
übernommene Textrevisionen separat verwalten.

### Jira-HTML-Exporte

Den Jira-Export als HTML-Datei hochladen und die Quellenart **Jira** wählen.
Erkannte Jira-Layouts werden auch automatisch zugeordnet. Die ticketweise Verarbeitung bildet
je erkanntem Ticket einen Chunk, übernimmt fachliche Überschriften und entfernt
erkannte Personenfelder sowie erkennbare PII vor der Speicherung. In dieser
Importstrecke wird nur das bereinigte HTML als Quelldatei gespeichert. Das
Quellenlimit beträgt 20 MB; andere Importarten können zusätzliche Mengenlimits
haben. Die Verarbeitung arbeitet in Schritten von bis zu 25 Tickets. Pausieren
wirkt nach dem laufenden Schritt; ein gespeicherter offener Import kann über
**Fortsetzen** weiterlaufen. **Import abbrechen** entfernt seine vorbereiteten
Ticketdaten. Die Quelle mit ihren Chunks entsteht erst nach vollständiger
Verarbeitung. Bereits fertig importierte Quellen werden dadurch nicht gelöscht.

Maximal 10.000 Tickets je Export; größere Exporte aufteilen. Fehlt bei gewählter
Quellenart Jira ein erkanntes Ticketlayout, wird ein bereinigter Dokument-Chunk
mit Warnung angelegt. Doppelte Ticketnummern oder unlesbare Schlüssel in erkannten
Jira-Zeilen brechen den Import ab. Ticketanzahl und Grenzen anschließend prüfen.

Die Bereinigung arbeitet mit erkennbaren Feldern und Mustern. Freie Formulierungen,
unbekannte Exportlayouts und nicht erkannte persönliche Angaben können erhalten
bleiben. Importierte Chunks prüfen, bevor sie in Texte oder Modelle gelangen.
Die ursprüngliche Exportdatei auf dem Rechner wird nicht verändert.

## 6. Texte, Jira-Nachweise und Dokumenteignung

Texte können direkt im Kapitel oder in der zentralen Bibliothek **Inhalte zuordnen**
gepflegt werden. Zentrale Bausteine haben eigene Revisionen. Ein Kapitel bindet eine
feste Revision; neue zentrale Fassungen ausdrücklich prüfen und übernehmen.
Zusätzliche Bedingungen einer Verwendung können den ursprünglichen Geltungsbereich
nur einschränken.

Inhaltstypen und Umfangsfassungen steuern Kompakt, Standard und Ausführlich. Leere
Fassungen verwenden den Basistext. Als Voraussetzung, Schritt oder Warnhinweis
markierte Inhalte bleiben bei Umfangsreduktion erhalten. Sprachfassungen behalten
ihre Ausgangsrevision; bei Änderungen warnt das System vor veralteten Übersetzungen.
KI-Kürzung und Übersetzung liefern ungeprüfte Vorschläge mit manueller Übernahme.

Unter **Dokumenteignung · Jira-Nachweise · Zeit**:

1. Verwendbarkeit für **Manual / Handbuch**, **Releaseletter** und **Quick Reference**
   getrennt aktivieren. Diese Auswahl ergänzt Profil und Freigaberegeln.
2. Bei Bedarf Markdown statt Klartext auswählen. Word, HTML und PDF formatieren
   Markdown; PowerPoint bleibt eine verdichtete Textdarstellung.
3. Jira-Ticketnummer, Status, Typ, Datum und internen Prüfvermerk ergänzen. Erst
   nach inhaltlicher Prüfung **Text anhand dieses Nachweises geprüft** aktivieren.
4. Änderungen an Text, Varianten oder Gültigkeit setzen die Verifikation zurück.
   Ungeprüfte verknüpfte Nachweise blockieren die Veröffentlichung.

Nachweise werden manuell aus Exporten gepflegt. Der Ticketstatus wird nicht live
abgerufen. Strukturierte Nachweise, Quellenfelder und interne Vermerke erscheinen
nicht im Leserinhalt. Verknüpfte Ticketnummern und zugehörige `/browse/`-Links werden
zusätzlich aus Lesertexten entfernt. Das ersetzt keine Prüfung beliebiger freier
Texte, Screens oder Templatekopfzeilen auf vertrauliche Informationen.

## 7. Gültigkeit und Versionsverlauf

Gültigkeitsregeln auf Gliederung, Kapitel und Text kombinieren Zeitraum, Jahr,
Land, Rolle, Sparte, Prod/Preprod, fachliche Version und Status. Ohne Zeitregeln
besteht keine zeitliche Einschränkung. Bei Zeitregeln im Ausgabeprofil einen
**Stichtag** angeben. `*` bedeutet alle; leeres Jahr bedeutet alle Jahre.

Die spezifischere passende Regel gewinnt. Gleich spezifische, widersprüchliche
Regeln werden nicht willkürlich aufgelöst und blockieren die Veröffentlichung.
Für kombinierte Van-/PC-Ausgaben muss die zeitliche Abdeckung konsistent sein;
gegebenenfalls getrennte Texte oder Ausgaben verwenden. „Zurückgezogen“ schließt
Inhalte für das passende Profil aus, „Entwurf“ erteilt keine Freigabe.

**Verwendung & Zeit** zeigt, welche Texte in den drei Dokumentarten tatsächlich
verwendet werden und warum andere entfallen. Dort stehen auch interne Jira-Nachweise.
Der Versionsverlauf filtert gespeicherte Gliederungsstände nach Land, Jahr, Rolle,
Sparte und Status. Fachliche Versionen bleiben manuell gepflegt. Die
**Releaseverwaltung** übernimmt geprüfte Dokumentationspakete ausdrücklich nach
Prod (Abschnitt 14); eine automatische Vierwochen-Terminsteuerung gibt es nicht.
Ein Stichtag wählt passende Gültigkeitsregeln aus, ersetzt aber keine gebundene
Textrevision durch eine historische Fassung.

## 8. Screens, PII und Klickstrecken

Unter **Bilder & Klickstrecken** PNG/JPEG hochladen. Schon beim Upload Land, Rolle,
Sparte, Umfang, Priorität und Labels zuweisen. Die Bibliothek filtert diese Merkmale
und sortiert unter anderem nach Land oder Priorität. Allgemeingültige Bilder (`*`)
passen auch zu konkreten Profilfiltern. Doppelte Bilddateien überschreiben keine
bestehenden Metadaten.

Mit **Bearbeiten / OCR / PII** Bildunterschrift, interne Notiz, Profil, Labels und
Domänen pflegen. OCR über Tesseract liefert Text und prüfbare PII-/Labelvorschläge.
USERID, Login, IBAN, FIN, Kennzeichen und weitere persönliche Daten visuell prüfen.
PII-Regionen markieren, abdecken oder stark unkenntlich machen; anschließend die
gerasterte Ausgabefassung ansehen und ausdrücklich bestätigen. Schrittmarkierungen
und Texte können ergänzt werden. Nur geprüfte, freigegebene Bildrevisionen werden
ausgegeben. Änderungen an Markierungen erfordern erneute Sichtprüfung.

Kapitel können Einzelbilder oder geordnete Klickstrecken mit Profilvarianten
verwenden. Pro Schritt muss genau eine passende freigegebene Variante vorliegen.
Unvollständige oder widersprüchliche Strecken werden nicht ausgegeben. Historisch
verwendete Bilder archivieren; unbenutzte können gelöscht werden.

Originalzugriff ist im Prototyp über den Redaktionsmodus HQ/intern gesteuert.
Dies ist keine Authentifizierung. Es gibt keine automatische Garantie, dass OCR
alle persönlichen Daten erkennt.

## 9. Separates internes Wissensregister

**Internes Register · FAQ** ist unabhängig von den acht fachlichen Domänen und
der Textbibliothek. Die Hauptthemen **Testing**, **UI**, **Steuerung** und
**IT-Themen** können umbenannt und um Unterthemen ergänzt werden. Bis zu vier
Ebenen sind möglich. Bestehende Themen bleiben erhalten; Archive werden über den
Eintragsstatus verwaltet.

Ein Eintrag kann mehrere interne Themen sowie optionale fachliche Domänen,
Rollen, Länder, Labels und Stichwörter referenzieren. Titel, interner Inhalt,
Quelle/Jira-Referenz, Notiz, Sprache, Status und ein FAQ-Frage-Antwort-Paar werden
revisioniert gespeichert. Suchfeld und Statusfilter unterstützen die Pflege;
**Revisionen** zeigt die bisherigen Texte.

Für den internen Chatbot die FAQ-Vormerkung ausdrücklich aktivieren. Frage und
Antwort sind dann Pflicht. Zusätzlich Sparte und zeitliche Gültigkeit pflegen. Die **interne Chatbot-FAQ-Vorschau** zeigt ausschließlich
freigegebene, vorgemerkte Paare und berücksichtigt ausgewählte Rolle, Land und
Sprache. Archivierte oder ungeprüfte Einträge erscheinen dort nicht. Die Vorschau
ist eine einfache lokale Stichwortsuche. Für Antworten mit zusätzlichen Sparten-,
Zeit- und Umgebungsfiltern **Interner Chatbot** verwenden (Abschnitt 13).
Rollenbezug beschreibt die Gültigkeit der Information, keine Benutzerberechtigung.

**Alle Inhalte dieses Registers bleiben aus Handbuch, Releaseletter, Quick Reference
und deren Leser-Vorschau ausgeschlossen – auch bei Ausgabeprofil HQ/intern.** Es
gibt keine automatische Übernahme in Dokumentbausteine. Interne FAQ gehören hierhin;
FAQ für Leser gehören weiterhin in die zentrale Textbibliothek. Ein im Dokumenteditor
als „Interner Inhalt: nur HQ/intern“ markierter Baustein ist dagegen ausdrücklich
Leserinhalt für diese Zielgruppen. Für Informationen, die niemals im Dokument
erscheinen dürfen, das separate Register oder interne Vermerksfelder verwenden.

## 10. Layouttemplates und Ausgaben

Unter **Layouttemplates** DOCX oder PPTX hochladen, Name und fachliche Version
vergeben. Weitere Fassungen derselben Templatereihe erzeugen neue Revisionen.
Je Gliederung eine feste Word- und/oder PowerPoint-Revision auswählen und speichern.
Word übernimmt Formatvorlagen, Seitenlayout und Kopf-/Fußzeilen; PowerPoint Master,
Layouts und Folienformat. Beispielkörper bzw. Beispielsfolien werden entfernt.
Markenelemente in Kopfzeilen/Mastern müssen für Leser geeignet sein.

HTML/PDF verwenden portable Farben, Schriftgröße und ein eigenes Layout. Sie sind
keine pixelgenaue Konvertierung der Office-Dateien. Native Templates sind noch kein
beliebiger Platzhalterdesigner. Lange Tabellen, Sonderzeichen, Koreanisch, Bilder
und Umbrüche in den tatsächlichen Windows-/Office-Versionen abnehmen.

**Ausgabe prüfen** zeigt Leserinhalt und verbleibende Prüfpunkte. Zunächst Word,
PowerPoint, PDF oder HTML als Prüfausgabe erzeugen. Für eine freigegebene Ausgabe
**Profil prüfen & freigeben** ausführen und **Veröffentlichung** aktivieren.
Freigaben gelten für den geprüften Stand und das Profil. Änderungen erzeugen einen
neuen Entwurf. Der **Verwendungsnachweis** enthält Profil, Revisionen und die
ursprünglichen Ausgabedateien zum erneuten, unveränderten Download.

### Designstudio

**Designstudio** öffnet die Gestaltung für die aktuelle Gliederung. Office-Templates
bleiben in **Layouttemplates** hochladbar; im Designstudio die gewünschte feste
Word-/PowerPoint-Revision auswählen. Ohne native Vorlage gilt das Standardlayout.

| Einstellung | Steuerung |
|---|---|
| Farben | Hauptfarbe, Akzentfarbe, Kapitel, Unterkapitel, Fließtext, Links, Hervorhebungen, Hinweise, Ausnahmen, Tipps |
| Schrift | Schriftfamilie und Größe von 8–18 pt; installierte Schriften bzw. PDF-Schriftunterstützung beachten |
| Bilder | Breite von 25–100 Prozent der verfügbaren Breite; Bildunterschriften ein-/ausschalten |
| Orientierung | Erzeugte Seiten-/Foliennummern und Symbole für Hinweise, Ausnahmen und Tipps ein-/ausschalten |
| Hervorhebungen | Bis zu 50 Begriffe, ein Begriff je Zeile, maximal 80 Zeichen; Textsuche ohne reguläre Ausdrücke |

**Gestaltungsbeispiel** reagiert auf Änderungen, verwendet aber Beispieltext und
einen schematischen Screen. Es ist keine Vorschau der tatsächlichen Kapitel,
Seitenumbrüche oder Office-Master. **Design übernehmen** ändert die aktuelle
Gliederung; danach **Speichern** drücken. So bleibt das Design mit deren Revision
nachvollziehbar. **Standarddesign einsetzen** setzt Gestaltungswerte zurück und
behält die ausgewählten Office-Templates.

Eigene Master, Kopf-/Fußzeilen und native Formatvorlagen bleiben Teil des
Office-Templates. Die Wirkung der Designwerte deshalb in den tatsächlich erzeugten
DOCX-, PPTX-, PDF- und HTML-Dateien prüfen; die Formate teilen sich keinen
pixelgleichen Satzspiegel. Der Bereich ist kein freier Drag-and-drop-Seitendesigner.

Hinweisfelder entstehen durch sichtbaren Lesertext am Absatzanfang, beispielsweise
`Hinweis:`, `Ausnahme:` oder `Tipp:`. Auch `Note:`, `Notice:`, `Exception:` und
`Tip:` werden erkannt. Es werden keine internen Vermerke zu solchen Feldern
umgewandelt. Stichworthervorhebung sucht Begriffe ohne Beachtung der Groß-/
Kleinschreibung an Wortgrenzen; über mehrere unterschiedlich formatierte Textteile
verteilte Begriffe können anders erscheinen.

| Ausgabe | Wichtige Gestaltungseigenschaft |
|---|---|
| Word ohne Template | Designschrift und Überschriftenfarben; Bildbreite, Linkfarbe, Hervorhebungen und Hinweisfelder; Seitenzahl als Word-Feld |
| Word mit Template | Native Grundschrift und Überschriftenstile bleiben; zusätzliche Auszeichnung und Bildregeln wirken. Bereits im Template vorhandene Seitenzahlen werden durch den Schalter nicht entfernt |
| PowerPoint | Text wird auf Folien verteilt, die Schriftgröße für die Lesbarkeit angepasst; native Master bleiben erhalten. Bildbreite, Hinweise, Hervorhebungen und erzeugte Foliennummern sind steuerbar |
| HTML | Browserlayout mit eingebetteten Bildern; Seitenzahlen beim Drucken hängen von der Unterstützung des Browsers ab |
| PDF | Eigenständiger Renderer mit Seitenzahlen; Unicode-Schrift wird passend zu Sprache und verfügbaren Schriften gewählt, nicht jeder eingegebene Office-Schriftname direkt übernommen |

Der Nummernschalter betrifft die vom Tool erzeugten Nummern. Fest in einem
Office-Master oder einer Kopf-/Fußzeile vorhandene Gestaltung bleibt Teil der
Vorlage. Eine Renderprobe im Finalisierungsablauf ersetzt die Sichtprüfung nicht.

## 11. Viele Markdown-Dateien in Word umwandeln

**Markdown → Word** ist auch ohne aktive Gliederung nutzbar. Dateien auswählen,
Reihenfolge mit Pfeilen ändern, einzelne Dateien entfernen und eine Ausgabe wählen:
einzelne Word-Dateien als ZIP oder ein gemeinsames Word-Dokument. Optional eine
Word-Templaterevision auswählen. Überschriften, Listen, Hervorhebungen, Tabellen,
Links und Code werden bearbeitbar umgesetzt. Grenzen: maximal 100 Dateien,
1 Mio. Zeichen je Datei, insgesamt 5 Mio. Zeichen. Verknüpfte Bilder bleiben Hinweise;
sie werden nicht aus dem Internet nachgeladen.

Dies ist eine eigenständige Dateikonvertierung. Sie durchläuft weder die fachlichen
Dokumentfilter noch Jira-Bereinigung oder PII-Freigabe. Nur für die beabsichtigte
Zielgruppe geeignete Markdown-Dateien verwenden.

## 12. Agentenläufe und Finalisierung

Zuerst die Gliederung speichern. **Agentenläufe** bietet zwei Ablaufvorlagen:

| Vorlage | Schritte | Ergebnis |
|---|---|---|
| Finalisierung · 4 Agenten | Finalisierung, Validierung, Layout, Dokumentation | Prüfpunkte, Renderprobe in vier Formaten, interner Markdown-Bericht |
| Wissensaufbereitung | Wissens-, Gliederungs-, Bild-, Qualitätsagent | Prüffähige Chunk- und Zuordnungsvorschläge |

Die Fachagenten sind gespeicherte, aufeinanderfolgende Verarbeitungsschritte. Sie
arbeiten regelbasiert; optional nutzen Wissens- und Übersetzungsschritte lokales
Ollama. Vorhandene Copilot-, Claude- und Gemini-Chat-Abonnements verwendet man
stattdessen über den separaten manuellen **KI-Austausch** (Abschnitt 16). Diese
Chat-Anwendungen werden vom Orchestrator nicht automatisch aufgerufen. Für die Finalisierung sind keine Quellen oder KI-Modelle nötig. Eine
Renderprobe prüft die technische Dateierzeugung, nicht die visuelle Office-Abnahme.

Fortschritt, Eingaberevisionen und Ergebnisse bleiben gespeichert. Pausieren wirkt
nach dem aktuellen Schritt; Abbrechen übernimmt keine Vorschläge. Nach einem
Neustart einen unterbrochenen Lauf ausdrücklich fortsetzen. Der Browser führt die
Schritte nacheinander aus; es gibt keinen autonomen Hintergrunddienst.

Vorgeschlagene Labels/Zuordnungen prüfen und einzeln auswählen. Bei Bedarf zusätzlich
Textentwürfe in der Bibliothek anlegen. Veränderte Quellen, Gliederungen oder
Taxonomien verhindern eine Übernahme veralteter Ergebnisse. Kein Agentenlauf gibt
ein Dokument automatisch frei. Der Finalisierungsbericht ist ein internes
Arbeitsdokument und keine Leserpublikation.

## 13. Interner Chatbot mit Belegen

Zunächst im **Internen Register · FAQ** Frage, Antwort, Herkunft und Gültigkeit
pflegen, für den Chat vormerken und fachlich freigeben. Der Chat durchsucht diese
FAQ; hochgeladene Quellen, Dokumentbausteine und sämtliche Register-Freitexte
werden nicht automatisch zu Antwortwissen.

1. **Interner Chatbot** öffnen und **Neuer Chat** wählen.
2. Rolle, Land, Sparte, Sprache, Stichtag und Prod/Preprod einstellen. Land `*`
   sucht ausschließlich allgemein gültige FAQ. Bei Sparte „Beide“ müssen die
   Belege für Van und PC gelten. Das Profil bleibt nach der ersten Frage fest;
   für ein anderes Profil einen neuen Chat beginnen.
3. Eine konkrete Frage stellen. **Lokale FAQ-Belege** benötigt kein Modell und
   zeigt bis zu drei passende freigegebene Antworten mit Belegen.
4. Optional **Lokale KI zur Belegauswahl** und den Namen eines bereits installierten
   Ollama-Modells wählen. Das Modell darf nur zusammenhängende, wortgetreue
   Ausschnitte auswählen. Ungültige Zitate werden verworfen. Das ist kein freies
   generatives RAG und kein allgemeiner Chat über alle hochgeladenen Dokumente.
5. Belege aufklappen und mit **Belegte Registerrevision ansehen** den zugrunde
   liegenden Stand prüfen. Fehlende Herkunft im Register ergänzen.

Ohne ausreichend passende Belege erscheint ein Hinweis statt einer erfundenen
Antwort. Erkannte abweichende FAQ-Antworten werden nebeneinander zur Klärung
gezeigt. Stichwortsuche und Widerspruchsregeln garantieren keine vollständige
semantische Erkennung. Eine wörtliche Antwort kann sachlich falsch sein, wenn die
freigegebene FAQ falsch ist; die fachliche Freigabe bleibt entscheidend.

**Vorherige Frage als Kontext verwenden** ergänzt nur die unmittelbar vorherige
Frage. Ein Chat umfasst höchstens 50 Fragen. Verläufe bleiben lokal gespeichert.
Wenn ein Beleg später geändert, archiviert oder unpassend wird, markiert die
Ansicht die historische Antwort als veraltet. Eine frühere Antwort wird nicht
still umgeschrieben. Chat und Belege bleiben intern und erscheinen in keiner
Leserausgabe. Das Rollenprofil ist keine Anmeldung oder Zugriffssperre.

## 14. Dokumentationsreleases von Preprod nach Prod

Die **Releaseverwaltung** verwaltet lokale Dokumentationsstände. Sie aktiviert
keine Funktionen im oneSCM-System und synchronisiert sich nicht mit Jira oder
Confluence. Der geplante Termin dient der manuellen Aktivierung; es gibt keinen
Scheduler und keine automatische Promotion nach vier Wochen.

1. Für jedes benötigte Zielprofil eine gespeicherte Preprod-Gliederung vorbereiten.
   Markt ausdrücklich setzen, Inhalte und PII prüfen, Quellenzuordnungen bestätigen
   und **Profil prüfen & freigeben** ausführen.
2. Unter **Releaseverwaltung** eine neue Releaseversion und den Prod-Termin angeben.
   Zwischen 1 und 50 unterschiedliche Preprod-Gliederungen auswählen und **Neues
   Paket vorbereiten** drücken. Das erstellt zunächst eine Vorschau.
3. Beim ersten Paket sämtliche benötigten Profile bewusst aufnehmen. Bereits
   vorhandene Prod-Gliederungen werden nicht automatisch als Baseline erkannt.
   Danach muss jedes bisher aktive Profil in jedem neuen Paket vertreten sein.
   Ein Profil umfasst Markt, Rolle, Sparte, Sprache, Umfang und Dokumentart.
4. Bisherigen und vorgesehenen Prod-Baum, Texte, Metadaten sowie ausgeschlossene
   Kapitel und Inhalte vergleichen. Die Kandidaten werden mit der neuen Version,
   Umgebung Prod und dem geplanten Stichtag erneut geprüft. Offene zugeordnete
   Quellenwidersprüche können die Promotion blockieren.
5. Blocker beheben, Änderungen speichern/freigeben und die Vorschau erneut
   erstellen. Wenn sich Ausgangsstände, Quellenprüfung, Taxonomie oder aktive
   Prod-Stände geändert haben, darf eine alte Vorschau nicht aktiviert werden.
6. Zum Termin oder danach die fachliche Prüfung bestätigen und begründen.
   **Geprüftes Paket nach Prod übernehmen** übernimmt alle Profile in einer
   gemeinsamen Datenbanktransaktion. Bei einem Fehler bleibt kein Teilpaket aktiv.

Preprod-Fassungen und bereits erzeugte Dateien bleiben erhalten. Neue Ausgabedateien
werden weiterhin über die jeweilige Gliederung erzeugt. Das Aktivierungsprotokoll
zeigt Version, Datum und Begründung. Ein gespeichertes Paket ist keine Anmeldung
oder Vier-Augen-Freigabe; am Einzelarbeitsplatz entscheidet dieselbe Person.

Nur das aktuell aktive Paket kann über **Aktives Release zurücknehmen** mit
Bestätigung und Begründung zurückgenommen werden. Vorherige Stände werden als
neue Revisionen wiederhergestellt; erstmals hinzugekommene Profile werden archiviert.
Wurde Prod nach Aktivierung manuell verändert oder fehlt eine benötigte frühere
Quellenzuordnung, wird die gesamte Rücknahme abgebrochen, um Änderungen nicht zu
überschreiben. Diese Release-Rücknahme ersetzt keine allgemeine Sicherung oder
Wiederherstellung beliebiger Gliederungsrevisionen.

## 15. Widersprüche zwischen Quellen klären

**Quellenwidersprüche** verwendet bestätigte Chunk-Zuordnungen, um betroffene
Gliederungen und Kapitel zu zeigen. Ein Import allein bestätigt keine Aussage.

1. Unter **Quellenkontext pflegen** je Quelle Land, Rolle, Sparte, Sprache,
   Prod/Preprod, fachliches Quelldatum und Gültigkeitszeitraum pflegen. `*` steht
   für allgemeine Gültigkeit. Explizit getrennte Bereiche werden nicht als
   gleichzeitig gültige Aussagen miteinander verglichen.
2. Zwei bis zwanzig Quellen mit insgesamt höchstens 300 Chunks wählen und
   **Quellen vergleichen** ausführen. Regeln suchen Dubletten sowie ähnliche
   Aussagen mit abweichenden Zahlen oder Verneinungen. Unterschiedliche
   Release-Angaben können eine beabsichtigte Änderung erklären.
3. Alternativ zwei Textstellen verschiedener Quellen wählen und einen manuellen
   Prüfpunkt mit Begründung anlegen. **Lokale KI mit Belegprüfung** kann einen
   Vorschlag mit wörtlichen Quellenausschnitten liefern; hierfür ist ein lokales
   Ollama-Modell erforderlich. Ein ungültiges Zitat wird nicht übernommen.
4. Hinweise anhand von Herkunft, Version, Datum und Profil fachlich prüfen.
   Entscheidung, Begründung und bei Bedarf bevorzugten Beleg speichern.
   Die Entscheidungshistorie hält frühere Bewertungen fest.

| Entscheidung | Bedeutung |
|---|---|
| Offen | Noch nicht fachlich entschieden |
| Widerspruch bestätigt | Konflikt besteht und muss vor Promotion geklärt werden |
| Kein Widerspruch | Unterschied wurde fachlich als widerspruchsfrei begründet |
| Geklärt | Die fachliche Klärung ist dokumentiert; Texte separat nachführen |
| Nicht mehr anwendbar | Nur bei gelöschter Quelle oder nachweislich getrennten Gültigkeitsbereichen möglich |

Eine Entscheidung ändert weder Quellen noch Dokumenttexte automatisch. Eine
bevorzugte Quelle ist ebenfalls keine automatische Ersetzungsregel. Inhaltliche
Änderungen im Texteditor übernehmen und erneut freigeben. Ändern sich die
belegten Quellendaten oder ihr Kontext, wird die Bewertung als **Erneut prüfen**
markiert. Erneut vergleichen und die aktuelle Aussage bewerten.

Offene, bestätigte oder veraltete Widerspruchsprüfungen zu zugeordneten Kapiteln
blockieren die Releasepromotion. Dubletten allein blockieren sie nicht. Ein Scan
mit null Treffern belegt keine Widerspruchsfreiheit. Ohne bestätigte
Chunk-Zuordnungen können Quellenkonflikte keinem Releaseprofil vollständig
zugeordnet werden; die Releasevorschau weist darauf hin.


## 16. Mit Copilot, Claude oder Gemini über den Chat arbeiten

**KI-Austausch · Copilot / Claude / Gemini** nutzt die vorhandenen Chat-Anwendungen
manuell. Ein Chat-Abonnement ist keine API-Berechtigung. Hier werden keine
API-Schlüssel verlangt, keine Anbieter automatisch aufgerufen und keine
Ollama-Installation vorausgesetzt. Das Kopieren oder Herunterladen bleibt lokal;
erst das eigene Einfügen oder Hochladen im ausgewählten Chat übermittelt Inhalte
an diesen Dienst.

1. Eine Quelle auswählen und mit Strg/Umschalt zwischen 1 und 20 Chunks markieren.
   Ein Auftrag umfasst höchstens 60.000 Zeichen bereinigten Quelltext. Im Dialog
   werden Chunks der jeweils ausgewählten Quelle angezeigt.
2. Chat-Anwendung, Dokumentart (Handbuch, Releaseletter, Quickreference), Sprache,
   Zielrolle, Markt und Sparte festlegen. **Auftrag vorbereiten** erzeugt einen
   gespeicherten Auftrag mit eindeutiger Kennung und Quelltextständen.
3. Den vollständigen Auftrag lesen. Es werden ausgewählte Quelltexte angehängt;
   das interne Register, Vermerksfelder und Screens werden nicht hinzugefügt.
   Bekannte Personenfelder und erkennbare Kennungen werden reduziert. Unbekannte
   Namen, vertrauliche Freitexte und fachlich sensible Angaben können verbleiben.
4. **Auftrag geprüft und für die gewählte Chat-Anwendung geeignet** bestätigen.
   Mit **Auftrag kopieren** oder **Auftrag als TXT herunterladen** übertragen und
   in der gewählten Chat-Anwendung selbst einfügen. Bei blockierter Browser-
   Zwischenablage die TXT-Datei verwenden. Falls der Auftrag ungeeignete Inhalte
   enthält, vor dem Austausch die Quellenauswahl korrigieren.
5. Die Antwort als JSON gemäß Auftrag anfordern. Sie muss `job_id`, `title`,
   `text` (Markdown), `source_ids` und optional `warnings` enthalten. Zurück in
   oneSCM-360 beim zugehörigen gespeicherten Auftrag einfügen oder eine `.json`-/
   `.txt`-Antwortdatei auswählen und **Antwort prüfen** drücken.
6. Vorschautext, genannte Quellen und Warnungen fachlich prüfen. Stimmen Funktionen,
   Zahlen, Bedingungen, Sprache und Zielgruppe mit den Quellen überein? Personen-
   und Jira-Angaben prüfen. Eine vorhandene Quellkennung allein beweist keine
   fachliche Richtigkeit der Antwort.
7. **Text, Quellenbezüge und Personenangaben geprüft** bestätigen und **Als
   Bibliotheksentwurf übernehmen** drücken. Der Baustein bleibt ein Entwurf,
   erhält das gewählte Profil und die ausgewählte Dokumenteignung. Er wird weder
   automatisch einem Kapitel zugeordnet noch freigegeben.

Der Import prüft gültiges JSON, passende Auftragskennung, zulässige Quellenbezüge
und Größenlimits. Er ist keine semantische Belegprüfung. Falsche Zuordnungen,
Erfindungen oder Auslassungen trotz gültiger Kennungen muss die Redaktion erkennen.
Das Ergebnis erscheint in **Inhalte zuordnen** zur weiteren Pflege. Dort bei Bedarf
Jira-Nachweise ergänzen, eine passende Kapitelverwendung anlegen und den üblichen
Freigabeablauf durchlaufen. Chat-Warnungen und die Anbieter-/Auftragsreferenz werden
als interner Vermerk gespeichert.

Geänderte oder gelöschte Quelltexte blockieren die Übernahme eines alten Auftrags;
dann neu vorbereiten. Jeder Auftrag kann einmal als Bibliotheksentwurf übernommen
werden. Aufträge und ihre Quelltextauszüge bleiben lokal gespeichert. Die
Anbieterwahl dient der eigenen Arbeitsorganisation; sie meldet sich bei keinem
Dienst an und automatisiert keine Browserbedienung.


### Ergänzungen zu Design und Massenimport in v0.5.0

Im Designstudio stehen die Startvorlagen **oneSCM**, **Druck** und **Kontrast** zur
Verfügung. Der Symbolstil ist zwischen Symbolen, Buchstaben und einer minimalen
Markierung wählbar. Die Gestaltung wird je Gliederung gespeichert; Änderungen
nach **Design übernehmen** mit **Speichern** sichern.

Lesertexte mit den sichtbaren Präfixen `Hinweis:`, `Tipp:` oder `Ausnahme:`
(auch `Note:`, `Notice:`, `Tip:`, `Exception:`) erhalten die gewählte Gestaltung.
Interne Vermerke werden dadurch nicht ausgegeben. Stichwörter werden als ganze
Wörter/Wortkombinationen markiert, ohne reguläre Ausdrücke. In Word und PowerPoint
bleiben native Vorlagenformate erhalten; Farben und Schrift für Standardlayouts
sowie Markierungen und neue Hinweisformatierung sind direkt steuerbar.
Bereits in einer nativen Vorlage vorhandene Seitenzahlen werden beim Ausschalten
nicht entfernt. HTML-Seitenzahlen hängen von der Druckunterstützung des Browsers
ab. Eine verbindliche Gesamtseitenzahl oder ein Seitenbudget wird nicht berechnet.

Die Import-Warteschlange zeigt pro Datei Erfolg, Duplikat, Fehler oder Pause.
**Warteschlange fortsetzen** bearbeitet die übrigen ausgewählten Dateien in
derselben Browsersitzung. Nach einem Neuladen müssen noch nicht hochgeladene
Dateien erneut ausgewählt werden. Bereits vorbereitete Jira-Importe bleiben über
**Fortsetzen** verfügbar. Parsergrenzen werden als Fehler gemeldet; ein dabei
abgeschnittener HTML-Text wird nicht stillschweigend als vollständige Quelle gespeichert.

Im KI-Austausch werden erkannte Ticketkennungen und zugehörige `/browse/`-Links aus
zurückgegebenen Lesertexten entfernt. Die Erkennung ist konservativ und kann
ähnlich aufgebaute Kennungen betreffen; den bereinigten Vorschautext prüfen.


## 17. Sicherung und Wiederherstellung (v0.6.0)

1. Offene Änderungen speichern und **Sicherung & Wiederherstellung** öffnen.
2. **Arbeitsbereich sichern** lädt eine konsistente ZIP mit dem gesamten
   Datenbestand herunter. Sie enthält Texte, Quellen, Originalscreens, interne
   Informationen, Historien, Exporte und gespeicherte Arbeitsaufträge. Die ZIP ist
   unverschlüsselt; geschützt speichern. Programmdateien sind nicht enthalten.
3. Zum Wiederherstellen eine Sicherungs-ZIP auswählen und **Sicherung prüfen**.
   Dateiaufbau, Prüfsumme, Programmversion, Datenbankschema und Integrität werden
   geprüft. Die Vorschau nennt Datum und Anzahlen. Nur Sicherungen derselben
   Programmversion werden angenommen; ZIP maximal 128 MB, Datenbank maximal 512 MB.
4. Die Wiederherstellung ersetzt den gesamten Arbeitsbereich, ohne Zusammenführung.
   Erst nach Eingabe von **WIEDERHERSTELLEN** auf **Arbeitsbereich ersetzen** klicken.
   Es darf währenddessen keine zweite Programm-Instanz dieselbe Datenbank verwenden.
5. Vor dem Ersetzen schreibt die Anwendung eine Rücksicherung in `backups` neben
   der Datenbank. Scheitert diese Sicherung, beginnt das Ersetzen nicht. Änderungen
   seit der Vorschau oder eine Vorschau älter als 15 Minuten erfordern neue Prüfung.
6. Nach Erfolg wird die Oberfläche neu geladen. Andere alte Browserseiten müssen
   ebenfalls neu laden. Die Rücksicherung kann mit derselben Programmversion wieder
   über diesen Dialog eingelesen werden.

Bei einem Programm-Upgrade die passende alte Programm-ZIP gemeinsam mit der
Sicherung aufbewahren: zunächst mit der alten Version wiederherstellen, anschließend
mit der neuen Version starten. Die Sicherungsfunktion ersetzt kein geschütztes
externes Backupmedium und keine Aufbewahrungsstrategie.

## 18. Mehrere Dokumentvarianten als Stapel (v0.6.0)

Eine Gliederung öffnen und speichern, dann **Dokumentvarianten erzeugen** wählen.
Deutsch, Englisch und Französisch sind vorausgewählt; weitere vorhandene Sprachen
können gewählt werden. Rollen, Handbuch/Releaseletter/Quickreference und Word,
PowerPoint, PDF oder HTML kombinieren. Maximal 60 Dateien pro Stapel, insgesamt
höchstens 128 MB erzeugte Dateien. Markt, Sparte, Umfang, Release und Stichtag
stammen aus der geöffneten Gliederung.

**Varianten prüfen** zeigt pro Datei sichtbare Kapitel und Prüfpunkte. Fehlende
Titelübersetzungen, fehlende Pflichtinhalte und weitere Freigabehindernisse bleiben
sichtbar. Das System übersetzt nicht automatisch und ersetzt fehlende Texte nicht
mit fremdsprachigen Texten. Rollen-, Sprach-, Gültigkeits- und Dokumenteignungsregeln
sowie Bildzuordnungen werden wie im Einzelexport angewandt.

Die geprüfte Auswahl bestätigen und die **Varianten-ZIP herunterladen**. Alle
Dateien sind ausdrücklich Prüfausgaben. `Pruefbericht.json` enthält Profile,
Prüfpunkte, Exportkennungen und Prüfsummen und dient der internen Redaktion; ihn
nicht ungeprüft zusammen mit Leserunterlagen verteilen. Jede Datei wird in der
Ausgabehistorie abgelegt. Die Ausgangsgliederung wird nicht verändert. Eine
Veröffentlichung erfolgt weiterhin über eine geprüfte, freigegebene Gliederung.


## 19. Quellen markieren und zusammenstellen (v0.6.1)

Über der Dateiübersicht stehen Dateitypfilter für DOCX, PDF, MD, HTML/HTM und andere
Formate. Der Typfilter und die Textsuche wirken zusammen. **Alle markieren** wählt
alle aktuell gefilterten Dateien; **Alle aufheben** leert die gesamte Auswahl.
Einzelne Dateien lassen sich über ihre Checkbox markieren. Eine Anzeige nennt auch
markierte Dateien außerhalb des Filters: Diese gehören weiter zur Sammelaktion.

**Markierte Dateien verarbeiten** führt die oben eingestellte Regel-/Ollama-Triage
für die Auswahl nacheinander aus. Eine Zielgliederung ist erforderlich. Vorschläge
werden nicht automatisch zu bestätigten Kapitelzuordnungen. Der bestehende
Stoppbutton hält nach der laufenden Verarbeitung an; Fehler einzelner Dateien
werden gemeldet, die übrigen Dateien können weiter verarbeitet werden.

**Dateien zusammenführen / Texte ansehen** lädt extrahierte Texte samt Fundstellen
in einen Editor. Die Originaldateien bleiben unverändert. **Kurze Textauszüge
einsetzen** verwendet höchstens 500 Zeichen pro Chunk: eine ausdrücklich gekennzeichnete
Auszugssammlung, keine KI-Zusammenfassung. Wesentliche Bedingungen können fehlen.
Eine sprachliche Zusammenfassung kann über den vorhandenen KI-Austausch mit der
anschließend gespeicherten Quelle erstellt werden.

Den Text bearbeiten und als Markdown herunterladen oder **Als neue Quelle speichern**.
Unbearbeitete Zusammenstellungen behalten die Chunk-Grenzen und Ursprungsreferenzen;
bearbeitete Texte werden neu gechunked. Labels, Freigaben und Zuordnungen werden
nicht übernommen. Bei Änderungen/Löschung der Ausgangsquellen muss die Zusammenstellung
neu geladen werden. Bis 1500 Dateien und insgesamt 2 Millionen extrahierte Textzeichen
je Zusammenstellung; größere Bestände in Teilmengen bearbeiten. Der Download enthält
Quelltext, keine geprüfte Leserpublikation und keine neue vollständige PII-Bereinigung.
