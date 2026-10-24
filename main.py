"""Postfach Agent.

Befehle:
  python main.py            startet den Agenten dauerhaft (alle 30 Minuten + 7 Uhr Zusammenfassung)
  python main.py check      prüft, ob alles richtig eingerichtet ist
  python main.py once       prüft die Postfächer genau einmal
  python main.py digest     schickt die Tageszusammenfassung sofort
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from mailagent.config import TIMEZONE, load_accounts, load_settings
from mailagent.jobs import run_cycle, run_digest

log = logging.getLogger("main")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%d.%m. %H:%M:%S",
    )
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def check() -> int:
    import os

    import anthropic

    from mailagent.gmail_client import GmailClient
    from mailagent.telegram import Telegram

    settings = load_settings()
    problems = 0

    def ok(msg): print(f"✅ {msg}")
    def bad(msg):
        nonlocal problems
        problems += 1
        print(f"❌ {msg}")

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            client = anthropic.Anthropic()
            client.messages.create(model=settings.model_classify, max_tokens=200,
                                   messages=[{"role": "user", "content": "Antworte mit: ok"}])
            ok(f"Claude Schlüssel funktioniert ({settings.model_classify})")
        except Exception as e:
            bad(f"Claude Schlüssel oder Modell fehlerhaft: {e}")
    else:
        bad("ANTHROPIC_API_KEY fehlt in .env")

    if not (settings.google_client_id and settings.google_client_secret):
        bad("GOOGLE_CLIENT_ID oder GOOGLE_CLIENT_SECRET fehlt in .env")
    accounts = load_accounts(only_connected=False)
    for acc in accounts:
        if not acc.connected:
            bad(f"Konto '{acc.name}' ist nicht verbunden. Ausführen: python einrichten.py {acc.key}")
            continue
        try:
            gmail = GmailClient(acc, settings.google_client_id, settings.google_client_secret)
            ok(f"Konto '{acc.name}' verbunden als {gmail.email}")
        except Exception as e:
            bad(f"Konto '{acc.name}' funktioniert nicht: {e}")

    tg = Telegram(settings.telegram_token, settings.telegram_chat_id)
    if tg.ready:
        if tg.send("✅ Test vom Postfach Agenten. Telegram funktioniert."):
            ok("Telegram Testnachricht gesendet, schau auf dein Handy")
        else:
            bad("Telegram Nachricht konnte nicht gesendet werden")
    else:
        bad("Telegram ist nicht eingerichtet (python einrichten.py)")

    if settings.dry_run:
        print("ℹ️  DRY_RUN ist an: Der Agent verändert nichts.")
    print("\nAlles in Ordnung." if not problems else f"\n{problems} Problem(e) gefunden.")
    return 1 if problems else 0


def run_forever() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    settings = load_settings()
    if not load_accounts():
        log.error("Kein Gmail Konto verbunden. Bitte zuerst 'python einrichten.py' ausführen.")
        sys.exit(1)

    tz = ZoneInfo(TIMEZONE)
    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        run_cycle, "interval", minutes=settings.check_interval_minutes,
        next_run_time=datetime.now(tz), max_instances=1, coalesce=True,
        misfire_grace_time=300, id="cycle",
    )
    scheduler.add_job(
        run_digest, "cron", hour=settings.digest_hour, minute=0,
        max_instances=1, coalesce=True, misfire_grace_time=3600, id="digest",
    )
    log.info("Agent läuft. Prüfung alle %d Minuten, Zusammenfassung täglich um %02d:00 (%s).",
             settings.check_interval_minutes, settings.digest_hour, TIMEZONE)
    if settings.dry_run:
        log.warning("DRY_RUN ist an: Es wird nichts verändert.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Agent beendet.")


def main() -> None:
    setup_logging()
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "check":
        sys.exit(check())
    elif command == "once":
        run_cycle()
    elif command == "digest":
        run_digest()
    elif command == "run":
        run_forever()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
