# Funktionsstand: Gliederungsverwaltung und Dokumentstudio

Stand: 03.11.2026. Grundlage: die vom Benutzer hochgeladene Spezifikation mit neun
Kernpunkten sowie die anschließende Aufforderung, offene Punkte weiter umzusetzen.
„Vorher“ bezeichnet den Repository-Stand `ba2e937` vor diesem Ausbau.
„Umgesetzt“ bezieht sich auf den lokalen Einzelbenutzer-Prototyp, nicht auf ein
abgenommenes Mehrbenutzer-Produkt. Alle internen Vermerke bleiben gemäß der späteren
Benutzervorgabe aus **jeder** Ausgabe ausgeschlossen; die ältere Forderung nach
Vermerken in Prüfausgaben ist damit ersetzt.

| Nr. | Funktion | Vorher | Jetzt | Umsetzung / verbleibende Grenze |
|---|---|---|---|---|
| 1.1 | Zentrale Bibliothek mehrerer Gliederungen | Umgesetzt | Umgesetzt | Übersicht mit Suche, Rolle, Status, Version und Sortierung |
| 1.2 | Detailseite mit Kapitelbaum und Zielprofil | Umgesetzt | Umgesetzt | Metadaten, Version, Rolle, Umfang, Markt, Sparte, Sprache, Release |
| 1.3 | Anlegen, importieren, bearbeiten, kopieren | Umgesetzt | Umgesetzt | Stabile IDs; Kopien behalten Vergleichsherkunft |
| 1.4 | Gliederungen und gespeicherte Revisionen vergleichen | Umgesetzt | Umgesetzt | Zwei aufklappbare Ordnerbäume mit Änderungen |
| 1.5 | Freigeben | Teilweise | Umgesetzt | Explizite Prüfung des aktuellen Profils; veröffentlichte Ausgabe separat wählbar |
| 1.6 | Archivieren | Umgesetzt | Umgesetzt | Status und Übersichtsfilter; keine automatische Löschung |
| 1.7 | Verwendungsnachweis je Gliederung | Teilweise | Umgesetzt | Bestätigte Quellenzuordnungen, Ausgaben und Originaldownload |
| 2.1 | Zwischenablage, TXT, Markdown, Word importieren | Umgesetzt | Umgesetzt | Textimport und DOCX-Überschriftformatvorlagen |
| 2.2 | Nummerierung und Hierarchie erkennen | Umgesetzt | Umgesetzt | Nummern, Markdown, Einrückung; Ebenenprüfung |
| 2.3 | Importvorschau mit editierbaren Titeln und Ebenen | Umgesetzt | Umgesetzt | Anpassung vor Übernahme; Pflichtkapitel-Erkennung |
| 2.4 | Import als neue Gliederung | Umgesetzt | Umgesetzt | Eigene Gliederungskennung |
| 2.5 | Erneuter Import in bestehende Gliederung | Offen | Umgesetzt | Zielauswahl, Zuordnungsvorschlag und neue Revision |
| 2.6 | Neue, verschobene, umbenannte und entfallene Kapitel prüfen | Teilweise | Umgesetzt | Vergleich vor Übernahme; fehlende Alt-Kapitel werden ausgewiesen und behalten |
| 2.7 | Unklare Übereinstimmungen manuell entscheiden | Offen | Umgesetzt | Explizit bestehendes Kapitel oder „Neu anlegen“ wählen |
| 2.8 | Inhalts- und Chunk-Zuordnungen beim Reimport erhalten | Offen | Umgesetzt | Kennungen bleiben erhalten; kein stilles Entfernen |
| 3.1 | Stabile Kapitelkennung | Umgesetzt | Umgesetzt | Auch bei Umbenennen und Verschieben |
| 3.2 | Titel je Sprache | Offen | Umgesetzt | de/en/fr/it/sk/ko; manuelle Pflege und Prüfpunkt bei fehlender gepflegter Sprachfassung |
| 3.3 | Übergeordnetes Kapitel / Hierarchie | Umgesetzt | Umgesetzt | Erstellen, verschieben, einrücken, ausrücken, auf-/zuklappen |
| 3.4 | Kapiteltyp | Offen | Umgesetzt | Redaktionell, fachlich, automatisch, zusammengestellt |
| 3.5 | Kapitelziel | Umgesetzt | Umgesetzt | Frei editierbar |
| 3.6 | Mehrere Domänen und Unterdomänen je Kapitel | Umgesetzt | Umgesetzt | Acht Hauptdomänen; Mapping global und je Zuordnung schaltbar |
| 3.7 | Pflicht-, bedingte und manuelle Aufnahme | Teilweise | Umgesetzt | Bedingungen nach Rolle, Umfang, Markt, Sparte, Sprache, Release; wirken auf Unterkapitel |
| 3.8 | Erwartete Texte, Bilder, Klickstrecken und FAQ | Offen | Umgesetzt | Inhaltsvorgaben erzeugen bei Fehlen einen Prüfpunkt |
| 3.9 | Leerstellenregel blockieren / auslassen | Teilweise | Umgesetzt | Veröffentlichung blockiert; Prüfausgabe bleibt möglich |
| 3.10 | Kapitelstatus Entwurf / Prüfung / freigegeben | Offen | Umgesetzt | Für die Dokumentfreigabe ausgewertet |
| 4.1 | Rolle und Umfang getrennt steuern | Umgesetzt | Umgesetzt | Rollenfilter unabhängig von Darstellungstiefe |
| 4.2 | Kompakt / Standard / Ausführlich mit anpassbaren Regeln | Teilweise | Umgesetzt | Inhaltstypen pro Gliederung und Umfang konfigurierbar |
| 4.3 | Wesentliche Voraussetzungen, Schritte, Warnungen erhalten | Teilweise | Umgesetzt | Als solche gekennzeichnete Typen werden nicht durch den Umfang ausgeschlossen |
| 4.4 | Eigene Kurz-/Langfassungen pro Text | Teilweise | Umgesetzt | Varianten mit eigenem Prüfstatus; Basistext als Rückfall |
| 4.5 | Automatisch gekürzte Texte als ungeprüfte Vorschläge | Offen | Teilweise | Lokaler Ollama-Adapter mit expliziter Übernahme; echter Modelllauf und Qualität auf Zielrechner offen |
| 5.1 | Modus „Inhalte zuordnen“ | Teilweise | Umgesetzt | Zielkapitel links, zentrale Bausteine rechts; Auswahlzuordnung |
| 5.2 | Zentrale wiederverwendbare Textbibliothek | Offen | Umgesetzt | Eigene Revisionen, Archiv, Herkunft und Verwendungslisten |
| 5.3 | Filter nach Domäne, Rolle, Markt, Sparte, Release, Sprache, Status | Teilweise | Umgesetzt | Zusätzlich Stichwort und Umfang |
| 5.4 | Reihenfolge und Gültigkeit je Textverwendung | Teilweise | Umgesetzt | Positionspfeile und zusätzliche Bedingungen |
| 5.5 | Leserinhalt, interner Vermerk, Steuerungsfelder trennen | Umgesetzt | Umgesetzt | Alle Vermerke bleiben aus Word/PPTX ausgeschlossen |
| 5.6 | Vermerke an Kapitel, Text, Bild und Zuordnung | Teilweise | Umgesetzt | Einschließlich farbiger Kapitel-/Rollen-/Domänenmatrix |
| 5.7 | Zuordnung darf Originalgültigkeit nur einschränken | Offen | Umgesetzt | Schnittmenge; gebundene Originalrevision wird serverseitig aufgelöst |
| 5.8 | Zentrale Textänderung kontrolliert übernehmen | Offen | Umgesetzt | Bestehende Verwendungen behalten Revision; Aktualisierung ausdrücklich prüfen |
| 6.1 | Zentrale Bildbibliothek mit stabiler Kennung | Offen | Umgesetzt | PNG/JPEG, Duplikaterkennung, Versionen, Verwendungsliste, Archiv |
| 6.2 | Bilder aus Word, PPTX, PDF extrahieren | Offen | Teilweise | Rasterbilder unterstützt; Vektorgrafiken und vollständiges PDF-Seitenrendering fehlen |
| 6.3 | Bilder nach Rolle, Markt, Sparte, Release, Sprache, Umfang | Offen | Umgesetzt | Bildprofil plus einschränkende Verwendungsregeln |
| 6.4 | Mehrere Varianten einer Bildposition | Offen | Umgesetzt | Genau eine passende freigegebene Variante erforderlich; Konflikte sichtbar |
| 6.5 | Klickstrecken erstellen und ordnen | Offen | Umgesetzt | 1–50 Schritte; Varianten je Schritt; unvollständige Strecke wird nicht ausgegeben |
| 6.6 | Zentrale und verwendungsspezifische Bildunterschriften | Offen | Umgesetzt | Überschreibung je Kapitelverwendung |
| 6.7 | PII unkenntlich machen | Offen | Umgesetzt | Mausregionen, Abdeckung/starke Unkenntlichmachung, dauerhafte Rasterung und ausdrückliche PII-Prüfung |
| 6.8 | Schrittmarkierungen / Texte im Bild | Offen | Umgesetzt | Rahmen und Beschriftung; in bearbeitete Bildrevision eingerechnet |
| 6.9 | Lokale OCR und PII-Vorschläge | Offen | Teilweise | Tesseract angebunden und real getestet; Vorschläge müssen geprüft werden; zusätzliche OCR-Sprachwahl fehlt |
| 6.10 | Originalbilder nur HQ / intern | Offen | Teilweise | Wählbarer Redaktionsmodus; keine echte Anmeldung/ACL am Einzelarbeitsplatz |
| 6.11 | Passende Bildfassung prüfen und im Office ausgeben | Offen | Umgesetzt | Nur geprüfte/freigegebene Bildrevisionen; keine Originale oder internen Notizen |
| 6.12 | Bilder löschen / historische Verwendungen erhalten | Offen | Umgesetzt | Unbenutzte Bilder löschbar; historisch verwendete Bilder archivieren |
| 7.1 | Einleitung, Glossar, FAQ als Pflichtvorgabe | Umgesetzt | Umgesetzt | Bei neuen Gliederungen; zusätzliche Pflichtkapitel manuell ergänzbar |
| 7.2 | Redaktionelle Kapitel ohne externe Quelle | Umgesetzt | Umgesetzt | Frei verfasste Texte und zentrale Redaktionstexte |
| 7.3 | Inhaltsverzeichnis aus tatsächlicher Ausgabe | Offen | Umgesetzt | Kapitelnummern und Titel; keine Word-Seitenzahlberechnung |
| 7.4 | Relevante und verpflichtende Glossarbegriffe | Offen | Teilweise | Vorschlag aus zentralen Begriffen nach Domäne/Profil; Pflichtbegriffe zusätzlich; semantische Erkennung im Fließtext fehlt |
| 7.5 | FAQ passend zum Profil zusammenstellen | Teilweise | Umgesetzt | Zentrale FAQ nach Domäne, Rolle, Markt, Sparte, Release, Sprache und Umfang; explizite Übernahme |
| 7.6 | Leere Pflichtkapitel verhindern Veröffentlichung | Teilweise | Umgesetzt | Prüfpunkt, Freigabesperre und klare Trennung zur Prüfausgabe |
| 8.1 | Änderungen freigegebener Gliederung als neue Revision | Teilweise | Umgesetzt | Weiterbearbeitung wird Entwurf; historischer Freigabestand bleibt |
| 8.2 | Bestehende Ausgaben unverändert halten | Umgesetzt | Umgesetzt | Gespeicherte Originaldatei; byte-identischer erneuter Download getestet |
| 8.3 | Gliederung, Revision, Profil und Release dokumentieren | Teilweise | Umgesetzt | Ausgabenhistorie im Verwendungsnachweis |
| 8.4 | Text-, Sprach- und Bildrevisionen nachweisen | Teilweise | Umgesetzt | Kennungen, Textfingerabdrücke, zentrale Revisionen, Übersetzungsherkunft, Bildrevisionen |
| 8.5 | Übersetzungen mit Ausgangsrevision und Prüfstatus | Offen | Umgesetzt | Manuelle Sprachfassungen; Warnung bei neuer Quellrevision |
| 8.6 | KI-Übersetzungsvorschlag | Offen | Teilweise | Lokaler Adapter und Fehlerfälle getestet; echter Modelllauf/Sprachqualität offen |
| 8.7 | Templateversion und Vermerksregel im Nachweis | Teilweise | Umgesetzt | Festes Template `onescm-office-2`; Vermerke immer ausgeschlossen |
| 8.8 | Eigene hochladbare Layouttemplates / Corporate Design | Offen | Offen | Beispieltemplates noch nicht bereitgestellt; Upload-/Templateauswahl noch zu bauen |
| 9.1 | Struktur → Import → Regeln → Zuordnung → Vorschau → Revision → Office | Teilweise | Umgesetzt | Durchgängiger bedienbarer Ablauf für Texte und Medien |
| 9.2 | Verschieben erhält Inhalte; Varianten aus gemeinsamer Basis | Teilweise | Umgesetzt | Modell- und Browserabnahme |
| 9.3 | Pflichtregeln, interne Vermerke und Reimport ohne Zuordnungsverlust | Teilweise | Umgesetzt | Automatisierte Abnahme einschließlich Office-Dateiinhalten |

## Weitere Plattformfunktionen und Restarbeiten

| Funktion | Stand | Grenze / nächster konkreter Schritt |
|---|---|---|
| Quellenimport HTML, TXT, MD, DOCX, PPTX, PDF, CSV, JSON | Umgesetzt | Datei-Exporte aus Jira, Confluence, Mural und Transkriptionen |
| Quellenübersicht und Löschen | Umgesetzt | Quelle/Chunks/Zuordnungen werden gelöscht; extrahierte Medienkopien separat verwalten |
| Chunk-Triage, manuelle Prüfung, Kapitelzuordnung und Zähler | Umgesetzt | Regeln ohne KI; optional lokales Ollama; echte KI-Qualität noch nicht abgenommen |
| Stichwort-/Label-/Rollen-/Themensuche und farbige Matrixbemerkungen | Umgesetzt | Interne Bemerkungen in keiner Ausgabe |
| OCR → Kapitel-/Domänen-/Rollenvorschlag | Umgesetzt | Lokale Regeln erzeugen prüfbare Vorschläge; Labels ausdrücklich übernehmen, Kapitel/Rollen als interne Hinweise |
| Automatisierte PII-Vollständigkeitsgarantie | Offen | Keine vollständige Erkennung behauptet; visuelle Prüfung bleibt erforderlich |
| Echte Benutzerrechte und geschützte Originalablage | Offen | Erst bei Mehrbenutzerbetrieb Authentifizierung und serverseitige ACL ergänzen |
| Templateimport und professionelles Layout | Offen | DOCX-Stile/Kopf-Fußzeilen und PPTX-Master versioniert übernehmen; konkrete Muster prüfen |
| PDF-/HTML-Ausgabe | Offen | Word/PPTX bleiben Priorität 1; weitere Renderer mit gleichen Auswahlregeln anbinden |
| Direkte Jira-/Confluence-/SharePoint-Anbindung | Offen | Derzeit Dateiimport; Zugang und gewünschte API-/Exportkonventionen später festlegen |
| Markt-/Sparten-Blueprint mit Vererbungs-/Konfliktregeln | Teilweise | Exakte Gültigkeitsfilter vorhanden; zeitliche Vorrangregeln und Konflikterkennung fehlen |
| Preprod-/Prod-Releasepromotion | Offen | Releasefeld vorhanden; kein automatischer Vierwochen-Workflow |
| Mehrere Fachagenten mit Orchestrator | Offen | Einzelne lokale KI-Aufrufe vorhanden; kein Agentenlauf mit Aufgaben-/Qualitätsschritten |
| Wiederherstellen alter Gliederungen | Offen | Historie ist lesbar/vergleichbar; Wiederherstellung als neue Revision noch zu ergänzen |
| Integrierte Sicherung / Wiederherstellung | Offen | Manuell bei beendeter Anwendung Datenordner kopieren |

## Prüfung und praktische Grenzen

- 53 erfolgreiche automatisierte Modell-/HTTP-Tests für Import, Regeln, Revisionen, Bibliothek,
  Übersetzungsherkunft, Medien, OCR, Löschschutz und echte Office-Dateiinhalte.
- Fünf erfolgreiche Browserabnahmen in `tests/browser_smoke.py`, `browser_management.py`,
  `browser_sources.py`, `browser_editorial.py`, `browser_media.py`.
- Tesseract wurde tatsächlich mit synthetischen Bilddaten aufgerufen.
- Ollama-Adapter mit simulierten Antworten geprüft; kein Modell installiert,
  daher keine behauptete Endabnahme von Übersetzungs- oder Kürzungsqualität.
- Windows-Start und Darstellung in installiertem Microsoft Office sind noch
  auf dem Zielrechner zu prüfen. Cloudtests liefen unter Linux/Chromium.
- Eigene Datenbanken, Quellen, Originalbilder und Testartefakte gehören nicht
  in das Repository oder die Prototyp-ZIP.
