# Aktualisieren auf oneSCM-360 v0.8.1

Stand: **04.11.2026**. Die neue Oberfläche wird vom lokalen Python-Server
bereitgestellt. Ein bereits laufender Server liefert weiterhin seine alte Version,
auch wenn eine neue ZIP heruntergeladen wurde.

## Update mit Erhalt der vorhandenen Daten

1. In der alten Anwendung offene Gliederungsänderungen **Speichern**. In der
   zugehörigen Konsole den angezeigten Datenordner notieren. Standard unter Windows:
   `%LOCALAPPDATA%\oneSCM-360`.
2. In genau dieser Konsole **Strg+C** drücken, um den alten Server zu beenden.
   Ein geschlossenes Browserfenster beendet den Server nicht.
3. Den gesamten Datenordner in einen separaten Sicherungsordner kopieren, während
   die Anwendung beendet ist. Datenbank und zugehörige Dateien zusammen sichern.
   Den aktiven Datenordner nicht in OneDrive oder auf einem Netzlaufwerk betreiben;
   abgeschlossene Sicherungskopien können dort nach den eigenen Vorgaben liegen.
4. Die [aktuelle ZIP](https://github.com/Andreas76761/oneSCM-360/archive/refs/heads/main.zip)
   herunterladen und in einen **neuen Programmordner** entpacken, beispielsweise
   `C:\oneSCM-360-v0.8.1`. Die ZIP muss vollständig entpackt sein.
5. Im neuen Ordner `start.bat` doppelklicken. Python 3.11 oder neuer mit `py`-Launcher
   muss installiert sein. Der erste Start installiert die Paketabhängigkeiten;
   dafür wird Netzwerkzugriff zu den Paketquellen benötigt.
6. Den in der neuen Konsole angezeigten Datenordner prüfen. Bei Standardinstallation
   wird der bisherige lokale Datenbestand wiederverwendet. Wer zuvor `--data-dir`
   verwendet hat, muss denselben eigenen Pfad weiter angeben.
7. `http://127.0.0.1:8765` öffnen und **Strg+F5** drücken. Oben rechts muss
   **v0.8.1 · 04.11.2026** stehen. Die Bibliothek enthält nun unter anderem
   **Interner Chatbot**, **Releaseverwaltung** und **Quellenwidersprüche**.
8. Eine bekannte Gliederung, vorhandene Quellen und eine gespeicherte Ausgabe
   kontrollieren. Erst danach produktiv weiterarbeiten. Sicherung aufbewahren.

Für vorhandene Microsoft-365-Copilot-, Claude- oder Gemini-Chat-Abonnements
sind weder API-Schlüssel noch eine Ollama-Installation erforderlich. Der Austausch
von Arbeitsaufträgen und Antworten erfolgt manuell über die neue Oberfläche.

Neue Datenbanktabellen werden beim Start ergänzt. Historische Dateien werden nicht
neu erzeugt. Vorhandene Daten werden nicht durch eine leere Beispieldatenbank aus
der ZIP ersetzt. Die ZIP enthält Programmdateien und Frontend, keine eigenen
Quellen, persönlichen Screens oder Arbeitsdaten.

## Wenn weiterhin die alte Oberfläche erscheint

| Beobachtung | Prüfung und nächster Schritt |
|---|---|
| Alte Versionsnummer trotz neuer ZIP | Alte Serverkonsole mit Strg+C beenden; `start.bat` aus dem neuen entpackten Ordner starten; Strg+F5 |
| Port 8765 belegt / neuer Server startet nicht | Meist läuft noch der alte Server. Zugehörige Konsole finden und beenden; erst dann erneut starten |
| Oberfläche geöffnet, Funktionen reagieren nicht | Nicht `web/index.html` direkt öffnen; Server starten und die HTTP-Adresse verwenden |
| Bisherige Gliederungen fehlen | Datenpfad in der Konsole mit dem vorherigen Pfad vergleichen; keinen neuen Datenbestand über die Sicherung kopieren |
| Python oder `py` nicht gefunden | Python 3.11+ einschließlich Windows-Launcher installieren und Start erneut versuchen |
| Paketinstallation scheitert | Fehlermeldung in der Konsole prüfen; Netzwerk-/Proxyfreigabe für Python-Paketquellen klären |
| Browser zeigt neue Version, Office-Ausgabe sieht anders aus | Verwendete Templaterevision und installierte Schriften prüfen; neue Version mit echten Office-Mustern abnehmen |

Ein Zurückwechseln auf eine alte Programmversion ist nicht automatisch eine
Datenbank-Rücknahme. Für eine vollständige Rückkehr zuerst beide Server beenden,
den aktuellen Datenordner separat sichern und anschließend die vorherige
Sicherung zusammen mit dem passenden alten Programmstand verwenden. Seit der
Sicherung entstandene Änderungen sind darin nicht enthalten.

[Bedienungsanleitung](BEDIENUNG.md) · [Funktionsstand](../FUNKTIONSSTATUS.md)
