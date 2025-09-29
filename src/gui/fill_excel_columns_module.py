"""
"""

import pandas as pd
import time
from selenium import webdriver as wd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager as CDM
from bs4 import BeautifulSoup as BS
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt  # QMimeData
# from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPalette


class FillExcelColumns(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Drag and Drop Files")
        self.setGeometry(100, 100, 400, 300)

        self.widget_ui()

    def widget_ui(self):
        main_layout = QVBoxLayout()

        self.label = QLabel("Drag and drop files here \n or \n", alignment=Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("border: 2px dashed gray; padding: 20px;")
        self.label.setAcceptDrops(True)
        self.label.dragEnterEvent = self.drag_enter_event
        self.label.dropEvent = self.drop_event

        browse_file_button = QPushButton("Browse file")
        browse_file_button.clicked.connect(self.browse_file)

        main_layout.addWidget(self.label)
        main_layout.addWidget(browse_file_button)

        self.setLayout(main_layout)

    def drag_enter_event(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def drop_event(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if not self.check_file_extensions(file_path):
                QMessageBox.warning(self, "Ошибка", "Неподдерживаемый тип файла!")
            else:
                self.time_save_file(file_path)
                print(f"File dropped: {file_path}")

    def browse_file(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select files", "", "Excel-files (*.xlsx; *.xls)")
        for file_path in file_paths:
            print(f"File selected: {file_path}")
            self.time_save_file(file_path)

    def check_file_extensions(self, file_path):
        return file_path.endswith(('.xlsx', '.xls'))

    def time_save_file(self, file_path):
        try:
            self.df = pd.read_excel(file_path)
            self.parse_excel_data()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f'Не удалось обработать файл: {str(e)}')

    def parse_excel_data(self):
        data_fourth_column = self.analyze_file()
        print("Данные из четвертого столбца:")
        for el in data_fourth_column:
            print(el)
        self.inner_parse(data_fourth_column)

    def analyze_file(self):
        try:
            data = []
            column_index = self.df.columns.get_loc("Образовательное учреждение из 1С")
            column_data = self.df.iloc[0:, column_index].dropna()
            data = column_data.tolist()
            return data
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f'Не удалось проанализировать файл: {str(e)}')

    def inner_parse(self, our_parse_data):
        # driver = CDM().install()
        chrome_options = wd.ChromeOptions()
        chrome_options.add_argument("--log-level=3")
        browser = wd.Chrome(options=chrome_options)
        browser.get("https://www.rusprofile.ru/")
        time.sleep(2)
        open_search = browser.find_element(By.ID, "indexsearchform")
        open_search.click()
        search = browser.find_elements(By.NAME, "query")[1]
        time.sleep(2)
        # time.sleep(2)
        for data_element in our_parse_data:
            search.send_keys(data_element)
            time.sleep(3)
            # search = browser.find_elements(By.NAME, "query")[1]
            search.send_keys(Keys.CONTROL + 'a')
            search.send_keys(Keys.DELETE)
            # search.send_keys(Keys.ENTER)
        time.sleep(2)
        browser.quit()
        # time.sleep(2)
        # open_search = browser.find_element(By.ID, "indexsearchform")
        # open_search.click()
        # time.sleep(2)
        # search = browser.find_elements(By.NAME, "query")[1]
        # # browser.execute_script("arguments[0].send_keys('Школа 58');", search)
        # search.send_keys("Школа 58")
        # search.send_keys(Keys.ENTER)
