"""
Парсер организаций из Excel с использованием Selenium + GigaChat
"""

import pandas as pd
import time
import random as rd
import re
import os
import tempfile
import threading
from queue import Queue
import language_tool_python
from dotenv import load_dotenv
from selenium import webdriver as wd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup as BS
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QProgressBar,
    QTextEdit,
    QCheckBox,
    QSpinBox,
)
from PySide6.QtCore import Qt, QThread, Signal

# Импортируем GigaChat API
try:
    from .gigachat_api import GigaChatAPI

    GIGACHAT_AVAILABLE = True
except ImportError:
    GIGACHAT_AVAILABLE = False
    print("⚠️ Модуль gigachat_api.py не найден")

# Загружаем переменные окружения
load_dotenv()


class ParserThread(QThread):
    """Отдельный поток для парсинга"""

    progress = Signal(int, int)
    log_message = Signal(str)
    finished = Signal(pd.DataFrame)

    def __init__(self, data, df, use_gigachat=False, gigachat_retries=3):
        super().__init__()
        self.data = data
        self.df = df
        self.browser = None
        self.use_gigachat = use_gigachat
        self.gigachat_retries = gigachat_retries
        self.gigachat_api = None

        # Инициализируем GigaChat если нужно
        if self.use_gigachat and GIGACHAT_AVAILABLE:
            auth_token = os.getenv("GIGACHAT_AUTH_TOKEN")
            if auth_token:
                try:
                    self.gigachat_api = GigaChatAPI(auth_token)
                    if self.gigachat_api.test_connection():
                        self.log_message.emit("✅ GigaChat подключен")
                    else:
                        self.gigachat_api = None
                except Exception as e:
                    self.log_message.emit(f"⚠️ Ошибка GigaChat: {e}")
                    self.gigachat_api = None
            else:
                self.log_message.emit("⚠️ GIGACHAT_AUTH_TOKEN не найден в .env")

    def run(self):
        try:
            # Настройка Chrome
            chrome_options = wd.ChromeOptions()
            chrome_options.add_argument("--user-data-dir=./selenium_session")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
            chrome_options.add_experimental_option(
                "excludeSwitches", ["enable-automation"]
            )
            chrome_options.add_experimental_option("useAutomationExtension", False)
            chrome_options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            self.log_message.emit("🚀 Запуск браузера...")
            self.browser = wd.Chrome(options=chrome_options)
            self.browser.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            results = []
            for idx, org_name in enumerate(self.data, 1):
                self.progress.emit(idx, len(self.data))
                self.log_message.emit(f"\n{'='*60}")
                self.log_message.emit(f"📋 [{idx}/{len(self.data)}] {org_name}")

                result = self.search_organization(org_name)
                results.append(result)

            # Добавляем результаты в DataFrame
            self.df["Полное название"] = [r["name"] for r in results]
            self.df["Адрес"] = [r["address"] for r in results]
            self.df["Индекс"] = [r["postal_code"] for r in results]
            self.df["ИНН"] = [r["inn"] for r in results]
            self.df["ОГРН"] = [r["ogrn"] for r in results]
            self.df["Источник"] = [r["source"] for r in results]

            self.finished.emit(self.df)

        except Exception as e:
            self.log_message.emit(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
        finally:
            if self.browser:
                self.browser.quit()
                self.log_message.emit("✅ Браузер закрыт")

    def search_organization(self, org_name):
        """Поиск организации с каскадом источников"""
        result = {
            "name": "",
            "address": "",
            "postal_code": "",
            "inn": "",
            "ogrn": "",
            "source": "Не найдено",
        }

        # 1. RusProfile
        self.log_message.emit(f"🔍 RusProfile...")
        rusprofile_result = self.search_rusprofile(org_name)
        if rusprofile_result["found"]:
            result.update(rusprofile_result)
            result["source"] = "RusProfile"
            return result

        # 2. Контур Фокус
        self.log_message.emit(f"🔍 Контур Фокус...")
        fokus_result = self.search_kontur_fokus(org_name)
        if fokus_result["found"]:
            result.update(fokus_result)
            result["source"] = "Контур Фокус"
            return result

        # 3. ЕГРЮЛ
        self.log_message.emit(f"🔍 ЕГРЮЛ...")
        egrul_result = self.search_egrul(org_name)
        if egrul_result["found"]:
            result.update(egrul_result)
            result["source"] = "ЕГРЮЛ"
            return result

        # 4. GigaChat (если включен и не нашли выше)
        if self.gigachat_api:
            self.log_message.emit(f"🤖 GigaChat (попыток: {self.gigachat_retries})...")
            gigachat_result = self.search_with_gigachat(org_name)
            if gigachat_result["found"]:
                result.update(gigachat_result)
                result["source"] = "GigaChat + повторный поиск"
                return result

        self.log_message.emit(f"❌ Не найдено нигде")
        return result

    def search_rusprofile(self, org_name=None, inn=None):
        result = {"found": False}
        try:
            main_url = "https://www.rusprofile.ru"
            chrome_options = wd.ChromeOptions()
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--incognito")
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_argument("--headless")

            browser = wd.Chrome(options=chrome_options)

            if inn:
                browser.get(main_url)  # обычный поиск
                search_id = "search-query"
            else:
                browser.get(main_url + "/search-advanced") 
                search_id = "advanced-search-query"

            try:
                search = WDW(browser, 10).until(
                    EC.presence_of_element_located((By.ID, search_id))
                )
            except TimeoutException:
                self.log_message.emit("⚠️ Не загрузился поиск")
                browser.quit()
                return result

            search.send_keys(Keys.CONTROL + "a")
            search.send_keys(Keys.DELETE)
            search.send_keys(inn if inn else org_name)
            search.send_keys(Keys.ENTER)
            time.sleep(1.5)

            try:
                WDW(browser, 10).until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "list-element__title")
                    )
                )
            except TimeoutException:
                self.log_message.emit(f"⚠️ Нет результатов для '{org_name}'")
                browser.quit()
                return result

            soup = BS(browser.page_source, "lxml")
            publications = soup.find_all("a", {"class": "list-element__title"})
            if not publications:
                self.log_message.emit("⚠️ Пустой список публикаций")
                browser.quit()
                return result

            self.log_message.emit(f"✓ Найдено результатов: {len(publications)}")

            # Переходим на первую найденную организацию
            link = publications[0]["href"]
            browser.get(main_url + link)

            try:
                name_elem = WDW(browser, 10).until(
                    EC.presence_of_element_located((By.ID, "clip_name-long"))
                )
                address_elem = WDW(browser, 10).until(
                    EC.presence_of_element_located((By.ID, "clip_address"))
                )
            except TimeoutException:
                self.log_message.emit("⚠️ Не загрузились элементы")
                browser.quit()
                return result

            result["name"] = name_elem.text.strip()
            result["address"] = address_elem.text.strip()

            postal_match = re.search(r"\b(\d{6})\b", result["address"])
            if postal_match:
                result["postal_code"] = postal_match.group(1)

            page_text = browser.find_element(By.TAG_NAME, "body").text
            inn_match = re.search(r"ИНН[:\s]*(\d{10,12})", page_text)
            ogrn_match = re.search(r"ОГРН[:\s]*(\d{13,15})", page_text)
            if inn_match:
                result["inn"] = inn_match.group(1)
            if ogrn_match:
                result["ogrn"] = ogrn_match.group(1)

            result["found"] = True
            self.log_message.emit(
                f"✅ ИНН: {result.get('inn')}  ОГРН: {result.get('ogrn')}"
            )
            self.log_message.emit(f"📝 {result['name'][:70]}...")
            self.log_message.emit(f"📍 {result['address'][:70]}...")

            browser.quit()

        except Exception as e:
            self.log_message.emit(f"⚠️ Ошибка: {str(e)}")

        return result

    def search_kontur_fokus(self, org_name):
        """Поиск в Контур Фокус"""
        result = {"found": False}
        try:
            url = f"https://focus.kontur.ru/search?country=RU&query={org_name}"
            self.browser.get(url)

            try:
                WDW(self.browser, 5).until(
                    EC.any_of(
                        EC.presence_of_element_located(
                            (By.XPATH, "//*[contains(text(), 'ИНН')]")
                        ),
                        EC.presence_of_element_located(
                            (By.XPATH, "//*[contains(text(), 'ОГРН')]")
                        ),
                    )
                )
                time.sleep(rd.uniform(1, 2))

                page_text = self.browser.find_element(By.TAG_NAME, "body").text

                if "Найдено 0" in page_text or "Ничего не найдено" in page_text:
                    self.log_message.emit(f"  ⚠️ Нет результатов")
                    return result

                inn_match = re.search(r"ИНН[:\s]*(\d{10,12})", page_text)
                if inn_match:
                    result["inn"] = inn_match.group(1)

                ogrn_match = re.search(r"ОГРН[:\s]*(\d{13,15})", page_text)
                if ogrn_match:
                    result["ogrn"] = ogrn_match.group(1)

                lines = page_text.split("\n")
                for line in lines:
                    if any(
                        word in line.upper()
                        for word in [
                            "АВТОНОМНАЯ",
                            "ГОСУДАРСТВЕННАЯ",
                            "МУНИЦИПАЛЬНАЯ",
                            "ОБЩЕОБРАЗОВАТЕЛЬНАЯ",
                            "НЕКОММЕРЧЕСКАЯ",
                        ]
                    ):
                        if len(line) > 20 and "ИНН" not in line:
                            result["name"] = line.strip()
                            break

                address_match = re.search(
                    r"(\d{6})[,\s]+([^\n]+(?:обл|край|респ|г\.|г |область)[^\n]+)",
                    page_text,
                )
                if address_match:
                    result["address"] = (
                        address_match.group(1) + ", " + address_match.group(2).strip()
                    )
                    result["postal_code"] = address_match.group(1)

                if result["inn"] or result["name"]:
                    result["found"] = True
                    self.log_message.emit(
                        f"  ✅ ИНН: {result['inn']}, ОГРН: {result['ogrn']}"
                    )
                    if result["name"]:
                        self.log_message.emit(f"  📝 {result['name'][:70]}...")
                    if result["address"]:
                        self.log_message.emit(f"  📍 {result['address'][:70]}...")

            except TimeoutException:
                self.log_message.emit(f"  ⏱️ Timeout")

        except Exception as e:
            self.log_message.emit(f"  ⚠️ Ошибка: {str(e)}")

        return result

    def search_egrul(self, org_name):
        """Поиск организации в ЕГРЮЛ с автопереходом в RusProfile"""
        result = {"found": False}
        try:
            url = "https://egrul.nalog.ru/"
            self.browser.get(url)

            try:
                search_field = WDW(self.browser, 7).until(
                    EC.presence_of_element_located((By.ID, "query"))
                )
                search_field.clear()
                search_field.send_keys(org_name)
                search_field.send_keys(Keys.RETURN)

                WDW(self.browser, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "res-text"))
                )
                time.sleep(1)

                page_text = self.browser.find_element(By.TAG_NAME, "body").text

                inn_match = re.search(r"ИНН[:\s]*(\d{10,12})", page_text)
                ogrn_match = re.search(r"ОГРН[:\s]*(\d{13,15})", page_text)
                if inn_match:
                    result["inn"] = inn_match.group(1)
                if ogrn_match:
                    result["ogrn"] = ogrn_match.group(1)

                try:
                    first_result = self.browser.find_element(By.CSS_SELECTOR, ".res-text a")
                    first_result.click()
                    time.sleep(2)
                    detail_text = self.browser.find_element(By.TAG_NAME, "body").text

                    name_match = re.search(r"Полное наименование[:\s]*([^\n]+)", detail_text)
                    if name_match:
                        result["name"] = name_match.group(1).strip()

                    address_match = re.search(r"Адрес[:\s]*([^\n]+)", detail_text)
                    if address_match:
                        result["address"] = address_match.group(1).strip()
                        postal_match = re.search(r"\b(\d{6})\b", result["address"])
                        if postal_match:
                            result["postal_code"] = postal_match.group(1)
                except:
                    pass

                if result.get("inn") or result.get("ogrn"):
                    result["found"] = True
                    self.log_message.emit(f"  ✅ ИНН: {result.get('inn')}, ОГРН: {result.get('ogrn')}")
                    if result.get("name"):
                        self.log_message.emit(f"  📝 {result['name'][:70]}...")

                    # авто-запуск RusProfile
                    self.log_message.emit("  🔗 Переход в RusProfile по ИНН...")
                    rus_result = self.search_rusprofile(org_name, inn=result.get("inn"))
                    if rus_result.get("found"):
                        result.update(rus_result)

            except TimeoutException:
                self.log_message.emit("  ⏱️ Время ожидания истекло")

        except Exception as e:
            self.log_message.emit(f"  ⚠️ Ошибка: {str(e)}")

        return result


    def search_with_gigachat(self, org_name):
        """Нормализация через GigaChat и повторный поиск"""
        result = {"found": False}

        for attempt in range(self.gigachat_retries):
            try:
                self.log_message.emit(
                    f"  🤖 Попытка {attempt + 1}/{self.gigachat_retries}..."
                )

                # Нормализуем название
                normalized_name = self.gigachat_api.normalize_school_name(org_name)

                if normalized_name and normalized_name != "Ошибка":
                    self.log_message.emit(
                        f"  📝 Нормализовано: {normalized_name[:70]}..."
                    )

                    # Пробуем искать нормализованное название
                    self.log_message.emit(f"  🔄 Повторный поиск...")

                    # Пробуем RusProfile с нормализованным названием
                    rus_result = self.search_rusprofile(normalized_name)
                    if rus_result["found"]:
                        result.update(rus_result)
                        result["found"] = True
                        self.log_message.emit(f"  ✅ Найдено после нормализации!")
                        return result

                    # Пробуем Контур Фокус
                    fokus_result = self.search_kontur_fokus(normalized_name)
                    if fokus_result["found"]:
                        result.update(fokus_result)
                        result["found"] = True
                        self.log_message.emit(f"  ✅ Найдено после нормализации!")
                        return result
                else:
                    self.log_message.emit(f"  ⚠️ Ошибка нормализации")

            except Exception as e:
                self.log_message.emit(f"  ⚠️ Ошибка GigaChat: {str(e)}")

            if attempt < self.gigachat_retries - 1:
                time.sleep(1)

        return result


class FillExcelColumns(QWidget):
    def __init__(self):
        super().__init__()
        self.df = None
        self.parser_thread = None
        self.tool = language_tool_python.LanguageTool('ru')

        self.setWindowTitle("Парсер организаций")
        self.setGeometry(100, 100, 800, 700)
        self.widget_ui()

    def parse_excel_data(self):
        raw_data_column = self.get_raw_data_from_column()
        convert_time_start = time.time()
        processed_data_column = self.convert_names_for_parse(raw_data_column)
        convert_time_end = time.time()
        convert_time_result = round(convert_time_end - convert_time_start, 2)
        self.add_log(f"⏱ Преобразование слов заняло: {convert_time_result} с")

        self.start_parsing(processed_data_column)

    def get_raw_data_from_column(self):
        try:
            column_index = self.df.columns.get_loc("Образовательное учреждение из 1С")
            column_data = self.df.iloc[0:, column_index].dropna()
            return column_data.tolist()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f'Не удалось получить данные из файла: {str(e)}')
            return []

    def convert_names_for_parse(self, raw_data_column):
        def create_correct_spelling(word):
            result_queue = Queue()

            def check_word():
                try:
                    matches = self.tool.check(word)
                    corrected_word = self.tool.correct(word) if matches else word
                    result_queue.put(corrected_word)
                except Exception as e:
                    result_queue.put(word)

            thread = threading.Thread(target=check_word)
            thread.start()
            thread.join(timeout=10.0)
            if thread.is_alive():
                thread.join()
                return word
            return result_queue.get()

        def remove_geo_mentions(text):
            return re.sub(r'(.*)".*$', r'\1"', text)

        def clean_text(text):
            quoted_parts = re.findall(r'"(.*?)"', text)
            temp_text = text
            for part in quoted_parts:
                temp_text = re.sub(rf'"{re.escape(part)}"', '', temp_text)
            words = temp_text.split()
            cleaned_words = [w if w.isupper() else w.lower() for w in words]
            cleaned_text = ' '.join(cleaned_words).strip()
            if cleaned_text:
                cleaned_text = cleaned_text[0].upper() + cleaned_text[1:]
            for part in quoted_parts:
                insert_pos = text.find(f'"{part}"')
                if insert_pos != -1:
                    cleaned_text = cleaned_text[:insert_pos] + f'"{part}"' + cleaned_text[insert_pos:]
            corrected_words = [create_correct_spelling(w) for w in cleaned_text.split()]
            return " ".join(corrected_words)

        result = []
        for company_name in raw_data_column:
            company_name = remove_geo_mentions(company_name)
            company_name = clean_text(company_name)
            result.append(company_name)
        return result

    def widget_ui(self):
        main_layout = QVBoxLayout()

        self.label = QLabel(
            "📁 Перетащите Excel файл сюда\nили", alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.label.setStyleSheet(
            """
            border: 2px dashed #2196F3; 
            padding: 30px; 
            font-size: 16px;
            background-color: #E3F2FD;
            border-radius: 10px;
        """
        )
        self.label.setAcceptDrops(True)
        self.label.dragEnterEvent = self.drag_enter_event
        self.label.dropEvent = self.drop_event

        browse_file_button = QPushButton("📂 Выбрать файл")
        browse_file_button.clicked.connect(self.browse_file)
        browse_file_button.setStyleSheet(
            """
            padding: 12px; 
            font-size: 14px;
            background-color: #2196F3;
            color: white;
            border: none;
            border-radius: 5px;
        """
        )
        browse_file_button.setCursor(Qt.CursorShape.PointingHandCursor)

        # Настройки GigaChat
        gigachat_layout = QHBoxLayout()
        self.gigachat_checkbox = QCheckBox("🤖 Использовать GigaChat")
        self.gigachat_checkbox.setChecked(False)
        self.gigachat_checkbox.setStyleSheet("font-size: 12px; padding: 5px;")

        gigachat_layout.addWidget(self.gigachat_checkbox)
        gigachat_layout.addWidget(QLabel("Попыток:"))

        self.gigachat_retries = QSpinBox()
        self.gigachat_retries.setMinimum(1)
        self.gigachat_retries.setMaximum(5)
        self.gigachat_retries.setValue(3)
        self.gigachat_retries.setStyleSheet("padding: 5px;")
        gigachat_layout.addWidget(self.gigachat_retries)
        gigachat_layout.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                border: 2px solid #2196F3;
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """
        )

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            """
            font-family: 'Consolas', 'Monaco', monospace; 
            font-size: 11px;
            background-color: #1E1E1E;
            color: #D4D4D4;
            border: 1px solid #333;
            padding: 10px;
            """
        )

        info_label = QLabel(
            "⚡ Приоритет: RusProfile → Контур Фокус → ЕГРЮЛ → GigaChat"
        )
        info_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")

        main_layout.addWidget(self.label)
        main_layout.addWidget(browse_file_button)
        main_layout.addLayout(gigachat_layout)
        main_layout.addWidget(info_label)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(QLabel("📊 Лог обработки:"))
        main_layout.addWidget(self.log_text)

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
                self.process_file(file_path)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл", "", "Excel-файлы (*.xlsx *.xls)"
        )
        if file_path:
            self.process_file(file_path)

    def check_file_extensions(self, file_path):
        return file_path.endswith((".xlsx", ".xls"))

    def process_file(self, file_path):
        try:
            self.df = pd.read_excel(file_path)
            self.log_text.append(f"✅ Файл загружен: {file_path}")
            self.parse_excel_data()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось обработать файл: {str(e)}")

    def start_parsing(self, data):
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(data))
        self.progress_bar.setValue(0)

        use_gigachat = self.gigachat_checkbox.isChecked()
        retries = self.gigachat_retries.value()

        self.parser_thread = ParserThread(data, self.df.copy(), use_gigachat, retries)
        self.parser_thread.progress.connect(self.update_progress)
        self.parser_thread.log_message.connect(self.add_log)
        self.parser_thread.finished.connect(self.parsing_finished)
        self.parser_thread.start()

    def update_progress(self, current, total):
        self.progress_bar.setValue(current)

    def add_log(self, message):
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def parsing_finished(self, result_df):
        self.df = result_df
        self.add_log("\n" + "=" * 60)
        self.add_log("🎉 Парсинг завершен!")

        found = self.df[self.df["Источник"] != "Не найдено"].shape[0]
        total = self.df.shape[0]
        self.add_log(f"📊 Найдено: {found}/{total} ({round(found/total*100, 1)}%)")

        sources = self.df["Источник"].value_counts()
        self.add_log("\n📈 Статистика по источникам:")
        for source, count in sources.items():
            self.add_log(f"  • {source}: {count}")

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить результат", "", "Excel-файлы (*.xlsx)"
        )

        if save_path:
            try:
                self.df.to_excel(save_path, index=False)
                QMessageBox.information(
                    self,
                    "✅ Успех",
                    f"Результаты сохранены!\n\n📊 Найдено: {found}/{total}\n📁 {save_path}",
                )
                self.add_log(f"✅ Файл сохранен: {save_path}")
            except Exception as e:
                QMessageBox.warning(
                    self, "Ошибка", f"Не удалось сохранить файл: {str(e)}"
                )

        self.progress_bar.setVisible(False)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    window = FillExcelColumns()
    window.show()
    sys.exit(app.exec())
