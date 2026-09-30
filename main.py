from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from fastdrop.ui.main_window import FastDropMainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("FastDrop")
    window = FastDropMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
