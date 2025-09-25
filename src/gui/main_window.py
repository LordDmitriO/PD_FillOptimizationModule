"""
"""


import sys
from PySide6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QLabel, QTabWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPalette


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
        tab2 = QWidget()
        tab3 = QWidget()

        self.tab_widget.addTab(tab1, "Первая вкладка")
        self.tab_widget.addTab(tab2, "Вторая вкладка")
        self.tab_widget.addTab(tab3, "Третья вкладка")

        layout.addWidget(self.tab_widget)

    def set_language(self):
        pass

    def choose_theme(self):
        pass

    def drag_enter_event():
        pass

    def drop_event():
        pass

    def browse_file():
        pass

    def light_theme(self):
        pass

    def dark_theme(self):
        pass


class DragDropWidget(QWidget):
    def __init__(self):
        super().__init__()

    def widget_ui(self):
        main_layout = QVBoxLayout()

        self.label = QLabel("Drag and drop files here", alignment=Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("")
