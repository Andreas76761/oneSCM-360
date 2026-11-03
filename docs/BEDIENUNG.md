# Bedienungsanleitung oneSCM-360

Version **0.4.0 · 03.11.2026**. Lokaler Einzelarbeitsplatz. Installation und Sicherung:
[README](../README.md). Der [Funktionsstand](../FUNKTIONSSTATUS.md) unterscheidet
umgesetzte Funktionen und verbleibende Grenzen.

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
Sparte und Status. Fachliche Release-Versionen werden manuell gepflegt; automatische
Vierwochen-Promotion von Preprod nach Prod ist noch nicht implementiert.

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

Für spätere interne Chatbot-FAQ die Vormerkung ausdrücklich aktivieren. Frage und
Antwort sind dann Pflicht. Die **interne Chatbot-FAQ-Vorschau** zeigt ausschließlich
freigegebene, vorgemerkte Paare und berücksichtigt ausgewählte Rolle, Land und
Sprache. Archivierte oder ungeprüfte Einträge erscheinen dort nicht. Die Vorschau
ist eine lokale Stichwortsuche; ein antwortgenerierender Chatbot ist noch offen.
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
Ollama. Für die Finalisierung sind keine Quellen oder KI-Modelle nötig. Eine
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
