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

    def __init__(self, auth_token):
        """
        Args:
            auth_token: Base64 токен для авторизации (Basic токен)
        """
        self.auth_token = auth_token
        self.access_token = None
        self.token_expiry = None

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
            response = requests.post(url, headers=headers, data=data, verify=False)
            response.raise_for_status()
            result = response.json()
            self.access_token = result["access_token"]
            # Токен действует 30 минут, обновляем за 1 минуту до истечения
            self.token_expiry = datetime.now() + timedelta(minutes=29)
            print(
                f"✓ Токен GigaChat обновлен (действителен до {self.token_expiry.strftime('%H:%M:%S')})"
            )
            return True
        except Exception as e:
            print(f"✗ Ошибка обновления токена: {e}")
            return False


class GigaChatAPI:
    """Класс для работы с GigaChat API"""

    def __init__(self, auth_token):
        """
        Args:
            auth_token: Base64 токен для авторизации (Basic токен)
                       Формат: 'CLIENT_ID:CLIENT_SECRET' в base64
        """
        self.token_manager = TokenManager(auth_token)
        self.api_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    def normalize_school_name(self, raw_name):
        """
        Нормализовать название образовательного учреждения

        Args:
            raw_name: Исходное название учреждения

        Returns:
            str: Нормализованное название или "Ошибка"
        """
        try:
            access_token = self.token_manager.get_token()

            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            prompt = self._create_normalization_prompt(raw_name)

            data = {
                "model": "GigaChat-2-Pro",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,  # Низкая температура для более точных ответов
                "max_tokens": 200,
            }

            response = requests.post(
                self.api_url,
                headers=headers,
                data=json.dumps(data),
                verify=False,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            normalized = result["choices"][0]["message"]["content"].strip()
            # Очистка от возможных пояснений
            normalized = self._clean_response(normalized)

            return normalized

        except Exception as e:
            print(f"✗ Ошибка GigaChat для '{raw_name}': {e}")
            return "Ошибка"

    def _create_normalization_prompt(self, name):
        prompt = f"""Исходное: "{name}"

Найди официальное название в ЕГРЮЛ и приведи к формату:
"Организационная форма название «имя»"

Правила:
- Регистр: Первая Буква Заглавная
- №: без пробела (№47)
- Кавычки: «елочки»
- Убери географию
- НЕ выдумывай

Примеры:
"АНОО ШКОЛА ВЕКТОР г.о. Мытищи" → "Автономная некоммерческая общеобразовательная организация Школа «Вектор»"
"гбоу сош № 47 города москвы" → "Государственное бюджетное общеобразовательное учреждение города Москвы «Средняя общеобразовательная школа №47»"

Верни ТОЛЬКО название одной строкой."""

        return prompt

    def _clean_response(self, response):
        """Очистить и нормализовать ответ"""
        # Убираем возможные пояснения после двоеточия
        if ":" in response and response.index(":") < 50:
            parts = response.split(":", 1)
            if len(parts[1].strip()) > 10:
                response = parts[1].strip()

        # Убираем внешние кавычки
        response = response.strip('"').strip("'").strip()

        # Убираем префиксы
        prefixes = [
            "Ответ:",
            "Название:",
            "Результат:",
            "Официальное название:",
            "Нормализованное:",
        ]
        for prefix in prefixes:
            if response.startswith(prefix):
                response = response[len(prefix) :].strip()

        # Заменяем обычные кавычки на елочки
        response = response.replace('"', "«").replace('"', "»")
        # Если есть только открывающая кавычка, заменяем все " на елочки
        if '"' in response:
            parts = response.split('"')
            result = []
            for i, part in enumerate(parts):
                result.append(part)
                if i < len(parts) - 1:
                    result.append("«" if i % 2 == 0 else "»")
            response = "".join(result)

        # Убираем лишние пробелы перед №
        response = re.sub(r"\s+№", " №", response)
        # Убираем пробел после №
        response = re.sub(r"№\s+(\d)", r"№\1", response)

        # Исправляем регистр для аббревиатур
        abbrs = [
            "ГБОУ",
            "МБОУ",
            "МАОУ",
            "АНОО",
            "АНООО",
            "АНО",
            "ГАПОУ",
            "ГБПОУ",
            "ФГБОУ",
            "СОШ",
            "ООО",
        ]
        for abbr in abbrs:
            # Если аббревиатура в начале и вся в нижнем регистре - исправляем
            pattern = r"\b" + abbr.lower() + r"\b"
            if re.search(pattern, response.lower()):
                response = re.sub(pattern, abbr, response, flags=re.IGNORECASE)

        return response

    def test_connection(self):
        """Проверить подключение к API"""
        try:
            access_token = self.token_manager.get_token()
            print("✓ Подключение к GigaChat успешно установлено")
            return True
        except Exception as e:
            print(f"✗ Ошибка подключения к GigaChat: {e}")
            return False


# Пример использования
# if __name__ == "__main__":
#     AUTH_TOKEN = "токен"
#     # Создаем API клиент
#     gigachat = GigaChatAPI(AUTH_TOKEN)

#     # Проверяем подключение
#     if gigachat.test_connection():
#         # Тестируем нормализацию
#         test_name = 'муниципальное автономное общеобразовательное учреждение средняя общеобразовательная школа № 18 с углубленным изучением отдельных предметов города Арма'
#         result = gigachat.normalize_school_name(test_name)
#         print(f"\nИсходное: {test_name}")
#         print(f"Результат: {result}")
