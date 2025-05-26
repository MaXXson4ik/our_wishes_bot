
import os
import threading
import http.server
import socketserver
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import json
import logging

# ---------------- tiny HTTP server for Render port scan ----------------
def run_http_probe():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')

        def log_message(self, format, *args):
            # отключаем лишний вывод в консоль
            return

    port = int(os.getenv("PORT", 8080))
    with socketserver.TCPServer(("", port), Handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_http_probe, daemon=True).start()

# ---------------- bot logic ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"Котик": {}, "Солнышко": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_states = {}

def kb_profiles():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Котик", callback_data="profile_Котик"),
                InlineKeyboardButton("Солнышко", callback_data="profile_Солнышко"),
            ]
        ]
    )

def kb_user_home():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Добавить категорию", callback_data="add_category")],
            [
                InlineKeyboardButton(
                    "Посмотреть категории", callback_data="view_categories"
                )
            ],
            [InlineKeyboardButton("Назад", callback_data="back_profiles")],
        ]
    )

def kb_categories(cats):
    keyboard = [
        [InlineKeyboardButton(cat, callback_data=f"cat_{cat}")]
        for cat in sorted(cats)
    ]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_user_home")])
    return InlineKeyboardMarkup(keyboard)

def kb_category_actions(cat):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Добавить ссылку", callback_data="add_link")],
            [InlineKeyboardButton("🔗 Посмотреть ссылки", callback_data="show_links")],
            [InlineKeyboardButton("Назад", callback_data="back_categories")],
        ]
    )

def kb_links(links):
    kb = []
    for idx, _ in enumerate(links):
        kb.append(
            [
                InlineKeyboardButton(f"✏️ {idx+1}", callback_data=f"edit_{idx}"),
                InlineKeyboardButton(f"🗑️ {idx+1}", callback_data=f"del_{idx}"),
            ]
        )
    kb.append([InlineKeyboardButton("Назад", callback_data="back_category_actions")])
    return InlineKeyboardMarkup(kb)

# -------- command helpers ----------
async def show_profiles(dest):
    await dest.reply_text("Выбери профиль:", reply_markup=kb_profiles())

async def set_profile(dest, profile):
    uid = dest.from_user.id
    user_states[uid] = {"user": profile}
    await dest.reply_text(f"Профиль: {profile}", reply_markup=kb_user_home())

# -------- commands ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_profiles(update.message)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_profiles(update.message)

async def cmd_kotik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_profile(update.message, "Котик")

async def cmd_sol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_profile(update.message, "Солнышко")

# -------- callback handler ----------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    state = user_states.get(uid, {})
    store = load_data()

    # profile select
    if data.startswith("profile_"):
        profile = data.split("_", 1)[1]
        user_states[uid] = {"user": profile}
        await query.edit_message_text(f"Профиль: {profile}", reply_markup=kb_user_home())
        return

    if data == "back_profiles":
        user_states.pop(uid, None)
        await query.edit_message_text("Выбери профиль:", reply_markup=kb_profiles())
        return

    if 'user' not in state:
        await query.edit_message_text("Сначала выбери профиль: /start")
        return

    user = state['user']

    if data == "add_category":
        state['stage'] = 'await_category_name'
        await query.edit_message_text("Введи название новой категории:",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_user_home")]]))
        return

    if data == "view_categories":
        cats = store[user]
        if not cats:
            await query.edit_message_text("У тебя пока нет категорий.", reply_markup=kb_user_home())
        else:
            await query.edit_message_text("Твои категории:", reply_markup=kb_categories(cats))
        return

    if data == "back_user_home":
        await query.edit_message_text(f"Профиль: {user}", reply_markup=kb_user_home())
        state.pop('stage', None)
        return

    if data.startswith("cat_"):
        cat = data.split("_", 1)[1]
        state['category'] = cat
        await query.edit_message_text(f"Категория: {cat}", reply_markup=kb_category_actions(cat))
        return

    if data == "back_categories":
        cats = store[user]
        await query.edit_message_text("Твои категории:", reply_markup=kb_categories(cats))
        state.pop('category', None)
        return

    if data == "add_link":
        state['stage'] = 'await_link_name'
        await query.edit_message_text("Отправь название ссылки:",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_category_actions")]]))
        return

    if data == "show_links":
        cat = state.get('category')
        links = store[user].get(cat, [])
        text = "В этой категории нет ссылок." if not links else "\n".join([f"{i+1}. {l['name']} - {l['url']}" for i,l in enumerate(links)])
        await query.edit_message_text(text, reply_markup=kb_links(links))
        return

    if data == "back_category_actions":
        cat = state.get('category')
        await query.edit_message_text(f"Категория: {cat}", reply_markup=kb_category_actions(cat))
        state.pop('stage', None)
        return

    if data.startswith("del_"):
        idx = int(data.split("_")[1])
        cat = state.get('category')
        links = store[user][cat]
        if 0 <= idx < len(links):
            removed = links.pop(idx)
            save_data(store)
            await query.edit_message_text(f"Ссылка '{removed['name']}' удалена.", reply_markup=kb_links(links))
        return

    if data.startswith("edit_"):
        idx = int(data.split("_")[1])
        state['edit_idx'] = idx
        state['stage'] = 'await_new_link_name'
        await query.edit_message_text("Отправь новое название ссылки:",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_category_actions")]]))
        return

# -------- message handler ----------
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    state = user_states.get(uid)
    if not state or 'user' not in state:
        await update.message.reply_text("Нажми /start и выбери профиль.")
        return

    stage = state.get('stage')
    user = state['user']
    store = load_data()

    if stage == 'await_category_name':
        cat = update.message.text.strip()
        if cat in store[user]:
            await update.message.reply_text("Такая категория уже существует.", reply_markup=kb_user_home())
        else:
            store[user][cat] = []
            save_data(store)
            await update.message.reply_text(f"Категория '{cat}' добавлена.", reply_markup=kb_user_home())
        state.pop('stage', None)
        return

    if stage == 'await_link_name':
        state['temp_link_name'] = update.message.text.strip()
        state['stage'] = 'await_link_url'
        await update.message.reply_text("Теперь отправь URL ссылки:",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_category_actions")]]))
        return

    if stage == 'await_link_url':
        url = update.message.text.strip()
        name = state.pop('temp_link_name', 'Без названия')
        cat = state.get('category')
        store[user][cat].append({'name': name, 'url': url})
        save_data(store)
        await update.message.reply_text(f"Ссылка '{name}' добавлена.", reply_markup=kb_category_actions(cat))
        state.pop('stage', None)
        return

    if stage == 'await_new_link_name':
        state['new_link_name'] = update.message.text.strip()
        state['stage'] = 'await_new_link_url'
        await update.message.reply_text("Теперь отправь новый URL ссылки:",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_category_actions")]]))
        return

    if stage == 'await_new_link_url':
        new_url = update.message.text.strip()
        cat = state.get('category')
        idx = state.get('edit_idx')
        links = store[user][cat]
        if 0 <= idx < len(links):
            links[idx]['name'] = state.get('new_link_name', links[idx]['name'])
            links[idx]['url'] = new_url
            save_data(store)
            await update.message.reply_text("Ссылка обновлена.", reply_markup=kb_category_actions(cat))
        state.clear()
        return

    await update.message.reply_text("Не понимаю сообщение. Используй кнопки.")

# -------- main ----------
def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise EnvironmentError("BOT_TOKEN env var missing")

    app = ApplicationBuilder().token(token).build()

    app.bot.set_my_commands([
        ("start", "Открыть меню профилей"),
        ("menu", "Показать меню профилей"),
        ("kotik", "Профиль Котик"),
        ("solnyshko", "Профиль Солнышко"),
    ])

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("kotik", cmd_kotik))
    app.add_handler(CommandHandler("solnyshko", cmd_sol))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info("Bot started (long polling with heartbeat server)")
    app.run_polling()

if __name__ == "__main__":
    main()
