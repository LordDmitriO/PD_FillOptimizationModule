"""
Головной модуль программы
"""


import sys
from PySide6 import QtWidgets as QTW
from gui.winapp import Application


def start_app():
    app = QTW.QApplication(sys.argv)
    window = Application()
    window.show()

    sys.exit(app.exec())


def main():
    """
    Головная функция для запуска
    """
    start_app()


if __name__ == '__main__':
    main()
