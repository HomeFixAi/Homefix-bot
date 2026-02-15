HomeFix AI Pro - Complete Bot
Professional home services AI assistant
"""

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

# =============================================================================
# CONFIGURATION
# =============================================================================

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    bot_token: "7978174707:AAFjHjK1tB9AsY1yloTS-9vmykiJ8BacZPs"
    admin_id:  1967786876 
    groq_api_key:  "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"
    payment_token: "371317599:TEST:1770638863894"
    database_url: str = "sqlite+aiosqlite:///homefix_pro.db"
    debug: bool = False
    log_level: str = "INFO"
    max_requests_per_minute: int = 20
    port: int = 8080
    
    PREMIUM_PRICE: int = 50000
    PREMIUM_AMOUNT: int = 5000000

settings = Settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE SETUP
# =============================================================================

Base = declarative_base()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# =============================================================================
# DATABASE MODELS
# =============================================================================

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)
    total_requests = Column(Integer, default=0)
    joined_date = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class Master(Base):
    __tablename__ = "masters"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    profession = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    city = Column(String(100), nullable=False)
    rating = Column(Float, default=5.0)
    total_jobs = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class Request(Base):
    __tablename__ = "requests"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    request_type = Column(String(50))
    request_text = Column(Text, nullable=True)
    ai_model = Column(String(50))
    response_text = Column(Text)
    response_time = Column(Float)
    created_at = Column(DateTime, server_default=func.now())

# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database initialized")
        
        # Add sample masters if empty
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Master))
            if not result.scalars().first():
                masters = [
                    Master(name="Ali Usta", profession="Santexnik", phone="+998901234567", city="Toshkent"),
                    Master(name="Vali Usta", profession="Elektrik", phone="+998939876543", city="Samarqand"),
                    Master(name="G'ani Usta", profession="Maishiy texnika", phone="+998971112233", city="Buxoro")
                ]
                session.add_all(masters)
                await session.commit()
                logger.info("✅ Sample masters added")
    except Exception as e:
        logger.error(f"❌ Database error: {e}")
        raise

# =============================================================================
# AI SERVICE
# =============================================================================

groq_client = Groq(api_key=settings.groq_api_key)
user_context = {}

def update_context(user_id: int, role: str, content: str):
    if user_id not in user_context:
        user_context[user_id] = deque(maxlen=10)
    user_context[user_id].append({"role": role, "content": content})

def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

async def ai_text_response(user_id: int, user_input: str) -> tuple[str, float]:
    system_prompt = """
Sen HomeFix Pro - professional usta va muhandissan. 
Vazifang: Foydalanuvchi muammosini hal qilish.

Qoidalar:
1. Faqat O'ZBEK tilida javob ber.
2. Javobing aniq, qisqa va foydali bo'lsin.
3. Agar muammo xavfli bo'lsa (gaz, tok), avval xavfsizlik haqida ogohlantir.
4. Javobni chiroyli formatda yoz.
"""
    
    try:
        update_context(user_id, "user", user_input)
        history = [{"role": "system", "content": system_prompt}] + list(user_context.get(user_id, []))
        
        start_time = time.time()
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history,
            temperature=0.7,
            max_tokens=1500
        )
        response_time = time.time() - start_time
        
        response = completion.choices[0].message.content
        update_context(user_id, "assistant", response)
        
        return response, response_time
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return f"❌ Xatolik yuz berdi: {str(e)}", 0.0

async def ai_vision_response(image_path: str) -> str:
    try:
        base64_image = encode_image(image_path)
        
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Bu rasmdagi texnik muammoni aniqla va O'ZBEK tilida bosqichma-bosqich yechim ber. Usta kabi gapir."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        }]
        
        completion = groq_client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )
        
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Vision AI Error: {e}")
        return f"❌ Rasm tahlilida xatolik: {str(e)}"

async def ai_voice_transcription(audio_path: str) -> str:
    try:
        with open(audio_path, "rb") as f:
            transcription = groq_client.audio.transcriptions.create(
                file=(audio_path, f.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        return transcription
    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        return ""

# =============================================================================
# KEYBOARDS
# =============================================================================

def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🛠 Muammo yechish")
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

# =============================================================================
# BOT HANDLERS
# =============================================================================

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                user_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name
            )
            session.add(user)
            await session.commit()
            logger.info(f"New user: {message.from_user.id}")
    
    await message.answer(
        f"🏠 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
        "Men <b>HomeFix Pro</b> — uyingizdagi har qanday texnik muammoni hal qiluvchi aqlli yordamchiman.\n\n"
        "👇 <i>Quyidagi bo'limlardan birini tanlang:</i>",
        reply_markup=main_menu_kb()
    )

@router.message(F.text == "👤 Profilim")
async def show_profile(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()
        
        if user:
            status = "💎 Premium" if user.is_premium else "🆓 Bepul"
            text = (
                f"📂 <b>Sizning Profilingiz:</b>\n\n"
                f"👤 Ism: {user.full_name}\n"
                f"🆔 ID: {user.user_id}\n"
                f"🌟 Status: <b>{status}</b>\n"
                f"📊 So'rovlar: {user.total_requests}\n"
                f"📅 Qo'shilgan: {user.joined_date.strftime('%d.%m.%Y')}"
            )
            await message.answer(text)

@router.message(F.text == "💎 Premium Panel")
async def show_premium(message: Message):
    text = (
        "💎 <b>HomeFix Premium</b>\n\n"
        "✅ Cheksiz AI so'rovlar\n"
        "✅ Rasm va Ovozli xabarlar tahlili\n"
        "✅ Eng kuchli AI model\n"
        "✅ Priority support\n"
        "✅ Reklamasiz\n\n"
        f"💰 <b>Narxi: {settings.PREMIUM_PRICE:,} so'm / oy</b>"
    )
    await message.answer(text, reply_markup=premium_kb())

@router.callback_query(F.data == "buy_premium")
async def process_premium_buy(callback: CallbackQuery):
    await callback.message.bot.send_invoice(
        chat_id=callback.from_user.id,
        title="HomeFix Premium",
        description="1 oylik to'liq foydalanish",
        payload="premium_subscription",
        provider_token=settings.payment_token,
        currency="uzs",
        prices=[LabeledPrice(label="Obuna", amount=settings.PREMIUM_AMOUNT)],
        start_parameter="premium-sub"
    )
    await callback.answer()

@router.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()
        
        if user:
            user.is_premium = True
            await session.commit()
    
    await message.answer("🎉 <b>Tabriklaymiz!</b> Siz endi Premium foydalanuvchisiz!")

@router.message(F.text == "📞 Usta kerak")
async def show_masters(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Master).where(Master.is_active == True))
        masters = result.scalars().all()
        
        if masters:
            text = "👷‍♂️ <b>Bizning eng yaxshi ustalarimiz:</b>\n\n"
            for m in masters:
                text += f"▪️ <b>{m.name}</b> ({m.profession}) - {m.city}\n"
                text += f"📞 Tel: {m.phone}\n"
                text += f"⭐ Reyting: {m.rating:.1f} ({m.total_jobs} ish)\n\n"
            await message.answer(text)
        else:
            await message.answer("❌ Hozircha ustalar mavjud emas.")

@router.message(F.text == "🛠 Muammo yechish")
async def ask_problem(message: Message):
    await message.answer(
        "Men tayyorman! 🎤 <b>Gapiring</b>, 📸 <b>Rasm tashlang</b> yoki 📝 <b>Yozing</b>.\n\n"
        "Muammo nimada?"
    )

@router.message(F.photo)
async def handle_photo(message: Message):
    wait_msg = await message.answer("🧐 <i>Rasm tahlil qilinmoqda...</i>")
    
    file_path = f"img_{message.from_user.id}.jpg"
    try:
        photo = await message.bot.get_file(message.photo[-1].file_id)
        await message.bot.download_file(photo.file_path, file_path)
        
        response = await ai_vision_response(file_path)
        
        async with AsyncSessionLocal() as session:
            request = Request(
                user_id=message.from_user.id,
                request_type="photo",
                ai_model="llama-vision",
                response_text=response,
                response_time=0.0
            )
            session.add(request)
            await session.commit()
        
        await wait_msg.edit_text(f"📸 <b>Tahlil natijalari:</b>\n\n{response}")
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await wait_msg.edit_text(f"❌ Xatolik: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@router.message(F.voice)
async def handle_voice(message: Message):
    wait_msg = await message.answer("🎤 <i>Ovoz tanilmoqda...</i>")
    
    file_path = f"voice_{message.from_user.id}.ogg"
    try:
        file = await message.bot.get_file(message.voice.file_id)
        await message.bot.download_file(file.file_path, file_path)
        
        transcription = await ai_voice_transcription(file_path)
        
        if transcription:
            await message.answer(f"🗣 <b>Siz aytdingiz:</b> {transcription}")
            response, response_time = await ai_text_response(message.from_user.id, transcription)
            
            async with AsyncSessionLocal() as session:
                request = Request(
                    user_id=message.from_user.id,
                    request_type="voice",
                    request_text=transcription,
                    ai_model="groq",
                    response_text=response,
                    response_time=response_time
                )
                session.add(request)
                await session.commit()
            
            await wait_msg.edit_text(response)
        else:
            await wait_msg.edit_text("❌ Ovozni tanib bo'lmadi.")
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await wait_msg.edit_text(f"❌ Xatolik: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@router.message(F.text)
async def handle_text(message: Message):
    if message.text in ["🛠 Muammo yechish", "👤 Profilim", "💎 Premium Panel", "📞 Usta kerak"]:
        return
    
    wait_msg = await message.answer("🤔 <i>O'ylayapman...</i>")
    
    try:
        response, response_time = await ai_text_response(message.from_user.id, message.text)
        
        async with AsyncSessionLocal() as session:
            request = Request(
                user_id=message.from_user.id,
                request_type="text",
                request_text=message.text,
                ai_model="groq",
                response_text=response,
                response_time=response_time
            )
            session.add(request)
            
            result = await session.execute(select(User).where(User.user_id == message.from_user.id))
            user = result.scalar_one_or_none()
            if user:
                user.total_requests += 1
            
            await session.commit()
        
        await wait_msg.edit_text(response)
    except Exception as e:
        logger.error(f"Text error: {e}")
        await wait_msg.edit_text(f"❌ Xatolik: {str(e)}")

# =============================================================================
# WEB SERVER (for hosting)
# =============================================================================

async def handle_web(request):
    return web.Response(text="🏠 HomeFix Pro is Running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', settings.port)
    await site.start()
    logger.info(f"🌐 Web server started on port {settings.port}")

# =============================================================================
# MAIN
# =============================================================================

async def main():
    logger.info("🚀 HomeFix Pro starting...")
    
    # Initialize bot
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    
    # Initialize database
    await init_db()
    
    # Start web server and bot
    await asyncio.gather(
        start_web_server(),
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
