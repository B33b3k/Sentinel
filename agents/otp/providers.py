"""OTP provider implementations: Mock, Twilio, Sparrow."""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from typing import Protocol

import redis


class OTPProvider(Protocol):
    def send(self, recipient: str, code: str) -> bool: ...


class MockProvider:
    """Writes OTP to Redis + prints to console. Default for demo."""

    def __init__(self, redis_url: str | None = None) -> None:
        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._r = redis.Redis.from_url(url, decode_responses=True)

    def send(self, recipient: str, code: str) -> bool:
        self._r.setex(f"mock_otp:{recipient}", 300, code)
        print(f"[MockOTP] → {recipient}: {code}")
        return True


class TwilioProvider:
    """Real SMS via Twilio REST API."""

    def __init__(self) -> None:
        from twilio.rest import Client  # type: ignore[import]
        self._client = Client(
            os.environ["TWILIO_ACCOUNT_SID"],
            os.environ["TWILIO_AUTH_TOKEN"],
        )
        self._from = os.environ["TWILIO_FROM_NUMBER"]

    def send(self, recipient: str, code: str) -> bool:
        try:
            self._client.messages.create(
                body=f"SENTINEL verification code: {code}",
                from_=self._from,
                to=recipient,
            )
            return True
        except Exception as e:
            print(f"[Twilio] send failed: {e}")
            return False


class SparrowProvider:
    """SMS via sparrowsms.com API (Nepal production target)."""

    _URL = "https://api.sparrowsms.com/v2/sms/"

    def __init__(self) -> None:
        import requests  # type: ignore[import]
        self._requests = requests
        self._token = os.environ["SPARROW_TOKEN"]
        self._identity = os.environ["SPARROW_IDENTITY"]

    def send(self, recipient: str, code: str) -> bool:
        try:
            resp = self._requests.post(self._URL, data={
                "token": self._token,
                "identity": self._identity,
                "to": recipient,
                "text": f"SENTINEL code: {code}",
            }, timeout=5)
            return resp.status_code == 200
        except Exception as e:
            print(f"[Sparrow] send failed: {e}")
            return False


class SMTPEmailProvider:
    """Email OTP via SMTP (Gmail relay)."""

    def __init__(self) -> None:
        self._host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self._port = int(os.environ.get("SMTP_PORT", "587"))
        self._user = os.environ["SMTP_USER"]
        self._password = os.environ["SMTP_PASSWORD"]
        self._from = os.environ.get("SMTP_FROM", self._user)

    def send(self, recipient: str, code: str) -> bool:
        try:
            msg = MIMEText(f"Your SENTINEL verification code is: {code}\n\nValid for 5 minutes.")
            msg["Subject"] = "SENTINEL Security Code"
            msg["From"] = self._from
            msg["To"] = recipient
            with smtplib.SMTP(self._host, self._port) as s:
                s.starttls()
                s.login(self._user, self._password)
                s.send_message(msg)
            return True
        except Exception as e:
            print(f"[SMTP] send failed: {e}")
            return False


def get_sms_provider(redis_url: str | None = None) -> OTPProvider:
    provider = os.environ.get("SMS_PROVIDER", "mock").lower()
    if provider == "twilio":
        return TwilioProvider()
    if provider == "sparrow":
        return SparrowProvider()
    return MockProvider(redis_url=redis_url)


def get_email_provider(redis_url: str | None = None) -> OTPProvider:
    provider = os.environ.get("OTP_PROVIDER", "mock").lower()
    if provider == "smtp":
        return SMTPEmailProvider()
    return MockProvider(redis_url=redis_url)
