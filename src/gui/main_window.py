"""
Главное окно приложения с вкладками для различных модулей
"""

from .excel_merger_module import ExcelMerger
from .fill_excel_columns_module import FillExcelColumns
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QTabWidget
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Fill optinization module")
        self.resize(640, 480)

        self.main_window_ui()

    def main_window_ui(self):
        """Инициализация главного окна"""
        central_widget = QWidget()
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.create_tabs(layout)

    def create_toggle_button_language():
        """Переключение языка интерфейса"""
        pass

    def create_switch_button_theme():
        """Переключение темы"""
        pass

    def create_tabs(self, layout):
        """Создание вкладок приложения"""
        self.tab_widget = QTabWidget()

        tab1 = ExcelMerger()
        tab2 = FillExcelColumns()

        self.tab_widget.addTab(tab1, "🔗 Объединение Excel")
        self.tab_widget.addTab(tab2, "🔍 Парсинг организаций")

        layout.addWidget(self.tab_widget)

    def set_language(self):
        pass

    def choose_theme(self):
        pass

    def light_theme(self):
        pass

    def dark_theme(self):
        pass
