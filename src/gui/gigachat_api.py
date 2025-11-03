"""
Модуль для работы с GigaChat API
"""

import re
import requests
import json
from datetime import datetime, timedelta
import urllib3

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TokenManager:
    """Управление токеном GigaChat с автоматическим обновлением"""

    def __init__(self, auth_token, log_callback=None):
        """
        Args:
            auth_token: Base64 токен для авторизации (Basic токен)
            log_callback: Функция для логирования
        """
        self.auth_token = auth_token
        self.access_token = None
        self.token_expiry = None
        self.log_callback = log_callback

    def log(self, message):
        """Вывод сообщения в лог"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def get_token(self):
        """Получить действующий токен, обновить при необходимости"""
        if self.access_token is None or datetime.now() >= self.token_expiry:
            if not self.refresh_token():
                raise Exception("Не удалось обновить токен GigaChat")
        return self.access_token

    def refresh_token(self):
        """Обновить токен через API"""
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": "ccc3905b-2e41-4f73-9f34-3d1dceef0902",
            "Authorization": f"Basic {self.auth_token}",
        }
        data = {"scope": "GIGACHAT_API_PERS"}

        try:
            response = requests.post(
                url, headers=headers, data=data, verify=False, timeout=10
            )
            response.raise_for_status()
            result = response.json()
            self.access_token = result["access_token"]
            # Токен действует 30 минут, обновляем за 1 минуту до истечения
            self.token_expiry = datetime.now() + timedelta(minutes=29)
            self.log(
                f"✅ Токен GigaChat обновлен (до {self.token_expiry.strftime('%H:%M:%S')})"
            )
            return True
        except Exception as e:
            self.log(f"❌ Ошибка обновления токена: {e}")
            return False


class GigaChatAPI:
    """Класс для работы с GigaChat API"""

    def __init__(self, auth_token, log_callback=None):
        """
        Args:
            auth_token: Base64 токен для авторизации (Basic токен)
            log_callback: Функция для логирования
        """
        self.token_manager = TokenManager(auth_token, log_callback)
        self.api_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        self.log_callback = log_callback

    def log(self, message):
        """Вывод сообщения в лог"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def search_organization_in_egrul(self, raw_name):
        """
        Поиск организации в ЕГРЮЛ через GigaChat

        Args:
            raw_name: Исходное название учреждения

        Returns:
            dict: {
                'found': bool,
                'name': str,           # Полное юридическое название
                'address': str,        # Полный адрес
                'inn': str,           # ИНН
                'ogrn': str,          # ОГРН
                'postal_code': str    # Индекс
            }
        """
        result = {
            "found": False,
            "name": "",
            "address": "",
            "inn": "",
            "ogrn": "",
            "postal_code": "",
        }

        try:
            access_token = self.token_manager.get_token()

            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            prompt = self._create_search_prompt(raw_name)

            data = {
                "model": "GigaChat-2-Pro",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 500,
            }

            response = requests.post(
                self.api_url,
                headers=headers,
                data=json.dumps(data),
                verify=False,
                timeout=45,
            )
            response.raise_for_status()
            api_result = response.json()

            response_text = api_result["choices"][0]["message"]["content"].strip()

            # Парсим ответ
            parsed = self._parse_response(response_text)

            if parsed and parsed.get("name"):
                result.update(parsed)
                result["found"] = True

                self.log(f"  ✅ GigaChat нашел:")
                self.log(f"    • Название: {result['name'][:60]}...")
                self.log(f"    • ИНН: {result['inn']}")
                self.log(f"    • ОГРН: {result['ogrn']}")
                self.log(f"    • Адрес: {result['address'][:60]}...")
            else:
                self.log(f"  ⚠️ GigaChat не нашел данные")

            return result

        except Exception as e:
            self.log(f"  ❌ Ошибка GigaChat: {str(e)}")
            return result

    def _create_search_prompt(self, name):
        """Создание промпта для поиска в ЕГРЮЛ"""
        prompt = f"""Найди организацию "{name}" в ЕГРЮЛ и верни данные СТРОГО в формате:

НАЗВАНИЕ: <полное официальное название>
ИНН: <ИНН>
ОГРН: <ОГРН>
АДРЕС: <полный юридический адрес>

Требования:
1. Название - ПОЛНОЕ официальное юридическое название из ЕГРЮЛ
2. ИНН - только цифры (10 или 12 цифр)
3. ОГРН - только цифры (13 или 15 цифр)
4. Адрес - полный с индексом, регионом, городом, улицей, домом
5. НЕ выдумывай данные - только из реального ЕГРЮЛ
6. Если не нашел - напиши "НЕ НАЙДЕНО"

Пример:
НАЗВАНИЕ: Муниципальное бюджетное общеобразовательное учреждение "Средняя общеобразовательная школа №5"
ИНН: 7707083893
ОГРН: 1027700132195
АДРЕС: 119021, город Москва, улица Тимура Фрунзе, дом 11, строение 1

Верни данные ТОЛЬКО в этом формате, без дополнительных пояснений."""

        return prompt

    def _parse_response(self, response):
        """Парсинг ответа GigaChat"""
        if "НЕ НАЙДЕНО" in response.upper():
            return None

        result = {"name": "", "inn": "", "ogrn": "", "address": "", "postal_code": ""}

        # Парсим построчно
        lines = response.split("\n")
        for line in lines:
            line = line.strip()

            if line.startswith("НАЗВАНИЕ:"):
                result["name"] = line.replace("НАЗВАНИЕ:", "").strip()
                # Очищаем от лишних кавычек и пробелов
                result["name"] = result["name"].strip('"').strip("'").strip()

            elif line.startswith("ИНН:"):
                inn = re.search(r"(\d{10,12})", line)
                if inn:
                    result["inn"] = inn.group(1)

            elif line.startswith("ОГРН:"):
                ogrn = re.search(r"(\d{13,15})", line)
                if ogrn:
                    result["ogrn"] = ogrn.group(1)

            elif line.startswith("АДРЕС:"):
                result["address"] = line.replace("АДРЕС:", "").strip()
                # Извлекаем индекс из адреса
                postal = re.search(r"(\d{6})", result["address"])
                if postal:
                    result["postal_code"] = postal.group(1)

        # Если название не найдено, пробуем найти его в тексте
        if not result["name"]:
            # Ищем строки с типичными словами для названий организаций
            for line in lines:
                if any(
                    word in line.upper()
                    for word in [
                        "МУНИЦИПАЛЬН",
                        "ГОСУДАРСТВЕН",
                        "АВТОНОМН",
                        "БЮДЖЕТН",
                        "УЧРЕЖДЕНИ",
                        "ОРГАНИЗАЦИ",
                        "ШКОЛ",
                    ]
                ):
                    if "ИНН" not in line and "ОГРН" not in line and "АДРЕС" not in line:
                        result["name"] = line.strip()
                        break

        # Проверяем, что есть минимально необходимые данные
        if result["name"] and (result["inn"] or result["ogrn"]):
            return result

        return None

    def test_connection(self):
        """Проверить подключение к API"""
        try:
            access_token = self.token_manager.get_token()
            self.log("✅ Подключение к GigaChat установлено")
            return True
        except Exception as e:
            self.log(f"❌ Ошибка подключения к GigaChat: {e}")
            return False
