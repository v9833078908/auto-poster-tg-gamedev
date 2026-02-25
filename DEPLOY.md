# Деплой на VPS через Coolify

## Предварительные требования

- VPS с установленным Coolify (минимум 1 CPU, 1GB RAM)
- Репозиторий на GitHub/GitLab (публичный или приватный с подключённым SSH-ключом)
- Все API-ключи: Telegram Bot Token, Anthropic, Tavily

---

## Шаг 1 — Подготовить репозиторий

1. Убедиться что в репозитории есть `Dockerfile` и `docker-compose.yml`
2. `.env` **не должен** быть в репозитории (он в `.gitignore`)
3. Файлы `topic.json` и папка `prompts/` должны быть закоммичены — они монтируются как read-only

```bash
git add Dockerfile docker-compose.yml .dockerignore topic.json prompts/
git commit -m "add docker setup"
git push
```

---

## Шаг 2 — Установить Coolify на VPS

Если Coolify ещё не установлен:

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

Открыть `http://<VPS_IP>:8000` и завершить первичную настройку.

---

## Шаг 3 — Создать приложение в Coolify

1. **New Project** → придумать название (например, `auto-poster-tg`)
2. **New Resource** → **Application**
3. Выбрать **Git Repository**
4. Подключить репозиторий (GitHub App или Deploy Key)
5. Выбрать ветку `main`

---

## Шаг 4 — Настройить сборку

В настройках приложения:

| Параметр | Значение |
|---|---|
| Build Pack | **Dockerfile** |
| Dockerfile Path | `./Dockerfile` |
| Port | оставить пустым (бот не слушает порт) |
| Start Command | *(оставить пустым, используется CMD из Dockerfile)* |

> Если используется `docker-compose.yml`, можно выбрать **Docker Compose** вместо Dockerfile.

---

## Шаг 5 — Добавить переменные окружения

В разделе **Environment Variables** добавить все переменные из `.env.example`:

```
BOT_TOKEN=ваш_токен_бота
CHANNEL_ID=@ваш_канал
ANTHROPIC_API_KEY=ваш_ключ
TAVILY_API_KEY=ваш_ключ
ADMIN_TELEGRAM_ID=ваш_telegram_id
PUBLISH_HOUR=19
CLAUDE_MODEL=claude-sonnet-4-6
TOPIC_CONFIG=topic.json
LOG_LEVEL=INFO
```

---

## Шаг 6 — Настроить персистентное хранилище

В разделе **Storages / Volumes** добавить том:

| Source (Volume Name) | Destination (в контейнере) |
|---|---|
| `bot_data` | `/app/data` |

Это сохранит очередь, опубликованные посты и черновики между перезапусками.

---

## Шаг 7 — Деплой

1. Нажать **Deploy**
2. Следить за логами сборки — убедиться что `pip install` прошёл без ошибок
3. После деплоя проверить **Logs** — должна появиться строка `bot_starting`

---

## Автодеплой при push

В разделе **Webhooks** Coolify автоматически создаёт GitHub/GitLab webhook.
При каждом `git push` в `main` — бот пересобирается и перезапускается.

---

## Команды для ручного управления через SSH

```bash
# Посмотреть статус контейнера
docker ps | grep auto-poster

# Посмотреть логи
docker logs <container_id> --tail 50 -f

# Перезапустить вручную
docker restart <container_id>
```

---

## Troubleshooting

| Проблема | Решение |
|---|---|
| Бот не запускается | Проверить переменные окружения, все ли заполнены |
| `Missing required environment variables` | Добавить недостающие переменные в Coolify |
| Данные теряются при перезапуске | Проверить что volume `bot_data` → `/app/data` добавлен |
| Бот не отвечает на команды | Проверить `ADMIN_TELEGRAM_ID` — только этот ID может управлять ботом |
