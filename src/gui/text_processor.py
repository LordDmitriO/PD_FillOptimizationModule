"""
Модуль для обработки и нормализации текста
"""

import re
import threading
from queue import Queue
import language_tool_python


class TextProcessor:
    """Класс для обработки и нормализации названий организаций"""

    def __init__(self, log_callback=None):
        self.tool = language_tool_python.LanguageTool("ru")
        self.log_callback = log_callback

    def log(self, message):
        """Вывод сообщения в лог"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def create_correct_spelling(self, word):
        """Проверка и исправление орфографии слова"""
        result_queue = Queue()

        def check_word():
            try:
                matches = self.tool.check(word)
                if matches:
                    corrected_word = self.tool.correct(word)
                else:
                    corrected_word = word
                result_queue.put(corrected_word)
            except Exception as e:
                result_queue.put((word, f"Ошибка: {str(e)}"))

        thread = threading.Thread(target=check_word)
        thread.start()
        thread.join(timeout=10.0)

        if thread.is_alive():
            self.log(f"  ⏱️ Превышено время проверки для слова: {word}")
            thread.join()
            return word
        else:
            self.log(f"  ✓ Проверено: {word}")

        result_correct_word = result_queue.get()
        if isinstance(result_correct_word, tuple):
            self.log(f"  ⚠️ {result_correct_word[1]}")
            result_correct_word = result_correct_word[0]

        return result_correct_word

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
            corrected_word = self.create_correct_spelling(word)
            corrected_words.append(corrected_word)

            # Прогресс каждые 5 слов
            if idx % 5 == 0:
                self.log(f"  📝 Обработано слов: {idx}/{len(words)}")

        cleaned_text = " ".join(corrected_words)
        return cleaned_text

    def convert_names_for_parse(self, raw_data_column):
        """Конвертация списка названий для парсинга"""
        result = []
        total = len(raw_data_column)

        self.log(f"\n{'='*60}")
        self.log(f"🔄 Начинаю нормализацию {total} записей...")
        self.log(f"{'='*60}\n")

        for idx, company_name in enumerate(raw_data_column, 1):
            self.log(f"\n📌 [{idx}/{total}] Обработка: {company_name[:60]}...")

            # Удаляем географические упоминания
            company_name = self.remove_geo_mentions(company_name)
            self.log(f"  ✓ Удалены географические упоминания")

            # Очищаем текст
            company_name = self.clean_text(company_name)

            result.append(company_name)
            self.log(f"  ✅ Результат: {company_name[:60]}...")

        self.log(f"\n{'='*60}")
        self.log(f"✅ Нормализация завершена! Обработано: {total}")
        self.log(f"{'='*60}\n")

        return result

    def close(self):
        """Закрыть инструмент проверки орфографии"""
        if self.tool:
            self.tool.close()
