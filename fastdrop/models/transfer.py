from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any


@dataclass
class DeviceInfo:
    """Metadata for a discovered FastDrop peer."""

    device_id: str
    device_name: str
    ip: str
    port: int
    status: str = "available"
    discovered_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "ip": self.ip,
            "port": self.port,
            "status": self.status,
            "discovered_at": self.discovered_at,
        }


@dataclass
class TransferRequest:
    """A pending file-transfer request."""

    request_id: str
    sender_device_id: str
    sender_device_name: str
    filename: str
    file_size: int
    sha256: str
    sender_ip: str
    sender_port: int
    message_type: str = "TRANSFER_REQUEST"


@dataclass
class TransferProgress:
    """Transfer state for a single file send/receive operation."""

    total_bytes: int = 0
    transferred_bytes: int = 0
    speed_bps: float = 0.0
    eta_seconds: float = 0.0
    status: str = "idle"
    error: str | None = None
    file_hash: str | None = None
    verified: bool = False
