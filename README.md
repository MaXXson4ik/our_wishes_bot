
# Telegram Wishes Bot

Бот для хранения ссылок по категориям для двух пользователей: **Котик** и **Солнышко**.

## Локальный запуск

```bash
pip install -r requirements.txt
export BOT_TOKEN="ваш_токен"
python main.py
```

## Деплой на Render

1. **Форк** или залейте этот репозиторий на GitHub.
2. Создайте файл `render.yaml` (уже включён).
3. Зайдите на [Render](https://render.com) → *New > Web Service*.
4. Подключите GitHub-репозиторий.
5. В разделе Environment Variables добавьте:
   - `BOT_TOKEN` — токен из BotFather.
6. Нажмите **Create Web Service**.  
   Render установит зависимости и запустит бота.

## Файлы

- `main.py` — исходный код бота (полинг).
- `requirements.txt` — зависимости.
- `render.yaml` — конфигурация Render.
- `data.json` — файл хранения данных (создаётся/обновляется автоматически).

