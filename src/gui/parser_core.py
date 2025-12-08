"""
Модуль для парсинга данных организаций из различных источников
"""

import re
import os
import json
import random as rd
import tempfile
import pymorphy3
import time
from selenium import webdriver as wd
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup as BS

import config
from .humanization import Humanization
from .recaptcha_solver import ReCaptchaSolver


class BaseSearcher:
    """Базовый класс для всех сеарчеров с общими утилитами"""

    def __init__(self, browser, humanizer, log_callback=None):
        self.browser = browser
        self.humanizer = humanizer
        self.log_callback = log_callback

    def log(self, message):
        """Вывод сообщения в лог"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    @staticmethod
    def get_genitive_case_pymorphy(org_name):
        """Получение родительного падежа через pymorphy3"""
        if not org_name:
            return org_name

        morph = pymorphy3.MorphAnalyzer()

        words = org_name.split()
        genitive_words = []

        for word in words:
            if word.startswith(("«", '"', '"')) or word.endswith(("»", '"', '"')):
                genitive_words.append(word)
            else:
                clean_word = word.strip(".,;:!?")
                punct = word[len(clean_word) :] if len(word) > len(clean_word) else ""

                parsed = morph.parse(clean_word)[0]
                genitive_form = parsed.inflect({"gent"})

                if genitive_form:
                    genitive_words.append(
                        genitive_form.word.capitalize()
                        if clean_word[0].isupper()
                        else genitive_form.word + punct
                    )
                else:
                    genitive_words.append(word)

        return " ".join(genitive_words)

    @staticmethod
    def remove_quotes_for_search(text):
        """Удаляет все типы кавычек из текста для поиска"""
        if not text:
            return text
        # Удаляем все типы кавычек: обычные, типографские, одинарные
        return re.sub(r'["\'«»""]', '', text).strip()

    @staticmethod
    def normalize_organization_name(name):
        """
        Приводит название организации к нормальному виду:
        - Первое слово с заглавной буквы
        - Остальные слова со строчной
        - Текст в кавычках с заглавной первой буквы
        """
        if not name:
            return name

        # Паттерн для поиска текста в кавычках (любые типы кавычек)
        quote_pattern = r'[«"\'"][^«»"\'""]+[»"\'""]'

        # Находим все совпадения с кавычками и их позиции
        matches = list(re.finditer(quote_pattern, name))

        # Если нет кавычек, просто приводим к нормальному виду
        if not matches:
            return name.capitalize()

        result = []
        last_end = 0

        for i, match in enumerate(matches):
            start, end = match.span()

            # Обрабатываем текст ДО кавычек
            before_text = name[last_end:start]
            if before_text:
                words = before_text.split()
                normalized_words = []
                for j, word in enumerate(words):
                    # Первое слово всего названия - с заглавной
                    if last_end == 0 and j == 0:
                        normalized_words.append(word.capitalize())
                    else:
                        normalized_words.append(word.lower())

                # Добавляем текст, сохраняя пробел в конце если он был
                normalized_before = " ".join(normalized_words)
                if before_text.endswith(" "):
                    normalized_before += " "
                result.append(normalized_before)

            # Обрабатываем текст В кавычках
            quoted_text = match.group()
            opening_quote = quoted_text[0]
            closing_quote = quoted_text[-1]
            inner_text = quoted_text[1:-1]

            # Приводим к нормальному виду: первая буква заглавная, остальные строчные
            normalized_inner = inner_text.capitalize()
            result.append(f"{opening_quote}{normalized_inner}{closing_quote}")

            last_end = end

        # Обрабатываем остаток текста ПОСЛЕ последних кавычек (если есть)
        if last_end < len(name):
            after_text = name[last_end:]
            words = after_text.split()
            normalized_words = [word.lower() for word in words]
            result.append(" ".join(normalized_words))

        return "".join(result)


class RusProfileSearcher(BaseSearcher):
    """Класс для поиска организаций в RusProfile"""

    def __init__(
        self, browser, humanizer, log_callback=None, use_recaptcha_solver=False, recaptcha_solver=None
    ):
        super().__init__(browser, humanizer, log_callback)
        self.use_recaptcha_solver = use_recaptcha_solver
        self.recaptcha_solver = recaptcha_solver
        self._std_rules = None

    def _handle_rusprofile_captcha(self):
        """
        Проверяет наличие капчи на RusProfile и обрабатывает её.
        """
        try:
            # Сначала проверяем, есть ли результаты поиска или сообщение "не найдено"
            # Если есть - это не капча, а просто отсутствие результатов
            try:
                # Проверяем наличие результатов поиска
                has_results = (
                    self.browser.find_elements(By.ID, "clip_name-long")
                    or self.browser.find_elements(By.CLASS_NAME, "list-element__title")
                    or self.browser.find_elements(By.CLASS_NAME, "company-name")
                )
                
                # Проверяем наличие сообщения "не найдено"
                body = self.browser.find_element(By.TAG_NAME, "body")
                page_text = body.text.lower()
                has_no_results_message = (
                    "не найдено" in page_text
                    or "не найдено организаций" in page_text
                    or "попробуйте смягчить фильтры" in page_text
                )
                
                # Если есть результаты или сообщение "не найдено" - это не капча
                if has_results or has_no_results_message:
                    return
            except Exception:
                pass  # Продолжаем проверку дальше

            # Проверяем наличие элементов капчи (более точная проверка)
            try:
                # Проверяем наличие iframe с recaptcha
                recaptcha_iframes = self.browser.find_elements(
                    By.CSS_SELECTOR, "iframe[src*='recaptcha'], iframe[title*='reCAPTCHA']"
                )
                
                # Проверяем наличие формы капчи
                captcha_forms = self.browser.find_elements(
                    By.CSS_SELECTOR, "form[id*='captcha'], form[class*='captcha']"
                )
                
                # Проверяем наличие конкретных текстов о капче/роботе
                body = self.browser.find_element(By.TAG_NAME, "body")
                page_text = body.text.lower()
                page_source_lower = self.browser.page_source.lower()
                
                # Конкретные фразы, которые указывают на капчу
                captcha_phrases = [
                    "вы робот",
                    "подтвердите что вы не робот",
                    "подтвердите, что вы не робот",
                    "проверка на робота",
                    "вы похожи на робота",
                ]
                
                has_captcha_text = any(phrase in page_text for phrase in captcha_phrases)
                has_recaptcha_widget = "g-recaptcha" in page_source_lower or "recaptcha/api.js" in page_source_lower
                
                # Капча есть только если:
                # 1. Есть iframe с recaptcha ИЛИ
                # 2. Есть форма капчи ИЛИ
                # 3. Есть конкретный текст о капче И есть виджет recaptcha
                is_captcha = (
                    len(recaptcha_iframes) > 0
                    or len(captcha_forms) > 0
                    or (has_captcha_text and has_recaptcha_widget)
                )
                
                if not is_captcha:
                    return  # Капчи нет, выходим
                    
            except Exception:
                # Если не можем проверить элементы, используем старую логику как fallback
                try:
                    body = self.browser.find_element(By.TAG_NAME, "body")
                    page_text = body.text.lower()
                    page_source_lower = self.browser.page_source.lower()
                    
                    # Только если есть и "робот" в тексте, и recaptcha в коде
                    if "робот" in page_text and ("g-recaptcha" in page_source_lower or "recaptcha/api.js" in page_source_lower):
                        pass  # Продолжаем обработку капчи
                    else:
                        return  # Не капча
                except Exception:
                    return  # Не можем определить, считаем что капчи нет

            # Если дошли сюда - капча действительно обнаружена
            self.log("\n" + "!" * 60)
            self.log("🛑 ОБНАРУЖЕНА КАПЧА RUSPROFILE! 🛑")

            # НОВОЕ: Автоматическое решение капчи
            if self.use_recaptcha_solver and self.recaptcha_solver:
                self.log("🤖 Попытка автоматического решения через ruCaptcha...")

                # Пытаемся решить
                if self.recaptcha_solver.solve_recaptcha_v2(self.browser):
                    self.log("🔄 Решение получено. Пробуем отправить форму...")

                    # Блок отправки формы после ввода токена
                    try:
                        # 1. Сначала пробуем найти кнопку сабмита (это надежнее чем просто form.submit)
                        submit_btn = self.browser.find_elements(
                            By.CSS_SELECTOR,
                            "button[type='submit'], input[type='submit']",
                        )
                        if submit_btn:
                            submit_btn[0].click()
                            self.log("🖱️ Нажата кнопка отправки.")
                        else:
                            # 2. Если кнопки нет, сабмитим форму
                            self.browser.execute_script(
                                """
                                var forms = document.getElementsByTagName('form');
                                if (forms.length > 0) {
                                    forms[0].submit();
                                }
                            """
                            )
                            self.log("📩 Отправлена форма через JS.")

                        self.humanizer.human_like_wait(3.0)

                    except Exception as e:
                        self.log(f"⚠️ Ошибка при отправке формы: {e}")
                        self.log("🔄 Пробуем просто обновить страницу...")
                        self.browser.refresh()
                        self.humanizer.human_like_wait(3.0)

                    # Проверка результата
                    try:
                        page_text_after = self.browser.find_element(
                            By.TAG_NAME, "body"
                        ).text
                        if "робот" not in page_text_after.lower():
                            self.log("✅ Капча успешно пройдена!")
                            self.log("!" * 60 + "\n")
                            return
                    except:
                        pass

                    self.log("⚠️ Капча все еще на месте после попытки решения.")
                else:
                    self.log("❌ Не удалось получить ответ от ruCaptcha.")
            else:
                self.log("ℹ️ Авто-решение отключено или солвер не настроен.")

            self.log("👉 Пожалуйста, решите капчу ВРУЧНУЮ в браузере.")
            self.log("⏳ Ожидание прохождения капчи...")
            self.log("!" * 60 + "\n")

            # Цикл ожидания
            while True:
                try:
                    # Если нашли элементы успешной выдачи - выходим
                    if (
                        self.browser.find_elements(By.ID, "clip_name-long")
                        or self.browser.find_elements(
                            By.CLASS_NAME, "list-element__title"
                        )
                        or self.browser.find_elements(By.CLASS_NAME, "company-name")
                    ):  # Добавил еще один признак

                        self.log("✅ Капча пройдена (обнаружен контент)!")
                        self.humanizer.human_like_wait(2.0)
                        break

                    # Проверка на закрытие браузера
                    if not self.browser.window_handles:
                        break

                    # Проверка, исчез ли текст про робота
                    body_text = self.browser.find_element(By.TAG_NAME, "body").text
                    if (
                        "робот" not in body_text.lower()
                        and "recaptcha" not in self.browser.page_source
                    ):
                        # Дополнительная проверка, что мы не на пустой странице
                        self.log("✅ Текст капчи исчез. Продолжаем.")
                        time.sleep(2)
                        break

                except Exception:
                    pass  # Игнорируем ошибки поиска элементов пока ждем

                time.sleep(2)

        except Exception as e:
            self.log(f"⚠️ Ошибка в логике обработки капчи: {e}")

    def _load_standardization_rules(self):
        """Загрузка правил стандартизации"""
        if self._std_rules is not None:
            return self._std_rules

        try:
            rules_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "standardization_rules.json"
            )
            rules_path = os.path.abspath(rules_path)
            with open(rules_path, "r", encoding="utf-8") as f:
                self._std_rules = json.load(f)
                return self._std_rules
        except Exception as e:
            self.log(f"  ⚠️ Не удалось загрузить standardization_rules.json: {e}")
            # Возвращаем минимальный набор правил
            self._std_rules = {"abbreviations": {}, "type_synonyms": {}}
            return self._std_rules

    def _expand_abbreviations_in_text(self, text):
        """Расшифровывает все аббревиатуры в тексте, но НЕ заменяет аббревиатуры внутри кавычек"""
        if not text:
            return text
        
        rules = self._load_standardization_rules()
        result = text
        abbreviations = rules.get("abbreviations", {})
        
        # Извлекаем все части текста в кавычках, чтобы не заменять аббревиатуры внутри них
        quote_pattern = r'["\'«»][^"\']+["\'»]'
        quoted_parts = []
        for match in re.finditer(quote_pattern, result):
            quoted_parts.append((match.start(), match.end(), match.group()))
        
        # Создаем версию текста без кавычек для замены
        text_without_quotes = result
        placeholders = {}
        for i, (start, end, quoted_text) in enumerate(quoted_parts):
            placeholder = f"__QUOTE_PLACEHOLDER_{i}__"
            placeholders[placeholder] = quoted_text
            text_without_quotes = text_without_quotes[:start] + placeholder + text_without_quotes[end:]
        
        # Сначала заменяем ОПФ (организационно-правовые формы) в начале строки
        # Сортируем по длине (от длинных к коротким), чтобы сначала заменять составные аббревиатуры
        opf_abbreviations = sorted(
            [(abbr, full_form) for abbr, full_form in abbreviations.items() 
             if abbr in ["АНОО", "АНО", "МБОУ", "ГБОУ", "МАОУ", "МКОУ", "ГКОУ", 
                        "ЧОУ", "НЧОУ", "ФГБОУ", "ФГАОУ", "ГАОУ", "ГБПОУ", "ГАПОУ"]],
            key=lambda x: len(x[0]),
            reverse=True
        )
        
        for abbr, full_form in opf_abbreviations:
            # Ищем ОПФ в начале строки (только вне кавычек)
            pattern = r'^' + re.escape(abbr) + r'\s+'
            if re.search(pattern, text_without_quotes, re.IGNORECASE):
                text_without_quotes = re.sub(pattern, full_form + " ", text_without_quotes, flags=re.IGNORECASE)
                break  # Заменяем только первую найденную ОПФ в начале
        
        # Затем заменяем остальные аббревиатуры (сортируем по длине для правильной замены)
        # Исключаем короткие аббревиатуры (1-2 символа), которые могут быть частью других слов
        other_abbreviations = sorted(
            [(abbr, full_form) for abbr, full_form in abbreviations.items() 
             if abbr not in ["АНОО", "АНО", "МБОУ", "ГБОУ", "МАОУ", "МКОУ", "ГКОУ", 
                            "ЧОУ", "НЧОУ", "ФГБОУ", "ФГАОУ", "ГАОУ", "ГБПОУ", "ГАПОУ"]
             and len(abbr) >= 3],  # Только аббревиатуры длиной 3+ символа
            key=lambda x: len(x[0]),
            reverse=True
        )
        
        for abbr, full_form in other_abbreviations:
            # Ищем аббревиатуру как отдельное слово (только вне кавычек)
            pattern = r'\b' + re.escape(abbr) + r'\b'
            if re.search(pattern, text_without_quotes, re.IGNORECASE):
                text_without_quotes = re.sub(pattern, full_form, text_without_quotes, flags=re.IGNORECASE)
        
        # Восстанавливаем кавычки обратно
        result = text_without_quotes
        for placeholder, quoted_text in placeholders.items():
            result = result.replace(placeholder, quoted_text)
        
        return result

    def _is_educational_keyword(self, text):
        """Проверяет, содержит ли текст образовательные ключевые слова"""
        if not text:
            return False
        
        text_lower = text.lower()
        rules = self._load_standardization_rules()
        
        # Проверяем аббревиатуры (как отдельные слова)
        for abbr in rules.get("abbreviations", {}).keys():
            # Ищем аббревиатуру как отдельное слово
            pattern = r'\b' + re.escape(abbr.lower()) + r'\b'
            if re.search(pattern, text_lower):
                return True
        
        # Проверяем образовательные ключевые слова
        edu_keywords = [
            "школа", "сош", "лицей", "гимназия", "колледж", "университет",
            "институт", "училище", "образовательн", "учреждение", "детский сад",
            "доу", "дворец творчества", "дом творчества", "центр детского",
            "центр развития", "центр образования"
        ]
        
        # Проверяем точные совпадения для более надежной проверки
        for keyword in edu_keywords:
            if keyword in text_lower:
                return True
        
        return False

    def _has_unique_words(self, text, original_text=None):
        """Проверяет, содержит ли текст уникальные слова (не только общие образовательные термины)"""
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Общие образовательные слова, которые не являются уникальными (загружаем из файла)
        rules = self._load_standardization_rules()
        common_edu_words = set(rules.get("common_words", []))
        
        # Извлекаем все слова из текста
        words = set(re.findall(r'\b[А-ЯЁа-яё]{3,}\b', text_lower))
        
        # Убираем общие слова
        unique_words = words - common_edu_words
        
        # Если есть уникальные слова - это хорошо
        if unique_words:
            return True
        
        # Если есть слова в кавычках - это тоже уникально
        if re.search(r'["\'«»][^"\']+["\'»]', text):
            return True
        
        # Если передан оригинальный текст, проверяем совпадение уникальных слов
        if original_text:
            original_words = set(re.findall(r'\b[А-ЯЁа-яё]{3,}\b', original_text.lower()))
            original_unique = original_words - common_edu_words
            if original_unique and unique_words:
                # Если есть пересечение уникальных слов - это хорошо
                if original_unique.intersection(unique_words):
                    return True
        
        # Если нет уникальных слов - это слишком общий вариант
        return False

    def _validate_organization_result(self, org_name, result, check_keyword_match=True):
        """Проверяет валидность найденной организации
        
        Args:
            org_name: Оригинальное название для поиска (может быть пустым для поиска по ИНН)
            result: Результат поиска с данными организации
            check_keyword_match: Проверять ли совпадение ключевых слов (False для поиска по ИНН)
        """
        if not result.get("found") or not result.get("name"):
            return False
        
        found_name = result["name"].lower()
        
        # Проверяем, что найденная организация - образовательное учреждение
        if not self._is_educational_keyword(found_name):
            self.log(f"  ⚠️ Найдена организация не является образовательным учреждением: {found_name[:70]}...")
            return False
        
        # Проверяем негативные ключевые слова
        negative_keywords = [
            "прекращение деятельности",
            "ликвидатор",
            "ликвидационной комиссии",
            "признания регистрации недействительной",
            "театр",
            "религиозная организация",
            "приход",
            "храм",
            "церковь",
            "товарищество",
            "снт",
            "тсн",
        ]
        
        for neg_keyword in negative_keywords:
            if neg_keyword in found_name:
                self.log(f"  ⚠️ Найдена организация содержит негативное ключевое слово '{neg_keyword}': {found_name[:70]}...")
                return False
        
        # Проверяем совпадение ключевых слов только если указано оригинальное название
        if check_keyword_match and org_name:
            original_name = org_name.lower()
            # Извлекаем ключевые слова из оригинального названия
            original_words = set(re.findall(r'\b[А-ЯЁа-яё]{3,}\b', original_name))
            found_words = set(re.findall(r'\b[А-ЯЁа-яё]{3,}\b', found_name))
            
            # Исключаем общие слова (загружаем из файла)
            rules = self._load_standardization_rules()
            common_words = set(rules.get("common_words", []))
            original_words -= common_words
            found_words -= common_words
            
            # Извлекаем слова в кавычках из оригинального названия (это очень важные уникальные слова)
            quoted_words_original = set()
            quoted_matches = re.findall(r'["\'«»]([^"\']+)["\'»]', original_name)
            for quoted_text in quoted_matches:
                quoted_words_original.update(re.findall(r'\b[А-ЯЁа-яё]{3,}\b', quoted_text.lower()))
            quoted_words_original -= common_words
            
            # Проверяем совпадение уникальных слов
            if original_words and found_words:
                intersection = original_words.intersection(found_words)
                if not intersection:
                    self.log(f"  ⚠️ Нет совпадения ключевых слов между '{org_name[:50]}...' и '{found_name[:50]}...'")
                    return False
                
                # Если есть слова в кавычках, они должны обязательно совпадать
                if quoted_words_original:
                    quoted_intersection = quoted_words_original.intersection(found_words)
                    if not quoted_intersection:
                        self.log(f"  ⚠️ Не найдено совпадения уникальных слов из кавычек '{org_name[:50]}...' в '{found_name[:50]}...'")
                        return False
        
        return True

    def generate_search_variants(self, org_name):
        """Генерирует варианты названия для поиска с расшифровкой аббревиатур"""
        variants = []
        rules = self._load_standardization_rules()

        # 1. ПЕРВЫЙ ВАРИАНТ: Оригинальное название с расшифрованными аббревиатурами
        expanded_original = self._expand_abbreviations_in_text(org_name)
        if expanded_original != org_name:
            variants.append(expanded_original)

        # 2. Оригинальное название (без расшифровки)
        variants.append(org_name)

        # 3. Убираем город в конце (после запятой или пробела)
        # "АНОО Лицей Интеллект Балашиха" -> "АНОО Лицей Интеллект"
        without_city = re.sub(
            r"[,\s]+(?:г\.?\s*)?[А-ЯЁ][а-яё]+(?:\s+обл\.?)?$", "", org_name
        )
        if without_city != org_name:
            variants.append(without_city.strip())
            # С расшифровкой
            expanded_without_city = self._expand_abbreviations_in_text(without_city.strip())
            if expanded_without_city != without_city.strip() and expanded_without_city not in variants:
                variants.append(expanded_without_city)

        # 4. Убираем всё после последних кавычек
        # 'АНОО "Лицей "Интеллект" Балашиха' -> 'АНОО "Лицей "Интеллект"'
        quote_match = re.search(r'(.+["\'])\s+[А-ЯЁ]', org_name)
        if quote_match:
            variant = quote_match.group(1).strip()
            variants.append(variant)
            # С расшифровкой
            expanded_variant = self._expand_abbreviations_in_text(variant)
            if expanded_variant != variant and expanded_variant not in variants:
                variants.append(expanded_variant)

        # 5. Только текст в кавычках (НО только если содержит образовательные ключевые слова)
        # '"Лицей "Интеллект"' или "Интеллект"
        quoted = re.findall(r'["\']([^"\']+)["\']', org_name)
        if quoted:
            # Берем самую длинную цитату
            longest_quote = max(quoted, key=len)
            # Добавляем только если содержит образовательные ключевые слова
            if self._is_educational_keyword(longest_quote):
                variants.append(longest_quote)
                # С расшифровкой
                expanded_quote = self._expand_abbreviations_in_text(longest_quote)
                if expanded_quote != longest_quote and expanded_quote not in variants:
                    variants.append(expanded_quote)

        # 6. Убираем организационно-правовую форму в начале
        # "АНОО Лицей Интеллект" -> "Лицей Интеллект"
        without_opf = re.sub(
            r'^(?:ООО|ЗАО|ОАО|АО|ИП|ФГБОУ|МБОУ|АНОО|НОУ|ГОУ|МОУ|АНО)\s+["\']?', "", org_name
        )
        if without_opf != org_name:
            without_opf_clean = without_opf.strip()
            # Добавляем только если содержит уникальные слова
            if self._has_unique_words(without_opf_clean, org_name):
                variants.append(without_opf_clean)
                # С расшифровкой
                expanded_without_opf = self._expand_abbreviations_in_text(without_opf_clean)
                if expanded_without_opf != without_opf_clean and expanded_without_opf not in variants:
                    if self._has_unique_words(expanded_without_opf, org_name):
                        variants.append(expanded_without_opf)

        # 7. Ключевые слова (самое важное - обычно в кавычках или после ОПФ)
        # Находим основное название без ОПФ и города
        core_name = re.sub(
            r"^(?:ООО|ЗАО|ОАО|АО|ИП|ФГБОУ|МБОУ|АНОО|НОУ|ГОУ|МОУ|АНО)\s+", "", org_name
        )
        core_name = re.sub(
            r"[,\s]+(?:г\.?\s*)?[А-ЯЁ][а-яё]+(?:\s+обл\.?)?$", "", core_name
        )
        if core_name and core_name != org_name:
            core_name_clean = core_name.strip()
            # Добавляем только если содержит уникальные слова
            if self._has_unique_words(core_name_clean, org_name):
                variants.append(core_name_clean)
                # С расшифровкой
                expanded_core = self._expand_abbreviations_in_text(core_name_clean)
                if expanded_core != core_name_clean and expanded_core not in variants:
                    if self._has_unique_words(expanded_core, org_name):
                        variants.append(expanded_core)

        # 8. Только слова в кавычках без спецсимволов (НО только если содержат образовательные ключевые слова)
        clean_quoted = re.findall(r'["\']([А-ЯЁа-яё\s]+)["\']', org_name)
        for cq in clean_quoted:
            cq_clean = cq.strip()
            if cq_clean and cq_clean not in variants:
                # Добавляем только если содержит образовательные ключевые слова
                if self._is_educational_keyword(cq_clean):
                    variants.append(cq_clean)
                    # С расшифровкой
                    expanded_cq = self._expand_abbreviations_in_text(cq_clean)
                    if expanded_cq != cq_clean and expanded_cq not in variants:
                        variants.append(expanded_cq)

        # Убираем дубликаты, сохраняя порядок
        seen = set()
        unique_variants = []
        for v in variants:
            v_clean = v.strip()
            if v_clean and v_clean not in seen and len(v_clean) > 3:
                seen.add(v_clean)
                unique_variants.append(v_clean)

        return unique_variants

    def search(self, org_name=None, inn=None):
        """Поиск в RusProfile по названию или ИНН с множественными попытками"""
        result = {
            "found": False,
            "address": "",
            "postal_code": "",
        }

        try:
            main_url = "https://www.rusprofile.ru"

            if inn:
                # Поиск по ИНН (оставляем как есть)
                return self._search_by_inn(main_url, inn, result)
            else:
                # Поиск по названию с вариациями
                return self._search_by_name_with_variants(main_url, org_name, result)

        except Exception as e:
            self.log(f"  ⚠️ Ошибка: {str(e)}")

        return result

    def _search_by_name_with_variants(self, main_url, org_name, result):
        """Поиск по названию с несколькими вариантами"""
        variants = self.generate_search_variants(org_name)
        original_org_name = org_name  # Сохраняем оригинальное название для валидации

        self.log(f"  🔄 Попробую {len(variants)} вариантов поиска:")
        for i, variant in enumerate(variants, 1):
            self.log(f"     {i}. «{variant}»")

        for attempt, variant in enumerate(variants, 1):
            self.log(f"  🔍 Попытка {attempt}/{len(variants)}: «{variant}»")

            # Очищаем результат перед каждой попыткой
            result["found"] = False
            result["name"] = ""
            result["address"] = ""
            result["postal_code"] = ""
            result["inn"] = ""
            result["ogrn"] = ""
            result["name_genitive"] = ""

            try:
                # Расширенный поиск
                self.browser.get(main_url + "/search-advanced")
                self.humanizer.human_like_wait(rd.uniform(0.5, 1.0))

                self._handle_rusprofile_captcha()

                try:
                    search = self.humanizer.human_like_wait_for_element(
                        self.browser, (By.ID, "advanced-search-query"), 10
                    )
                    if not search:
                        # Очищаем результат перед следующей попыткой
                        result["found"] = False
                        result["name"] = ""
                        result["address"] = ""
                        result["postal_code"] = ""
                        result["inn"] = ""
                        result["ogrn"] = ""
                        result["name_genitive"] = ""
                        continue

                    search.clear()
                    # Убираем кавычки из варианта для поиска
                    search_variant = self.remove_quotes_for_search(variant)
                    self.humanizer.human_like_type(self.browser, search, search_variant)
                    self.humanizer.random_mouse_movement(self.browser, search)
                    search.send_keys(Keys.ENTER)
                    self.humanizer.human_like_wait(rd.uniform(1.0, 2.0))

                    self._handle_rusprofile_captcha()
                except TimeoutException:
                    # Очищаем результат перед следующей попыткой
                    result["found"] = False
                    result["name"] = ""
                    result["address"] = ""
                    result["postal_code"] = ""
                    result["inn"] = ""
                    result["ogrn"] = ""
                    result["name_genitive"] = ""
                    continue

                # Проверяем результаты
                try:
                    search_result = self.humanizer.human_like_wait_for_element(
                        self.browser, (By.CLASS_NAME, "list-element__title"), 5
                    )
                    if not search_result:
                        self.log(f"     ⚠️ Нет результатов")
                        # Очищаем результат перед следующей попыткой
                        result["found"] = False
                        result["name"] = ""
                        result["address"] = ""
                        result["postal_code"] = ""
                        result["inn"] = ""
                        result["ogrn"] = ""
                        result["name_genitive"] = ""
                        continue
                except TimeoutException:
                    self.log(f"     ⚠️ Нет результатов")
                    # Очищаем результат перед следующей попыткой
                    result["found"] = False
                    result["name"] = ""
                    result["address"] = ""
                    result["postal_code"] = ""
                    result["inn"] = ""
                    result["ogrn"] = ""
                    result["name_genitive"] = ""
                    continue

                self.humanizer.human_like_scroll(self.browser)
                soup = BS(self.browser.page_source, "lxml")
                publications = soup.find_all("a", {"class": "list-element__title"})

                if not publications:
                    self.log(f"     ⚠️ Пустой список")
                    # Очищаем результат перед следующей попыткой
                    result["found"] = False
                    result["name"] = ""
                    result["address"] = ""
                    result["postal_code"] = ""
                    result["inn"] = ""
                    result["ogrn"] = ""
                    result["name_genitive"] = ""
                    continue

                self.log(f"     ✓ Найдено: {len(publications)} результат(ов)")

                # Открываем первый результат
                link = publications[0]["href"]
                try:
                    link_element = self.humanizer.human_like_wait_for_element(
                        self.browser, (By.XPATH, f"//a[@href='{link}']"), 5
                    )
                    if link_element:
                        self.humanizer.human_like_click(self.browser, link_element)
                    else:
                        self.browser.get(main_url + link)
                except TimeoutException:
                    self.browser.get(main_url + link)

                self.humanizer.human_like_wait(rd.uniform(1.0, 2.0))
                self.humanizer.human_like_scroll(self.browser)

                # Проверяем, загрузилась ли страница организации
                if self._extract_organization_data(result):
                    # Проверяем валидность найденной организации (используем оригинальное название)
                    if self._validate_organization_result(original_org_name, result):
                        self.log(f"  ✅ Успешно найдено (вариант {attempt})")
                        return result
                    else:
                        self.log(f"     ⚠️ Найденная организация не прошла проверку валидности, продолжаю поиск...")
                        # Полностью очищаем результат для следующей попытки
                        result["found"] = False
                        result["name"] = ""
                        result["address"] = ""
                        result["postal_code"] = ""
                        result["inn"] = ""
                        result["ogrn"] = ""
                        result["name_genitive"] = ""
                        continue
                else:
                    self.log(f"     ⚠️ Не удалось извлечь данные")
                    # Очищаем результат на случай, если там остались данные от предыдущей попытки
                    result["found"] = False
                    result["name"] = ""
                    result["address"] = ""
                    result["postal_code"] = ""
                    result["inn"] = ""
                    result["ogrn"] = ""
                    result["name_genitive"] = ""
                    continue

            except Exception as e:
                self.log(f"     ⚠️ Ошибка при попытке {attempt}: {str(e)}")
                # Очищаем результат на случай ошибки
                result["found"] = False
                result["name"] = ""
                result["address"] = ""
                result["postal_code"] = ""
                result["inn"] = ""
                result["ogrn"] = ""
                result["name_genitive"] = ""
                continue

        self.log(f"  ❌ Не найдено ни по одному варианту")
        return result

    def _search_by_inn(self, main_url, inn, result):
        """Поиск по ИНН (исходная логика)"""
        self.browser.get(f"{main_url}/search?query={inn}")
        self.humanizer.human_like_wait(rd.uniform(1.5, 2.5))

        self._handle_rusprofile_captcha()

        # Проверяем, открылась ли сразу страница организации
        try:
            name_elem = self.humanizer.human_like_wait_for_element(
                self.browser, (By.ID, "clip_name-long"), 3
            )
            if name_elem:
                self.log("  ✓ Организация найдена сразу по ИНН")
                self.humanizer.human_like_scroll(self.browser)
                if self._extract_organization_data(result):
                    # Проверяем валидность (для поиска по ИНН не проверяем совпадение ключевых слов)
                    if self._validate_organization_result("", result, check_keyword_match=False):
                        return result
        except TimeoutException:
            pass

        # Если не открылась сразу, ищем в списке результатов
        try:
            search_result = self.humanizer.human_like_wait_for_element(
                self.browser, (By.CLASS_NAME, "list-element__title"), 5
            )
            if search_result:
                self.humanizer.human_like_scroll(self.browser)
                soup = BS(self.browser.page_source, "lxml")
                publications = soup.find_all("a", {"class": "list-element__title"})

                if publications:
                    self.log(f"  ✓ Найдено результатов: {len(publications)}")
                    link = publications[0]["href"]
                    self.browser.get(main_url + link)
                    self.humanizer.human_like_wait(rd.uniform(1.0, 2.0))
                    self._handle_rusprofile_captcha()
                    self.humanizer.human_like_scroll(self.browser)

                    if self._extract_organization_data(result):
                        # Проверяем валидность (для поиска по ИНН проверка менее строгая)
                        if self._validate_organization_result("", result):
                            return result
        except TimeoutException:
            pass

        self.log("  ⚠️ Нет результатов")
        return result

    def _extract_organization_data(self, result):
        """Извлекает данные организации со страницы"""
        try:
            name_elem = self.humanizer.human_like_wait_for_element(
                self.browser, (By.ID, "clip_name-long"), 10
            )
            address_elem = self.humanizer.human_like_wait_for_element(
                self.browser, (By.ID, "clip_address"), 10
            )

            if not name_elem or not address_elem:
                return False

            result["name"] = name_elem.text.strip()
            result["name"] = self.normalize_organization_name(result["name"])
            result["name_genitive"] = self.get_genitive_case_pymorphy(result["name"])
            result["address"] = address_elem.text.strip()

            # Извлекаем почтовый индекс
            postal_match = re.search(r"\b(\d{6})\b", result["address"])
            if postal_match:
                result["postal_code"] = postal_match.group(1)

            # Извлекаем ИНН и ОГРН
            page_text = self.browser.find_element(By.TAG_NAME, "body").text
            inn_match = re.search(r"ИНН[:\s]*(\d{10,12})", page_text)
            ogrn_match = re.search(r"ОГРН[:\s]*(\d{13,15})", page_text)

            if inn_match:
                result["inn"] = inn_match.group(1)
            if ogrn_match:
                result["ogrn"] = ogrn_match.group(1)

            result["found"] = True
            self.log(f"  ✅ ИНН: {result.get('inn')}  ОГРН: {result.get('ogrn')}")
            self.log(f"  📝 {result['name'][:70]}...")
            self.log(f"  📍 {result['address'][:70]}...")

            return True

        except TimeoutException:
            return False
        except Exception as e:
            self.log(f"  ⚠️ Ошибка извлечения данных: {str(e)}")
            return False


class KonturFokusSearcher(BaseSearcher):
    """Класс для поиска организаций в Контур Фокус"""

    def search(self, org_name=None, inn=None):
        """Поиск в Контур Фокус по названию или ИНН"""
        result = {
            "found": False,
            "name": "",
            "address": "",
            "inn": "",
            "ogrn": "",
            "postal_code": "",
            "name_genitive": "",
        }

        try:
            query = inn if inn else org_name
            if not query:
                return result

            # Убираем кавычки из запроса для поиска
            if not inn:
                query = self.remove_quotes_for_search(query)

            url = f"https://focus.kontur.ru/search?country=RU&query={query}"
            self.browser.get(url)
            self.humanizer.human_like_wait(rd.uniform(0.5, 1.0))

            try:
                self.humanizer.human_like_wait_for_element(
                    self.browser, (By.XPATH, "//*[contains(text(), 'ИНН')]"), 5
                )
                self.humanizer.human_like_wait(rd.uniform(1, 2))
                self.humanizer.human_like_scroll(self.browser)

                page_text = self.browser.find_element(By.TAG_NAME, "body").text

                if "не найдено" in page_text:
                    self.log("  ⚠️ Нет результатов")
                    return result

                inn_match = re.search(r"ИНН[:\s]*(\d{10,12})", page_text)
                if inn_match:
                    result["inn"] = inn_match.group(1)

                ogrn_match = re.search(r"ОГРН[:\s]*(\d{13,15})", page_text)
                if ogrn_match:
                    result["ogrn"] = ogrn_match.group(1)

                # Поиск полного названия
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
                            "БЮДЖЕТНАЯ",
                            "АВТОНОМНОЕ",
                            "ГОСУДАРСТВЕННОЕ",
                            "МУНИЦИПАЛЬНОЕ",
                            "ОБЩЕОБРАЗОВАТЕЛЬНОЕ",
                            "НЕКОММЕРЧЕСКОЕ",
                            "БЮДЖЕТНОЕ",
                        ]
                    ):
                        if len(line) > 10 and "ИНН" not in line:
                            result["name"] = line.strip()
                            result["name_genitive"] = self.get_genitive_case_pymorphy(
                                result["name"]
                            )
                            break

                # Поиск адреса
                address_match = re.search(
                    r"(\d{6})[,\s]+([^\n]+(?:обл|край|респ|г\.|г |область|севастополь)[^\n]+)",
                    page_text,
                    re.IGNORECASE,
                )
                if address_match:
                    result["address"] = (
                        address_match.group(1) + ", " + address_match.group(2).strip()
                    )
                    result["postal_code"] = address_match.group(1)

                if result["inn"] or result["name"]:
                    result["found"] = True
                    self.log(f"  ✅ ИНН: {result['inn']}, ОГРН: {result['ogrn']}")

                    if result["name"]:
                        self.log(f"  📝 {result['name'][:70]}...")
                    else:
                        self.log("  ⚠️ Название не найдено")

                    if result["address"]:
                        self.log(f"  📍 {result['address'][:70]}...")

            except TimeoutException:
                self.log("  ⏱️ Timeout")

        except Exception as e:
            self.log(f"  ⚠️ Ошибка: {str(e)}")

        return result


class EgrulSearcher(BaseSearcher):
    """Класс для поиска организаций в ЕГРЮЛ"""

    def _load_standardization_rules(self):
        """Загрузка правил стандартизации"""
        if hasattr(self, "_std_rules"):
            return self._std_rules

        try:
            rules_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "standardization_rules.json"
            )
            with open(rules_path, "r", encoding="utf-8") as f:
                self._std_rules = json.load(f)
                return self._std_rules
        except Exception as e:
            self.log(f"  ⚠️ Не удалось загрузить standardization_rules.json: {e}")
            # Возвращаем минимальный набор правил
            self._std_rules = {"abbreviations": {}, "type_synonyms": {}}
            return self._std_rules

    def _expand_abbreviations(self, text):
        """Расширяет аббревиатуры в тексте для лучшего сопоставления"""
        rules = self._load_standardization_rules()

        expanded_variants = [text.lower()]

        # Добавляем варианты с расшифрованными аббревиатурами
        for abbr, full_form in rules.get("abbreviations", {}).items():
            if abbr.lower() in text.lower():
                variant = re.sub(
                    r"\b" + re.escape(abbr) + r"\b",
                    full_form,
                    text,
                    flags=re.IGNORECASE,
                )
                expanded_variants.append(variant.lower())

        # Добавляем синонимы типов учреждений
        for type_name, synonyms in rules.get("type_synonyms", {}).items():
            if type_name.lower() in text.lower():
                for synonym in synonyms:
                    expanded_variants.append(synonym.lower())

        return expanded_variants

    def _find_best_educational_match(self, results, query):
        """
        Находит наиболее релевантное образовательное учреждение из результатов

        Использует standardization_rules.json для умного сопоставления
        """

        rules = self._load_standardization_rules()

        # Создаем набор образовательных ключевых слов из правил
        edu_keywords = set()

        # Добавляем все аббревиатуры
        for abbr in rules.get("abbreviations", {}).keys():
            edu_keywords.add(abbr.lower())

        # Добавляем распространенные слова
        edu_keywords.update(
            [
                "школа",
                "сош",
                "лицей",
                "гимназия",
                "колледж",
                "университет",
                "институт",
                "училище",
                "образовательн",
                "учреждение",
                "детский сад",
            ]
        )

        # Негативные ключевые слова
        negative_keywords = [
            "прекращение деятельности",
            "ликвидатор",
            "ликвидационной комиссии",
            "признания регистрации недействительной",
            "театр",
            "религиозная",
            "приход",
            "храм",
            "церковь",
            "товарищество",
            "снт",
            "тсн",
        ]

        # Извлекаем числа из запроса
        query_numbers = set(re.findall(r"\b\d+\b", query))

        # Получаем расширенные варианты запроса
        query_variants = self._expand_abbreviations(query)

        candidates = []

        for res in results:
            try:
                text = res.text.lower()

                # 1. Проверка на негативные слова
                if any(neg in text for neg in negative_keywords):
                    continue

                # 2. Проверка, что это образовательное учреждение
                is_educational = any(keyword in text for keyword in edu_keywords)
                if not is_educational:
                    continue

                # 3. ОБЯЗАТЕЛЬНАЯ проверка совпадения чисел
                result_numbers = set(re.findall(r"\b\d+\b", text))

                if query_numbers:
                    if not query_numbers.intersection(result_numbers):
                        continue

                # 4. Подсчет релевантности
                score = 0

                # Бонус за совпадение чисел (очень важно!)
                score += len(query_numbers.intersection(result_numbers)) * 15

                # Бонус за совпадение слов из ВСЕХ вариантов запроса
                for variant in query_variants:
                    variant_words = set(re.findall(r"\b[а-яё]{3,}\b", variant))
                    result_words = set(re.findall(r"\b[а-яё]{3,}\b", text))
                    score += len(variant_words.intersection(result_words)) * 3

                # Бонус за совпадение аббревиатур
                for abbr in rules.get("abbreviations", {}).keys():
                    if abbr.lower() in query.lower() and abbr.lower() in text:
                        score += 8

                # Бонус за точное совпадение типа учреждения
                for type_name, synonyms in rules.get("type_synonyms", {}).items():
                    if type_name.lower() in query.lower():
                        if type_name.lower() in text or any(
                            syn.lower() in text for syn in synonyms
                        ):
                            score += 10

                # Штраф за несовпадение региона (если регион указан)
                query_region_words = {
                    "москв",
                    "московск",
                    "спб",
                    "петербург",
                    "липецк",
                    "одинцов",
                }
                for region in query_region_words:
                    if region in query.lower() and region not in text:
                        score -= 5

                candidates.append((score, res, text))

            except Exception as e:
                continue

        if not candidates:
            return None

        # Сортируем по убыванию релевантности
        candidates.sort(key=lambda x: x[0], reverse=True)

        self.log(f"  📊 Релевантность топ-3:")
        for i, (score, _, text) in enumerate(candidates[:3], 1):
            self.log(f"    {i}. {score} баллов - {text[:60]}...")

        return candidates[0][1]

    def search(self, org_name):
        """Поиск в ЕГРЮЛ с умной фильтрацией результатов"""
        result = {
            "found": False,
            "address": "",
            "postal_code": "",
        }

        try:
            url = "https://egrul.nalog.ru/"
            self.browser.get(url)
            self.humanizer.human_like_wait(rd.uniform(0.5, 1.0))

            try:
                search_field = self.humanizer.human_like_wait_for_element(
                    self.browser, (By.ID, "query"), 7
                )
                if not search_field:
                    self.log("  ⚠️ Поле поиска не найдено")
                    return result

                # Убираем кавычки из названия для поиска
                search_org_name = self.remove_quotes_for_search(org_name)
                self.humanizer.human_like_type(self.browser, search_field, search_org_name)
                self.humanizer.random_mouse_movement(self.browser, search_field)
                search_field.send_keys(Keys.RETURN)

                self.humanizer.human_like_wait_for_element(
                    self.browser, (By.CLASS_NAME, "res-text"), 10
                )
                self.humanizer.human_like_wait(rd.uniform(1.0, 1.5))
                self.humanizer.human_like_scroll(self.browser)

                # Ищем все результаты
                try:
                    all_results = self.browser.find_elements(
                        By.CSS_SELECTOR, ".res-text"
                    )

                    if not all_results:
                        self.log("  ⚠️ Нет результатов")
                        return result

                    self.log(f"  🔍 Найдено результатов: {len(all_results)}")

                    # Фильтруем результаты по релевантности
                    best_match = self._find_best_educational_match(
                        all_results, org_name
                    )

                    if not best_match:
                        self.log("  ⚠️ Не найдено подходящих образовательных учреждений")
                        return result

                    # Кликаем на лучшее совпадение
                    result_link = best_match.find_element(By.TAG_NAME, "a")
                    self.log(f"  ✓ Выбрано: {result_link.text[:50]}...")

                    self.humanizer.human_like_click(self.browser, result_link)
                    self.humanizer.human_like_wait(rd.uniform(1.5, 2.5))
                    self.humanizer.human_like_scroll(self.browser)

                    detail_text = self.browser.find_element(By.TAG_NAME, "body").text

                    # Извлекаем данные
                    inn_match = re.search(r"ИНН[:\s]*(\d{10,12})", detail_text)
                    if inn_match:
                        result["inn"] = inn_match.group(1)

                    ogrn_match = re.search(r"ОГРН[:\s]*(\d{13,15})", detail_text)
                    if ogrn_match:
                        result["ogrn"] = ogrn_match.group(1)

                    name_match = re.search(
                        r"Полное наименование[:\s]*([^\n]+)", detail_text
                    )
                    if name_match:
                        result["name"] = name_match.group(1).strip()
                        result["name_genitive"] = self.get_genitive_case_pymorphy(
                            result["name"]
                        )

                    address_match = re.search(r"Адрес[:\s]*([^\n]+)", detail_text)
                    if address_match:
                        result["address"] = address_match.group(1).strip()
                        postal_match = re.search(r"\b(\d{6})\b", result["address"])
                        if postal_match:
                            result["postal_code"] = postal_match.group(1)

                    # Если есть полные данные
                    if result.get("name") and result.get("address"):
                        result["found"] = True
                        self.log(
                            f"  ✅ ИНН: {result.get('inn')}, ОГРН: {result.get('ogrn')}"
                        )
                        self.log(f"  📝 {result['name'][:70]}...")
                        self.log(f"  📍 {result['address'][:70]}...")
                    elif result.get("inn") or result.get("ogrn"):
                        result["found"] = False
                        self.log(
                            f"  ⚠️ Найден только ИНН: {result.get('inn')} (без полных данных)"
                        )

                except Exception as e:
                    self.log(f"  ⚠️ Ошибка при фильтрации: {e}")
                    return result

            except TimeoutException:
                self.log("  ⏱️ Timeout")

        except Exception as e:
            self.log(f"  ⚠️ Ошибка: {str(e)}")

        return result


class OrganizationParser:
    """Класс для парсинга информации об организациях"""

    def __init__(
        self,
        log_callback=None,
        use_gigachat=False,
        gigachat_api=None,
        gigachat_retries=3,
        use_recaptcha_solver=False,
        recaptcha_api_key=None,
        humanization_mode="normal",
    ):
        self.log_callback = log_callback
        self.browser = None
        self.humanizer = Humanization(mode=humanization_mode)
        self.use_gigachat = use_gigachat
        self.gigachat_api = gigachat_api
        self.gigachat_retries = gigachat_retries

        self.use_recaptcha_solver = use_recaptcha_solver
        self.recaptcha_solver = None
        if use_recaptcha_solver and recaptcha_api_key:
            try:
                self.recaptcha_solver = ReCaptchaSolver(
                    api_key=recaptcha_api_key, log_callback=self.log
                )
                self.log("✅ Автоматическое решение капчи включено")
            except Exception as e:
                self.log(f"⚠️ Не удалось инициализировать решатель капчи: {e}")

        # Инициализируем сеарчеры (после инициализации браузера)
        self.rusprofile_searcher = None
        self.kontur_fokus_searcher = None
        self.egrul_searcher = None

    def log(self, message):
        """Вывод сообщения в лог"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def init_browser(self):
        """Инициализация браузера Chrome"""
        chrome_options = wd.ChromeOptions()
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--incognito")
        if not config.AppSettings.is_dev_mode:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        with open("user_agents.json", "r", encoding="utf-8") as f:
            user_agents = json.load(f)
        selected_user_agent = rd.choice(user_agents)
        chrome_options.add_argument(f"--user-agent={selected_user_agent}")

        self.log("\n🌐 ЭТАП 2: Поиск в базах данных")
        self.log("=" * 60)
        self.log("🚀 Запуск браузера...")
        self.browser = wd.Chrome(options=chrome_options)
        self.browser.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.humanizer.human_like_wait(rd.uniform(0.5, 1.5))

        # Инициализируем сеарчеры после создания браузера
        self.rusprofile_searcher = RusProfileSearcher(
            browser=self.browser,
            humanizer=self.humanizer,
            log_callback=self.log_callback,
            use_recaptcha_solver=self.use_recaptcha_solver,
            recaptcha_solver=self.recaptcha_solver,
        )
        self.kontur_fokus_searcher = KonturFokusSearcher(
            browser=self.browser,
            humanizer=self.humanizer,
            log_callback=self.log_callback,
        )
        self.egrul_searcher = EgrulSearcher(
            browser=self.browser,
            humanizer=self.humanizer,
            log_callback=self.log_callback,
        )

    def close_browser(self):
        """Закрытие браузера"""
        if self.browser:
            self.browser.quit()
            self.log("✅ Браузер закрыт")

    def search_organization(self, org_name):
        """Каскадный поиск организации через разные источники"""
        result = {
            "name": "",
            "address": "",
            "postal_code": "",
            "inn": "",
            "ogrn": "",
            "source": "Не найдено",
        }

        # 1. RusProfile
        self.log("🔍 Поиск в RusProfile...")
        rusprofile_result = self.rusprofile_searcher.search(org_name=org_name)
        if rusprofile_result["found"]:
            result.update(rusprofile_result)
            result["source"] = "RusProfile"
            return result

        # 2. Контур Фокус
        self.log("🔍 Поиск в Контур Фокус...")
        fokus_result = self.kontur_fokus_searcher.search(org_name=org_name)
        if fokus_result["found"]:
            result.update(fokus_result)
            result["source"] = "Контур Фокус"
            return result

        # 3. ЕГРЮЛ - ищем ИНН и полные данные
        self.log("🔍 Поиск в ЕГРЮЛ...")
        egrul_result = self.egrul_searcher.search(org_name)
        if egrul_result["found"]:
            result.update(egrul_result)
            result["source"] = "ЕГРЮЛ"
            return result

        # Если в ЕГРЮЛ нашли ИНН (но не полные данные), пробуем повторить поиск по ИНН
        if egrul_result.get("inn"):
            self.log(
                f"  🔗 Найден ИНН в ЕГРЮЛ: {egrul_result.get('inn')}, повторный поиск..."
            )

            # Пробуем RusProfile по ИНН
            self.log("  🔍 Повторный поиск в RusProfile по ИНН...")
            rusprofile_result = self.rusprofile_searcher.search(inn=egrul_result.get("inn"))
            if rusprofile_result["found"]:
                result.update(rusprofile_result)
                result["source"] = "ЕГРЮЛ → RusProfile"
                return result

            # Пробуем Контур Фокус по ИНН
            self.log("  🔍 Повторный поиск в Контур Фокус по ИНН...")
            fokus_result = self.kontur_fokus_searcher.search(
                org_name=None, inn=egrul_result.get("inn")
            )
            if fokus_result["found"]:
                result.update(fokus_result)
                result["source"] = "ЕГРЮЛ → Контур Фокус"
                return result

        # 4. GigaChat - прямой поиск в ЕГРЮЛ через AI (если включен)
        if self.gigachat_api:
            self.log("🤖 Поиск через GigaChat (прямой запрос в ЕГРЮЛ)...")
            gigachat_result = self.search_with_gigachat(org_name)
            if gigachat_result["found"]:
                result.update(gigachat_result)
                result["source"] = "GigaChat (ЕГРЮЛ)"
                return result

        self.log("❌ Не найдено нигде")
        return result

    # Методы get_genitive_case_pymorphy и normalize_organization_name теперь в BaseSearcher
    # Оставляем их для обратной совместимости
    @staticmethod
    def get_genitive_case_pymorphy(org_name):
        """Получение родительного падежа через pymorphy3 (делегирует в BaseSearcher)"""
        return BaseSearcher.get_genitive_case_pymorphy(org_name)

    @staticmethod
    def normalize_organization_name(name):
        """Нормализация названия организации (делегирует в BaseSearcher)"""
        return BaseSearcher.normalize_organization_name(name)

    # Старые методы поиска оставлены для обратной совместимости, но делегируют в сеарчеры
    def search_rusprofile(self, org_name=None, inn=None):
        """Поиск в RusProfile (делегирует в RusProfileSearcher)"""
        if not self.rusprofile_searcher:
            # Если браузер еще не инициализирован, возвращаем пустой результат
            return {"found": False}
        return self.rusprofile_searcher.search(org_name=org_name, inn=inn)

    def search_kontur_fokus(self, org_name=None, inn=None):
        """Поиск в Контур Фокус (делегирует в KonturFokusSearcher)"""
        if not self.kontur_fokus_searcher:
            return {"found": False}
        return self.kontur_fokus_searcher.search(org_name=org_name, inn=inn)

    def search_egrul(self, org_name):
        """Поиск в ЕГРЮЛ (делегирует в EgrulSearcher)"""
        if not self.egrul_searcher:
            return {"found": False}
        return self.egrul_searcher.search(org_name)

    # Удаленные методы (теперь в соответствующих сеарчерах):
    # - _handle_rusprofile_captcha -> RusProfileSearcher
    # - generate_search_variants -> RusProfileSearcher
    # - _search_by_name_with_variants -> RusProfileSearcher
    # - _search_by_inn -> RusProfileSearcher
    # - _extract_organization_data -> RusProfileSearcher
    # - _load_standardization_rules -> EgrulSearcher
    # - _expand_abbreviations -> EgrulSearcher
    # - _find_best_educational_match -> EgrulSearcher

    def search_with_gigachat(self, org_name):
        """Прямой поиск в ЕГРЮЛ через GigaChat"""
        result = {
            "found": False,
            "address": "",
            "postal_code": "",
        }

        try:
            gigachat_result = self.gigachat_api.search_organization_in_egrul(org_name)

            if gigachat_result["found"]:
                result.update(gigachat_result)
                return result
            else:
                self.log("  ⚠️ GigaChat не нашел организацию")

        except Exception as e:
            self.log(f"  ⚠️ Ошибка GigaChat: {str(e)}")

        return result
