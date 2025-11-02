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

# from gensim.models import Word2Vec
# from gensim.utils import simple_preprocess

from selenium import webdriver as wd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
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

        self.humanizer = Humanization()
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
        chrome_options = wd.ChromeOptions()
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--incognito")
        chrome_options.add_argument("--enable-unsafe-swiftshader")
        # chrome_options.add_argument("--headless")

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

        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        browser = wd.Chrome(options=chrome_options)
        main_url = "https://www.rusprofile.ru"
        url = "/search-advanced"
        full_start_url = main_url + url

        time.sleep(rd.uniform(0.1, 0.5))

        browser.get(full_start_url)
        self.humanizer.human_like_wait(2)
        try:
            search = self.humanizer.human_like_wait_for_element(
                browser, (By.ID, "advanced-search-query"), 10
            )
        except TimeoutException:
            print("Поисковая строка расширенного поиска не найдена!")

            browser.quit

            return

        string_count = 2

        for data_element in our_parse_data:
            # search.send_keys(Keys.CONTROL + 'a')
            # search.send_keys(Keys.DELETE)

            # search.send_keys(data_element)

            self.humanizer.human_like_type(browser, search, data_element)
            self.humanizer.random_mouse_movement(browser, search)

            search.send_keys(Keys.ENTER)
            self.humanizer.human_like_wait(1.5)

            try:
                search_result = self.humanizer.human_like_wait_for_element(
                    browser, (By.CLASS_NAME, "list-element__title"), 5
                )
                if search_result:
                    self.humanizer.human_like_wait(rd.uniform(0.5, 1.0))
                # WDW(browser, 5).until(
                #     EC.staleness_of(search_result)
                # )
            except Exception:
                pass

            try:
                # WDW(browser, 5).until(
                #     EC.presence_of_element_located((By.CLASS_NAME, "list-element__title"))
                # )
                self.humanizer.human_like_wait_for_element(
                    browser, (By.CLASS_NAME, "list-element__title"), 5
                )
                self.humanizer.human_like_scroll(browser)

                soup = BS(browser.page_source, "lxml")
                all_publications = soup.find_all("a", {"class": "list-element__title"})

            except TimeoutException:
                print(f'Ошибка при поиске {data_element}: превышено время ожидания')
                all_publications = None
                try:
                    # WDW(browser, 5).until(
                    #     EC.element_to_be_clickable((By.ID, "advanced-search-query"))
                    # )
                    self.humanizer.human_like_wait_for_element(
                        browser, (By.ID, "advanced-search-query"), 5
                    )
                except TimeoutException:
                    print("Поле поиска недоступно, выполнение программы прервано!")
                    break

            print(data_element)
            self.parse_full_company_name(browser, main_url, all_publications, string_count)
            string_count += 1
            if all_publications:
                self.humanizer.human_like_wait_for_element(
                    browser, (By.ID, "advanced-search-query"), 10
                )
            else:
                self.humanizer.human_like_wait(1)
                self.humanizer.human_like_wait_for_element(
                    browser, (By.ID, "advanced-search-query"), 10
                )

            search = self.humanizer.human_like_wait_for_element(
                browser, (By.ID, "advanced-search-query"), 5
            )

        browser.quit()

    def parse_full_company_name(self, browser, main_url, all_publications, string_count):
        organizations_data_arr = []
        company_info = {}
        if all_publications:

            article = all_publications[0]
            try:

                link_element = self.humanizer.human_like_wait_for_element(
                    browser, (By.XPATH, f"//a[@href='{article['href']}']"), 5
                )
                if link_element:
                    self.humanizer.human_like_click(browser, link_element)
                else:
                    browser.get(main_url + article["href"])
            except TimeoutException:
                browser.get(main_url + article["href"])

            self.humanizer.human_like_wait(1.5)
            self.humanizer.human_like_scroll(browser)

            try:
                self.humanizer.debug_element_search(browser, 'clip_name-long')
                name = self.humanizer.human_like_wait_for_element(
                    browser, (By.ID, "clip_name-long"), 10
                )
            except TimeoutException:
                print("Элемент названия не найден!")
                name = None

            try:
                self.humanizer.debug_element_search(browser, 'clip_address')
                address = self.humanizer.human_like_wait_for_element(
                    browser, (By.ID, "clip_address"), 10
                )
            except TimeoutException:
                print("Элемент адреса не найден!")
                address = None

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
        self.humanizer.close_all_except_first(browser)

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


class Humanization:
    def __init__(self):
        self.type_pause_time = rd.uniform(0.01, 0.1)
        self.scroll_pause_time = rd.uniform(1.0, 2.0)
        self.scroll_up = rd.randint(100, 300)

    def human_like_type(self, browser, element, text):
        try:
            actions = AC(browser)
            actions.move_to_element(element)
            actions.click()
            actions.perform()

            element.clear()
            time.sleep(rd.uniform(0.1, 0.3))

            for char in text:
                element.send_keys(char)
                time.sleep(self.type_pause_time)

                if rd.random() < 0.05:
                    wrong_char = rd.choice(string.ascii_lowercase)
                    element.send_keys(wrong_char)
                    time.sleep(rd.uniform(0.1, 0.2))
                    element.send_keys(Keys.BACKSPACE)
                    time.sleep(rd.uniform(0.1, 0.2))

        except Exception as e:
            print(f"Ошибка при вводе текста: {e}")
            element.clear()
            element.send_keys(text)

    def human_like_scroll(self, browser):
        try:
            last_height = browser.execute_script("return document.body.scrollHeight")
            current_scroll = 0

            while current_scroll < last_height:
                scroll_amount = rd.randint(200, 500)
                current_scroll += scroll_amount

                if current_scroll > last_height:
                    current_scroll = last_height

                browser.execute_script(f"window.scrollTo(0, {current_scroll});")
                time.sleep(self.scroll_pause_time)

                if rd.random() < 0.3:
                    time.sleep(rd.uniform(0.5, 1.5))

                new_height = browser.execute_script("return document.body.scrollHeight")
                if new_height > last_height:
                    last_height = new_height

            if rd.random() < 0.5:
                scroll_back = rd.randint(100, 300)
                browser.execute_script(f"window.scrollTo(0, {current_scroll - scroll_back});")
                time.sleep(rd.uniform(0.5, 1.0))

        except Exception as e:
            print(f"Ошибка при прокрутке: {e}")

    def human_like_click(self, browser, element):

        timeout = 10
        old_tabs = browser.window_handles

        try:
            actions = AC(browser)

            actions.move_to_element(element)
            actions.perform()
            time.sleep(rd.uniform(0.3, 0.8))

            element.click()

            WDW(browser, timeout).until(
                lambda driver: len(driver.window_handles) > len(old_tabs)
            )

            new_tab = [tab for tab in browser.window_handles if tab not in old_tabs][0]
            browser.switch_to.window(new_tab)

            WDW(browser, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )

        except TimeoutException:
            print("⚠️ Новая вкладка не открылась, возможно переход на той же странице")

            WDW(browser, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )

            return True

        except Exception as e:
            print(f"❌ Ошибка: {e}")

            return False

    def human_like_hover(self, browser, element):
        try:
            actions = AC(browser)

            x_offset = rd.randint(-10, 10)
            y_offset = rd.randint(-10, 10)

            actions.move_to_element_with_offset(element, x_offset, y_offset)
            actions.perform()

            time.sleep(rd.uniform(1, 2))

        except Exception as e:
            print(f"Ошибка при наведении: {e}")

    def human_like_wait(self, base_seconds):
        variation = rd.uniform(-0.3, 0.3)
        wait_time = max(0.1, base_seconds + variation)
        time.sleep(wait_time)

    def human_like_wait_for_element(self, browser, locator, timeout=10):
        try:
            try:
                _ = browser.current_url
            except Exception:
                print("❌ Браузер закрыт или недоступен!")
                return None

            element = WDW(browser, timeout).until(
                EC.visibility_of_element_located(locator)
            )

            self.human_like_wait(rd.uniform(0.2, 0.8))
            return element

        except TimeoutException:
            print(f"⏱️ Таймаут: элемент {locator} не найден за {timeout} сек")
            return None

        except WebDriverException as e:
            print(f"❌ WebDriver ошибка для {locator}: {e.msg}")

            try:
                browser.current_url
                print("✅ Браузер еще работает")
            except Exception:
                print("❌ Браузер недоступен!")
            return None

        except Exception as e:
            print(f"❌ Неожиданная ошибка для {locator}: {type(e).__name__} - {e}")
            return None

    def random_mouse_movement(self, browser, element=None):
        try:
            actions = AC(browser)

            if element:
                location = element.location_once_scrolled_into_view
                x = location['x'] + rd.randint(-50, 50)
                y = location['y'] + rd.randint(-50, 50)
                actions.move_by_offset(x, y)
            else:
                x_offset = rd.randint(-100, 100)
                y_offset = rd.randint(-100, 100)
                actions.move_by_offset(x_offset, y_offset)

            actions.perform()
            time.sleep(rd.uniform(0.2, 0.5))

        except Exception as e:
            print(f"Ошибка при движении мышью: {e}")

    def debug_element_search(self, browser, element_id):
        print(f"\n🔍 Диагностика элемента: {element_id}")
        print(f"📄 URL: {browser.current_url}")

        elements_by_id = browser.find_elements(By.ID, element_id)
        print(f"✅ Найдено по ID: {len(elements_by_id)}")

        all_ids = browser.execute_script("""
            return Array.from(document.querySelectorAll('[id]'))
                .map(el => el.id)
                .filter(id => id.includes('clip'));
        """)
        print(f"📋 ID содержащие 'clip': {all_ids}")

        iframes = browser.find_elements(By.TAG_NAME, "iframe")
        print(f"🖼️ Найдено iframe: {len(iframes)}")

        ready_state = browser.execute_script("return document.readyState")
        print(f"📊 Состояние страницы: {ready_state}")

        shadow_check = browser.execute_script(f"""
            const el = document.getElementById('{element_id}');
            if (el) return 'Элемент найден!';

            const allElements = document.querySelectorAll('*');
            for (let el of allElements) {{
                if (el.shadowRoot) {{
                    const shadowEl = el.shadowRoot.getElementById('{element_id}');
                    if (shadowEl) return 'Найден в Shadow DOM';
                }}
            }}
            return 'Не найден';
        """)
        print(f"🌓 Shadow DOM: {shadow_check}")

    def close_all_except_first(self, browser):
        first_handle = browser.window_handles[0]

        while len(browser.window_handles) > 1:

            for handle in browser.window_handles:
                if handle != first_handle:
                    browser.switch_to.window(handle)
                    time.sleep(rd.uniform(0.3, 0.6))

                    try:
                        actions = AC(handle)
                        actions.key_down(Keys.CONTROL).send_keys('w').key_up(Keys.CONTROL).perform()
                        time.sleep(2)
                    except Exception:
                        browser.close()

                    time.sleep(rd.uniform(0.5, 1.0))
                    break

        browser.switch_to.window(first_handle)
        time.sleep(rd.uniform(0.5, 1.0))
        print("✅ Осталась только первая вкладка")
