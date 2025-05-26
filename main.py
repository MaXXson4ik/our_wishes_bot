
import os, logging, sqlite3, threading, http.server, socketserver, datetime, csv, io
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# --- heartbeat HTTP server for Render ---
def run_probe():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
        def log_message(self,*a): pass
    port=int(os.getenv("PORT","8080"))
    with socketserver.TCPServer(("",port),H) as srv: srv.serve_forever()
threading.Thread(target=run_probe, daemon=True).start()

# --- logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("bot")

# --- database ---
DB="bot.db"
def init_db():
    with sqlite3.connect(DB) as con:
        cur=con.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("""CREATE TABLE IF NOT EXISTS categories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT,
            name TEXT
        )""")
        cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_cat ON categories(profile,name)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS links(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT,
            category TEXT,
            name TEXT,
            url TEXT,
            favorite INTEGER DEFAULT 0,
            created TEXT,
            updated TEXT
        )""")
        con.commit()
init_db()

def db(q,p=(),fetch=False):
    with sqlite3.connect(DB) as con:
        con.row_factory=sqlite3.Row
        cur=con.cursor(); cur.execute(q,p); con.commit()
        return cur.fetchall() if fetch else None

# --- keyboards ---
PROFILES=["Котик","Солнышко"]
def kb_profiles(): return InlineKeyboardMarkup([[InlineKeyboardButton(p, callback_data=f"profile_{p}")] for p in PROFILES])

def kb_home(): return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Домой",callback_data="home")]])

def kb_profile_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Все ссылки", callback_data="all_links")],
        [InlineKeyboardButton("Категории",  callback_data="show_categories")],
        [InlineKeyboardButton("➕ Новая категория", callback_data="add_cat")],
        [InlineKeyboardButton("🏠 Домой", callback_data="home")]
    ])

def kb_categories(profile):
    rows=db("SELECT name FROM categories WHERE profile=? ORDER BY name",(profile,),True)
    kb=[[InlineKeyboardButton(r['name'],callback_data=f"cat_{r['name']}")] for r in rows]
    kb.append([InlineKeyboardButton("⬅️ Назад",callback_data="back_profile")])
    kb.append([InlineKeyboardButton("🏠 Домой",callback_data="home")])
    return InlineKeyboardMarkup(kb)

def kb_links(profile,cat):
    rows=db("SELECT id,name,favorite FROM links WHERE profile=? AND category=?",(profile,cat),True)
    kb=[[InlineKeyboardButton("➕ Добавить ссылку",callback_data="add_link")]]
    for r in rows:
        star="⭐" if r['favorite'] else "☆"
        kb.append([
            InlineKeyboardButton(r['name'], callback_data=f"open_{r['id']}"),
            InlineKeyboardButton(star,      callback_data=f"fav_{r['id']}"),
            InlineKeyboardButton("✏️",      callback_data=f"edit_{r['id']}"),
            InlineKeyboardButton("🗑️",      callback_data=f"del_{r['id']}")
        ])
    kb.append([InlineKeyboardButton("⬅️ Назад",callback_data="back_categories")])
    kb.append([InlineKeyboardButton("🏠 Домой",callback_data="home")])
    return InlineKeyboardMarkup(kb)

def kb_all_links(profile):
    rows=db("SELECT id,name,favorite,category FROM links WHERE profile=? ORDER BY category",(profile,),True)
    kb=[]
    for r in rows:
        star="⭐" if r['favorite'] else "☆"
        label=f"[{r['category']}] {r['name']}"
        kb.append([
            InlineKeyboardButton(label, callback_data=f"open_{r['id']}"),
            InlineKeyboardButton(star,  callback_data=f"fav_{r['id']}")
        ])
    kb.append([InlineKeyboardButton("⬅️ Назад",callback_data="back_profile")])
    kb.append([InlineKeyboardButton("🏠 Домой",callback_data="home")])
    return InlineKeyboardMarkup(kb)

# --- in-memory state ---
user_state={}  # uid -> dict

# --- helpers ---
async def send_or_edit(msg_or_query, text, reply_markup):
    if hasattr(msg_or_query,"edit_message_text"):
        await msg_or_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await msg_or_query.reply_text(text, reply_markup=reply_markup)

# --- handlers ---
async def cmd_start(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери профиль:", reply_markup=kb_profiles())

async def callback(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; data=q.data
    st=user_state.setdefault(uid,{})
    if data.startswith("profile_"):
        st.clear(); st['profile']=data.split("_",1)[1]
        await send_or_edit(q,"Меню профиля:",kb_profile_menu()); return
    if data=="home": st.clear(); await send_or_edit(q,"Выбери профиль:",kb_profiles()); return
    if 'profile' not in st: await send_or_edit(q,"/start",kb_profiles()); return
    profile=st['profile']
    if data=="back_profile": await send_or_edit(q,"Меню профиля:",kb_profile_menu()); return
    if data=="show_categories": await send_or_edit(q,"Категории:", kb_categories(profile)); return
    if data=="add_cat":
        st['stage']="await_cat"; await send_or_edit(q,"Название новой категории:",kb_home()); return
    if data.startswith("cat_"):
        cat=data.split("_",1)[1]; st['category']=cat
        await send_or_edit(q,f"Категория: {cat}", kb_links(profile,cat)); return
    if data=="back_categories": await send_or_edit(q,"Категории:", kb_categories(profile)); return
    if data=="all_links": await send_or_edit(q,"Все ссылки:", kb_all_links(profile)); return
    if data=="add_link":
        st['stage']="await_link_name"; await send_or_edit(q,"Название ссылки:", kb_home()); return
    # actions on link
    if data.startswith("fav_"):
        lid=int(data.split("_")[1])
        fav=db("SELECT favorite FROM links WHERE id=?",(lid,),True)[0]['favorite']
        db("UPDATE links SET favorite=? WHERE id=?", (0 if fav else 1, lid))
        if 'category' in st:
            await q.edit_message_reply_markup(reply_markup=kb_links(profile, st['category']))
        else:
            await q.edit_message_reply_markup(reply_markup=kb_all_links(profile))
        return
    if data.startswith("del_"):
        lid=int(data.split("_")[1]); db("DELETE FROM links WHERE id=?",(lid,))
        cat=st.get('category')
        if cat: await q.edit_message_reply_markup(reply_markup=kb_links(profile,cat))
        else: await q.edit_message_reply_markup(reply_markup=kb_all_links(profile))
        return
    if data.startswith("edit_"):
        lid=int(data.split("_")[1]); st['edit_id']=lid; st['stage']="await_edit_name"
        await send_or_edit(q,"Новое название:", kb_home()); return
    if data.startswith("open_"):
        lid=int(data.split("_")[1]); row=db("SELECT name,url FROM links WHERE id=?",(lid,),True)[0]
        await q.message.reply_text(f"[{row['name']}]({row['url']})", parse_mode="Markdown", disable_web_page_preview=False); return

async def text(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.message.from_user.id; txt=update.message.text.strip()
    st=user_state.get(uid)
    if not st or 'profile' not in st: await update.message.reply_text("/start"); return
    profile=st['profile']
    if st.get('stage')=="await_cat":
        db("INSERT OR IGNORE INTO categories(profile,name) VALUES(?,?)",(profile,txt))
        st.pop('stage',None)
        await update.message.reply_text("Категория создана.", reply_markup=kb_profile_menu()); return
    if st.get('stage')=="await_link_name":
        st['tmp_name']=txt; st['stage']="await_link_url"
        await update.message.reply_text("URL:", reply_markup=kb_home()); return
    if st.get('stage')=="await_link_url":
        url=txt if txt.startswith("http") else "http://"+txt
        cat=st.get('category')
        db("INSERT INTO links(profile,category,name,url,created) VALUES(?,?,?,?,?)",
           (profile,cat, st.pop('tmp_name'), url, datetime.datetime.utcnow().isoformat()))
        st.pop('stage',None)
        await update.message.reply_text("Ссылка добавлена.", reply_markup=kb_links(profile,cat)); return
    if st.get('stage')=="await_edit_name":
        st['new_name']=txt; st['stage']="await_edit_url"
        await update.message.reply_text("Новый URL:", reply_markup=kb_home()); return
    if st.get('stage')=="await_edit_url":
        url=txt if txt.startswith("http") else "http://"+txt
        lid=st.pop('edit_id')
        db("UPDATE links SET name=?, url=?, updated=? WHERE id=?",
           (st.pop('new_name'), url, datetime.datetime.utcnow().isoformat(), lid))
        cat=st.get('category')
        st.pop('stage',None)
        if cat:
            await update.message.reply_text("Сохранено.", reply_markup=kb_links(profile,cat))
        else:
            await update.message.reply_text("Сохранено.", reply_markup=kb_all_links(profile))
        return
    await update.message.reply_text("Используй меню.")

def main():
    token=os.getenv("BOT_TOKEN"); assert token
    app=ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    app.bot.set_my_commands([("start","Меню профилей")])
    log.info("Bot start"); app.run_polling()

if __name__=="__main__": main()
