"""Die beiden Aufgaben des Agenten: Postfächer prüfen und Tageszusammenfassung."""
from __future__ import annotations

import logging
import time

import anthropic
from google.auth.exceptions import RefreshError

from . import digest
from .config import Account, Settings, load_accounts, load_settings
from .gmail_client import GmailClient
from .processor import process_account
from .telegram import Telegram, esc

log = logging.getLogger(__name__)

_auth_warned: dict[str, float] = {}
AUTH_WARN_EVERY = 12 * 3600


def _make_gmail(account: Account, settings: Settings) -> GmailClient:
    return GmailClient(account, settings.google_client_id, settings.google_client_secret)


def _auth_problem(account: Account, telegram: Telegram) -> None:
    last = _auth_warned.get(account.key, 0)
    if time.time() - last < AUTH_WARN_EVERY:
        return
    _auth_warned[account.key] = time.time()
    telegram.send(
        f"⚠️ <b>{esc(account.name)}</b>: Die Verbindung zu Gmail ist abgelaufen oder wurde entzogen. "
        f"Bitte auf deinem Computer <code>python einrichten.py {account.key}</code> ausführen. "
        f"Danach den neuen Wert von GMAIL_{account.prefix}_REFRESH_TOKEN aus der .env Datei "
        f"auch bei Render eintragen."
    )


def run_cycle() -> None:
    settings = load_settings()
    telegram = Telegram(settings.telegram_token, settings.telegram_chat_id)
    accounts = load_accounts()
    if not accounts:
        log.error("Kein Gmail Konto verbunden. Bitte zuerst 'python einrichten.py' ausführen.")
        return
    claude = anthropic.Anthropic()
    for account in accounts:  # Konten sind getrennt: ein Fehler stoppt das andere nicht
        try:
            process_account(account, _make_gmail(account, settings), claude, telegram, settings)
        except RefreshError:
            log.error("[%s] Gmail Zugang abgelaufen.", account.name)
            _auth_problem(account, telegram)
        except Exception:
            log.exception("[%s] Durchlauf fehlgeschlagen", account.name)


def run_digest() -> None:
    settings = load_settings()
    telegram = Telegram(settings.telegram_token, settings.telegram_chat_id)
    for account in load_accounts():
        try:
            text = digest.build_digest(account, _make_gmail(account, settings))
            telegram.send(text)
        except RefreshError:
            log.error("[%s] Gmail Zugang abgelaufen.", account.name)
            _auth_problem(account, telegram)
        except Exception:
            log.exception("[%s] Zusammenfassung fehlgeschlagen", account.name)
            telegram.send(f"⚠️ Die Zusammenfassung für <b>{esc(account.name)}</b> ist fehlgeschlagen. "
                          f"Details stehen im Protokoll.")
