import re
import time
import json
import os
import language_tool_python
import pandas as pd
from pymorphy3 import MorphAnalyzer as MA
from bs4 import BeautifulSoup as BS
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox,
    QSpinBox, QProgressBar, QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt
import requests
from urllib.parse import quote

from .gigachat_api import GigaChatAPI
from .validate_rusprofile import is_valid_match

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

        # Результаты парсинга
        self.parsed_results = []
        
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
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f'Не удалось обработать файл: {str(e)}')

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
            matches = tool.check(word)
            if matches:
                corrected_word = tool.correct(word)
            else:
                corrected_word = word
            return corrected_word

        def remove_geo_mentions(text):
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

            return cleaned_text

        result = []
        for company_name in raw_data_column:
            company_name = remove_geo_mentions(company_name)
            company_name = clean_text(company_name)
            result.append(company_name)

        return result

    def parse_data(self, our_parse_data):
        """Улучшенный парсинг с более надежным поиском"""
        main_url = "https://www.rusprofile.ru"
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        })
        
        total = len(our_parse_data)
        found_count = 0
        not_found_count = 0
        
        for idx, data_element in enumerate(our_parse_data, 1):
            self.log(f"\n[{idx}/{total}] Поиск: {data_element}")
            self.progress_bar.setValue(int(idx / total * 100))
            
            search_url = f"{main_url}/search?query={quote(data_element)}&type=ul"
            
            try:
                response = session.get(search_url, timeout=15)
                response.raise_for_status()
                time.sleep(1.5)
                
                soup = BS(response.content, "html.parser")
                result_found = False
            
                id_links = soup.find_all('a', href=re.compile(r'^/id/\d+$'))
                if id_links:
                    result_url = main_url + id_links[0]['href']
                    company_data = self.parse_full_company_name(session, result_url)
                    if company_data:
                        self.parsed_results.append(company_data)
                        found_count += 1
                        result_found = True
                        self.log(f"  ✓ Найдено: {company_data.get('Название организации:', '')}")
                    time.sleep(1.5)
                
                if not result_found:
                    not_found_count += 1
                    self.log(f"  ✗ Не найдено")
                    self.parsed_results.append({
                        "Название организации:": "НЕ НАЙДЕНО",
                        "Название организации в род падеже:": "",
                        "Адрес организации:": "",
                        "Индекс:": ""
                    })
                        
            except Exception as e:
                not_found_count += 1
                self.log(f"  ✗ Ошибка: {str(e)}")
                self.parsed_results.append({
                    "Название организации:": "ОШИБКА",
                    "Название организации в род падеже:": "",
                    "Адрес организации:": "",
                    "Индекс:": ""
                })
                
            time.sleep(2)
        
        self.log(f"Парсинг завершен!")
        self.log(f"Найдено: {found_count} ({found_count/total*100:.1f}%)")
        self.log(f"Не найдено: {not_found_count} ({not_found_count/total*100:.1f}%)")

    def parse_full_company_name(self, session, result_url):
        try:
            response = session.get(result_url, timeout=15)
            response.raise_for_status()
            time.sleep(1.5)
            
            soup = BS(response.content, 'html.parser')
            
            company_info = {}
            
            # название - несколько методов
            full_name = soup.find('h1', class_='company-header__title')
            if not full_name:
                full_name = soup.find('div', class_='company-header__title')
            if not full_name:
                full_name = soup.find('h1')
            
            if full_name:
                name = full_name.get_text(strip=True)
                company_info["Название организации:"] = name
            else:
                return None
            
            address = ""
            address_index = None
            
            # ищем блок с адресом
            address_section = soup.find('div', class_='company-info__text', string=re.compile(r'Адрес'))
            if address_section:
                address_value = address_section.find_next_sibling('div', class_='company-info__text')
                if address_value:
                    address = address_value.get_text(strip=True)
            
            # если не нашли в блоке, ищем по паттерну в тексте
            if not address:
                text_content = soup.get_text()
                # ищем адрес до ключевых слов (Руководитель, Среднесписочная и т.д.)
                addr_match = re.search(
                    r'(\d{6}[,\s]+[^\.]+?(?:область|край|республика|город|улица|ул\.|д\.|дом|проспект|пр-кт)[^\.]{0,100}?(?=\s+(?:Еще|Руководитель|Среднесписочная|Специальный|\d{6}|$)))',
                    text_content,
                    re.IGNORECASE
                )
                if addr_match:
                    address = addr_match.group(1).strip()
                    # очищаем от мусора
                    address = re.sub(r'\s+', ' ', address)
                    address = re.split(r'(?=Еще\s+\d+\s+организаци)', address)[0].strip()
            
            # извлекаем индекс
            if address:
                idx_match = re.search(r'\b(\d{6})\b', address)
                if idx_match:
                    address_index = idx_match.group(1)
            
            company_info["Адрес организации:"] = address
            company_info["Индекс:"] = address_index
            
            # оодительный падеж
            rod_name = ""
            # rod_name = self.generate_genitive_case(name)
            company_info["Название организации в род падеже:"] = rod_name
            
            return company_info
            
        except Exception as e:
            print(f"Ошибка при парсинге страницы {result_url}: {str(e)}")
            return None

    # def generate_genitive_case(self, name):
        # добавить код


    def log(self, message):
        self.log_text.append(message)

    def start_processing(self):
        if not hasattr(self, 'df') or self.df is None:
            self.log("Ошибка: файл не загружен")
            return

        self.log("\n=== Начало обработки ===")
        self.process_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.parsed_results = []

        try:
            # извлекаем данные
            raw_data = self.analyze_file()
            self.log(f"Извлечено {len(raw_data)} записей")
            
            # предобработка
            processed_data = self.convert_name_for_parse(raw_data)
            self.log("Предобработка завершена")
            
            # парсинг
            self.parse_data(processed_data)
            
            # формируем результирующий DataFrame
            self.result_df = self._create_result_dataframe()
            
            self.progress_bar.setValue(100)
            self.processing_finished()
            
        except Exception as e:
            self.log(f"✗ Ошибка обработки: {str(e)}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка обработки: {str(e)}")

    def _expand_abbreviations(self, text):
        if not isinstance(text, str):
            return text

        path = os.path.join(os.path.dirname(__file__), 'resources', 'abbreviations.json')
        with open(path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)

        for abbr, full in mapping.items():
            pattern_start = rf'^\s*{abbr}\b'
            if re.search(pattern_start, text, flags=re.IGNORECASE):
                text = re.sub(pattern_start, full, text, flags=re.IGNORECASE)
                break

        for abbr, full in mapping.items():
            pattern_inside = rf'\b{abbr}\b'
            text = re.sub(pattern_inside, full, text, flags=re.IGNORECASE)

        return text

    def _normalize_locally(self, name):
        """Локальная нормализация без GigaChat"""
        if not isinstance(name, str):
            return name

        name = name.strip()
        
        # Сначала расшифровываем аббревиатуры
        name = self._expand_abbreviations(name)

        # Сохраняем содержимое кавычек без изменения
        # Ищем текст в кавычках (любых)
        quoted_parts = []
        quote_pattern = r'[«""]([^»""]+)[»""]'
        
        def save_quoted(match):
            quoted_parts.append(match.group(1))
            return f'<<<QUOTE{len(quoted_parts)-1}>>>'
        
        temp_name = re.sub(quote_pattern, save_quoted, name)
        
        # Приводим к Title Case (каждое слово с заглавной)
        words = temp_name.split()
        cap_words = []
        for w in words:
            # Пропускаем наши заглушки
            if w.startswith('<<<QUOTE'):
                cap_words.append(w)
            # Аббревиатуры оставляем как есть
            elif w.isupper() and len(w) <= 6:
                cap_words.append(w)
            # Слова через дефис
            elif '-' in w:
                cap_words.append('-'.join(seg.capitalize() for seg in w.split('-')))
            else:
                cap_words.append(w.capitalize())
        
        result = ' '.join(cap_words)
        
        # Возвращаем кавычки обратно как «ёлочки»
        for i, quoted_text in enumerate(quoted_parts):
            result = result.replace(f'<<<QUOTE{i}>>>', f'«{quoted_text}»')
        
        # Убираем пробел после №
        result = re.sub(r'№\s+(\d)', r'№\1', result)
        
        # Сжимаем множественные пробелы
        result = re.sub(r'\s+', ' ', result).strip()
        
        return result

    def _create_result_dataframe(self):
        """Создает итоговый DataFrame с результатами"""
        results = []
        use_giga = self.use_gigachat_checkbox.isChecked() and self.gigachat_api is not None
        max_reqs = self.max_requests_spinbox.value()
        used_reqs = 0

        for idx, row in self.df.iterrows():
            original_name = row.get(EXCEL_COLUMN_NAME)
            
            # Данные из парсинга
            if idx < len(self.parsed_results):
                parsed = self.parsed_results[idx]
                parsed_name = parsed.get("Название организации:", "")
                
                # Если найдено в RusProfile - используем с нормализацией
                if parsed_name and parsed_name not in ["НЕ НАЙДЕНО", "ОШИБКА"]:
                    if not is_valid_match(str(original_name), parsed_name, parsed.get("Адрес организации:", "")):
                        self.log(f"Отбраковано: {parsed_name}")
                        parsed_name = "" # заглушка

                    # Нормализуем название из RusProfile
                    normalized = self._normalize_locally(parsed_name)
                    source = "RusProfile"
                    
                    results.append({
                        'Исходное название': original_name,
                        'Нормализованное название': normalized,
                        'Родительный падеж': parsed.get("Название организации в род падеже:", ""),
                        'Адрес': parsed.get("Адрес организации:", ""),
                        'Индекс': parsed.get("Индекс:", ""),
                        'Источник': source,
                    })
                    continue
            
            # Если не найдено в RusProfile - пробуем GigaChat
            normalized = None
            rod_padezh = ""
            source = 'Локально'

            if use_giga and used_reqs < max_reqs:
                try:
                    self.log(f"  → Использую GigaChat ({used_reqs+1}/{max_reqs})...")
                    normalized = self.gigachat_api.normalize_school_name(str(original_name))
                    
                    if normalized and normalized != 'Ошибка':
                        source = 'GigaChat'
                        used_reqs += 1
                        # Генерируем родительный падеж для результата GigaChat
                        # rod_padezh = self.generate_genitive_case(normalized)
                        self.log(f"  ✓ GigaChat: {normalized}")
                    else:
                        self.log(f"  ✗ GigaChat вернул ошибку")
                        normalized = None
                        
                except Exception as e:
                    self.log(f"  ✗ Ошибка GigaChat: {str(e)}")
                    normalized = None

        self.log(f"\n=== Статистика GigaChat ===")
        self.log(f"Использовано запросов: {used_reqs}/{max_reqs}")
        
        return pd.DataFrame(results)

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
                if hasattr(self, 'result_df') and self.result_df is not None:
                    self.result_df.to_excel(file_path, index=False)
                    self.log(f"✓ Результат сохранен: {file_path}")
                    QMessageBox.information(self, "Успех", "Результат успешно сохранен!")
                else:
                    self.log("✗ Нет данных для сохранения")
                    QMessageBox.warning(self, "Ошибка", "Нет данных для сохранения!")
            except Exception as e:
                self.log(f"✗ Ошибка сохранения: {str(e)}")
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл: {str(e)}")