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
from aiogram.types import FSInputFile, LabeledPrice, PreCheckoutQuery
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

# ==========================================================
# 1. SOZLAMALAR (KALITLAR)
# ==========================================================
# DIQQAT: Bu yerga o'z tokenlaringizni to'g'ri qo'ying
BOT_TOKEN = "7978174707:AAFjHjK1tB9AsY1yloTS-9vmykiJ8BacZPs"
PAYMENT_TOKEN = "371317599:TEST:1770638863894" 
GROQ_API_KEY = "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"

# Admin ID (Sizning ID raqamingiz - botga /start bosganda chiqadi, shuni yozing)
ADMIN_ID = 1967786876 

client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
user_context = {} 

# ==========================================================
# 2. RENDER UCHUN "YURAK" (WEB SERVER)
# ==========================================================
async def handle(request):
    return web.Response(text="HomeFix Pro is Running Live!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ==========================================================
# 3. MA'LUMOTLAR BAZASI (SQLITE)
# ==========================================================
def init_db():
    conn = sqlite3.connect('homefix_pro.db')
    cursor = conn.cursor()
    # Foydalanuvchilar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, is_premium INTEGER DEFAULT 0, joined_date TEXT)''')
    conn.commit()
    conn.close()

def register_user(user):
    conn = sqlite3.connect('homefix_pro.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, full_name, joined_date) VALUES (?, ?, ?, date('now'))", 
                 (user.id, user.username, user.full_name))
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('homefix_pro.db')
    cursor = conn.cursor()
    user = cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return user

def set_premium(user_id):
    conn = sqlite3.connect('homefix_pro.db')
    conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# Context (Xotira) funksiyasi
def update_context(user_id, role, content):
    if user_id not in user_context:
        user_context[user_id] = deque(maxlen=5) # Oxirgi 5 ta gapni eslab qoladi
    user_context[user_id].append({"role": role, "content": content})

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# ==========================================================
# 4. MENYULAR VA TUGMALAR
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
    return kb.as_markup()

# ==========================================================
# 5. BOT MANTIQI (ASOSIY QISM)
# ==========================================================

@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    register_user(message.from_user)
    await message.answer(
        f"🏠 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
        "Men <b>HomeFix Pro</b> — uyingizdagi har qanday buzilgan narsani tuzatishga yordam beradigan Sun'iy Ongman.\n\n"
        "📸 <i>Menga buzilgan narsani rasmga olib yuboring yoki muammoni yozing.</i>",
        reply_markup=main_menu_kb()
    )

# --- PROFIL ---
@dp.message(F.text == "👤 Profilim")
async def my_profile(message: types.Message):
    user = get_user_data(message.from_user.id)
    if user:
        status = "🌟 PREMIUM" if user[3] else "Oddiy"
        text = (f"📂 <b>Sizning Profilingiz:</b>\n\n"
                f"👤 Ism: {user[2]}\n"
                f"🆔 ID: {user[0]}\n"
                f"💎 Status: <b>{status}</b>\n"
                f"📅 A'zo bo'lgan sana: {user[4]}")
        await message.answer(text)

# --- PREMIUM SOTIB OLISH ---
@dp.message(F.text == "💎 Premium Panel")
async def premium_panel(message: types.Message):
    text = ("💎 <b>HomeFix Premium - Shaxsiy Muhandisingiz</b>\n\n"
            "✅ Cheksiz AI so'rovlar\n"
            "✅ <b>Smart Vision:</b> Rasmni detallargacha tahlil qilish\n"
            "✅ <b>Aniq Narx:</b> AI bozor narxlarini hisoblab beradi\n"
            "✅ Ustalar navbatsiz keladi\n\n"
            "💰 <b>Narxi: 50,000 so'm / oy</b>")
    await message.answer(text, reply_markup=premium_kb())

@dp.callback_query(F.data == "buy_premium")
async def buy_click(callback: types.CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="HomeFix Premium",
        description="To'liq imkoniyatlar to'plami (1 oy)",
        payload="premium_sub",
        provider_token=PAYMENT_TOKEN,
        currency="uzs",
        prices=[LabeledPrice(label="Obuna", amount=5000000)], # 50,000 so'm
        start_parameter="premium-sub"
    )
    await callback.answer()

@dp.pre_checkout_query()
async def checkout_process(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: types.Message):
    set_premium(message.from_user.id)
    await message.answer("🎉 <b>Tabriklaymiz!</b> Siz endi Premium a'zosiz!\nEndi rasm yuborib, to'liq tahlil olishingiz mumkin.")

# --- USTA QIDIRISH (AI ROUTING) ---
@dp.message(F.text == "📞 Usta kerak")
async def find_master(message: types.Message):
    await message.answer("📍 Iltimos, lokatsiyangizni yuboring yoki manzilingizni yozing. Men eng yaqin ustani qidiraman...")

@dp.message(F.text == "🛠 Muammo yechish")
async def ask_problem(message: types.Message):
    await message.answer("Men eshitaman! \n🎤 <b>Gapiring</b> (Ovozli xabar),\n📸 <b>Rasm yuboring</b>,\n📝 Yoki <b>yozing</b>.")

# ==========================================================
# 6. SUN'IY ONG (AI) QISMI - ENG MUHIM JOYI
# ==========================================================

# A) RASM TAHLILI (VISION - SENIOR ENGINEER)
@dp.message(F.photo)
async def ai_vision(message: types.Message):
    wait = await message.answer("🧐 <b>Rasm tahlil qilinmoqda...</b>\n<i>(Men 20 yillik tajribali muhandis sifatida ko'ryapman)</i>")
    
    file_path = f"img_{message.from_user.id}.jpg"
    try:
        photo = await bot.get_file(message.photo[-1].file_id)
        await bot.download_file(photo.file_path, file_path)
        base64_image = encode_image(file_path)
        
        # MUKAMMAL SYSTEM PROMPT
        system_instruction = """
        Sen HomeFix kompaniyasining Bosh Muhandisisan. Vazifang: Rasmdagi texnik muammoni aniqlash.

        QOIDALAR:
        1. XAVFSIZLIK: Agar rasmda ochiq simlar, gaz yoki suv toshqini bo'lsa, birinchi bo'lib "OGOHLANTIRISH" (qizil rangda) ber.
        2. TASHXIS: Nima buzilgan? Aniq texnik nomini ayt (masalan: "Smesitel kartriji" yoki "Avtomat o'chirgich").
        3. YECHIM:
           - Oddiy bo'lsa: Qanday tuzatishni tushuntir.
           - Qiyin bo'lsa: "Mutaxassis chaqiring" de va qaysi usta kerakligini ayt.
        4. NARX: O'zbekiston bozoridagi o'rtacha narxni (ehtiyot qism + xizmat) so'mda taxmin qil.
        
        Javobni chiroyli va lo'nda qilib, O'zbek tilida yoz.
        """

        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": system_instruction},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}
        ]
        
        # ENG KUCHLI VISION MODEL (90b)
        completion = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview", 
            messages=messages,
            temperature=0.6,
            max_tokens=1024
        )
        response = completion.choices[0].message.content
        await wait.edit_text(f"🔧 <b>XULOSA:</b>\n\n{response}")

    except Exception as e:
        await wait.edit_text(f"❌ Xatolik: {e}\n(Model band bo'lishi mumkin, qayta urinib ko'ring)")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# B) OVOZ VA MATN (CHAT AGENT)
@dp.message(F.text | F.voice)
async def ai_agent(message: types.Message):
    wait = await message.answer("🤔 Tushundim, yechim qidiryapman...")
    
    try:
        user_input = message.text
        # Agar ovozli xabar bo'lsa
        if message.voice:
            file_path = f"voice_{message.from_user.id}.ogg"
            file = await bot.get_file(message.voice.file_id)
            await bot.download_file(file.file_path, file_path)
            
            # Whisper (Ovozni matnga aylantirish)
            with open(file_path, "rb") as f:
                user_input = client.audio.transcriptions.create(
                    file=(file_path, f.read()), 
                    model="whisper-large-v3"
                ).text
            os.remove(file_path)
            await message.answer(f"🗣 <b>Siz aytdingiz:</b> <i>{user_input}</i>")

        # Chat modeli uchun Prompt
        sys_prompt = "Sen HomeFix ustasisan. Mijoz muammosiga aniq yechim ber. Xavfsizlikni birinchi o'ringa qo'y. Javobni O'zbek tilida ber."
        
        update_context(message.from_user.id, "user", user_input)
        
        # ENG KUCHLI MATN MODEL (70b)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": sys_prompt}] + list(user_context[message.from_user.id])
        )
        
        response = completion.choices[0].message.content
        update_context(message.from_user.id, "assistant", response)
        
        await wait.edit_text(response)

    except Exception as e:
        await wait.edit_text(f"❌ Xatolik: {e}")

# ==========================================================
# 7. ISHGA TUSHIRISH
# ==========================================================
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    # Web server va Bot birga ishlaydi
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
