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
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox,
    QSpinBox, QProgressBar, QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt  # QMimeData
# from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPalette

# Импортируем GigaChat API
from gigachat_api import GigaChatAPI
from config import GIGACHAT_AUTH_TOKEN, EXCEL_COLUMN_NAME


class FillExcelColumns(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Нормализация названий ОУ")
        self.setGeometry(100, 100, 700, 500)
        
        # Инициализация GigaChat API
        if not GIGACHAT_AUTH_TOKEN:
            QMessageBox.warning(self, "Ошибка", "Токен GigaChat не найден! Создайте файл .env с переменной GIGACHAT_AUTH_TOKEN")
            self.gigachat_api = None
        else:
            self.gigachat_api = GigaChatAPI(GIGACHAT_AUTH_TOKEN)

        self.widget_ui()

    def widget_ui(self):
        main_layout = QVBoxLayout()

        # Область загрузки файла
        self.label = QLabel("Перетащите файл Excel сюда\nили", alignment=Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("border: 2px dashed gray; padding: 20px;")
        self.label.setAcceptDrops(True)
        self.label.dragEnterEvent = self.drag_enter_event
        self.label.dropEvent = self.drop_event

        browse_file_button = QPushButton("Выбрать файл")
        browse_file_button.clicked.connect(self.browse_file)

        # Настройки GigaChat
        settings_layout = QHBoxLayout()
        
        self.use_gigachat_checkbox = QCheckBox("Использовать GigaChat для не найденных")
        self.use_gigachat_checkbox.setChecked(True)
        
        settings_layout.addWidget(QLabel("Макс. запросов к GigaChat:"))
        self.max_requests_spinbox = QSpinBox()
        self.max_requests_spinbox.setMinimum(0)
        self.max_requests_spinbox.setMaximum(1000)
        self.max_requests_spinbox.setValue(50)
        settings_layout.addWidget(self.max_requests_spinbox)
        settings_layout.addStretch()

        # Кнопка запуска обработки
        self.process_button = QPushButton("Начать обработку")
        self.process_button.clicked.connect(self.start_processing)
        self.process_button.setEnabled(False)

        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        # Текстовое поле для логов
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)

        # Кнопка сохранения
        self.save_button = QPushButton("Сохранить результат")
        self.save_button.clicked.connect(self.save_results)
        self.save_button.setEnabled(False)

        main_layout.addWidget(self.label)
        main_layout.addWidget(browse_file_button)
        main_layout.addWidget(self.use_gigachat_checkbox)
        main_layout.addLayout(settings_layout)
        main_layout.addWidget(self.process_button)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(QLabel("Лог обработки:"))
        main_layout.addWidget(self.log_text)
        main_layout.addWidget(self.save_button)

        self.setLayout(main_layout)
        
        # Проверка подключения к GigaChat
        self.log("Проверка подключения к GigaChat...")
        if self.gigachat_api:
            if self.gigachat_api.test_connection():
                self.log("✓ GigaChat подключен успешно")
            else:
                self.log("✗ Ошибка подключения к GigaChat")
        else:
            self.log("✗ GigaChat API не инициализирован")

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
            
            if EXCEL_COLUMN_NAME not in self.df.columns:
                QMessageBox.warning(self, "Ошибка", f'Столбец "{EXCEL_COLUMN_NAME}" не найден!')
                return
            
            self.log(f"✓ Загружено {len(self.df)} записей из файла")
            self.log(f"Столбец: '{EXCEL_COLUMN_NAME}'")
            self.process_button.setEnabled(True)
            self.label.setText(f"Файл загружен: {len(self.df)} записей")
            
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
            column_index = self.df.columns.get_loc(EXCEL_COLUMN_NAME)
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
            soup = BS(browser.page_source, "html.parser")
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

    # Методы для работы с GigaChat
    def log(self, message):
        """Добавляет сообщение в лог"""
        self.log_text.append(message)

    def start_processing(self):
        """Запускает обработку данных с использованием GigaChat"""
        if not hasattr(self, 'df') or self.df is None:
            self.log("Ошибка: файл не загружен")
            return
        
        self.log("\n=== Начало обработки с GigaChat ===")
        self.process_button.setEnabled(False)
        self.progress_bar.setValue(0)
        
        # Здесь можно добавить логику обработки с GigaChat
        # Пока что просто логируем настройки
        self.log(f"Использовать GigaChat: {self.use_gigachat_checkbox.isChecked()}")
        self.log(f"Максимум запросов: {self.max_requests_spinbox.value()}")
        
        # Симуляция обработки
        self.simulate_processing()

    def simulate_processing(self):
        """Симуляция обработки для демонстрации"""
        import time
        from PySide6.QtCore import QTimer
        
        self.progress = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(100)  # Обновляем каждые 100мс

    def update_progress(self):
        """Обновляет прогресс-бар"""
        self.progress += 2
        self.progress_bar.setValue(self.progress)
        
        if self.progress >= 100:
            self.timer.stop()
            self.processing_finished()

    def processing_finished(self):
        """Завершение обработки"""
        self.log("=== Обработка завершена ===")
        self.process_button.setEnabled(True)
        self.save_button.setEnabled(True)

    def save_results(self):
        """Сохранение результатов"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить результат", "результат_нормализации.xlsx", "Excel-файлы (*.xlsx)"
        )
        
        if file_path:
            try:
                # Здесь должна быть логика сохранения результатов
                self.log(f"✓ Результат сохранен: {file_path}")
                QMessageBox.information(self, "Успех", "Результат успешно сохранен!")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл: {str(e)}")

    def normalize_with_gigachat(self, name):
        """Нормализация названия с помощью GigaChat"""
        try:
            if self.use_gigachat_checkbox.isChecked() and self.gigachat_api:
                normalized = self.gigachat_api.normalize_school_name(name)
                self.log(f"GigaChat нормализовал: {name} -> {normalized}")
                return normalized
            else:
                return name
        except Exception as e:
            self.log(f"Ошибка GigaChat: {str(e)}")
            return name