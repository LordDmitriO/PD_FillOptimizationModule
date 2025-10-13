"""
"""

import re
import time
import string
import random as rd
import pandas as pd
import threading
import language_tool_python
from queue import Queue
from pymorphy3 import MorphAnalyzer as MA

from gensim.models import Word2Vec
from gensim.utils import simple_preprocess

from selenium import webdriver as wd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains as AC
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
        start_time = time.time()
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if not self.check_file_extensions(file_path):
                QMessageBox.warning(self, "Ошибка", "Неподдерживаемый тип файла!")
            else:
                self.read_excel_file(file_path)
                print(f"File dropped: {file_path}")

                end_time = time.time()
                result_time = round(end_time - start_time, 2)
                print(f'Время выполнения программы заняло: {result_time} с')

    def browse_file(self):
        start_time = time.time()
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select files", "", "Excel-files (*.xlsx; *.xls)")
        for file_path in file_paths:
            print(f"File selected: {file_path}")
            self.read_excel_file(file_path)

            end_time = time.time()
            result_time = round(end_time - start_time, 2)
            print(f'Время выполнения программы заняло: {result_time} с')

    def check_file_extensions(self, file_path):
        return file_path.endswith(('.xlsx', '.xls'))

    def read_excel_file(self, file_path):
        try:
            self.df = pd.read_excel(file_path)
            self.parse_excel_data()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f'Не удалось обработать файл: {str(e)}')

    def parse_excel_data(self):
        raw_data_column = self.get_raw_data_from_column()

        convert_time_start = time.time()
        processed_data_column = self.convert_names_for_parse(raw_data_column)
        convert_time_end = time.time()
        convert_time_result = round(convert_time_end - convert_time_start, 2)

        print(f'Преобразование слов заняло: {convert_time_result} с')

        self.parse_browser_data(processed_data_column)

    def get_raw_data_from_column(self):
        try:
            data = []
            column_index = self.df.columns.get_loc("Образовательное учреждение из 1С")
            column_data = self.df.iloc[0:, column_index].dropna()
            data = column_data.tolist()

            return data
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f'Не удалось получить данные из файла: {str(e)}')

    def convert_names_for_parse(self, raw_data_column):
        tool = language_tool_python.LanguageTool('ru')

        def create_correct_spelling(word):
            result_queue = Queue()

            def check_word():
                try:
                    matches = tool.check(word)
                    if matches:
                        corrected_word = tool.correct(word)
                    else:
                        corrected_word = word
                    result_queue.put(corrected_word)
                except Exception as e:
                    result_queue.put((word, f'Ошибки: {str(e)}'))

            thread = threading.Thread(target=check_word)
            thread.start()

            thread.join(timeout=10.0)

            if thread.is_alive():
                print(f'Превышено время проверки для слова: {word}')
                thread.join()
                return word
            else:
                print(f'Успешно прошло проверку слово: {word}')

            result_correct_word = result_queue.get()
            if isinstance(result_correct_word, tuple):
                print(f'Описание ошибки: {result_correct_word[1]}')
                result_correct_word = result_correct_word[0]

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

    def parse_browser_data(self, our_parse_data):
        # driver = CDM().install()
        main_url = "https://www.rusprofile.ru"
        chrome_options = wd.ChromeOptions()
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--incognito")

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.2420.81",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 OPR/109.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 OPR/109.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux i686; rv:124.0) Gecko/20100101 Firefox/124.0"
        ]
        selected_user_agent = rd.choice(user_agents)
        chrome_options.add_argument(f'--user-agent={selected_user_agent}')

        # chrome_options.add_argument("--headless")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        browser = wd.Chrome(options=chrome_options)
        browser.get(main_url + "/search-advanced")
        # url = "/search-advanced"
        # open_search = browser.find_element(By.XPATH, "//a[@href='/search-advanced']")
        try:
            search = WDW(browser, 10).until(
                EC.presence_of_element_located((By.ID, "advanced-search-query"))
            )
        except TimeoutException:
            print("Элемент не найден!")

        string_count = 2

        for data_element in our_parse_data:
            search.send_keys(Keys.CONTROL + 'a')
            search.send_keys(Keys.DELETE)

            search.send_keys(data_element)

            try:
                search_result = WDW(browser, 5).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "list-element__title"))
                )
                WDW(browser, 5).until(
                    EC.staleness_of(search_result)
                )
            except Exception as e:
                pass

            try:
                WDW(browser, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "list-element__title"))
                )

                soup = BS(browser.page_source, "lxml")
                all_publications = soup.find_all("a", {"class": "list-element__title"})

            except TimeoutException:
                print(f'Ошибка при поиске {data_element}: превышено время ожидания')
                all_publications = None
                try:
                    WDW(browser, 5).until(
                        EC.element_to_be_clickable((By.ID, "advanced-search-query"))
                    )
                except TimeoutException:
                    print("Поле поиска недоступно, выполнение программы прервано!")
                    break

            print(data_element)
            self.parse_full_company_name(browser, main_url, all_publications, string_count)
            string_count += 1
            if all_publications:
                current_url = browser.current_url
                browser.back()
                WDW(browser, 10).until(
                    EC.url_changes(current_url)
                )
                WDW(browser, 10).until(
                    EC.element_to_be_clickable((By.ID, "advanced-search-query"))
                )
            else:
                # print("Ничего не найдено!")
                WDW(browser, 10).until(
                    EC.element_to_be_clickable((By.ID, "advanced-search-query"))
                )
            # search = browser.find_elements(By.NAME, "query")[1]
            # search.send_keys(Keys.ENTER)
        # time.sleep(2)
        browser.quit()
        # time.sleep(2)
        # open_search = browser.find_element(By.ID, "indexsearchform")
        # open_search.click()
        # time.sleep(2)
        # search = browser.find_elements(By.NAME, "query")[1]
        # # browser.execute_script("arguments[0].send_keys('Школа 58');", search)
        # search.send_keys("Школа 58")
        # search.send_keys(Keys.ENTER)

    def parse_full_company_name(self, browser, main_url, all_publications, string_count):
        organizations_data_arr = []
        company_info = {}
        if all_publications:
            # for article in all_publications:
            article = all_publications[0]
            browser.get(main_url + article["href"])
            try:
                name = WDW(browser, 10).until(
                    EC.presence_of_element_located((By.ID, "clip_name-long"))
                )
            except TimeoutException:
                print("Элемент не найден!")
            try:
                address = WDW(browser, 10).until(
                    EC.presence_of_element_located((By.ID, "clip_address"))
                )
            except TimeoutException:
                print("Элемент не найден!")
            company_info["Номер строки:"] = string_count
            company_info["Название организации:"] = name.text
            company_info["Адрес организации:"] = address.text
            organizations_data_arr.append(company_info)
        else:
            company_info["Номер строки:"] = string_count
            company_info["Название организации:"] = None
            company_info["Адрес организации:"] = None
            company_info["Название организации в род падеже:"] = None
            company_info["Индекс:"] = None
            organizations_data_arr.append(company_info)
        self.create_complete_data(organizations_data_arr)

    def create_complete_data(self, organizations_data_arr):
        morph = MA()
        for company_info in organizations_data_arr:
            if company_info["Название организации:"]:
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


# class Humanization:
#     def __init__(self):
#         super().__init__()

#         self.type_pause_time = rd.uniform(0.1, 0.3)
#         self.scroll_pause_time = rd.uniform(1.0, 2.0)
#         self.scroll_up = rd.randint(100, 300)

#     def human_like_type(self, browser, element, text):
#         actions = AC(browser)
#         actions.move_to_element(element)
#         actions.click()
#         actions.perform()

#         if element.get_attribute():
#             pass

#         for char in text:
#             actions.send_keys(char)
#             time.sleep(self.type_pause_time)

#             if rd.random() < 0.05:
#                 actions.send_keys(rd.choice(string.ascii_lowercase))
#                 time.sleep(rd.uniform(0.1, 0.2))
#                 actions.send_keys(u'\ue003')

#         actions.perform()

#     def human_like_scroll(self, browser):
#         last_height = browser.execute_script("return document.body.scrollHeight")

#         while True:
#             browser.execute_script(f"window.scrollTo(0, {self.scroll_up});")
#             time.sleep(self.scroll_pause_time)

#             new_height = browser.execute_script("return document.body.scrollHeight")
#             if new_height == last_height:
#                 break
#             last_height = new_height

#     def human_like_click(self, browser, element):
#         actions = AC(browser)
#         actions.move_to_element(element)
#         time.sleep(rd.uniform(0.5, 1.5))
#         actions.click().perform()

#     def human_like_hover(self, browser, element):
#         actions = AC(browser)
#         actions.move_to_element(element)
#         time.sleep(rd.uniform(1, 2))
#         actions.perform()

#     def human_like_wait(self, seconds):
#         time.sleep(rd.uniform(seconds - 0.5, seconds + 0.5))

#     def human_like_wait_for_element(self, browser, locator, timeout=10):
#         try:
#             element = WDW(browser, timeout).until(
#                 EC.presence_of_element_located(locator)
#             )
#             self.human_like_wait(rd.uniform(0.5, 1.5))

#             return element
#         except Exception as e:
#             print(f"Ошибка при ожидании элемента: {e}")

#             return None
