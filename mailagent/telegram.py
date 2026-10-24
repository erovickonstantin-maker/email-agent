"""Telegram Nachrichten senden."""
from __future__ import annotations

import html
import logging

import requests

log = logging.getLogger(__name__)

MAX_LEN = 3800  # Telegram erlaubt 4096 Zeichen


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def split_message(text: str, limit: int = MAX_LEN) -> list[str]:
    """Teilt lange Texte an Zeilenumbrüchen."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks or [""]


class Telegram:
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id

    @property
    def ready(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, html_text: str) -> bool:
        """Sendet HTML formatierten Text. Gibt False zurück, wenn es nicht klappt."""
        if not self.ready:
            log.warning("Telegram ist nicht eingerichtet. Nachricht nicht gesendet:\n%s", html_text)
            return False
        ok = True
        for chunk in split_message(html_text):
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": chunk,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=20,
                )
                if not r.ok:
                    log.error("Telegram Fehler %s: %s", r.status_code, r.text[:300])
                    ok = False
            except requests.RequestException as e:
                log.error("Telegram nicht erreichbar: %s", e)
                ok = False
        return ok
