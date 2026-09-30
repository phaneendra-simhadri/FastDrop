from __future__ import annotations


def get_app_stylesheet() -> str:
    return """
        QWidget {
            background: #0b1020;
            color: #e2e8f0;
            font-family: "Segoe UI", Arial, sans-serif;
        }

        QMainWindow, QWidget {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #111827, stop:1 #0b1020);
        }

        QLabel {
            color: #e5eefb;
        }

        QLabel#windowTitle {
            font-size: 30px;
            font-weight: 700;
            color: #f8fafc;
            padding-bottom: 6px;
        }

        QLabel#subtitle {
            font-size: 14px;
            color: #94a3b8;
            padding-bottom: 12px;
        }

        QLabel#deviceName,
        QLabel#deviceId,
        QLabel#localIp,
        QLabel#statusValue,
        QLabel#fileName,
        QLabel#fileSize,
        QLabel#pairingCode,
        QLabel#progressLabel,
        QLabel#incomingTitle,
        QLabel#senderLabel,
        QLabel#codeHint {
            font-size: 14px;
            color: #dfe7f7;
        }

        QLabel#statusValue {
            font-weight: 600;
            color: #7dd3fc;
        }

        QFrame#card, QFrame.card {
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 16px;
        }

        QFrame#card:hover, QFrame.card:hover {
            border: 1px solid rgba(96, 165, 250, 0.5);
        }

        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #38bdf8, stop:1 #2563eb);
            border: none;
            border-radius: 12px;
            color: white;
            font-size: 15px;
            font-weight: 600;
            padding: 12px 16px;
            min-height: 42px;
        }

        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #7dd3fc, stop:1 #3b82f6);
        }

        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #0ea5e9, stop:1 #1d4ed8);
        }

        QPushButton#secondaryButton {
            background: rgba(148, 163, 184, 0.12);
            border: 1px solid rgba(148, 163, 184, 0.22);
            color: #e2e8f0;
        }

        QPushButton#secondaryButton:hover {
            background: rgba(148, 163, 184, 0.2);
        }

        QPushButton#dangerButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #f87171, stop:1 #ef4444);
        }

        QPushButton#dangerButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #fb7185, stop:1 #dc2626);
        }

        QPushButton:disabled {
            background: rgba(148, 163, 184, 0.18);
            color: rgba(226, 232, 240, 0.45);
        }

        QListWidget {
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 12px;
            padding: 8px;
            color: #f8fafc;
            min-height: 150px;
        }

        QListWidget::item {
            border-radius: 8px;
            padding: 8px 10px;
            margin: 2px 0;
        }

        QListWidget::item:selected {
            background: rgba(59, 130, 246, 0.45);
            border: 1px solid rgba(96, 165, 250, 0.5);
            color: #f8fafc;
        }

        QLineEdit {
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 10px;
            color: #f8fafc;
            padding: 10px 12px;
            font-size: 18px;
            letter-spacing: 3px;
            text-align: center;
        }

        QLineEdit:focus {
            border: 1px solid rgba(96, 165, 250, 0.8);
        }

        QProgressBar {
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.9);
            text-align: center;
            color: #e2e8f0;
            min-height: 16px;
        }

        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                      stop:0 #34d399, stop:1 #22c55e);
            border-radius: 8px;
        }

        QScrollBar:vertical {
            background: transparent;
            width: 10px;
        }

        QScrollBar::handle:vertical {
            background: rgba(148, 163, 184, 0.55);
            border-radius: 5px;
        }
    """
