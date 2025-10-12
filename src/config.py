"""
Конфигурационный файл для приложения
"""

import os
from dotenv import load_dotenv

load_dotenv()

# GigaChat API Configuration
GIGACHAT_AUTH_TOKEN = os.getenv('GIGACHAT_AUTH_TOKEN')

# RusProfile Configuration
RUSPROFILE_DELAY = int(os.getenv('RUSPROFILE_DELAY', '5'))
RUSPROFILE_MAX_REQUESTS = int(os.getenv('RUSPROFILE_MAX_REQUESTS', '100'))

# Excel Configuration
EXCEL_COLUMN_NAME = "Образовательное учреждение из 1С"
