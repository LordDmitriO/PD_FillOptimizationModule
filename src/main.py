"""
Головной модуль программы
"""


import sys
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow


def start_app():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


def main():
    """
    Головная функция для запуска
    """
    start_app()


if __name__ == '__main__':
    main()
