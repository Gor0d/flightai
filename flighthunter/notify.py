"""Notificadores: console, Telegram e e-mail (SMTP)."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import Config
from .http import HttpClient, ProviderError


class Notifier:
    def send(self, subject: str, body: str) -> None: ...


class ConsoleNotifier(Notifier):
    def send(self, subject, body):
        print(f"\n🔔 {subject}\n{body}\n")


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str, http: HttpClient | None = None):
        self.token, self.chat_id, self.http = token, chat_id, http or HttpClient()

    def send(self, subject, body):
        self.http.request("POST", f"https://api.telegram.org/bot{self.token}/sendMessage",
                          json_body={"chat_id": self.chat_id, "text": f"{subject}\n\n{body}"[:4000]})


class EmailNotifier(Notifier):
    def __init__(self, host: str, port: int, user: str, password: str, to: str):
        self.host, self.port, self.user, self.password, self.to = host, port, user, password, to

    def send(self, subject, body):
        m = EmailMessage()
        m["Subject"], m["From"], m["To"] = subject, self.user, self.to
        m.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=30) as s:
            s.starttls()
            s.login(self.user, self.password)
            s.send_message(m)


def build_notifiers(cfg: Config, http: HttpClient | None = None) -> list[Notifier]:
    out: list[Notifier] = []
    for n in cfg.notifiers:
        if n == "console":
            out.append(ConsoleNotifier())
        elif n == "telegram":
            t, c = cfg.secret("TELEGRAM_BOT_TOKEN"), cfg.secret("TELEGRAM_CHAT_ID")
            if t and c:
                out.append(TelegramNotifier(t, c, http))
        elif n == "email":
            h, u, p, to = (cfg.secret(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"))
            if h and u and p and to:
                out.append(EmailNotifier(h, int(cfg.secret("SMTP_PORT") or 587), u, p, to))
    return out


def safe_send(notifiers: list[Notifier], subject: str, body: str) -> list[str]:
    errors = []
    for n in notifiers:
        try:
            n.send(subject, body)
        except (ProviderError, OSError, smtplib.SMTPException) as e:
            errors.append(f"{type(n).__name__}: {e}")
    return errors
