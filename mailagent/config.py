"""Alle Einstellungen. Geheimnisse kommen ausschliesslich aus der .env Datei."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
KNOWLEDGE_DIR = ROOT / "knowledge"

load_dotenv(ENV_PATH)

TIMEZONE = "Europe/Vienna"

# Kategorien (genau diese fünf)
WICHTIG = "Wichtig"
ANTWORT = "Antwort nötig"
INFO = "Info"
WERBUNG = "Werbung"
NEWSLETTER = "Newsletter"
CATEGORIES = (WICHTIG, ANTWORT, INFO, WERBUNG, NEWSLETTER)
# Diese Kategorien verschwinden aus dem Posteingang (werden archiviert, nie gelöscht)
ARCHIVE_CATEGORIES = (WERBUNG, NEWSLETTER)

LABEL_PREFIX = "Agent/"
PROCESSED_LABEL = "Agent-Verarbeitet"


def label_name(category: str) -> str:
    return f"{LABEL_PREFIX}{category}"


def all_label_names() -> list[str]:
    return [label_name(c) for c in CATEGORIES] + [PROCESSED_LABEL]


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Account:
    key: str            # interner Name, z.B. "privat"
    prefix: str         # Präfix in der .env, z.B. "PRIVAT"
    name: str           # Anzeigename
    refresh_token: str
    context: str        # Beschreibung des Postfachs für Claude
    sender_name: str    # Name unter Antwortentwürfen
    reply_hint: str     # Zusatzregeln für Antwortentwürfe
    knowledge_file: Path

    @property
    def connected(self) -> bool:
        return bool(self.refresh_token)

    def knowledge(self) -> str:
        try:
            return self.knowledge_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""


_ACCOUNT_SPECS = (
    # key, prefix, Anzeigename, Standard-Kontext, Zusatzregeln für Entwürfe
    (
        "privat",
        "PRIVAT",
        "Privat",
        "Privates Postfach. Wichtig sind Schule, Prüfungen, Fristen, Zahlungen, Verträge und Behörden.",
        "Antworte in der Sprache der eingehenden Mail.",
    ),
    (
        "headneck",
        "HEADNECK",
        "Headneckmasterclass",
        "Postfach von headneckmasterclass.com, einem Kursanbieter. Kursanfragen und Kursanmeldungen sind wichtig.",
        "Antworte auf Englisch, ausser die eingehende Mail ist eindeutig in einer anderen Sprache. "
        "Direkt und sachlich, ausschliesslich mit Informationen aus dem Wissensblock.",
    ),
)


def load_accounts(only_connected: bool = True) -> list[Account]:
    accounts = []
    for key, prefix, name, default_ctx, hint in _ACCOUNT_SPECS:
        acc = Account(
            key=key,
            prefix=prefix,
            name=name,
            refresh_token=_env(f"GMAIL_{prefix}_REFRESH_TOKEN"),
            context=_env(f"{prefix}_CONTEXT", default_ctx),
            sender_name=_env(f"{prefix}_SENDER_NAME"),
            reply_hint=hint,
            knowledge_file=KNOWLEDGE_DIR / f"{key}.txt",
        )
        if acc.connected or not only_connected:
            accounts.append(acc)
    return accounts


@dataclass(frozen=True)
class Settings:
    google_client_id: str
    google_client_secret: str
    telegram_token: str
    telegram_chat_id: str
    model_classify: str
    model_draft: str
    check_interval_minutes: int
    digest_hour: int
    lookback_days: int
    max_mails_per_run: int
    dry_run: bool

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)


def load_settings() -> Settings:
    return Settings(
        google_client_id=_env("GOOGLE_CLIENT_ID"),
        google_client_secret=_env("GOOGLE_CLIENT_SECRET"),
        telegram_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
        model_classify=_env("MODEL_CLASSIFY", "claude-haiku-5-5"),
        model_draft=_env("MODEL_DRAFT", "claude-sonnet-5-5"),
        check_interval_minutes=max(1, _env_int("CHECK_INTERVAL_MINUTES", 30)),
        digest_hour=min(23, max(0, _env_int("DIGEST_HOUR", 7))),
        lookback_days=max(1, _env_int("LOOKBACK_DAYS", 2)),
        max_mails_per_run=max(1, _env_int("MAX_MAILS_PER_RUN", 25)),
        dry_run=_env("DRY_RUN", "0").lower() in ("1", "true", "ja", "yes"),
    )
