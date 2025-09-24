"""
Модуль для визуальной отрисовки интерфейса
"""


from PySide6 import QtWidgets as QTW


class Application(QTW.QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Fiil Optimization Module")
        self.resize(640, 480)


class ExcelFileDropWidget(QTW.QWidget):
    def __init__(self):
        super().__init__()

        pass
