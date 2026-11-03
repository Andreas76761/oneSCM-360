# oneSCM-360 · Dokumentstudio

**Prototyp 0.4.0 · Stand 03.11.2026**

Lokale Plattform für Gliederungen, wiederverwendbare Texte, Quellen und Screens.
Aus derselben Wissensbasis entstehen rollen-, markt-, sparten- und sprachabhängige
Manuals, Releaseletter und Quick References. Ausgabeformate: **Word, PowerPoint,
PDF und HTML**. Die Anwendung ist für einen vertrauenswürdigen Benutzer an einem
lokalen Windows-Arbeitsplatz ausgelegt.

Jira und Confluence werden entsprechend der festgelegten Arbeitsweise **über
HTML-/Word-Exporte und die Zwischenablage** eingebunden. Direkte Verbindungen,
Zugangsdaten oder Synchronisierung mit diesen Systemen sind nicht Bestandteil des
aktuellen Auftrags. Optionale KI-Verarbeitung erfolgt über ein selbst betriebenes
Ollama auf demselben Rechner; ohne Modell stehen lokale Regeln und manuelle
Bearbeitung zur Verfügung.

## Downloads und Dokumentation

- [Aktuellen Prototyp als ZIP herunterladen](https://github.com/Andreas76761/oneSCM-360/archive/refs/heads/main.zip)
- [Bedienungsanleitung](docs/BEDIENUNG.md)
- [Vollständiger Funktionsstand](FUNKTIONSSTATUS.md)
- [Verbesserungen mit Priorität, Aufwand und Abnahmekriterien](docs/VERBESSERUNGEN.md)

Die ZIP enthält Frontend unter `web/`, lokalen Python-Server, Startskript,
Dokumentation und Tests. Sie enthält keine Benutzerdatenbank, Quellen oder
Originalscreens. Das Frontend wird über den lokalen Server geöffnet; `index.html`
allein bildet die Anwendung nicht ab.

## Start unter Windows

Voraussetzung: Python 3.11 oder neuer mit Windows-Python-Launcher `py`.

1. ZIP entpacken, beispielsweise nach `C:\oneSCM-360`.
2. `start.bat` doppelklicken. Das Skript erzeugt eine virtuelle Umgebung,
   installiert die Python-Abhängigkeiten und öffnet den Browser.
3. Die Anwendung läuft unter `http://127.0.0.1:8765`.
4. Zum Beenden im Konsolenfenster **Strg+C** drücken.

Für die erste Paketinstallation ist Internetzugriff nötig. Die spätere lokale
Dokumentenverarbeitung benötigt keine direkte Jira-/Confluence-Verbindung.

Alternativ in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py --open-browser
```

Daten liegen standardmäßig unter
`%LOCALAPPDATA%\oneSCM-360\onescm.sqlite3`, außerhalb des Programmordners.
Mit `--data-dir PFAD` lässt sich ein anderer lokaler Datenordner wählen. Die aktive
SQLite-Datei nicht parallel über OneDrive, SharePoint oder ein Netzlaufwerk
bearbeiten. Für Sicherungen die Anwendung beenden und den gesamten Datenordner
kopieren.

Optionale lokale Programme:

| Programm | Zweck | Ohne dieses Programm |
|---|---|---|
| Tesseract im `PATH` | OCR und Hinweise auf mögliche PII in Bildern | Manuelle PII-Markierung und Bildverwaltung nutzbar |
| Ollama, Port `11434`, bereits installiertes Modell | KI-Triage, Übersetzungs- und Kürzungsvorschläge | Regel-Triage, manuelle Texte und Sprachfassungen nutzbar |
| Antiword im `PATH` | Texte aus alten binären `.doc`-Dateien | Datei in Word als DOCX speichern; HTML-basierte DOC-Exporte funktionieren direkt |

Die Anwendung installiert oder lädt diese optionalen Programme und KI-Modelle
nicht automatisch. PDF-Erzeugung erfolgt lokal mit ReportLab; hierfür ist kein
installiertes Microsoft Office erforderlich.

## Funktionen dieser Version

| Bereich | Umsetzung |
|---|---|
| Gliederungen | Zentrale Übersicht, Metadaten, stabile Kapitelkennungen, aufklappbare Bäume, Kopien, Versionsvergleich, geprüfter Reimport |
| Steuerung | Acht Hauptdomänen mit Unterdomänen, Mehrfachmapping, farbige interne Matrixbemerkungen, Suche und Chunk-Zähler |
| Quellen | Datei- und Zwischenablageimport, Text-/Tabellenextraktion, prüfbare Triage, Quellenübersicht und Löschung |
| Texte | Zentrale revisionierte Bibliothek, Kapitelzuordnung, eigene Umfangsfassungen und Sprachfassungen |
| Jira-Verifikation | Ticketnummer, Status, Typ, Datum und Prüfvermerk pro Text; ausschließlich interne Nachweise |
| Dokumenteignung | Auswahl pro Text für Manual, Releaseletter und Quick Reference; Übersicht der tatsächlich verwendeten Inhalte |
| Zeit und Version | Stichtag, Prod/Preprod, Gültigkeitszeiträume, Jahr, Land, Rolle, Sparte und Status; gespeicherte Stände im Zeitverlauf |
| Screens | Uploadlabels, Profil, Priorität, Filter und Sortierung; PII-Abdeckung, Markierungen, Varianten, Bildrevisionen und Klickstrecken |
| Layouttemplates | Versionierter DOCX-/PPTX-Upload, feste Auswahl je Gliederung und portable Farben/Schriftgröße |
| Markdown → Word | Stapelkonvertierung mit formatierten Überschriften, Listen, Tabellen, Hervorhebungen, Links und Code |
| Ausgaben | DOCX, PPTX, PDF und selbstständige HTML-Datei; gemeinsame Auswahl- und Freigaberegeln |
| Agentenläufe | Gespeicherte Eingabestände, Fachschritte, Fortschritt, Pause/Abbruch, Prüfung und ausdrückliche Übernahme |
| Internes Register | Testing, UI, Steuerung und IT mit Unterthemen, Mehrfachzuordnung, Revisionen und ausschließlich internen FAQ-Kandidaten |
| Nachvollziehbarkeit | Gliederungs-, Text-, Sprach-, Bild- und Templaterevisionen sowie Originaldownload erzeugter Ausgaben |

## Empfohlener erster Ablauf

1. Gliederung anlegen oder importieren, Pflichtkapitel und Domänen prüfen.
2. Unter **Quellen & Chunks** einen HTML-/Word-Export oder eingefügten Text
   aufnehmen und Triage-Vorschläge kontrollieren.
3. Texte in **Inhalte zuordnen** pflegen. Dokumenteignung, Jira-Nachweise und
   Gültigkeit festlegen; zentrale Revisionen den Kapiteln zuweisen.
4. Screens unter **Bilder & Klickstrecken** importieren, PII bearbeiten,
   Ausgabefassung visuell prüfen und geeignete Bildrevisionen zuordnen.
5. Ausgabeprofil und bei Zeitregeln einen **Stichtag** wählen. Unter
   **Verwendung & Zeit** die Auswahl der drei Dokumentarten vergleichen.
6. **Layouttemplates** wählen, speichern und **Ausgabe prüfen** öffnen.
7. Zunächst eine Prüfausgabe herunterladen. Nach fachlicher Prüfung aller Inhalte
   **Profil prüfen & freigeben** ausführen. Für die endgültige Ausgabe
   **Veröffentlichung** aktivieren und das gewünschte Format wählen.

Die separate Funktion **Markdown → Word** ist auch ohne Kapitelaufbau nutzbar.
Sie konvertiert ausgewählte Markdown-Dateien als einzelne DOCX-Dateien in einer ZIP
oder als gemeinsames Word-Dokument. Sie erstellt dabei keine fachliche Freigabe.

## Auswahl- und Datenschutzregeln

Interne Vermerke und strukturierte Jira-Nachweise gehören nicht zum Leserinhalt.
In der Dokumenterzeugung werden die verknüpften Ticketnummern und zugehörigen
`/browse/`-Links zusätzlich aus dem Lesertext entfernt. Das ist kein allgemeiner
Suchlauf nach beliebigen vertraulichen Inhalten. Nicht verknüpfte Referenzen,
Screens, Layoutkopfzeilen und separat konvertierte Markdown-Dateien müssen in der
Redaktion geprüft werden.

Ausgegeben werden ausschließlich passende, PII-geprüfte und freigegebene
Bildrevisionen. Originalbilder gelangen nicht in die Ausgabedateien. Die wählbare
Redaktionsrolle HQ/intern ist eine Bedienregel, **keine Anmeldung oder sichere
Mehrbenutzer-Zugriffskontrolle**. Die Anwendung nur am vertrauenswürdigen lokalen
Einzelarbeitsplatz betreiben.

Ausgabeprofile und Agenten ersetzen keine fachliche Entscheidung. Der Status eines
Jira-Tickets allein bestätigt nicht die Richtigkeit eines Textes. KI-Ergebnisse
bleiben Vorschläge; eine Veröffentlichung wird nicht durch einen Agentenlauf
ausgelöst.

Das **Interne Register · FAQ** bleibt einschließlich Frage-Antwort-Paaren aus allen
Leserausgaben ausgeschlossen, auch bei HQ/intern. Die lokale FAQ-Vorschau liefert
freigegebene, vorgemerkte Einträge. Ein antwortgenerierender Chatbot ist noch offen.

## Aktualisierung und Sicherung

Anwendung beenden, Datenordner sichern und die neue ZIP in einen neuen
Programmordner entpacken. Anschließend dort `start.bat` starten. Bei Verwendung
des Standard-Datenpfads werden die bisherigen Inhalte wieder geladen. Bei einem
eigenen `--data-dir` denselben lokalen Datenordner weiterverwenden.

Neue Tabellen und Standardwerte werden ergänzt; vorhandene Historieneinträge
werden nicht umgeschrieben. Erzeugte Dateien behalten ihren ursprünglichen Stand.
Eine Sicherungsoberfläche und das Wiederherstellen einer alten Gliederung als
neue Revision sind noch nicht enthalten.

## Grenzen und Abnahme

Native Office-Templates übernehmen Formatvorlagen, Kopf-/Fußzeilen beziehungsweise
Master und Folienformat. Die Anwendung ist kein allgemeiner Platzhalter- oder
Layoutdesigner. Eigene Corporate-Design-Muster, lange Tabellen, Bilder, Umbrüche und
Schriften sind mit den tatsächlichen Word-/PowerPoint-Versionen unter Windows
abzunehmen. HTML/PDF verwenden das portable Layout; sie reproduzieren nicht
pixelgenau ein Office-Template.

Die PDF-Schriftwahl nutzt lokal verfügbare Unicode-Schriften; für Koreanisch ist ein
CJK-Schriftpfad vorgesehen. Ein vollständiger Test der vorgesehenen Sprachen und
Schriftsysteme auf dem Zielrechner steht aus. Die konkrete Darstellung von
Sonderzeichen und Screens ist Teil der Abnahme.

Ollama-Adapter lassen sich mit simulierten Antworten prüfen. Ein echter lokaler
Modelllauf und die fachliche Qualität seiner Antworten sind gesondert auf dem
Zielrechner zu prüfen. Die vorhandene Tesseract-Integration wurde mit synthetischen
Bildern erprobt; sie garantiert keine vollständige PII-Erkennung.

## Entwicklung und Tests

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py --data-dir /tmp/onescm-dev
```

Die automatisierten Tests arbeiten mit temporären Datenbanken. Browserabnahmen
benötigen zusätzlich Playwright und Chromium:

```sh
python -m pip install playwright
python -m playwright install chromium
python tests/browser_smoke.py
python tests/browser_management.py
python tests/browser_sources.py
python tests/browser_editorial.py
python tests/browser_media.py
python tests/browser_publishing.py
```

Ein vorhandener Browser lässt sich über `ONESCM_BROWSER_PATH` auswählen. Weitere
Abnahmetests für Veröffentlichung, Agentenläufe und die neuen Oberflächen befinden
sich im Verzeichnis `tests/`. Das Ergebnis des vollständigen Abschlusslaufs wird
bei der Auslieferung berichtet; aus dem Vorhandensein eines Tests folgt keine
Abnahme auf dem Windows-Zielrechner.
