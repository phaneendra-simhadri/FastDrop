from __future__ import annotations

import threading
from typing import Callable


class TransferRejected(Exception):
    """Raised when the receiver user declines the transfer."""


class ReceiveSessionCoordinator:
    """Synchronizes incoming TCP sessions with receiver UI actions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._code_ready = threading.Event()
        self._decision_ready = threading.Event()
        self._code = ""
        self._accept = False
        self._rejected = False
        self.on_incoming_request: Callable[[dict], None] | None = None
        self.on_pairing_verified: Callable[[dict], None] | None = None

    def reset_wait_state(self) -> None:
        with self._lock:
            self._code = ""
            self._accept = False
            self._rejected = False
        self._code_ready.clear()
        self._decision_ready.clear()

    def wait_for_pairing_code(self, request: dict, timeout: float = 120) -> str:
        self.reset_wait_state()
        if self.on_incoming_request:
            self.on_incoming_request(request)
        if not self._code_ready.wait(timeout):
            raise TimeoutError("Pairing code entry timed out. Open Receive and enter the code shown on the sender.")
        with self._lock:
            if self._rejected:
                raise TransferRejected("Transfer rejected by receiver")
            return self._code

    def submit_pairing_code(self, code: str) -> None:
        with self._lock:
            self._code = code.strip()
            self._rejected = False
        self._code_ready.set()

    def reject_transfer(self) -> None:
        with self._lock:
            self._rejected = True
            self._accept = False
        self._code_ready.set()
        self._decision_ready.set()

    def wait_for_accept(self, request: dict, timeout: float = 120) -> bool:
        self._decision_ready.clear()
        if self.on_pairing_verified:
            self.on_pairing_verified(request)
        if not self._decision_ready.wait(timeout):
            raise TimeoutError("Transfer accept/reject timed out")
        with self._lock:
            if self._rejected or not self._accept:
                raise TransferRejected("Transfer rejected by receiver")
            return True

    def submit_decision(self, accept: bool) -> None:
        with self._lock:
            self._accept = accept
            if not accept:
                self._rejected = True
        self._decision_ready.set()
