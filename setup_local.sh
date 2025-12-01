#!/bin/bash

# Скрипт для локального запуска без Docker

echo "🚀 Настройка локального окружения..."

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не установлен!"
    echo "Установите: brew install python@3.12"
    exit 1
fi

# Проверка Java
if ! command -v java &> /dev/null; then
    echo "❌ Java не установлен!"
    echo "Установите: brew install openjdk@21"
    exit 1
fi

# Создание виртуального окружения
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активация
source venv/bin/activate

# Установка зависимостей
echo "Установка зависимостей..."
pip install -r requirements.txt

# Установка Chromium (если нужен)
if ! command -v chromium &> /dev/null; then
    echo "⚠️  Chromium не установлен"
    echo "Установите: brew install chromium"
fi

# Установка LanguageTool
if [ ! -d "/opt/languagetool" ]; then
    echo "Установка LanguageTool..."
    sudo mkdir -p /opt/languagetool
    wget https://languagetool.org/download/LanguageTool-stable.zip -O /tmp/lt.zip
    sudo unzip /tmp/lt.zip -d /opt/languagetool
    rm /tmp/lt.zip
fi

# Создание папки данных
mkdir -p data

echo ""
echo "✅ Настройка завершена!"
echo ""
echo "Для запуска программы:"
echo "  source venv/bin/activate"
echo "  python src/main.py"
echo ""