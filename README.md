# oneSCM-360 – lokales Gliederungsstudio

Erster funktionsfähiger Prototyp für die zentrale Verwaltung von Gliederungen und
die Zusammenstellung von Word-/PowerPoint-Prüf- und freigegebenen Ausgaben. Einzelbenutzeranwendung,
lokale Verarbeitung, keine externen KI-Aufrufe.

## Start unter Windows

Voraussetzung: Python 3.11 oder neuer mit dem Windows-Python-Launcher `py`.
`start.bat` doppelklicken. Das Skript legt beim ersten Start eine virtuelle
Umgebung an, installiert die Abhängigkeiten und öffnet die lokale Anwendung im
Browser. Für die Paketinstallation ist Internetzugriff nötig. Beenden mit Strg+C
im Konsolenfenster. Die Anwendung bindet ausschließlich an `127.0.0.1`.

Alternativ in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py --open-browser
```

Unter Windows liegen die Daten standardmäßig in
`%LOCALAPPDATA%\oneSCM-360\onescm.sqlite3`, außerhalb des Projektordners und von
OneDrive. Ein eigenes Verzeichnis kann mit `--data-dir PFAD` gewählt werden.
Die aktive Datenbank nicht in einem Synchronisations- oder Netzlaufwerk ablegen.

## Vorhandene Funktionen

- Mehrere Gliederungen anlegen und unabhängig kopieren.
- Zentrale Übersicht mit Suche, Status-/Rollenfilter und Sortierung; direkte
  Bearbeitung und Auswahl zweier Gliederungen für einen Vergleich.
- Manuell pflegbare Gliederungsversion, Dokumentart, Status, Verantwortliche,
  Beschreibung und Tags. Automatische Speicherrevisionen bleiben davon getrennt.
- Gliederungsimport per eingefügtem Text, TXT, Markdown oder DOCX bis 5 MB;
  Vorschau mit korrigierbaren Titeln und Ebenen. DOCX nutzt Überschriftstile;
  ohne diese werden Absätze übernommen und eine Warnung angezeigt.
- Kapitel und Unterkapitel (bis Ebene 6) über einen Dialog direkt anlegen;
  aufklappbarer Ordnerbaum, Pflichtkapitel, Ziele und Domänen.
- Verschieben vollständiger Teilbäume mit stabilen Kapitelkennungen.
- Mehrfachzuordnungen Kapitel ↔ Domänen/Unterdomänen, pro Zuordnung und pro
  Gliederung aktivierbar. Zusätzlicher aufklappbarer Domänenbaum.
- Kapitel-/Rollen-/Domänenmatrix mit farbigen internen Bemerkungen sowie Suche
  nach Stichwörtern, Labels, Rolle und Thema.
- Quellenübersicht mit Upload, Duplikaterkennung, Text-/Tabellenextraktion,
  Chunks und Löschung. Unterstützt TXT, MD, HTML, DOCX, PPTX, PDF, CSV und JSON.
- Prüfbare Triage-Vorschläge per lokalen Regeln oder optional lokalem Ollama;
  bestätigte Chunk-Zuordnungen mit Zählern je Kapitel, Domäne und Rolle.
- Textbausteine mit Rolle, Markt, Sparte, Sprache, Release, Umfang, Quelle,
  Status und internen Vermerken.
- Nachvollziehbare Vorschau mit Ausschlussgründen und fehlenden Pflichtinhalten.
- DOCX und PPTX als **Prüfausgaben**, einschließlich Fortsetzungsfolien bei
  langen Texten. Keine automatische inhaltliche Kürzung.
- Lokale Speicherung mit Revisionen und Schutz vor veralteten Schreibzugriffen.
  Exportplan und erzeugte Datei werden gemeinsam in der Datenbank archiviert.
- Zwei Gliederungen oder zwei gespeicherte Revisionen nebeneinander im Ordnerbaum
  vergleichen: neue, entfernte, umbenannte, verschobene und geänderte Kapitel;
  Metadatenvergleich, Filter „Nur Unterschiede“ und Markierung des Gegenstücks.

## Bedienablauf

1. Gliederung anlegen oder importieren; Pflichtkapitel kontrollieren.
2. Kapitel wählen, Domäne und Ziel ergänzen, Textbausteine anlegen.
3. Gültigkeit pro Baustein eintragen: `*` bedeutet alle, ein leeres Markt- oder
   Releasefeld bedeutet ungeklärt und verhindert die Aufnahme.
4. Das Ausgabeprofil oben wählen und „Ausgabe prüfen“ öffnen.
5. Änderungen speichern; Word oder PowerPoint herunterladen.

## Gliederungen pflegen und vergleichen

Die Anwendung startet mit **Alle Gliederungen**. „Bearbeiten“ öffnet einen
Datensatz. Unter **Version & Metadaten** lässt sich beispielsweise die fachliche
Version `1.2` pflegen. Jeder Speichervorgang erstellt zusätzlich eine automatische
Revision. Die Version wird auch in Word-/PowerPoint-Prüfausgaben ausgegeben.
Der Gliederungsstatus ist eine redaktionelle Kennzeichnung; er ersetzt keine
fachliche Dokumentfreigabe. Archivierte Gliederungen bleiben über den Statusfilter
auffindbar und bearbeitbar.

**Kapitel erstellen** legt einen Eintrag auf der Hauptebene an. **Unterkapitel
erstellen** wählt das aktuell markierte Kapitel als übergeordneten Eintrag.
Im Dialog kann die Zuordnung geändert werden. Neue Kapitel erscheinen am Ende
der gewählten Ebene und lassen sich anschließend mit den Pfeiltasten verschieben.
Die Kapitelkennungen und zugeordneten Texte bleiben dabei erhalten.

Für einen Vergleich in der Übersicht zwei Kontrollkästchen wählen und **Auswahl
vergleichen** anklicken. Links steht der Ausgangsstand, rechts der Vergleichsstand:
„Neu“ bedeutet ausschließlich rechts vorhanden, „Entfernt“ ausschließlich links.
Alternativ öffnet **Gespeicherte Stände vergleichen** im Editor zwei Revisionen
derselben Gliederung. Der Vergleich ist lesend; ungespeicherte Änderungen werden
nicht einbezogen und bleiben beim Wechsel zwischen den Ansichten erhalten.

Kapitel werden zuerst über bekannte Kennungen zugeordnet; Kopien behalten dafür
die Kapitelherkunft. Bei unabhängigen Importen werden eindeutige Kapitelpfade
oder eindeutige Titel verglichen. Mehrdeutige Kapitel werden nicht automatisch
zugeordnet. Umbenannte Kapitel aus voneinander unabhängigen Importen können daher
als entfernt/neu erscheinen. Im reinen Zwei-Gliederungs-Vergleich bleiben diese
Treffer getrennt; beim erneuten Import in eine bestehende Gliederung können sie
jetzt ausdrücklich manuell zugeordnet werden.
„Geändert“ kennzeichnet Unterschiede an Pflichtregel, Domäne, Kapitelziel oder
Textbausteinen; es ist noch kein zeilenweiser Textvergleich.

## Domänenmapping und interne Matrix

Im Kapitel-Editor unter **Domänen & Unterdomänen** mehrere Zuordnungen ergänzen.
Jede Zuordnung hat ihren eigenen Aktiv-Schalter. **Mapping dieser Gliederung
aktiv** pausiert beziehungsweise reaktiviert die gesamte Zuordnung, ohne sie zu
löschen. Die Ansicht **Domänen → Kapitel** gruppiert dieselben Kapitel unter
allen zugeordneten Domänen. Kapitel werden dabei nicht kopiert. Unterkapitel
erhalten eigene Zuordnungen; es gibt keine automatische Vererbung.

**Unterdomänen verwalten** pflegt die Begriffe zentral für alle Gliederungen.
Die acht Hauptdomänen sind fest vorgegeben; Domäne 8 bleibt als Platzhalter
verfügbar. Unterdomänen können angelegt und umbenannt werden. Ihre Kennungen
bleiben erhalten. Das Entfernen oder Verschieben bestehender Unterdomänen ist
noch nicht vorgesehen. Gliederungsrevisionen halten den verwendeten Namensstand
fest; ältere Revisionen werden bei Umbenennungen nicht umgeschrieben.

Die Matrix **Kapitel · Rolle · Domäne** zeigt Kombinationen mit aktiven und
inaktiven Zuordnungen. Bemerkungen können für alle oder einzelne Rollen/Domänen
gelten und die Farben Gelb, Blau, Grün, Rot oder Violett haben. Sie werden zusammen
mit der Gliederung gespeichert. **Interne Bemerkungen und Bausteinvermerke
erscheinen niemals in Word-/PowerPoint-Ausgaben**, auch nicht für HQ/intern und
auch nicht bei einem aus älteren Versionen gespeicherten Vermerkschalter.

Die Rollen-/Domänenangaben des Kapitels dienen der Redaktion und Navigation.
Die Ausgabeauswahl wird weiterhin durch die Gültigkeit der Textbausteine bestimmt.

## Quellen, Triage und Chunk-Zuordnungen

1. **Quellen & Chunks** öffnen. Dateien auswählen, Quellenart, Herkunft und
   gegebenenfalls Release ergänzen und hochladen. Exporte aus Jira, Confluence,
   Mural oder Transkriptionswerkzeugen werden als unterstützte Dateien importiert;
   direkte API-Connectoren sind noch nicht enthalten.
2. **Zielgliederung** und Verarbeitungsmodus wählen; bei der Datei **KI Triage**
   anklicken. Die Zielgliederung muss zuvor gespeichert sein.
3. Vorschläge unter **Triage-Vorschlag prüfen** kontrollieren. Rollen, Domänen,
   Stichwörter, Labels, Thema und Kapitelzuordnungen bearbeiten und bestätigen.
4. In Kapitelbaum, Domänenbaum und Matrix die bestätigten Zuordnungen verfolgen.

Der Modus **Lokale Regeln (keine KI)** ist ohne Modell nutzbar. Er verwendet
Wortüberschneidungen und einfache deutsch-/englischsprachige Begriffshinweise.
Die Ergebnisse sind Vorschläge und keine fachliche Freigabe. Eine erneute Triage
überschreibt keine bereits bestätigten Labels oder Zuordnungen.

Für **Lokale KI über Ollama** muss Ollama auf demselben Rechner unter Port 11434
laufen und das eingetragene Modell bereits installiert sein. Die Anwendung lädt
kein Modell herunter. Sie sendet Chunktext und einen begrenzten Kandidatenkatalog
an diesen lokalen Dienst: bis zu 25 anhand der Begriffe vorgewählte Kapitel,
acht Hauptdomänen und bis zu 20 Unterdomänen. Ungültige Rollen/Kapitelkennungen
werden zurückgewiesen. Bei einem KI-Fehler erfolgt kein stiller Regel-Fallback.
Die Modellanbindung wurde mit simulierten Antworten geprüft; ein realer
Modelllauf wurde in der Entwicklungsumgebung mangels installiertem Modell noch
nicht durchgeführt. Modellqualität und Laufzeit sind auf dem Zielrechner zu prüfen.

Imports sind auf 10 MB pro Datei, 300 PDF-Seiten, 2 Millionen extrahierte Zeichen
und 2000 Chunks begrenzt. Office-Dateien dürfen entpackt höchstens 32 MB groß sein.
Fundstellen benennen beispielsweise PDF-Seite, Folie oder CSV-Zeile. Identische
Dateiinhalte werden anhand ihrer Prüfsumme als bereits vorhanden erkannt.
Über **Bilder extrahieren** lassen sich eingebettete PNG/JPEG-Bilder aus DOCX/PPTX
und eingebettete Rasterbilder aus PDF in die Medienbibliothek übernehmen.
Die OCR wird dort pro Bild separat ausgelöst. Ein vollständiges PDF-Seitenrendering,
eine automatische OCR-Übernahme in Textchunks und PPTX-Sprechernotizen fehlen noch.

**Zählregeln:** Vorschläge zählen erst nach Bestätigung. Direktzuordnungen und
die Summe inklusive Unterkapiteln zählen eindeutige Chunks, keine wiederholten
Verknüpfungen. Die Domänenzähler zählen die Chunks der dort zugeordneten Kapitel;
die Domänenlabels am Chunk bleiben separat gepflegte Quellenmetadaten. Der
Rollenfilter verwendet bestätigte Chunk-Rollen. Chunks ohne Rolle zählen nur in
„Alle Rollen“. Die Matrix zählt je Kapitel und Rolle; ein Chunk kann in mehreren
Domänenzeilen erscheinen. Kopien von Gliederungen übernehmen vorhandene bestätigte
Chunk-Verknüpfungen. Die Chunk-Zähler zeigen den aktuellen Zuordnungsstand und
sind noch keine historische Auswertung alter Gliederungsrevisionen.

Chunks bleiben Quellmaterial und werden nicht automatisch in Office-Ausgaben
übernommen. Die redaktionell geprüften Dokumenttexte werden weiterhin als
Textbausteine gepflegt. **Datei löschen** entfernt Original, Chunks, Vorschläge
und deren Zuordnungen gemeinsam. Bereits erzeugte Dokumentausgaben und manuell
übernommene Texte sowie eigenständige extrahierte Medienkopien bleiben erhalten.
Unbenutzte Medienkopien können in der Medienübersicht separat endgültig gelöscht
werden; bei historischer Verwendung ist nur Archivieren vorgesehen.

## Bestehende Installation aktualisieren

Anwendung beenden, die neue ZIP in einen neuen Programmordner entpacken und dort
`start.bat` starten. Bei Verwendung des Standardpfads werden die vorhandenen Daten
unter `%LOCALAPPDATA%\oneSCM-360` wieder geladen. Bei einem benutzerdefinierten
`--data-dir` denselben Datenordner weiterverwenden. Vor dem Update bei beendeter
Anwendung eine Kopie des Datenordners sichern.

Alte Gliederungen erhalten die Metadaten-Standardwerte beim Laden; Kapitel,
Bausteine und bisherige Revisionen bleiben erhalten. Alte Historieneinträge
werden nicht umgeschrieben. Für alte Datensätze ohne eigenen Zeitstempel wird
kein ursprüngliches Erstellungsdatum erfunden.

Die Auswahl „Beide“ bei der Sparte enthält gemeinsame sowie PC-/Van-spezifische
Bausteine. Spezifische Inhalte sind entsprechend beschriftet. Markt- und
Releasebezeichnungen werden exakt verglichen; Marktgruppen und Releasebereiche
sind noch nicht implementiert. SK und KO sind vorläufige Sprachoptionen.
Übersetzungen werden manuell oder auf ausdrückliche Anforderung als lokaler KI-Vorschlag erstellt; es erfolgt keine automatische Freigabe.

Interne Inhalte werden nur in HQ-/intern-Varianten aufgenommen. Interne Vermerke
bleiben ausschließlich in der Redaktion. **Dies ist eine
Ausgaberegel, keine Anmeldung oder Zugriffskontrolle:** Die Person am lokalen
Arbeitsplatz kann alle Quelldaten sehen. Der Prototyp ist noch kein geschütztes
Mehrbenutzersystem und soll nicht über das Netzwerk bereitgestellt werden.

## Aktuelle Grenzen

Noch nicht implementiert: direkte Jira-/Confluence-Connectoren, mehrere orchestrierte
KI-Agenten, PDF/HTML-Export und hochladbare Layouttemplates. Lokale KI-Vorschläge für Übersetzung und Kürzung
sind angebunden, benötigen aber ein installiertes Ollama-Modell und fachliche Prüfung. Die zentrale Textbibliothek gilt innerhalb dieser
lokalen Datenbank; ein Abgleich mit anderen Installationen fehlt.
Gliederungsrevisionen lassen sich vergleichen; eine Wiederherstellung alter
Gliederungsstände bleibt offen. Gespeicherte Exportdateien lassen sich über den
Verwendungsnachweis erneut herunterladen.

Die Layouts sind einfache Arbeitsvorlagen. Seiten-/Folienumbrüche und Darstellung
in Microsoft Office müssen auf dem Windows-Zielsystem geprüft werden. Der lokale
Freigabeschritt prüft ein Ausgabeprofil und ersetzt kein Mehrpersonenverfahren
mit getrennten Berechtigungen. Die fachliche Richtigkeit beurteilt die Redaktion.

Pflichtkapitel oder blockierende Leerstellen verhindern die Freigabe und die
Veröffentlichung, erlauben aber ausdrücklich gekennzeichnete Prüfausgaben.
„Nur freigegebene Bausteine“ filtert Texte und ist keine Dokumentfreigabe.

## Erweiterte Gliederungsverwaltung

Der vollständige Abgleich mit der hochgeladenen Spezifikation steht in
[FUNKTIONSSTATUS.md](FUNKTIONSSTATUS.md), einschließlich Vorher-/Nachher-Status,
Restarbeiten und Abnahmekriterien.

### Erneuter Import

Im Importdialog unter **Übernahmeziel** eine vorhandene Gliederung wählen.
Nach der Strukturerkennung **Änderungen prüfen** anklicken. Eindeutige Treffer
werden vorgeschlagen; umbenannte oder mehrdeutige Kapitel müssen ausdrücklich
zugeordnet oder als neu markiert werden. Nach Änderungen am Mapping den Vergleich
aktualisieren, dann **Geprüfte Änderungen übernehmen** wählen. Der Vergleich zeigt
alte und vorgeschlagene Bäume. Fehlende alte Kapitel werden aufgelistet und am
Ende behalten; ihre Unterstruktur bleibt soweit möglich erhalten. Ein gewolltes
Entfernen erfolgt separat im Kapitelbaum. Texte, interne Vermerke, Mapping und
Chunk-Zuordnungen behalten bei zugeordneten Kapiteln ihre Kennungen. Die Zielgliederung
muss vorher gespeichert sein; zwischenzeitliche Änderungen führen zu einem Konflikt.

### Kapitelregeln und Darstellungstiefe

**Kapitelregeln & Sprachtitel** enthält Typ, Status, Pflicht-/Bedingt-/Manuell-Regel,
Leerstellenregel, erwartete Inhalte und Titel für de/en/fr/it/sk/ko. Bedingungen
nach Rolle, Umfang, Markt, Sparte, Sprache und Release wirken auch auf Unterkapitel.
Leere Bedingungen gelten für alle. Der Basistitel ist der Rückfallwert; wenn bereits
Sprachtitel gepflegt sind, erzeugt eine fehlende Sprache einen Prüfpunkt.
Titel werden nicht automatisch übersetzt.

Unter **Darstellungstiefe je Umfang** können die enthaltenen Inhaltstypen je
Gliederung gewählt werden. Voreinstellung: Kompakt enthält Anleitung, Ziel,
Voraussetzung, Schritt, Warnhinweis und Glossarbegriff; Standard zusätzlich FAQ;
Ausführlich alle Typen. Voraussetzungen, Schritte und Warnhinweise bleiben immer
enthalten. Rollen-, Sprach- und Gültigkeitsfilter gelten weiterhin.
**Inhaltstyp & Umfangsfassungen** im Baustein ermöglicht eigene Texte für jeden
Umfang. Leere Texte verwenden den Basistext. Entwurfsfassungen blockieren die
Veröffentlichung, soweit sie in der Ausgabe enthalten sind. Es gibt keine
ungeprüfte automatische Textverkürzung.

### Zentrale Inhalte und Glossar/FAQ

**Inhalte zuordnen** öffnet Zielkapitel links und Textbibliothek rechts. Filter:
Stichwort, Domäne, Rolle, Umfang, Markt, Sparte, Release, Sprache und Status.
Neue zentrale Texte können dort erstellt oder bestehende Kapiteltexte mit
**In zentraler Bibliothek speichern** übernommen werden. Das Übernehmen eines
lokalen Texts in die Bibliothek ersetzt die bisherige lokale Verwendung nicht.
Zentrale Texte besitzen eigene Revisionen, Domänen, Stichwörter und Verwendungslisten.
Archivierte Einträge stehen nicht für neue Zuordnungen bereit.

Eine Kapitelverwendung bindet eine feste zentrale Revision. Änderungen an dieser
Revision erfolgen ausschließlich in der Bibliothek; bestehende Verwendungen bleiben
unverändert. **Neueste Revision prüfen** zeigt einen kurzen Vorher-/Nachher-Ausschnitt
und übernimmt erst nach Bestätigung. Danach die vollständige Ausgabe prüfen.
Die Pfeile im Baustein ändern die Position. Zusätzliche Bedingungen je Verwendung
wirken als Schnittmenge: Ein HQ-Baustein wird durch eine Retailer-Bedingung niemals
für Retailer sichtbar. Interne Zuordnungsvermerke gelangen nicht in Ausgaben.

Für **Glossar** oder **FAQ** den Kapitelgenerator wählen und **Glossar / FAQ aus
Bibliothek vorschlagen** anklicken. Erfasst werden zentrale Einträge vom Inhaltstyp
Glossarbegriff bzw. FAQ, die zum aktuellen Profil und zu aktiven Domänen der
Gliederung passen. Einträge ohne Domäne gelten allgemein. Hauptdomänen werden bei
zugeordneten Unterdomänen mit berücksichtigt. Verpflichtende Glossarbegriffe
umgehen den Domänenfilter, aber keine Rolle, Sprache oder sonstige Gültigkeit.
Die Bibliothekstitel werden als Begriff bzw. Frage mit ausgegeben. Vorschläge werden
alphabetisch ergänzt, bereits verwendete Einträge übersprungen. Vorhandene Einträge
werden nicht automatisch aktualisiert oder entfernt. Erneut vorschlagen, wenn sich
Quellen oder Profile ändern. Semantisches Erkennen von Begriffen in Fließtext fehlt.

Der Generator **Inhaltsverzeichnis** erstellt hingegen bei jeder Vorschau/Ausgabe
die tatsächlich enthaltenen Kapitel mit Nummern, ohne Seitenzahlen.
Bild-/Klickstreckenanforderungen prüfen die tatsächlich ausgewählten freigegebenen Bildrevisionen.

### Freigabe und Ausgabennachweis

Zuerst die enthaltenen Kapitel und Texte fachlich prüfen und auf **Freigegeben**
setzen. **Profil prüfen & freigeben** prüft fehlende Pflichtinhalte, Inhaltsvorgaben,
Sprachtitel und Kapitel-/Textstatus für das aktuelle Ausgabeprofil. Die Freigabe
wird als eigene Gliederungsrevision gespeichert. Bei weiteren Änderungen beginnt
eine Entwurfsrevision; der freigegebene historische Stand bleibt erhalten.

Für eine freigegebene Office-Ausgabe **Veröffentlichung** aktivieren und Word oder
PowerPoint wählen. Ohne diesen Schalter entsteht eine Prüfausgabe. Interne Vermerke
werden in beiden Modi immer ausgeschlossen. Unter **Verwendungsnachweis** stehen
Quellenzuordnungen und erzeugte Ausgaben mit erneutem Download der Originaldatei.
Der Nachweis enthält Gliederungskennung und -revision, Profil/Release, Templateversion,
Bausteinkennungen und -fingerabdrücke, verwendete Umfangs-/Sprachfassungen sowie
zentrale Bausteinrevisionen. Sprachfassungen sind eigenständige zentrale Texte mit
eigenen Revisionen und Herkunftsrevision. Verwendete Bildrevisionen werden ebenfalls festgehalten. Frühere Exportdatensätze ohne
Gliederungskennung bleiben in SQLite erhalten, können aber nicht eindeutig zugeordnet
und deshalb nicht in dieser Übersicht angezeigt werden.

## Sicherung

Anwendung beenden und das gesamte Datenverzeichnis kopieren. Zum Wiederherstellen
die Sicherung bei beendeter Anwendung zurückkopieren oder mit `--data-dir`
starten. Diese Version hat noch keine integrierte Sicherungsoberfläche.

## Entwicklung und Prüfung

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py --data-dir /tmp/onescm-dev
```

Die Tests prüfen Importhierarchie, DOCX-Import, Variantenregeln, interne Inhalte,
Revisionen, Persistenz, HTTP-Zugriff und den tatsächlichen Inhalt beider
Office-Ausgaben. Dafür wird ausschließlich eine temporäre Testdatenbank benutzt.
Ein zusätzlicher Browserablauf steht in `tests/browser_smoke.py` bereit. Er
benötigt Playwright und Chromium (`python -m pip install playwright`, danach
`python -m playwright install chromium`). Ausführen mit
`python tests/browser_smoke.py`. Ein bereits installierter Browser lässt sich
über `ONESCM_BROWSER_PATH` auswählen. Der Test startet einen eigenen lokalen
Server und verwendet eine temporäre Datenbank; er verändert keine Benutzerdaten.
`python tests/browser_management.py` prüft zusätzlich Metadaten, manuelles
Anlegen von Kapiteln, Filter, Baumdarstellung sowie Gliederungs-/Revisionsvergleiche.
Die Modelltests umfassen auch bestehende Datenbanken ohne Metadaten und mehrdeutige
Kapitelbezeichnungen.
`python tests/browser_sources.py` prüft den gesamten neuen Ablauf: Mapping,
Unterdomänen, farbige Matrixbemerkungen, Filter, Quellenimport, lokale Regel-Triage,
bestätigte Zuordnungen, deduplizierte Zähler, Löschung und vermerkfreie Exporte.
Die Modelltests prüfen zusätzlich die Ollama-Anbindung mit simulierten Antworten,
den Erhalt von Verknüpfungen beim Speichern sowie das kaskadierende Löschen.
Der vorhandene Checkout ist bereits isoliert; zusätzliche Git-Worktrees sind
für den normalen Entwicklungsablauf nicht erforderlich.

`python tests/browser_editorial.py` prüft Reimport mit Kennungserhalt, zentrale
Bausteinverwendung, zusätzliche Gültigkeit, Sprachtitel, Freigabe, Originaldownload
und das Weiterbearbeiten als Entwurf.

## Bilder, PII und Klickstrecken

**Bilder & Klickstrecken** öffnet die zentrale Medienbibliothek. PNG/JPEG-Dateien
bis 10 MB und 16 Millionen Pixeln werden importiert; identische Bildinhalte werden
erkannt. Quellenbilder aus Word, PowerPoint und PDF können über **Quellen & Chunks →
Bilder extrahieren** übernommen werden (maximal 100 Bilder / 32 MB je Quelldatei).
Vektorgrafiken und vollständiges Rendering komplexer PDF-Seiten fehlen noch.
Extrahierte Bilder sind eigenständige Kopien; Quellenlöschung löscht sie nicht.

Im Redaktionsmodus **HQ** oder **intern** sind Originale und die Bearbeitung verfügbar.
Dieser wählbare Modus ist eine Bedienregel für einen vertrauenswürdigen lokalen
Einzelbenutzer, keine sichere Trennung mehrerer angemeldeter Personen.
**Bearbeiten / OCR / PII** öffnet das Original. Mit der Maus einen Bereich aufziehen:
**PII abdecken**, **PII stark unkenntlich machen** oder **Schritt / Text markieren**.
Die starke Unkenntlichmachung reduziert die Region auf eine unlesbare Farbfläche;
Originalpixel und Metadaten werden nicht in die ausgegebene PNG-Fassung übernommen.

**Lokale OCR & PII-Hinweise** verwendet das separat installierte Programm Tesseract
(im PATH). Die Anwendung installiert es nicht selbst. Ohne Tesseract bleiben alle
manuellen Werkzeuge verfügbar. Die Erkennung verwendet die lokal konfigurierte
Tesseract-Standardsprache; mehrsprachige OCR-Auswahl steht noch aus. Gefundene
Schlüssel wie USERID, Login, IBAN, FIN oder Kennzeichen sowie Muster für E-Mail,
IBAN und FIN erzeugen mögliche Abdeckungsregionen. Hinweise können fehlen oder
zu viel markieren. Der gesamte Screenshot, Untertitel und Markierungen müssen
visuell kontrolliert werden. Die OCR-Antwort bleibt intern und wird nicht als
Leserinhalt ausgegeben. Lokale Regeln schlagen für die gespeicherte aktuelle
Gliederung Kapitel, Domänen, Rollen und Stichwörter vor. Nach ausdrücklicher
Übernahme können Domänenlabels, Stichwörter und Labels bearbeitet werden; Kapitel
und Rollen werden als Hinweise im internen Bildvermerk gehalten, nicht automatisch
zugeordnet. Der Regelabgleich ist keine KI und kann falsch oder unvollständig sein. Ein echter OCR-Lauf wurde mit synthetischen Testdaten geprüft.

**Anonymisierte Fassung prüfen** zeigt die dauerhaft gerasterte Ausgabefassung.
Anschließend **PII-Prüfung bestätigt** setzen und bei fachlich korrektem Bild den
Status **Freigegeben** wählen. Jede Speicherung erzeugt eine eigene Bildrevision.
Die Anwendung gibt nur passende, PII-geprüfte und freigegebene Bildrevisionen aus;
Originalbilder werden auch in HQ-Ausgaben nicht eingebettet. Bestehende Zuordnungen
bleiben auf ihrer ursprünglichen Revision. Zum Aktualisieren die Zuordnung öffnen
und ausdrücklich die neue Revision auswählen.

Im Kapitel **+ Bild / Klickstrecke zuordnen** wählen. Eine Bildposition kann mehrere
Varianten enthalten (Strg + Auswahl). Die Gültigkeit am Bild und die zusätzlichen
Bedingungen der Verwendung müssen zusammenpassen. Pro Position muss genau eine
freigegebene Variante passen. Bei keiner oder mehreren passenden Varianten entsteht
ein Prüfpunkt; eine unvollständige Klickstrecke wird vollständig zurückgehalten.
Für die kombinierte Sparte „Beide“ gegebenenfalls getrennte Bildpositionen/Zuordnungen
für Van und PC verwenden, damit keine zweideutige Variante entsteht.

Klickstrecken unterstützen 1–50 geordnete Schritte, zentrale oder pro Verwendung
überschriebene Untertitel und interne Zuordnungsvermerke. Die Vorschau zeigt alle
Bilder; Word enthält die gerasterten Bilder, PowerPoint eine Folie je Schritt.
Der Verwendungsnachweis nennt Bild-ID und -revision. Unter **Endgültig löschen**
werden unbenutzte Bilder mit Original und Bildrevisionen entfernt. Eine Verwendung
in gespeicherten Gliederungsständen verhindert das Löschen; Archivieren verhindert
neue Verwendungen und erhält die historischen Stände.

## Übersetzungen und KI-Kurzfassungen

In **Inhalte zuordnen** bei einem zentralen Text **Sprachfassung anlegen** wählen.
Die neue Fassung hat eine eigene Kennung, eine Zielsprache und eine Referenz auf die
Ausgangsrevision. Text manuell übersetzen, **Übersetzung fachlich und sprachlich geprüft**
bestätigen und erst dann freigeben. Wird der Ausgangstext später geändert, erscheint
in der Bibliothek ein Aktualitätshinweis. Bestehende Übersetzungsrevisionen werden
nicht automatisch verändert. Mehrsprachige Kapitelüberschriften werden separat gepflegt.

Optional kann unter **Optionaler KI-Vorschlag (lokales Ollama)** ein bereits lokal
installiertes Modell gewählt werden. **Übersetzung vorschlagen** nutzt den gespeicherten
Ausgangstext. **Umfangsfassung vorschlagen** nutzt die gespeicherte Basisrevision und
trägt das Ergebnis in den gewählten Umfang ein. Ungespeicherte Änderungen am
Basistext gehen nicht in diese Anfrage ein. Die Anfrage enthält Titel und Text,
keine internen Vermerke. Der Benutzer übernimmt den Vorschlag ausdrücklich; er
bleibt **Entwurf**, bis er geprüft wird. Fehlende oder fehlerhafte Modellergebnisse
führen zu einer Fehlermeldung, nicht zu fingierten Übersetzungen.
Die Adapter wurden mit simulierten Modellantworten geprüft; ein echter Ollama-Lauf
steht auf dem Zielrechner aus. Begriffstreue, Grammatik und vollständiger Erhalt
wichtiger Voraussetzungen/Schritte müssen fachlich geprüft werden.

`python tests/browser_media.py` prüft Upload, gezeichnete PII-Abdeckung, Freigabe,
Klickstrecke, Bildvorschau und die tatsächlichen Bilddateien in DOCX/PPTX.
Die zusätzlichen Modelltests prüfen PDF-/Office-Bildextraktion, unveränderliche
Bildrevisionen, Löschschutz historischer Verwendungen, lokale OCR sowie
Übersetzungsherkunft und die Trennung von KI-Vorschlag und Freigabe.
