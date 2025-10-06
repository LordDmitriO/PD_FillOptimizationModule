"""
"""

import re
import time
import language_tool_python
import pandas as pd
from pymorphy3 import MorphAnalyzer as MA
from selenium import webdriver as wd
from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait as WDW
# from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
# from webdriver_manager.chrome import ChromeDriverManager as CDM
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
        raw_data_column = self.analyze_file()
        processed_data_column = self.convert_name_for_parse(raw_data_column)

        self.parse_data(processed_data_column)

    def analyze_file(self):
        try:
            data = []
            column_index = self.df.columns.get_loc("Образовательное учреждение из 1С")
            column_data = self.df.iloc[0:, column_index].dropna()
            data = column_data.tolist()
            return data
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f'Не удалось проанализировать файл: {str(e)}')

    def convert_name_for_parse(self, raw_data_column):
        tool = language_tool_python.LanguageTool('ru')

        def create_correct_spelling(word):
            # tool = language_tool_python.LanguageTool('ru')

            # word = 'лицей'
            matches = tool.check(word)
            if matches:
                corrected_word = tool.correct(word)
            else:
                corrected_word = word
            result_correct_word = corrected_word

            return result_correct_word

        def remove_geo_mentions(text):
            # result_correct_text = re.sub(r'\b(г\.?|город|село|округ|г.\.?|пос\.?|д\.?|станица|хутор|район|область|край|республика)\s+\w+', '', text, flags=re.IGNORECASE)
            result_correct_text = re.sub(r'(.*)".*$', r'\1"', text)

            return result_correct_text

        def clean_text(text):

            quoted_parts = re.findall(r'"(.*?)"', text)
            
            temp_text = text
            
            for part in quoted_parts:
                temp_text = re.sub(rf'"{re.escape(part)}"', '', temp_text)
        
            words = temp_text.split()
            corrected_words = []
    
            for word in words:
                if word.isupper():
                    corrected_words.append(word)
                else:
                    corrected_words.append(word.lower())
        
            cleaned_text = ' '.join(corrected_words).strip()
            if cleaned_text:
                cleaned_text = cleaned_text[0].upper() + cleaned_text[1:]
        
            for part in quoted_parts:
                insert_pos = text.find(f'"{part}"')
                if insert_pos != -1:
                    cleaned_text = cleaned_text[:insert_pos] + f'"{part}"' + cleaned_text[insert_pos:]
            intermediate_result = cleaned_text

            words = intermediate_result.split()
            corrected_words = []
            for word in words:
                corrected_word = create_correct_spelling(word)
                corrected_words.append(corrected_word)
                # time.sleep(10)
            cleaned_text = " ".join(corrected_words)

            result_clean_text = cleaned_text

            return result_clean_text

        result = []
        for company_name in raw_data_column:
            company_name = remove_geo_mentions(company_name)
            company_name = clean_text(company_name)
            result.append(company_name)

        return result

    def parse_data(self, our_parse_data):
        # driver = CDM().install()
        main_url = "https://www.rusprofile.ru"
        chrome_options = wd.ChromeOptions()
        chrome_options.add_argument("--log-level=3")
        # chrome_options.add_argument("--headless")
        browser = wd.Chrome(options=chrome_options)
        browser.get(main_url + "/search-advanced")
        time.sleep(2)
        # url = "/search-advanced"
        # open_search = browser.find_element(By.XPATH, "//a[@href='/search-advanced']")
        # open_search.
        # time.sleep(2)
        search = browser.find_element(By.ID, "advanced-search-query")
        for data_element in our_parse_data:
            search.send_keys(data_element)
            time.sleep(5)
            soup = BS(browser.page_source, "lxml")
            all_publications = soup.find_all("a", {"class": "list-element__title"})
            print(data_element)
            if all_publications:
                self.parse_full_company_name(browser, main_url, all_publications)
                time.sleep(3)
                browser.back()
            else:
                print("Ничего не найдено!")
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

    def parse_full_company_name(self, browser, main_url, all_publications):
        string_count = 2
        organizations_data_arr = []
        if all_publications:
            for article in all_publications:
                browser.get(main_url + article["href"])
                time.sleep(2)
                company_info = {}
                name = browser.find_element(By.ID, "clip_name-long")
                address = browser.find_element(By.ID, "clip_address")
                company_info["Номер строки:"] = string_count
                company_info["Название организации:"] = name.text
                company_info["Адрес организации:"] = address.text
                organizations_data_arr.append(company_info)
                string_count += 1
        self.create_complete_data(organizations_data_arr)

    def create_complete_data(self, organizations_data_arr):
        morph = MA()
        for company_info in organizations_data_arr:
            upd_name = company_info["Название организации:"].title()
            words = upd_name.split()
            transformed_words = []
            in_quotes = False

            for word in words:
                if word.startswith('"') and word.endswith('"'):
                    transformed_words.append(word)
                elif word.startswith('"'):
                    in_quotes = True
                    transformed_words.append(word)
                elif word.endswith('"'):
                    in_quotes = False
                    transformed_words.append(word)
                elif in_quotes:
                    transformed_words.append(word)
                else:
                    parsed = morph.parse(word)[0]
                    transformed_word = parsed.inflect({'gent'})
                    if transformed_word:
                        transformed_words.append(transformed_word.word)
                    else:
                        transformed_words.append(word)
            result_rod_name = ' '.join(transformed_words)

            address = company_info["Адрес организации:"]
            match = re.search(r'\b\d{6}\b', address)
            if match:
                address_index = match.group()
            else:
                address_index = None

            company_info.update({"Название организации:": upd_name, "Название организации в род падеже:": result_rod_name, "Индекс:": address_index})

            print(company_info)
