# Content Pipeline Bot для Telegram-канала (Business/PMF)

Конвейер постов по модели Sereja.tech: человек задаёт направление через бота → 5 фаз агентской обработки → автопубликация в канал по cron в 19:00 МСК.

## Структура проекта

```
AI-PMF-ilya_eli/
├── main.py                       # Entry point
├── config.py                     # Settings из .env
├── requirements.txt
├── bot/                          # Telegram bot
│   ├── handlers.py               # /newpost (FSM), /queue, /cancel
│   ├── states.py                 # FSM states
│   └── middlewares.py            # Admin-only filter
├── pipeline/                     # 5-phase pipeline
│   ├── base.py                   # BaseAgent
│   ├── orchestrator.py           # Orchestrates all phases
│   ├── researcher.py             # Phase 2: Tavily + Claude
│   ├── writer.py                 # Phase 3: Draft writer
│   ├── critics.py                # Phase 4: Critics
│   ├── rewriter.py               # Phase 4: Rewriter
│   └── publisher.py              # Phase 5: Queue + publish
├── llm/                          # Claude client
│   └── client.py
├── research/                     # Tavily client
│   └── tavily_client.py
├── storage/                      # JSON storage
│   └── json_store.py
├── scheduler/                    # APScheduler
│   └── publish_job.py
├── utils/                        # Utilities
│   └── prompt_loader.py
├── prompts/                      # System prompts
│   ├── researcher.md
│   ├── writer.md
│   ├── writing_guide.md
│   ├── rewriter.md
│   └── critics/
│       ├── generic_detector.md
│       ├── rhythm_analyzer.md
│       ├── specificity_checker.md
│       └── fact_checker.md
└── data/                         # Data storage
    ├── queue/                    # Queued posts
    ├── published/                # Published posts
    └── drafts/                   # Draft artifacts
```

## 5 фаз пайплайна

### Фаза 1: Questions (диалог в ТГ через FSM)
- `/newpost` → бот задаёт вопросы через inline-кнопки и текстовый ввод
- FSM состояния: `topic_angle` → `audience` → `key_takeaway` → `extra_points` → `confirm`

### Фаза 2: Research (Tavily + Claude)
- Формирует поисковый запрос из контекста пользователя
- Tavily: 3-5 источников (`search_depth="advanced"`)
- Claude структурирует результаты

### Фаза 3: Draft (Claude)
- Пишет пост на русском по writing_guide.md
- Требования: 500+ символов, личный тон, конкретные примеры, inline-ссылки

### Фаза 4: Deaify (4 критика параллельно + rewriter)
- 4 критика одновременно:
  1. **Generic Detector** — AI-фразы
  2. **Rhythm Analyzer** — разнообразие длины предложений
  3. **Specificity Checker** — конкретика
  4. **Fact Checker** — верификация фактов
- Rewriter переписывает с учётом всех замечаний

### Фаза 5: Publish
- Сохраняет пост в `data/queue/`
- APScheduler cron в 19:00 МСК публикует в канал
- Перемещает в `data/published/`

## Установка

### 1. Создать виртуальное окружение

```bash
python3 -m venv venv
source venv/bin/activate  # На macOS/Linux
# или
venv\Scripts\activate  # На Windows
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Настроить .env

Скопируйте `.env.example` в `.env`:

```bash
cp .env.example .env
```

Заполните значения:

```env
BOT_TOKEN=your_telegram_bot_token_here
CHANNEL_ID=@your_channel
ANTHROPIC_API_KEY=your_anthropic_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
ADMIN_TELEGRAM_ID=your_telegram_id_here
PUBLISH_HOUR=19
CLAUDE_MODEL=claude-sonnet-4-5-20250929
```

**Как получить токены:**

- **BOT_TOKEN**: Создайте бота через [@BotFather](https://t.me/BotFather) в Telegram
- **CHANNEL_ID**: ID вашего канала (формат: `@channel_name` или `-100XXXXXXXXX`)
- **ANTHROPIC_API_KEY**: Зарегистрируйтесь на [console.anthropic.com](https://console.anthropic.com/)
- **TAVILY_API_KEY**: Зарегистрируйтесь на [tavily.com](https://tavily.com/)
- **ADMIN_TELEGRAM_ID**: Ваш Telegram ID (получите через [@userinfobot](https://t.me/userinfobot))

### 4. Дать боту права администратора канала

Бот должен иметь права на публикацию в канале:
1. Откройте настройки канала
2. Администраторы → Добавить администратора
3. Найдите вашего бота и дайте права "Публикация сообщений"

## Запуск

```bash
python main.py
```

Бот запустится и начнёт слушать команды. Scheduler автоматически запустится и будет публиковать посты ежедневно в 19:00 МСК.

## Использование

### Создать пост

1. Напишите боту `/newpost`
2. Ответьте на вопросы (тип поста, аудитория, главная мысль, детали)
3. Подтвердите создание
4. Дождитесь завершения пайплайна (2-5 минут)
5. Пост автоматически добавится в очередь

### Посмотреть очередь

```
/queue
```

Показывает все посты в очереди публикации.

### Отменить текущее действие

```
/cancel
```

## Публикация

Посты публикуются **автоматически** каждый день в **19:00 МСК** (по умолчанию).

Изменить время публикации можно в `.env`:

```env
PUBLISH_HOUR=20  # Публикация в 20:00
```

## Логи

Все события логируются в консоль:
- Запуск бота
- Создание постов
- Публикация
- Ошибки

## Структура данных

### Очередь (`data/queue/`)

Каждый пост сохраняется как JSON:

```json
{
  "final_post": "HTML-текст поста",
  "draft": "Черновик",
  "research": {...},
  "critiques": [...],
  "user_answers": {...},
  "queued_at": "2025-02-04T12:00:00",
  "status": "queued"
}
```

### Опубликованные (`data/published/`)

После публикации добавляются поля:

```json
{
  ...
  "status": "published",
  "published_at": "2025-02-04T19:00:00"
}
```

## Troubleshooting

### Бот не отвечает

- Проверьте `BOT_TOKEN` в `.env`
- Убедитесь, что бот запущен (`python main.py`)
- Проверьте, что ваш Telegram ID совпадает с `ADMIN_TELEGRAM_ID`

### Пайплайн падает с ошибкой

- Проверьте API ключи (`ANTHROPIC_API_KEY`, `TAVILY_API_KEY`)
- Убедитесь, что на балансе Anthropic есть средства
- Проверьте логи в консоли

### Посты не публикуются

- Проверьте `CHANNEL_ID` (правильный формат)
- Убедитесь, что бот добавлен как администратор канала
- Проверьте права бота на публикацию
- Проверьте, что в очереди есть посты (`/queue`)

### Время публикации неправильное

- Убедитесь, что `PUBLISH_HOUR` указан в 24-часовом формате (0-23)
- Время публикации в часовом поясе МСК (Europe/Moscow)

## Разработка

### Тестирование компонентов

Все компоненты можно тестировать отдельно:

```python
# Config
python -c "from config import load_settings; print(load_settings())"

# LLM Client
# Создайте тестовый скрипт для проверки
```

### Настройка промптов

Все промпты находятся в `prompts/`. Редактируйте `.md` файлы для изменения поведения агентов.

**Важно:** После изменения промптов перезапустите бота.

## Tech Stack

- **Python 3.10+**
- **aiogram 3.3.0** — Async Telegram Bot API
- **anthropic** — Claude API
- **tavily-python** — Web research
- **APScheduler** — Cron scheduling
- **aiofiles** — Async file I/O

## License

MIT
