
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import json
import os
import logging

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Котик", callback_data="user_Котик"),
         InlineKeyboardButton("Солнышко", callback_data="user_Солнышко")]
    ]
    await update.message.reply_text("Кто ты?", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_user_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.data.split("_")[1]
    user_states[query.from_user.id] = {"user": user}
    keyboard = [
        [InlineKeyboardButton("Добавить категорию", callback_data="add_category")],
        [InlineKeyboardButton("Посмотреть категории", callback_data="view_categories")]
    ]
    await query.edit_message_text(f"Привет, {user}!", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    state = user_states.get(user_id)
    if not state:
        return await query.edit_message_text("Сначала нажми /start")

    data = load_data()
    user = state["user"]

    if query.data == "add_category":
        user_states[user_id]["action"] = "add_category"
        await query.edit_message_text("Введи название новой категории:")
    elif query.data == "view_categories":
        categories = data[user]
        if not categories:
            await query.edit_message_text("У тебя пока нет категорий.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back")]]))
        else:
            keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in categories]
            keyboard.append([InlineKeyboardButton("Назад", callback_data="back")])
            await query.edit_message_text("Выбери категорию:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("cat_"):
        cat = query.data.split("_", 1)[1]
        user_states[user_id]["category"] = cat
        keyboard = [
            [InlineKeyboardButton("➕ Добавить ссылку", callback_data="add_link")],
            [InlineKeyboardButton("🔗 Посмотреть ссылки", callback_data="show_links")],
            [InlineKeyboardButton("Назад", callback_data="view_categories")]
        ]
        await query.edit_message_text(f"Категория: {cat}", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "add_link":
        user_states[user_id]["action"] = "add_link_name"
        await query.edit_message_text("Введи название ссылки:")
    elif query.data == "show_links":
        cat = state.get("category")
        links = data[user].get(cat, [])
        if not links:
            text = "В этой категории нет ссылок."
        else:
            text = "\n".join([f"{i+1}. {item['name']} - {item['url']}" for i, item in enumerate(links)])
        keyboard = [[InlineKeyboardButton("Назад", callback_data=f"cat_{cat}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "back":
        await handle_user_choice(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    state = user_states.get(user_id)
    if not state:
        return await update.message.reply_text("Сначала нажми /start")

    action = state.get("action")
    data = load_data()
    user = state["user"]

    if action == "add_category":
        category_name = update.message.text.strip()
        if category_name not in data[user]:
            data[user][category_name] = []
            save_data(data)
            await update.message.reply_text(f"Категория '{category_name}' добавлена.")
        else:
            await update.message.reply_text("Такая категория уже есть.")
        user_states[user_id].pop("action", None)
    elif action == "add_link_name":
        state["temp_name"] = update.message.text.strip()
        state["action"] = "add_link_url"
        await update.message.reply_text("Теперь отправь ссылку:")
    elif action == "add_link_url":
        url = update.message.text.strip()
        name = state.get("temp_name")
        category = state.get("category")
        if name and category:
            data[user][category].append({"name": name, "url": url})
            save_data(data)
            await update.message.reply_text(f"Ссылка '{name}' добавлена в категорию '{category}'.")
        else:
            await update.message.reply_text("Ошибка добавления ссылки.")
        state.pop("action", None)
        state.pop("temp_name", None)
    else:
        await update.message.reply_text("Не понимаю сообщение. Используй кнопки.")

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("Переменная окружения BOT_TOKEN не установлена")
    logger.info("Запуск бота...")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_user_choice, pattern="^user_"))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот готов. Ожидает команды.")
    app.run_polling()

if __name__ == "__main__":
    main()
