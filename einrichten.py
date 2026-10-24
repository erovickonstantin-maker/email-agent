"""Geführte Einrichtung. Fragt nur nach dem, was noch fehlt. Kann beliebig oft ausgeführt werden.

  python einrichten.py            richtet alles ein, was noch fehlt
  python einrichten.py privat     verbindet das private Gmail Konto neu
  python einrichten.py headneck   verbindet das headneckmasterclass Konto neu
  python einrichten.py telegram   richtet Telegram neu ein
"""
from __future__ import annotations

import os
import sys
import time

import requests

from mailagent.config import load_accounts
from mailagent.envfile import ask_and_save, ensure_env_file, set_env_value
from mailagent.gmail_client import SCOPES, TOKEN_URI


def connect_google(key: str) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    account = next(a for a in load_accounts(only_connected=False) if a.key == key)
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    flow = InstalledAppFlow.from_client_config(
        {"installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }},
        scopes=SCOPES,
    )
    print(f"\n🔴 Gleich öffnet sich ein Browserfenster. Melde dich dort mit dem Konto '{account.name}' an.")
    print("🔴 Falls 'Google hat diese App nicht überprüft' erscheint: auf 'Erweitert' klicken, "
          "dann 'Weiter zu ... (unsicher)', dann alles erlauben.")
    creds = flow.run_local_server(
        port=0, access_type="offline", prompt="consent",
        authorization_prompt_message="Falls sich nichts öffnet, kopiere diesen Link in den Browser:\n{url}\n",
        success_message="Fertig! Du kannst dieses Fenster schliessen und zum Terminal zurückgehen.",
    )
    if not creds.refresh_token:
        sys.exit("❌ Google hat keinen dauerhaften Schlüssel geliefert. Bitte nochmal ausführen.")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    address = service.users().getProfile(userId="me").execute()["emailAddress"]
    set_env_value(f"GMAIL_{account.prefix}_REFRESH_TOKEN", creds.refresh_token)
    print(f"✅ Verbunden: {address} wird als '{account.name}' behandelt.")


def setup_telegram() -> None:
    token = ask_and_save("TELEGRAM_BOT_TOKEN",
                         "🔴 Füge den Bot Token von Telegram (@BotFather) ein und drücke Enter:")
    if not token:
        sys.exit("❌ Kein Token eingegeben.")
    base = f"https://api.telegram.org/bot{token}"
    me = requests.get(f"{base}/getMe", timeout=20).json()
    if not me.get("ok"):
        sys.exit("❌ Der Token ist ungültig. Prüfe ihn bei @BotFather.")
    username = me["result"]["username"]
    print(f"\n🔴 Öffne in Telegram deinen Bot @{username} und schicke ihm eine Nachricht (zum Beispiel 'Hallo').")
    print("Ich warte bis zu 2 Minuten ...")
    deadline = time.time() + 120
    chat_id = None
    while time.time() < deadline and not chat_id:
        updates = requests.get(f"{base}/getUpdates", timeout=20).json().get("result", [])
        for u in reversed(updates):
            msg = u.get("message") or {}
            if msg.get("chat", {}).get("id"):
                chat_id = str(msg["chat"]["id"])
                break
        if not chat_id:
            time.sleep(3)
    if not chat_id:
        sys.exit("❌ Keine Nachricht erhalten. Bitte nochmal 'python einrichten.py telegram' ausführen.")
    set_env_value("TELEGRAM_CHAT_ID", chat_id)
    requests.post(f"{base}/sendMessage",
                  json={"chat_id": chat_id, "text": "✅ Der Postfach Agent ist mit Telegram verbunden."},
                  timeout=20)
    print("✅ Telegram verbunden. Du solltest gerade eine Nachricht bekommen haben.")


def main() -> None:
    ensure_env_file()
    from dotenv import load_dotenv
    from mailagent.config import ENV_PATH
    load_dotenv(ENV_PATH, override=True)

    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    keys = {a.key for a in load_accounts(only_connected=False)}
    if arg and arg not in keys | {"telegram"}:
        print(__doc__)
        sys.exit(2)

    print("== Postfach Agent: Einrichtung ==\n")
    ask_and_save("ANTHROPIC_API_KEY",
                 "🔴 Füge deinen Claude API Key ein (console.anthropic.com, API Keys) und drücke Enter:")
    ask_and_save("GOOGLE_CLIENT_ID", "🔴 Füge die Google Client ID ein und drücke Enter:")
    ask_and_save("GOOGLE_CLIENT_SECRET", "🔴 Füge das Google Client Secret ein und drücke Enter:")
    if not (os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")):
        sys.exit("❌ Google Zugangsdaten fehlen. Siehe README, Schritt 3.")

    for account in load_accounts(only_connected=False):
        if arg == account.key or (not arg and not account.connected):
            connect_google(account.key)

    if arg == "telegram" or (not arg and not (os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))):
        setup_telegram()

    print("\n✅ Einrichtung abgeschlossen. Als Nächstes: python main.py check")


if __name__ == "__main__":
    main()
