from __future__ import annotations

import ipaddress
import socket


def get_local_ip() -> str:
    """Return the local IPv4 address used to reach the internet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def build_broadcast_address(ip: str) -> str:
    """Infer the local broadcast address for the active IPv4 subnet."""
    try:
        network = ipaddress.ip_network(f"{ip}/24", strict=False)
        return str(network.broadcast_address)
    except ValueError:
        return "255.255.255.255"


def is_local_network_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False
