"""
Модуль для обработки и нормализации текста
"""

import re
import time
import json
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
        # self.convert_time_start = 0
        # self.convert_time_end = None
        # self.convert_time_result = None
        self.tool = None
        self._is_cancelled = False

        self.rules = {
            "abbreviations": {},
            "geo_markers": [],
            "type_synonyms": {}
        }

        self.load_standartization_rules()
        self.compile_regex()

    def load_standartization_rules(self):
        try:
            with open("standardization_rules.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                self.rules["abbreviations"] = data.get("abbreviations", {})
                self.rules["geo_markers"] = data.get("geo_markers", [])
                self.rules["type_synonyms"] = data.get("type_synonyms", {})
        except Exception as e:
            self.log(f"❌ Ошибка чтения файла standardization_rules.json: {e}")

    def compile_regex(self):
        """Компиляция регулярных выражений на основе правил"""
        geo_list = self.rules["geo_markers"]
        if geo_list:
            geo_list = sorted(geo_list, key=len, reverse=True)
            geo_pattern = r'(?:\b|^)(' + '|'.join(map(re.escape, geo_list)) + r')(?:\b|\s|$)'
            self.geo_regex = re.compile(geo_pattern, re.IGNORECASE)
        else:
            self.geo_regex = re.compile(r'(?!x)x')

        self.replacements = {}

        for short_name, synonyms in self.rules["type_synonyms"].items():
            for syn in synonyms:
                self.replacements[syn.lower()] = short_name

        for abbr, full_name in self.rules["abbreviations"].items():
            if full_name:
                self.replacements[full_name.lower()] = abbr

    def cancel(self):
        """Отмена выполнения"""
        self._is_cancelled = True

    def run(self):
        """Основной метод, выполняющийся в отдельном потоке"""
        self.convert_time_start = time.time()
        result = []

        try:
            # Инициализируем LanguageTool
            self.log("🔧 Инициализация проверки орфографии...")
            self.tool = language_tool_python.LanguageTool("ru")

            total = len(self.raw_data_column)

            self.log(f"\n{'='*60}")
            self.log(f"🔄 Начинаю нормализацию {total} записей...")
            self.log(f"{'='*60}\n")

            for idx, company_name in enumerate(self.raw_data_column, 1):
                if self._is_cancelled:
                    self.log("\n⚠️ Обработка отменена пользователем")
                    return

                origin_company_name = str(company_name).strip()
                # self.log(f"\n📌 [{idx}/{total}] Обработка: {company_name[:60]}...")

                company_name_no_geo = self.remove_geo_mentions(origin_company_name)
                company_namee_standardized = self.standardize_names(company_name_no_geo)
                company_nam_cleaned = self.clean_formatting(company_namee_standardized)
                final_company_name = self.check_and_correct(company_nam_cleaned)

                result.append(final_company_name)

                if idx % 5 == 0 or idx == total:
                    self.log(f"[{idx}/{total}] Обработано: {final_company_name[:40]}...")

                progress = int((idx / total) * 100)
                self.progress_signal.emit(progress)

                # # Удаляем географические упоминания
                # company_name = self.remove_geo_mentions(company_name)
                # self.log("  ✓ Удалены географические упоминания")

                # # Очищаем текст
                # company_name = self.clean_text(company_name)

                # result.append(company_name)
                # self.log(f"  ✅ Результат: {company_name[:60]}...")

                # Обновляем прогресс

            if not self._is_cancelled:
                duration = round(time.time() - self.convert_time_start, 2)

                self.log(f"\n{'='*60}")
                self.log(f"✅ Нормализация завершена! Обработано: {total}")
                self.log(f"⏱ Нормализация заняла: {duration} с")
                self.log(f"{'='*60}\n")

                self.finished_signal.emit(result)
            # self.convert_time_end = time.time()
            # self.convert_time_result = round(self.convert_time_end - self.convert_time_start, 2)

            # self.finished_signal.emit(result)

        except Exception as e:
            error_msg = f"❌ Ошибка обработки: {str(e)}"
            self.log(error_msg)
            # self.error_signal.emit(error_msg)

        finally:
            # Закрываем LanguageTool
            self.close_tool()

    def close_tool(self):
        """Безопасное закрытие LanguageTool"""
        if self.tool:
            try:
                self.log("🔌 Закрытие процесса LanguageTool...")
                self.tool.close()
                self.tool = None
                self.log("✅ Процесс Java остановлен.")
            except Exception as e:
                self.log(f"⚠️ Ошибка при закрытии LT: {e}")

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
        result_correct_text = self.geo_regex.sub('', text)

        return result_correct_text

    def standardize_names(self, text):
        """Заменяет полные названия на аббревиатуры"""
        # lower_text = text.lower()
        # Сортируем замены по длине (сначала длинные фразы)
        sorted_replacements = sorted(self.replacements.items(), key=lambda x: len(x[0]), reverse=True)

        temp_text = text

        for long_name, short_name in sorted_replacements:
            pattern = re.compile(re.escape(long_name), re.IGNORECASE)
            if pattern.search(temp_text):
                temp_text = pattern.sub(short_name, temp_text)

        return temp_text

    def clean_formatting(self, text):
        """Базовая очистка пунктуации и пробелов"""
        # Убираем пробелы перед знаками препинания
        text = re.sub(r'\s+([.,;?!])', r'\1', text)
        # Убираем лишние кавычки
        text = re.sub(r'""+', '"', text)
        # Первая буква заглавная
        if text:
            text = text[0].upper() + text[1:]
        return text.strip()

    def check_and_correct(self, text):
        """Проверка орфографии всей строки целиком"""
        try:
            matches = self.tool.check(text)
            if not matches:
                return text
            return language_tool_python.utils.correct(text, matches)
        except Exception:
            return text

    # def clean_text(self, text):
        # """Очистка и нормализация текста"""
        # # Извлекаем части в кавычках
        # quoted_parts = re.findall(r'"(.*?)"', text)

        # temp_text = text
        # for part in quoted_parts:
        #     temp_text = re.sub(rf'"{re.escape(part)}"', "", temp_text)

        # # Обрабатываем слова вне кавычек
        # words = temp_text.split()
        # corrected_words = []

        # for word in words:
        #     if word.isupper():
        #         corrected_words.append(word)
        #     else:
        #         corrected_words.append(word.lower())

        # cleaned_text = " ".join(corrected_words).strip()
        # if cleaned_text:
        #     cleaned_text = cleaned_text[0].upper() + cleaned_text[1:]

        # # Возвращаем кавычки на место
        # for part in quoted_parts:
        #     insert_pos = text.find(f'"{part}"')
        #     if insert_pos != -1:
        #         cleaned_text = (
        #             cleaned_text[:insert_pos] + f'"{part}"' + cleaned_text[insert_pos:]
        #         )

        # intermediate_result = cleaned_text

        # # Проверяем орфографию каждого слова
        # words = intermediate_result.split()
        # corrected_words = []

        # self.log(f"  🔍 Проверка орфографии ({len(words)} слов)...")

        # for idx, word in enumerate(words, 1):
        #     if self._is_cancelled:
        #         break

        #     corrected_word = self.create_correct_spelling(word)
        #     corrected_words.append(corrected_word)

        #     # Прогресс каждые 5 слов
        #     if idx % 5 == 0:
        #         self.log(f"  📝 Обработано слов: {idx}/{len(words)}")

        # cleaned_text = " ".join(corrected_words)
        # return cleaned_text
