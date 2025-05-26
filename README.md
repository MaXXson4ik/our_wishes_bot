
# Telegram Wishes Bot (worker)

## Особенности
* Два профиля: **Котик** и **Солнышко**.
* Добавление категорий, ссылок, редактирование ✏️ и удаление 🗑️.
* Кнопки «Назад» на каждом уровне.
* Фоновый **worker** для Render (не слушает порты).

## Локальный запуск
```bash
pip install -r requirements.txt
export BOT_TOKEN="YOUR_TOKEN"
python main.py
```

## Деплой на Render
1. Репозиторий должен содержать этот `render.yaml`.
2. Создайте *Blueprint*-сервис или измените существующий на **Background Worker**.
3. В *Environment → Add Variable* добавьте `BOT_TOKEN`.
4. Нажмите **Deploy**.
