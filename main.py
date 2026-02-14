import asyncio
import logging
import sqlite3
import os
import base64
from datetime import datetime
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
# 1. SOZLAMALAR VA KALITLAR
# ==========================================================
BOT_TOKEN = "7978174707:AAFjHjK1tB9AsY1yloTS-9vmykiJ8BacZPs"
PAYMENT_TOKEN = "371317599:TEST:1770638863894" 
GROQ_API_KEY = "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"
ADMIN_ID = 1967786876  # Sizning ID (God Mode)

# ==========================================================
# 2. REAL BOZOR NARXLARI BAZASI (2026 O'ZBEKISTON)
# ==========================================================
# Bot hisoblaganda shu narxlarga qarab ish qiladi.
MARKET_DB = {
    "devor": {
        "oboy_oddiy": "Roloni (10m) 150,000 - 250,000 so'm",
        "oboy_yuviladigan": "Roloni (10m) 350,000 - 600,000 so'm",
        "emulsiya": "20kg chelak - 400,000 so'm (o'rtacha sifat)",
        "shpatlevka": "Qop (20kg) - 45,000 so'm",
        "gish_pishgan": "1 dona - 1,800 so'm",
        "shlakoblok": "1 dona - 4,500 so'm"
    },
    "pol": {
        "laminat_32": "1 kv.m - 75,000 so'm (Xitoy/Uzbek)",
        "laminat_33": "1 kv.m - 110,000 so'm (Rossiya/Yevropa)",
        "kafel": "1 kv.m - 90,000 dan 250,000 gacha",
        "plintus": "1 dona (2.5m) - 15,000 so'm"
    },
    "shif": {
        "gipskarton": "1 list (1.2x2.5) - 45,000 so'm (Knauf)",
        "profil_fon": "1 dona (3m) - 12,000 so'm",
        "armstrong": "1 kv.m to'liq komplekt - 65,000 so'm"
    },
    "elektr": {
        "kabel_2x2_5": "1 metr - 8,500 so'm (Mis)",
        "rozetka": "1 dona - 25,000 so'm (Viko)",
        "avtomat": "1 dona - 45,000 so'm"
    }
}

client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
user_context = {} 

# ==========================================================
# 3. WEB SERVER (RENDER UCHUN)
# ==========================================================
async def handle(request):
    return web.Response(text="HomeFix Pro v2.0 is Active!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ==========================================================
# 4. MA'LUMOTLAR BAZASI (SQLITE)
# ==========================================================
def init_db():
    conn = sqlite3.connect('homefix_pro.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, is_premium INTEGER DEFAULT 0, joined_date TEXT)''')
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
    return user 

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
# 5. MENYULAR (KENGAYTIRILGAN)
# ==========================================================
def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🛠 Muammo yechish")
    kb.button(text="🧮 Material Hisoblash")
    kb.button(text="👷‍♂️ Men Ustaman")
    kb.button(text="💎 Premium Panel")
    kb.button(text="👤 Profilim")
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def calc_menu_kb():
    # KENGAYTIRILGAN KALKULYATOR MENYUSI
    kb = ReplyKeyboardBuilder()
    kb.button(text="🧱 Devor (G'isht/Oboy)")
    kb.button(text="🪵 Pol (Laminat/Kafel)")
    kb.button(text="🏠 Shif (Gips/Potolok)")
    kb.button(text="⚡ Elektr (Kabel/Rozetka)")
    kb.button(text="🔙 Bosh menyu")
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def master_reg_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚰 Santexnik")
    kb.button(text="⚡ Elektrik")
    kb.button(text="❄️ Maishiy Texnika")
    kb.button(text="🏠 Universal Usta")
    kb.button(text="🔙 Bosh menyu")
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def premium_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Sotib olish (50,000 so'm)", callback_data="buy_premium")
    return kb.as_markup()

# ==========================================================
# 6. ASOSIY MANTIQ
# ==========================================================

@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    register_user(message.from_user)
    welcome = f"🏠 <b>Salom, {message.from_user.first_name}!</b>\n\nMen HomeFix Pro (v2.0) — Uyingizdagi Sun'iy Ong."
    if message.from_user.id == ADMIN_ID:
        welcome += "\n👑 <b>Xo'jayin, sizga hamma narsa bepul!</b>"
    await message.answer(welcome, reply_markup=main_menu_kb())

# --- PROFIL ---
@dp.message(F.text == "👤 Profilim")
async def my_profile(message: types.Message):
    user = get_user_data(message.from_user.id)
    status = "👑 ADMIN" if message.from_user.id == ADMIN_ID else ("🌟 PREMIUM" if user and user[3] else "Oddiy")
    await message.answer(f"👤 <b>Status:</b> {status}\n🆔 ID: {user[0]}", reply_markup=main_menu_kb())

# --- PREMIUM PANEL ---
@dp.message(F.text == "💎 Premium Panel")
async def premium_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 Siz Adminsiz, to'lov shart emas!")
    else:
        await message.answer("💎 <b>Premium narxi: 59,000 so'm/oy</b>\n\n✅ Smart Vision (Rasm)\n✅ Real Kalkulyator", reply_markup=premium_kb())

@dp.callback_query(F.data == "buy_premium")
async def buy_click(callback: types.CallbackQuery):
    await bot.send_invoice(callback.from_user.id, "HomeFix Premium", "Full Access", "premium_sub", PAYMENT_TOKEN, "uzs", [LabeledPrice(label="Obuna", amount=5000000)], start_parameter="premium-sub")
    await callback.answer()

@dp.pre_checkout_query()
async def checkout(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def success(message: types.Message):
    set_premium(message.from_user.id)
    await message.answer("🎉 Tabriklaymiz! Siz Premiumsiz!")

# --- USTA RO'YXATI ---
@dp.message(F.text == "👷‍♂️ Men Ustaman")
async def master_start(message: types.Message):
    await message.answer("Sohangizni tanlang:", reply_markup=master_reg_kb())

@dp.message(F.text.in_({"🚰 Santexnik", "⚡ Elektrik", "❄️ Maishiy Texnika", "🏠 Universal Usta"}))
async def master_save(message: types.Message):
    register_master_db(message.from_user.id, message.from_user.full_name, message.text)
    await message.answer("✅ Bazaga qo'shildingiz!", reply_markup=main_menu_kb())
    if message.from_user.id != ADMIN_ID:
        await bot.send_message(ADMIN_ID, f"🔔 YANGI USTA: {message.from_user.full_name} ({message.text})")

# --- QAYTISH ---
@dp.message(F.text == "🔙 Bosh menyu")
async def back(message: types.Message):
    await message.answer("Menyu:", reply_markup=main_menu_kb())

# ==========================================================
# 7. MUKAMMAL KALKULYATOR (AI + REAL DB)
# ==========================================================
@dp.message(F.text == "🧮 Material Hisoblash")
async def open_calc(message: types.Message):
    user = get_user_data(message.from_user.id)
    if message.from_user.id != ADMIN_ID and (not user or user[3] == 0):
        await message.answer("🔒 <b>Kalkulyator faqat PREMIUM a'zolar uchun!</b>", reply_markup=premium_kb())
        return
    await message.answer("🧮 <b>Kalkulyator 2.0</b>\nNimani hisoblaymiz?", reply_markup=calc_menu_kb())

@dp.message(F.text.in_({"🧱 Devor (G'isht/Oboy)", "🪵 Pol (Laminat/Kafel)", "🏠 Shif (Gips/Potolok)", "⚡ Elektr (Kabel/Rozetka)"}))
async def calc_category(message: types.Message):
    update_context(message.from_user.id, "system", f"CALC_MODE: {message.text}")
    await message.answer(f"✅ <b>{message.text}</b> tanlandi.\n\n📝 Endi menga o'lchamlarni yozing.\n<i>Masalan: 4x5 xona, yoki 30 kvadrat, yoki 50 metr kabel</i>", reply_markup=types.ReplyKeyboardRemove())

# ==========================================================
# 8. SUN'IY ONG (AGENT, VISION VA INTERNET)
# ==========================================================
def search_internet(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region="uz-uz", max_results=3))
            if not results: return "Internetdan topilmadi."
            return "\n".join([f"- {r['title']}: {r['body']}" for r in results])
    except: return "Qidiruv xatosi."

@dp.message(F.photo)
async def ai_vision(message: types.Message):
    user = get_user_data(message.from_user.id)
    if message.from_user.id != ADMIN_ID and (not user or user[3] == 0):
        await message.answer("🔒 Rasm tahlili faqat PREMIUM!", reply_markup=premium_kb())
        return

    wait = await message.answer("🧐 <b>Diagnostika ketmoqda...</b>")
    file_path = f"img_{message.from_user.id}.jpg"
    try:
        await bot.download_file((await bot.get_file(message.photo[-1].file_id)).file_path, file_path)
        base64_img = encode_image(file_path)
        
        sys_prompt = f"""
        Sen HomeFix Ekspertisan. Bugun {datetime.now().strftime('%Y-yil')}.
        Rasmga qarab: 1. Xavfni aniqla. 2. Modelni va nosozlikni top. 3. O'zbekiston narxlarida smeta tuz.
        """
        completion = client.chat.completions.create(model="meta-llama/llama-4-scout-17b-16e-instruct", messages=[
            {"role": "user", "content": [{"type": "text", "text": sys_prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}]}
        ])
        await wait.delete()
        await message.answer(f"🔧 <b>XULOSA:</b>\n\n{completion.choices[0].message.content}", reply_markup=main_menu_kb())
    except Exception as e:
        await wait.edit_text(f"Xatolik: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

@dp.message(F.text | F.voice)
async def ai_agent(message: types.Message):
    wait = await message.answer("🌐 <b>O'ylayapman...</b>")
    try:
        txt = message.text
        if message.voice:
            fpath = f"v_{message.from_user.id}.ogg"
            await bot.download_file((await bot.get_file(message.voice.file_id)).file_path, fpath)
            with open(fpath, "rb") as f: txt = client.audio.transcriptions.create(file=(fpath, f.read()), model="whisper-large-v3").text
            os.remove(fpath)
            await message.answer(f"🗣 <b>Siz:</b> {txt}")

        # MARKET DATA contextga qo'shiladi agar hisob-kitob bo'lsa
        context_str = str(list(user_context.get(message.from_user.id, [])))
        market_info = ""
        if "CALC_MODE" in context_str or "hisob" in txt.lower():
            market_info = f"\n⚠️ FOYDALANUVCHI UCHUN REAL NARXLAR JADVALI (Buni ishlat):\n{MARKET_DB}\n"

        # Qidiruv
        search_res = ""
        if any(w in txt.lower() for w in ["narx", "iphone", "samsung", "qancha", "yangi", "2025", "2026"]):
            search_res = search_internet(txt + " narxi uzbekistan 2026")

        sys_prompt = f"""
        Sen HomeFix AI (v2.0)san. Bugun sana: {datetime.now().strftime('%d-%m-%Y')}.
        
        MA'LUMOTLAR:
        1. Internet: {search_res}
        2. Bozor Bazasi: {market_info}

        VAZIFA:
        - Agar foydalanuvchi o'lcham yozsa (Kalkulyator rejimi), Bozor Bazasidagi narxlardan foydalanib aniq smeta tuz. 10% zapas qo'sh.
        - Agar texnika (iPhone 17 kabi) so'rasa, Internet ma'lumotiga tayan. Hozir 2026 yil, eski gapni gapirma.
        - Javob lo'nda va o'zbek tilida bo'lsin.
        """

        update_context(message.from_user.id, "user", txt)
        resp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": sys_prompt}] + list(user_context[message.from_user.id])).choices[0].message.content
        update_context(message.from_user.id, "assistant", resp)
        
        await wait.delete()
        await message.answer(resp, reply_markup=main_menu_kb())
    except Exception as e:
        await wait.delete()
        await message.answer(f"Xatolik: {e}", reply_markup=main_menu_kb())

@dp.message(F.text == "🛠 Muammo yechish")
async def ask_prob(message: types.Message):
    await message.answer("Eshitaman! Yozing, gapiring yoki rasm tashlang.")

# ==========================================================
# 9. START
# ==========================================================
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
