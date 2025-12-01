#!/bin/bash

if [ ! -d "venv" ]; then
    echo "❌ Виртуальное окружение не найдено!"
    echo "Запустите сначала: ./setup-local.sh"
    exit 1
fi

echo "🚀 Запуск Fill Optimization Module..."
source venv/bin/activate
python src/main.py