"""
Головной модуль программы
"""

from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow


def start_app():
    app = QApplication()
    window = MainWindow()
    window.show()

    app.exec()


def main():
    """
    Головная функция для запуска
    """
    start_app()


if __name__ == '__main__':
    main()
