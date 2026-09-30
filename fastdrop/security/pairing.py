from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from hmac import compare_digest


@dataclass
class PairingRecord:
    code: str
    expires_at: float
    attempts_left: int = 3


class PairingCodeManager:
    """Maintains one-time pairing codes for sender-to-receiver authorization."""

    def __init__(self, ttl_seconds: int = 60, max_attempts: int = 3) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_attempts = max_attempts
        self._codes: dict[str, PairingRecord] = {}

    @staticmethod
    def generate_code() -> str:
        return str(secrets.randbelow(1_000_000)).zfill(6)

    def create(self, request_id: str, *, code: str | None = None) -> str:
        generated = code if code else self.generate_code()
        self._codes[request_id] = PairingRecord(
            code=generated,
            expires_at=time.time() + self.ttl_seconds,
            attempts_left=self.max_attempts,
        )
        return generated

    def validate(self, request_id: str, code: str) -> bool:
        record = self._codes.get(request_id)
        if record is None:
            return False
        if time.time() > record.expires_at:
            self._codes.pop(request_id, None)
            return False
        if record.attempts_left <= 0:
            self._codes.pop(request_id, None)
            return False
        if not compare_digest(code, record.code):
            record.attempts_left -= 1
            if record.attempts_left <= 0:
                self._codes.pop(request_id, None)
            return False
        self._codes.pop(request_id, None)
        return True

    def is_active(self, request_id: str) -> bool:
        record = self._codes.get(request_id)
        if not record:
            return False
        if time.time() > record.expires_at:
            self._codes.pop(request_id, None)
            return False
        return True

    def clear(self, request_id: str) -> None:
        self._codes.pop(request_id, None)
