from __future__ import annotations

import json
import socket
import threading
import time
from typing import Callable

from fastdrop.models.transfer import DeviceInfo
from fastdrop.security.validation import validate_device_name, validate_tcp_port
from fastdrop.utils.network import build_broadcast_address, get_local_ip, is_local_network_ip


class DiscoveryService:
    """Broadcast UDP discovery messages and cache discovered devices."""

    DEVICE_EXPIRY_SECONDS = 8.0

    def __init__(
        self,
        device_id: str,
        device_name: str,
        tcp_port: int,
        discovery_port: int = 50001,
        callback: Callable[[DeviceInfo], None] | None = None,
    ) -> None:
        self.device_id = device_id
        self.device_name = device_name
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port
        self.callback = callback
        self._devices: dict[str, DeviceInfo] = {}
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self._running = False
        self._listener_thread: threading.Thread | None = None
        self._broadcast_thread: threading.Thread | None = None

    @property
    def devices(self) -> list[DeviceInfo]:
        with self._lock:
            cutoff = time.monotonic() - self.DEVICE_EXPIRY_SECONDS
            expired = [device_id for device_id, seen_at in self._last_seen.items() if seen_at < cutoff]
            for device_id in expired:
                self._last_seen.pop(device_id, None)
                self._devices.pop(device_id, None)
            return list(self._devices.values())

    def start(self) -> None:
        self._running = True
        self._listener_thread = threading.Thread(target=self._listen_for_messages, daemon=True)
        self._listener_thread.start()
        self._broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._broadcast_thread.start()

    def stop(self) -> None:
        self._running = False

    def _listen_for_messages(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self.discovery_port))
        sock.settimeout(1.0)
        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            if not is_local_network_ip(addr[0]):
                continue
            try:
                payload = json.loads(data.decode("utf-8"))
            except (TypeError, ValueError, UnicodeDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            message_type = payload.get("type")
            if message_type == "DISCOVERY":
                self._handle_discovery_message(payload, addr)
            elif message_type == "DISCOVERY_RESPONSE":
                self._handle_discovery_response(payload)

    def _broadcast_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        while self._running:
            try:
                local_ip = get_local_ip()
                broadcast_ip = build_broadcast_address(local_ip)
                payload = {
                    "type": "DISCOVERY",
                    "device_id": self.device_id,
                    "device_name": self.device_name,
                    "port": self.tcp_port,
                    "status": "available",
                }
                sock.sendto(json.dumps(payload).encode("utf-8"), (broadcast_ip, self.discovery_port))
            except OSError:
                pass
            time.sleep(2.0)

    def _handle_discovery_message(self, payload: dict, addr: tuple[str, int]) -> None:
        if not is_local_network_ip(addr[0]):
            return
        peer_device_id = payload.get("device_id")
        if not peer_device_id or peer_device_id == self.device_id:
            return
        try:
            validate_tcp_port(int(payload.get("port", self.tcp_port)))
        except (TypeError, ValueError):
            return
        response_payload = {
            "type": "DISCOVERY_RESPONSE",
            "device_id": self.device_id,
            "device_name": validate_device_name(self.device_name),
            "ip": get_local_ip(),
            "port": self.tcp_port,
            "status": "available",
        }
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(json.dumps(response_payload).encode("utf-8"), (addr[0], self.discovery_port))

    def _handle_discovery_response(self, payload: dict) -> None:
        device_ip = payload.get("ip") or payload.get("sender_ip")
        if not device_ip or not is_local_network_ip(device_ip):
            return
        try:
            port = int(payload.get("port", 0))
            validate_tcp_port(port)
        except (TypeError, ValueError):
            return
        device = DeviceInfo(
            device_id=str(payload.get("device_id", "unknown"))[:128],
            device_name=validate_device_name(str(payload.get("device_name", "Unknown"))),
            ip=device_ip,
            port=port,
            status=str(payload.get("status", "available"))[:32],
        )
        with self._lock:
            self._devices[device.device_id] = device
            self._last_seen[device.device_id] = time.monotonic()
        if self.callback:
            self.callback(device)
