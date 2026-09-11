import os
import time
import sqlite3
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ==================== البيانات المثبتة ====================
BOT_TOKEN = "8954423162:AAHSAyR39EyIVtz0WatixCS5tz1mNeEpcqM"
ADMIN_ID = 155765606  # محمد غني عبد النبي
APP_URL = os.getenv("APP_URL", "http://localhost:8000")  # ضع رابط الاستضافة هنا
# ==========================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI(title="Khayrat Iraq Bot")

DB_PATH = "khayrat_iraq.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        points INTEGER DEFAULT 0,
        last_mine INTEGER DEFAULT 0,
        referrer_id INTEGER DEFAULT 0,
        created_at INTEGER DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        method TEXT,
        account TEXT,
        amount INTEGER,
        status TEXT DEFAULT 'pending',
        created_at INTEGER
    )
    """)
    conn.commit()
    conn.close()

init_db()

def get_or_create_user(user_id: int, name: str, referrer_id: int = 0):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, name, points, last_mine, referrer_id FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        now = int(time.time())
        bonus = 0
        if referrer_id and referrer_id != user_id:
            cur.execute("UPDATE users SET points = points + 100 WHERE user_id = ?", (referrer_id,))
            bonus = 50
        cur.execute("INSERT INTO users (user_id, name, points, last_mine, referrer_id, created_at) VALUES (?, ?, ?, 0, ?, ?)",
                    (user_id, name, bonus, referrer_id, now))
        conn.commit()
        cur.execute("SELECT user_id, name, points, last_mine, referrer_id FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
    conn.close()
    return {
        "user_id": row[0],
        "name": row[1],
        "points": row[2],
        "last_mine": row[3],
        "referrer_id": row[4]
    }

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/user")
async def get_user_data(user_id: int, name: str = "مستخدم"):
    user_data = get_or_create_user(user_id, name)
    return {"success": True, "user": user_data}

class MineRequest(BaseModel):
    user_id: int

@app.post("/api/mine")
async def start_mine(data: MineRequest):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT points, last_mine FROM users WHERE user_id = ?", (data.user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"success": False, "msg": "المستخدم غير مسجل"}

    points, last_mine = row
    now = int(time.time())
    cycle = 86400
    if now - last_mine < cycle:
        conn.close()
        return {"success": False, "msg": "دورة التعدين قيد التشغيل بالفعل"}

    new_points = points + 400
    cur.execute("UPDATE users SET points = ?, last_mine = ? WHERE user_id = ?", (new_points, now, data.user_id))
    conn.commit()
    conn.close()
    return {"success": True, "points": new_points, "last_mine": now}

class WithdrawRequest(BaseModel):
    user_id: int
    method: str
    account: str
    amount: int

@app.post("/api/withdraw")
async def request_withdraw(req: WithdrawRequest):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT points, name FROM users WHERE user_id = ?", (req.user_id,))
    row = cur.fetchone()
    if not row or row[0] < req.amount:
        conn.close()
        return {"success": False, "msg": "الرصيد غير كافٍ"}

    new_points = row[0] - req.amount
    now = int(time.time())
    cur.execute("UPDATE users SET points = ? WHERE user_id = ?", (new_points, req.user_id))
    cur.execute("INSERT INTO withdrawals (user_id, method, account, amount, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                (req.user_id, req.method, req.account, req.amount, now))
    conn.commit()
    conn.close()

    try:
        msg = f"🔔 **طلب سحب جديد في خيرات العراق:**\n\n👤 الاسم: {row[1]}\n🆔 الآيدي: `{req.user_id}`\n💰 المبلغ: {req.amount} سنت (≈ {int(req.amount * 0.15)} د.ع)\n💳 الطريقة: {req.method}\n📱 الحساب: `{req.account}`"
        await bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
    except Exception as e:
        print("Admin notification error:", e)

    return {"success": True, "remaining_points": new_points}

# ==================== بوت تليجرام ====================
@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    ref_id = 0
    if command.args and command.args.isdigit():
        ref_id = int(command.args)

    get_or_create_user(message.from_user.id, message.from_user.first_name, ref_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 فتح تطبيق خيرات العراق", web_app=WebAppInfo(url=APP_URL))],
        [InlineKeyboardButton(text="📊 رصيدي الحالي", callback_data="my_balance")],
        [InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="my_ref")]
    ])

    await message.answer(
        f"أهلاً بك يا {message.from_user.first_name} في **بوت وتطبيق خيرات العراق** 🇮🇶⚡\n\n"
        f"اضغط الزر أدناه لتشغيل العداد اليومي وجمع السنتات وتحويلها إلى كاش (زين كاش، ماستر كارد، كروت شحن):",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data == "my_balance")
async def cb_balance(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT points FROM users WHERE user_id = ?", (callback.from_user.id,))
    row = cur.fetchone()
    conn.close()
    pts = row[0] if row else 0
    await callback.answer(f"رصيدك الحالي: {pts} سنت (≈ {int(pts*0.15)} د.ع)", show_alert=True)

@dp.callback_query(lambda c: c.data == "my_ref")
async def cb_ref(callback: types.CallbackQuery):
    ref_link = f"https://t.me/IraqKhayrat26bot?start={callback.from_user.id}"
    await callback.message.answer(f"🔗 رابط الدعوة الخاص بك:\n`{ref_link}`\n\nتكسب 100 سنت عن كل صديق يسجل من خلالك!", parse_mode="Markdown")
    await callback.answer()

async def run_services():
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    try:
        asyncio.run(run_services())
    except (KeyboardInterrupt, SystemExit):
        print("Stopped")
