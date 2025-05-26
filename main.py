
import os, logging, sqlite3, threading, http.server, socketserver, datetime, csv, io
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# --- tiny HTTP server so Render sees a port ---
def run_probe():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
        def log_message(self, f, *a): pass
    port=int(os.getenv("PORT", "8080"))
    with socketserver.TCPServer(('',port), H) as s: s.serve_forever()
threading.Thread(target=run_probe, daemon=True).start()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("bot")

DB="bot.db"
def init_db():
    with sqlite3.connect(DB) as con:
        c=con.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS links(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT, category TEXT, name TEXT, url TEXT,
            favorite INTEGER DEFAULT 0,
            created TEXT, updated TEXT
        )""")
        con.commit()
init_db()

def db(q, params=(), fetch=False, many=False):
    with sqlite3.connect(DB) as con:
        con.row_factory=sqlite3.Row
        cur=con.cursor()
        cur.executemany(q, params) if many else cur.execute(q, params)
        con.commit()
        return cur.fetchall() if fetch else None

PROFILES=["Котик","Солнышко"]
def kb_profiles():
    return InlineKeyboardMarkup([[InlineKeyboardButton(p,callback_data=f"profile_{p}")] for p in PROFILES])

def kb_home(): return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Домой", callback_data="home")]])

def kb_profile_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Все ссылки", callback_data="all_links")],
        [InlineKeyboardButton("Категории", callback_data="show_categories")],
        [InlineKeyboardButton("➕ Новая категория", callback_data="add_cat")],
        [InlineKeyboardButton("🏠 Домой", callback_data="home")]
    ])

def kb_categories(profile):
    rows=db("SELECT DISTINCT category FROM links WHERE profile=? ORDER BY category",(profile,),fetch=True)
    kb=[[InlineKeyboardButton(r["category"], callback_data=f"cat_{r['category']}")] for r in rows]
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_profile")])
    kb.append([InlineKeyboardButton("🏠 Домой", callback_data="home")])
    return InlineKeyboardMarkup(kb)

def kb_links(profile,cat):
    rows=db("SELECT id,name,favorite FROM links WHERE profile=? AND category=?",(profile,cat),fetch=True)
    kb=[]
    for r in rows:
        star="⭐" if r["favorite"] else "☆"
        kb.append([
            InlineKeyboardButton(r["name"],callback_data=f"link_{r['id']}"), 
            InlineKeyboardButton(star,callback_data=f"fav_{r['id']}"), 
            InlineKeyboardButton("✏️",callback_data=f"edit_{r['id']}"), 
            InlineKeyboardButton("🗑️",callback_data=f"del_{r['id']}")
        ])
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_categories")])
    kb.append([InlineKeyboardButton("🏠 Домой", callback_data="home")])
    return InlineKeyboardMarkup(kb)

def kb_all_links(profile):
    rows=db("SELECT id,name,favorite,category FROM links WHERE profile=? ORDER BY category",(profile,),fetch=True)
    kb=[]
    for r in rows:
        star="⭐" if r["favorite"] else "☆"
        label=f"[{r['category']}] {r['name']}"
        kb.append([
            InlineKeyboardButton(label, callback_data=f"link_{r['id']}"), 
            InlineKeyboardButton(star,callback_data=f"fav_{r['id']}")
        ])
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_profile")])
    kb.append([InlineKeyboardButton("🏠 Домой", callback_data="home")])
    return InlineKeyboardMarkup(kb)

user_state={}  # uid -> dict(profile, stage, tmp, category)

async def start(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери профиль:", reply_markup=kb_profiles())

async def profile_menu(chat,profile):
    await chat.edit_text(f"Профиль: {profile}", reply_markup=kb_profile_menu())

async def callback(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; data=q.data
    state=user_state.setdefault(uid,{})
    if data.startswith("profile_"):
        state.clear(); state["profile"]=data.split("_",1)[1]
        await profile_menu(q.message, state["profile"]); return
    if data=="home": state.clear(); await q.edit_message_text("Выбери профиль:", reply_markup=kb_profiles()); return
    if "profile" not in state: await q.edit_message_text("Сначала /start", reply_markup=kb_profiles()); return
    profile=state["profile"]
    if data=="back_profile": await profile_menu(q.message,profile); return
    if data=="show_categories": await q.edit_message_text("Категории:", reply_markup=kb_categories(profile)); return
    if data=="add_cat": state["stage"]="await_cat"; await q.edit_message_text("Название новой категории:", reply_markup=kb_home()); return
    if data.startswith("cat_"): cat=data.split("_",1)[1]; state["category"]=cat; await q.edit_message_text(f"Категория: {cat}", reply_markup=kb_links(profile,cat)); return
    if data=="back_categories": await q.edit_message_text("Категории:", reply_markup=kb_categories(profile)); return
    if data=="all_links": await q.edit_message_text("Все ссылки:", reply_markup=kb_all_links(profile)); return
    # link actions
    if data.startswith("link_"):
        lid=int(data.split("_")[1]); row=db("SELECT name,url FROM links WHERE id=?",(lid,),fetch=True)[0]
        await q.message.reply_text(f"[{row['name']}]({row['url']})", parse_mode="Markdown", disable_web_page_preview=False)
        return
    if data.startswith("fav_"):
        lid=int(data.split("_")[1]); fav=db("SELECT favorite FROM links WHERE id=?",(lid,),fetch=True)[0]["favorite"]
        db("UPDATE links SET favorite=? WHERE id=?",(0 if fav else 1,lid))
        if "category" in state:
            cat=state["category"]; await q.edit_message_reply_markup(reply_markup=kb_links(profile,cat))
        else:
            await q.edit_message_reply_markup(reply_markup=kb_all_links(profile))
        return

async def text(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.message.from_user.id
    state=user_state.get(uid)
    if not state or "profile" not in state: await update.message.reply_text("/start"); return
    profile=state["profile"]
    if state.get("stage")=="await_cat":
        cat=update.message.text.strip()
        db("INSERT INTO links(profile,category,name,url,created) VALUES(?,?,?,?,?)",(profile,cat,"example","https://example.com", datetime.datetime.utcnow().isoformat()))
        state.pop("stage",None)
        await update.message.reply_text("Категория добавлена.", reply_markup=kb_profile_menu())
        return
    await update.message.reply_text("Используй меню.")

async def export_cmd(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.message.from_user.id
    state=user_state.get(uid)
    if not state or "profile" not in state: await update.message.reply_text("Сначала /start"); return
    profile=state["profile"]
    rows=db("SELECT category,name,url,favorite,created FROM links WHERE profile=?",(profile,),fetch=True)
    if not rows: await update.message.reply_text("Нет ссылок"); return
    buf=io.StringIO(); w=csv.writer(buf); w.writerow(["Категория","Название","URL","Избранное","Создано"])
    for r in rows: w.writerow([r["category"],r["name"],r["url"],r["favorite"],r["created"]])
    data=BytesIO(buf.getvalue().encode("utf-8"))
    await update.message.reply_document(InputFile(data, filename=f"{profile}_links.csv"))

def main():
    token=os.getenv("BOT_TOKEN"); assert token, "BOT_TOKEN missing"
    app=ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    app.add_handler(CommandHandler("export", export_cmd))
    app.bot.set_my_commands([("start","Меню профилей"), ("export","Экспорт CSV")])
    log.info("Bot run"); app.run_polling()
if __name__=="__main__": main()
