import os
import time
import re
from twocaptcha import TwoCaptcha
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


class ReCaptchaSolver:
    """Класс для решения reCAPTCHA v2"""
    
    def __init__(self, api_key=None, log_callback=None):
        """
        Инициализация решателя капчи
        
        Args:
            api_key: API ключ ruCaptcha (если None, берется из переменной окружения)
            log_callback: Функция для логирования
        """
        self.api_key = api_key or os.getenv('RUCAPTCHA_API_KEY')
        if not self.api_key:
            # Можно не рейзить ошибку сразу, а просто работать в ручном режиме, 
            # но для автоматизации лучше знать об этом сразу.
            print("⚠️ API ключ ruCaptcha не найден. Автоматическое решение будет недоступно.")
        
        # Инициализация клиента. 
        # Если возникают сетевые ошибки, можно попробовать убрать параметр server='rucaptcha.com'
        try:
            self.solver = TwoCaptcha(
                self.api_key,
                server='rucaptcha.com'
            )
        except Exception as e:
            self.solver = None
            print(f"❌ Ошибка инициализации TwoCaptcha: {e}")

        self.log_callback = log_callback
    
    def log(self, message):
        """Вывод сообщения в лог"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    def solve_recaptcha_v2(self, browser, sitekey=None, timeout=120):
        """
        Решает reCAPTCHA v2 на текущей странице
        
        Returns:
            bool: True если капча решена успешно
        """
        if not self.solver:
            self.log("❌ Солвер не инициализирован (нет API ключа или ошибка библиотеки).")
            return False

        try:
            current_url = browser.current_url
            
            # Если sitekey не передан, пытаемся найти его на странице
            if not sitekey:
                self.log("🔍 Поиск sitekey на странице...")
                sitekey = self._find_sitekey(browser)
                
            if not sitekey:
                self.log("❌ Не удалось найти sitekey на странице")
                return False
            
            self.log(f"🔑 Найден sitekey: {sitekey[:20]}...")
            self.log("⏳ Отправка капчи на решение в ruCaptcha...")
            
            # Отправляем капчу на решение
            # Добавлен параметр enterprise=0, так как на RusProfile обычная V2
            result = self.solver.recaptcha(
                sitekey=sitekey,
                url=current_url,
                enterprise=0
            )
            
            # Проверяем формат ответа библиотеки
            if isinstance(result, dict) and 'code' in result:
                g_recaptcha_response = result['code']
            elif isinstance(result, str):
                # Иногда библиотека может вернуть строку, если версия старая или измененная
                # Но по документации должен быть dict
                if 'code:' in result:
                    g_recaptcha_response = result.split('code:')[1]
                else:
                    g_recaptcha_response = result
            else:
                self.log(f"❌ Непонятный ответ от солвера: {result}")
                return False

            self.log(f"✅ Капча решена! Токен получен: {g_recaptcha_response[:20]}...")
            
            # Вставляем токен в форму
            self.log("📝 Вставка токена в форму...")
            self._inject_token(browser, g_recaptcha_response)
            
            self.log("✅ Токен успешно вставлен!")
            
            # Небольшая пауза, чтобы скрипты сайта успели подхватить изменение
            time.sleep(1)
            
            return True
            
        except Exception as e:
            self.log(f"❌ Ошибка при решении капчи: {str(e)}")
            return False
    
    def _find_sitekey(self, browser):
        """
        Ищет sitekey капчи на странице
        """
        try:
            # Метод 0: Прямой поиск по ID (как в примере RusProfile)
            try:
                element_by_id = browser.find_element(By.ID, 'recaptcha')
                key = element_by_id.get_attribute('data-sitekey')
                if key:
                    return key
            except Exception:
                pass

            # Метод 1: Поиск по классу g-recaptcha
            try:
                elements = browser.find_elements(By.CLASS_NAME, 'g-recaptcha')
                for el in elements:
                    key = el.get_attribute('data-sitekey')
                    if key:
                        return key
            except Exception:
                pass

            # Метод 2: Поиск в любом элементе с атрибутом data-sitekey
            elements = browser.find_elements(By.CSS_SELECTOR, '[data-sitekey]')
            if elements:
                return elements[0].get_attribute('data-sitekey')
            
            # Метод 3: Поиск в iframe
            iframes = browser.find_elements(By.TAG_NAME, 'iframe')
            for iframe in iframes:
                src = iframe.get_attribute('src')
                if src and 'recaptcha' in src and 'k=' in src:
                    match = re.search(r'k=([^&]+)', src)
                    if match:
                        return match.group(1)
            
            # Метод 4: Regex по исходному коду (как крайний случай)
            page_source = browser.page_source
            match = re.search(r'"sitekey"\s*:\s*"([^"]+)"', page_source)
            if match:
                return match.group(1)
            
            match = re.search(r'data-sitekey="([^"]+)"', page_source)
            if match:
                return match.group(1)
            
        except Exception as e:
            self.log(f"⚠️ Ошибка при поиске sitekey: {str(e)}")
        
        return None
    
    def _inject_token(self, browser, token):
        """
        Вставляет токен решения капчи в форму и вызывает callback
        """
        # 1. Вставка в textarea (стандартный метод)
        script_textarea = f"""
            var el = document.getElementById('g-recaptcha-response');
            if (el) {{
                el.innerHTML = '{token}';
                el.value = '{token}';
                el.style.display = 'block'; // Делаем видимым для отладки
            }}
            
            // Также ищем по имени, так как ID может не быть
            var els = document.getElementsByName('g-recaptcha-response');
            for (var i=0; i<els.length; i++) {{
                els[i].innerHTML = '{token}';
                els[i].value = '{token}';
            }}
        """
        browser.execute_script(script_textarea)
        
        # 2. Попытка вызова callback функции Google Recaptcha
        # Это самый надежный способ заставить сайт "съесть" капчу
        script_callback = f"""
            function findRecaptchaClients() {{
                if (typeof ___grecaptcha_cfg !== 'undefined' && ___grecaptcha_cfg.clients) {{
                    return Object.keys(___grecaptcha_cfg.clients).filter(function(key) {{
                        return ___grecaptcha_cfg.clients[key].hasOwnProperty('id');
                    }});
                }}
                return [];
            }}
            
            var clients = findRecaptchaClients();
            if (clients && clients.length > 0) {{
                clients.forEach(function(clientId) {{
                    try {{
                        console.log('Trying callback for client: ' + clientId);
                        // Вызываем стандартный callback рекапчи
                        ___grecaptcha_cfg.clients[clientId].callback('{token}');
                        return true;
                    }} catch (e) {{
                        console.error('Error calling captcha callback', e);
                    }}
                }});
            }}
        """
        try:
            browser.execute_script(script_callback)
        except Exception:
            pass  # Не критично, если не сработало, попробуем submit формы

    def wait_for_captcha_disappear(self, browser, timeout=10):
        """Ждет, пока капча исчезнет"""
        try:
            WebDriverWait(browser, timeout).until(
                lambda driver: "робот" not in driver.find_element(By.TAG_NAME, "body").text.lower()
            )
            return True
        except Exception:
            return False
