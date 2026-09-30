from __future__ import annotations

import os
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from fastdrop.networking.discovery import DiscoveryService
from fastdrop.networking.receive_session import ReceiveSessionCoordinator
from fastdrop.networking.receiver import ReceiverListener
from fastdrop.ui.receive_window import ReceiveWindow
from fastdrop.ui.send_window import SendWindow
from fastdrop.ui.theme import get_app_stylesheet
from fastdrop.security.validation import validate_tcp_port
from fastdrop.utils.file_utils import ensure_directory
from fastdrop.utils.network import get_local_ip


class ReceiveEventBridge(QObject):
    """Marshals receiver callbacks from background threads into the Qt UI thread."""

    incoming_request = Signal(dict)
    pairing_verified = Signal(dict)
    transfer_event = Signal(object)


class FastDropMainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.device_id = str(uuid.uuid4())
        self.device_name = os.getenv("FASTDROP_DEVICE_NAME", os.environ.get("COMPUTERNAME", "My Laptop"))
        self.local_ip = get_local_ip()
        self.tcp_port = int(os.getenv("FASTDROP_TCP_PORT", "50002"))
        self.discovery_port = int(os.getenv("FASTDROP_DISCOVERY_PORT", "50001"))
        validate_tcp_port(self.tcp_port)
        validate_tcp_port(self.discovery_port)
        self.receive_directory = os.getenv("FASTDROP_RECEIVE_DIR", str(Path.home() / "Downloads" / "FastDrop"))
        ensure_directory(self.receive_directory)

        self.receive_coordinator = ReceiveSessionCoordinator()
        self.receive_bridge = ReceiveEventBridge()
        self.receive_coordinator.on_incoming_request = lambda req: self.receive_bridge.incoming_request.emit(req)
        self.receive_coordinator.on_pairing_verified = lambda req: self.receive_bridge.pairing_verified.emit(req)

        self.discovery = DiscoveryService(self.device_id, self.device_name, self.tcp_port, self.discovery_port)
        self.discovery.start()
        self.receiver = ReceiverListener(
            self.device_id,
            self.device_name,
            self.receive_directory,
            self.tcp_port,
            session=self.receive_coordinator,
            callback=lambda payload: self.receive_bridge.transfer_event.emit(payload),
        )
        self.receiver.start()

        self.receive_window: ReceiveWindow | None = None
        self._build_ui()
        self._refresh_status()
        self.setStyleSheet(get_app_stylesheet())

        self.receive_bridge.incoming_request.connect(self._on_incoming_request)
        self.receive_bridge.pairing_verified.connect(self._on_pairing_verified)
        self.receive_bridge.transfer_event.connect(self._on_transfer_event)

    def _build_ui(self) -> None:
        self.setWindowTitle("FastDrop")
        self.resize(620, 450)
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(18)

        header = QVBoxLayout()
        title = QLabel("FastDrop")
        title.setObjectName("windowTitle")
        subtitle = QLabel("Local Wi‑Fi file sharing with pairing code and SHA-256 verification.")
        subtitle.setObjectName("subtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        info_card = QFrame()
        info_card.setObjectName("card")
        card_layout = QVBoxLayout(info_card)
        card_layout.setSpacing(8)

        self.device_name_label = QLabel(f"Device name: {self.device_name}")
        self.device_name_label.setObjectName("deviceName")
        self.local_ip_label = QLabel(f"Local IP: {self.local_ip}  •  TCP port {self.tcp_port}")
        self.local_ip_label.setObjectName("localIp")
        self.save_path_label = QLabel(f"Save folder: {self.receive_directory}")
        self.save_path_label.setObjectName("deviceId")
        self.connection_state_label = QLabel("Status: Ready — receiver listens as soon as this app is open")
        self.connection_state_label.setObjectName("statusValue")

        card_layout.addWidget(self.device_name_label)
        card_layout.addWidget(self.local_ip_label)
        card_layout.addWidget(self.save_path_label)
        card_layout.addWidget(self.connection_state_label)
        root.addWidget(info_card)

        actions = QHBoxLayout()
        send_button = QPushButton("Send File")
        send_button.clicked.connect(self.open_send_window)
        send_button.setObjectName("primaryButton")

        receive_button = QPushButton("Receive File")
        receive_button.clicked.connect(self.open_receive_window)
        receive_button.setObjectName("secondaryButton")

        actions.addWidget(send_button)
        actions.addWidget(receive_button)
        root.addLayout(actions)

        demo_hint = QLabel(
            "Demo: On the receiver laptop, open Receive File first. On the sender, pick a file, "
            "select the receiver, click Send, then enter the pairing code on the receiver."
        )
        demo_hint.setWordWrap(True)
        demo_hint.setObjectName("subtitle")
        root.addWidget(demo_hint)

    def _refresh_status(self) -> None:
        self.local_ip = get_local_ip()
        self.local_ip_label.setText(f"Local IP: {self.local_ip}  •  TCP port {self.tcp_port}")

    def open_send_window(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select a file to send")
        if not path:
            return
        self.send_window = SendWindow(self.device_id, self.device_name, self.discovery, path)
        self.send_window.show()

    def open_receive_window(self) -> None:
        if self.receive_window is None:
            self.receive_window = ReceiveWindow(self.receive_coordinator, self.receiver.cancel_current_transfer)
        self.receive_window.show()
        self.receive_window.raise_()
        self.receive_window.activateWindow()

    def _on_incoming_request(self, request: dict) -> None:
        self.connection_state_label.setText("Status: Incoming transfer request")
        self.open_receive_window()
        if self.receive_window is not None:
            self.receive_window.on_incoming_request(request)

    def _on_pairing_verified(self, request: dict) -> None:
        if self.receive_window is not None:
            self.receive_window.on_pairing_verified(request)

    def _on_transfer_event(self, payload) -> None:
        if isinstance(payload, dict) and payload.get("success") is True:
            self.connection_state_label.setText("Status: Last transfer completed successfully")
        if self.receive_window is not None:
            self.receive_window.handle_event(payload)

    def closeEvent(self, event) -> None:  # pragma: no cover - GUI event
        self.discovery.stop()
        self.receiver.stop()
        super().closeEvent(event)
