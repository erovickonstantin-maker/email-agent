"""Gmail Zugriff. Dieses Modul sendet NIE Mails und löscht NIE Mails.

Es gibt nur: lesen, Labels setzen, aus dem Posteingang verschieben (archivieren)
und Entwürfe speichern.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr
from html.parser import HTMLParser

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import PROCESSED_LABEL, Account, all_label_names

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass
class Mail:
    id: str
    thread_id: str
    sender: str
    sender_email: str
    reply_to: str
    subject: str
    date: str
    body: str
    snippet: str
    message_id: str
    references: str
    label_ids: list[str] = field(default_factory=list)
    is_bulk: bool = False


@dataclass
class MailRef:
    """Kurzinfo für die Tageszusammenfassung."""
    id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str


# ---------------------------------------------------------------- Textaufbereitung

class _HtmlToText(HTMLParser):
    _SKIP = {"script", "style", "head", "title"}
    _BREAK = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _HtmlToText()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    return clean_text("".join(parser.parts))


def clean_text(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def decode_header_value(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).replace("\r", " ").replace("\n", " ").strip()
    except Exception:
        return value.replace("\r", " ").replace("\n", " ").strip()


def _decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    charset = "utf-8"
    for h in part.get("headers", []) or []:
        if h.get("name", "").lower() == "content-type":
            m = re.search(r'charset="?([\w\-]+)"?', h.get("value", ""), re.I)
            if m:
                charset = m.group(1)
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def extract_body(payload: dict) -> str:
    """Nimmt bevorzugt text/plain, sonst HTML als Text."""
    plain: list[str] = []
    html: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            plain.append(_decode_part(part))
        elif mime == "text/html":
            html.append(_decode_part(part))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if any(p.strip() for p in plain):
        return clean_text("\n".join(plain))
    return html_to_text("\n".join(html))


def _headers(payload: dict) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


# ---------------------------------------------------------------- Client

class GmailClient:
    def __init__(self, account: Account, client_id: str, client_secret: str) -> None:
        self.account = account
        creds = Credentials(
            token=None,
            refresh_token=account.refresh_token,
            token_uri=TOKEN_URI,
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        self.service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self._labels: dict[str, str] = {}
        self._email: str | None = None

    # -- Grundlagen
    @staticmethod
    def _run(request):
        return request.execute(num_retries=3)

    @property
    def email(self) -> str:
        if self._email is None:
            profile = self._run(self.service.users().getProfile(userId="me"))
            self._email = profile["emailAddress"].lower()
        return self._email

    # -- Labels
    def ensure_labels(self) -> dict[str, str]:
        existing = self._list_labels()
        for name in all_label_names():
            if name not in existing:
                try:
                    created = self._run(self.service.users().labels().create(
                        userId="me",
                        body={
                            "name": name,
                            "labelListVisibility": "labelShow",
                            "messageListVisibility": "show",
                        },
                    ))
                    existing[name] = created["id"]
                except HttpError as e:
                    if e.resp.status == 409:  # gibt es schon
                        existing = self._list_labels()
                    else:
                        raise
        self._labels = existing
        return existing

    def _list_labels(self) -> dict[str, str]:
        resp = self._run(self.service.users().labels().list(userId="me"))
        return {l["name"]: l["id"] for l in resp.get("labels", [])}

    def label_id(self, name: str) -> str:
        if not self._labels:
            self.ensure_labels()
        return self._labels[name]

    # -- Mails lesen
    def list_new_message_ids(self, lookback_days: int, limit: int) -> list[str]:
        query = f"in:inbox newer_than:{lookback_days}d -label:{PROCESSED_LABEL}"
        resp = self._run(self.service.users().messages().list(
            userId="me", q=query, maxResults=limit))
        ids = [m["id"] for m in resp.get("messages", [])]
        ids.reverse()  # älteste zuerst
        return ids

    def get_mail(self, message_id: str) -> Mail:
        msg = self._run(self.service.users().messages().get(
            userId="me", id=message_id, format="full"))
        payload = msg.get("payload", {})
        h = _headers(payload)
        sender = decode_header_value(h.get("from", ""))
        bulk = (
            "list-unsubscribe" in h
            or "list-id" in h
            or h.get("precedence", "").lower() in ("bulk", "list", "junk")
            or h.get("auto-submitted", "").lower() not in ("", "no")
        )
        return Mail(
            id=msg["id"],
            thread_id=msg["threadId"],
            sender=sender,
            sender_email=parseaddr(sender)[1].lower(),
            reply_to=h.get("reply-to", ""),
            subject=decode_header_value(h.get("subject", "")) or "(kein Betreff)",
            date=h.get("date", ""),
            body=extract_body(payload),
            snippet=msg.get("snippet", ""),
            message_id=h.get("message-id", ""),
            references=h.get("references", ""),
            label_ids=msg.get("labelIds", []),
            is_bulk=bulk,
        )

    # -- Labels setzen, archivieren
    def modify(self, message_id: str, add: list[str] = (), remove: list[str] = ()) -> None:
        self._run(self.service.users().messages().modify(
            userId="me", id=message_id,
            body={"addLabelIds": list(add), "removeLabelIds": list(remove)}))

    # -- Entwürfe
    def draft_thread_ids(self) -> set[str]:
        ids: set[str] = set()
        token = None
        for _ in range(5):
            resp = self._run(self.service.users().drafts().list(
                userId="me", maxResults=100, pageToken=token))
            for d in resp.get("drafts", []):
                tid = d.get("message", {}).get("threadId")
                if tid:
                    ids.add(tid)
            token = resp.get("nextPageToken")
            if not token:
                break
        return ids

    def create_reply_draft(self, mail: Mail, body: str) -> str:
        """Speichert einen Entwurf in Gmail. Er wird NICHT gesendet."""
        msg = EmailMessage()
        msg["To"] = mail.reply_to or mail.sender
        subject = mail.subject
        msg["Subject"] = subject if subject.lower().startswith(("re:", "aw:")) else f"Re: {subject}"
        if mail.message_id:
            msg["In-Reply-To"] = mail.message_id
            msg["References"] = f"{mail.references} {mail.message_id}".strip()
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = self._run(self.service.users().drafts().create(
            userId="me", body={"message": {"raw": raw, "threadId": mail.thread_id}}))
        return draft["id"]

    # -- Für die Tageszusammenfassung
    def list_refs(self, label_name: str, query: str, limit: int, in_inbox: bool = False) -> list[MailRef]:
        label_ids = [self.label_id(label_name)] + (["INBOX"] if in_inbox else [])
        resp = self._run(self.service.users().messages().list(
            userId="me", labelIds=label_ids, q=query, maxResults=limit))
        refs = []
        for m in resp.get("messages", []):
            full = self._run(self.service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject"]))
            h = _headers(full.get("payload", {}))
            refs.append(MailRef(
                id=full["id"],
                thread_id=full["threadId"],
                sender=decode_header_value(h.get("from", "")),
                subject=decode_header_value(h.get("subject", "")) or "(kein Betreff)",
                snippet=full.get("snippet", ""),
            ))
        return refs

    def last_sender_in_thread(self, thread_id: str) -> str:
        thread = self._run(self.service.users().threads().get(
            userId="me", id=thread_id, format="metadata", metadataHeaders=["From"]))
        messages = thread.get("messages", [])
        if not messages:
            return ""
        h = _headers(messages[-1].get("payload", {}))
        return parseaddr(decode_header_value(h.get("from", "")))[1].lower()
