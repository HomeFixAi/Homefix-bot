import asyncio
import logging
import sqlite3
import os
import base64
from collections import deque
from groq import Groq
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.client.default import DefaultBotProperties
from aiohttp import web  # <--- Yangi qo'shimcha

# ==========================================================
# 1. SOZLAMALAR
# ==========================================================
BOT_TOKEN = "7978174707:AAFjHjK1tB9AsY1yloTS-9vmykiJ8BacZPs"
PAYMENT_TOKEN = "371317599:TEST:1770638863894"
GROQ_API_KEY = "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"
ADMIN_ID = 1967786876 

client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
user_context = {}

# --- RENDER UCHUN SOXTA WEB SERVER ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render PORT muhit o'zgaruvchisini beradi, bo'lmasa 8080 ni oladi
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🚀 Health check server started on port {port}")

# ==========================================================
# 2. MA'LUMOTLAR BAZASI
# ==========================================================
def init_db():
    conn = sqlite3.connect('homefix_pro.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, username TEXT, is_premium INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS masters 
                      (id INTEGER PRIMARY KEY, name TEXT, profession TEXT, phone TEXT, city TEXT)''')
    if cursor.execute("SELECT count(*) FROM masters").fetchone()[0] == 0:
        cursor.executemany("INSERT INTO masters VALUES (?,?,?,?,?)", [
            (1, "Ali Usta", "Santexnik", "+998901234567", "Toshkent"),
            (2, "Vali Usta", "Elektrik", "+998939876543", "Samarqand"),
            (3, "G'ani Usta", "Maishiy texnika", "+998971112233", "Buxoro")
        ])
        conn.commit()
    conn.close()

def register_user(user_id, username):
    conn = sqlite3.connect('homefix_pro.db')
    conn.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

# ==========================================================
# 3. YORDAMCHI FUNKSIYALAR
# ==========================================================
def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🤖 AI Diagnostika")
    kb.button(text="📍 Yaqin usta")
    kb.button(text="💎 Premium Obuna")
    kb.button(text="👤 Profil")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def update_context(user_id, role, content):
    if user_id not in user_context:
        user_context[user_id] = deque(maxlen=5)
    user_context[user_id].append({"role": role, "content": content})

# ==========================================================
# 4. BOT HANDLERLARI
# ==========================================================

@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    register_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"👋 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
        "Men <b>HomeFix AI</b> — uyingizdagi muammolarni AI yordamida hal qilaman.",
        reply_markup=main_menu()
    )

@dp.message(F.text == "📍 Yaqin usta")
async def find_master(message: types.Message):
    conn = sqlite3.connect('homefix_pro.db')
    masters = conn.execute("SELECT name, profession, phone, city FROM masters").fetchall()
    conn.close()
    text = "🛠 <b>Tavsiya etilgan ustalar:</b>\n\n"
    for m in masters:
        text += f"👤 <b>{m[0]}</b> ({m[1]})\n📍 {m[3]} | 📞 {m[2]}\n➖➖➖➖➖\n"
    await message.answer(text)

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    wait = await message.answer("👀 <i>Rasm tahlil qilinmoqda...</i>")
    file_path = f"img_{message.from_user.id}.jpg"
    try:
        photo = await bot.get_file(message.photo[-1].file_id)
        await bot.download_file(photo.file_path, file_path)
        base64_image = encode_image(file_path)
        completion = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Bu rasmdagi texnik muammoni ko'r va menga O'ZBEK tilida yechim ber."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}]
        )
        await wait.edit_text(f"📸 <b>AI Xulosasi:</b>\n\n{completion.choices[0].message.content}")
    except Exception as e:
        await wait.edit_text(f"❌ Xatolik: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

@dp.message()
async def chat_logic(message: types.Message):
    if not message.text: return
    wait = await message.answer("💬 <i>Yozmoqda...</i>")
    try:
        update_context(message.from_user.id, "user", message.text)
        sys_msg = {"role": "system", "content": "Sen HomeFix AI profesional ustasisan. Faqat O'ZBEK tilida javob ber."}
        history = [sys_msg] + list(user_context[message.from_user.id])
        completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=history)
        response = completion.choices[0].message.content
        update_context(message.from_user.id, "assistant", response)
        await wait.edit_text(response)
    except Exception as e:
        await wait.edit_text(f"Aloqa uzildi: {e}")

# ==========================================================
# 5. ISHGA TUSHIRISH
# ==========================================================
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    # Botingizni va soxta serverni bir vaqtda ishga tushiramiz
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
