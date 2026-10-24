"""Tägliche Zusammenfassung pro Postfach."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .config import ANTWORT, TIMEZONE, WICHTIG, Account, label_name
from .gmail_client import GmailClient, MailRef
from .processor import gmail_link
from .telegram import esc

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MAX_ITEMS = 15


def _line(ref: MailRef, extra: str = "") -> str:
    sender = ref.sender.split("<")[0].strip().strip('"') or ref.sender
    return f"• {esc(sender)}: {esc(ref.subject)}{extra}"


def build_digest(account: Account, gmail: GmailClient, now: datetime | None = None) -> str:
    now = now or datetime.now(ZoneInfo(TIMEZONE))
    gmail.ensure_labels()
    me = gmail.email

    wichtig = gmail.list_refs(label_name(WICHTIG), "newer_than:1d", MAX_ITEMS)

    candidates = gmail.list_refs(label_name(ANTWORT), "newer_than:14d", 40, in_inbox=True)
    offen = [r for r in candidates if gmail.last_sender_in_thread(r.thread_id) != me]

    draft_threads = gmail.draft_thread_ids()
    mit_entwurf = [r for r in offen if r.thread_id in draft_threads]

    head = (f"☀️ <b>Guten Morgen · {esc(account.name)}</b>\n"
            f"{WEEKDAYS[now.weekday()]}, {now:%d.%m.%Y}")
    parts = [head]

    parts.append("\n🔴 <b>Wichtiges (letzte 24 Stunden)</b>")
    parts += [_line(r) for r in wichtig] or ["Nichts Neues."]

    parts.append("\n📌 <b>Offen, Antwort nötig</b>")
    parts += [_line(r, " ✍️" if r.thread_id in draft_threads else "") for r in offen[:MAX_ITEMS]] \
        or ["Nichts offen."]

    parts.append("\n✍️ <b>Entwürfe liegen bereit</b>")
    parts += [f'{_line(r)} (<a href="{gmail_link(me, r.thread_id)}">öffnen</a>)'
              for r in mit_entwurf[:MAX_ITEMS]] or ["Keine Entwürfe."]

    return "\n".join(parts)
