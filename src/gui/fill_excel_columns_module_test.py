"""
Модуль для нормализации названий образовательных учреждений
через RusProfile и GigaChat API
"""

import pandas as pd
import time
import re
from selenium import webdriver as wd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup as BS
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QMessageBox, QSpinBox, QProgressBar, QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal

# Импортируем GigaChat API
from gigachat_api import GigaChatAPI


class NameNormalizer:
    """Класс для нормализации названий организаций"""

    @staticmethod
    def clean_name(name):
        """Базовая очистка названия от лишних символов"""
        if pd.isna(name):
            return ""

        name = str(name).strip()
        # Убираем множественные пробелы
        name = re.sub(r'\s+', ' ', name)
        # Убираем географические метки в конце
        name = re.sub(r'\s+(г\.о\.|обл\.|г\.|пос\.|с\.).*$', '', name, flags=re.IGNORECASE)
        return name

    @staticmethod
    def generate_search_variants(name):
        """Генерация вариантов поиска для RusProfile"""
        variants = []
        base_name = NameNormalizer.clean_name(name)

        # Вариант 1: Исходное название (очищенное)
        variants.append(base_name)

        # Вариант 2: Без пробелов после №
        variant2 = re.sub(r'№\s+', '№', base_name)
        if variant2 != base_name:
            variants.append(variant2)

        # Вариант 3: С пробелом после № (если был без)
        variant3 = re.sub(r'№(\d)', r'№ \1', base_name)
        if variant3 != base_name and variant3 not in variants:
            variants.append(variant3)

        # Вариант 4: Исправление дублирования букв (шкоола -> школа, Праавославная -> Православная)
        variant4 = re.sub(r'([аоуыэяёюиеАОУЫЭЯЁЮИЕ])\1+', r'\1', base_name)
        if variant4 != base_name:
            variants.append(variant4)

        # Вариант 5: Замена похожих символов (0→О, l→I)
        variant5 = base_name.replace('0', 'О').replace('l', 'I')
        if variant5 != base_name:
            variants.append(variant5)

        # Вариант 6: Без кавычек всех типов
        variant6 = re.sub(r'["\'"«»]', '', base_name)
        if variant6 != base_name:
            variants.append(variant6)

        # Вариант 7: Сокращенное название (только ключевые слова)
        # Извлекаем номер и ключевое слово (школа, гимназия, лицей, колледж)
        match = re.search(r'(школа|гимназия|лицей|колледж|техникум)\s*["\'"«»]?(.+?)["\'"«»]?(?:\s|$)',
                         base_name, re.IGNORECASE)
        if match:
            key_part = match.group(0).strip()
            variants.append(key_part)

        # Вариант 8: Только аббревиатура + номер/название
        abbr_match = re.match(r'^([А-ЯA-Z]{3,})\s*["\'"«»]?(.+)', base_name)
        if abbr_match:
            variants.append(f"{abbr_match.group(1)} {abbr_match.group(2)}")

        # Убираем дубликаты, сохраняя порядок
        seen = set()
        unique_variants = []
        for v in variants:
            v_clean = v.strip()
            if v_clean and v_clean not in seen and len(v_clean) > 3:
                seen.add(v_clean)
                unique_variants.append(v_clean)

        return unique_variants[:8]  # Ограничиваем 8 вариантами для скорости


class ProcessingThread(QThread):
    """Поток для обработки данных"""

    progress = Signal(int)
    status = Signal(str)
    finished = Signal(pd.DataFrame)
    error = Signal(str)

    def __init__(self, df, column_name, max_gigachat_requests, use_gigachat, gigachat_api):
        super().__init__()
        self.df = df
        self.column_name = column_name
        self.max_gigachat_requests = max_gigachat_requests
        self.use_gigachat = use_gigachat
        self.gigachat_api = gigachat_api
        self.is_running = True

    def run(self):
        try:
            results = []
            gigachat_count = 0
            total = len(self.df)

            for idx, row in self.df.iterrows():
                if not self.is_running:
                    break

                original_name = row[self.column_name]
                self.status.emit(f"Обработка: {original_name}")

                # Поиск в RusProfile
                found_name = self.search_rusprofile(original_name)

                if found_name:
                    results.append({
                        'Исходное название': original_name,
                        'Нормализованное название': found_name,
                        'Источник': 'RusProfile'
                    })
                else:
                    # Если не найдено в RusProfile и включен GigaChat
                    if self.use_gigachat and gigachat_count < self.max_gigachat_requests:
                        self.status.emit(f"GigaChat ({gigachat_count + 1}/{self.max_gigachat_requests}): {original_name}")
                        normalized = self.gigachat_api.normalize_school_name(original_name)
                        gigachat_count += 1

                        results.append({
                            'Исходное название': original_name,
                            'Нормализованное название': normalized,
                            'Источник': 'GigaChat'
                        })
                    else:
                        results.append({
                            'Исходное название': original_name,
                            'Нормализованное название': original_name,
                            'Источник': 'Не обработано'
                        })

                self.progress.emit(int((idx + 1) / total * 100))
                time.sleep(0.5)  # Небольшая задержка между запросами

            result_df = pd.DataFrame(results)
            self.finished.emit(result_df)

        except Exception as e:
            self.error.emit(str(e))

    def search_rusprofile(self, name):
        """Поиск в RusProfile с различными вариантами - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        variants = NameNormalizer.generate_search_variants(name)

        browser = None
        try:
            chrome_options = wd.ChromeOptions()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

            browser = wd.Chrome(options=chrome_options)
            browser.implicitly_wait(3)

            for i, variant in enumerate(variants):
                if not self.is_running:
                    break

                try:
                    self.status.emit(f"🔍 RusProfile [{i+1}/{len(variants)}]: {variant[:40]}...")

                    # Формируем URL с параметрами поиска
                    search_url = f"https://www.rusprofile.ru/search?query={variant}&type=ul"
                    browser.get(search_url)

                    # Ждем загрузки
                    time.sleep(2)

                    # Парсим через BeautifulSoup
                    soup = BS(browser.page_source, 'html.parser')

                    # Проверяем, есть ли сообщение "не найдено"
                    no_results = soup.find(text=re.compile(r'(ничего не найдено|не найдено компаний|нет результатов)', re.I))
                    if no_results:
                        continue  # Переходим к следующему варианту

                    # КРИТИЧНО: Ищем ТОЛЬКО в блоке результатов поиска
                    search_results_block = soup.find('div', id='search-results')
                    if not search_results_block:
                        search_results_block = soup.find('div', class_='search-results')

                    if not search_results_block:
                        # Если блока результатов нет вообще - пропускаем
                        self.status.emit(f"⚠ Блок результатов не найден")
                        continue

                    # Ищем элементы company-item ТОЛЬКО в блоке результатов
                    company_items = search_results_block.find_all('div', class_='company-item', limit=5)

                    if company_items:
                        # Берем первый результат (лучшее совпадение)
                        first_item = company_items[0]

                        # Ищем название
                        title_link = first_item.find('a', class_='company-item__title')
                        if not title_link:
                            title_div = first_item.find('div', class_='company-item__title')
                            if title_div:
                                title_link = title_div.find('a')

                        if title_link:
                            found_name = title_link.get_text(strip=True)
                            href = title_link.get('href', '')

                            # Проверяем что это реальная ссылка на компанию
                            if found_name and len(found_name) > 10 and '/id/' in href:
                                self.status.emit(f"✓ Найдено: {found_name[:40]}...")
                                browser.quit()
                                return found_name

                    # Небольшая задержка между вариантами
                    time.sleep(1)
                    
                except Exception as e:
                    self.status.emit(f"✗ Вариант {i+1}: {str(e)[:30]}")
                    continue
            
            browser.quit()
            self.status.emit("✗ Не найдено в RusProfile")
            return None
            
        except Exception as e:
            self.status.emit(f"✗ Ошибка RusProfile: {str(e)[:50]}")
            if browser:
                try:
                    browser.quit()
                except:
                    pass
            return None
    
    def stop(self):
        self.is_running = False


class FillExcelColumns(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Нормализация названий ОУ")
        self.setGeometry(100, 100, 700, 500)
        self.df = None
        self.processing_thread = None
        
        # Инициализация GigaChat API
        AUTH_TOKEN = "MDE5OWI5MWUtNWYyYy03YTA4LWFjOTgtYzVjZWY5ZTk5MDMwOmM2YTM1OTlmLTU2NWYtNDU2OS1hZjY0LTNiMTgwOWZjYzA5MA=="
        self.gigachat_api = GigaChatAPI(AUTH_TOKEN)
        
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
        if self.gigachat_api.test_connection():
            self.log("✓ GigaChat подключен успешно")
        else:
            self.log("✗ Ошибка подключения к GigaChat")

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
                self.load_file(file_path)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите файл", "", "Excel-файлы (*.xlsx *.xls)")
        if file_path:
            self.load_file(file_path)

    def check_file_extensions(self, file_path):
        return file_path.endswith(('.xlsx', '.xls'))

    def load_file(self, file_path):
        try:
            self.df = pd.read_excel(file_path)
            
            # Проверяем наличие нужного столбца
            if "Образовательное учреждение из 1С" not in self.df.columns:
                QMessageBox.warning(self, "Ошибка", 'Столбец "Образовательное учреждение из 1С" не найден!')
                return
            
            self.log(f"✓ Загружено {len(self.df)} записей из файла")
            self.log(f"Столбец: 'Образовательное учреждение из 1С'")
            self.process_button.setEnabled(True)
            self.label.setText(f"Файл загружен: {len(self.df)} записей")
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f'Не удалось загрузить файл: {str(e)}')

    def start_processing(self):
        if self.df is None:
            return
        
        self.process_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log("\n=== Начало обработки ===")
        
        self.processing_thread = ProcessingThread(
            self.df,
            "Образовательное учреждение из 1С",
            self.max_requests_spinbox.value(),
            self.use_gigachat_checkbox.isChecked(),
            self.gigachat_api
        )
        
        self.processing_thread.progress.connect(self.update_progress)
        self.processing_thread.status.connect(self.log)
        self.processing_thread.finished.connect(self.processing_finished)
        self.processing_thread.error.connect(self.processing_error)
        
        self.processing_thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def log(self, message):
        self.log_text.append(message)

    def processing_finished(self, result_df):
        self.result_df = result_df
        self.log("\n=== Обработка завершена ===")
        self.log(f"Всего обработано: {len(result_df)}")
        self.log(f"Найдено в RusProfile: {len(result_df[result_df['Источник'] == 'RusProfile'])}")
        self.log(f"Обработано GigaChat: {len(result_df[result_df['Источник'] == 'GigaChat'])}")
        self.log(f"Не обработано: {len(result_df[result_df['Источник'] == 'Не обработано'])}")
        
        self.process_button.setEnabled(True)
        self.save_button.setEnabled(True)

    def processing_error(self, error_message):
        self.log(f"\n✗ ОШИБКА: {error_message}")
        self.process_button.setEnabled(True)
        QMessageBox.critical(self, "Ошибка", f"Ошибка обработки: {error_message}")

    def save_results(self):
        if not hasattr(self, 'result_df'):
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить результат", "результат_нормализации.xlsx", "Excel-файлы (*.xlsx)"
        )
        
        if file_path:
            try:
                self.result_df.to_excel(file_path, index=False)
                self.log(f"✓ Результат сохранен: {file_path}")
                QMessageBox.information(self, "Успех", "Результат успешно сохранен!")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл: {str(e)}")