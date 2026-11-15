"""Send conflict notifications through an existing outgoing SMTP account."""
from email.message import EmailMessage
import os
from pathlib import Path
import smtplib
import ssl

from .git import git


def send_conflict_email(root: Path, notification: dict) -> dict:
  """Send the approved conflict payload and retain a delivery disposition.

  Parameters
  ----------
  root : Path
      Repository supplying ordinary Git sendemail configuration.
  notification : dict
      Recipient, subject and actual conflict body.

  Returns
  -------
  dict
      Original notification with sent or failed status; credentials are omitted.
  """
  def setting(environment: str, key: str, default: str = "") -> str:
    """Resolve an SMTP setting from environment or Git sendemail configuration."""
    return os.environ.get(environment) or git(root, "config", "--get", key,
      check=False).stdout.strip() or default

  try:
    host = setting("SMTP_HOST", "sendemail.smtpServer")
    if not host:
      return {**notification, "status": "failed", "error": "outgoing SMTP host is not configured"}
    encryption = setting("SMTP_ENCRYPTION", "sendemail.smtpEncryption", "tls").lower()
    if encryption not in {"ssl", "tls", "starttls", "none"}:
      raise ValueError("unsupported SMTP encryption setting")
    port = int(setting("SMTP_PORT", "sendemail.smtpServerPort", "465" if encryption == "ssl" else "587"))
    username = setting("SMTP_USERNAME", "sendemail.smtpUser")
    password = setting("SMTP_PASSWORD", "sendemail.smtpPass")
    sender = setting("SMTP_FROM", "sendemail.from") or git(root, "config", "--get", "user.email", check=False).stdout.strip()
    recipient = setting("RWF_NOTIFICATION_EMAIL", "rwf.notificationEmail") or notification["to"]
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = notification["subject"]
    message.set_content(notification["body"])
    context = ssl.create_default_context()
    client = smtplib.SMTP_SSL(host, port, timeout=30, context=context) if encryption == "ssl" else smtplib.SMTP(host, port, timeout=30)
    with client:
      if encryption in {"tls", "starttls"}:
        client.starttls(context=context)
      if username:
        client.login(username, password)
      refused = client.send_message(message)
      if refused:
        return {**notification, "to": recipient, "status": "failed", "error": "SMTP recipient refused"}
    return {**notification, "to": recipient, "status": "sent"}
  except (OSError, ValueError, smtplib.SMTPException) as error:
    return {**notification, "status": "failed", "error": type(error).__name__}
