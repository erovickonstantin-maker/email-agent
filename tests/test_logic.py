"""Tests ohne Internet: python -m unittest discover -s tests"""
import base64
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from mailagent import ai, digest, envfile, processor
from mailagent.config import Account
from mailagent.gmail_client import MailRef, Mail, extract_body, html_to_text
from mailagent.telegram import split_message

ROOT = Path(__file__).resolve().parent.parent


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()


def make_mail(**kw) -> Mail:
    base = dict(id="m1", thread_id="t1", sender="Max <max@example.com>", sender_email="max@example.com",
                reply_to="", subject="Frage", date="", body="Hallo", snippet="", message_id="<a@b>",
                references="", label_ids=[], is_bulk=False)
    base.update(kw)
    return Mail(**base)


def cls(**kw) -> ai.Classification:
    base = dict(category="Info", needs_reply=False, alert=False, summary="s", reason="r")
    base.update(kw)
    return ai.Classification(**base)


class BodyTests(unittest.TestCase):
    def test_prefers_plain(self):
        payload = {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("Klartext")}},
            {"mimeType": "text/html", "body": {"data": b64("<p>Html</p>")}}]}
        self.assertEqual(extract_body(payload), "Klartext")

    def test_html_fallback_strips_script(self):
        payload = {"mimeType": "text/html", "body": {"data": b64("<style>x{}</style><p>Hallo</p><script>evil()</script><p>Welt</p>")}}
        text = extract_body(payload)
        self.assertIn("Hallo", text)
        self.assertIn("Welt", text)
        self.assertNotIn("evil", text)
        self.assertNotIn("x{}", text)

    def test_html_to_text_entities(self):
        self.assertEqual(html_to_text("<p>Fr&uuml;hst&uuml;ck</p>"), "Frühstück")


class RuleTests(unittest.TestCase):
    def test_noreply_never_needs_reply(self):
        r = processor.apply_rules(cls(category="Antwort nötig", needs_reply=True),
                                  make_mail(sender_email="no-reply@shop.at"))
        self.assertEqual(r.category, "Info")
        self.assertFalse(r.needs_reply)

    def test_werbung_never_alerts_or_drafts(self):
        r = processor.apply_rules(cls(category="Werbung", needs_reply=True, alert=True), make_mail())
        self.assertFalse(r.alert)
        self.assertFalse(r.needs_reply)

    def test_antwort_implies_needs_reply(self):
        r = processor.apply_rules(cls(category="Antwort nötig", needs_reply=False), make_mail())
        self.assertTrue(r.needs_reply)

    def test_labels_and_archive(self):
        names, archive = processor.labels_for(cls(category="Newsletter"))
        self.assertTrue(archive)
        self.assertIn("Agent/Newsletter", names)
        self.assertIn("Agent-Verarbeitet", names)
        names, archive = processor.labels_for(cls(category="Wichtig", needs_reply=True))
        self.assertFalse(archive)
        self.assertIn("Agent/Wichtig", names)
        self.assertIn("Agent/Antwort nötig", names)

    def test_alert_text_escapes_html(self):
        acc = Account("privat", "PRIVAT", "Privat", "t", "", "", "", Path("x"))
        text = processor.format_alert(acc, "me@gmail.com", make_mail(subject="<b>Frist</b> & Zahlung"),
                                      cls(category="Wichtig", alert=True), True)
        self.assertIn("&lt;b&gt;Frist&lt;/b&gt; &amp; Zahlung", text)
        self.assertIn("Antwortentwurf", text)


class FakeGmail:
    email = "me@gmail.com"

    def ensure_labels(self): pass

    def list_refs(self, label, query, limit, in_inbox=False):
        if label == "Agent/Wichtig":
            return [MailRef("1", "t1", "Schule <s@schule.at>", "Elternabend", "")]
        return [MailRef("2", "t2", "Kunde <k@x.com>", "Kursfrage", ""),
                MailRef("3", "t3", "Mama <m@x.com>", "Bereits beantwortet", "")]

    def last_sender_in_thread(self, tid):
        return "me@gmail.com" if tid == "t3" else "k@x.com"

    def draft_thread_ids(self): return {"t2"}


class DigestTests(unittest.TestCase):
    def test_digest_sections(self):
        acc = Account("headneck", "HEADNECK", "Headneckmasterclass", "", "", "", "", Path("x"))
        text = digest.build_digest(acc, FakeGmail(), datetime(2026, 10, 26, 7, 0, tzinfo=ZoneInfo("Europe/Vienna")))
        self.assertIn("Headneckmasterclass", text)
        self.assertIn("Montag, 26.10.2026", text)
        self.assertIn("Elternabend", text)
        self.assertIn("Kursfrage", text)
        self.assertNotIn("Bereits beantwortet", text)  # schon geantwortet
        self.assertIn("Entwürfe liegen bereit", text)


class TelegramTests(unittest.TestCase):
    def test_split(self):
        text = "\n".join(f"zeile {i}" * 20 for i in range(100))
        chunks = split_message(text, 500)
        self.assertTrue(all(len(c) <= 500 for c in chunks))
        self.assertEqual("\n".join(chunks).replace("\n", ""), text.replace("\n", ""))


class EnvTests(unittest.TestCase):
    def test_set_value_keeps_other_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("# Kommentar\nA=1\nB=\n")
            envfile.set_env_value("B", "zwei", p)
            envfile.set_env_value("C", "drei", p)
            self.assertEqual(p.read_text(), "# Kommentar\nA=1\nB=zwei\nC=drei\n")


class FakeCycleGmail:
    """Spielt ein Postfach mit drei Mails nach, ohne Internet."""
    email = "me@gmail.com"

    def __init__(self):
        self.calls = []
        self.drafts = []
        self.mails = {
            "a": make_mail(id="a", thread_id="ta", subject="Frist Zahlung"),
            "b": make_mail(id="b", thread_id="tb", subject="Rabatt!", sender_email="shop@x.com"),
            "c": make_mail(id="c", thread_id="tc", subject="Ich selbst", sender_email="me@gmail.com"),
        }

    def ensure_labels(self): pass
    def label_id(self, name): return f"L:{name}"
    def list_new_message_ids(self, days, limit): return list(self.mails)
    def draft_thread_ids(self): return set()
    def get_mail(self, i): return self.mails[i]
    def modify(self, i, add=(), remove=()): self.calls.append((i, list(add), list(remove)))
    def create_reply_draft(self, mail, body): self.drafts.append((mail.id, body))


class FakeTelegram:
    def __init__(self): self.sent = []
    def send(self, text): self.sent.append(text); return True


def fake_settings(dry_run=False):
    from mailagent.config import Settings
    return Settings("", "", "", "", "haiku", "sonnet", 30, 7, 2, 25, dry_run)


class CycleTests(unittest.TestCase):
    def setUp(self):
        self._classify, self._draft = ai.classify, ai.draft_reply
        def fake_classify(client, model, mail, account):
            if mail.id == "a":
                return cls(category="Wichtig", needs_reply=True, alert=True)
            return cls(category="Werbung")
        ai.classify = fake_classify
        ai.draft_reply = lambda client, model, mail, account: "Entwurfstext"
        processor._failures.clear()

    def tearDown(self):
        ai.classify, ai.draft_reply = self._classify, self._draft

    def run_it(self, dry_run=False):
        gmail, tg = FakeCycleGmail(), FakeTelegram()
        acc = Account("privat", "PRIVAT", "Privat", "", "", "", "", Path("x"))
        stats = processor.process_account(acc, gmail, None, tg, fake_settings(dry_run))
        return gmail, tg, stats

    def test_full_cycle(self):
        gmail, tg, stats = self.run_it()
        by_id = {c[0]: c for c in gmail.calls}
        # Wichtige Mail: Labels Wichtig + Antwort nötig, bleibt im Posteingang, Entwurf, Telegram
        self.assertEqual(by_id["a"][2], [])
        self.assertIn("L:Agent/Antwort nötig", by_id["a"][1])
        self.assertEqual(gmail.drafts, [("a", "Entwurfstext")])
        self.assertEqual(len(tg.sent), 1)
        # Werbung: archiviert (INBOX entfernt), nicht gelöscht, kein Entwurf
        self.assertEqual(by_id["b"][2], ["INBOX"])
        self.assertIn("L:Agent-Verarbeitet", by_id["b"][1])
        # Eigene Mail: nur als verarbeitet markiert
        self.assertEqual(by_id["c"][1], ["L:Agent-Verarbeitet"])
        self.assertEqual(stats["entwuerfe"], 1)

    def test_dry_run_changes_nothing(self):
        gmail, tg, _ = self.run_it(dry_run=True)
        self.assertEqual(gmail.calls, [])
        self.assertEqual(gmail.drafts, [])
        self.assertEqual(tg.sent, [])

    def test_error_in_one_mail_does_not_stop_others(self):
        def boom(client, model, mail, account):
            if mail.id == "a":
                raise RuntimeError("kaputt")
            return cls(category="Info")
        ai.classify = boom
        gmail, _, stats = self.run_it()
        self.assertEqual(stats["fehler"], 1)
        self.assertNotIn("a", [c[0] for c in gmail.calls])  # a bleibt unverarbeitet
        self.assertIn("b", [c[0] for c in gmail.calls])


class ClaudeCallShapeTests(unittest.TestCase):
    """Prüft mit einem lokalen Fake Server, dass die Claude Aufrufe korrekt gebaut sind."""

    def test_classify_and_draft(self):
        import json, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import anthropic
        seen = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append(body)
                text = json.dumps({"category": "Wichtig", "needs_reply": True, "alert": True,
                                   "summary": "Frist", "reason": "Zahlung"}) \
                    if "output_config" in body and "format" in body["output_config"] else "Hallo Max"
                out = json.dumps({"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
                                  "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                                  "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            client = anthropic.Anthropic(api_key="test", base_url=f"http://127.0.0.1:{srv.server_port}")
            acc = Account("privat", "PRIVAT", "Privat", "tok", "ctx", "Konstantin", "regel", Path("nix.txt"))
            result = ai.classify(client, "claude-haiku-5-5", make_mail(), acc)
            self.assertEqual(result.category, "Wichtig")
            self.assertTrue(result.alert)
            self.assertEqual(ai.draft_reply(client, "claude-sonnet-5-5", make_mail(), acc), "Hallo Max")
        finally:
            srv.shutdown()
        self.assertEqual(seen[0]["output_config"]["effort"], "low")
        self.assertEqual(seen[0]["model"], "claude-haiku-5-5")
        self.assertEqual(seen[1]["model"], "claude-sonnet-5-5")
        self.assertIn("Unterschreibe mit: Konstantin", seen[1]["messages"][0]["content"])


class SafetyTests(unittest.TestCase):
    def test_code_never_sends_or_deletes_mail(self):
        forbidden = ["messages().send", "drafts().send", ".trash(", "messages().delete",
                     "drafts().delete", "threads().delete", "batchDelete"]
        for path in list((ROOT / "mailagent").glob("*.py")) + [ROOT / "main.py", ROOT / "einrichten.py"]:
            src = path.read_text(encoding="utf-8")
            for word in forbidden:
                self.assertNotIn(word, src, f"{word} gefunden in {path.name}")


if __name__ == "__main__":
    unittest.main()
