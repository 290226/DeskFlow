#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeskFlow - Desktop Project Manager"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    font = QFont("Helvetica Neue", 10)
    if not QFontDatabase.hasFamily("Helvetica Neue"):
        font = QFont("Arial", 10)
    if not QFontDatabase.hasFamily("Arial"):
        font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
