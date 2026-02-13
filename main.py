import asyncio
import logging
import sqlite3
import os
import base64
from collections import deque
from groq import Groq
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import FSInputFile, LabeledPrice, PreCheckoutQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

# ==========================================================
# 1. SOZLAMALAR (TOKENLAR)
# ==========================================================
BOT_TOKEN = "7978174707:AAFjHjK1tB9AsY1yloTS-9vmykiJ8BacZPs"
PAYMENT_TOKEN = "371317599:TEST:1770638863894" # Click/Payme Test tokeni
GROQ_API_KEY = "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"
ADMIN_ID = 1967786876

# Tizimni sozlash
client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
user_context = {} 

# --- RENDER UCHUN SOXTA WEB SERVER (Bot o'chib qolmasligi uchun) ---
async def handle(request):
    return web.Response(text="HomeFix Pro is Running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ==========================================================
# 2. BAZA VA YORDAMCHI FUNKSIYALAR
# ==========================================================
def init_db():
    conn = sqlite3.connect('homefix_pro.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, is_premium INTEGER DEFAULT 0, joined_date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS masters 
                      (id INTEGER PRIMARY KEY, name TEXT, profession TEXT, phone TEXT, city TEXT)''')
    
    # Namuna ustalar (Agar bo'sh bo'lsa)
    if cursor.execute("SELECT count(*) FROM masters").fetchone()[0] == 0:
        cursor.executemany("INSERT INTO masters VALUES (?,?,?,?,?)", [
            (1, "Ali Usta", "Santexnik", "+998901234567", "Toshkent"),
            (2, "Vali Usta", "Elektrik", "+998939876543", "Samarqand"),
            (3, "G'ani Usta", "Maishiy texnika", "+998971112233", "Buxoro")
        ])
        conn.commit()
    conn.close()

def register_user(user):
    conn = sqlite3.connect('homefix_pro.db')
    conn.execute("INSERT OR IGNORE INTO users (user_id, username, full_name, joined_date) VALUES (?, ?, ?, date('now'))", 
                 (user.id, user.username, user.full_name))
    conn.commit()
    conn.close()

def get_user_info(user_id):
    conn = sqlite3.connect('homefix_pro.db')
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return user

def update_context(user_id, role, content):
    """Xotira: Bot avvalgi gaplarni eslab qoladi"""
    if user_id not in user_context:
        user_context[user_id] = deque(maxlen=10) # 10 ta oxirgi gapni eslab qoladi
    user_context[user_id].append({"role": role, "content": content})

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# ==========================================================
# 3. MENYULAR VA TUGMALAR (DIZAYN)
# ==========================================================
def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🛠 Muammo yechish") # AI
    kb.button(text="👤 Profilim")
    kb.button(text="💎 Premium Panel")
    kb.button(text="📞 Usta kerak")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)

def premium_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Sotib olish (50,000 so'm)", callback_data="buy_premium")
    kb.button(text="ℹ️ Imkoniyatlar", callback_data="premium_info")
    return kb.as_markup()

# ==========================================================
# 4. BOT MANTIQI (ASOSIY QISM)
# ==========================================================

@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    register_user(message.from_user)
    await message.answer(
        f"🏠 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
        "Men <b>HomeFix Pro</b> — uyingizdagi har qanday texnik muammoni hal qiluvchi aqlli yordamchiman.\n\n"
        "👇 <i>Quyidagi bo'limlardan birini tanlang:</i>",
        reply_markup=main_menu_kb()
    )

# --- PROFIL BO'LIMI ---
@dp.message(F.text == "👤 Profilim")
async def my_profile(message: types.Message):
    user = get_user_info(message.from_user.id)
    status = "💎 Premium" if user[3] else "bepul"
    text = (f"📂 <b>Sizning Profilingiz:</b>\n\n"
            f"👤 Ism: {user[2]}\n"
            f"🆔 ID: {user[0]}\n"
            f"🌟 Status: <b>{status}</b>\n"
            f"📅 Qo'shilgan sana: {user[4]}")
    await message.answer(text)

# --- PREMIUM PANEL ---
@dp.message(F.text == "💎 Premium Panel")
async def premium_panel(message: types.Message):
    text = ("💎 <b>HomeFix Premium</b>\n\n"
            "✅ Cheksiz AI so'rovlar\n"
            "✅ Rasm va Ovozli xabarlar tahlili\n"
            "✅ Eng kuchli 'Claude' rejimi\n"
            "✅ Reklamasiz\n\n"
            "💰 <b>Narxi: 50,000 so'm / oy</b>")
    await message.answer(text, reply_markup=premium_kb())

@dp.callback_query(F.data == "buy_premium")
async def buy_click(callback: types.CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="HomeFix Premium",
        description="1 oylik to'liq foydalanish",
        payload="premium_sub",
        provider_token=PAYMENT_TOKEN,
        currency="uzs",
        prices=[LabeledPrice(label="Obuna", amount=5000000)],
        start_parameter="premium-sub"
    )
    await callback.answer()

@dp.pre_checkout_query()
async def checkout_process(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: types.Message):
    conn = sqlite3.connect('homefix_pro.db')
    conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (message.from_user.id,))
    conn.commit()
    conn.close()
    await message.answer("🎉 <b>Tabriklaymiz!</b> Siz endi Premium foydalanuvchisiz!")

# --- USTA QIDIRISH ---
@dp.message(F.text == "📞 Usta kerak")
async def find_master(message: types.Message):
    conn = sqlite3.connect('homefix_pro.db')
    masters = conn.execute("SELECT name, profession, phone, city FROM masters").fetchall()
    conn.close()
    text = "👷‍♂️ <b>Bizning eng yaxshi ustalarimiz:</b>\n\n"
    for m in masters:
        text += f"▪️ <b>{m[0]}</b> ({m[1]}) - {m[3]}\n📞 Tel: {m[2]}\n\n"
    await message.answer(text)

# --- AI MUAMMO YECHISH (OVOZ, RASM, TEXT) ---
@dp.message(F.text == "🛠 Muammo yechish")
async def ask_problem(message: types.Message):
    await message.answer("Men tayyorman! 🎤 <b>Gapiring</b>, 📸 <b>Rasm tashlang</b> yoki 📝 <b>Yozing</b>.\n\nMuammo nimada?")

# 1. RASM TAHLILI (Llama Vision)
@dp.message(F.photo)
async def ai_vision(message: types.Message):
    wait = await message.answer("🧐 <i>Rasm tahlil qilinmoqda (bu biroz vaqt oladi)...</i>")
    file_path = f"img_{message.from_user.id}.jpg"
    try:
        photo = await bot.get_file(message.photo[-1].file_id)
        await bot.download_file(photo.file_path, file_path)
        base64_image = encode_image(file_path)
        
        # System prompt - rasm uchun
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": "Bu rasmdagi texnik muammoni aniqla va O'ZBEK tilida bosqichma-bosqich yechim ber. Usta kabi gapir."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}
        ]
        completion = client.chat.completions.create(model="meta-llama/llama-4-scout-17b-16e-instruct", messages=messages)
        await wait.edit_text(f"📸 <b>Xulosa:</b>\n\n{completion.choices[0].message.content}")
    except Exception as e:
        await wait.edit_text(f"❌ Xatolik: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# 2. OVOZ VA TEXT (Universal Aqlli Agent)
@dp.message(F.text | F.voice)
async def ai_agent(message: types.Message):
    wait = await message.answer("🤔 <i>O'ylayapman...</i>")
    user_input = ""
    
    try:
        # Agar ovoz bo'lsa - matnga aylantiramiz
        if message.voice:
            file_path = f"voice_{message.from_user.id}.ogg"
            file = await bot.get_file(message.voice.file_id)
            await bot.download_file(file.file_path, file_path)
            with open(file_path, "rb") as f:
                user_input = client.audio.transcriptions.create(
                    file=(file_path, f.read()), model="whisper-large-v3", response_format="text"
                )
            os.remove(file_path)
            await message.answer(f"🗣 <b>Siz aytdingiz:</b> {user_input}")
        else:
            user_input = message.text

        # AGENT UCHUN MAXSUS "MIYA" (System Prompt)
        # Bu yerda biz botga "Rol" o'ynashni o'rgatamiz
        system_prompt = """
        Sen HomeFix Pro - professional usta va muhandissan. 
        Vazifang: Foydalanuvchi muammosini hal qilish.
        
        Qoidalar:
        1. Faqat O'ZBEK tilida javob ber.
        2. Javobing aniq, lo'nda va foydali bo'lsin.
        3. Agar muammo xavfli bo'lsa (gaz, tok), avval xavfsizlik haqida ogohlantir.
        4. Javobni chiroyli formatda (sarlavha, punktlar bilan) yoz.
        """

        update_context(message.from_user.id, "user", user_input)
        history = [{"role": "system", "content": system_prompt}] + list(user_context[message.from_user.id])

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile", # Eng kuchli matn modeli
            messages=history
        )
        response = completion.choices[0].message.content
        update_context(message.from_user.id, "assistant", response)
        
        await wait.edit_text(response)

    except Exception as e:
        await wait.edit_text(f"❌ Uzr, xatolik yuz berdi: {e}")

# ==========================================================
# 5. ISHGA TUSHIRISH
# ==========================================================
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    # Web server va Botni birga yurgizamiz
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())

