#!/bin/bash

# ========================================
# Скрипт для создания нового чистого репозитория BYSE
# ========================================

set -e  # Остановка при ошибке

echo "🚀 СОЗДАНИЕ НОВОГО РЕПОЗИТОРИЯ BYSE"
echo "===================================="

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Путь к текущему коду на VPS
SOURCE_DIR="/root/byse_bot"
# Новый репозиторий
NEW_REPO_DIR="/root/byse-new-repo"
# Имя ветки
BRANCH_NAME="claude/analyze-commit-03dc471-114A2"

echo -e "${YELLOW}📂 Исходная директория: ${SOURCE_DIR}${NC}"
echo -e "${YELLOW}📂 Новый репозиторий: ${NEW_REPO_DIR}${NC}"
echo ""

# Проверка существования исходной директории
if [ ! -d "$SOURCE_DIR" ]; then
    echo -e "${RED}❌ Директория $SOURCE_DIR не найдена!${NC}"
    exit 1
fi

# Удаляем старую директорию нового репо если существует
if [ -d "$NEW_REPO_DIR" ]; then
    echo -e "${YELLOW}⚠️  Директория $NEW_REPO_DIR уже существует. Удаляю...${NC}"
    rm -rf "$NEW_REPO_DIR"
fi

# Создаем новую директорию
echo -e "${GREEN}✅ Создаю новую директорию...${NC}"
mkdir -p "$NEW_REPO_DIR"

# Копируем только Python файлы и важные конфиги
echo -e "${GREEN}✅ Копирую Python файлы...${NC}"
cd "$SOURCE_DIR"

# Копируем все .py файлы
find . -maxdepth 1 -name "*.py" -exec cp {} "$NEW_REPO_DIR/" \;

# Копируем важные файлы
echo -e "${GREEN}✅ Копирую конфигурационные файлы...${NC}"
[ -f "requirements.txt" ] && cp requirements.txt "$NEW_REPO_DIR/" || echo "requirements.txt не найден"
[ -f "docker-compose.yml" ] && cp docker-compose.yml "$NEW_REPO_DIR/" || echo "docker-compose.yml не найден"
[ -f "Dockerfile" ] && cp Dockerfile "$NEW_REPO_DIR/" || echo "Dockerfile не найден"
[ -f "config_example.py" ] && cp config_example.py "$NEW_REPO_DIR/" || echo "config_example.py не найден"

# Копируем markdown файлы
find . -maxdepth 1 -name "*.md" -exec cp {} "$NEW_REPO_DIR/" \; 2>/dev/null || true

# Копируем директории если есть
[ -d "tests" ] && cp -r tests "$NEW_REPO_DIR/" || echo "tests/ не найдена"
[ -d "models" ] && mkdir -p "$NEW_REPO_DIR/models" && touch "$NEW_REPO_DIR/models/.gitkeep" || echo "models/ не найдена"

cd "$NEW_REPO_DIR"

# Создаем .gitignore
echo -e "${GREEN}✅ Создаю .gitignore...${NC}"
cat > .gitignore << 'EOF'
# ===== СЕКРЕТНЫЕ ФАЙЛЫ =====
# ВАЖНО: НЕ коммитить файлы с API ключами!
config.py
.env
*.key
*.pem
*secret*

# ===== ЛОГИ =====
*.log
byse.log
logs/
*.log.*

# ===== СОСТОЯНИЕ БОТА =====
bot_state.json
trading_mode.json
strategy_history.json
*.save
*.save.*

# ===== МОДЕЛИ И ДАННЫЕ =====
*.pkl
*.pickle
*.h5
*.keras
*.hdf5
*.joblib
*.model
models/*.pkl
models/*.h5
models/*.keras

# База данных
*.db
*.sqlite
*.sqlite3
trades.db

# ===== BACKUP И ВРЕМЕННЫЕ =====
backup_*/
*.backup
*.bak
*.tmp
*.temp
*~

# ===== PYTHON =====
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual environments
venv/
env/
ENV/
env.bak/
venv.bak/

# ===== IDE =====
.vscode/
.idea/
*.swp
*.swo
.DS_Store

# ===== ТЕСТЫ =====
.pytest_cache/
.coverage
htmlcov/
.tox/
.hypothesis/

# ===== JUPYTER =====
.ipynb_checkpoints/
*.ipynb

# ===== DOCKER =====
.dockerignore

# ===== СИСТЕМНЫЕ =====
.Trash-*/
.directory
Thumbs.db
EOF

# Создаем README.md если его нет
if [ ! -f "README.md" ]; then
    echo -e "${GREEN}✅ Создаю README.md...${NC}"
    cat > README.md << 'EOF'
# 🤖 BYSE Ultimate Trading Bot

Автономный торговый бот для криптовалютных фьючерсов на бирже Bybit.

## 📊 Возможности

- ✅ Автономная торговля с ML прогнозами (LSTM, Ensemble)
- ✅ Multi-timeframe анализ (5m, 15m, 1h, 4h, 1d)
- ✅ Автоматический выбор монет
- ✅ Динамическое управление рисками и плечом
- ✅ Telegram бот для управления
- ✅ Множество торговых стратегий
- ✅ Частичные выходы и трейлинг-стопы

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка

Создайте `config.py` на основе `config_example.py`:

```bash
cp config_example.py config.py
```

**⚠️ ВАЖНО:** Укажите СВОИ API ключи в `config.py`!

### 3. Запуск

```bash
python main.py
```

## ⚠️ ПРЕДУПРЕЖДЕНИЯ

- ❌ НИКОГДА не публикуйте API ключи
- ❌ НЕ коммитьте config.py в git
- ⚠️ Начните с малых сумм
- ⚠️ Используйте на свой риск

## 📁 Структура

- `main.py` - Точка входа
- `fully_autonomous_trader.py` - Основная логика
- `smart_signals.py` - Анализ сигналов
- `exchange.py` - API биржи
- `bot.py` - Telegram бот
- `neural_network.py` - LSTM модель

## 📞 Telegram команды

- `/start` - Старт
- `/status` - Статус позиции
- `/balance` - Баланс
- `/stats` - Статистика
- `/modes` - Переключение режима

## ⚖️ Лицензия

Используйте на свой страх и риск. Автор не несет ответственности за потери.
EOF
fi

# Инициализируем git
echo -e "${GREEN}✅ Инициализирую git репозиторий...${NC}"
git init

# Создаем ветку
echo -e "${GREEN}✅ Создаю ветку ${BRANCH_NAME}...${NC}"
git checkout -b "$BRANCH_NAME"

# Добавляем все файлы
echo -e "${GREEN}✅ Добавляю файлы в git...${NC}"
git add .

# Проверяем что будет закоммичено
echo ""
echo -e "${YELLOW}📋 Файлы для коммита:${NC}"
git status --short

# Делаем коммит
echo ""
read -p "Сделать initial commit? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git commit -m "Initial commit: BYSE Ultimate Trading Bot from VPS

- Все Python модули
- Конфигурация и примеры
- README и requirements.txt
- Правильный .gitignore

Source: /root/byse_bot
Date: $(date '+%Y-%m-%d %H:%M:%S')"

    echo ""
    echo -e "${GREEN}✅ Коммит создан успешно!${NC}"
fi

# Информация о следующих шагах
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ НОВЫЙ РЕПОЗИТОРИЙ СОЗДАН!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}📂 Расположение: ${NEW_REPO_DIR}${NC}"
echo -e "${YELLOW}🌿 Ветка: ${BRANCH_NAME}${NC}"
echo ""
echo -e "${YELLOW}📋 Следующие шаги:${NC}"
echo ""
echo "1️⃣  Перейдите в новый репозиторий:"
echo "   cd $NEW_REPO_DIR"
echo ""
echo "2️⃣  Добавьте remote репозиторий (GitHub/GitLab):"
echo "   git remote add origin <URL_вашего_репозитория>"
echo ""
echo "3️⃣  Запушьте код:"
echo "   git push -u origin $BRANCH_NAME"
echo ""
echo -e "${GREEN}✅ Готово!${NC}"
