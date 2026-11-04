# Verbesserungen und verbleibender Aufwand

Stand **v0.8.1 · 04.11.2026**. Die Zahlen sind grobe Restaufwände in Personentagen
(PT) zu acht Stunden für eine entwickelnde Person einschließlich gezielter Tests.
Sie sind keine Zusagen. Wartezeit auf fachliche Entscheidungen, Muster, Hardware
und Freigaben kommt hinzu. Überschneidungen zwischen Aufgaben verhindern eine
sinnvolle pauschale Addition aller Schätzungen.

P0 = vor verlässlichem Alltagseinsatz abnehmen, P1 = nächster Ausbau,
P2 = späterer Ausbau nach Bedarf. Rechte sind nur dann P0, wenn der derzeitige
vertrauenswürdige Einzelarbeitsplatz für weitere Benutzer geöffnet werden soll.

In v0.5.0 vorhanden und daher nicht mehr als vollständig fehlend bewertet:
beleggestützter interner FAQ-Chat, manuelle atomare Dokumentations-Releasepromotion
mit Rücknahme, regelbasierte Quellenkonflikte mit manueller/lokaler KI-Paarprüfung,
manueller Chat-Auftragsaustausch und ein eigenes Designstudio.
Weitere Qualität, Skalierung und Automatisierung dieser Funktionen bleiben separate
Aufgaben. Die folgenden Schätzungen beziehen sich auf diese Restarbeiten.

| Priorität | Verbesserung | Restaufwand | Voraussetzung / Abhängigkeit | Abnahmekriterium |
|---|---|---:|---|---|
| P0 | Windows- und Microsoft-Office-Abnahme | 2–4 PT | Zielrechner, reale Word-/PPTX-Muster, lange Dokumente und geplante Sprachen | Start und Update mit vorhandenen Daten; reale Vorlagen, Umbrüche, PDF-Schriften und Koreanisch nachvollziehbar abgenommen |
| P0 | Jira-HTML-Bereinigung mit Exportvarianten abnehmen | 2–4 PT | Repräsentative lokal verwaltete Exporte und fachlich markierte PII-Beispiele | Ticketanzahl und Fundstellen stimmen; bekannte Personenfelder entfernt; bereinigte gespeicherte Datei geprüft; Abbruch und Neuimport verständlich. Keine Behauptung vollständiger PII-Erkennung |
| P1 | Sicherungen verschlüsseln und Aufbewahrung automatisieren | 2–4 PT | ZIP-Sicherung und geprüfte Wiederherstellung in v0.6.0 umgesetzt; Schlüssel-/Speicherkonzept | Geschützte Sicherungen, definierte Aufbewahrung und Wiederherstellung großer Bestände; derzeit gleiche Programmversion, 128 MB ZIP / 512 MB Datenbank |
| P0 bei Mehrbenutzeröffnung | Anmeldung und serverseitige Zugriffsrechte | 8–15 PT | Festgelegte Benutzer-/Rechtematrix, Betriebsentscheidung | Rechte für interne FAQ, Originalbilder und Verwaltung serverseitig erzwungen; Tests verweigern unberechtigten Zugriff auch außerhalb der UI |
| P1 | Fachliche FAQ-/Chat-Abnahme | 3–5 PT | Freigegebener Fragekatalog je Sprache, Rolle und Markt | Relevanz, keine-Belege-Fälle, veraltete Belege und widersprüchliche Antworten gegen manuell bewertete Referenzen gemessen; lokale KI-Belegauswahl am echten Modell geprüft |
| P1 | Quellenkonflikte semantisch und mehrsprachig verbessern | 4–7 PT | Echte Konflikt-/Nichtkonflikt-Paare mit Versionskontext | Regeln und Modellbefunde auf Referenzfällen bewertet, Fehler nachvollziehbar; Entscheidungen bleiben menschlich und belegt; keine automatische Textüberschreibung |
| P1 | Reale KI- und Übersetzungsqualität abnehmen | 4–7 PT | Vorhandene Copilot-/Claude-/Gemini-Chats oder optional lokales Modell; mehrsprachige Fachprüfer | Manuell ausgetauschte Antworten und optionale lokale Triage, Kürzung und Übersetzung gegen Referenzfälle gemessen; Terminologie, Auslassungen und falsche Aussagen dokumentiert; keine ungeprüfte automatische Veröffentlichung |
| P1 | Releaseprofil-Katalog und planbare Termine | 3–5 PT | Verbindliche Markt-/Rollen-/Spartenliste, vorhandene Promotion | Schon das erste Paket gegen Sollprofile prüfen; Erinnerungen/Fälligkeiten anzeigen; Aktivierung bleibt ausdrücklich bestätigt. Kein oneSCM-Deployment |
| P1 | Änderungen neuer Quellen auf Inhalte zurückführen | 5–8 PT | Stabile Ticket-/Quellenkennungen und wiederholte Exportbeispiele | Neuer Export zeigt betroffene Texte, Übersetzungen, Screens und Kapitel; Zuordnungen bleiben erhalten; Aktualisierung nur nach Prüfung |
| P1 | Vollständige Blueprint-Vererbung | 6–10 PT | Fachliche Vorrangregeln für Markt, Sparte und Domäne | Herkunft jeder Abweichung erklärbar; Vererbung und konkurrierende Ausnahmen in konkreten Profilbeispielen kontrollierbar |
| P1 | Beliebigen alten Gliederungsstand wiederherstellen | 2–3 PT | Bestehende Historie und Revisionen | Alter Stand als neue Revision mit Vorschau übernehmbar; historische Ausgaben unverändert. Release-Rücknahme bleibt unabhängig |
| P1 | Markdown mit lokalen Bildern und relativen Links | 3–5 PT | Typische MD-Dateibündel | Relative Bilder, lokale Anker und Fußnoten nach Word übernommen; fehlende Dateien als prüfbare Importfehler ausgewiesen |
| P1 | Gescannte PDFs, Vektoren und weitere große Importe | 5–9 PT | Repräsentative PDF-/PPTX-Daten, lokale OCR-/Rendererentscheidung; Jira-Import bereits fortsetzbar | Seitenrendering und OCR mit Fundstellen; Vektorgrafiken abnehmbar; weitere umfangreiche Importformate nach Unterbrechung kontrolliert fortsetzbar |
| P1 | PII-/OCR-Prüfung für Screens ausbauen | 4–7 PT | Mehrsprachige Beispielscreens und fachliche PII-Regeln | OCR-Sprachwahl, regionale Muster und Stapel-Prüfung verfügbar; visuelle Freigabe weiterhin erforderlich |
| P1 | CI-Läufe und Windows-Start abnehmen | 1–2 PT | GitHub-Actions-Workflow für Windows/Linux Python 3.11/3.12 und Chromium vorhanden | Externe Läufe prüfen; echtes start.bat und installiertes Microsoft Office separat abnehmen |
| P2 | Semantisches RAG und freie belegte Antworten | 6–12 PT | Lokale registerübergreifende Belegsuche seit v0.7.0 vorhanden; Modell, Rechte und Qualitätsmaßstab klären | Belegter Testkatalog für Antworten aus freigegebenen Quellen; falsche Profile ausgeschlossen; fehlende Evidenz erkannt; Nutzer kann Belege prüfen. Eigenständige Erweiterung über den aktuellen FAQ-Chat hinaus |
| P2 | Erweiterter Template-/Platzhalterdesigner | 6–10 PT | Designstudio vorhanden; verbindliche Corporate-Design-Vorlagen | Deckblätter, Kapitelmuster, Icons und definierte Platzhalter reproduzierbar; Beispielmanual, Releaseletter und Quick Reference in Office abgenommen |
| P2 | Seitengenaue Verzeichnisse und Querverweise | 3–5 PT | Layoutmuster, Office-Feld-/Aktualisierungskonzept | Inhalts- und Bildverzeichnis mit Seitenzahlen, Bildnummern und korrekten Querverweisen im Zielprogramm |
| P2 | Terminologie, Stil und Grammatik | 5–9 PT | Glossar, Streichliste und Sprachleitfaden | Synonym-/Übersetzungsspeicher und Stilregeln zeigen nachvollziehbare Vorschläge je Sprache; keine stillen fachlichen Änderungen |
| P2 | Interne Wissenspflege im Stapel | 3–5 PT | Registermodell vorhanden, Beispiele für Importfelder | Import ins Register, Massenbearbeitung und Reviewfälligkeit verfügbar; Änderungen erzeugen Revisionen und markieren alte Chatbelege |
| P2 | Agenten als Hintergrundwarteschlange | 4–7 PT | Worker-/Betriebskonzept und gespeicherte Läufe | Läufe ohne geöffneten Browser fortsetzbar, Pause/Abbruch und Wiederholung nachvollziehbar; Übernahme weiterhin geprüft |
| P2 | Große Bibliotheken und Barrierefreiheit | 3–6 PT | Reale Größenordnung und Tastatur-/Screenreader-Abnahme | Paginierung, Tastaturnavigation und verständliche Fokusführung; Antwortzeiten mit festgelegtem Testbestand gemessen |
| P2 | Windows-Paket ohne Python-Vorinstallation | 4–7 PT | Paket-/Signaturstrategie, Offline-Bedarf | Installieren und aktualisieren mit Datenerhalt auf sauberem Windows-Rechner; Abhängigkeiten und Programmversion sichtbar |

## Empfohlene Reihenfolge

1. Neue ZIP auf dem Zielrechner aktualisieren und prüfen, dass die veröffentlichte Zielversion sichtbar ist.
   Mit echten Office-Templates, Jira-Exporten und einer gesicherten Kopie der
   Arbeitsdaten den Kernablauf abnehmen.
2. Sicherung/Wiederherstellung mit eigenem Datenbestand abnehmen. Die tatsächlich benötigten Prod-Profile
   und einen fachlichen FAQ-/Konflikt-Testkatalog festlegen.
3. Chat, Quellenprüfung und Releases an realen Fällen erproben; anschließend
   Änderungswirkung und Blueprint-Vererbung ausbauen.
4. Nur nach gemessener Notwendigkeit freies RAG, Terminologie, zusätzliche OCR,
   Layoutdesigner und Hintergrundautomatisierung ergänzen.

Für Microsoft 365 Copilot, Claude und Gemini sind derzeit Chat-Abonnements
vorhanden. Der vereinbarte Weg ist manueller Auftrags-/Antwortaustausch.
API-Anbindungen werden nicht vorausgesetzt und sind kein blockierender Restpunkt.
Für eine spätere automatische Anbindung wären passende API-Zugänge, Kostenrahmen
und ein ausdrücklich festgelegter Funktionsumfang separat zu klären.

Direkte Jira-/Confluence-Anbindungen sind auf ausdrücklichen Wunsch aus dem Umfang
genommen. HTML-/Word-Exporte und Zwischenablage sind der vereinbarte Importweg.
Malaysia/Indien sowie die fachliche Definition der achten Domäne bleiben
zurückgestellt. Vollständige automatische PII-Erkennung wird nicht zugesagt.

In v0.6.0 zusätzlich umgesetzt: vollständige ZIP-Sicherung mit geprüfter Wiederherstellung und Rücksicherung, Stapel-Prüfausgaben für Sprachen/Rollen/Dokumentarten/Formate sowie CI-Konfiguration. Versionsübergreifende Sicherungsübernahme, verschlüsselte ZIPs und automatische Stapelfreigaben bleiben außerhalb dieses Ausbaus.


In v0.8.1 abgeschlossen: lokale HTTP-Tests und Chromium-Abnahme für Designstudio,
Agenten, Publikation und RAG. Klassifikations-, Wissens- und Medienvorschläge
lassen sich nach Bearbeitung und ausdrücklicher Prüfung direkt übernehmen.

Nächste Restarbeiten: OCR mit persistierten Fundstellen (3–5 PT), Windows-/Office-
Layoutabnahme (2–4 PT), fachlicher Referenzlauf mit drei Sprachen und zwei Rollen
(3–5 PT), semantisches RAG (5–10 PT). Eine automatische KI-Anbindung setzt
passende API-Zugänge und eine festgelegte Datenfreigabe voraus (3–6 PT).
