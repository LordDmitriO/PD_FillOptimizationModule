"""
Главный модуль для парсинга организаций из Excel
"""

import pandas as pd
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
    QComboBox,
    QGroupBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QFile, QTextStream

from .text_processor_upd import TextProcessor
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

    def __init__(
        self, data, df, use_gigachat=False, gigachat_retries=3, use_recaptcha=False, humanization_mode="normal"
    ):
        super().__init__()
        self.data = data
        self.df = df
        self.use_gigachat = use_gigachat
        self.gigachat_retries = gigachat_retries
        self.use_recaptcha = use_recaptcha  # НОВОЕ
        self.humanization_mode = humanization_mode  # Режим хуманизации
        self.gigachat_api = None
        self.parser = None
        self._stop_requested = False  # Флаг для корректного завершения
        self._paused = False  # Флаг паузы

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
            # Инициализируем парсер
            recaptcha_api_key = os.getenv("RUCAPTCHA_API_KEY")  # Берем из .env

            self.parser = OrganizationParser(
                log_callback=self.emit_log,
                use_gigachat=False,  # Сначала без GigaChat
                gigachat_api=None,
                gigachat_retries=0,
                use_recaptcha_solver=self.use_recaptcha,  # НОВОЕ
                recaptcha_api_key=recaptcha_api_key,  # НОВОЕ
                humanization_mode=self.humanization_mode,  # Режим хуманизации
            )

            self.parser.init_browser()

            # Инициализируем колонки пустыми значениями
            self.df["Полное название"] = ""
            self.df["Родительный падеж"] = ""
            self.df["Адрес"] = ""
            self.df["Индекс"] = ""
            self.df["ИНН"] = ""
            self.df["ОГРН"] = ""
            self.df["Источник"] = ""

            # Получаем индексы строк, для которых есть данные
            data_indices = self.df.index[: len(self.data)].tolist()

            # Список ненайденных организаций для обработки через GigaChat
            not_found_items = []

            # Основной цикл поиска (без GigaChat)
            for idx, (row_idx, org_name) in enumerate(zip(data_indices, self.data), 1):
                # Проверяем флаг остановки
                if self._stop_requested:
                    self.log_message.emit("\n⚠️ Получен запрос на остановку парсинга")
                    break

                # Ожидание снятия паузы
                while self._paused and not self._stop_requested:
                    self.msleep(100)  # Небольшая задержка, чтобы не нагружать CPU

                if self._stop_requested:
                    break

                self.progress.emit(idx, len(self.data))
                self.log_message.emit(f"\n{'='*60}")
                self.log_message.emit(f"📋 [{idx}/{len(self.data)}] {org_name}")

                result = self.parser.search_organization(org_name)

                self.df.at[row_idx, "Полное название"] = result.get("name", "")
                self.df.at[row_idx, "Родительный падеж"] = result.get(
                    "name_genitive", ""
                )
                self.df.at[row_idx, "Адрес"] = result.get("address", "")
                self.df.at[row_idx, "Индекс"] = result.get("postal_code", "")
                self.df.at[row_idx, "ИНН"] = result.get("inn", "")
                self.df.at[row_idx, "ОГРН"] = result.get("ogrn", "")
                self.df.at[row_idx, "Источник"] = result.get("source", "Не найдено")

                # Сохраняем ненайденные для обработки через GigaChat
                if result.get("source") == "Не найдено":
                    not_found_items.append((row_idx, org_name))

            # Если включен GigaChat и есть ненайденные организации
            if not self._stop_requested and self.use_gigachat and self.gigachat_api and not_found_items:
                self.log_message.emit(f"\n{'='*60}")
                self.log_message.emit(
                    f"🤖 GigaChat: обработка {len(not_found_items)} ненайденных организаций"
                )
                self.log_message.emit(
                    f"📊 Всего попыток: {self.gigachat_retries} (на все организации)"
                )
                self.log_message.emit(f"{'='*60}")

                # Подключаем GigaChat к парсеру
                self.parser.gigachat_api = self.gigachat_api
                self.parser.use_gigachat = True

                # Обрабатываем ненайденные через GigaChat с ограничением попыток на все организации
                items_to_process = not_found_items.copy()
                gigachat_attempts_used = 0
                found_count = 0

                for row_idx, org_name in items_to_process:
                    # Проверяем флаг остановки
                    if self._stop_requested:
                        self.log_message.emit("\n⚠️ Получен запрос на остановку парсинга")
                        break

                    if gigachat_attempts_used >= self.gigachat_retries:
                        self.log_message.emit(
                            f"\n⚠️ Достигнут лимит попыток GigaChat ({self.gigachat_retries})"
                        )
                        self.log_message.emit(
                            f"📊 Найдено через GigaChat: {found_count} из {len(not_found_items)}"
                        )
                        break

                    self.log_message.emit(
                        f"\n  📋 [{gigachat_attempts_used + 1}/{self.gigachat_retries}] {org_name}"
                    )
                    gigachat_result = self.parser.search_with_gigachat(org_name)
                    gigachat_attempts_used += 1

                    if gigachat_result["found"]:
                        self.df.at[row_idx, "Полное название"] = gigachat_result.get(
                            "name", ""
                        )
                        self.df.at[row_idx, "Адрес"] = gigachat_result.get(
                            "address", ""
                        )
                        self.df.at[row_idx, "Индекс"] = gigachat_result.get(
                            "postal_code", ""
                        )
                        self.df.at[row_idx, "ИНН"] = gigachat_result.get("inn", "")
                        self.df.at[row_idx, "ОГРН"] = gigachat_result.get("ogrn", "")
                        source = gigachat_result.get("source", "GigaChat")
                        if not source or source == "Не найдено":
                            source = "GigaChat"
                        self.df.at[row_idx, "Источник"] = source
                        found_count += 1
                        self.log_message.emit("  ✅ Найдено через GigaChat!")

                if gigachat_attempts_used < self.gigachat_retries:
                    self.log_message.emit(
                        f"\n📊 Найдено через GigaChat: {found_count} из {len(not_found_items)}"
                    )
                else:
                    self.log_message.emit(
                        f"\n📊 Обработано через GigaChat: {found_count} из {len(not_found_items)} (лимит попыток достигнут)"
                    )

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
        self.is_parsing = False
        self.is_paused = False  # Флаг паузы
        self.current_file_path = None
        self.browse_file_button = None

        self.setWindowTitle("Парсер организаций")
        self.setGeometry(100, 100, 900, 750)

        # Загружаем стили из файла
        self.load_stylesheet()

        self.widget_ui()

    def closeEvent(self, event):
        """Обработка закрытия окна"""
        if self.is_parsing:
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                "Парсинг выполняется. Вы уверены, что хотите закрыть окно?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_parsing()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def load_stylesheet(self):
        """Загрузка стилей из файла styles.qss"""
        try:
            # Пытаемся загрузить из той же директории, что и модуль
            style_path = os.path.join(os.path.dirname(__file__), "styles.qss")

            if not os.path.exists(style_path):
                # Если не найден, пробуем относительный путь
                style_path = "styles.qss"

            style_file = QFile(style_path)
            if style_file.open(QFile.OpenModeFlag.ReadOnly | QFile.OpenModeFlag.Text):
                stream = QTextStream(style_file)
                stylesheet = stream.readAll()
                self.setStyleSheet(stylesheet)
                style_file.close()
            else:
                print(f"⚠️ Не удалось открыть файл стилей: {style_path}")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки стилей: {e}")

    def widget_ui(self):
        """Инициализация интерфейса"""
        main_layout = QVBoxLayout()

        # Зона для перетаскивания файлов
        self.label = QLabel(
            "📁 Перетащите Excel файл сюда\nили", alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.label.setObjectName("dropZoneLabel")
        self.label.setAcceptDrops(True)
        self.label.dragEnterEvent = self.drag_enter_event
        self.label.dropEvent = self.drop_event

        # Информация о загруженном файле
        self.file_info_label = QLabel("Файл не загружен")
        self.file_info_label.setObjectName("fileInfoLabel")
        self.file_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_info_label.setWordWrap(True)

        # Кнопка выбора файла
        self.browse_file_button = QPushButton("📂 Выбрать файл")
        self.browse_file_button.clicked.connect(self.browse_file)
        self.browse_file_button.setObjectName("browseFileButton")
        self.browse_file_button.setCursor(Qt.CursorShape.PointingHandCursor)

        # Кнопки управления парсингом
        buttons_layout = QHBoxLayout()
        self.start_parse_button = QPushButton("🚀 Начать парсинг")
        self.start_parse_button.clicked.connect(self.start_parsing_clicked)
        self.start_parse_button.setObjectName("startParseButton")
        self.start_parse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_parse_button.setEnabled(False)  # Неактивна до загрузки файла

        self.pause_button = QPushButton("⏸ Пауза")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setObjectName("pauseButton")
        self.pause_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_button.setEnabled(False)  # Неактивна до начала парсинга
        self.pause_button.setVisible(False)  # Скрыта до начала парсинга

        buttons_layout.addWidget(self.start_parse_button)
        buttons_layout.addWidget(self.pause_button)
        buttons_layout.addStretch()

        # Группа настроек парсинга
        settings_group = QGroupBox("⚙️ Настройки парсинга")
        settings_layout = QVBoxLayout()

        # Настройка скорости хуманизации
        humanization_layout = QHBoxLayout()
        humanization_layout.addWidget(QLabel("⚡ Скорость хуманизации:"))
        self.humanization_mode = QComboBox()
        self.humanization_mode.addItems(["Быстрая (fast)", "Нормальная (normal)", "Безопасная (safe)"])
        self.humanization_mode.setCurrentIndex(1)  # По умолчанию "normal"
        self.humanization_mode.setObjectName("humanizationMode")
        self.humanization_mode.setToolTip(
            "Быстрая - минимальные задержки\n"
            "Нормальная - баланс скорости и безопасности\n"
            "Безопасная - максимальная имитация человека"
        )
        humanization_layout.addWidget(self.humanization_mode)
        humanization_layout.addStretch()
        settings_layout.addLayout(humanization_layout)

        # Настройки GigaChat
        gigachat_layout = QHBoxLayout()
        self.gigachat_checkbox = QCheckBox("🤖 Использовать GigaChat")
        self.gigachat_checkbox.setChecked(False)
        self.gigachat_checkbox.setObjectName("gigachatCheckbox")
        self.gigachat_checkbox.setEnabled(False)  # Неактивна до загрузки файла

        gigachat_layout.addWidget(self.gigachat_checkbox)
        gigachat_layout.addWidget(QLabel("Попыток (на все ненайденные):"))

        self.gigachat_retries = QSpinBox()
        self.gigachat_retries.setMinimum(1)
        self.gigachat_retries.setMaximum(5)
        self.gigachat_retries.setValue(3)
        self.gigachat_retries.setObjectName("gigachatRetries")
        self.gigachat_retries.setEnabled(False)  # Неактивен до загрузки файла
        gigachat_layout.addWidget(self.gigachat_retries)
        gigachat_layout.addStretch()
        settings_layout.addLayout(gigachat_layout)

        # Настройки автоматического решения капчи
        recaptcha_layout = QHBoxLayout()
        self.recaptcha_checkbox = QCheckBox(
            "🔓 Автоматическое решение капчи (ruCaptcha)"
        )
        self.recaptcha_checkbox.setChecked(False)
        self.recaptcha_checkbox.setObjectName("recaptchaCheckbox")
        self.recaptcha_checkbox.setEnabled(False)  # Неактивна до загрузки файла

        recaptcha_layout.addWidget(self.recaptcha_checkbox)
        recaptcha_layout.addStretch()
        settings_layout.addLayout(recaptcha_layout)

        settings_group.setLayout(settings_layout)

        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        # self.progress_bar.setStyleSheet(
        #     """
        #     QProgressBar {
        #         border: 2px solid #2196F3;
        #         border-radius: 5px;
        #         text-align: center;
        #         height: 25px;
        #     }
        #     QProgressBar::chunk {
        #         background-color: #4CAF50;
        #     }
        # """
        # )

        # Лог
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setObjectName("logText")

        # Кнопка сохранения логов
        self.save_log_button = QPushButton("💾 Сохранить логи")
        self.save_log_button.clicked.connect(self.save_logs)
        self.save_log_button.setObjectName("saveLogButton")
        self.save_log_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_log_button.setEnabled(False)  # Неактивна, пока нет логов

        # Информация
        info_label = QLabel(
            "⚡ Приоритет: RusProfile → Контур Фокус → ЕГРЮЛ → GigaChat"
        )
        info_label.setObjectName("infoLabel")

        # Сборка интерфейса
        main_layout.addWidget(self.label)
        main_layout.addWidget(self.browse_file_button)
        main_layout.addWidget(self.file_info_label)
        main_layout.addLayout(buttons_layout)
        main_layout.addWidget(settings_group)
        main_layout.addWidget(info_label)
        main_layout.addWidget(self.progress_bar)
        # main_layout.addWidget(QLabel("📊 Лог обработки:"))
        log_header_layout = QHBoxLayout()
        log_header_layout.addWidget(QLabel("📊 Лог обработки:"))
        log_header_layout.addStretch()
        log_header_layout.addWidget(self.save_log_button)

        main_layout.addLayout(log_header_layout)
        main_layout.addWidget(self.log_text)

        self.setLayout(main_layout)

    def save_logs(self):
        """Сохранение логов в текстовый файл"""
        if not self.log_text.toPlainText().strip():
            QMessageBox.information(self, "Информация", "Логи пусты, нечего сохранять!")
            return

        from datetime import datetime

        # Предлагаем имя файла с текущей датой и временем
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"parser_logs_{timestamp}.txt"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить логи",
            default_filename,
            "Текстовые файлы (*.txt);;Все файлы (*.*)",
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.log_text.toPlainText())

                QMessageBox.information(
                    self, "✅ Успех", f"Логи успешно сохранены!\n📁 {file_path}"
                )
                self.add_log(f"\n💾 Логи сохранены: {file_path}")

            except Exception as e:
                QMessageBox.warning(
                    self, "Ошибка", f"Не удалось сохранить логи: {str(e)}"
                )

    def drag_enter_event(self, event):
        """Обработка начала перетаскивания"""
        if not self.is_parsing and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def drop_event(self, event):
        """Обработка завершения перетаскивания"""
        if self.is_parsing:
            QMessageBox.warning(
                self, "Внимание", "Парсинг уже выполняется. Дождитесь завершения."
            )
            return
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if not self.check_file_extensions(file_path):
                QMessageBox.warning(self, "Ошибка", "Неподдерживаемый тип файла!")
            else:
                self.process_file(file_path)

    def browse_file(self):
        """Выбор файла через диалог"""
        if self.is_parsing:
            QMessageBox.warning(
                self, "Внимание", "Парсинг уже выполняется. Дождитесь завершения."
            )
            return
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
            self.current_file_path = file_path
            file_name = os.path.basename(file_path)
            self.file_info_label.setText(f"📄 Загружен: {file_name}\n📊 Строк: {len(self.df)}")
            self.file_info_label.setStyleSheet("color: #4CAF50; font-weight: bold; padding: 5px;")
            self.add_log(f"✅ Файл загружен: {file_path}")
            self.add_log(f"📊 Строк в файле: {len(self.df)}")
            # Активируем кнопку запуска и настройки
            self.start_parse_button.setEnabled(True)
            self.gigachat_checkbox.setEnabled(True)
            self.gigachat_retries.setEnabled(True)
            self.recaptcha_checkbox.setEnabled(True)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить файл: {str(e)}")
            self.file_loaded = False
            self.current_file_path = None
            self.file_info_label.setText("Файл не загружен")
            self.file_info_label.setStyleSheet("color: #666; padding: 5px;")
            self.start_parse_button.setEnabled(False)
            self.recaptcha_checkbox.setEnabled(False)

    def parse_excel_data(self):
        # """Парсинг данных из Excel"""
        # raw_data_column = self.get_raw_data_from_column()

        # # Создаем процессор текста с callback для логов
        # self.text_processor = TextProcessor(log_callback=self.add_log)

        # self.add_log("\n🔧 ЭТАП 1: Нормализация названий")
        # self.add_log("=" * 60)

        # convert_time_start = time.time()
        # processed_data_column = self.text_processor.convert_names_for_parse(
        #     raw_data_column
        # )
        # convert_time_end = time.time()
        # convert_time_result = round(convert_time_end - convert_time_start, 2)

        # self.add_log(f"\n⏱ Нормализация заняла: {convert_time_result} с")
        # self.add_log("\n🌐 ЭТАП 2: Поиск в базах данных")
        # self.add_log("=" * 60)

        # self.start_parsing(processed_data_column)

        """Парсинг данных из Excel"""
        raw_data_column = self.get_raw_data_from_column()

        self.add_log("\n🔧 ЭТАП 1: Нормализация названий")
        self.add_log("=" * 60)

        # Создаем и запускаем worker
        self.worker = TextProcessor(raw_data_column)

        # Подключаем сигналы
        self.worker.log_signal.connect(self.add_log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.start_parsing)
        # self.worker.error_signal.connect(self.on_processing_error)

        # Запоминаем время начала
        # convert_time_start = time.time()
        # Запускаем обработку
        self.worker.start()

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
        """Обработка нажатия кнопки запуска/остановки парсинга"""
        if self.is_parsing:
            # Остановка парсинга
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                "Вы уверены, что хотите остановить парсинг?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_parsing()
            return

        if not self.file_loaded or self.df is None:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите файл!")
            return

        # Устанавливаем флаг парсинга
        self.is_parsing = True

        # Блокируем элементы интерфейса на время парсинга
        self.start_parse_button.setText("⏹ Остановить парсинг")
        self.start_parse_button.setEnabled(True)
        self.pause_button.setVisible(True)
        self.pause_button.setEnabled(True)
        self.pause_button.setText("⏸ Пауза")
        self.browse_file_button.setEnabled(False)
        self.label.setAcceptDrops(False)
        self.gigachat_checkbox.setEnabled(False)
        self.gigachat_retries.setEnabled(False)
        self.recaptcha_checkbox.setEnabled(False)
        self.humanization_mode.setEnabled(False)

        self.parse_excel_data()

    def start_parsing(self, data):
        """Запуск парсинга в отдельном потоке"""
        if not self.is_parsing:
            return  # Парсинг был остановлен

        self.progress_bar.setMaximum(len(data))
        self.progress_bar.setValue(0)

        use_gigachat = self.gigachat_checkbox.isChecked()
        retries = self.gigachat_retries.value()
        use_recaptcha = self.recaptcha_checkbox.isChecked()  # НОВОЕ

        # Получаем режим хуманизации из выпадающего списка
        mode_index = self.humanization_mode.currentIndex()
        humanization_modes = ["fast", "normal", "safe"]
        humanization_mode = humanization_modes[mode_index]

        self.parser_thread = ParserThread(
            data, self.df.copy(), use_gigachat, retries, use_recaptcha, humanization_mode
        )
        self.parser_thread.progress.connect(self.update_progress)
        self.parser_thread.log_message.connect(self.add_log)
        self.parser_thread.finished.connect(self.parsing_finished)
        self.parser_thread.start()

    def toggle_pause(self):
        """Переключение паузы/возобновления парсинга"""
        if not self.is_parsing or not self.parser_thread:
            return

        if self.is_paused:
            # Возобновляем парсинг
            self.is_paused = False
            if self.parser_thread:
                self.parser_thread._paused = False
            self.pause_button.setText("⏸ Пауза")
            self.add_log("\n▶️ Парсинг возобновлен")
        else:
            # Ставим на паузу
            self.is_paused = True
            if self.parser_thread:
                self.parser_thread._paused = True
            self.pause_button.setText("▶ Возобновить")
            self.add_log("\n⏸ Парсинг приостановлен")

    def stop_parsing(self):
        """Остановка парсинга"""
        # Снимаем паузу если была установлена
        self.is_paused = False
        if self.parser_thread and self.parser_thread.isRunning():
            # Устанавливаем флаг остановки для корректного завершения
            self.parser_thread._stop_requested = True
            self.parser_thread._paused = False  # Снимаем паузу

            # Закрываем браузер если он открыт
            if self.parser_thread.parser:
                try:
                    self.parser_thread.parser.close_browser()
                except Exception as e:
                    self.add_log(f"\n⚠️ Ошибка при закрытии браузера: {e}")

            # Ждем завершения потока (максимум 5 секунд)
            if not self.parser_thread.wait(5000):
                # Если поток не завершился за 5 секунд, принудительно завершаем
                self.add_log("\n⚠️ Принудительное завершение потока...")
                self.parser_thread.terminate()
                self.parser_thread.wait(1000)

            self.add_log("\n⚠️ Парсинг остановлен пользователем")

        self.is_parsing = False
        self.reset_ui_after_parsing()

    def update_progress(self, current, total=None):
        """Обновление прогресс бара"""
        self.progress_bar.setValue(current)

    def add_log(self, message):
        """Добавление сообщения в лог"""
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        # Активируем кнопку сохранения логов, если есть логи
        if self.log_text.toPlainText().strip():
            self.save_log_button.setEnabled(True)

    def parsing_finished(self, result_df):
        """Завершение парсинга"""
        if not self.is_parsing:
            return  # Парсинг был остановлен

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

        self.is_parsing = False
        self.is_paused = False
        self.reset_ui_after_parsing()

        # Закрываем процессор текста
        if self.text_processor:
            self.text_processor.close()

    def reset_ui_after_parsing(self):
        """Сброс UI после завершения парсинга"""
        self.is_paused = False
        self.start_parse_button.setText("🚀 Начать парсинг")
        self.pause_button.setVisible(False)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("⏸ Пауза")
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)

        # Восстанавливаем кнопки и элементы интерфейса
        self.start_parse_button.setText("🚀 Начать парсинг")
        self.start_parse_button.setEnabled(self.file_loaded)
        self.browse_file_button.setEnabled(True)
        self.label.setAcceptDrops(True)
        self.gigachat_checkbox.setEnabled(self.file_loaded)
        self.gigachat_retries.setEnabled(self.file_loaded)
        self.recaptcha_checkbox.setEnabled(self.file_loaded)
        self.humanization_mode.setEnabled(self.file_loaded)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    window = FillExcelColumns()
    window.show()
    sys.exit(app.exec())
