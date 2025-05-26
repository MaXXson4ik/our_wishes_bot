
import os, logging, sqlite3, threading, http.server, socketserver, datetime, csv, io
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# --- tiny HTTP server for Render ---
def run_probe():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
        def log_message(self, f,*a): pass
    port=int(os.getenv("PORT","8080"))
    with socketserver.TCPServer(("",port),H) as s: s.serve_forever()
threading.Thread(target=run_probe, daemon=True).start()

# --- logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("bot")

# --- database ---
DB="bot.db"
def init_db():
    with sqlite3.connect(DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS links(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT, category TEXT,
            name TEXT, url TEXT, favorite INTEGER DEFAULT 0,
            created TEXT, updated TEXT)""")
init_db()

def db(q, params=(), fetch=False):
    with sqlite3.connect(DB) as con:
        con.row_factory=sqlite3.Row
        cur=con.cursor(); cur.execute(q, params); con.commit()
        return cur.fetchall() if fetch else None

# --- keyboards ---
PROFILES=["Котик","Солнышко"]
def kb_profiles(): return InlineKeyboardMarkup([[InlineKeyboardButton(p,callback_data=f"profile_{p}")] for p in PROFILES])

def kb_home(): return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Домой", callback_data="home")]])

def kb_profile_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Все ссылки", callback_data="all_links")],
        [InlineKeyboardButton("Категории", callback_data="show_categories")],
        [InlineKeyboardButton("➕ Новая категория", callback_data="add_cat")],
        [InlineKeyboardButton("🏠 Домой", callback_data="home")]
    ])

def kb_categories(profile):
    rows=db("SELECT DISTINCT category FROM links WHERE profile=? ORDER BY category",(profile,),True)
    kb=[[InlineKeyboardButton(r['category'],callback_data=f"cat_{r['category']}")] for r in rows]
    kb.append([InlineKeyboardButton("⬅️ Назад",callback_data="back_profile")])
    kb.append([InlineKeyboardButton("🏠 Домой",callback_data="home")])
    return InlineKeyboardMarkup(kb)

def kb_links(profile,cat):
    rows=db("SELECT id,name,favorite FROM links WHERE profile=? AND category=?",(profile,cat),True)
    kb=[[InlineKeyboardButton("➕ Добавить ссылку",callback_data="add_link")]]
    for r in rows:
        star="⭐" if r['favorite'] else "☆"
        kb.append([
            InlineKeyboardButton(r['name'],callback_data=f"link_{r['id']}"),
            InlineKeyboardButton(star,callback_data=f"fav_{r['id']}"),
            InlineKeyboardButton("✏️",callback_data=f"edit_{r['id']}"), 
            InlineKeyboardButton("🗑️",callback_data=f"del_{r['id']}")
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
            InlineKeyboardButton(label,callback_data=f"link_{r['id']}"),
            InlineKeyboardButton(star,callback_data=f"fav_{r['id']}")
        ])
    kb.append([InlineKeyboardButton("⬅️ Назад",callback_data="back_profile")])
    kb.append([InlineKeyboardButton("🏠 Домой",callback_data="home")])
    return InlineKeyboardMarkup(kb)

# --- state ---
user_state={}  # uid -> dict

# --- handlers ---
async def start(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери профиль:", reply_markup=kb_profiles())

async def callback(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; data=q.data
    st=user_state.setdefault(uid,{})
    if data.startswith("profile_"):
        st.clear(); st['profile']=data.split('_',1)[1]
        await q.edit_message_text(f"Профиль: {st['profile']}", reply_markup=kb_profile_menu()); return
    if data=="home": st.clear(); await q.edit_message_text("Выбери профиль:", reply_markup=kb_profiles()); return
    if 'profile' not in st: await q.edit_message_text("Сначала /start", reply_markup=kb_profiles()); return
    profile=st['profile']
    if data=="back_profile": await q.edit_message_text("Меню профиля:", reply_markup=kb_profile_menu()); return
    if data=="show_categories": await q.edit_message_text("Категории:", reply_markup=kb_categories(profile)); return
    if data=="add_cat": st['stage']='await_cat'; await q.edit_message_text("Название категории:", reply_markup=kb_home()); return
    if data.startswith("cat_"): cat=data.split('_',1)[1]; st['category']=cat; await q.edit_message_text(f"Категория: {cat}", reply_markup=kb_links(profile,cat)); return
    if data=="back_categories": await q.edit_message_text("Категории:", reply_markup=kb_categories(profile)); return
    if data=="all_links": await q.edit_message_text("Все ссылки:", reply_markup=kb_all_links(profile)); return
    if data=="add_link": st['stage']='await_link_name'; await q.edit_message_text("Название новой ссылки:", reply_markup=kb_home()); return
    # links actions (fav/del etc) omitted for brevity
    if data.startswith("link_"):
        lid=int(data.split('_')[1])
        row=db("SELECT name,url FROM links WHERE id=?",(lid,),True)[0]
        await q.message.reply_text(f"[{row['name']}]({row['url']})", parse_mode="Markdown", disable_web_page_preview=False)
        return

async def text(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.message.from_user.id
    st=user_state.get(uid)
    if not st or 'profile' not in st: await update.message.reply_text("/start"); return
    profile=st['profile']; msg=update.message.text.strip()
    if st.get('stage')=='await_cat':
        db("INSERT INTO links(profile,category,name,url,created) VALUES(?,?,?,?,?)",(profile,msg,'example','https://example.com', datetime.datetime.utcnow().isoformat()))
        st.pop('stage',None)
        await update.message.reply_text("Категория создана.", reply_markup=kb_profile_menu()); return
    if st.get('stage')=='await_link_name':
        st['tmp_name']=msg; st['stage']='await_link_url'
        await update.message.reply_text("URL:", reply_markup=kb_home()); return
    if st.get('stage')=='await_link_url':
        cat=st.get('category','Прочее')
        url=msg if msg.startswith('http') else 'http://'+msg
        db("INSERT INTO links(profile,category,name,url,created) VALUES(?,?,?,?,?)",(profile,cat,st.pop('tmp_name'),url, datetime.datetime.utcnow().isoformat()))
        st.pop('stage',None)
        await update.message.reply_text("Ссылка добавлена.", reply_markup=kb_links(profile,cat)); return
    await update.message.reply_text("Используй меню.")

def main():
    token=os.getenv('BOT_TOKEN'); assert token
    app=ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    app.bot.set_my_commands([('start','Меню профилей')])
    app.run_polling()

if __name__=='__main__': main()
