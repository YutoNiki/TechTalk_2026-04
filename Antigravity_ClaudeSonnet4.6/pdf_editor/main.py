"""
main.py - Entry point for PDF Editor Pro
"""
import sys
import os

# Ensure the project root is on the Python path when running directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow


def main():
    # Enable High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("PDF Editor Pro")
    app.setOrganizationName("PDFEditorPro")

    # Set a clean default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
