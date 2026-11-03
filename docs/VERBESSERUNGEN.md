# Verbesserungen und fehlende Funktionen

Stand **v0.4.0 · 03.11.2026**. Schätzungen in Personentagen zu 8 Stunden für eine
entwickelnde Person, einschließlich Umsetzung und gezielter Tests. Es sind grobe
Planungswerte, keine Zusage; neue Anforderungen und verfügbare Beispieldaten können
den Aufwand ändern. P0 = vor verlässlichem Alltagseinsatz, P1 = nächster Ausbau,
P2 = anschließender Komfort-/Gestaltungsausbau. Abhängigkeiten beachten.

| Priorität | Verbesserung / fehlendes Feature | Stand und konkretes Abnahmekriterium | Aufwand |
|---|---|---|---:|
| P0 | Windows- und Microsoft-Office-Abnahme | Linux/Chromium und Dateiinhalte geprüft. Start, Updates, Word/PPTX-Umbrüche, PDF-Schriften und reale Templates auf dem Zielrechner mit repräsentativen langen Dokumenten abnehmen. | 2–4 PT |
| P0 | Integrierte Sicherung und Wiederherstellung | Bisher manuelle Sicherung bei beendeter Anwendung. Konsistente verschlüsselte Sicherung, Wiederherstellungsprüfung und verständliche Bedienoberfläche ergänzen. | 3–5 PT |
| P0 bei Mehrbenutzer-/Chatbot-Freigabe | Echte Zugriffsrechte und sichere Originalablage | Bisher vertrauenswürdiger Einzelarbeitsplatz mit Rollenbezug. Anmeldung, serverseitige Rechte für interne FAQ und Originalbilder sowie negative Zugriffstests erforderlich. | 8–15 PT |
| P1 | Interner Chatbot mit belegten Antworten | Register und freigegebene FAQ-Suche vorhanden. Lokaler Suchindex/RAG, Quellen- und Revisionszitate, Antworten bei unzureichender Evidenz verweigern; Tests verhindern Antworten aus falschem Land/Rollenprofil. Rechtekonzept vorher festlegen. | 8–15 PT |
| P1 | Reale KI- und Sprachqualitätsabnahme | Ollama-Adapter technisch geprüft, kein fachlich abgenommenes Modell. Referenzfälle für Triage, Kürzung, Übersetzung und Halluzinationen erstellen; Ergebnisse gegen manuelle Bewertung messen. | 4–7 PT |
| P1 | Automatische Releasepromotion Preprod → Prod | Datum, Umgebung, Version und Gültigkeitsregeln vorhanden. Vierwochen-Workflow mit Releasepaket, Änderungsübersicht, Freigabe und Rücknahme fehlt. Keine direkte Jira-Anbindung erforderlich. | 5–8 PT |
| P1 | Vollständige Blueprint-Vererbung | Zeitliche Vorrang-/Konfliktregeln vorhanden. Domänenübergreifende Markt-/Sparten-Vererbung mit Herkunftsauflösung und erklärbarer Konfliktansicht ergänzen. | 6–10 PT |
| P1 | Inhaltliche Widersprüche und Dubletten prüfen | Datei-/Bildduplikate und strukturierte Konflikte erkannt; semantischer Vergleich verschiedener Quellenstände fehlt. Prüfwarteschlange mit belegten konkurrierenden Aussagen und manueller Entscheidung ergänzen. | 6–10 PT |
| P1 | Quellenseitige Änderungswirkung | Revisionen und Herkunft vorhanden. Neue HTML-/Word-Release-Exporte mit Vorständen vergleichen und betroffene Kapitel, Übersetzungen und Screens zur Prüfung markieren. | 5–8 PT |
| P1 | Alte Gliederung wiederherstellen | Historie lesbar und vergleichbar. Einen Stand als neue Revision übernehmen, ohne historische Ausgaben oder aktuelle Zuordnungen still zu verändern. | 2–3 PT |
| P1 | Markdown mit lokalen Bildern und relativen Links | Text, Tabellen, Listen und Code nach Word funktionieren. Dateibündel mit relativen Bildpfaden, lokalen Ankern, Fußnoten und nachvollziehbaren Importfehlern ergänzen. | 3–5 PT |
| P1 | Umfangreiche Quellen und gescannte PDFs | Text- und Rasterextraktion vorhanden. PDF-Seitenrendering, Scan-OCR, Vektorgrafiken, große Importe mit Wiederaufnahme und präzisen Fundstellen ergänzen. | 5–9 PT |
| P1 | PII-Prüfung und OCR-Sprachen ausbauen | Manuelle Masken, OCR-Hinweise und Rasterausgabe vorhanden. Sprachauswahl, regionenspezifische Erkennung und Stapel-Prüfoberfläche verbessern; visuelle Freigabe bleibt erforderlich. | 4–7 PT |
| P1 | Tests der neuen Regeln automatisiert in CI | Lokale Modell-/HTTP-/Browser-Suiten vorhanden. CI für unterstützte Python-Versionen, Windows-Start und herunterladbare Testberichte einrichten. | 2–4 PT |
| P2 | Professioneller Template- und Platzhalterdesigner | Native Stile/Master und portable Farben vorhanden. Deckblätter, Kapitelmuster, Icons, dynamische Platzhalter und firmenspezifische Inhaltslayouts anhand der noch bereitzustellenden Muster ergänzen. | 6–10 PT |
| P2 | Seitengenaues Verzeichnis und Bildverzeichnis | Inhaltsverzeichnis nach sichtbarer Struktur vorhanden. Word-Felder/Seitenzahlen, Abbildungsnummern, Querverweise und druckreife Register ergänzen. | 3–5 PT |
| P2 | Redaktionelle Terminologie | Keywords/Labels, manuelle Sprachfassungen und Glossarbegriffe vorhanden. Synonym-/Übersetzungsspeicher, verbotene Begriffe und Stil-/Grammatikprüfung systematisch integrieren. | 5–9 PT |
| P2 | Interne Wissenspflege im Stapel | Register, Unterthemen, Mehrfachzuordnung, Revisionen, Archivstatus und FAQ-Vormerkung vorhanden. Datei-/Zwischenablageimport direkt in das Register, Reviewfälligkeit und Massenbearbeitung ergänzen. | 3–5 PT |
| P2 | Agenten als Hintergrundwarteschlange | Persistente sequenzielle Läufe mit Prüfung vorhanden. Browserunabhängigen Worker, Planung, Fortschrittsereignisse und gezielte Wiederholung einzelner Schritte ergänzen. | 4–7 PT |
| P2 | Bedienbarkeit großer Bibliotheken | Suche, Filter und Bäume vorhanden. Serverseitige Paginierung, Tastaturnavigation, Barrierefreiheit und Messung mit realen Datenmengen ergänzen. | 3–6 PT |
| P2 | Windows-Paket ohne Python-Vorinstallation | `start.bat` benötigt Python und für Erstinstallation Paketnetzwerk. Signiertes Installationspaket, Offline-Abhängigkeiten und Updatepfad ergänzen. | 4–7 PT |

## Empfohlene nächste Reihenfolge

1. Reale Word-/PowerPoint-Muster und ein repräsentatives Releasepaket für Windows-
   Abnahme verwenden; gleichzeitig Sicherung/Wiederherstellung ergänzen.
2. Automatische Releasepromotion und Änderungswirkung auf Kapitel entwickeln.
3. Interne FAQ mit echten Fragen befüllen, Qualitätsmaßstab und Zugriffsmodell
   festlegen; anschließend den lokalen Chatbot anbinden.
4. Nach gemessenen Qualitätslücken Terminologie, OCR und professionelle Layouts
   ausbauen.

Direkte Jira-/Confluence-Anbindungen sind auf ausdrücklichen Wunsch aus dem Umfang
genommen. HTML-/Word-Exporte und Zwischenablage sind der vereinbarte Importweg und
werden hier nicht als fehlende Systemanbindung bewertet. Malaysia/Indien sowie
die fachliche Definition der achten Domäne bleiben zurückgestellt. Automatische
vollständige PII-Erkennung wird nicht als erreichbare Garantie zugesagt.
