import asyncio
import logging
import os
import base64
import time
from collections import deque
from datetime import datetime
from typing import Optional

from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

from groq import Groq
from duckduckgo_search import DDGS  # Qaytarildi!

# =============================================================================
# 1. SOZLAMALAR VA REAL BOZOR BAZASI
# =============================================================================

class Settings(BaseSettings):
    bot_token: str = "7978174707:AAFjHjK1tB9AsY1yloTS-9vmykiJ8BacZPs"
    admin_id: int = 1967786876 
    groq_api_key: str = "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"
    payment_token: str = "371317599:TEST:1770638863894"
    database_url: str = "sqlite+aiosqlite:///homefix_pro.db"
    
    PREMIUM_PRICE: int = 50000
    PREMIUM_AMOUNT: int = 5000000
    port: int = 8080

settings = Settings()

# O'ZBEKISTON QURILISH MATERIALLARI NARXLARI (2026)
MARKET_DB = {
    "devor": {
        "oboy_oddiy": "Roloni (10m) 150,000 - 250,000 so'm",
        "emulsiya": "20kg chelak - 400,000 so'm",
        "gish_pishgan": "1 dona - 1,800 so'm"
    },
    "pol": {
        "laminat_32": "1 kv.m - 75,000 so'm",
        "laminat_33": "1 kv.m - 110,000 so'm",
        "kafel": "1 kv.m - 90,000 - 250,000 so'm"
    },
    "elektr": {
        "kabel_2x2_5": "1 metr - 8,500 so'm",
        "rozetka": "1 dona - 35,000 so'm"
    }
}

logging.basicConfig(level="INFO", format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# 2. DATABASE (SQLAlchemy)
# =============================================================================

Base = declarative_base()
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=False)
    is_premium = Column(Boolean, default=False)
    total_requests = Column(Integer, default=0)
    joined_date = Column(DateTime, server_default=func.now())

class Master(Base):
    __tablename__ = "masters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True) # Telegram ID
    name = Column(String(255), nullable=False)
    profession = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    rating = Column(Float, default=5.0)
    is_active = Column(Boolean, default=True)

class Request(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    request_type = Column(String(50))
    request_text = Column(Text, nullable=True)
    response_text = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Bazalar yaratildi")

# =============================================================================
# 3. AI MANTIQI (GROQ + DUCKDUCKGO + VISION)
# =============================================================================

groq_client = Groq(api_key=settings.groq_api_key)
user_context = {}

def update_context(user_id: int, role: str, content: str):
    if user_id not in user_context: user_context[user_id] = deque(maxlen=5)
    user_context[user_id].append({"role": role, "content": content})

def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f: return base64.b64encode(f.read()).decode('utf-8')

# INTERNET QIDIRUVI
def search_internet(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region="uz-uz", max_results=3))
            if not results: return ""
            return "\n".join([f"- {r['title']}: {r['body']}" for r in results])
    except: return ""

async def ai_text_response(user_id: int, user_input: str) -> str:
    # 1. Internetdan qidirish (agar kerak bo'lsa)
    search_res = ""
    if any(w in user_input.lower() for w in ["narx", "qancha", "iphone", "dollar", "yangilik", "2026"]):
        search_res = search_internet(user_input + " narxi 2026 uzbekistan")

    # 2. Tizim Prompti (Market DB + Sana)
    system_prompt = f"""
    Sen HomeFix Pro (v2.0)san. Bugungi sana: {datetime.now().strftime('%d-%m-%Y')}.
    
    QO'LINGDAGI MA'LUMOTLAR:
    1. Real Bozor Narxlari (Baza): {MARKET_DB}
    2. Internet Yangiliklari: {search_res}
    
    VAZIFA:
    - Odamlarga "Aka" kabi samimiy maslahat ber.
    - Narx so'rasa, bazadan yoki internetdan qarab ayt. 
    - Agar qurilish materiali (oboy, g'isht) so'rasa, o'lchamini so'ra va hisoblab ber.
    - Javob faqat O'ZBEK tilida bo'lsin.
    """
    
    try:
        update_context(user_id, "user", user_input)
        history = [{"role": "system", "content": system_prompt}] + list(user_context.get(user_id, []))
        
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history,
            temperature=0.7
        )
        response = completion.choices[0].message.content
        update_context(user_id, "assistant", response)
        return response
    except Exception as e:
        return f"Xatolik: {e}"

async def ai_vision_response(image_path: str) -> str:
    try:
        base64_img = encode_image(image_path)
        messages = [{
            "role": "user", 
            "content": [
                {"type": "text", "text": "Rasmga qarab muammoni, modelni va O'zbekiston bozoridagi narxini (2026) ayt."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
            ]
        }]
        completion = groq_client.chat.completions.create(model="llama-3.2-90b-vision-preview", messages=messages)
        return completion.choices[0].message.content
    except Exception as e: return f"Rasm xatosi: {e}"

# =============================================================================
# 4. BOT HANDLERS
# =============================================================================

router = Router()

def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🛠 Muammo yechish")
    kb.button(text="🧮 Material Hisoblash")
    kb.button(text="👷‍♂️ Men Ustaman")
    kb.button(text="👤 Profilim")
    kb.button(text="💎 Premium Panel")
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def calc_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🧱 Devor")
    kb.button(text="🪵 Pol")
    kb.button(text="⚡ Elektr")
    kb.button(text="🔙 Bosh menyu")
    kb.adjust(3, 1)
    return kb.as_markup(resize_keyboard=True)

def master_reg_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚰 Santexnik")
    kb.button(text="⚡ Elektrik")
    kb.button(text="🏠 Universal")
    kb.button(text="🔙 Bosh menyu")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)

@router.message(Command("start"))
async def cmd_start(message: Message):
    async with AsyncSessionLocal() as session:
        if not await session.scalar(select(User).where(User.user_id == message.from_user.id)):
            session.add(User(user_id=message.from_user.id, full_name=message.from_user.full_name))
            await session.commit()
    
    txt = f"🏠 <b>Salom, {message.from_user.first_name}!</b>\nMen HomeFix Pro — Uyingizdagi Sun'iy Ong."
    if message.from_user.id == settings.admin_id: txt += "\n👑 <b>Xo'jayin, sizga cheklov yo'q!</b>"
    await message.answer(txt, reply_markup=main_menu())

# --- KALKULYATOR ---
@router.message(F.text == "🧮 Material Hisoblash")
async def show_calc(message: Message):
    await message.answer("Nimani hisoblaymiz?", reply_markup=calc_menu())

@router.message(F.text.in_({"🧱 Devor", "🪵 Pol", "⚡ Elektr"}))
async def calc_logic(message: Message):
    update_context(message.from_user.id, "system", f"Foydalanuvchi {message.text} hisoblamoqchi.")
    await message.answer(f"✅ {message.text} tanlandi. O'lchamlarni yozing (masalan: 4x5 xona):", reply_markup=ReplyKeyboardBuilder().button(text="🔙 Bosh menyu").as_markup(resize_keyboard=True))

# --- USTA RO'YXATI ---
@router.message(F.text == "👷‍♂️ Men Ustaman")
async def master_reg(message: Message):
    await message.answer("Sohangizni tanlang:", reply_markup=master_reg_menu())

@router.message(F.text.in_({"🚰 Santexnik", "⚡ Elektrik", "🏠 Universal"}))
async def master_save(message: Message):
    async with AsyncSessionLocal() as session:
        session.add(Master(user_id=message.from_user.id, name=message.from_user.full_name, profession=message.text, phone="Noma'lum"))
        await session.commit()
    await message.answer("✅ Bazaga qo'shildingiz!", reply_markup=main_menu())

# --- PROFIL VA PREMIUM ---
@router.message(F.text == "👤 Profilim")
async def profile(message: Message):
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.user_id == message.from_user.id))
        status = "👑 ADMIN" if user.user_id == settings.admin_id else ("💎 Premium" if user.is_premium else "oddi")
        await message.answer(f"👤 <b>{user.full_name}</b>\nStatus: {status}\nSo'rovlar: {user.total_requests}")

@router.message(F.text == "💎 Premium Panel")
async def premium(message: Message):
    if message.from_user.id == settings.admin_id: return await message.answer("Sizga tekin!")
    await message.answer("💎 Premium narxi: 50,000 so'm", reply_markup=InlineKeyboardBuilder().button(text="Sotib olish", callback_data="buy").as_markup())

@router.callback_query(F.data == "buy")
async def buy(cb: CallbackQuery):
    await cb.message.bot.send_invoice(cb.from_user.id, "Premium", "1 oy", "payload", settings.payment_token, "uzs", [LabeledPrice(label="Obuna", amount=5000000)])

@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery): await q.answer(ok=True)

@router.message(F.successful_payment)
async def success_pay(msg: Message):
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.user_id == msg.from_user.id))
        user.is_premium = True
        await session.commit()
    await msg.answer("🎉 Premium olindi!")

# --- AI HANDLERS (TEXT, VOICE, PHOTO) ---
@router.message(F.photo)
async def handle_photo(message: Message):
    # Admin yoki Premium tekshiruvi
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.user_id == message.from_user.id))
        if message.from_user.id != settings.admin_id and not user.is_premium:
            return await message.answer("🔒 Rasm tahlili faqat Premium uchun!")

    wait = await message.answer("🧐 Tahlil qilinmoqda...")
    path = f"img_{message.from_user.id}.jpg"
    await message.bot.download(message.photo[-1], destination=path)
    resp = await ai_vision_response(path)
    os.remove(path)
    
    # Bazaga yozish
    async with AsyncSessionLocal() as session:
        session.add(Request(user_id=message.from_user.id, request_type="photo", response_text=resp))
        await session.commit()
        
    await wait.delete()
    await message.answer(resp, reply_markup=main_menu())

@router.message(F.text | F.voice)
async def handle_all(message: Message):
    if message.text in ["🔙 Bosh menyu", "🛠 Muammo yechish"]: return await message.answer("Menyuni tanlang", reply_markup=main_menu())

    wait = await message.answer("🌐 ...")
    text = message.text
    if message.voice:
        path = f"voice_{message.from_user.id}.ogg"
        await message.bot.download(message.voice, destination=path)
        with open(path, "rb") as f: text = groq_client.audio.transcriptions.create(file=(path, f.read()), model="whisper-large-v3").text
        os.remove(path)
        await message.answer(f"🗣 {text}")

    resp = await ai_text_response(message.from_user.id, text)
    
    async with AsyncSessionLocal() as session:
        session.add(Request(user_id=message.from_user.id, request_type="text", request_text=text, response_text=resp))
        user = await session.scalar(select(User).where(User.user_id == message.from_user.id))
        user.total_requests += 1
        await session.commit()

    await wait.delete()
    await message.answer(resp, reply_markup=main_menu())

# =============================================================================
# MAIN
# =============================================================================

async def handle_web(request): return web.Response(text="Running!")

async def main():
    await init_db()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    
    app = web.Application()
    app.router.add_get('/', handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', settings.port).start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
