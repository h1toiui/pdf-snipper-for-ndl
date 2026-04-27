import sys

from PySide6.QtWidgets import QApplication

from app import PDFSnipper


def main():
    """Qtアプリケーションを起動してメイン画面を表示する。"""
    app = QApplication(sys.argv)
    window = PDFSnipper()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
