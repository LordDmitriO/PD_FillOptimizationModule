"""
Модуль для имитации человеческого поведения в браузере
Версия с поддержкой режимов скорости
"""

import time
import string
import random as rd
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains as AC
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


class Humanization:
    """
    Класс хуманизации с тремя режимами работы:
    1. 'fast' - Минимальные задержки, без опечаток. Для простых сайтов.
    2. 'normal' - Баланс скорости и имитации. Опечатки редкие.
    3. 'safe' - (Твой старый режим) Медленный, параноидальный. Для RusProfile и капризных защит.
    """

    # Настройки для разных режимов
    SETTINGS = {
        'fast': {
            'type_speed': (0.005, 0.03),   # Очень быстрый ввод
            'scroll_pause': (0.1, 0.4),    # Почти мгновенный скролл
            'click_delay': (0.1, 0.3),     # Быстрый клик
            'typo_chance': 0.0,            # Без опечаток
            'wait_multiplier': 0.5,        # Уменьшаем все ожидания в 2 раза
            'scroll_step': (400, 700)      # Большие шаги скролла
        },
        'normal': {
            'type_speed': (0.03, 0.08),
            'scroll_pause': (0.5, 1.0),
            'click_delay': (0.3, 0.6),
            'typo_chance': 0.02,           # 2% шанс опечатки
            'wait_multiplier': 1.0,
            'scroll_step': (200, 500)
        },
        'safe': {
            'type_speed': (0.05, 0.15),
            'scroll_pause': (1.0, 2.0),
            'click_delay': (0.5, 1.0),
            'typo_chance': 0.08,           # 8% шанс опечатки
            'wait_multiplier': 1.5,        # Увеличиваем ожидания
            'scroll_step': (150, 300)      # Мелкие шаги
        }
    }

    def __init__(self, mode='normal'):
        if mode not in self.SETTINGS:
            print(f"⚠️ Режим '{mode}' не найден, включен 'normal'")
            mode = 'normal'
        
        self.mode = mode
        self.config = self.SETTINGS[mode]

    def human_like_type(self, browser, element, text):
        """Ввод текста с имитацией опечаток (зависит от режима)"""
        try:
            # В быстром режиме просто кликаем и очищаем, ввод почти мгновенный
            actions = AC(browser)
            actions.move_to_element(element)
            actions.click()
            actions.perform()
            
            element.clear()
            time.sleep(rd.uniform(0.1, 0.3))

            # Если режим 'fast', вводим кусками или очень быстро
            if self.mode == 'fast':
                element.send_keys(text)
                return

            for char in text:
                element.send_keys(char)
                time.sleep(rd.uniform(*self.config['type_speed']))

                # Логика опечаток
                if rd.random() < self.config['typo_chance']:
                    wrong_char = rd.choice(string.ascii_lowercase)
                    element.send_keys(wrong_char)
                    time.sleep(rd.uniform(0.1, 0.2))
                    element.send_keys(Keys.BACKSPACE)
                    time.sleep(rd.uniform(0.1, 0.2))

        except Exception as e:
            print(f"Ошибка при вводе текста: {e}")
            element.clear()
            element.send_keys(text)

    def human_like_scroll(self, browser):
        """Прокрутка страницы. В 'fast' режиме она гораздо агрессивнее."""
        try:
            last_height = browser.execute_script("return document.body.scrollHeight")
            current_scroll = 0
            
            # В быстром режиме скроллим меньше раз, но большими кусками
            step_min, step_max = self.config['scroll_step']

            while current_scroll < last_height:
                scroll_amount = rd.randint(step_min, step_max)
                current_scroll += scroll_amount

                if current_scroll > last_height:
                    current_scroll = last_height

                browser.execute_script(f"window.scrollTo(0, {current_scroll});")
                
                # Пауза зависит от режима
                time.sleep(rd.uniform(*self.config['scroll_pause']))

                # Проверка подгрузки контента (бесконечная прокрутка)
                new_height = browser.execute_script("return document.body.scrollHeight")
                if new_height > last_height:
                    last_height = new_height

            # Скролл немного вверх (только в безопасных режимах)
            if self.mode != 'fast' and rd.random() < 0.3:
                scroll_back = rd.randint(100, 300)
                browser.execute_script(
                    f"window.scrollTo(0, {current_scroll - scroll_back});"
                )
                time.sleep(rd.uniform(0.5, 1.0))

        except Exception as e:
            print(f"Ошибка при прокрутке: {e}")

    def human_like_hover(self, browser, element):
        try:
            actions = AC(browser)

            x_offset = rd.randint(-10, 10)
            y_offset = rd.randint(-10, 10)

            actions.move_to_element_with_offset(element, x_offset, y_offset)
            actions.perform()

            time.sleep(rd.uniform(1, 2))

        except Exception as e:
            print(f"Ошибка при наведении: {e}")

    def human_like_click(self, browser, element):
        timeout = 10
        old_tabs = browser.window_handles

        try:
            actions = AC(browser)
            actions.move_to_element(element)
            actions.perform()
            
            # Задержка перед кликом (имитация прицеливания)
            time.sleep(rd.uniform(*self.config['click_delay']))

            element.click()

            # Ждем появления новой вкладки
            try:
                WDW(browser, timeout).until(
                    lambda driver: len(driver.window_handles) > len(old_tabs)
                )
                new_tab = [tab for tab in browser.window_handles if tab not in old_tabs][0]
                browser.switch_to.window(new_tab)
            except TimeoutException:
                # Если вкладка не открылась, значит переход в текущей - это нормально
                pass

            # Ждем полной загрузки (readyState)
            WDW(browser, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )

        except Exception as e:
            print(f"❌ Ошибка клика: {e}")
            return False
        return True

    def human_like_wait(self, base_seconds):
        """Умное ожидание с учетом множителя режима"""
        variation = rd.uniform(-0.2, 0.2)
        # Применяем множитель режима (например 0.5 для fast)
        wait_time = max(0.1, (base_seconds + variation) * self.config['wait_multiplier'])
        time.sleep(wait_time)

    def human_like_wait_for_element(self, browser, locator, timeout=10):
        try:
            element = WDW(browser, timeout).until(
                EC.visibility_of_element_located(locator)
            )
            # Небольшая пауза "на осознание", что элемент появился
            self.human_like_wait(0.5) 
            return element
        except TimeoutException:
            # Не спамим в лог ошибками, если просто проверяем наличие
            return None
        except Exception as e:
            print(f"❌ Ошибка поиска {locator}: {e}")
            return None

    def random_mouse_movement(self, browser, element=None):
        try:
            actions = AC(browser)

            if element:
                location = element.location_once_scrolled_into_view
                x = location["x"] + rd.randint(-50, 50)
                y = location["y"] + rd.randint(-50, 50)
                actions.move_by_offset(x, y)
            else:
                x_offset = rd.randint(-100, 100)
                y_offset = rd.randint(-100, 100)
                actions.move_by_offset(x_offset, y_offset)

            actions.perform()
            time.sleep(rd.uniform(0.2, 0.5))

        except Exception as e:
            print(f"Ошибка при движении мышью: {e}")

    def debug_element_search(self, browser, element_id):
        print(f"\n🔍 Диагностика элемента: {element_id}")
        print(f"📄 URL: {browser.current_url}")

        elements_by_id = browser.find_elements(By.ID, element_id)
        print(f"✅ Найдено по ID: {len(elements_by_id)}")

        all_ids = browser.execute_script(
            """
            return Array.from(document.querySelectorAll('[id]'))
                .map(el => el.id)
                .filter(id => id.includes('clip'));
        """
        )
        print(f"📋 ID содержащие 'clip': {all_ids}")

        iframes = browser.find_elements(By.TAG_NAME, "iframe")
        print(f"🖼️ Найдено iframe: {len(iframes)}")

        ready_state = browser.execute_script("return document.readyState")
        print(f"📊 Состояние страницы: {ready_state}")

        shadow_check = browser.execute_script(
            f"""
            const el = document.getElementById('{element_id}');
            if (el) return 'Элемент найден!';

            const allElements = document.querySelectorAll('*');
            for (let el of allElements) {{
                if (el.shadowRoot) {{
                    const shadowEl = el.shadowRoot.getElementById('{element_id}');
                    if (shadowEl) return 'Найден в Shadow DOM';
                }}
            }}
            return 'Не найден';
        """
        )
        print(f"🌓 Shadow DOM: {shadow_check}")

    def close_all_except_first(self, browser):
        first_handle = browser.window_handles[0]

        while len(browser.window_handles) > 1:

            for handle in browser.window_handles:
                if handle != first_handle:
                    browser.switch_to.window(handle)
                    time.sleep(rd.uniform(0.3, 0.6))

                    try:
                        actions = AC(handle)
                        actions.key_down(Keys.CONTROL).send_keys("w").key_up(
                            Keys.CONTROL
                        ).perform()
                        time.sleep(2)
                    except Exception:
                        browser.close()

                    time.sleep(rd.uniform(0.5, 1.0))
                    break

        browser.switch_to.window(first_handle)
        time.sleep(rd.uniform(0.5, 1.0))
        print("✅ Осталась только первая вкладка")