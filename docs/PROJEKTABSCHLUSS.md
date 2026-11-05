# Projektabschluss · oneSCM-360 v0.12.0

Stand: 05.11.2026. Übergabe als lokaler Einzelplatz-Prototyp. Der technische Entwicklungsstand wird abgeschlossen und zur Erprobung bereitgestellt; die produktive fachliche Abnahme bleibt offen.

## Lieferumfang

Quellenimport und Stapelverarbeitung, Gliederungen und Domänenmapping, Medien/OCR mit optionalem OpenCV, regelbasierte interne Belegsuche, neun Agenten einschließlich Audit, interne Flags, dreisprachige Anhänge, Designpresets, Word/PPTX/PDF/HTML, Releaseverwaltung, Speicherinventar und Sicherungen. Navigation folgt dem Dokumentationsprozess.

OpenCV ist eine optionale lokale Bildvorverarbeitung. Tesseract bleibt OCR-Engine. Es gibt keine Garantie vollständiger Texterkennung oder PII-Freiheit und keine automatische fachliche Bildinterpretation.

## Offene Themen zur Folgeplanung

| Priorität | Thema | Grober Restaufwand |
|---|---|---|
| P0 | Windows-/Office-Abnahme mit realen Templates, Schriften, langen Dokumenten und Updates mit Bestandsdaten | 2–4 PT |
| P0 | Fachliche und PII-Abnahme für DE/EN/FR und mehrere Rollen, repräsentative Originalquellen | 3–5 PT |
| P1 | Semantisches RAG mit lokalem Embedding-Modell; derzeit Stichwort-/Belegsuche | 5–10 PT |
| P1 | OCR-Qualitätskatalog, Sprachpakete, gescannte PDFs, Perspektivkorrektur und geometrische Rückprojektion | 3–6 PT |
| P1 | Reale Release-, Länder-, Sparten- und Übersetzungsvarianten prüfen | 3–5 PT |
| P2 | Verschlüsselte Sicherungen und automatische Hintergrundaufträge | 4–7 PT |

PT = Personentage. Schätzungen überschneiden sich und sind keine Zusagen. Mehrbenutzerbetrieb benötigt zusätzlich Authentifizierung und serverseitige Berechtigungen; die jetzige Rollenauswahl ist ein redaktionelles Profil.

## Start und Übergabe

1. Bisherige Daten sichern und alten Server stoppen.
2. ZIP in neuen Programmordner entpacken, `start.bat` starten und Browser mit Strg+F5 aktualisieren.
3. Optional `install-opencv.bat` ausführen und Tesseract separat bereitstellen.
4. Im Register Speicher den aktiven Datenbankpfad kontrollieren.
5. Mit einem Referenzhandbuch samt Quellen und Screens beginnen; fachliche und visuelle Abnahmen dokumentieren.

Bestehende Daten bleiben im Datenordner. Das Auslieferungs-ZIP enthält Programmcode, Frontend, Tests und Dokumentation, keine Nutzerdatenbank.

## Technische Validierung

167 automatisierte Tests erfolgreich, einschließlich tatsächlicher OpenCV-/Tesseract-Verarbeitung und Prüfung unveränderter Originalbilder. Browserprüfung für Prozessnavigation, Burgermenü, Zähler, Speicherung, Tastatur und mobile Ansicht erfolgreich. Diese technischen Tests ersetzen keine fachliche Abnahme realer Benutzerhandbücher.
