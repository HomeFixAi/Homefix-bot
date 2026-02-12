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
from aiogram.types import FSInputFile, LabeledPrice, PreCheckoutQuery
from aiogram.client.default import DefaultBotProperties

# ==========================================================
# 1. SOZLAMALAR (ENG MUHIM QISM)
# ==========================================================
# BotFather bergan yangi tokenni shu yerga qo'ying:
BOT_TOKEN = "7978174707:AAFjHjK1tB9AsY1yloTS-9vmykiJ8BacZPs"

# Click yoki Payme tokeni (Test rejimi uchun):
PAYMENT_TOKEN = "371317599:TEST:1770638863894"

# Groq API kalitingiz:
GROQ_API_KEY = "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"

# O'zingizning Telegram ID raqamingiz (userinfobot orqali oling):
ADMIN_ID = 1967786876 # <--- SHUNI O'ZGARTIRING!!!

# Tizim sozlamalari
client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
user_context = {}  # Xotira uchun

# ==========================================================
# 2. MA'LUMOTLAR BAZASI (SQLite)
# ==========================================================
def init_db():
    """Bazani yaratish va boshlang'ich ma'lumotlarni yuklash"""
    conn = sqlite3.connect('homefix_pro.db')
    cursor = conn.cursor()
    
    # Foydalanuvchilar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, username TEXT, is_premium INTEGER DEFAULT 0)''')
    
    # Ustalar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS masters 
                      (id INTEGER PRIMARY KEY, name TEXT, profession TEXT, phone TEXT, city TEXT)''')
    
    # Agar ustalar bo'lmasa, namuna qo'shamiz
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
    """Foydalanuvchi bilan suhbat tarixini saqlash"""
    if user_id not in user_context:
        user_context[user_id] = deque(maxlen=5) # Oxirgi 5 ta gapni eslab qoladi
    user_context[user_id].append({"role": role, "content": content})

# ==========================================================
# 4. BOT HANDLERLARI (MANTIQ)
# ==========================================================

# --- START ---
@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    register_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"👋 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
        "Men <b>HomeFix AI</b> — uyingizdagi texnik muammolarni hal qilishda yordam beraman.\n"
        "📸 Rasm yuboring\n🎤 Gapiring\n📝 Yoki yozing!",
        reply_markup=main_menu()
    )

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        conn = sqlite3.connect('homefix_pro.db')
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        await message.answer(f"📊 <b>Admin Hisoboti:</b>\n\n👥 Jami foydalanuvchilar: {count} ta\n✅ Tizim holati: Barqaror")
    else:
        await message.answer("🔒 Siz admin emassiz.")

# --- USTA QIDIRISH ---
@dp.message(F.text == "📍 Yaqin usta")
async def find_master(message: types.Message):
    conn = sqlite3.connect('homefix_pro.db')
    masters = conn.execute("SELECT name, profession, phone, city FROM masters").fetchall()
    conn.close()
    
    text = "🛠 <b>Tavsiya etilgan ustalar:</b>\n\n"
    for m in masters:
        text += f"👤 <b>{m[0]}</b> ({m[1]})\n📍 {m[3]} | 📞 {m[2]}\n➖➖➖➖➖\n"
    
    await message.answer(text)

# --- PREMIUM SOTIB OLISH ---
@dp.message(F.text.contains("Premium"))
async def buy_premium(message: types.Message):
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="HomeFix Premium",
        description="AI cheksiz ishlashi uchun obuna",
        payload="premium_sub",
        provider_token=PAYMENT_TOKEN,
        currency="uzs",
        prices=[LabeledPrice(label="Premium Obuna", amount=5000000)], # 50,000 so'm
        start_parameter="premium-sub"
    )

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success_payment(message: types.Message):
    await message.answer("🎉 <b>To'lov qabul qilindi!</b>\nSiz endi Premium foydalanuvchisiz.")

# --- RASM TAHLILI (YAXSHILANGAN & XAVFSIZ) ---
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    wait = await message.answer("👀 <i>Rasm yuklanmoqda va tahlil qilinmoqda...</i>")
    file_path = f"img_{message.from_user.id}.jpg"

    try:
        # 1. Yuklab olish (Endi bu ham himoya ichida)
        photo = await bot.get_file(message.photo[-1].file_id)
        await bot.download_file(photo.file_path, file_path)
        
        # 2. AI tahlili
        base64_image = encode_image(file_path)
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Bu rasmdagi texnik muammoni ko'r va menga O'ZBEK tilida aniq yechim ber."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            temperature=0.7,
        )
        response = completion.choices[0].message.content
        await wait.edit_text(f"📸 <b>AI Xulosasi:</b>\n\n{response}")

    except TimeoutError:
        await wait.edit_text("❌ <b>Xatolik:</b> Internet juda sekin ishlayapti. Rasmni qaytadan yuboring.")
    except Exception as e:
        await wait.edit_text(f"❌ <b>Xatolik:</b> {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# --- OVOZLI XABAR (WHISPER) ---
@dp.message(F.voice)
async def handle_voice(message: types.Message):
    wait = await message.answer("🎧 <i>Eshitmoqdaman...</i>")
    
    file_path = f"voice_{message.from_user.id}.ogg"
    file = await bot.get_file(message.voice.file_id)
    await bot.download_file(file.file_path, file_path)
    
    try:
        # 1. Ovozni matnga aylantirish
        with open(file_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(file_path, f.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        
        # 2. Matnga javob olish
        update_context(message.from_user.id, "user", transcription)
        
        # Tizim xabari (System Prompt) - TILNI MAJBURLASH
        sys_msg = {"role": "system", "content": "Sen HomeFix AI ustasisan. Faqat va faqat O'ZBEK tilida, qisqa va lo'nda javob ber. Boshqa tillarni ishlatma."}
        history = [sys_msg] + list(user_context[message.from_user.id])
        
        ai_reply = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history
        ).choices[0].message.content
        
        update_context(message.from_user.id, "assistant", ai_reply)
        await wait.edit_text(f"🗣 <b>Siz:</b> {transcription}\n\n🤖 <b>Javob:</b> {ai_reply}")
        
    except Exception as e:
        await wait.edit_text(f"Xatolik: {e}")
...     finally:
...         if os.path.exists(file_path): os.remove(file_path)
... 
... # --- ODDIY CHAT (TEXT) ---
... @dp.message()
... async def chat_logic(message: types.Message):
...     if not message.text: return
...     wait = await message.answer("💬 <i>Yozmoqda...</i>")
...     
...     update_context(message.from_user.id, "user", message.text)
...     
...     try:
...         # Tilni majburlash uchun System Prompt
...         sys_msg = {"role": "system", "content": "Sen HomeFix AI professional ustasisan. Faqat O'ZBEK tilida javob ber. Rus yoki Ingliz tiliga o'tma."}
...         history = [sys_msg] + list(user_context[message.from_user.id])
...         
...         completion = client.chat.completions.create(
...             model="llama-3.3-70b-versatile",
...             messages=history
...         )
...         response = completion.choices[0].message.content
...         update_context(message.from_user.id, "assistant", response)
...         await wait.edit_text(response)
...     except Exception as e:
...         await wait.edit_text(f"Aloqa uzildi: {e}")
... 
... # ==========================================================
... # 5. ISHGA TUSHIRISH
... # ==========================================================
... async def main():
...     init_db()
...     logging.basicConfig(level=logging.INFO)
...     print("🚀 HomeFix AI Tizimi ishga tushdi (Versiya 2.0)...")
...     await dp.start_polling(bot)
... 
... if __name__ == "__main__":
...     asyncio.run(main())


