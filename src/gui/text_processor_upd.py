"""
Модуль для обработки и нормализации текста
"""

import re
import time
from PySide6.QtCore import QThread, Signal
import language_tool_python


class TextProcessor(QThread):
    """Класс для обработки и нормализации названий организаций"""

    # Сигналы для связи с UI
    log_signal = Signal(str)           # Логи
    progress_signal = Signal(int)      # Прогресс (0-100)
    finished_signal = Signal(list)     # Результат обработки
    # error_signal = Signal(str)         # Ошибки

    def __init__(self, raw_data_column):
        super().__init__()
        self.raw_data_column = raw_data_column
        self.convert_time_start = time.time()
        self.convert_time_end = None
        self.convert_time_result = None
        self.tool = None
        self._is_cancelled = False

    def cancel(self):
        """Отмена выполнения"""
        self._is_cancelled = True

    def run(self):
        """Основной метод, выполняющийся в отдельном потоке"""
        try:
            # Инициализируем LanguageTool
            self.log("🔧 Инициализация проверки орфографии...")
            self.tool = language_tool_python.LanguageTool("ru")

            result = []
            total = len(self.raw_data_column)

            self.log(f"\n{'='*60}")
            self.log(f"🔄 Начинаю нормализацию {total} записей...")
            self.log(f"{'='*60}\n")

            for idx, company_name in enumerate(self.raw_data_column, 1):
                if self._is_cancelled:
                    self.log("\n⚠️ Обработка отменена пользователем")
                    return

                self.log(f"\n📌 [{idx}/{total}] Обработка: {company_name[:60]}...")

                # Удаляем географические упоминания
                company_name = self.remove_geo_mentions(company_name)
                self.log("  ✓ Удалены географические упоминания")

                # Очищаем текст
                company_name = self.clean_text(company_name)

                result.append(company_name)
                self.log(f"  ✅ Результат: {company_name[:60]}...")

                # Обновляем прогресс
                progress = int((idx / total) * 100)
                self.progress_signal.emit(progress)

            self.convert_time_end = time.time()
            self.convert_time_result = round(self.convert_time_end - self.convert_time_start, 2)

            self.log(f"\n{'='*60}")
            self.log(f"✅ Нормализация завершена! Обработано: {total}")
            self.log(f"⏱ Нормализация заняла: {self.convert_time_result} с")
            self.log(f"{'='*60}\n")

            # Отправляем результат
            self.finished_signal.emit(result)

        except Exception as e:
            error_msg = f"❌ Ошибка обработки: {str(e)}"
            self.log(error_msg)
            # self.error_signal.emit(error_msg)

        finally:
            # Закрываем LanguageTool
            if self.tool:
                self.tool.close()

    def log(self, message):
        """Отправка лога в UI"""
        self.log_signal.emit(message)

    def create_correct_spelling(self, word):
        """Проверка и исправление орфографии слова"""
        try:
            matches = self.tool.check(word)
            if matches:
                corrected_word = self.tool.correct(word)
            else:
                corrected_word = word

            self.log(f"  ✓ Проверено: {word}")
            return corrected_word

        except Exception as e:
            self.log(f"  ⚠️ Ошибка проверки '{word}': {str(e)}")
            return word

    def remove_geo_mentions(self, text):
        """Удаление географических упоминаний из текста"""
        result_correct_text = re.sub(r'(.*)".*$', r'\1"', text)
        return result_correct_text

    def clean_text(self, text):
        """Очистка и нормализация текста"""
        # Извлекаем части в кавычках
        quoted_parts = re.findall(r'"(.*?)"', text)

        temp_text = text
        for part in quoted_parts:
            temp_text = re.sub(rf'"{re.escape(part)}"', "", temp_text)

        # Обрабатываем слова вне кавычек
        words = temp_text.split()
        corrected_words = []

        for word in words:
            if word.isupper():
                corrected_words.append(word)
            else:
                corrected_words.append(word.lower())

        cleaned_text = " ".join(corrected_words).strip()
        if cleaned_text:
            cleaned_text = cleaned_text[0].upper() + cleaned_text[1:]

        # Возвращаем кавычки на место
        for part in quoted_parts:
            insert_pos = text.find(f'"{part}"')
            if insert_pos != -1:
                cleaned_text = (
                    cleaned_text[:insert_pos] + f'"{part}"' + cleaned_text[insert_pos:]
                )

        intermediate_result = cleaned_text

        # Проверяем орфографию каждого слова
        words = intermediate_result.split()
        corrected_words = []

        self.log(f"  🔍 Проверка орфографии ({len(words)} слов)...")

        for idx, word in enumerate(words, 1):
            if self._is_cancelled:
                break

            corrected_word = self.create_correct_spelling(word)
            corrected_words.append(corrected_word)

            # Прогресс каждые 5 слов
            if idx % 5 == 0:
                self.log(f"  📝 Обработано слов: {idx}/{len(words)}")

        cleaned_text = " ".join(corrected_words)
        return cleaned_text
