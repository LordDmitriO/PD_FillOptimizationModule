"""
Модуль для парсинга данных организаций из различных источников
"""

import re
import json
import random as rd
import tempfile
import pymorphy3
from selenium import webdriver as wd
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup as BS

import config
from .humanization import Humanization


class OrganizationParser:
    """Класс для парсинга информации об организациях"""

    def __init__(
        self,
        log_callback=None,
        use_gigachat=False,
        gigachat_api=None,
        gigachat_retries=3,
    ):
        self.log_callback = log_callback
        self.browser = None
        self.humanizer = Humanization()
        self.use_gigachat = use_gigachat
        self.gigachat_api = gigachat_api
        self.gigachat_retries = gigachat_retries

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
        chrome_options.add_argument(f'--user-agent={selected_user_agent}')

        self.log("\n🌐 ЭТАП 2: Поиск в базах данных")
        self.log("=" * 60)
        self.log("🚀 Запуск браузера...")
        self.browser = wd.Chrome(options=chrome_options)
        self.browser.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.humanizer.human_like_wait(rd.uniform(0.5, 1.5))

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
        rusprofile_result = self.search_rusprofile(org_name)
        if rusprofile_result["found"]:
            result.update(rusprofile_result)
            result["source"] = "RusProfile"
            return result

        # 2. Контур Фокус
        self.log("🔍 Поиск в Контур Фокус...")
        fokus_result = self.search_kontur_fokus(org_name)
        if fokus_result["found"]:
            result.update(fokus_result)
            result["source"] = "Контур Фокус"
            return result

        # 3. ЕГРЮЛ - ищем ИНН и полные данные
        self.log("🔍 Поиск в ЕГРЮЛ...")
        egrul_result = self.search_egrul(org_name)
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
            rusprofile_result = self.search_rusprofile(inn=egrul_result.get("inn"))
            if rusprofile_result["found"]:
                result.update(rusprofile_result)
                result["source"] = "ЕГРЮЛ → RusProfile"
                return result

            # Пробуем Контур Фокус по ИНН
            self.log("  🔍 Повторный поиск в Контур Фокус по ИНН...")
            fokus_result = self.search_kontur_fokus(
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

    @staticmethod
    def get_genitive_case_pymorphy(org_name):
        """Получение родительного падежа через pymorphy3"""
        if not org_name:
            return org_name
        
        morph = pymorphy3.MorphAnalyzer()  # ← Изменено на pymorphy3
        
        # Остальной код остается без изменений
        words = org_name.split()
        genitive_words = []
        
        for word in words:
            if word.startswith(('«', '"', '"')) or word.endswith(('»', '"', '"')):
                genitive_words.append(word)
            else:
                clean_word = word.strip('.,;:!?')
                punct = word[len(clean_word):] if len(word) > len(clean_word) else ''
                
                parsed = morph.parse(clean_word)[0]
                genitive_form = parsed.inflect({'gent'})
                
                if genitive_form:
                    genitive_words.append(genitive_form.word.capitalize() if clean_word[0].isupper() else genitive_form.word + punct)
                else:
                    genitive_words.append(word)
        
        return ' '.join(genitive_words)

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
                normalized_before = ' '.join(normalized_words)
                if before_text.endswith(' '):
                    normalized_before += ' '
                result.append(normalized_before)
            
            # Обрабатываем текст В кавычках
            quoted_text = match.group()
            opening_quote = quoted_text[0]
            closing_quote = quoted_text[-1]
            inner_text = quoted_text[1:-1]
            
            # Приводим к нормальному виду: первая буква заглавная, остальные строчные
            normalized_inner = inner_text.capitalize()
            result.append(f'{opening_quote}{normalized_inner}{closing_quote}')
            
            last_end = end
        
        # Обрабатываем остаток текста ПОСЛЕ последних кавычек (если есть)
        if last_end < len(name):
            after_text = name[last_end:]
            words = after_text.split()
            normalized_words = [word.lower() for word in words]
            result.append(' '.join(normalized_words))
        
        return ''.join(result)

    def search_rusprofile(self, org_name=None, inn=None):
        """Поиск в RusProfile по названию или ИНН"""
        result = {"found": False}

        try:
            main_url = "https://www.rusprofile.ru"

            if inn:
                # Поиск по ИНН
                self.browser.get(f"{main_url}/search?query={inn}")
                self.humanizer.human_like_wait(rd.uniform(1.5, 2.5))

                # Проверяем, открылась ли сразу страница организации
                try:
                    name_elem = self.humanizer.human_like_wait_for_element(
                        self.browser, (By.ID, "clip_name-long"), 3
                    )
                    if name_elem:
                        self.log("  ✓ Организация найдена сразу по ИНН")
                        self.humanizer.human_like_scroll(self.browser)
                    else:
                        # Список результатов
                        try:
                            search_result = self.humanizer.human_like_wait_for_element(
                                self.browser, (By.CLASS_NAME, "list-element__title"), 5
                            )
                            if search_result:
                                self.humanizer.human_like_scroll(self.browser)
                                soup = BS(self.browser.page_source, "lxml")
                                publications = soup.find_all(
                                    "a", {"class": "list-element__title"}
                                )

                                if publications:
                                    self.log(
                                        f"  ✓ Найдено результатов: {len(publications)}"
                                    )
                                    link = publications[0]["href"]
                                    self.browser.get(main_url + link)
                                    self.humanizer.human_like_wait(rd.uniform(1.0, 2.0))
                                    self.humanizer.human_like_scroll(self.browser)
                                else:
                                    self.log("  ⚠️ Пустой список")
                                    return result
                            else:
                                self.log("  ⚠️ Нет результатов")
                                return result
                        except TimeoutException:
                            self.log("  ⚠️ Нет результатов")
                            return result
                except TimeoutException:
                    # Проверяем список результатов
                    try:
                        search_result = self.humanizer.human_like_wait_for_element(
                            self.browser, (By.CLASS_NAME, "list-element__title"), 5
                        )
                        if search_result:
                            self.humanizer.human_like_scroll(self.browser)
                            soup = BS(self.browser.page_source, "lxml")
                            publications = soup.find_all(
                                "a", {"class": "list-element__title"}
                            )

                            if publications:
                                self.log(
                                    f"  ✓ Найдено результатов: {len(publications)}"
                                )
                                link = publications[0]["href"]
                                self.browser.get(main_url + link)
                                self.humanizer.human_like_wait(rd.uniform(1.0, 2.0))
                                self.humanizer.human_like_scroll(self.browser)
                            else:
                                self.log("  ⚠️ Пустой список")
                                return result
                        else:
                            self.log("  ⚠️ Нет результатов")
                            return result
                    except TimeoutException:
                        self.log("  ⚠️ Нет результатов")
                        return result
            else:
                # Поиск по названию - расширенный поиск
                self.browser.get(main_url + "/search-advanced")
                self.humanizer.human_like_wait(rd.uniform(0.5, 1.0))

                try:
                    search = self.humanizer.human_like_wait_for_element(
                        self.browser, (By.ID, "advanced-search-query"), 10
                    )
                    if not search:
                        self.log("  ⚠️ Не загрузился поиск")
                        return result

                    self.humanizer.human_like_type(self.browser, search, org_name)
                    self.humanizer.random_mouse_movement(self.browser, search)
                    search.send_keys(Keys.ENTER)
                    self.humanizer.human_like_wait(rd.uniform(1.0, 2.0))
                except TimeoutException:
                    self.log("  ⚠️ Не загрузился поиск")
                    return result

                try:
                    search_result = self.humanizer.human_like_wait_for_element(
                        self.browser, (By.CLASS_NAME, "list-element__title"), 10
                    )
                    if not search_result:
                        self.log("  ⚠️ Нет результатов")
                        return result
                    self.humanizer.human_like_wait(rd.uniform(0.5, 1.0))
                except TimeoutException:
                    self.log("  ⚠️ Нет результатов")
                    return result

                self.humanizer.human_like_scroll(self.browser)
                soup = BS(self.browser.page_source, "lxml")
                publications = soup.find_all("a", {"class": "list-element__title"})

                if not publications:
                    self.log("  ⚠️ Пустой список")
                    return result

                self.log(f"  ✓ Найдено результатов: {len(publications)}")

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

            try:
                name_elem = self.humanizer.human_like_wait_for_element(
                    self.browser, (By.ID, "clip_name-long"), 10
                )
                address_elem = self.humanizer.human_like_wait_for_element(
                    self.browser, (By.ID, "clip_address"), 10
                )
                if not name_elem or not address_elem:
                    self.log("  ⚠️ Не загрузились элементы")
                    return result
            except TimeoutException:
                self.log("  ⚠️ Не загрузились элементы")
                return result

            result["name"] = name_elem.text.strip()
            result["name"] = self.normalize_organization_name(result["name"])
            result["name_genitive"] = self.get_genitive_case_pymorphy(result["name"])
            result["address"] = address_elem.text.strip()

            postal_match = re.search(r"\b(\d{6})\b", result["address"])
            if postal_match:
                result["postal_code"] = postal_match.group(1)

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

        except Exception as e:
            self.log(f"  ⚠️ Ошибка: {str(e)}")

        return result

    def search_kontur_fokus(self, org_name=None, inn=None):
        """Поиск в Контур Фокус по названию или ИНН"""
        result = {"found": False}

        try:
            query = inn if inn else org_name
            if not query:
                return result

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

                if "Найдено 0" in page_text or "Ничего не найдено" in page_text:
                    self.log("  ⚠️ Нет результатов")
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
                            result["name_genitive"] = self.get_genitive_case_pymorphy(result["name"])
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
                    self.log(f"  ✅ ИНН: {result['inn']}, ОГРН: {result['ogrn']}")
                    if result["name"]:
                        self.log(f"  📝 {result['name'][:70]}...")
                    if result["address"]:
                        self.log(f"  📍 {result['address'][:70]}...")

            except TimeoutException:
                self.log("  ⏱️ Timeout")

        except Exception as e:
            self.log(f"  ⚠️ Ошибка: {str(e)}")

        return result

    def search_egrul(self, org_name):
        """Поиск в ЕГРЮЛ"""
        result = {"found": False}

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

                self.humanizer.human_like_type(self.browser, search_field, org_name)
                self.humanizer.random_mouse_movement(self.browser, search_field)
                search_field.send_keys(Keys.RETURN)

                self.humanizer.human_like_wait_for_element(
                    self.browser, (By.CLASS_NAME, "res-text"), 10
                )
                self.humanizer.human_like_wait(rd.uniform(1.0, 1.5))
                self.humanizer.human_like_scroll(self.browser)

                page_text = self.browser.find_element(By.TAG_NAME, "body").text

                inn_match = re.search(r"ИНН[:\s]*(\d{10,12})", page_text)
                ogrn_match = re.search(r"ОГРН[:\s]*(\d{13,15})", page_text)

                if inn_match:
                    result["inn"] = inn_match.group(1)
                if ogrn_match:
                    result["ogrn"] = ogrn_match.group(1)

                try:
                    first_result = self.humanizer.human_like_wait_for_element(
                        self.browser, (By.CSS_SELECTOR, ".res-text a"), 5
                    )
                    if first_result:
                        self.humanizer.human_like_click(self.browser, first_result)
                        self.humanizer.human_like_wait(rd.uniform(1.5, 2.5))
                        self.humanizer.human_like_scroll(self.browser)
                    detail_text = self.browser.find_element(By.TAG_NAME, "body").text

                    name_match = re.search(
                        r"Полное наименование[:\s]*([^\n]+)", detail_text
                    )
                    if name_match:
                        result["name"] = name_match.group(1).strip()
                        result["name_genitive"] = self.get_genitive_case_pymorphy(result["name"])

                    address_match = re.search(r"Адрес[:\s]*([^\n]+)", detail_text)
                    if address_match:
                        result["address"] = address_match.group(1).strip()
                        postal_match = re.search(r"\b(\d{6})\b", result["address"])
                        if postal_match:
                            result["postal_code"] = postal_match.group(1)
                except Exception:
                    pass

                # Если есть полные данные
                if result.get("name") and result.get("address"):
                    result["found"] = True
                    self.log(
                        f"  ✅ ИНН: {result.get('inn')}, ОГРН: {result.get('ogrn')}"
                    )
                    self.log(f"  📝 {result['name'][:70]}...")
                    self.log(f"  📍 {result['address'][:70]}...")
                # Если есть только ИНН - не помечаем как found
                elif result.get("inn") or result.get("ogrn"):
                    result["found"] = False
                    self.log(
                        f"  ⚠️ Найден только ИНН: {result.get('inn')} (без полных данных)"
                    )

            except TimeoutException:
                self.log("  ⏱️ Timeout")

        except Exception as e:
            self.log(f"  ⚠️ Ошибка: {str(e)}")

        return result

    def search_with_gigachat(self, org_name):
        """Прямой поиск в ЕГРЮЛ через GigaChat"""
        result = {"found": False}

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
