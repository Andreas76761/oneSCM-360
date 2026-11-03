# oneSCM-360 – lokales Gliederungsstudio

Erster funktionsfähiger Prototyp für die zentrale Verwaltung von Gliederungen und
die Zusammenstellung von Word-/PowerPoint-Prüfausgaben. Einzelbenutzeranwendung,
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
als entfernt/neu erscheinen. Eine manuelle Zuordnung solcher Treffer folgt später.
„Geändert“ kennzeichnet Unterschiede an Pflichtregel, Domäne, Kapitelziel oder
Textbausteinen; es ist noch kein zeilenweiser Textvergleich.

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
Inhalte werden nicht automatisch übersetzt.

Interne Inhalte werden nur in HQ-/intern-Varianten aufgenommen. Interne Vermerke
erscheinen zusätzlich nur bei aktiviertem Vermerkschalter. **Dies ist eine
Ausgaberegel, keine Anmeldung oder Zugriffskontrolle:** Die Person am lokalen
Arbeitsplatz kann alle Quelldaten sehen. Der Prototyp ist noch kein geschütztes
Mehrbenutzersystem und soll nicht über das Netzwerk bereitgestellt werden.

## Aktuelle Grenzen

Noch nicht implementiert: Bildverwaltung und PII-Bereinigung, OCR,
Klickstrecken, zentrale projektübergreifende Bausteinbibliothek,
Quellenextraktion aus PDF/PPTX, Jira-/Confluence-Connectoren, KI-Agenten,
automatische Glossar-/FAQ-Erzeugung, Übersetzungsworkflow, vollständige
Freigabeverfahren, PDF/HTML-Export und eigene hochladbare Layouttemplates.
Gliederungsrevisionen lassen sich vergleichen; eine Wiederherstellung alter
Stände sowie eine Oberfläche für archivierte Exportdateien folgen später.
Die aktuell erzeugten Layouts sind einfache
Arbeitsvorlagen. Seiten-/Folienumbrüche und Darstellung in Microsoft Office
müssen auf dem Windows-Zielsystem geprüft werden.

Pflichtkapitel warnen bei fehlendem Inhalt; ein Export bleibt zur redaktionellen
Prüfung möglich und trägt deshalb immer die Kennzeichnung PRÜFAUSGABE.
Die Auswahl „Nur freigegebene Bausteine“ ist noch keine Dokumentfreigabe.

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
Der vorhandene Checkout ist bereits isoliert; zusätzliche Git-Worktrees sind
für den normalen Entwicklungsablauf nicht erforderlich.
