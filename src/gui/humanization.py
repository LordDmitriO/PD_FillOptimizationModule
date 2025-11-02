"""
Модуль для имитации человеческого поведения в браузере
"""

import time
import string
import random as rd
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains as AC
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


class Humanization:
    def __init__(self):
        self.type_pause_time = rd.uniform(0.01, 0.1)
        self.scroll_pause_time = rd.uniform(1.0, 2.0)
        self.scroll_up = rd.randint(100, 300)

    def human_like_type(self, browser, element, text):
        try:
            actions = AC(browser)
            actions.move_to_element(element)
            actions.click()
            actions.perform()

            element.clear()
            time.sleep(rd.uniform(0.1, 0.3))

            for char in text:
                element.send_keys(char)
                time.sleep(self.type_pause_time)

                if rd.random() < 0.05:
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
        try:
            last_height = browser.execute_script("return document.body.scrollHeight")
            current_scroll = 0

            while current_scroll < last_height:
                scroll_amount = rd.randint(200, 500)
                current_scroll += scroll_amount

                if current_scroll > last_height:
                    current_scroll = last_height

                browser.execute_script(f"window.scrollTo(0, {current_scroll});")
                time.sleep(self.scroll_pause_time)

                if rd.random() < 0.3:
                    time.sleep(rd.uniform(0.5, 1.5))

                new_height = browser.execute_script("return document.body.scrollHeight")
                if new_height > last_height:
                    last_height = new_height

            if rd.random() < 0.5:
                scroll_back = rd.randint(100, 300)
                browser.execute_script(
                    f"window.scrollTo(0, {current_scroll - scroll_back});"
                )
                time.sleep(rd.uniform(0.5, 1.0))

        except Exception as e:
            print(f"Ошибка при прокрутке: {e}")

    def human_like_click(self, browser, element):

        timeout = 10
        old_tabs = browser.window_handles

        try:
            actions = AC(browser)

            actions.move_to_element(element)
            actions.perform()
            time.sleep(rd.uniform(0.3, 0.8))

            element.click()

            WDW(browser, timeout).until(
                lambda driver: len(driver.window_handles) > len(old_tabs)
            )

            new_tab = [tab for tab in browser.window_handles if tab not in old_tabs][0]
            browser.switch_to.window(new_tab)

            WDW(browser, timeout).until(
                lambda driver: driver.execute_script("return document.readyState")
                == "complete"
            )

        except TimeoutException:
            print("⚠️ Новая вкладка не открылась, возможно переход на той же странице")

            WDW(browser, timeout).until(
                lambda driver: driver.execute_script("return document.readyState")
                == "complete"
            )

            return True

        except Exception as e:
            print(f"❌ Ошибка: {e}")

            return False

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

    def human_like_wait(self, base_seconds):
        variation = rd.uniform(-0.3, 0.3)
        wait_time = max(0.1, base_seconds + variation)
        time.sleep(wait_time)

    def human_like_wait_for_element(self, browser, locator, timeout=10):
        try:
            try:
                _ = browser.current_url
            except Exception:
                print("❌ Браузер закрыт или недоступен!")
                return None

            element = WDW(browser, timeout).until(
                EC.visibility_of_element_located(locator)
            )

            self.human_like_wait(rd.uniform(0.2, 0.8))
            return element

        except TimeoutException:
            print(f"⏱️ Таймаут: элемент {locator} не найден за {timeout} сек")
            return None

        except WebDriverException as e:
            print(f"❌ WebDriver ошибка для {locator}: {e.msg}")

            try:
                browser.current_url
                print("✅ Браузер еще работает")
            except Exception:
                print("❌ Браузер недоступен!")
            return None

        except Exception as e:
            print(f"❌ Неожиданная ошибка для {locator}: {type(e).__name__} - {e}")
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
