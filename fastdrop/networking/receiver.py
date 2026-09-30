from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path

from fastdrop.models.transfer import TransferProgress
from fastdrop.networking.protocol import recv_exact, recv_json_message, send_json_message
from fastdrop.networking.receive_session import ReceiveSessionCoordinator, TransferRejected
from fastdrop.security.hashing import sha256_file
from fastdrop.security.validation import validate_chunk_size, validate_request_id, validate_transfer_metadata
from fastdrop.utils.file_utils import build_receive_path


class TransferReceiver:
    """Handles a single incoming transfer session on the TCP socket."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        receive_directory: str | Path,
        session: ReceiveSessionCoordinator | None = None,
    ) -> None:
        self.device_id = device_id
        self.device_name = device_name
        self.receive_directory = Path(receive_directory)
        self.session = session

    def handle_connection(
        self,
        conn: socket.socket,
        on_progress=None,
        on_status=None,
        *,
        get_pairing_code: Callable[[dict], str] | None = None,
        confirm_transfer: Callable[[dict], bool] | None = None,
    ) -> dict:
        request = recv_json_message(conn, timeout=10)
        if request.get("type") != "TRANSFER_REQUEST":
            raise ValueError("Invalid protocol message")
        request_id = str(request.get("request_id", ""))
        validate_request_id(request_id)

        file_name = str(request.get("file_name", "received_file.bin"))
        file_size = int(request.get("file_size", 0))
        file_hash = str(request.get("sha256", ""))
        validate_transfer_metadata(file_name=file_name, file_size=file_size, file_hash=file_hash)

        if on_status:
            on_status(f"Incoming file: {file_name} ({file_size} bytes)")

        send_json_message(conn, {"type": "PAIRING_CHALLENGE", "request_id": request_id, "message": "Enter the transfer code"})

        try:
            if get_pairing_code is not None:
                entered_code = get_pairing_code(request)
            elif self.session is not None:
                entered_code = self.session.wait_for_pairing_code(request)
            else:
                raise RuntimeError("No receiver UI is active. Open Receive File on this device first.")

            if not entered_code.isdigit() or len(entered_code) != 6:
                send_json_message(conn, {"type": "ERROR", "error": "Invalid pairing code format"})
                raise ValueError("Incorrect pairing code")

            send_json_message(conn, {"type": "PAIRING_RESPONSE", "request_id": request_id, "code": entered_code})

            verified = recv_json_message(conn, timeout=30)
            if verified.get("type") == "ERROR":
                raise ValueError(verified.get("error", "Pairing failed"))
            if verified.get("type") != "PAIRING_VERIFIED":
                raise ValueError("Sender did not verify the pairing code")

            if on_status:
                on_status("Code verified. Confirm accept or reject.")

            if confirm_transfer is not None:
                if not confirm_transfer(request):
                    send_json_message(conn, {"type": "TRANSFER_REJECT", "request_id": request_id})
                    raise TransferRejected("Transfer rejected by receiver")
            elif self.session is not None:
                self.session.wait_for_accept(request)
            else:
                raise RuntimeError("No receiver UI is active. Open Receive File on this device first.")

            send_json_message(conn, {"type": "TRANSFER_ACCEPT", "request_id": request_id})

            info_message = recv_json_message(conn, timeout=30)
            if info_message.get("type") != "FILE_INFO":
                raise ValueError("Invalid file metadata message")
            if str(info_message.get("request_id", "")) != request_id:
                raise ValueError("Mismatched transfer request ID")
            if int(info_message.get("file_size", -1)) != file_size:
                raise ValueError("Mismatched file size")
            if str(info_message.get("sha256", "")) != file_hash:
                raise ValueError("Mismatched file hash")
            if str(info_message.get("file_name", "")) != file_name:
                raise ValueError("Mismatched file name")

            actual_path = build_receive_path(self.receive_directory, file_name)
            total_received = 0
            start_time = time.time()
            try:
                with actual_path.open("wb") as handle:
                    while total_received < file_size:
                        chunk_header = recv_json_message(conn, timeout=60)
                        if chunk_header.get("type") != "FILE_DATA":
                            if chunk_header.get("type") == "ERROR":
                                raise RuntimeError(chunk_header.get("error", "Transfer failed"))
                            raise ValueError("Invalid file chunk protocol")
                        if str(chunk_header.get("request_id", "")) != request_id:
                            raise ValueError("Mismatched chunk request ID")
                        chunk_size = int(chunk_header.get("chunk_size", 0))
                        validate_chunk_size(chunk_size)
                        if total_received + chunk_size > file_size:
                            raise ValueError("Chunk exceeds declared file size")
                        chunk = recv_exact(conn, chunk_size)
                        if len(chunk) != chunk_size:
                            raise RuntimeError("Connection ended before a file chunk finished")
                        handle.write(chunk)
                        total_received += len(chunk)
                        elapsed = max(time.time() - start_time, 0.001)
                        rate = total_received / elapsed
                        eta = max(file_size - total_received, 0) / rate if rate > 0 else 0.0
                        progress = TransferProgress(
                            total_bytes=file_size,
                            transferred_bytes=total_received,
                            speed_bps=rate,
                            eta_seconds=eta,
                            status="receiving",
                        )
                        if on_progress:
                            on_progress(progress)

                if total_received != file_size:
                    raise RuntimeError("Incomplete file transfer")

                receiver_hash = sha256_file(actual_path)
                send_json_message(conn, {"type": "TRANSFER_COMPLETE", "request_id": request_id, "sha256": receiver_hash})
                if file_hash and receiver_hash != file_hash:
                    if on_status:
                        on_status("Integrity verification failed")
                    return {"success": False, "path": str(actual_path), "sha256": receiver_hash, "expected_sha256": file_hash}
                if on_status:
                    on_status("Transfer successful. File integrity verified")
                return {"success": True, "path": str(actual_path), "sha256": receiver_hash, "expected_sha256": file_hash}
            except Exception:
                if actual_path.exists():
                    try:
                        actual_path.unlink()
                    except OSError:
                        pass
                raise
        except TransferRejected:
            try:
                send_json_message(conn, {"type": "TRANSFER_REJECT", "request_id": request_id})
            except OSError:
                pass
            raise


class ReceiverListener:
    """Listens for incoming TCP connections and dispatches them to TransferReceiver."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        receive_directory: str | Path,
        tcp_port: int,
        session: ReceiveSessionCoordinator | None = None,
        callback=None,
    ) -> None:
        self.device_id = device_id
        self.device_name = device_name
        self.receive_directory = Path(receive_directory)
        self.tcp_port = tcp_port
        self.session = session
        self.callback = callback
        self._running = False
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._connections: set[socket.socket] = set()
        self._cancelled_connections: set[socket.socket] = set()
        self._connections_lock = threading.Lock()

    def start(self) -> None:
        self._running = True
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("0.0.0.0", self.tcp_port))
        self._socket.listen(5)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
        self.cancel_current_transfer()

    def cancel_current_transfer(self) -> None:
        with self._connections_lock:
            connections = list(self._connections)
            self._cancelled_connections.update(connections)
        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

    def _run(self) -> None:
        while self._running and self._socket:
            try:
                conn, _ = self._socket.accept()
            except OSError:
                continue
            with self._connections_lock:
                self._connections.add(conn)
            handler = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
            handler.start()

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            receiver = TransferReceiver(self.device_id, self.device_name, self.receive_directory, session=self.session)

            def on_progress(progress: TransferProgress) -> None:
                if self.callback:
                    self.callback(progress)

            def on_status(message: str) -> None:
                if self.callback:
                    self.callback({"status_message": message})

            result = receiver.handle_connection(conn, on_progress=on_progress, on_status=on_status)
            if self.callback:
                self.callback(result)
        except TransferRejected as exc:
            if self.callback:
                self.callback({"success": False, "error": str(exc), "rejected": True})
        except Exception as exc:
            if self.callback:
                with self._connections_lock:
                    cancelled = conn in self._cancelled_connections
                if cancelled:
                    self.callback({"success": False, "cancelled": True})
                else:
                    self.callback({"success": False, "error": str(exc)})
        finally:
            with self._connections_lock:
                self._connections.discard(conn)
                self._cancelled_connections.discard(conn)
            conn.close()
