FROM python:3.12-slim

WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY *.py ./
COPY models/ ./models/ 2>/dev/null || true
COPY tests/ ./tests/ 2>/dev/null || true

# Директории для данных
RUN mkdir -p /app/models /app/data

# Переменные окружения (обязательные)
ENV API_KEY=""
ENV API_SECRET=""
ENV TELEGRAM_TOKEN=""
ENV TELEGRAM_CHAT_ID=""
ENV NEWS_API_KEY=""

# Порт для healthcheck (если нужен)
EXPOSE 8080

# Запуск
CMD ["python3", "main.py"]
