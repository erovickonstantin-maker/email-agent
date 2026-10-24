"""Verarbeitet neue Mails eines Postfachs. Jedes Postfach läuft für sich allein."""
from __future__ import annotations

import logging
import re
from collections import Counter

import anthropic

from . import ai
from .config import (ANTWORT, ARCHIVE_CATEGORIES, PROCESSED_LABEL, Account, Settings, label_name)
from .gmail_client import GmailClient, Mail
from .telegram import Telegram, esc

log = logging.getLogger(__name__)

MAX_FAILURES = 3
_failures: dict[tuple[str, str], int] = {}

_NOREPLY = re.compile(r"(no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer-daemon|postmaster)", re.I)


def is_noreply(sender_email: str) -> bool:
    return bool(_NOREPLY.search(sender_email or ""))


def apply_rules(cls: ai.Classification, mail: Mail) -> ai.Classification:
    """Sicherheitsregeln, die für Claudes Antwort immer gelten."""
    data = cls.model_copy()
    if is_noreply(mail.sender_email):
        data.needs_reply = False
        if data.category == ANTWORT:
            data.category = "Info"
    if data.category == ANTWORT:
        data.needs_reply = True
    if data.category in ARCHIVE_CATEGORIES:
        data.alert = False
        data.needs_reply = False
    return data


def labels_for(cls: ai.Classification) -> tuple[list[str], bool]:
    """Gibt (Label Namen, aus Posteingang entfernen) zurück."""
    names = [label_name(cls.category)]
    if cls.needs_reply and cls.category != ANTWORT:
        names.append(label_name(ANTWORT))
    names.append(PROCESSED_LABEL)
    return names, cls.category in ARCHIVE_CATEGORIES


def gmail_link(email: str, thread_id: str) -> str:
    return f"https://mail.google.com/mail/u/{email}/#all/{thread_id}"


def format_alert(account: Account, email: str, mail: Mail, cls: ai.Classification, draft: bool) -> str:
    lines = [
        f"🔴 <b>Wichtige Mail · {esc(account.name)}</b>",
        f"<b>Von:</b> {esc(mail.sender)}",
        f"<b>Betreff:</b> {esc(mail.subject)}",
        f"<b>Worum:</b> {esc(cls.summary)}",
        f"<b>Grund:</b> {esc(cls.reason)}",
    ]
    if draft:
        lines.append("✍️ Antwortentwurf liegt in Gmail bereit.")
    lines.append(f'<a href="{gmail_link(email, mail.thread_id)}">In Gmail öffnen</a>')
    return "\n".join(lines)


def process_account(account: Account, gmail: GmailClient, claude: anthropic.Anthropic,
                    telegram: Telegram, settings: Settings) -> Counter:
    stats: Counter = Counter()
    gmail.ensure_labels()
    ids = gmail.list_new_message_ids(settings.lookback_days, settings.max_mails_per_run)
    ids = [i for i in ids if _failures.get((account.key, i), 0) < MAX_FAILURES]
    if not ids:
        log.info("[%s] Keine neuen Mails.", account.name)
        return stats

    draft_threads = gmail.draft_thread_ids()
    for message_id in ids:
        try:
            _process_one(account, gmail, claude, telegram, settings, message_id, draft_threads, stats)
        except Exception:
            key = (account.key, message_id)
            _failures[key] = _failures.get(key, 0) + 1
            stats["fehler"] += 1
            log.exception("[%s] Fehler bei Mail %s (Versuch %d von %d)",
                          account.name, message_id, _failures[key], MAX_FAILURES)
    log.info("[%s] Fertig: %s", account.name, dict(stats))
    return stats


def _process_one(account, gmail, claude, telegram, settings, message_id, draft_threads, stats) -> None:
    mail = gmail.get_mail(message_id)
    if gmail.label_id(PROCESSED_LABEL) in mail.label_ids:
        return

    # Mails von mir selbst nur als erledigt markieren
    if mail.sender_email == gmail.email:
        if not settings.dry_run:
            gmail.modify(mail.id, add=[gmail.label_id(PROCESSED_LABEL)])
        stats["eigene"] += 1
        return

    cls = apply_rules(ai.classify(claude, settings.model_classify, mail, account), mail)
    log.info("[%s] %s | %s → %s%s%s", account.name, mail.sender, mail.subject, cls.category,
             " +Antwort" if cls.needs_reply and cls.category != ANTWORT else "",
             " ALARM" if cls.alert else "")

    if settings.dry_run:
        stats[cls.category] += 1
        return

    draft_created = False
    if cls.needs_reply:
        if mail.thread_id in draft_threads:
            log.info("[%s] Für diesen Verlauf gibt es schon einen Entwurf, überspringe.", account.name)
        else:
            text = ai.draft_reply(claude, settings.model_draft, mail, account)
            gmail.create_reply_draft(mail, text)
            draft_threads.add(mail.thread_id)
            draft_created = True
            stats["entwuerfe"] += 1

    if cls.alert:
        if telegram.send(format_alert(account, gmail.email, mail, cls, draft_created)):
            stats["alarme"] += 1

    names, archive = labels_for(cls)
    gmail.modify(
        mail.id,
        add=[gmail.label_id(n) for n in names],
        remove=["INBOX"] if archive else [],
    )
    stats[cls.category] += 1
