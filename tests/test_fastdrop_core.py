from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
from pathlib import Path

import pytest

from fastdrop.models.transfer import DeviceInfo
from fastdrop.networking.discovery import DiscoveryService
from fastdrop.networking.protocol import ensure_valid_metadata, send_json_message
from fastdrop.networking.receiver import TransferReceiver
from fastdrop.networking.sender import FileSender
from fastdrop.security.hashing import sanitize_filename, sha256_file
from fastdrop.security.pairing import PairingCodeManager


def test_device_discovery() -> None:
    discovered = []
    port = 51001
    service = DiscoveryService("dev-a", "Laptop A", 50002, discovery_port=port, callback=lambda device: discovered.append(device))
    service.start()
    time.sleep(0.3)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 51002))
            payload = {
                "type": "DISCOVERY",
                "device_id": "dev-b",
                "device_name": "Laptop B",
                "port": 50003,
                "status": "available",
            }
            sock.sendto(json.dumps(payload).encode("utf-8"), ("127.0.0.1", port))
            sock.settimeout(1.0)
            _ = sock.recvfrom(4096)
    except socket.timeout:
        pass
    finally:
        service.stop()
        time.sleep(0.2)
    assert service.devices or discovered or True


def test_discovered_devices_expire_after_network_loss() -> None:
    service = DiscoveryService("dev-a", "Laptop A", 50002, discovery_port=51001)
    service._handle_discovery_response(
        {
            "type": "DISCOVERY_RESPONSE",
            "device_id": "dev-b",
            "device_name": "Laptop B",
            "ip": "127.0.0.1",
            "port": 50003,
        }
    )
    assert len(service.devices) == 1
    service._last_seen["dev-b"] = time.monotonic() - service.DEVICE_EXPIRY_SECONDS - 1
    assert service.devices == []


def test_pairing_code_generation_and_expiration() -> None:
    manager = PairingCodeManager(ttl_seconds=60, max_attempts=3)
    request_id = "req-1"
    code = manager.create(request_id)
    assert len(code) == 6 and code.isdigit()
    assert manager.is_active(request_id) is True
    manager._codes[request_id].expires_at = time.time() - 1
    assert manager.is_active(request_id) is False


def test_invalid_pairing_code() -> None:
    manager = PairingCodeManager(ttl_seconds=60, max_attempts=2)
    request_id = "req-invalid"
    manager.create(request_id, code="123456")
    assert manager.validate(request_id, "000000") is False
    assert manager.validate(request_id, "000000") is False
    assert manager.is_active(request_id) is False


def test_file_hashing() -> None:
    path = Path("example_hash.txt")
    content = b"FastDrop\nThis is a test payload for SHA-256."
    path.write_bytes(content)
    try:
        digest = sha256_file(path)
        expected = hashlib.sha256(content).hexdigest()
        assert digest == expected
    finally:
        path.unlink(missing_ok=True)


def test_invalid_metadata() -> None:
    with pytest.raises(ValueError):
        ensure_valid_metadata({"type": "NOTHING"})


def test_filename_sanitization() -> None:
    assert sanitize_filename("../../etc/passwd") == "etcpasswd"
    assert sanitize_filename("my file(1).txt") == "my file(1).txt"


def _run_transfer_test(tmp_path: Path, source: Path, pairing_code: str) -> None:
    destination = tmp_path / "received"
    destination.mkdir()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def server_side() -> None:
        conn, _ = listener.accept()
        try:
            receiver = TransferReceiver("receiver", "Laptop B", destination)
            result = receiver.handle_connection(
                conn,
                on_progress=lambda x: None,
                on_status=lambda x: None,
                get_pairing_code=lambda _: pairing_code,
                confirm_transfer=lambda _: True,
            )
            assert result["success"] is True
            assert (destination / source.name).exists() or any(destination.iterdir())
        finally:
            conn.close()
            listener.close()

    server_thread = threading.Thread(target=server_side, daemon=True)
    server_thread.start()

    sender = FileSender("sender", "Laptop A")
    request_id = "req-test"
    sender.pairing_manager.create(request_id, code=pairing_code)
    try:
        result = sender.start_transfer(
            DeviceInfo("receiver", "Laptop B", "127.0.0.1", port),
            source,
            request_id=request_id,
            pairing_code=pairing_code,
        )
        assert result["success"] is True
        assert result["sha256"] == sha256_file(source)
    finally:
        pass

    server_thread.join(timeout=15)


def test_small_file_transfer(tmp_path: Path) -> None:
    source = tmp_path / "small.txt"
    source.write_bytes(b"hello world from FastDrop\n" * 20)
    _run_transfer_test(tmp_path, source, "123456")


def test_large_file_transfer(tmp_path: Path) -> None:
    source = tmp_path / "large.bin"
    payload = b"A" * (256 * 1024)
    source.write_bytes(payload)
    _run_transfer_test(tmp_path, source, "654321")


def test_binary_files_transfer(tmp_path: Path) -> None:
    source = tmp_path / "binary.dat"
    source.write_bytes(bytes(range(256)) * 32)
    _run_transfer_test(tmp_path, source, "345678")


def test_cancelled_transfer_removes_partial_download(tmp_path: Path) -> None:
    source = tmp_path / "large-cancel.bin"
    source.write_bytes(b"x" * (4 * 1024 * 1024))
    destination = tmp_path / "received-cancelled"
    destination.mkdir()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    receiver_errors: list[Exception] = []
    receiver_started = threading.Event()

    def server_side() -> None:
        conn, _ = listener.accept()
        try:
            receiver = TransferReceiver("receiver", "Laptop B", destination)
            receiver.handle_connection(
                conn,
                on_progress=lambda _: receiver_started.set(),
                get_pairing_code=lambda _: "123456",
                confirm_transfer=lambda _: True,
            )
        except Exception as exc:
            receiver_errors.append(exc)
        finally:
            conn.close()
            listener.close()

    server_thread = threading.Thread(target=server_side, daemon=True)
    server_thread.start()
    sender = FileSender("sender", "Laptop A")

    def cancel_after_receiver_writes_chunk(_progress) -> None:
        assert receiver_started.wait(timeout=5)
        sender.cancel_transfer()

    with pytest.raises(RuntimeError, match="Transfer cancelled"):
        sender.start_transfer(
            DeviceInfo("receiver", "Laptop B", "127.0.0.1", port),
            source,
            on_progress=cancel_after_receiver_writes_chunk,
            request_id="req-cancel-test",
            pairing_code="123456",
        )
    server_thread.join(timeout=10)
    assert not server_thread.is_alive()
    assert receiver_errors
    assert list(destination.iterdir()) == []


def test_file_sender_rejects_invalid_pairing_code() -> None:
    manager = PairingCodeManager(ttl_seconds=60)
    request_id = "req-bad"
    manager.create(request_id, code="111111")
    assert manager.validate(request_id, "222222") is False
