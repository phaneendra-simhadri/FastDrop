from __future__ import annotations

import socket
import struct

import pytest

from fastdrop.networking.protocol import recv_json_message
from fastdrop.security.validation import (
    is_valid_sha256_hex,
    validate_chunk_size,
    validate_file_size,
    validate_transfer_metadata,
)
from fastdrop.utils.file_utils import assert_path_within_directory, build_receive_path


def test_rejects_invalid_sha256() -> None:
    assert is_valid_sha256_hex("abc") is False
    assert is_valid_sha256_hex("g" * 64) is False


def test_rejects_negative_file_size() -> None:
    with pytest.raises(ValueError):
        validate_file_size(-1)


def test_rejects_oversized_chunk() -> None:
    with pytest.raises(ValueError):
        validate_chunk_size(1024 * 1024)


def test_transfer_metadata_validation() -> None:
    digest = "a" * 64
    validate_transfer_metadata(file_name="notes.txt", file_size=10, file_hash=digest)
    with pytest.raises(ValueError):
        validate_transfer_metadata(file_name="../x", file_size=10, file_hash="bad")


def test_build_receive_path_stays_in_directory(tmp_path) -> None:
    receive_dir = tmp_path / "inbox"
    path = build_receive_path(receive_dir, "../../outside.txt")
    assert_path_within_directory(receive_dir.resolve(), path)
    assert path.parent.resolve() == receive_dir.resolve()


def test_protocol_rejects_oversized_message() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    oversized = struct.pack(">I", 1024 * 1024) + (b"x" * 1024)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    conn, _ = listener.accept()
    client.sendall(oversized)
    with pytest.raises(ValueError):
        recv_json_message(conn, timeout=2)
    conn.close()
    client.close()
    listener.close()
