# oneSCM360 Knowledge Studio

Lokal betriebene Webanwendung zur strukturierten Übernahme von Rovo-, Jira-, Confluence-, HTML- und Word-Inhalten in einen nachvollziehbaren Wissens- und Handbuchprozess. Grundlage ist die „Konsolidierte Gesamtdokumentation des Projekt-Chats“ (Version 1.0, 06.11.2026).

**Datenfluss:** HTML/DOCX → Parser → Tabellenextraktion → Regelwerk → Fragen → Claims → Evidence → Coverage/Gates → OneDrive-Export → manueller SharePoint-Transfer

## Betriebsentscheidungen

- Lokaler Flask-Dienst ausschließlich auf `127.0.0.1:8080`. Keine Entra-ID, kein Microsoft Graph.
- Eingaben: `.docx`, `.html`, `.htm`, maximal 50 MB.
- Kapitel CH01 bis CH16 sind auswählbar. CH01 ist das vollständig ausgearbeitete Referenzkapitel. CH02 bis CH16 haben einen Schema-Entwurf (`schemaStatus: DRAFT`) mit generischen Fragen.
- OneDrive ist ein lokal beschreibbarer Sync-Ordner. Die App bestätigt nur die lokale Bereitstellung. Der Cloudstatus lautet immer `NOT_VERIFIABLE_WITHOUT_GRAPH`.
- Automatisch erzeugte Claims sind Vorschläge (`DRAFT`). Sie werden nie ungeprüft freigegeben.

## Installation und Start (Windows)

```
cd 'C:\oneSCM360\onescm360_app_build'
py -3 -m pip install -r requirements.txt
powershell.exe -ExecutionPolicy Bypass -File '.\start_onescm360.ps1'
```

Das Startskript prüft Python (3.10 oder neuer) und die Pflichtpakete `flask` und `jsonschema`. Es setzt die Umgebungsvariablen, startet die App und öffnet den Browser.

Pfade mit Leerzeichen oder Klammern, zum Beispiel `OneDrive - Firma (tenant.onmicrosoft.com)`, immer in einfache Anführungszeichen setzen oder mit `-LiteralPath` verwenden.

| Konfiguration | Wert |
|---|---|
| `ONESCM_LOCAL_ONEDRIVE_ROOT` | Lokaler OneDrive-Zielordner, z. B. `C:\Users\<Benutzer>\OneDrive - <Firma>\-oneSCM360`. Ohne Angabe nimmt das Startskript `%OneDriveCommercial%\-oneSCM360`. |
| `ONESCM_HOST` | `127.0.0.1` (andere Werte werden abgelehnt) |
| `ONESCM_PORT` | `8080` |
| `ONESCM_DATA_DIR` | optional, Standard `data\` im Programmordner |
| Python | 3.10 oder neuer |
| Pflichtpakete | `flask`, `jsonschema` |

Den OneDrive-Pfad können Sie auch im Register **Synchronisation** setzen. Die Einstellung wird in `data\settings.json` gespeichert und hat Vorrang vor der Umgebungsvariable.

Start mit eigenem Pfad:

```
powershell.exe -ExecutionPolicy Bypass -File '.\start_onescm360.ps1' -OneDriveRoot 'C:\Users\<Benutzer>\OneDrive - <Firma>\-oneSCM360'
```

## Register

| Register | Funktion |
|---|---|
| Dashboard | Importläufe mit Sprache, Rolle und Domäne, gruppierbar. KPIs (Importläufe, Quelldateien, Output-Dateien, JSON, CSV, Uploadpakete), Importtabelle, Outputtabelle, OneDrive-Pfadprüfung. Beschädigte Import-JSONs erscheinen als `INVALID_JSON` / `BLOCKED`. |
| Import | Eine oder mehrere Dateien auswählen oder hineinziehen. Je Datei schlägt die App Kapitel, Sprache, Rolle und Domäne vor (siehe unten). Alle Werte sind in der Liste änderbar. Die Liste lässt sich nach Kapitel, Sprache, Rolle, Domäne oder Dateiname ordnen. Der Import läuft Datei für Datei mit Sanduhr und Gesamtfortschritt. Eine fehlerhafte Datei stoppt die übrigen nicht. Ergebnis je Datei: Import-ID, erkannte Fragen, Tabellen, Validierung, Regelbefunde, Coverage. |
| Regelwerk | Namenskonvention, Systemübersicht, Synonyme, Erklärungen, Abkürzungen: anlegen, bearbeiten, speichern, abbrechen, löschen mit Rückfrage. Testfeld für Regeln. |
| Kapitel | Fragenkataloge CH01–CH16 pflegen: Titel, Schema-Status (DRAFT/REFERENCE), Schwerpunkt, Pflichtauswertungen, Rollen der Rollenabdeckung sowie je Frage Gruppe, Titel DE/EN und Kritikalität. CSV-Vorlage herunterladen und Kataloge aus Excel per CSV übernehmen (Semikolon oder Komma, UTF-8 oder Windows-1252, Kritikalität auch als kritisch/hoch/mittel/niedrig). Änderungen liegen unter `data\chapters`, „Auf Standard zurücksetzen“ verwirft sie. |
| Claims | Claims filtern, bearbeiten (Subject/Predicate/Object, Rolle, Division, PI, Reifegrad …), bestätigen, löschen, manuell anlegen, Evidence zuordnen. |
| Evidence | Evidence-Stufe und -Status pflegen, Faktor sehen, löschen. |
| Tabellen | Separat extrahierte Tabellen ansehen, Quellfrage zuordnen, als JSON oder CSV herunterladen. |
| Coverage | Readiness, sechs Dimensionen, Gate, Hard Blocker, Konflikte (auflösen mit Begründung), Rollenabdeckung. |
| Synchronisation | Verbindung zum lokalen OneDrive-Ordner, Ordnerstruktur anlegen, Kapitel exportieren, Handbuchstand erzeugen (Draft/Reviewed/Released), regelbasierte Datenbereinigung, Hinweise zum manuellen SharePoint-Transfer. |
| Interner Chat | Fragen in natürlicher Sprache. Der Router wählt genau ein Tool aus der Tool Registry, die Security Policy prüft (default DENY), dann wird es auf den lokalen Daten ausgeführt. Mit Audit-Protokoll, Routing-Testsuite und Trainingsdaten-Export (siehe unten). |
| Dokumentation | Diese Datei. |

## Fachliche Regeln

### Fragenerkennung

Je Kapitel gibt es die Fragen `xx-F01` bis `xx-F20`. Die Erkennung toleriert `F01`, `xx F01`, `xx-F01`, `CHxx-F01` und `F1:`.

- Eine Kennung eines anderen Kapitels (z. B. `02-F01` in CH01) wird als `CHAPTER_MISMATCH` gemeldet und blockiert den Import (Validierung `BLOCKED`).
- Fragen außerhalb von F01 bis F20 werden ignoriert und als Hinweis ausgegeben.

### Mehrfachimport: Kapitel, Sprache, Rolle, Domäne

Beim Auswählen liest die App jede Datei, ohne sie zu importieren (`POST /api/import/classify`). Daraus macht sie Vorschläge:

| Angabe | Aus dem Dateinamen | Aus dem Inhalt |
|---|---|---|
| Kapitel | `CH05`, `Kapitel 5`, `Chapter 05` | häufigste Fragekennung `05-F..` |
| Sprache | `_DE`, `_EN`, `_DE_EN`, `deutsch`, `english` | Anteil deutscher bzw. englischer Funktionswörter; beides deutlich vertreten ergibt `DE+EN` |
| Rolle | Rollenname oder Schreibvariante, z. B. `Dealer`, `MO`, `Market-Operations`, `HQ` | klar überwiegend genannte Rolle, sonst „Alle Rollen“ |
| Domäne | Domänenname oder Stichwort, z. B. `Finance` | Stichwort-Treffer mit klarem Vorsprung, sonst „Ohne Domäne“ |

Nicht erkannte Angaben übernehmen die Standardwerte oberhalb der Liste. In der Liste steht bei jedem Wert, woher er stammt: „erkannt: Dateiname“, „erkannt: Inhalt“ oder „manuell“.

Rollen und Domänen stehen in `classification.json`.

### Rollen

| ID | Anzeige | Erkannt als |
|---|---|---|
| `Dealer` | Dealer | Dealer, Händler, Autohaus |
| `MO` | MO (Market Operations) | MO, Market Operations, Market Operation |
| `HQ` | HQ | HQ, Headquarters, Zentrale |
| `Market` | Market | Market, Markt, Märkte, Markets |
| `IT` | IT | IT, IT-Abteilung, IT department |
| `intern` | intern | intern, interne, internal |

Regeln für die Erkennung:

- Längere Schreibvarianten gehen vor. „Market Operations“ ergibt also MO und nicht Market.
- Domänennamen wie „Market Setting“ zählen nicht als Rolle.
- Kurze Großbuchstaben-Kürzel (MO, HQ, IT) werden nur in genau dieser Schreibweise erkannt. Das englische „it“ ist also keine Rolle.
- Gespeichert wird immer die ID. Eine Schreibvariante als Eingabe, z. B. „Market Operations“, wird auf die ID umgesetzt.

Rollen und Varianten lassen sich in `classification.json` ergänzen.

Die Rollenabdeckung im Coverage bewertet nur die Rollen, die in `chapters/CHxx.json` unter `roles` stehen. Derzeit sind das Dealer und MO. Weitere Rollen werden dort je Kapitel aufgenommen.

Die sieben Domänen entsprechen denen der bestehenden Handbuch-App: Die sieben Domänen entsprechen denen der bestehenden Handbuch-App:

- Product Management
- Contract Generation
- Contract Management
- Customer Management
- Finance Management
- Market Setting
- Admin Section

Was beim Import mit Rolle und Domäne passiert:

- Rolle und Domäne werden am Import gespeichert und gehen in den Export.
- Die Domäne wird als `Category` der Knowledge Blocks übernommen.
- Aussagen ohne eigene Rolle erhalten die Rolle der Datei (`roleFromImport`). Eine im Satz genannte Rolle hat Vorrang.
- Dieselbe Datei kann für verschiedene Rollen oder Domänen getrennt importiert werden.

### Tabellen

- IDs folgen dem Muster `TBL-CHxx-001`. Kopfzeile, Zeilen und Zellwerte bleiben erhalten, ungleiche Zeilen werden markiert.
- Die Quellfrage ergibt sich aus der Position im Dokument. Vor der ersten Frage gilt `sourceQuestionId = null`, und die Tabelle braucht einen Review.
- CSV-Dateien haben UTF-8 mit BOM und Semikolon als Trennzeichen.

### Claims

- Ein Claim enthält eine überprüfbare Aussage.
- Konjunktionen werden nur getrennt, wenn sich Aktion, Rolle, Objekt, PI, Reifegrad oder Division unterscheiden. Sätze mit Bedingungen bleiben ungeteilt.
- Negationen und Bedingungen bleiben erhalten.
- Unsichere Begriffe („möglicherweise“, „expected“, „planned“ …) setzen `uncertain`. Solche Claims lassen sich nicht auf `CONFIRMED` setzen.
- PI und Reifegrad werden getrennt erkannt. `IMPLEMENTED`, `IN_TEST` und `ACCEPTED` gelten nie als `PRODUCTION`.
- Ein PC-Nachweis zählt nicht für VAN.
- `NOT_RELEVANT` braucht einen Nachweis.
- Rovo-Inhalte ergeben nur `INDIRECT`-Evidence. Jira-Keys und Confluence-Links im Text werden als `DIRECT`-Vorschläge erfasst.

### Evidence-Faktoren

| Stufe | Faktor |
|---|---|
| DIRECT_VALIDATED | 1,00 |
| MULTIPLE_CONSISTENT | 1,00 |
| DIRECT | 0,90 |
| INDIRECT | 0,50 |
| OUTDATED | 0,25 |
| CONFLICTING | 0,00 |
| MISSING | 0,00 |

### Konflikte

Erkannt werden `DIRECT_CONTRADICTION`, `ROLE_CONFLICT`, `DIVISION_CONFLICT`, `PI_CONFLICT`, `MATURITY_CONFLICT` und `SOURCE_SYSTEM_CONFLICT`. Unterschiedlicher Scope (Rolle, Division, Markt, PI) ist nicht automatisch ein Konflikt.

### Kritikalität und Knowledge Blocks

- **Kritikalität:** Ein Claim übernimmt beim Import die Kritikalität seiner Frage. Für Coverage und Gate zählt die höhere von beiden, die des Claims oder die der Frage im Kapitelschema. Wird eine Frage später auf CRITICAL hochgestuft, gilt das sofort für ihre bestehenden Claims.
- **Status eines Knowledge Blocks:** folgt seinen Claims.
  - `CONFIRMED`, wenn alle aktiven Claims freigegeben sind
  - `REVIEWED`, wenn alle mindestens geprüft sind
  - `REJECTED`, wenn alle abgelehnt sind
  - sonst `DRAFT`
- **Version:** steigt, sobald sich Claims des Blocks ändern (Aussage, Status, neu oder gelöscht). Beides geht in `KnowledgeBlocks.csv` für die SharePoint-Liste.

### Coverage

`Readiness = Questions×0,20 + Evidence×0,30 + Roles×0,15 + Division×0,15 + PI×0,10 + Confidence×0,10`

| Gate | Regel |
|---|---|
| BLOCKED | mindestens ein Hard Blocker (der Score spielt keine Rolle) |
| READY | Readiness ≥ 90, Evidence ≥ 90, kritische Questions und Claims zu 100 % abgedeckt, keine Blocker |
| REVIEW | Readiness ≥ 70 |
| INCOMPLETE | 40 ≤ Readiness < 70 |
| STARTED | 0 < Readiness < 40 |
| NOT_STARTED | Readiness = 0 |

Hard Blocker:

- offener kritischer Konflikt
- kritischer Claim ohne direkte Evidence (Faktor ≥ 0,9)
- ungeklärte kritische Berechtigung, finanzielle Regel, irreversible Aktion oder Security/Compliance-Aussage (Claim nicht `CONFIRMED`)
- widersprüchlicher Produktivstatus
- gebrochene referentielle Integrität (auch `CHAPTER_MISMATCH` und `INVALID_JSON`)

## Interner Chat: Router, Security Policy, Tool Registry

Vorbild ist das Google-Notebook „Fine-tuning with FunctionGemma“ (`google/functiongemma-270m-it`). Der Chat ist in vier Schichten getrennt:

```
UI (Register „Interner Chat“)
  → lokaler Router (Regeln oder FunctionGemma auf localhost): Intent → Tool → Parameter
  → Security/Policy Engine: Allowlist · Berechtigung · Schema-Prüfung · Audit · default DENY
  → Tool Layer (tool_registry.json)
  → interne Daten (CH01–CH16, Regeln, Claims, Evidence, Knowledge Blocks, Importe)
╳ Internet  ╳ öffentliches LLM  ╳ externe API  ╳ öffentliche Suche
```

**Der Router entscheidet, was getan werden soll. Die Policy entscheidet, ob es getan werden darf.** Coverage, Gates und Validierung berechnet weiterhin der deterministische Python-Service, nie das Modell.

### Tool Registry v1 (`tool_registry.json`)

| Tool | Zweck | Quelle | Schreibend |
|---|---|---|---|
| `search_knowledge` | Knowledge Blocks und freigegebenes Wissen durchsuchen (inkl. Regelwerk) | oneSCM360 Store | Nein |
| `search_manual` | Handbuch CH01–CH16 durchsuchen (importierte Kapiteltexte) | lokaler Store | Nein |
| `search_jira` | Tickets/Evidence finden | interne Jira-Schnittstelle | Nein |
| `search_confluence` | interne Dokumentation suchen | Confluence | Nein |
| `query_rovo` | Rovo-Abfrage (nur intern/freigegeben) | Rovo | Nein |
| `get_claims` | Claims laden | oneSCM360 | Nein |
| `get_evidence` | Evidence zu Claim ermitteln | oneSCM360 | Nein |
| `calculate_coverage` | Coverage/Gates berechnen (Dimensionen questions, claims, evidence, roles, PC, VAN, CV, PI_status) | lokaler Service | Nein |
| `validate_chapter` | Kapitel validieren | lokales Regelwerk | Nein |
| `export_knowledge` | JSON, CSV oder Review-Paket erzeugen | lokaler Export | Ja, nur nach Bestätigung |

Jedes Tool hat:

- **ein JSON-Schema mit Enums**, z. B. `chapter` CH01–CH16, `vehicle_type` PC/VAN/CV/ALL, `status` Draft/Reviewed/Released, `language` DE/EN.
- **Sicherheits-Metadaten:** `classification`, `network`, `internet_access: false`, `authentication_required`, `authorization_required`, `audit`, `allowed_operations`, `blocked_operations`, `source`, `writes`, `confirmation_required`.

Die App startet nicht, wenn ein Tool Internetzugriff verlangt. Das Modell erhält nur Name, Beschreibung und Schema, nie die Sicherheitsdaten.

Statuszuordnung: `Released` = Claim `CONFIRMED`, `Reviewed` = `REVIEWED`, `Draft` = `DRAFT`.

Jira, Confluence und Rovo sind derzeit als „Connector fehlt“ markiert. Bis eine interne Schnittstelle konfiguriert ist, durchsuchen diese Tools die bereits importierte Evidence der jeweiligen Quelle und sagen das in der Antwort.

### Security Policy v1 (`security_policy.json`)

```
security_mode: INTERNAL_RESTRICTED · default_policy: DENY
external_network / external_llm / external_search / telemetry_external: false
allowed_sources: onescm360, jira_internal, confluence_internal, rovo_internal
```

Die App startet nicht, wenn `default_policy` nicht `DENY` ist oder ein externer Schalter auf `true` steht.

| Gate | Umsetzung im Pilot |
|---|---|
| 1 Authentication | lokaler Windows-Benutzer (Einzelplatz, localhost). SSO/Entra ID ist laut Projektentscheidung im Pilot nicht vorgesehen. |
| 2 Authorization | Profile je Benutzer in `profiles`: erlaubte Tools (Muster wie `search_*`), Kapitel und Operationen (`READ`, `WRITE_LOCAL`). Ohne Profil wird abgelehnt. Kapitelrechte filtern auch Suchergebnisse. Der Router kann sie nicht überschreiben. |
| 3 Tool-Allowlist | nur Tools der Registry. `search_web`, `send_email`, `delete_data`, `http_request` usw. werden vorgeschlagen, aber abgelehnt und protokolliert. |
| 4 Netzwerk | Im App-Prozess scheitert jede ausgehende Verbindung außer zu localhost (und den optional in `internal_networks` freigegebenen internen Netzen) technisch. Das lokale Modell muss auf localhost laufen. Ergänzend wird eine Firewall-Regel empfohlen, denn andere Programme auf dem Rechner deckt diese Sperre nicht ab. |
| 5 Audit | `data/audit.jsonl` pro Aufruf: Zeitpunkt, Benutzer, Session, Tool, Operation, Klassifikation, ALLOWED/DENIED, ausgeführt, Begründung, Router. Die Frage wird nur als Hash und Länge gespeichert, Suchtexte als Zeichenzahl. Mit `audit_include_prompt: true` würde die Frage im Klartext gespeichert. |

### Local First

Wissensfragen ohne ausdrücklichen Status durchlaufen diese Reihenfolge. Die erste Quelle mit Treffern liefert die Antwort:

1. `search_knowledge` mit Status **Released** (inkl. Regelwerk)
2. `search_knowledge` mit Status Reviewed, dann Draft (als „nicht freigegeben“ gekennzeichnet)
3. `search_manual`
4. `search_jira`, dann `search_confluence`, dann `query_rovo`
5. Ende: „Keine freigegebene Quelle gefunden.“ Es gibt keinen automatischen Rückgriff auf das Internet.

Jeder Schritt ist ein eigener, policy-geprüfter und auditierter Aufruf. Die Antwort zeigt die Kette.

### Router-Modi, Testsuite, Trainingsdaten

- **Router-Modi:**
  - Regeln (Standard, offline).
  - Lokales Modell über die Ollama-API `/api/chat` (`ONESCM_ROUTER_URL`, nur localhost; `ONESCM_ROUTER_MODEL`, Standard `functiongemma`). Erkannt werden Ollama-`tool_calls` und das rohe FunctionGemma-Format `<start_function_call>call:…{…}<end_function_call>`.
  - Was das Modell vorschlägt, läuft genauso durch die Policy. Ist es nicht erreichbar, antwortet der Regel-Router.
- **Routing-Testsuite** `chat_eval.json`: 30 Fälle mit erwartetem Tool, Kernparametern und, wo angegeben, der Policy-Entscheidung (u. a. Internet, E-Mail, Löschen → DENIED). Die Anzeige ist `Success: x / 30`, wie `check_success_rate` im Notebook.
- **Trainingsdaten:** Vorlagen über alle Kapitel, Rollen, Fahrzeugtypen und Regelbegriffe sowie bestätigtes Chat-Feedback. Enthalten sind nur Registry-Tools, die Testsuite ist ausgeschlossen. Formate: Notebook-Format (`user_content`, `tool_name`, `tool_arguments`) oder Chat-Format mit `tool_calls`.
- **Empfohlene Reihenfolge:** Tool Registry → Security Policy → Routing-Testsuite → Trainingsdatensatz → lokales Fine-Tuning (TRL `SFTTrainer`, wie im Notebook) → Offline-Akzeptanztest mit derselben Testsuite im Modus „Lokales Modell“.

## Export (OneDrive)

Der Export legt bei Bedarf diese Struktur an:

```
-oneSCM360/
├── 01_Rovo_Imports/CH01 … CH16
├── 02_Jira_Imports
├── 03_Confluence_Imports
├── 04_Source_Documents/HTML, Word
├── 05_Manual_Generated/Draft, Reviewed, Released
├── 06_Exports/JSON, CSV, API, Packages
├── Skill
├── Goal
└── 99_Archive
```

Je Kapitelexport entstehen:

- die Rohdateien
- ein JSON-Gesamtexport
- `KnowledgeBlocks.csv`, `Claims.csv`, `Evidence.csv` und `Coverage.csv`, passend zu den SharePoint-Listen
- Tabellen als CSV und JSON
- ein CONFIRMED-View unter `06_Exports/API` für Power BI und Agents
- ein Manifest mit SHA-256-Prüfsummen
- ein ZIP-Uploadpaket unter `06_Exports/Packages`

Lokale Statuswerte:

| Status | Bedeutung |
|---|---|
| `READY_FOR_CLIENT` | lokaler Ordner vorhanden und beschreibbar |
| `PATH_MISSING` | Zielpfad fehlt oder ist nicht konfiguriert |
| `NOT_READY` | lokaler Schreibtest fehlgeschlagen |

Ob Dateien in der Cloud angekommen sind, kann die App nicht erkennen. Das gilt auch für Konfliktkopien, DLP-Prüfungen und den SharePoint-Upload. Kontrollieren Sie das im OneDrive-Client.

## Handbuchstände

Im Register **Synchronisation** entsteht je Kapitel ein Handbuchstand. Die Stufe hängt am Gate:

| Stufe | Voraussetzung | Enthaltene Aussagen |
|---|---|---|
| Draft | immer | alle nicht abgelehnten Claims, ungeprüfte gekennzeichnet |
| Reviewed | Gate nicht BLOCKED | geprüfte und freigegebene Claims |
| Released | Gate READY | nur freigegebene Claims (`CONFIRMED`) |

Aufbau des Handbuchs:

- Fragen in der Reihenfolge des Kapitelschemas, gegliedert nach Fragegruppe.
- Je Aussage Rolle, Division, PI und Reifegrad sowie die Quelle, z. B. der Jira-Key.
- Die zugeordneten Tabellen. Tabellen ohne geprüfte Quellfrage fehlen.
- Ein Glossar aus dem Regelwerk.

Die Vorschau erscheint in der App. Beim Erzeugen entstehen HTML (öffnet in Word und im Browser) und Markdown unter `05_Manual_Generated/<Stufe>/` im OneDrive-Ordner. Bestehende Stände werden nie überschrieben.

## Bilder aus DOCX

Aus DOCX-Dateien extrahierte Bilder liegen unter `data/media/CHxx/<Import-ID>/`. Das Import-Ergebnis zeigt sie als Vorschaubilder. EMF, WMF, TIFF und SVG werden nur zum Herunterladen angeboten, SVG wegen möglicher Skripte nie direkt angezeigt.

## Daten und Bereinigung

Ablage unter `data\`:

| Pfad | Inhalt |
|---|---|
| `imports\IMP-*.json` | Importjournal mit den Status RECEIVED → PARSED → ANALYZED → COMPLETED oder FAILED |
| `raw\` | Rohdateien |
| `media\CHxx\` | aus DOCX extrahierte Bilder |
| `knowledge.json` | Knowledge Blocks, Claims, Evidence, Konflikte |
| `coverage\` | Coverage-Snapshots |
| `rules.json` | das Regelwerk. Wird beim ersten Start aus der ausgelieferten `rules.json` angelegt. |
| `chapters\` | eigene Fassungen der Kapitelschemas aus dem Register Kapitel |
| `backups\` | Sicherungen von Regelwerk (die letzten 30) und Kapitelschemas |
| `archive\` | archivierte Importe |

`data\rules.json` wird atomar geschrieben, also über eine temporäre Datei und anschließendes Ersetzen.

**Programm-Update:** Regelwerk und Kapitelschemas, die Sie in der App ändern, liegen in `data\`. `git pull` aktualisiert nur das Programm und die ausgelieferten Vorlagen, Ihre Eingaben bleiben unberührt. Ein Kapitel ohne eigene Fassung nutzt immer die ausgelieferte Vorlage aus `chapters\`.

Imports sind idempotent: Dieselbe Datei mit gleichem Kapitel, gleicher Sprache und gleichem Quelltyp liefert das vorhandene Ergebnis. Mit „Gleiche Datei erneut verarbeiten“ wird der Import unter derselben Import-ID neu aufgebaut.

Exportierte Importe lassen sich im Dashboard archivieren. Löschen entfernt einen Import samt den daraus erzeugten Claims und Evidence.

**Regelbasierte Bereinigung** im Register Synchronisation, Regeln in `cleanup_rules.json`:

| Regel | Wirkung |
|---|---|
| `quarantine-invalid` | Beschädigte Import-JSONs nach `data/archive/_invalid` verschieben. |
| `delete-failed` | Fehlgeschlagene Importläufe nach 14 Tagen löschen. |
| `archive-exported` | Exportierte Importe nach 30 Tagen archivieren (Import-JSON und Rohdatei). Claims und Evidence bleiben erhalten. |
| `purge-archive` | Archivierte Importe nach 365 Tagen endgültig löschen. |

Ablauf:

1. Die Vorschau listet, was die Regeln betreffen.
2. Ausgeführt werden nur die ausgewählten Einträge, nach einer Rückfrage.
3. Einträge, die nicht (mehr) in der Vorschau stehen, werden übersprungen.

## Sicherheit

- Der Server bindet nur an `127.0.0.1`. Anfragen mit fremdem Host-Header werden abgewiesen, das schützt gegen DNS-Rebinding.
- Ändernde Anfragen brauchen den Header `X-oneSCM360`, das schützt gegen Cross-Site-Requests.
- Es gibt keine Tokens oder Zugangsdaten.
- Dateinamen werden bereinigt.
- CSV-Zellen, die mit `=`, `+`, `-` oder `@` beginnen, werden gegen Formel-Injection entschärft.

## Tests

```
py -3 -m pip install -r requirements.txt
py -3 -m unittest discover -s tests -v
```

Optionaler Browsertest (Playwright):

```
py -3 -m pip install playwright
py -3 -m playwright install chromium
py -3 tests\browser_workflow.py
```

## Projektbaum

```
onescm360_app_build/
├── app.py                  Flask-App und API
├── index.html              Oberfläche (Register)
├── static/                 app.js, style.css
├── rules.json              ausgelieferte Vorlage des Regelwerks (bearbeitet wird data\rules.json)
├── classification.json     Rollen und Domänen für den Mehrfachimport
├── tool_registry.json      Tool Registry v1 (Schemas + Sicherheits-Metadaten)
├── security_policy.json    Security Policy v1 (INTERNAL_RESTRICTED, default DENY, Profile)
├── chat_eval.json          Routing-Testsuite
├── cleanup_rules.json      Regeln der Datenbereinigung
├── chapters/CH01…CH16.json ausgelieferte Kapitelschemas (eigene Fassungen: data\chapters)
├── schemas/                import.schema.json, claim.schema.json
├── services/               import, docx/html parser, rules, claims, knowledge, conflicts, coverage, export
├── data/                   Laufzeitdaten (nicht versioniert)
├── tests/
├── start_onescm360.ps1
├── README.md
└── requirements.txt
```

## Offene Punkte

- CH02 bis CH16: Die fachlichen Fragenkataloge, Kritikalitäten und Rollen fehlen noch. Sie werden im Register Kapitel gepflegt oder per CSV übernommen.
- Claim-Zerlegung und Subject/Predicate/Object-Erkennung sind regelbasiert und bewusst konservativ. Ergebnisse immer im Register Claims prüfen.
