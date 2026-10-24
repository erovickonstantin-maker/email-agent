# Postfach Agent

Der Agent schaut alle 30 Minuten in zwei Gmail Postfächer (privat und headneckmasterclass), sortiert neue Mails mit Claude, schreibt Antwortentwürfe und meldet Wichtiges per Telegram. Beide Postfächer werden komplett getrennt behandelt.

## Was er macht

| Funktion | Details |
|---|---|
| Sortieren | Claude Haiku ordnet jede neue Mail ein: Wichtig, Antwort nötig, Info, Werbung, Newsletter. Dazu setzt er Gmail Labels (`Agent/Wichtig` usw.). |
| Aufräumen | Werbung und Newsletter wandern aus dem Posteingang ins Archiv (alle Mails). **Es wird nie etwas gelöscht.** |
| Antwortentwürfe | Bei "Antwort nötig" schreibt Claude Sonnet einen Entwurf und speichert ihn in Gmail unter Entwürfe. **Es wird nie etwas gesendet.** |
| Sofortmeldung | Bei wirklich wichtigen Mails (Fristen, Zahlungen, Kursanmeldungen, Schule) kommt sofort eine Telegram Nachricht. |
| Tagesübersicht | Jeden Tag um 7 Uhr (Wien) pro Postfach: Wichtiges, Offenes, bereitliegende Entwürfe. |
| Geheimnisse | Alle Schlüssel stehen nur in der Datei `.env`, nicht im Code. |

Kleine Ergänzung: Ist eine wichtige Mail zugleich eine Anfrage (zum Beispiel eine Kursfrage), bekommt sie beide Labels (Wichtig und Antwort nötig) und einen Entwurf.

Mails, die schon bearbeitet wurden, bekommen das Label `Agent-Verarbeitet`. So merkt sich der Agent alles direkt in Gmail und braucht keine eigene Datenbank. Das funktioniert auch auf Render, wo Dateien nicht dauerhaft bleiben.

**Datenschutz:** Zum Sortieren und Schreiben wird der Text der Mails an die Claude Schnittstelle von Anthropic geschickt.

---

# Teil 1: Auf deinem Computer testen

Alles mit 🔴 musst du selbst machen. Der Rest passiert automatisch.

## Schritt 1: Python prüfen

🔴 Öffne das Terminal (Mac: Programm "Terminal", Windows: Programm "Eingabeaufforderung") und tippe:

```
python --version
```

Es muss `Python 3.10` oder höher erscheinen. Auf dem Mac heisst der Befehl oft `python3`. Wenn Python fehlt: 🔴 von python.org herunterladen und installieren (bei Windows den Haken "Add Python to PATH" setzen).

## Schritt 2: Programme installieren

🔴 Wechsle im Terminal in den Ordner `email-agent` (zum Beispiel `cd Pfad/zum/email-agent`) und tippe:

```
pip install -r requirements.txt
```

(Mac: `pip3 install -r requirements.txt`)

## Schritt 3: Claude Schlüssel holen

1. 🔴 Gehe auf console.anthropic.com und melde dich an.
2. 🔴 Lege unter "Billing" etwas Guthaben an (wenige Euro reichen zum Start).
3. 🔴 Unter "API Keys" einen neuen Key erstellen und kopieren. Du fügst ihn gleich in Schritt 6 ein.

## Schritt 4: Google einrichten (einmalig, das dauert am längsten)

Der Agent braucht von Google eine Erlaubnis, deine Postfächer zu lesen. Das geht nur über die Google Cloud Konsole. Es kostet nichts.

1. 🔴 Öffne console.cloud.google.com und melde dich mit einem deiner Google Konten an.
2. 🔴 Oben auf die Projektauswahl klicken, dann "Neues Projekt", Name `Postfach Agent`, erstellen.
3. 🔴 Menü "APIs und Dienste", dann "Bibliothek", nach `Gmail API` suchen, anklicken, "Aktivieren".
4. 🔴 Menü "APIs und Dienste", dann "OAuth Zustimmungsbildschirm" (heisst teils "Google Auth Platform"). "Jetzt starten":
   * App Name: `Postfach Agent`
   * Support E-Mail: deine Adresse
   * Zielgruppe: **Extern**
   * Kontakt E-Mail: deine Adresse, dann abschliessen
5. 🔴 Unter "Zielgruppe" (Audience) bei "Testnutzer" **beide** Gmail Adressen hinzufügen (privat und headneckmasterclass).
6. 🔴 Unter "Datenzugriff" (Data Access) "Bereiche hinzufügen", nach `gmail.modify` suchen, den Bereich `.../auth/gmail.modify` anhaken, speichern.
7. 🔴 **Wichtig:** Unter "Zielgruppe" auf "App veröffentlichen" klicken (Status "In Produktion"). Sonst läuft der Zugang nach 7 Tagen ab und der Agent hört plötzlich auf. Die App muss dafür nicht von Google geprüft werden, du siehst beim Anmelden nur eine Warnung (siehe Schritt 6).
8. 🔴 Menü "Clients" (oder "Anmeldedaten"), dann "Client erstellen" bzw. "Anmeldedaten erstellen", "OAuth Client ID". Anwendungstyp: **Desktop App**. Erstellen.
9. 🔴 Kopiere die **Client ID** und den **Clientschlüssel (Client Secret)**. Du fügst beide gleich in Schritt 6 ein.

## Schritt 5: Telegram Bot erstellen

1. 🔴 Öffne Telegram und suche nach `@BotFather`.
2. 🔴 Schicke ihm `/newbot`, vergib einen Namen und einen Benutzernamen (muss auf `bot` enden).
3. 🔴 Er schickt dir einen **Token** (lange Zeichenfolge). Kopiere ihn für Schritt 6.

## Schritt 6: Alles verbinden

🔴 Tippe im Terminal:

```
python einrichten.py
```

Das Programm fragt nacheinander nach allem, was fehlt, und speichert es selbst in der Datei `.env`:

1. Claude Key einfügen, Enter.
2. Google Client ID und Client Secret einfügen, Enter.
3. Es öffnet sich ein Browser. 🔴 Melde dich mit dem **privaten** Gmail Konto an. Kommt die Warnung "Google hat diese App nicht überprüft": auf "Erweitert" klicken, dann "Weiter zu Postfach Agent (unsicher)", dann die Berechtigungen erlauben. Das ist deine eigene App, das ist sicher.
4. Danach nochmal dasselbe mit dem **headneckmasterclass** Konto. 🔴 Achte darauf, dass du im Browser das richtige Konto wählst.
5. Telegram Token einfügen. 🔴 Dann deinem Bot in Telegram eine Nachricht schicken (zum Beispiel "Hallo"). Das Programm erkennt dich automatisch.

Nichts davon ist schlimm, wenn es schiefgeht: Du kannst `python einrichten.py` jederzeit nochmal ausführen. Es fragt nur nach dem, was noch fehlt. Ein einzelnes Konto neu verbinden: `python einrichten.py privat` oder `python einrichten.py headneck`.

## Schritt 7: Prüfen

🔴 Tippe:

```
python main.py check
```

Du solltest nur grüne Haken sehen und eine Testnachricht auf dem Handy bekommen.

## Schritt 8: Sicherer Testlauf (ohne etwas zu verändern)

1. 🔴 Öffne die Datei `.env` mit einem Texteditor und setze `DRY_RUN=1`.
2. 🔴 Tippe `python main.py once`.

Der Agent sortiert jetzt die Mails der letzten 2 Tage und schreibt im Terminal, was er tun würde. Er verändert nichts, schreibt keine Entwürfe und schickt keine Telegram Meldungen. Schau, ob die Einordnung zu deinen Mails passt.

## Schritt 9: Echter Testlauf

1. 🔴 Setze in der `.env` wieder `DRY_RUN=0`.
2. 🔴 Tippe `python main.py once`.
3. 🔴 Öffne Gmail und schau nach: Labels `Agent/...` in der linken Leiste, Entwürfe unter "Entwürfe", Werbung und Newsletter im Archiv ("Alle Mails").
4. 🔴 Tippe `python main.py digest`, um die Tagesübersicht sofort zu sehen.

Beim ersten echten Lauf werden bis zu 25 Mails pro Durchlauf bearbeitet (Mails der letzten 2 Tage). Es können also gleich mehrere Telegram Meldungen kommen. Das ist normal.

## Schritt 10: Dauerbetrieb auf deinem Computer

🔴 Tippe:

```
python main.py
```

Das Fenster muss offen bleiben und der Computer darf nicht schlafen. Beenden mit `Strg + C`. Für den Betrieb ohne Computer folgt Teil 2.

---

# Teil 2: Auf Render laufen lassen (wenn dein Computer aus ist)

Mache das erst, wenn Teil 1 gut funktioniert.

**Kosten:** Render bietet für Dauerprogramme ("Background Worker") keinen kostenlosen Tarif. Der kleinste Tarif kostet ein paar Dollar im Monat. Den aktuellen Preis siehst du beim Anlegen auf render.com.

1. 🔴 Lade den Ordner auf GitHub hoch (Repository `email-agent`). Stelle das Repository auf **privat**. Die Datei `.env` wird dank `.gitignore` nie mit hochgeladen. Prüfe trotzdem auf GitHub, dass sie nicht sichtbar ist.
2. 🔴 Erstelle ein Konto auf render.com und verbinde dein GitHub.
3. 🔴 Klicke "New", dann "Blueprint", wähle das Repository `email-agent`. Render liest die Datei `render.yaml` selbst.
4. 🔴 Render fragt nach den Werten. Kopiere sie aus deiner `.env` Datei:
   * `ANTHROPIC_API_KEY`
   * `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   * `GMAIL_PRIVAT_REFRESH_TOKEN`, `GMAIL_HEADNECK_REFRESH_TOKEN`
   * `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   * Optional: `PRIVAT_CONTEXT`, `HEADNECK_CONTEXT`, `PRIVAT_SENDER_NAME`, `HEADNECK_SENDER_NAME` (leere Felder dürfen leer bleiben)
5. 🔴 Auf "Apply" bzw. "Deploy" klicken. Nach 1 bis 2 Minuten läuft der Agent. Im Reiter "Logs" siehst du, was er macht ("Agent läuft. Prüfung alle 30 Minuten ...").
6. 🔴 **Stoppe den Agenten auf deinem Computer** (`Strg + C`), sobald Render läuft. Zwei Agenten gleichzeitig würden doppelte Meldungen und Entwürfe erzeugen.

Möchtest du, dass ich das Anlegen auf Render für dich übernehme? Sag Bescheid, dann machen wir es zusammen Schritt für Schritt.

---

# Hilfreiches

## Wissen für Antwortentwürfe

Claude erfindet in Entwürfen nichts. Er nutzt nur die Mail selbst und Texte, die du ihm gibst. 🔴 Lege dafür im Ordner `knowledge` Textdateien an:

* `knowledge/headneck.txt` für das headneckmasterclass Postfach (Kurse, Preise, Termine, Anmeldung)
* `knowledge/privat.txt` für das private Postfach

Fehlt eine Information, steht im Entwurf `[BITTE ERGÄNZEN: ...]`. Entwürfe an headneckmasterclass sind standardmässig auf Englisch, private in der Sprache der Mail.

## Was der Agent nie tut

* Er sendet keine Mails. Im Code gibt es keinen Sendebefehl, ein Test prüft das.
* Er löscht keine Mails. Es gibt keinen Löschbefehl im Code, ein Test prüft das. Werbung und Newsletter liegen im Archiv und sind über die Suche oder das Label auffindbar.
* Er verändert keine Mails, die er schon bearbeitet hat.

Technisch erlaubt Googles Zugriffsstufe `gmail.modify` auch Senden, deshalb ist es wichtig, dass der Code unverändert bleibt. Das Löschen für immer ist mit dieser Stufe von Google aus nicht möglich.

## Offenes in der Tagesübersicht

"Offen" sind Mails mit dem Label `Agent/Antwort nötig`, die noch im Posteingang liegen und auf die du noch nicht geantwortet hast. Hast du eine Mail erledigt, antworte oder archiviere sie, dann verschwindet sie aus der Liste.

## Einstellungen in der `.env`

| Name | Bedeutung | Standard |
|---|---|---|
| `CHECK_INTERVAL_MINUTES` | Wie oft geprüft wird | 30 |
| `DIGEST_HOUR` | Uhrzeit der Tagesübersicht (Wien) | 7 |
| `LOOKBACK_DAYS` | Wie viele Tage zurück Mails betrachtet werden | 2 |
| `MAX_MAILS_PER_RUN` | Maximal bearbeitete Mails pro Durchlauf | 25 |
| `MODEL_CLASSIFY` | Modell zum Sortieren | claude-haiku-5-5 |
| `MODEL_DRAFT` | Modell für Entwürfe | claude-sonnet-5-5 |
| `DRY_RUN` | 1 = nur ansehen, nichts verändern | 0 |

## Kosten für Claude

Sortiert wird mit dem günstigen Haiku, Sonnet kommt nur für Entwürfe zum Einsatz. Bei einem normalen Postfach sind das voraussichtlich wenige Euro im Monat oder weniger. Das habe ich nicht mit deinen echten Mails gemessen. Schau nach ein paar Tagen unter console.anthropic.com auf die Nutzung.

## Probleme

| Meldung | Lösung |
|---|---|
| `Gmail Zugang abgelaufen` (kommt auch per Telegram) | 🔴 `python einrichten.py privat` bzw. `headneck` ausführen. Auf Render danach den neuen Wert von `GMAIL_..._REFRESH_TOKEN` aus der `.env` bei Render eintragen. Passiert diese Meldung nach 7 Tagen, ist die Google App noch nicht veröffentlicht (Schritt 4, Punkt 7). |
| Keine Telegram Nachrichten | 🔴 `python einrichten.py telegram` ausführen und `python main.py check`. |
| `Claude Schlüssel oder Modell fehlerhaft` | 🔴 Key und Guthaben bei console.anthropic.com prüfen. |
| Eine Mail wird nie bearbeitet | Nach 3 Fehlversuchen überspringt der Agent sie bis zum nächsten Neustart. Die Ursache steht im Protokoll. |

## Technik für Interessierte

* `main.py` startet den Zeitplan (APScheduler, Zeitzone Europe/Vienna)
* `einrichten.py` führt durch die Einrichtung
* `mailagent/gmail_client.py` Gmail Zugriff, `ai.py` Claude, `telegram.py`, `processor.py` Sortierlogik, `digest.py` Tagesübersicht
* Tests: `python -m unittest discover -s tests`
