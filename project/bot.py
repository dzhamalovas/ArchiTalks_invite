import os
import random
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

load_dotenv()

# --- Загрузка переменных окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
CHANNEL_ID = os.getenv("CHANNEL_ID")
EMAIL_DOMAINS = os.getenv("EMAIL_DOMAINS")
CODE_EXPIRE_MINUTES = os.getenv("CODE_EXPIRE_MINUTES")

# --- Проверка корректности переменных ---
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")
if not SMTP_SERVER or not SMTP_USER or not SMTP_PASS:
    raise ValueError("SMTP_SERVER, SMTP_USER или SMTP_PASS не заданы в .env")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID не задан в .env")
if not EMAIL_DOMAINS:
    raise ValueError("EMAIL_DOMAINS не задан в .env")
if not CODE_EXPIRE_MINUTES:
    CODE_EXPIRE_MINUTES = 10  # по умолчанию 10 минут

CHANNEL_ID = int(CHANNEL_ID)
EMAIL_DOMAINS = EMAIL_DOMAINS.split(",")
CODE_EXPIRE_MINUTES = int(CODE_EXPIRE_MINUTES)

# --- Инициализация бота ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Состояния пользователей ---
user_state = {}  # uid: {"email": str, "code": str, "expires_at": datetime, "verified": bool}

# --- Функция отправки кода по email ---
def send_email(to_addr: str, code: str):
    msg = MIMEText(
        f"Ваш код подтверждения для доступа в канал: {code}\n\n"
        "",
        "plain",
        "utf-8"
    )
    msg["Subject"] = "Код подтверждения входа"
    msg["From"] = SMTP_USER
    msg["To"] = to_addr

    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as smtp:
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)

# --- Генерация случайного кода ---
def generate_code() -> str:
    return str(random.randint(100000, 999999))

# --- Команда /start ---
@dp.message(Command("start"))
async def start(message: types.Message):
    uid = message.from_user.id
    user_state[uid] = {"email": "", "code": "", "expires_at": None, "verified": False}
    await message.answer(
        f"Добрый день! Для доступа в канал ArchiTalks введите вашу корпоративную почту.\n"
        f"Допустимые домены: {', '.join(EMAIL_DOMAINS)}"
    )

# --- Обработка всех сообщений ---
@dp.message()
async def handler(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        await message.answer("Начните с команды /start")
        return

    state = user_state[uid]

    # --- 1. Ожидаем email ---
    if state["email"] == "":
        email = message.text.strip().lower()
        if not any(email.endswith(f"@{domain}") for domain in EMAIL_DOMAINS):
            await message.answer(
                f"Можно использовать только корпоративные почты: {', '.join(EMAIL_DOMAINS)}"
            )
            return

        # Генерация кода
        code = generate_code()
        state["email"] = email
        state["code"] = code
        state["expires_at"] = datetime.now() + timedelta(minutes=CODE_EXPIRE_MINUTES)

        try:
            send_email(email, code)
        except Exception as ex:
            await message.answer(
                f"Ошибка отправки письма: {ex}\nДля получения доступа в канал напишите @Ollliaz."
            )
            state["email"] = ""
            state["code"] = ""
            state["expires_at"] = None
            return

        await message.answer(
            f"Код подтверждения отправлен на {email}. "
            f"Если письма нет в почте, проверьте папку спам.\n"
            f"Код действителен {CODE_EXPIRE_MINUTES} минут."
        )
        return

    # --- 2. Ожидаем код ---
    if not state["verified"]:
        if datetime.now() > state["expires_at"]:
            # Срок кода истёк
            state["code"] = ""
            state["expires_at"] = None
            state["email"] = ""
            await message.answer(
                "Срок действия кода истёк. Пожалуйста, введите email заново для получения нового кода."
            )
            return

        if message.text.strip() == state["code"]:
            state["verified"] = True
            try:
                # Создаём одноразовую ссылку на канал
                invite = await bot.create_chat_invite_link(
                    chat_id=CHANNEL_ID,
                    member_limit=1,
                    expire_date=None
                )
                await message.answer(
                    "Код подтверждён! Вот ваша персональная ссылка для входа в канал:"
                )
                await message.answer(invite.invite_link)
            except Exception as ex:
                await message.answer(
                    f"Ошибка при создании ссылки на канал: {ex}\n"
                    "Для получения доступа в канал напишите @Ollliaz."
                )
        else:
            await message.answer("Неверный код. Попробуйте снова.")
        return

    # --- 3. Пользователь уже верифицирован ---
    await message.answer("Вы уже прошли верификацию. Используйте ссылку, чтобы войти в канал.")

# --- Запуск бота ---
if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
