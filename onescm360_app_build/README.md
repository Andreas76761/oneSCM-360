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
| Claims | Claims filtern, bearbeiten (Subject/Predicate/Object, Rolle, Division, PI, Reifegrad …), bestätigen, löschen, manuell anlegen, Evidence zuordnen. |
| Evidence | Evidence-Stufe und -Status pflegen, Faktor sehen, löschen. |
| Tabellen | Separat extrahierte Tabellen ansehen, Quellfrage zuordnen, als JSON oder CSV herunterladen. |
| Coverage | Readiness, sechs Dimensionen, Gate, Hard Blocker, Konflikte (auflösen mit Begründung), Rollenabdeckung. |
| Synchronisation | Verbindung zum lokalen OneDrive-Ordner, Ordnerstruktur anlegen, Kapitel exportieren, Hinweise zum manuellen SharePoint-Transfer. |
| Interner Chat | Fragen in natürlicher Sprache. Ein Router ordnet jede Frage genau einer Funktion mit Parametern zu und führt sie auf den lokalen Daten aus (siehe unten). Nur lesend. |
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

## Interner Chat (Router nach FunctionGemma-Prinzip)

Vorbild ist das Google-Notebook „Fine-tuning with FunctionGemma“ (`google/functiongemma-270m-it`). Ein kleines Modell lernt dort, eine Frage dem richtigen Werkzeug zuzuordnen, im Beispiel interne Wissensbasis oder Google-Suche. Die Anwendung führt das Werkzeug danach aus.

So arbeitet der Chat:

1. Ein **Router** macht aus der Frage genau einen Funktionsaufruf, z. B. `get_coverage({"chapter": "CH01"})`.
2. Die App führt die Funktion auf den lokalen Daten aus. Die Antwort zeigt den Aufruf und das Ergebnis mit Links in die Register.
3. Der Chat ändert keine Daten.
4. Antworten aus Claims mit Status `DRAFT` oder `REVIEWED` sind als nicht bestätigt markiert. Abgelehnte Claims erscheinen nie.

| Funktion | Zweck |
|---|---|
| `search_knowledge` | internes Wissen durchsuchen (optional Kapitel, Rolle, Domäne) |
| `get_coverage` | Readiness, Gate und Dimensionen eines Kapitels |
| `list_blockers` | Hard Blocker eines Kapitels |
| `list_conflicts` | Konflikte, optional nach Status |
| `find_claims` | Claims nach Kapitel, Status, Evidence (`missing`/`indirect`/`direct`), Rolle, Kritikalität |
| `get_claim` | einen Claim mit Evidence |
| `lookup_rule` | Begriff im Regelwerk |
| `list_imports` | Importe nach Kapitel, Sprache, Rolle, Domäne |
| `search_tables` | Tabellen durchsuchen |
| `search_external` | Jira, Confluence, Rovo oder Web |

`search_external` wird erkannt, ist aber nicht angebunden, gemäß der Entscheidung „kein Graph, keine Tokens“. Der Chat liefert dann eine kopierbare Suchanfrage.

### Router-Modi

- **Regeln (Standard):** offline, ohne KI-Modell, reproduzierbar.
- **Lokales Modell:** Das Modell wird über die Ollama-API `/api/chat` mit den Funktionsdeklarationen aufgerufen.
  - Adresse und Modell kommen aus `ONESCM_ROUTER_URL` (Standard `http://127.0.0.1:11434`, nur localhost erlaubt) und `ONESCM_ROUTER_MODEL` (Standard `functiongemma`).
  - Erkannt werden Ollama-`tool_calls` und das rohe FunctionGemma-Format `<start_function_call>call:…{…}<end_function_call>`.
  - Unbekannte Funktionen und ungültige Parameter werden verworfen.
  - Ist das Modell nicht erreichbar oder die Antwort ungültig, antwortet der Regel-Router und zeigt einen Hinweis.

### Router-Test und Trainingsdaten

- **Router testen:** prüft den gewählten Router gegen den Testsatz `chat_eval.json` mit 24 Fragen und zeigt `Success: x / 24`, wie `check_success_rate` im Notebook.
- **Feedback:** Unter jeder Antwort bestätigen Sie die Funktion („✓ Ja“) oder wählen die richtige. Das Feedback landet in `data/chat_feedback.jsonl`.
- **Trainingsdaten:** Der Export enthält Vorlagen über alle Kapitel, Rollen, Domänen und Regelwerksbegriffe sowie das bestätigte Feedback. Die Fragen des Testsatzes sind ausgeschlossen. Formate:
  - Notebook-Format: `user_content`, `tool_name`, `tool_arguments` als JSON-String.
  - Chat-Format: `messages` mit Rollen `developer`/`user`/`assistant` und `tool_calls` sowie `tools`.
- Das Fine-Tuning selbst ist nicht Teil der App. Es läuft wie im Notebook mit Transformers/TRL `SFTTrainer`, z. B. in Colab.

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

## Daten und Bereinigung

Ablage unter `data\`:

| Pfad | Inhalt |
|---|---|
| `imports\IMP-*.json` | Importjournal mit den Status RECEIVED → PARSED → ANALYZED → COMPLETED oder FAILED |
| `raw\` | Rohdateien |
| `media\CHxx\` | aus DOCX extrahierte Bilder |
| `knowledge.json` | Knowledge Blocks, Claims, Evidence, Konflikte |
| `coverage\` | Coverage-Snapshots |
| `backups\` | Sicherungen von `rules.json` (die letzten 30) |
| `archive\` | archivierte Importe |

`rules.json` wird atomar geschrieben, also über eine temporäre Datei und anschließendes Ersetzen.

Imports sind idempotent: Dieselbe Datei mit gleichem Kapitel, gleicher Sprache und gleichem Quelltyp liefert das vorhandene Ergebnis. Mit „Gleiche Datei erneut verarbeiten“ wird der Import unter derselben Import-ID neu aufgebaut.

Exportierte Importe lassen sich im Dashboard archivieren. Löschen entfernt einen Import samt den daraus erzeugten Claims und Evidence.

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
├── rules.json              editierbares Regelwerk
├── classification.json     Rollen und Domänen für den Mehrfachimport
├── chat_eval.json          Testsatz für den Chat-Router
├── chapters/CH01…CH16.json Kapitelkonfiguration (Fragen, Kritikalität, Rollen)
├── schemas/                import.schema.json, claim.schema.json
├── services/               import, docx/html parser, rules, claims, knowledge, conflicts, coverage, export
├── data/                   Laufzeitdaten (nicht versioniert)
├── tests/
├── start_onescm360.ps1
├── README.md
└── requirements.txt
```

## Offene Punkte

- CH02 bis CH16: Die fachlichen Fragenkataloge, Kritikalitäten und Rollen fehlen noch. Sie werden in `chapters\CHxx.json` gepflegt; die App braucht dafür keine Codeänderung.
- Claim-Zerlegung und Subject/Predicate/Object-Erkennung sind regelbasiert und bewusst konservativ. Ergebnisse immer im Register Claims prüfen.
