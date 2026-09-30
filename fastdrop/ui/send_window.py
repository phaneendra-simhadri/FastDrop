from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fastdrop.models.transfer import DeviceInfo, TransferProgress
from fastdrop.networking.discovery import DiscoveryService
from fastdrop.networking.sender import FileSender
from fastdrop.ui.theme import get_app_stylesheet
from fastdrop.utils.file_utils import format_bytes


class SendTransferWorker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        sender: FileSender,
        device: DeviceInfo,
        file_path: str,
        request_id: str,
        pairing_code: str,
    ) -> None:
        super().__init__()
        self.sender = sender
        self.device = device
        self.file_path = file_path
        self.request_id = request_id
        self.pairing_code = pairing_code

    @Slot()
    def run(self) -> None:
        try:

            def on_status(message: str) -> None:
                self.progress.emit({"status_message": message})

            result = self.sender.start_transfer(
                self.device,
                self.file_path,
                on_progress=self.progress.emit,
                on_status=on_status,
                request_id=self.request_id,
                pairing_code=self.pairing_code,
            )
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - GUI error path
            if self.sender.cancelled:
                self.finished.emit({"cancelled": True})
            else:
                self.error.emit(str(exc))


class SendWindow(QWidget):
    def __init__(self, device_id: str, device_name: str, discovery: DiscoveryService, file_path: str) -> None:
        super().__init__()
        self.device_id = device_id
        self.device_name = device_name
        self.discovery = discovery
        self.file_path = file_path
        self.selected_device: DeviceInfo | None = None
        self.sender = FileSender(device_id, device_name)
        self._thread: QThread | None = None
        self._worker: SendTransferWorker | None = None
        self._build_ui()
        self._refresh_devices()
        self._device_timer = QTimer(self)
        self._device_timer.timeout.connect(self._refresh_devices)
        self._device_timer.start(2000)
        self.setStyleSheet(get_app_stylesheet())

    def _build_ui(self) -> None:
        self.setWindowTitle("FastDrop - Send")
        self.resize(540, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(16)

        file_card = QFrame()
        file_card.setObjectName("card")
        file_layout = QVBoxLayout(file_card)
        self.file_label = QLabel(f"Selected file: {Path(self.file_path).name}")
        self.file_label.setObjectName("fileName")
        self.size_label = QLabel(f"File size: {format_bytes(Path(self.file_path).stat().st_size)}")
        self.size_label.setObjectName("fileSize")
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.size_label)
        layout.addWidget(file_card)

        layout.addWidget(QLabel("Nearby receivers (same Wi‑Fi / hotspot):"))
        self.device_list = QListWidget()
        self.device_list.itemClicked.connect(self._on_device_selected)
        layout.addWidget(self.device_list)

        self.code_label = QLabel("Pairing code: —")
        self.code_label.setObjectName("pairingCode")
        self.progress_label = QLabel("Status: Select a receiver and click Send")
        self.progress_label.setObjectName("progressLabel")

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)

        layout.addWidget(self.code_label)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("primaryButton")
        self.send_button.clicked.connect(self.start_transfer)
        layout.addWidget(self.send_button)
        self.cancel_button = QPushButton("Cancel transfer")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_transfer)
        layout.addWidget(self.cancel_button)

    def _refresh_devices(self) -> None:
        previous = self.selected_device.device_id if self.selected_device else None
        self.device_list.clear()
        devices = self.discovery.devices
        if not devices:
            empty_item = QListWidgetItem("No devices found — open FastDrop on the receiver and wait a few seconds")
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemIsSelectable)
            self.device_list.addItem(empty_item)
            return
        for device in devices:
            item = QListWidgetItem(f"{device.device_name}  •  {device.ip}:{device.port}")
            item.setData(Qt.ItemDataRole.UserRole, device)
            self.device_list.addItem(item)
            if previous and device.device_id == previous:
                self.device_list.setCurrentItem(item)
                self.selected_device = device

    def _on_device_selected(self, item: QListWidgetItem) -> None:
        device = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(device, DeviceInfo):
            self.selected_device = device
            self.progress_label.setText(f"Selected: {device.device_name} ({device.ip})")

    def start_transfer(self) -> None:
        if not self.selected_device:
            QMessageBox.warning(self, "Selection required", "Choose a receiver from the list first.")
            return

        request_id = f"req-{int(time.time() * 1000)}"
        pairing_code = self.sender.pairing_manager.create(request_id)
        self.code_label.setText(f"Pairing code: {pairing_code}")
        self.progress_label.setText("Status: Connecting — tell the receiver this code")
        self.progress_bar.setValue(5)
        self.send_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

        self._thread = QThread(self)
        self._worker = SendTransferWorker(
            self.sender,
            self.selected_device,
            self.file_path,
            request_id,
            pairing_code,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._update_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._thread.start()

    def _update_progress(self, payload) -> None:
        if isinstance(payload, TransferProgress):
            total = max(payload.total_bytes, 1)
            progress_value = int((payload.transferred_bytes / total) * 100)
            self.progress_bar.setValue(max(0, min(progress_value, 100)))
            self.progress_label.setText(f"Status: {payload.status} — {payload.transferred_bytes}/{payload.total_bytes} bytes")
            return
        if isinstance(payload, dict) and payload.get("status_message"):
            self.progress_label.setText(f"Status: {payload['status_message']}")

    def _on_finished(self, result: dict) -> None:
        self.send_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        if result.get("cancelled"):
            self.progress_label.setText("Status: Transfer cancelled")
            self.progress_bar.setValue(0)
        elif result.get("success"):
            self.progress_bar.setValue(100)
            self.progress_label.setText("Status: Transfer complete — SHA-256 verified")
            QMessageBox.information(self, "Transfer complete", "File sent successfully and verified on the receiver.")
        else:
            self.progress_label.setText("Status: Transfer finished but integrity check failed")
            QMessageBox.warning(self, "Verification failed", "The receiver reported a hash mismatch.")

    def _on_error(self, error: str) -> None:
        self.send_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_label.setText(f"Status: {error}")
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        QMessageBox.critical(self, "Transfer failed", error)

    def _cancel_transfer(self) -> None:
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("Status: Cancelling transfer…")
        self.sender.cancel_transfer()

    def closeEvent(self, event) -> None:  # pragma: no cover
        self._device_timer.stop()
        super().closeEvent(event)
