"""
"""


# import sys
from .fill_excel_columns_module import FillExcelColumns
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QTabWidget
)
# from PySide6.QtCore import Qt, QMimeData
# from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPalette


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Fill optinization module")
        self.resize(640, 480)

        self.main_window_ui()

    def main_window_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.create_tabs(layout)

    def create_toggle_button_language():
        pass

    def create_switch_button_theme():
        pass

    def create_tabs(self, layout):
        self.tab_widget = QTabWidget()

        tab1 = QWidget()
        tab2 = FillExcelColumns()
        tab3 = QWidget()

        self.tab_widget.addTab(tab1, "Excel merger")
        self.tab_widget.addTab(tab2, "Fill module")
        self.tab_widget.addTab(tab3, "Третья вкладка")

        layout.addWidget(self.tab_widget)

    def set_language(self):
        pass

    def choose_theme(self):
        pass

    def light_theme(self):
        pass

    def dark_theme(self):
        pass
