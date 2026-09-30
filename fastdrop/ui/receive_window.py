from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fastdrop.networking.receive_session import ReceiveSessionCoordinator
from fastdrop.ui.theme import get_app_stylesheet


class ReceiveWindow(QWidget):
    def __init__(
        self,
        receive_coordinator: ReceiveSessionCoordinator,
        cancel_transfer: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.coordinator = receive_coordinator
        self.cancel_transfer = cancel_transfer
        self._pending_request: dict | None = None
        self._verified = False
        self._build_ui()
        self.setStyleSheet(get_app_stylesheet())

    def _build_ui(self) -> None:
        self.setWindowTitle("FastDrop - Receive")
        self.resize(520, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(16)

        self.status_label = QLabel("Listening for incoming transfers…")
        self.status_label.setObjectName("windowTitle")

        info_card = QFrame()
        info_card.setObjectName("card")
        info_layout = QVBoxLayout(info_card)
        self.file_label = QLabel("Incoming file: —")
        self.file_label.setObjectName("incomingTitle")
        self.sender_label = QLabel("Sender device: —")
        self.sender_label.setObjectName("senderLabel")
        info_layout.addWidget(self.file_label)
        info_layout.addWidget(self.sender_label)
        layout.addWidget(info_card)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Enter 6-digit code from sender")
        self.code_input.setMaxLength(6)
        self.code_input.setEnabled(False)
        layout.addWidget(self.code_input)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        button_row = QHBoxLayout()
        self.verify_button = QPushButton("Verify Code")
        self.verify_button.setObjectName("primaryButton")
        self.verify_button.setEnabled(False)
        self.verify_button.clicked.connect(self._on_verify_code)
        self.accept_button = QPushButton("Accept File")
        self.accept_button.setObjectName("primaryButton")
        self.accept_button.setEnabled(False)
        self.accept_button.clicked.connect(self._on_accept_file)
        self.reject_button = QPushButton("Reject")
        self.reject_button.setObjectName("dangerButton")
        self.reject_button.setEnabled(False)
        self.reject_button.clicked.connect(self._on_reject)
        self.cancel_button = QPushButton("Cancel download")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel_download)
        button_row.addWidget(self.verify_button)
        button_row.addWidget(self.accept_button)
        button_row.addWidget(self.reject_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        hint = QLabel("Keep this window open. When a sender connects, enter the code they show on their screen.")
        hint.setObjectName("codeHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def handle_event(self, payload) -> None:
        if isinstance(payload, dict):
            if payload.get("cancelled"):
                self._reset_form()
                self.status_label.setText("Transfer cancelled")
                return
            if payload.get("rejected"):
                self.status_label.setText("Transfer rejected")
                self._reset_form()
                return
            if payload.get("error"):
                QMessageBox.critical(self, "Transfer error", str(payload["error"]))
                self.status_label.setText("Transfer failed")
                self._reset_form()
                return
            if payload.get("status_message"):
                self.status_label.setText(str(payload["status_message"]))
                return
            status = getattr(payload, "status", None)
            if status == "receiving":
                total = max(getattr(payload, "total_bytes", 1), 1)
                done = getattr(payload, "transferred_bytes", 0)
                self.progress_bar.setValue(int((done / total) * 100))
                self.status_label.setText(f"Receiving… {done}/{total} bytes")
                self.cancel_button.setEnabled(True)
                return
            if payload.get("success") is True:
                path = payload.get("path", "Downloads/FastDrop")
                self.progress_bar.setValue(100)
                self.status_label.setText("Transfer complete — integrity verified")
                QMessageBox.information(self, "Transfer complete", f"File saved to:\n{path}")
                self._reset_form()
                return
            if payload.get("success") is False and "error" not in payload:
                QMessageBox.warning(self, "Integrity check failed", "The received file hash did not match the sender.")
                self._reset_form()

    def on_incoming_request(self, request: dict) -> None:
        self._pending_request = request
        self._verified = False
        name = request.get("file_name", "unknown")
        sender = request.get("sender_device_name", "Unknown")
        size = request.get("file_size", 0)
        self.file_label.setText(f"Incoming file: {name} ({size} bytes)")
        self.sender_label.setText(f"Sender device: {sender}")
        self.status_label.setText("Enter the pairing code from the sender")
        self.code_input.setEnabled(True)
        self.code_input.clear()
        self.verify_button.setEnabled(True)
        self.accept_button.setEnabled(False)
        self.reject_button.setEnabled(True)
        self.progress_bar.setValue(0)

    def on_pairing_verified(self, _request: dict) -> None:
        self._verified = True
        self.code_input.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.accept_button.setEnabled(True)
        self.status_label.setText("Code verified — click Accept File to start download")

    def _on_verify_code(self) -> None:
        entered = self.code_input.text().strip()
        if len(entered) != 6 or not entered.isdigit():
            QMessageBox.warning(self, "Invalid code", "Please enter the 6-digit code shown on the sender device.")
            return
        self.verify_button.setEnabled(False)
        self.code_input.setEnabled(False)
        self.status_label.setText("Verifying code with sender…")
        self.coordinator.submit_pairing_code(entered)

    def _on_accept_file(self) -> None:
        if not self._verified:
            QMessageBox.warning(self, "Verify first", "Enter and verify the pairing code before accepting.")
            return
        self.accept_button.setEnabled(False)
        self.reject_button.setEnabled(False)
        self.status_label.setText("Accepted — receiving file…")
        self.coordinator.submit_decision(True)

    def _on_reject(self) -> None:
        self.coordinator.reject_transfer()
        self.status_label.setText("Transfer rejected")
        self._reset_form()
        QMessageBox.information(self, "Transfer rejected", "The incoming transfer was cancelled.")

    def _on_cancel_download(self) -> None:
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Cancelling download…")
        if self.cancel_transfer is not None:
            self.cancel_transfer()

    def _reset_form(self) -> None:
        self._pending_request = None
        self._verified = False
        self.code_input.clear()
        self.code_input.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.accept_button.setEnabled(False)
        self.reject_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.file_label.setText("Incoming file: —")
        self.sender_label.setText("Sender device: —")
        self.status_label.setText("Listening for incoming transfers…")

    def closeEvent(self, event) -> None:  # pragma: no cover - GUI event
        super().closeEvent(event)
