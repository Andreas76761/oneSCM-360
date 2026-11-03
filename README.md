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
- Gliederungsimport per eingefügtem Text, TXT, Markdown oder DOCX bis 5 MB;
  Vorschau mit korrigierbaren Titeln und Ebenen. DOCX nutzt Überschriftstile;
  ohne diese werden Absätze übernommen und eine Warnung angezeigt.
- Kapitel und Unterkapitel (bis Ebene 6), Pflichtkapitel, Ziele und Domänen.
- Verschieben vollständiger Teilbäume mit stabilen Kapitelkennungen.
- Textbausteine mit Rolle, Markt, Sparte, Sprache, Release, Umfang, Quelle,
  Status und internen Vermerken.
- Nachvollziehbare Vorschau mit Ausschlussgründen und fehlenden Pflichtinhalten.
- DOCX und PPTX als **Prüfausgaben**, einschließlich Fortsetzungsfolien bei
  langen Texten. Keine automatische inhaltliche Kürzung.
- Lokale Speicherung mit Revisionen und Schutz vor veralteten Schreibzugriffen.
  Exportplan und erzeugte Datei werden gemeinsam in der Datenbank archiviert.

## Bedienablauf

1. Gliederung anlegen oder importieren; Pflichtkapitel kontrollieren.
2. Kapitel wählen, Domäne und Ziel ergänzen, Textbausteine anlegen.
3. Gültigkeit pro Baustein eintragen: `*` bedeutet alle, ein leeres Markt- oder
   Releasefeld bedeutet ungeklärt und verhindert die Aufnahme.
4. Das Ausgabeprofil oben wählen und „Ausgabe prüfen“ öffnen.
5. Änderungen speichern; Word oder PowerPoint herunterladen.

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
Revisionen und Exporte sind gespeichert, eine Oberfläche für deren Vergleich
und Wiederherstellung folgt später. Die aktuell erzeugten Layouts sind einfache
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
Der vorhandene Checkout ist bereits isoliert; zusätzliche Git-Worktrees sind
für den normalen Entwicklungsablauf nicht erforderlich.
