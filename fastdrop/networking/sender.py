from __future__ import annotations

import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from fastdrop.models.transfer import DeviceInfo, TransferProgress
from fastdrop.networking.protocol import CHUNK_SIZE, recv_json_message, send_json_message
from fastdrop.security.hashing import sha256_file
from fastdrop.security.pairing import PairingCodeManager
from fastdrop.security.validation import validate_file_size, validate_tcp_port


class FileSender:
    """Performs the sender side of the TCP file transfer handshake."""

    def __init__(self, device_id: str, device_name: str, pairing_manager: PairingCodeManager | None = None) -> None:
        self.device_id = device_id
        self.device_name = device_name
        self.pairing_manager = pairing_manager or PairingCodeManager()
        self._cancel_event = threading.Event()
        self._socket_lock = threading.Lock()
        self._active_socket: socket.socket | None = None

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel_transfer(self) -> None:
        self._cancel_event.set()
        with self._socket_lock:
            active_socket = self._active_socket
        if active_socket is not None:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    @contextmanager
    def _track_socket(self, sock: socket.socket) -> Iterator[socket.socket]:
        with self._socket_lock:
            self._active_socket = sock
        try:
            with sock:
                yield sock
        finally:
            with self._socket_lock:
                if self._active_socket is sock:
                    self._active_socket = None

    def start_transfer(
        self,
        device: DeviceInfo,
        file_path: str | Path,
        on_progress=None,
        on_status=None,
        *,
        request_id: str | None = None,
        pairing_code: str | None = None,
    ) -> dict:
        self._cancel_event.clear()
        file_obj = Path(file_path)
        if not file_obj.exists():
            raise FileNotFoundError(file_path)
        if not file_obj.is_file():
            raise ValueError("The selected path does not point to a regular file")

        request_id = request_id or f"req-{int(time.time() * 1000)}"
        if pairing_code is None:
            pairing_code = self.pairing_manager.create(request_id)
        else:
            pairing_code = self.pairing_manager.create(request_id, code=pairing_code)

        file_hash = sha256_file(file_obj)
        if self.cancelled:
            raise RuntimeError("Transfer cancelled")
        total_size = file_obj.stat().st_size
        validate_file_size(total_size)
        validate_tcp_port(device.port)

        progress = TransferProgress(total_bytes=total_size, status="connecting")
        payload = {
            "type": "TRANSFER_REQUEST",
            "request_id": request_id,
            "sender_device_id": self.device_id,
            "sender_device_name": self.device_name,
            "file_name": file_obj.name,
            "file_size": total_size,
            "sha256": file_hash,
        }

        if on_status:
            on_status(f"Connecting to {device.device_name} ({device.ip})")
            on_status(f"Share this pairing code with the receiver: {pairing_code}")

        with self._track_socket(socket.create_connection((device.ip, device.port), timeout=10)) as sock:
            if self.cancelled:
                raise RuntimeError("Transfer cancelled")
            send_json_message(sock, payload)
            challenge = recv_json_message(sock)
            if challenge.get("type") != "PAIRING_CHALLENGE":
                raise ValueError("Receiver did not issue a pairing challenge")
            if on_status:
                on_status("Waiting for receiver to enter the pairing code")

            response = recv_json_message(sock, timeout=120)
            if response.get("type") == "TRANSFER_REJECT":
                raise RuntimeError("Receiver rejected the transfer")
            if response.get("type") != "PAIRING_RESPONSE":
                raise ValueError("Receiver did not respond with a pairing code")

            entered_code = str(response.get("code", ""))
            if not self.pairing_manager.validate(request_id, entered_code):
                send_json_message(sock, {"type": "ERROR", "error": "Invalid or expired pairing code"})
                raise ValueError("Invalid or expired pairing code")

            send_json_message(sock, {"type": "PAIRING_VERIFIED", "request_id": request_id})
            if on_status:
                on_status("Pairing verified — waiting for receiver to accept the file")

            accept_message = recv_json_message(sock, timeout=120)
            if accept_message.get("type") == "TRANSFER_REJECT":
                raise RuntimeError("Receiver rejected the transfer")
            if accept_message.get("type") != "TRANSFER_ACCEPT":
                raise ValueError("Invalid transfer approval message")

            send_json_message(
                sock,
                {
                    "type": "FILE_INFO",
                    "request_id": request_id,
                    "file_name": file_obj.name,
                    "file_size": total_size,
                    "sha256": file_hash,
                },
            )
            start_time = time.time()
            sent_bytes = 0
            with file_obj.open("rb") as handle:
                while True:
                    if self.cancelled:
                        raise RuntimeError("Transfer cancelled")
                    chunk = handle.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    send_json_message(
                        sock,
                        {"type": "FILE_DATA", "request_id": request_id, "chunk_size": len(chunk), "offset": sent_bytes},
                    )
                    sock.sendall(chunk)
                    sent_bytes += len(chunk)
                    elapsed = max(time.time() - start_time, 0.001)
                    transfer_rate = sent_bytes / elapsed
                    remaining = max(total_size - sent_bytes, 0)
                    eta = (remaining / transfer_rate) if transfer_rate > 0 else 0.0
                    progress.transferred_bytes = sent_bytes
                    progress.speed_bps = transfer_rate
                    progress.eta_seconds = eta
                    progress.status = "sending"
                    if on_progress:
                        on_progress(progress)

            done = recv_json_message(sock, timeout=60)
            if done.get("type") == "TRANSFER_COMPLETE":
                receiver_hash = done.get("sha256")
                verified = receiver_hash == file_hash
                progress.status = "complete" if verified else "failed"
                progress.file_hash = file_hash
                progress.verified = verified
                if on_status:
                    on_status("Transfer complete" if verified else "Integrity verification failed")
                return {"success": verified, "sha256": file_hash, "receiver_sha256": receiver_hash}
            raise RuntimeError("Transfer did not complete correctly")
