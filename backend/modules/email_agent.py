# Path: backend/modules/email_agent.py
# Use: Drafts, sends, and lists user email messages.
"""
email_agent.py — MAX v4.0
Gmail Email Integration (Free tier, needs App Password)
Skills: email_send, email_check, email_reply
"""
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from datetime import datetime
from typing import List, Dict, Optional
from config import config


class EmailAgent:
    """Simple Gmail email agent using IMAP/SMTP + App Password."""

    def __init__(self):
        self.email_address = config.EMAIL_ADDRESS
        self.app_password = config.EMAIL_APP_PASSWORD
        self.imap_server = config.IMAP_SERVER
        self.smtp_server = config.SMTP_SERVER
        self.smtp_port = config.SMTP_PORT
        self._enabled = bool(self.email_address and self.app_password)

    def is_enabled(self) -> bool:
        return self._enabled

    def _get_imap(self) -> Optional[imaplib.IMAP4_SSL]:
        if not self._enabled:
            return None
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.app_password)
            return mail
        except Exception as e:
            return None

    def send_email(self, to: str, subject: str, body: str) -> str:
        """Send email via SMTP."""
        if not self._enabled:
            return "Email setup nahi hai boss. .env mein EMAIL_ADDRESS aur EMAIL_APP_PASSWORD daal."
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self.email_address
            msg["To"] = to

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_address, self.app_password)
                server.sendmail(self.email_address, [to], msg.as_string())

            return f"Email bhej diya boss — {to} ko."
        except Exception as e:
            return f"Email bhejne mein dikkat: {str(e)[:120]}"

    def check_emails(self, limit: int = 5) -> str:
        """Check latest unread emails via IMAP."""
        if not self._enabled:
            return "Email setup nahi hai boss. .env mein credentials daal."
        mail = self._get_imap()
        if not mail:
            return "Gmail connect nahi ho paya. Check internet ya credentials."
        try:
            mail.select("inbox")
            status, data = mail.search(None, "UNSEEN")
            if status != "OK" or not data[0]:
                return "Koi unread email nahi hai boss. Inbox clean hai!"

            ids = data[0].split()
            ids = ids[-limit:]  # Latest N
            results: List[str] = []

            for num in reversed(ids):
                status, msg_data = mail.fetch(num, "(RFC822)")
                if status != "OK":
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                subject = msg.get("Subject", "No Subject")
                sender = msg.get("From", "Unknown")
                date = msg.get("Date", "")
                results.append(f"📧 {subject[:60]} | From: {sender[:40]} | {date[:20]}")

            mail.close()
            mail.logout()

            if not results:
                return "Koi unread email nahi hai boss."
            return f"{len(results)} unread emails:\n" + "\n".join(results)

        except Exception as e:
            return f"Email check karne mein dikkat: {str(e)[:120]}"


# Singleton
_email_agent: Optional[EmailAgent] = None


def get_email_agent() -> EmailAgent:
    global _email_agent
    if _email_agent is None:
        _email_agent = EmailAgent()
    return _email_agent
