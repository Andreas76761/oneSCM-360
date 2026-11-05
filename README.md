# oneSCM-360 · Dokumentstudio

**Prototyp 0.10.0 · Stand 05.11.2026**

Lokale Plattform für Gliederungen, wiederverwendbare Texte, Quellen und Screens.
Aus derselben Wissensbasis entstehen rollen-, markt-, sparten- und sprachabhängige
Manuals, Releaseletter und Quick References. Ausgabeformate: **Word, PowerPoint,
PDF und HTML**. Die Anwendung ist für einen vertrauenswürdigen Benutzer an einem
lokalen Windows-Arbeitsplatz ausgelegt.

Jira und Confluence werden entsprechend der festgelegten Arbeitsweise **über
HTML-/Word-Exporte und die Zwischenablage** eingebunden. Direkte Verbindungen,
Zugangsdaten oder Synchronisierung mit diesen Systemen sind nicht Bestandteil des
aktuellen Auftrags. Die Anwendung benötigt weder einen KI-API-Vertrag noch
Ollama. Vorhandene Chat-Abonnements von **Microsoft 365 Copilot, Claude oder
Gemini** werden über einen manuellen Austausch genutzt: ausgewählten Auftrag
prüfen und kopieren, im jeweiligen Chat bearbeiten, Antwort zurückbringen und
vor Übernahme kontrollieren. Eine direkte API-Anbindung dieser Dienste besteht
nicht. Ein bereits installiertes lokales Ollama-Modell bleibt eine zusätzliche
Option; Regeln und manuelle Redaktion funktionieren ohne KI-Modell.

## Downloads und Dokumentation

- [Aktuellen Prototyp als ZIP herunterladen](https://github.com/Andreas76761/oneSCM-360/archive/refs/heads/main.zip)
- [Aktualisierung: alte Oberfläche ersetzen](docs/AKTUALISIERUNG.md)
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
| Ollama, Port `11434`, bereits installiertes Modell | Optionale direkte lokale Modellaufrufe | Regeln, manuelle Redaktion und Austausch mit vorhandenen Chat-Abonnements nutzbar |
| Antiword im `PATH` | Texte aus alten binären `.doc`-Dateien | Datei in Word als DOCX speichern; HTML-basierte DOC-Exporte funktionieren direkt |

Die Anwendung installiert oder lädt diese optionalen Programme und KI-Modelle
nicht automatisch. Ein Copilot-, Claude- oder Gemini-Chat-Abonnement ersetzt keine
API-Berechtigung; der manuelle Austausch benötigt keine API-Schlüssel. PDF-Erzeugung erfolgt lokal mit ReportLab; hierfür ist kein
installiertes Microsoft Office erforderlich.

## Neu in Version 0.6.0

- **KI-Austausch:** ausgewählte Quelltexte für Microsoft 365 Copilot, Claude oder
  Gemini vorbereiten, prüfen und kopieren; JSON-Antwort zurückbringen und als
  Bibliotheksentwurf übernehmen. Keine direkte API-Verbindung, keine automatische
  Übertragung oder Freigabe.
- **Designstudio:** Farben für Kapitel, Unterkapitel und Hinweise, Schrift,
  Bildbreite, Beschriftungen, Nummerierung, Symbole und Stichworthervorhebung je
  Gliederung bearbeiten; native Office-Templates fest auswählen.

- **Interner Chatbot:** antwortet mit freigegebenen FAQ-Belegen für Land, Rolle,
  Sparte, Sprache, Stichtag und Umgebung. Historische Belege sind nachvollziehbar;
  fehlende oder widersprüchliche Antworten werden kenntlich gemacht. Optional
  wählt ein lokales Modell wörtliche Zitate aus, ohne freie Antworten zu erzeugen.
- **Releaseverwaltung:** ein geprüftes Paket führt lokale Dokumentationsstände
  von Preprod nach Prod. Alle bisher aktiven Profile müssen enthalten sein.
  Vorschau, begründete Aktivierung und Rücknahme sind nachvollziehbar.
- **Quellenwidersprüche:** Regeln erkennen mögliche Zahlen-/Verneinungsabweichungen
  und Dubletten; manuelle oder lokale KI-Paarprüfung ergänzt die Hinweise.
  Die Redaktion entscheidet mit Begründung.
- **Jira-HTML-Import:** ticketweise Aufbereitung mit Überschriften,
  Bereinigung erkannter Personenfelder und PII vor der Speicherung sowie
  Fortschritt, Pause/Fortsetzen und Abbruch. Unterschiedliche Exportvarianten und die Vollständigkeit
  der Bereinigung müssen fachlich geprüft werden.

Wenn weiterhin die alte Oberfläche erscheint, zuerst den bisherigen Server in
seiner Konsole mit **Strg+C** beenden. Datenordner sichern, neue ZIP in einen neuen
Ordner entpacken, dort `start.bat` starten und den Browser mit **Strg+F5** neu laden.
Oben rechts muss **v0.6.0 · 04.11.2026** stehen. Einzelheiten und Fehlerhilfe:
[Aktualisierung](docs/AKTUALISIERUNG.md).

## Funktionen dieser Version

| Bereich | Umsetzung |
|---|---|
| Gliederungen | Zentrale Übersicht, Metadaten, stabile Kapitelkennungen, aufklappbare Bäume, Kopien, Versionsvergleich, geprüfter Reimport |
| Steuerung | Acht Hauptdomänen mit Unterdomänen, Mehrfachmapping, farbige interne Matrixbemerkungen, Suche und Chunk-Zähler |
| Quellen | Datei- und Zwischenablageimport, Jira-HTML ticketweise, Text-/Tabellenextraktion, prüfbare Triage, Quellenübersicht und Löschung |
| Quellenprüfung | Herkunft und Gültigkeitskontext, belegte Prüfpunkte, begründete Entscheidungen und Entscheidungshistorie |
| Texte | Zentrale revisionierte Bibliothek, Kapitelzuordnung, eigene Umfangsfassungen und Sprachfassungen |
| Jira-Verifikation | Ticketnummer, Status, Typ, Datum und Prüfvermerk pro Text; ausschließlich interne Nachweise |
| Dokumenteignung | Auswahl pro Text für Manual, Releaseletter und Quick Reference; Übersicht der tatsächlich verwendeten Inhalte |
| Zeit und Version | Stichtag, Prod/Preprod, Gültigkeitszeiträume, Jahr, Land, Rolle, Sparte und Status; gespeicherte Stände im Zeitverlauf |
| Releasepakete | Vollständige Profilabdeckung, Vergleich, manuelle atomare Promotion und Rücknahme lokaler Dokumentationsstände |
| Screens | Uploadlabels, Profil, Priorität, Filter und Sortierung; PII-Abdeckung, Markierungen, Varianten, Bildrevisionen und Klickstrecken |
| Layouttemplates und Design | Versionierter DOCX-/PPTX-Upload, feste Auswahl je Gliederung; eigenes Designstudio mit Farben, Schrift, Bildern und schematischer Vorschau |
| Manuelle KI-Nutzung | Aufträge für Copilot-/Claude-/Gemini-Chats kopieren oder herunterladen; Antworten prüfen und ausdrücklich als Entwurf übernehmen |
| Markdown → Word | Stapelkonvertierung mit formatierten Überschriften, Listen, Tabellen, Hervorhebungen, Links und Code |
| Ausgaben | DOCX, PPTX, PDF und selbstständige HTML-Datei; gemeinsame Auswahl- und Freigaberegeln |
| Interne FAQ und Chat | Separates Register, freigegebene profilgerechte Antwortbelege, Revisionen und Warnung bei veralteten Belegen |
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

Für vorhandene Chat-Abonnements **KI-Austausch · Copilot / Claude / Gemini**
verwenden. Die [Bedienungsanleitung](docs/BEDIENUNG.md#16-mit-copilot-claude-oder-gemini-über-den-chat-arbeiten)
beschreibt Auswahl, Prüfung und Übernahme.

Vor einem neuen Release unter **Quellenwidersprüche** den Kontext der Exporte
pflegen und Hinweise klären. **Releaseverwaltung** aktiviert anschließend ein
geprüftes Dokumentationspaket; sie steuert weder das oneSCM-System noch einen
automatischen Vierwochen-Termin.

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
freigegebene, vorgemerkte Einträge. Der separate **Interne Chatbot** beantwortet
Fragen mit solchen Belegen. Auch seine Antworten und Quellenzitate bleiben intern.
Ein freies generatives RAG über sämtliche Quellen ist nicht implementiert.

## Aktualisierung und Sicherung

Die vollständige [Updateanleitung](docs/AKTUALISIERUNG.md) erklärt auch die weiterhin
sichtbare alte Oberfläche. Alten Server mit **Strg+C** beenden, den in seiner
Konsole genannten Datenordner sichern und die neue ZIP in einen neuen
Programmordner entpacken. Anschließend dort `start.bat` starten und mit **Strg+F5**
die Frontend-Version prüfen. Bei Verwendung
des Standard-Datenpfads werden die bisherigen Inhalte wieder geladen. Bei einem
eigenen `--data-dir` denselben lokalen Datenordner weiterverwenden.

Neue Tabellen und Standardwerte werden ergänzt; vorhandene Historieneinträge
werden nicht umgeschrieben. Erzeugte Dateien behalten ihren ursprünglichen Stand.
Die Sicherungsoberfläche erstellt konsistente ZIP-Sicherungen und stellt den gesamten Arbeitsbereich nach Prüfung wieder her. Das allgemeine Wiederherstellen einzelner alter Gliederungsstände ist noch nicht enthalten. Die Releaseverwaltung kann das
aktuell aktive Releasepaket unter den beschriebenen Bedingungen zurücknehmen.

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
python tests/browser_knowledge.py
```

Ein vorhandener Browser lässt sich über `ONESCM_BROWSER_PATH` auswählen. Weitere
Abnahmetests für Veröffentlichung, Agentenläufe und die neuen Oberflächen befinden
sich im Verzeichnis `tests/`. Das Ergebnis des vollständigen Abschlusslaufs wird
bei der Auslieferung berichtet; aus dem Vorhandensein eines Tests folgt keine
Abnahme auf dem Windows-Zielrechner.

Prüfstand v0.6.0: 132 automatisierte Tests und neun Chromium-Browserabläufe erfolgreich. Windows-/Office-Abnahme bleibt erforderlich.


## Neu in v0.6.0

- **Sicherung & Wiederherstellung:** Gesamten Arbeitsbereich als konsistente ZIP
  herunterladen; Sicherung prüfen und bewusst zurückspielen. Vorher wird eine
  Rücksicherung unter `backups` im Datenordner angelegt. ZIPs enthalten auch interne
  Informationen und Originalscreens und sind unverschlüsselt. Wiederherstellung
  derzeit nur mit derselben Programmversion, maximal 128 MB ZIP / 512 MB Datenbank.
- **Dokumentvarianten erzeugen:** Sprachen, Rollen, Dokumentarten und Formate
  kombinieren; Vorschau mit Prüfpunkten; bis 60 Prüfausgaben als ZIP mit Prüfbericht.
  Keine automatische Übersetzung oder Freigabe. Markt, Sparte und Umfang stammen
  aus der gespeicherten Gliederung.
- **CI vorbereitet:** Python-Tests unter Windows/Linux und Chromium-Browserabläufe
  in GitHub Actions. Lokale Tests ersetzen keine fachliche Windows-/Office-Abnahme.

Neu in v0.6.1: Quellen nach DOCX/PDF/Markdown/HTML filtern, Dateien markieren, gemeinsam triagieren und extrahierte Texte bearbeiten, als Auszüge zusammenstellen oder als neue Markdown-Quelle speichern/herunterladen.


## Neu in v0.7.0: RAG · Zentrales Wissen

Registerübergreifende lokale Belegsuche verbindet Quellen, Bibliothek, Kapitel,
interne FAQ/Vermerke, offene Aufträge, Screens, Chatfragen, Domänen, Designs,
Releasepakete und Quellenprüfungen. Rollen-/Sprach-/Marktfilter und aktuelle
Fundstellenstände werden bei jeder Suche angewandt. Antworten zeigen vollständige
freigegebene Textbelege; ohne externes Modell, ohne Embeddings und ohne freie
KI-Generierung. Interne Treffer bleiben von Leser-Kapitelentwürfen ausgeschlossen.
Neue Kapitel lassen sich rollen-/sprachgebunden in bestehende Gliederungen einfügen;
geprüfte Screens können neuen oder bestehenden Kapiteln zugeordnet werden.


## Ausbau v0.8.0 / v0.8.1

- Designstudio ohne Gliederung: Quelldatei auswählen oder hochladen, Palette und
  Typografie festlegen, Vorher/Nachher als aufbereiteten Inhalt vergleichen und
  eine neue Word-/PowerPoint-/PDF-/HTML-Prüfausgabe herunterladen.
- Eigene Designpatterns werden mit Revisionen gespeichert. Kapitel, Unterkapitel
  und Fließtext besitzen getrennte Schriften, Größen und Zeilenabstände. Hinweis,
  Achtung, Ausnahme und Tipp erhalten eigene Hintergründe, Rahmen und Icons.
- Neues Register **Agenten · Orchestrator** mit den acht vereinbarten Aufgaben,
  gespeicherten Eingaberevisionen, schrittweiser Ausführung, Pause/Abbruch und
  internen Ergebnisberichten. Übersetzungen erfolgen als manueller Chat-Austausch
  aus freigegebenen Bibliotheksrevisionen; Übernahme bleibt ein Entwurf.
- Die zuvor erstellte RAG-Basis ist enthalten. v0.7.0 wurde nicht separat publiziert.

Prüfstand v0.8.1: 151 automatisierte Tests einschließlich HTTP erfolgreich. Chromium-Abnahmen für Designstudio/Agenten, Publikation und RAG erfolgreich. Windows-/Microsoft-Office-Abnahme bleibt offen.

Neu in v0.8.1: Klassifikations-, Wissens- und Medienvorschläge im Orchestrator bearbeiten, ausdrücklich prüfen und einzeln übernehmen. Herkunft, Übernahmezeit und Ziel werden protokolliert. Doppelte Übernahmen und veraltete Eingaben werden abgefangen; Wissensobjekte bleiben Entwürfe.


## Dashboard v0.8.2

Das neue Register **Dashboard** zeigt Dokument-/Quellenanzahl, Bilder, freigegebene PII-geprüfte Bilder, Gliederungen, Chunks, Bibliotheksbausteine und gespeicherte Ausgaben. Die Speicheranzeige unterscheidet Anwendungsdaten (Datenbank samt Begleitdateien) und Gesamt-/Belegt-/Freispeicher des Datenbanklaufwerks. Mit **Kennzahlen aktualisieren** werden die Werte neu ermittelt.


## Neu in v0.8.4

Persistente interne Sprach-/Datums-/Versionsflags für Quellen, Screens und interne Notizen, mit Analysevorschlag, manueller Bestätigung und Veraltet-Erkennung. Optionale lokale Tesseract-Analyse für Screens. Kapitelbezogene Bildaktivierung nach Ausgabe-Release und Domäne; keine Löschung und keine Übernahme interner Vermerke in Lesertexte. Details: Bedienung Kapitel 25–26.


OCR-Ausbau v0.8.4: persistierte interne Zeilenfundstellen mit Positionen, Bildrevision und Veraltet-Erkennung; aktuelle Ergebnisse über interne RAG-Suche auffindbar. Details in Bedienung Kapitel 27.


## Neu in v0.9.0

Neunter Agent: Audit Agent mit internen PII-Fundstellen. Aktuelle Lesertexte werden vor Export regelbasiert geprüft; Treffer blockieren die Ausgabe. Bekannte unmaskierte OCR-Bereiche werden ebenfalls abgefangen. Drei Design-Startvorlagen für Handbuch, Releaseletter und Quick Reference stehen im Designstudio bereit. Grenzen und Bedienung: Kapitel 28–29 der Dokumentation.


## Neu in v0.10.0

Anhang mit fünf Registern: Glossar, Abkürzungen, Synonyme, FAQs und Vorschau. Persistente DE/EN/FR-Sprachfassungen mit getrennter Bestätigung, internen Vermerken und expliziter Übernahme in Gliederungen. Interne Einträge und Vermerke werden nicht in Lesertexte kopiert. Bedienung: Kapitel 30.
