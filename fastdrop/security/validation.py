from __future__ import annotations

import os
import re

from fastdrop.networking.constants import CHUNK_SIZE

MAX_JSON_MESSAGE_BYTES = 64 * 1024
MAX_FILE_SIZE_BYTES = int(os.getenv("FASTDROP_MAX_FILE_BYTES", str(2 * 1024**3)))
MAX_FILENAME_LENGTH = 255
MAX_REQUEST_ID_LENGTH = 128
MAX_DEVICE_NAME_LENGTH = 128
MIN_TCP_PORT = 1024
MAX_TCP_PORT = 65535

_SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")


def is_valid_sha256_hex(value: str) -> bool:
    return bool(_SHA256_HEX.match(value))


def validate_request_id(request_id: str) -> None:
    if not request_id or len(request_id) > MAX_REQUEST_ID_LENGTH:
        raise ValueError("Invalid transfer request ID")


def validate_file_size(file_size: int) -> None:
    if file_size < 0:
        raise ValueError("Invalid file size")
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File exceeds maximum allowed size ({MAX_FILE_SIZE_BYTES} bytes)")


def validate_file_name(file_name: str) -> str:
    if not file_name or not isinstance(file_name, str):
        raise ValueError("Invalid file name")
    name = file_name.strip()
    if not name or len(name) > MAX_FILENAME_LENGTH:
        raise ValueError("Invalid file name length")
    return name


def validate_tcp_port(port: int) -> None:
    if port < MIN_TCP_PORT or port > MAX_TCP_PORT:
        raise ValueError("Invalid TCP port")


def validate_transfer_metadata(*, file_name: str, file_size: int, file_hash: str) -> None:
    validate_file_name(file_name)
    validate_file_size(file_size)
    if not is_valid_sha256_hex(file_hash):
        raise ValueError("Invalid SHA-256 hash")


def validate_chunk_size(chunk_size: int) -> None:
    if chunk_size <= 0 or chunk_size > CHUNK_SIZE:
        raise ValueError("Invalid chunk size")


def validate_device_name(name: str) -> str:
    if not name or not isinstance(name, str):
        return "Unknown"
    cleaned = name.strip()[:MAX_DEVICE_NAME_LENGTH]
    return cleaned or "Unknown"
