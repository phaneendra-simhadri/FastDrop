from __future__ import annotations

import json
import socket
import struct
from typing import Any

from fastdrop.networking.constants import CHUNK_SIZE, MAX_JSON_MESSAGE_BYTES, MESSAGE_HEADER_LENGTH

__all__ = ["CHUNK_SIZE", "MESSAGE_HEADER_LENGTH", "send_json_message", "recv_json_message", "recv_exact", "ensure_valid_metadata"]


def send_json_message(sock: socket.socket, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_JSON_MESSAGE_BYTES:
        raise ValueError("Protocol message too large")
    sock.sendall(struct.pack(">I", len(body)) + body)


def recv_json_message(sock: socket.socket, timeout: float | None = None) -> dict[str, Any]:
    if timeout is not None:
        sock.settimeout(timeout)
    try:
        header = recv_exact(sock, MESSAGE_HEADER_LENGTH)
    except socket.timeout as exc:  # pragma: no cover - exercised by integration tests
        raise TimeoutError("Timed out while reading a message header") from exc
    if not header:
        raise EOFError("Connection closed while reading message")
    length = struct.unpack(">I", header)[0]
    if length == 0 or length > MAX_JSON_MESSAGE_BYTES:
        raise ValueError("Invalid protocol message length")
    body = recv_exact(sock, length)
    if len(body) != length:
        raise EOFError("Connection closed while reading message body")
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid protocol message") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid protocol message")
    return payload


def recv_exact(sock: socket.socket, size: int) -> bytes:
    if size < 0 or size > CHUNK_SIZE:
        raise ValueError("Invalid read size")
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(min(size - len(chunks), CHUNK_SIZE))
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


def ensure_valid_metadata(payload: dict[str, Any]) -> None:
    required = {"type"}
    if not required.issubset(payload):
        raise ValueError("Missing required protocol fields")
    if payload["type"] not in {
        "DISCOVERY",
        "DISCOVERY_RESPONSE",
        "TRANSFER_REQUEST",
        "PAIRING_CHALLENGE",
        "PAIRING_RESPONSE",
        "PAIRING_VERIFIED",
        "TRANSFER_ACCEPT",
        "TRANSFER_REJECT",
        "FILE_INFO",
        "FILE_DATA",
        "TRANSFER_COMPLETE",
        "CHECKSUM",
        "ERROR",
    }:
        raise ValueError(f"Unsupported message type: {payload.get('type')}")
