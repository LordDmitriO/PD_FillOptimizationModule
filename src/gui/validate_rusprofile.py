import re
import difflib


def is_valid_match(original_name: str, parsed_name: str, parsed_address: str) -> bool:
    if not parsed_name or parsed_name in ["НЕ НАЙДЕНО", "ОШИБКА"]:
        return False

    original = original_name.lower()
    parsed = parsed_name.lower()
    address = parsed_address.lower()

    # проверка городов
    # надо добавить проверку города

    # проверка схожести названий
    ratio = difflib.SequenceMatcher(None, original, parsed).ratio()
    if ratio < 0.35:
        return False

    return True
