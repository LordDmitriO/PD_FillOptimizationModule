"""
Главное окно приложения с вкладками для различных модулей
"""

import config
from .excel_merger_module import ExcelMerger
from .fill_excel_columns_module import FillExcelColumns
from .settings import run_settings_dialog

from PySide6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QTabWidget, QToolButton
)
from PySide6.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Fill optimization module")
        self.resize(640, 480)

        self.is_dev_mode = config.AppSettings.is_dev_mode

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
        """Создание вкладок приложения и кнопки настроек"""
        self.tab_widget = QTabWidget()

        tab1 = ExcelMerger()
        tab2 = FillExcelColumns()

        self.tab_widget.addTab(tab1, "🔗 Объединение Excel")
        self.tab_widget.addTab(tab2, "🔍 Парсинг организаций")

        self.settings_button = QToolButton()
        self.settings_button.setText("⚙️")
        self.settings_button.setToolTip("Настройки")
        self.settings_button.clicked.connect(self.on_settings_clicked)

        self.tab_widget.setCornerWidget(self.settings_button, Qt.TopRightCorner)

        layout.addWidget(self.tab_widget)

    def on_settings_clicked(self):
        """Обработчик нажатия на кнопку"""

        new_settings = run_settings_dialog(self, config.AppSettings.is_dev_mode)

        config.AppSettings.is_dev_mode = new_settings["dev_mode"]
        self.is_dev_mode = config.AppSettings.is_dev_mode

        if self.is_dev_mode:
            print("Режим разработчика включен")
        else:
            print("Режим разработчика выключен")

    def set_language(self):
        pass

    def choose_theme(self):
        pass

    def light_theme(self):
        pass

    def dark_theme(self):
        pass
