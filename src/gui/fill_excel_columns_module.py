"""
Главный модуль для парсинга организаций из Excel
"""

import pandas as pd
import time
import os
from dotenv import load_dotenv
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

from .text_processor import TextProcessor
from .parser_core import OrganizationParser

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
        self.use_gigachat = use_gigachat
        self.gigachat_retries = gigachat_retries
        self.gigachat_api = None
        self.parser = None

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
            # Инициализируем парсер БЕЗ GigaChat для основного поиска
            self.parser = OrganizationParser(
                log_callback=self.emit_log,
                use_gigachat=False,  # Сначала без GigaChat
                gigachat_api=None,
                gigachat_retries=0,
            )

            self.parser.init_browser()

            # Инициализируем колонки пустыми значениями
            self.df["Полное название"] = ""
            self.df["Адрес"] = ""
            self.df["Индекс"] = ""
            self.df["ИНН"] = ""
            self.df["ОГРН"] = ""
            self.df["Источник"] = ""
            
            # Получаем индексы строк, для которых есть данные
            data_indices = self.df.index[:len(self.data)].tolist()
            
            # Список ненайденных организаций для обработки через GigaChat
            not_found_items = []
            
            # Основной цикл поиска (без GigaChat)
            for idx, (row_idx, org_name) in enumerate(zip(data_indices, self.data), 1):
                self.progress.emit(idx, len(self.data))
                self.log_message.emit(f"\n{'='*60}")
                self.log_message.emit(f"📋 [{idx}/{len(self.data)}] {org_name}")

                result = self.parser.search_organization(org_name)
                
                self.df.at[row_idx, "Полное название"] = result.get("name", "")
                self.df.at[row_idx, "Адрес"] = result.get("address", "")
                self.df.at[row_idx, "Индекс"] = result.get("postal_code", "")
                self.df.at[row_idx, "ИНН"] = result.get("inn", "")
                self.df.at[row_idx, "ОГРН"] = result.get("ogrn", "")
                self.df.at[row_idx, "Источник"] = result.get("source", "Не найдено")
                
                # Сохраняем ненайденные для обработки через GigaChat
                if result.get("source") == "Не найдено":
                    not_found_items.append((row_idx, org_name))
            
            # Если включен GigaChat и есть ненайденные организации
            if self.use_gigachat and self.gigachat_api and not_found_items:
                self.log_message.emit(f"\n{'='*60}")
                self.log_message.emit(f"🤖 GigaChat: обработка {len(not_found_items)} ненайденных организаций")
                self.log_message.emit(f"📊 Всего попыток: {self.gigachat_retries} (на все организации)")
                self.log_message.emit(f"{'='*60}")
                
                # Подключаем GigaChat к парсеру
                self.parser.gigachat_api = self.gigachat_api
                self.parser.use_gigachat = True
                
                # Обрабатываем ненайденные через GigaChat с ограничением попыток на все организации
                items_to_process = not_found_items.copy()
                gigachat_attempts_used = 0
                found_count = 0
                
                for row_idx, org_name in items_to_process:
                    if gigachat_attempts_used >= self.gigachat_retries:
                        self.log_message.emit(f"\n⚠️ Достигнут лимит попыток GigaChat ({self.gigachat_retries})")
                        self.log_message.emit(f"📊 Найдено через GigaChat: {found_count} из {len(not_found_items)}")
                        break
                    
                    self.log_message.emit(f"\n  📋 [{gigachat_attempts_used + 1}/{self.gigachat_retries}] {org_name}")
                    gigachat_result = self.parser.search_with_gigachat(org_name)
                    gigachat_attempts_used += 1
                    
                    if gigachat_result["found"]:
                        self.df.at[row_idx, "Полное название"] = gigachat_result.get("name", "")
                        self.df.at[row_idx, "Адрес"] = gigachat_result.get("address", "")
                        self.df.at[row_idx, "Индекс"] = gigachat_result.get("postal_code", "")
                        self.df.at[row_idx, "ИНН"] = gigachat_result.get("inn", "")
                        self.df.at[row_idx, "ОГРН"] = gigachat_result.get("ogrn", "")
                        source = gigachat_result.get("source", "GigaChat")
                        if not source or source == "Не найдено":
                            source = "GigaChat"
                        self.df.at[row_idx, "Источник"] = source
                        found_count += 1
                        self.log_message.emit(f"  ✅ Найдено через GigaChat!")
                
                if gigachat_attempts_used < self.gigachat_retries:
                    self.log_message.emit(f"\n📊 Найдено через GigaChat: {found_count} из {len(not_found_items)}")
                else:
                    self.log_message.emit(f"\n📊 Обработано через GigaChat: {found_count} из {len(not_found_items)} (лимит попыток достигнут)")

            self.finished.emit(self.df)

        except Exception as e:
            self.log_message.emit(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")

        finally:
            if self.parser:
                self.parser.close_browser()

    def emit_log(self, message):
        """Передача сообщения в главный поток"""
        self.log_message.emit(message)


class FillExcelColumns(QWidget):
    """Главное окно приложения"""

    def __init__(self):
        super().__init__()
        self.df = None
        self.parser_thread = None
        self.text_processor = None
        self.file_loaded = False

        self.setWindowTitle("Парсер организаций")
        self.setGeometry(100, 100, 900, 750)
        self.widget_ui()

    def widget_ui(self):
        """Инициализация интерфейса"""
        main_layout = QVBoxLayout()

        # Зона для перетаскивания файлов
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

        # Кнопка выбора файла
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
        
        # Кнопка запуска парсинга
        self.start_parse_button = QPushButton("🚀 Начать парсинг")
        self.start_parse_button.clicked.connect(self.start_parsing_clicked)
        self.start_parse_button.setStyleSheet(
            """
            padding: 15px; 
            font-size: 16px;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 5px;
            font-weight: bold;
        """
        )
        self.start_parse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_parse_button.setEnabled(False)  # Неактивна до загрузки файла

        # Настройки GigaChat
        gigachat_layout = QHBoxLayout()
        self.gigachat_checkbox = QCheckBox("🤖 Использовать GigaChat")
        self.gigachat_checkbox.setChecked(False)
        self.gigachat_checkbox.setStyleSheet("font-size: 12px; padding: 5px;")
        self.gigachat_checkbox.setEnabled(False)  # Неактивна до загрузки файла

        gigachat_layout.addWidget(self.gigachat_checkbox)
        gigachat_layout.addWidget(QLabel("Попыток (на все ненайденные):"))

        self.gigachat_retries = QSpinBox()
        self.gigachat_retries.setMinimum(1)
        self.gigachat_retries.setMaximum(5)
        self.gigachat_retries.setValue(3)
        self.gigachat_retries.setStyleSheet("padding: 5px;")
        self.gigachat_retries.setEnabled(False)  # Неактивен до загрузки файла
        gigachat_layout.addWidget(self.gigachat_retries)
        gigachat_layout.addStretch()

        # Прогресс бар
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

        # Лог
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

        # Информация
        info_label = QLabel(
            "⚡ Приоритет: RusProfile → Контур Фокус → ЕГРЮЛ → GigaChat"
        )
        info_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")

        # Сборка интерфейса
        main_layout.addWidget(self.label)
        main_layout.addWidget(browse_file_button)
        main_layout.addWidget(self.start_parse_button)
        main_layout.addLayout(gigachat_layout)
        main_layout.addWidget(info_label)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(QLabel("📊 Лог обработки:"))
        main_layout.addWidget(self.log_text)

        self.setLayout(main_layout)

    def drag_enter_event(self, event):
        """Обработка начала перетаскивания"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def drop_event(self, event):
        """Обработка завершения перетаскивания"""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if not self.check_file_extensions(file_path):
                QMessageBox.warning(self, "Ошибка", "Неподдерживаемый тип файла!")
            else:
                self.process_file(file_path)

    def browse_file(self):
        """Выбор файла через диалог"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл", "", "Excel-файлы (*.xlsx *.xls)"
        )
        if file_path:
            self.process_file(file_path)

    def check_file_extensions(self, file_path):
        """Проверка расширения файла"""
        return file_path.endswith((".xlsx", ".xls"))

    def process_file(self, file_path):
        """Загрузка выбранного файла"""
        try:
            self.df = pd.read_excel(file_path)
            self.file_loaded = True
            self.add_log(f"✅ Файл загружен: {file_path}")
            self.add_log(f"📊 Строк в файле: {len(self.df)}")
            # Активируем кнопку запуска и настройки
            self.start_parse_button.setEnabled(True)
            self.gigachat_checkbox.setEnabled(True)
            self.gigachat_retries.setEnabled(True)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить файл: {str(e)}")
            self.file_loaded = False
            self.start_parse_button.setEnabled(False)

    def parse_excel_data(self):
        """Парсинг данных из Excel"""
        raw_data_column = self.get_raw_data_from_column()

        # Создаем процессор текста с callback для логов
        self.text_processor = TextProcessor(log_callback=self.add_log)

        self.add_log("\n🔧 ЭТАП 1: Нормализация названий")
        self.add_log("=" * 60)

        convert_time_start = time.time()
        processed_data_column = self.text_processor.convert_names_for_parse(
            raw_data_column
        )
        convert_time_end = time.time()
        convert_time_result = round(convert_time_end - convert_time_start, 2)

        self.add_log(f"\n⏱ Нормализация заняла: {convert_time_result} с")
        self.add_log("\n🌐 ЭТАП 2: Поиск в базах данных")
        self.add_log("=" * 60)

        self.start_parsing(processed_data_column)

    def get_raw_data_from_column(self):
        """Получение данных из столбца Excel"""
        try:
            column_index = self.df.columns.get_loc("Образовательное учреждение из 1С")
            column_data = self.df.iloc[0:, column_index].dropna()
            return column_data.tolist()
        except Exception as e:
            QMessageBox.warning(
                self, "Ошибка", f"Не удалось получить данные из файла: {str(e)}"
            )
            return []

    def start_parsing_clicked(self):
        """Обработка нажатия кнопки запуска парсинга"""
        if not self.file_loaded or self.df is None:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите файл!")
            return
        
        # Блокируем кнопки на время парсинга
        self.start_parse_button.setEnabled(False)
        self.gigachat_checkbox.setEnabled(False)
        self.gigachat_retries.setEnabled(False)
        
        self.parse_excel_data()

    def start_parsing(self, data):
        """Запуск парсинга в отдельном потоке"""
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
        """Обновление прогресс бара"""
        self.progress_bar.setValue(current)

    def add_log(self, message):
        """Добавление сообщения в лог"""
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def parsing_finished(self, result_df):
        """Завершение парсинга"""
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
        
        # Разблокируем кнопки после завершения
        self.start_parse_button.setEnabled(True)
        self.gigachat_checkbox.setEnabled(True)
        self.gigachat_retries.setEnabled(True)

        # Закрываем процессор текста
        if self.text_processor:
            self.text_processor.close()


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    window = FillExcelColumns()
    window.show()
    sys.exit(app.exec())
