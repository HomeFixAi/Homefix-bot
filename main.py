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
from duckduckgo_search import DDGS 

# ==========================================================
# 1. SOZLAMALAR (KALITLAR)
# ==========================================================
BOT_TOKEN = "7978174707:AAFjHjK1tB9AsY1yloTS-9vmykiJ8BacZPs"
PAYMENT_TOKEN = "371317599:TEST:1770638863894" 
GROQ_API_KEY = "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"
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
    # Ustalar jadvali (YANGI)
    cursor.execute('''CREATE TABLE IF NOT EXISTS masters 
                      (user_id INTEGER PRIMARY KEY, full_name TEXT, specialty TEXT, phone TEXT)''')
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
    return user # user[3] bu is_premium

def set_premium(user_id):
    conn = sqlite3.connect('homefix_pro.db')
    conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def register_master_db(user_id, full_name, specialty):
    conn = sqlite3.connect('homefix_pro.db')
    conn.execute("INSERT OR REPLACE INTO masters (user_id, full_name, specialty) VALUES (?, ?, ?)", 
                 (user_id, full_name, specialty))
    conn.commit()
    conn.close()

def update_context(user_id, role, content):
    if user_id not in user_context:
        user_context[user_id] = deque(maxlen=5) 
    user_context[user_id].append({"role": role, "content": content})

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# ==========================================================
# 4. MENYULAR VA TUGMALAR
# ==========================================================
def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🛠 Muammo yechish")       # Hamma uchun
    kb.button(text="🧮 Material Hisoblash")   # PREMIUM
    kb.button(text="👷‍♂️ Men Ustaman")          # Baza yig'ish
    kb.button(text="💎 Premium Panel")
    kb.button(text="👤 Profilim")
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def premium_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Sotib olish (50,000 so'm)", callback_data="buy_premium")
    return kb.as_markup()

def master_reg_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚰 Santexnik")
    kb.button(text="⚡ Elektrik")
    kb.button(text="❄️ Maishiy Texnika")
    kb.button(text="🏠 Universal Usta")
    kb.button(text="🔙 Bosh menyu")
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def calc_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🧱 G'isht/Blok")
    kb.button(text="🎨 Bo'yoq (Kraska)")
    kb.button(text="📜 Oboy (Gulqog'oz)")
    kb.button(text="🪵 Laminat/Tarkett")
    kb.button(text="🔙 Bosh menyu")
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)

# ==========================================================
# 5. BOT MANTIQI (ASOSIY QISM)
# ==========================================================

@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    register_user(message.from_user)
    await message.answer(
        f"🏠 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
        "Men <b>HomeFix Pro</b> — uyingizdagi Sun'iy Ong yordamchisiman.\n\n"
        "🔻 <b>Bepul imkoniyatlar:</b>\n"
        "• Savol-javob va Internet qidiruvi\n"
        "• Usta bo'lib ro'yxatdan o'tish\n\n"
        "💎 <b>Premium imkoniyatlar:</b>\n"
        "• 📸 Rasm orqali diagnostika (Vision)\n"
        "• 🧮 Material hisoblash kalkulyatori",
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

# --- PREMIUM PANEL ---
@dp.message(F.text == "💎 Premium Panel")
async def premium_panel(message: types.Message):
    text = ("💎 <b>Premium Statusga o'ting!</b>\n\n"
            "⚠️ <i>Hozir sizda Rasm tahlili va Kalkulyator yopiq.</i>\n\n"
            "✅ <b>Smart Vision:</b> Rasmga qarab muammoni va narxni aytadi.\n"
            "✅ <b>Kalkulyator:</b> Remont xarajatini hisoblab beradi.\n\n"
            "💰 <b>Narxi: 50,000 so'm / oy</b>")
    await message.answer(text, reply_markup=premium_kb())

@dp.callback_query(F.data == "buy_premium")
async def buy_click(callback: types.CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="HomeFix Premium",
        description="Smart Vision va Kalkulyator (1 oy)",
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
    set_premium(message.from_user.id)
    await message.answer("🎉 <b>Tabriklaymiz!</b> Siz endi Premium a'zosiz!\nBarcha funksiyalar ochildi.")

# --- YANGI: MEN USTAMAN (BAZA YIG'ISH - BEPUL) ---
@dp.message(F.text == "👷‍♂️ Men Ustaman")
async def master_start(message: types.Message):
    await message.answer("🤝 Jamoamizga xush kelibsiz! Sohangizni tanlang:", reply_markup=master_reg_kb())

@dp.message(F.text.in_({"🚰 Santexnik", "⚡ Elektrik", "❄️ Maishiy Texnika", "🏠 Universal Usta"}))
async def master_save(message: types.Message):
    register_master_db(message.from_user.id, message.from_user.full_name, message.text)
    await message.answer("✅ <b>Qabul qilindi!</b>\nSizni bazaga qo'shdik. Buyurtma bo'lsa xabar beramiz.", reply_markup=main_menu_kb())
    # Adminga xabar
    await bot.send_message(ADMIN_ID, f"🔔 YANGI USTA:\n{message.from_user.full_name} - {message.text}")

@dp.message(F.text == "🔙 Bosh menyu")
async def back_main(message: types.Message):
    await message.answer("Bosh menyu:", reply_markup=main_menu_kb())

@dp.message(F.text == "🛠 Muammo yechish")
async def ask_problem(message: types.Message):
    await message.answer("Men eshitaman! \n🎤 <b>Gapiring</b> (Ovozli xabar),\n📸 <b>Rasm yuboring</b> (Premium),\n📝 Yoki <b>yozing</b>.")

# ==========================================================
# 6. SUN'IY ONG (AI) QISMI + KALKULYATOR
# ==========================================================

# --- YANGI QISM: INTERNET QIDIRUV TIZIMI ---
def search_internet(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region="uz-uz", max_results=3))
            if not results: return "Topilmadi."
            return "\n".join([f"- {r['title']}: {r['body']} ({r['href']})" for r in results])
    except Exception as e: return str(e)

# 1. KALKULYATOR (FAQAT PREMIUM UCHUN!)
@dp.message(F.text == "🧮 Material Hisoblash")
async def open_calc(message: types.Message):
    # TEKSHIRISH: User Premiummi?
    user = get_user_data(message.from_user.id)
    if not user or user[3] == 0: # 0 = Oddiy
        await message.answer("🔒 <b>Bu funksiya faqat PREMIUM a'zolar uchun!</b>\n\nRemont xarajatini aniq hisoblash uchun obuna bo'ling.", reply_markup=premium_kb())
        return

    await message.answer("🧮 Nima hisoblaymiz?", reply_markup=calc_menu_kb())

@dp.message(F.text.in_({"🧱 G'isht/Blok", "🎨 Bo'yoq (Kraska)", "📜 Oboy (Gulqog'oz)", "🪵 Laminat/Tarkett"}))
async def calc_process(message: types.Message):
    update_context(message.from_user.id, "system", f"Kalkulyator: {message.text}")
    await message.answer(f"✅ <b>{message.text}</b> tanlandi.\nXona o'lchamini yozing (masalan: 20 kv yoki 4x5 metr):", reply_markup=types.ReplyKeyboardRemove())

# 2. RASM TAHLILI (FAQAT PREMIUM UCHUN!)
@dp.message(F.photo)
async def ai_vision(message: types.Message):
    # TEKSHIRISH: User Premiummi?
    user = get_user_data(message.from_user.id)
    if not user or user[3] == 0:
        await message.answer("🔒 <b>Rasm tahlili faqat PREMIUM a'zolar uchun!</b>\n\nMen rasmga qarab muammoni, narxni va yechimni aytishim uchun obuna bo'ling.", reply_markup=premium_kb())
        return

    wait = await message.answer("🧐 <b>Premium Tahlil ketmoqda...</b>")
    file_path = f"img_{message.from_user.id}.jpg"
    try:
        photo = await bot.get_file(message.photo[-1].file_id)
        await bot.download_file(photo.file_path, file_path)
        base64_image = encode_image(file_path)
        
        system_instruction = """
        Sen HomeFix Bosh Muhandisisan. Rasmga qarab tashxis qo'y.
        1. Xavfsizlikni tekshir.
        2. Nima buzilganini va modelini aniqla (stikerlarni o'qi).
        3. O'zbekiston bozoridagi real narxni ayt.
        4. Javobni lo'nda qilib O'zbek tilida yoz.
        """

        messages = [{"role": "user", "content": [
            {"type": "text", "text": system_instruction},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]}]
        
        completion = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview", # Barqaror model
            messages=messages, temperature=0.5, max_tokens=1024
        )
        response = completion.choices[0].message.content
        await wait.edit_text(f"🔧 <b>XULOSA:</b>\n\n{response}")
    except Exception as e:
        await wait.edit_text(f"❌ Xatolik: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# 3. UNIVERSAL CHAT (HAMMA UCHUN, LEKIN KALKULYATORNI HAM QAMRAB OLADI)
@dp.message(F.text | F.voice)
async def ai_agent(message: types.Message):
    # Kalkulyator rejimini tekshirish
    context_list = list(user_context.get(message.from_user.id, []))
    is_calc_mode = any("Kalkulyator" in str(item) for item in context_list)
    
    # Agar kalkulyator rejimi bo'lsa va user Premium bo'lmasa -> Bloklash shart emas, chunki menyudan o'tolmaydi.
    # Lekin baribir ehtiyot shart.
    
    wait = await message.answer("🌐 <b>Yechim qidiryapman...</b>")
    try:
        user_input = message.text
        if message.voice:
            file_path = f"voice_{message.from_user.id}.ogg"
            file = await bot.get_file(message.voice.file_id)
            await bot.download_file(file.file_path, file_path)
            with open(file_path, "rb") as f:
                user_input = client.audio.transcriptions.create(file=(file_path, f.read()), model="whisper-large-v3").text
            os.remove(file_path)
            await message.answer(f"🗣 <b>Savol:</b> {user_input}")

        # Search
        keywords = ["narx", "qancha", "sotib", "texnomart", "olx", "bozor", "ob-havo", "dollar"]
        search_result = ""
        if any(word in user_input.lower() for word in keywords):
            search_result = search_internet(user_input)

        # Prompt
        sys_prompt = f"""
        Sen "HomeFix AI" yordamchisisan.
        Internet ma'lumoti: {search_result}
        
        Vazifa:
        1. Agar foydalanuvchi "Kalkulyator" rejimida bo'lsa (o'lcham yozsa), unga materialni hisoblab ber (faqat Premium userlar uchun aslida, lekin bu yerda hisoblab berovur, agar menyudan o'tgan bo'lsa).
        2. Agar oddiy savol bo'lsa, internetdan yoki o'z bilimingdan javob ber.
        3. Narxlarni so'rasa, "1 dona" yoki "1 kub" farqini tushuntir.
        """
        
        update_context(message.from_user.id, "user", user_input)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": sys_prompt}] + list(user_context[message.from_user.id])
        )
        response = completion.choices[0].message.content
        update_context(message.from_user.id, "assistant", response)
        
        markup = main_menu_kb() # Har doim menyuni qaytaramiz
        await wait.edit_text(response, reply_markup=markup)

    except Exception as e:
        await wait.edit_text(f"❌ Xatolik: {e}")

# ==========================================================
# 7. ISHGA TUSHIRISH
# ==========================================================
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
