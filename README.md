
# Telegram Wishes Bot (Web Free Plan)

* Работает на бесплатном Web Service Render.
* В `main.py` встроен маленький HTTP‑сервер на `$PORT`, чтобы пройти проверку портов.
* Бот использует long‑polling.

## Запуск локально
```bash
pip install -r requirements.txt
export BOT_TOKEN="YOUR_TOKEN"
python main.py
```

## Deploy на Render
1. Убедитесь, что `render.yaml` в корне репо (`type: web`, `plan: free`).
2. Создайте Web Service (или Blueprint) — Render увидит YAML.
3. Добавьте переменную окружения `BOT_TOKEN`.
4. Нажмите Deploy — бот запустится, порт‑скан пройдёт (видит HTTP «OK»).
