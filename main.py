from unittest.mock import call
import telebot
from telebot import types
import random
import time
from threading import Thread
from flask import Flask
import html
import json
import threading
from datetime import datetime, date
import os
from datetime import datetime, timedelta
import uuid
from groq import Groq
from bussines_bot import register_business_handlers

# ---------- BOT SETUP ----------
TOKEN = "8317148699:AAFZn4dZzKlBpivEKUYDbPcR4wL8iDgMMc8"
bot = telebot.TeleBot(TOKEN)
bot.delete_webhook()

# ---------- CONFIGURATION ----------
GROQ_API_KEY = "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"
groq_client = Groq(api_key=GROQ_API_KEY)

FREE_DAILY_QUOTA = 10
PREMIUM_DAYS = 30

DATA_FILE = "ai_users.json"
# Название канала для обязательной подписки (если нужно)
REQUIRED_CHANNEL = "@minigamesbottgk"  # или None

# ---------- AI MODES ----------
AI_MODES = {
    "chat": "Обычный дружелюбный помощник",
    "short": "Отвечай максимально кратко, 1–2 предложения",
    "long": "Отвечай подробно и развернуто",
    "code": "Ты опытный программист, пиши код и объясняй"
}

# Параметры тарифа
FREE_DAILY_QUOTA = 10   # бесплатный тариф: 10 запросов в день
PREMIUM_PRICE = 5       # произвольная метка; не производит оплату — логика "пометка"
PREMIUM_PERIOD_DAYS = 30

# Путь к файлу хранения данных
DATA_FILE = "bot_data.json"

_storage_lock = threading.Lock()

# Broadcast / system-wide notification settings (editable via /messagenot)
BROADCAST_SETTINGS = {
    "msg": "",
    "btn_text": "Открыть",
    "btn_type": "link",  # "link" or "callback"
    "btn_link": "https://t.me/minigamesbottgk"
}
try:
    dtmp = load_data()
    if dtmp.get("broadcast"):
        BROADCAST_SETTINGS.update(dtmp.get("broadcast"))
except Exception:
    pass
def _ensure_data_file(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"users": {}, "premium": {}, "ai_cache": {}, "stats": {}}, f, ensure_ascii=False, indent=2)

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"users": {}}, f)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_user_streak(user_id, display_name=None):
    d = load_data()
    users = d.setdefault("users", {})
    rec = users.setdefault(str(user_id), {})

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    last_day = rec.get("streak_last_day")
    cur = int(rec.get("streak_current", 0) or 0)

    if last_day == today:
        pass
    elif last_day == yesterday:
        cur = cur + 1 if cur > 0 else 1
    else:
        cur = 1

    rec["streak_current"] = cur
    rec["streak_last_day"] = today
    rec["streak_best"] = max(int(rec.get("streak_best", 0) or 0), cur)
    if display_name:
        rec["display_name"] = str(display_name)[:64]
    users[str(user_id)] = rec
    save_data(d)
    return cur

def get_user(uid):
    data = load_data()
    users = data["users"]
    today = date.today().isoformat()

    if str(uid) not in users or not isinstance(users[str(uid)], dict):
        users[str(uid)] = {}

    user = users[str(uid)]
    # ensure required fields exist (backward compatibility)
    if "count" not in user:
        user["count"] = 0
    if "date" not in user:
        user["date"] = today
    if "premium_until" not in user:
        user["premium_until"] = 0
    if "pending" not in user or not isinstance(user.get("pending"), dict):
        user["pending"] = {}

    if user.get("date") != today:
        user["date"] = today
        user["count"] = 0

    save_data(data)
    return user

def has_premium(uid):
    user = get_user(uid)
    return user["premium_until"] > time.time()

def can_use_ai(uid):
    user = get_user(uid)
    if has_premium(uid):
        return True, None
    if user["count"] < FREE_DAILY_QUOTA:
        return True, None
    return False, "⚠️ Лимит 10 запросов в день. Купите премиум для неограниченного доступа."

# Утилиты
def get_user_record(user_id):
    data = load_data()
    users = data.setdefault("users", {})
    return users.setdefault(str(user_id), {
        "daily_count": 0,
        "daily_date": date.today().isoformat(),
        "is_premium": False,
        "premium_until": None,
    })

def reset_daily_if_needed(user_id):
    rec = get_user_record(user_id)
    today = date.today().isoformat()
    if rec.get("daily_date") != today:
        rec["daily_date"] = today
        rec["daily_count"] = 0
        d = load_data()
        d["users"][str(user_id)] = rec
        save_data(d)

def inc_user_count(user_id):
    d = load_data()
    rec = d.setdefault("users", {}).setdefault(str(user_id), {"daily_count":0,"daily_date":date.today().isoformat(),"is_premium":False})
    # reset if needed
    if rec.get("daily_date") != date.today().isoformat():
        rec["daily_date"] = date.today().isoformat()
        rec["daily_count"] = 0
    rec["daily_count"] = rec.get("daily_count",0) + 1
    d["users"][str(user_id)] = rec
    save_data(d)
    return rec["daily_count"]

def pong_game_loop(gid, inline_id):
    while gid in games_pong:
        state = games_pong[gid]
        if not state["started"]:
            time.sleep(0.5)
            continue

        # движение мяча
        state["ball"][0] += state["ball"][2]
        state["ball"][1] += state["ball"][3]

        # отражение от стен
        if state["ball"][1] <= 0 or state["ball"][1] >= 6:
            state["ball"][3] *= -1

        try:
            bot.edit_message_text(
                render_pong_state(state),
                inline_message_id=inline_id,
                reply_markup=types.InlineKeyboardMarkup().row(
                    types.InlineKeyboardButton("⬅️", callback_data=f"pong_{gid}_L"),
                    types.InlineKeyboardButton("➡️", callback_data=f"pong_{gid}_R")
                )
            )
        except:
            break

        time.sleep(0.5)

def set_premium(user_id, until_timestamp):
    d = load_data()
    d.setdefault("premium", {})[str(user_id)] = {"until": until_timestamp}
    # also set users field
    user = d.setdefault("users", {}).setdefault(str(user_id), {})
    user["is_premium"] = True
    user["premium_until"] = until_timestamp
    save_data(d)

def clear_premium(user_id):
    d = load_data()
    if str(user_id) in d.get("premium", {}):
        del d["premium"][str(user_id)]
    user = d.setdefault("users", {}).setdefault(str(user_id), {})
    user["is_premium"] = False
    user["premium_until"] = None
    save_data(d)
    
def has_active_premium(user_id):
    d = load_data()
    user = d.get("users", {}).get(str(user_id), {})
    until = user.get("premium_until")
    if not until:
        return False
    try:
        return datetime.fromtimestamp(until) > datetime.utcnow()
    except:
        return False

def start_premium_watcher(bot_instance, check_interval=3600):
    """Фоновой поток: каждую check_interval сек проверяет премиум-аккаунты и шлет напоминания за 24h и при окончании."""
    def watcher():
        while True:
            try:
                data = load_data()
                pm = data.get("premium", {})
                now = datetime.utcnow()
                for uid_str, info in list(pm.items()):
                    try:
                        until_ts = info.get("until")
                        if not until_ts:
                            continue
                        until_dt = datetime.fromtimestamp(until_ts)
                        diff = until_dt - now
                        uid = int(uid_str)
                        # за 24 часа — напоминание
                        if 0 < diff.total_seconds() <= 24*3600 and not info.get("reminded_24h"):
                            try:
                                bot_instance.send_message(uid, f"⚠️ Ваша премиум-подписка истекает {until_dt.isoformat()} UTC. Продлите, чтобы не потерять доступ.")
                            except Exception as e:
                                print("notify 24h fail", e)
                            info["reminded_24h"] = True
                        # истекло — уведомляем и помечаем как неактивное
                        if diff.total_seconds() <= 0:
                            try:
                                bot_instance.send_message(uid, "⚠️ Ваша премиум-подписка окончена. Пока не продлите — премиум приостановлен.")
                            except Exception as e:
                                print("notify expired fail", e)
                            # удаляем/обнуляем
                            clear_premium(uid)
                            if str(uid) in pm:
                                del pm[str(uid)]
                    except Exception as e:
                        print("premium loop inner error", e)
                data["premium"] = pm
                save_data(data)
            except Exception as e:
                print("premium watcher error", e)
            time.sleep(check_interval)
    t = Thread(target=watcher, daemon=True)
    t.start()
    
def hide_keyboard(prefix):
    kb = types.InlineKeyboardMarkup()
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            row.append(
                types.InlineKeyboardButton(
                    "⬜",
                    callback_data=f"{prefix}_{i}"
                )
            )
        kb.row(*row)
    return kb

def user_quota_allows(user_id):
    reset_daily_if_needed(user_id)
    rec = get_user_record(user_id)

    if has_active_premium(user_id):
        return True, None

    if rec.get("daily_count", 0) < FREE_DAILY_QUOTA:
        return True, None

    return False, f"⚠️ Лимит бесплатных запросов достигнут ({FREE_DAILY_QUOTA}/день). Купите премиум."


# ------------------- SUBSCRIPTION HELPERS -------------------
def _channel_url():
    if not REQUIRED_CHANNEL:
        return None
    return f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"

def is_user_subscribed(user_id):
    """Return True if user is a member of REQUIRED_CHANNEL (or if no requirement set)."""
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        # statuses: 'creator','administrator','member','restricted','left','kicked'
        return member.status in ("creator", "administrator", "member", "restricted")
    except Exception:
        return False

def inline_subscription_prompt(query):
    """Answer an inline query with a subscribe prompt (used when user not in channel)."""
    url = _channel_url() or "https://t.me/"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📣 Подписаться", url=url))
    art = types.InlineQueryResultArticle(
        id="must_subscribe",
        title="⚠️ Вы не подписаны на канал!",
        description="Чтобы использовать этого бота — подпишитесь на его канал.",
        input_message_content=types.InputTextMessageContent(
            "⚠️ Для использования бота необходимо подписаться на официальный канал. Нажмите кнопку ниже, затем повторите действие."
        ),
        reply_markup=kb
    )
    try:
        bot.answer_inline_query(query.id, [art], cache_time=1, is_personal=True)
    except Exception:
        pass

# Register Telegram Business (Premium Chat Bots) handlers early.
register_business_handlers(
    bot,
    required_channel=REQUIRED_CHANNEL,
    is_user_subscribed=is_user_subscribed,
)


def safe_edit_message(call, text, reply_markup=None, parse_mode=None):
    """Edit message whether it's inline (inline_message_id) or normal (chat_id/message_id)."""
    try:
        if getattr(call, "inline_message_id", None):
            bot.edit_message_text(text, inline_message_id=call.inline_message_id, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            # fallback to chat message
            if call.message:
                bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=reply_markup, parse_mode=parse_mode)
            else:
                # last resort: send new message to user
                bot.send_message(call.from_user.id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        msg = str(e)
        # ignore non-fatal 'message is not modified' errors coming from Telegram API
        if "message is not modified" in msg or "specified new message content and reply markup are exactly the same" in msg:
            return
        print("safe_edit_message error:", e)

# ------------------- QUESTIONS -------------------
questions = [
    {
        "question": "Что такое Python?",
        "options": ["Язык программирования", "Программа", "Страна", "Ничего не подходит"],
        "answer": "Язык программирования"
    },
    {
        "question": "Что такое Roblox?",
        "options": ["Язык программирования", "Приложение", "Игра", "Платформа"],
        "answer": "Платформа"
    },
    {
        "question": "Какой тип данных используется для хранения текста в Python?",
        "options": ["int", "str", "float", "bool"],
        "answer": "str"
    },
    {
        "question": "Столица Франции?",
        "options": ["Париж", "Берлин", "Мадрид", "Рим"],
        "answer": "Париж"
    },
    {
        "question": "Сколько будет 2 + 2?",
        "options": ["3", "4", "5", "22"],
        "answer": "5"
    },
    {
        "question": "Какой океан самый большой?",
        "options": ["Тихий", "Атлантический", "Индийский", "Северный Ледовитый"],
        "answer": "Тихий"
    }
]

inline_ttt_games = {}
inline_guess_games = {}
inline_rps_games = {}
inline_snake_games = {}
inline_coin_games = {}
inline_slot_games = {}

user_sys_settings = {}      # uid -> {msg, btn, title, gui}
system_notify_wait = {}     # uid -> "field"
telos_input_wait = {}       # uid -> {"action": "..."}
millionaire_games = {}   # short_id -> {"question":..., "attempts":int}
user_show_easter_egg = {}  # uid -> bool (для управления отображением пасхалки)

games_flappy = {}   # gid -> {"bird_y":int,"pipes":[(x,gap)],"score":int}
games_2048 = {}     # gid -> {"board": [[int]]}
games_pong = {}     # gid -> {"players":[id_or_None,id_or_None],"paddles":[y1,y2],"ball":[x,y,dx,dy],"started":bool}
user_ai_mode = {}  # user_id -> mode
rps_games = {}  # game_id -> {"uid": int}
hide_games = {}
hangman_games = {}  # gid -> {"word": str, "guessed": set(), "wrong": set(), "attempts": int}
mafia_games = {}    # gid -> mafia game state
games_tetris = {}   # gid -> {"w","h","board","piece","score","over"}

# Словарь слов для Виселицы с подсказками
HANGMAN_WORDS = {
    "пайтон": "Язык программирования с именем змеи",
    "программист": "Человек, который пишет код",
    "компьютер": "Электронная вычислительная машина",
    "интернет": "Глобальная сеть связи",
    "телефон": "Устройство для связи",
    "клавиатура": "Устройство для ввода текста",
    "монитор": "Экран для вывода информации",
    "сервер": "Компьютер, предоставляющий услуги",
    "приложение": "Программное обеспечение",
    "функция": "Блок кода, который выполняет задачу",
    "переменная": "Контейнер для хранения данных",
    "алгоритм": "Последовательность шагов для решения задачи",
    "данные": "Информация для обработки",
    "байт": "Единица измерения информации",
    "пиксель": "Точка на экране",
    "игра": "Развлечение с правилами",
    "музыка": "Искусство звуков",
    "книга": "Сшитые листы с текстом",
    "машина": "Транспортное средство",
    "птица": "Животное, которое летает",
    "цветок": "Растение с яркими лепестками",
    "звезда": "Небесное тело на ночном небе",
    "луна": "Спутник земли",
    "солнце": "Звезда нашей системы",
    "океан": "Очень большой водный массив",
    "гора": "Высокое возвышение земли",
    "река": "Поток воды на земле",
    "лес": "Большое скопление деревьев",
    "город": "Населённый пункт с домами",
    "дорога": "Путь для передвижения",
    "школа": "Учебное заведение для детей",
    "учитель": "Человек, который учит",
    "ученик": "Человек, который учится",
    "друг": "Близкий человек",
    "семья": "Группа близких людей",
    "мама": "Женщина, которая родила вас",
    "папа": "Мужчина, который родил вас",
    "сестра": "Женская сестра",
    "брат": "Мужская сестра",
    "дом": "Здание для проживания",
    "окно": "Отверстие в стене для света",
    "дверь": "Вход в комнату или здание",
    "стол": "Мебель для работы или еды",
    "стул": "Мебель для сидения",
    "кровать": "Мебель для сна",
    "хлеб": "Продукт из муки и воды",
    "молоко": "Жидкость от коров",
    "масло": "Жидкий продукт для готовки",
    "сыр": "Молочный продукт",
    "яйцо": "Продукт от птиц",
    "рыба": "Животное, которое живёт в воде",
    "мясо": "Животный продукт питания",
    "салат": "Блюдо из овощей",
    "суп": "Жидкое блюдо",
    "радость": "Положительное чувство",
    "грусть": "Отрицательное чувство",
    "любовь": "Сильное положительное чувство",
    "надежда": "Вера в будущее",
    "вера": "Уверенность в чём-то",
    "сила": "Способность что-то делать",
    "ум": "Способность думать",
    "душа": "Внутренний мир человека",
    "сердце": "Орган, который качает кровь",
    "разум": "Способность к логике",
    "воля": "Определённость в действиях",
    "честь": "Репутация и достоинство",
    "долг": "Обязательство перед другими",
    "подвиг": "Героический поступок",
    "война": "Вооружённый конфликт",
    "мир": "Отсутствие войны",
    "победа": "Успех в борьбе",
    "поражение": "Неудача в борьбе",
    "истина": "То, что соответствует реальности",
    "ложь": "То, что не соответствует реальности",
    "справедливость": "Честное обращение",
    "несправедливость": "Нечестное обращение"
}

# Игры на двоих
word_games = {}  # gid -> {"word": str, "player1": id, "player2": id, "scores": {id: score}}
emoji_games = {}  # gid -> {"word": str, "p1": id, "p2": id, "emoji_desc": str, "scores": {id: score}}
quiz_games = {}  # gid -> {"question": str, "answer": str, "p1": id, "p2": id, "p1_answered": bool, "p2_answered": bool}
combo_games = {}  # gid -> {"p1": id, "p2": id, "p1_choice": str, "p2_choice": str, "round": int, "scores": {}}

# Слова для игры "Слова"
WORD_LIST = [
    "абрикос", "авокадо", "апельсин", "арбуз", "баклажан", "батон", "белок", "берёза",
    "билет", "блюдо", "борода", "ботинок", "будка", "булка", "булочка", "буква", "бульон",
    "вагон", "ванна", "ведро", "век", "велосипед", "весёлый", "веселье", "весна", "ветер",
    "ветка", "видео", "вилка", "виноград", "виолончель", "висок", "вода", "водитель", "воланчик",
    "волк", "волос", "волшебник", "волшебство", "вольтметр", "ворона", "вороны", "воротник", "ворошилка",
    "воспитание", "восток", "восьмой", "вот", "вохра", "впадина", "впечатление", "вперёд", "вперёди",
    "вперемешку", "вперемешку", "впереди", "вплотную", "вполголоса", "вполне", "вполовину", "впопыхах",
    "впорядке", "вправду", "вправо", "впредь", "впроголодь", "впрок", "вправо", "вскипание", "вскипать",
    "вскладчину", "вскользь", "вскрик", "вскрыть", "вскрытие", "вскрывать", "вскрывает", "вскупорить",
    "вскучу", "вслед", "вслед", "вследствие", "вслепую", "вслух", "всмятку", "всосать", "всполох",
    "всполошить", "всю", "всюду", "вта", "втайне", "втаптывать", "втаскивать", "втаскивать", "втачивать",
    "втачка", "втачку", "вте", "втё", "втеснение", "втеснить", "втеснять", "втёртый", "втёртый"
]

# Вопросы для викторины
QUIZ_QUESTIONS = [
    {"q": "Сколько планет в солнечной системе?", "a": "8"},
    {"q": "Какой язык программирования самый популярный?", "a": "пайтон"},
    {"q": "Столица России?", "a": "москва"},
    {"q": "Кто написал 'Войну и мир'?", "a": "толстой"},
    {"q": "Какой элемент имеет символ 'O'?", "a": "кислород"},
    {"q": "Сколько континентов на Земле?", "a": "7"},
    {"q": "Столица Украины?", "a": "киев"},
    {"q": "Кто изобрёл телефон?", "a": "грейм белл"},
    {"q": "Какое самое глубокое место в мировом океане?", "a": "марианская впадина"},
    {"q": "Сколько строк в каноне Уголовного кодекса РФ?", "a": "360"},
    {"q": "Какой элемент имеет символ 'Au'?", "a": "золото"},
    {"q": "Сколько струн на скрипке?", "a": "4"},
    {"q": "В каком году началась Вторая мировая война?", "a": "1939"},
    {"q": "Что изобрёл Томас Эдисон?", "a": "лампочка"},
    {"q": "Сколько букв в слове 'Телеграм'?", "a": "7"},
]

# ------------------- HELPERS -------------------
def short_id():
    return str(int(time.time()*1000))

# ------------------- KEYBOARDS -------------------
def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✖️ Крестики-нолики", "💰 Миллионер")
    kb.add("💬 Режим ИИ", "🐣 Пасхалка")
    kb.add("🪙 Орёл или решка", "🖥 TELOS v1.0")
    kb.add("🔢 Угадай число", "✂ Камень-ножницы-бумага")
    kb.add("🐍 Змейка", "🎰 Казино")
    kb.add("🐦 Flappy Bird", "🔢 2048")
    kb.add("🏓 Пинг-понг", "🕵️‍♀️ Прятки")
    kb.add("🔤 Виселица", "🔤 Викторина")
    kb.add("⚡ Комбо-битва", "🔔 Ваше уведомление")
    kb.add("🎭 Мафия", "🧱 Тетрис")
    kb.add("🚀 Поддержать автора")
    return kb

def snake_controls():
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("⬆️", callback_data="snake_up"))
    kb.row(types.InlineKeyboardButton("⬅️", callback_data="snake_left"),
           types.InlineKeyboardButton("➡️", callback_data="snake_right"))
    kb.row(types.InlineKeyboardButton("⬇️", callback_data="snake_down"))
    return kb

def telos_main_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📁 Файлы", callback_data="os_files"),
           types.InlineKeyboardButton("📝 Заметки", callback_data="os_notes"))
    kb.add(types.InlineKeyboardButton("🎮 Игры", callback_data="os_games"),
           types.InlineKeyboardButton("💬 Терминал", callback_data="os_terminal"))
    kb.add(types.InlineKeyboardButton("⚙️ Настройки", callback_data="os_settings"))
    kb.add(types.InlineKeyboardButton("⏻ Выключить", callback_data="os_shutdown"))
    return kb

def _telos_default_state():
    return {
        "booted": True,
        "settings": {"os_name": "TELOS", "theme": "classic"},
        "files": [{"name": "readme.txt", "content": "Добро пожаловать в TELOS! Эта система разработана для демонстрации возможностей бота. Вы можете создавать свои файлы и заметки, а также играть в мини-игры. Наслаждайтесь! :)"}],
        "notes": [],
        "terminal_history": [],
        "mini_games": {"guess_target": None},
        "created_at": int(time.time()),
    }

def _telos_get_state(user_id):
    data = load_data()
    users = data.setdefault("users", {})
    user = users.setdefault(str(user_id), {})
    state = user.get("telos")
    if not isinstance(state, dict):
        state = _telos_default_state()
    state.setdefault("booted", True)
    state.setdefault("settings", {})
    state["settings"].setdefault("os_name", "TELOS")
    state["settings"].setdefault("theme", "classic")
    state.setdefault("files", [{"name": "readme.txt", "content": "Добро пожаловать в TELOS"}])
    state.setdefault("notes", [])
    state.setdefault("terminal_history", [])
    state.setdefault("mini_games", {"guess_target": None})
    state.setdefault("created_at", int(time.time()))
    user["telos"] = state
    users[str(user_id)] = user
    save_data(data)
    return state

def _telos_save_state(user_id, state):
    data = load_data()
    users = data.setdefault("users", {})
    user = users.setdefault(str(user_id), {})
    user["telos"] = state
    users[str(user_id)] = user
    save_data(data)

def _telos_home_text(user_id):
    st = _telos_get_state(user_id)
    return (
        f"🖥 *{st['settings'].get('os_name', 'TELOS')} v1.1*\n"
        f"👤 ID пользователя: `{user_id}`\n\n"
        f"📁 Файлов: {len(st.get('files', []))}\n"
        f"📝 Заметок: {len(st.get('notes', []))}\n"
        f"🎨 Тема: {st['settings'].get('theme', 'classic')}\n\n"
        "Выбирайте приложение:"
    )

def _telos_files_kb(st):
    kb = types.InlineKeyboardMarkup()
    for i, fobj in enumerate(st.get("files", [])[:6]):
        kb.add(types.InlineKeyboardButton(f"📄 {str(fobj.get('name', 'file.txt'))[:24]}", callback_data=f"os_file_{i}"))
    kb.row(
        types.InlineKeyboardButton("➕ Добавить", callback_data="os_files_new"),
        types.InlineKeyboardButton("🧹 Очистить", callback_data="os_files_clear"),
    )
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="os_back"))
    return kb

def _telos_notes_kb(st):
    kb = types.InlineKeyboardMarkup()
    for i, note in enumerate(st.get("notes", [])[:6]):
        kb.add(types.InlineKeyboardButton(f"🗒 {str(note)[:24]}", callback_data=f"os_note_{i}"))
    kb.row(
        types.InlineKeyboardButton("➕ Добавить", callback_data="os_notes_add"),
        types.InlineKeyboardButton("🧹 Очистить", callback_data="os_notes_clear"),
    )
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="os_back"))
    return kb

def _telos_terminal_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("❓ Помощь", callback_data="os_term_help"),
        types.InlineKeyboardButton("🕒 Дата", callback_data="os_term_date"),
        types.InlineKeyboardButton("⏱ Аптайм", callback_data="os_term_uptime"),
    )
    kb.row(
        types.InlineKeyboardButton("📁 Файлы", callback_data="os_term_ls"),
        types.InlineKeyboardButton("🧹 Очистить", callback_data="os_term_clear"),
        types.InlineKeyboardButton("⌨️ Ввести", callback_data="os_term_input"),
    )
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="os_back"))
    return kb

def _telos_settings_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✏️ Имя ОС", callback_data="os_set_name"),
        types.InlineKeyboardButton("🎨 Тема", callback_data="os_set_theme"),
    )
    kb.row(
        types.InlineKeyboardButton("♻️ Сброс", callback_data="os_set_reset"),
        types.InlineKeyboardButton("⬅️ Назад", callback_data="os_back"),
    )
    return kb

def _telos_games_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🪙 Монетка", callback_data="os_game_coin"),
        types.InlineKeyboardButton("🎰 Слот", callback_data="os_game_slot"),
    )
    kb.row(
        types.InlineKeyboardButton("✂ КНБ", callback_data="os_game_rps"),
        types.InlineKeyboardButton("🔢 Угадай число", callback_data="os_game_guess"),
    )
    kb.add(types.InlineKeyboardButton("🎲 Кубик", callback_data="os_game_dice"))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="os_back"))
    return kb

def _telos_rps_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🪨", callback_data="os_game_rps_rock"),
        types.InlineKeyboardButton("📄", callback_data="os_game_rps_paper"),
        types.InlineKeyboardButton("✂️", callback_data="os_game_rps_scissors"),
    )
    kb.add(types.InlineKeyboardButton("⬅️ Назад к играм", callback_data="os_games"))
    return kb

def _telos_guess_kb():
    kb = types.InlineKeyboardMarkup()
    row = []
    for i in range(1, 11):
        row.append(types.InlineKeyboardButton(str(i), callback_data=f"os_game_guess_pick_{i}"))
        if i % 5 == 0:
            kb.row(*row)
            row = []
    kb.add(types.InlineKeyboardButton("⬅️ Назад к играм", callback_data="os_games"))
    return kb

def _telos_run_command(st, cmd):
    cmd = (cmd or "").strip().lower()
    alias = {
        "помощь": "help",
        "дата": "date",
        "аптайм": "uptime",
        "файлы": "ls",
        "очистить": "clear",
        "ктоя": "whoami",
        "заметки": "notes",
    }
    cmd = alias.get(cmd, cmd)
    if cmd == "help":
        return "Команды: help/помощь, date/дата, uptime/аптайм, ls/файлы, notes/заметки, whoami/ктоя, clear/очистить"
    if cmd == "date":
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if cmd == "uptime":
        return f"{max(0, int(time.time()) - int(st.get('created_at', int(time.time()))))} сек."
    if cmd == "ls":
        files = [x.get("name", "file.txt") for x in st.get("files", [])]
        return "\n".join(files) if files else "(пусто)"
    if cmd == "notes":
        notes = st.get("notes", [])
        return "\n".join([f"{i+1}. {str(n)[:60]}" for i, n in enumerate(notes[:8])]) if notes else "(нет заметок)"
    if cmd == "whoami":
        return "пользователь"
    if cmd == "clear":
        st["terminal_history"] = []
        return "История очищена."
    return "Команда не найдена. Введите help."

def eng_keyboard():
    kb = types.InlineKeyboardMarkup()
    rows = [
        ['Q','W','E','R','T','Y','U','I','O','P'],
        ['A','S','D','F','G','H','J','K','L'],
        ['Z','X','C','V','B','N','M']
    ]
    for row in rows:
        kb.add(*[types.InlineKeyboardButton(k, callback_data=f"key_{k}") for k in row])
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="os_back"))
    return kb

def ask_ai(prompt: str, user_id: int) -> str:
    try:
        if not prompt.strip():
            return "⚠️ Напиши вопрос текстом"

        mode = user_ai_mode.get(user_id, "chat")
        system_prompt = AI_MODES.get(mode, AI_MODES["chat"])

        chat = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt[:2000]}
            ],
            temperature=0.7,
            max_tokens=900
        )

        return chat.choices[0].message.content

    except Exception as e:
        print("AI ERROR:", repr(e))
        return "❌ Ошибка при получении ответа"

# ------------------- TTT (улучшённый модуль) -------------------
def _user_display_name_from_id(uid):
    try:
        u = bot.get_chat(uid)  # обычно работает для пользователей
        name = u.username or (u.first_name or f"Player_{uid}")
        return name
    except Exception:
        return f"Player_{uid}"

def ttt_render_header(game):
    p1_id, p2_id = game["players"][0], game["players"][1]
    p1_name = game["names"].get(p1_id, _user_display_name_from_id(p1_id))
    p2_name = game["names"].get(p2_id, _user_display_name_from_id(p2_id))
    score1 = game["scores"].get(p1_id, 0)
    score2 = game["scores"].get(p2_id, 0)
    line1 = f"❌ {p1_name} — {score1}"
    line2 = f"⭕ {p2_name} — {score2}"
    turn_symbol = "❌" if game["turn"] == p1_id else "⭕"
    return f"{line1}\n{line2}\n\nХодит: {turn_symbol}\n\n"

def emoji(move):
    return {"rock": "🪨", "paper": "📄", "scissors": "✂️"}[move]

def rps_result(a, b):
    if a == b:
        return "Ничья"
    wins = {
        "rock": "scissors",
        "scissors": "paper",
        "paper": "rock"
    }
    return "Победа!" if wins[a] == b else "Поражение"

def ttt_render_board(board):
    # board - list of 9 entries: " ", "❌", "⭕"
    lines = []
    for r in range(3):
        row = []
        for c in range(3):
            v = board[r*3 + c]
            row.append(v if v.strip() else "⬜️")
        lines.append(" ".join(row))
    return "\n".join(lines)

def ttt_build_keyboard(gid, board):
    kb = types.InlineKeyboardMarkup()
    symbols_map = {" ": "⬜️", "❌": "❌", "⭕": "⭕️"}
    for r in range(3):
        row = []
        for c in range(3):
            idx = r*3 + c
            label = symbols_map.get(board[idx], "⬜️")
            row.append(types.InlineKeyboardButton(label, callback_data=f"ttt_move_{gid}_{idx}"))
        kb.row(*row)
    # add restart button
    kb.row(types.InlineKeyboardButton("🔁 Сыграть ещё", callback_data=f"ttt_restart_{gid}"))
    return kb

def mafia_role_counts(n_players):
    mafia_cnt = 1 if n_players < 7 else 2
    doctor_cnt = 1 if n_players >= 5 else 0
    detective_cnt = 1 if n_players >= 6 else 0
    civ_cnt = n_players - mafia_cnt - doctor_cnt - detective_cnt
    return mafia_cnt, doctor_cnt, detective_cnt, civ_cnt

def mafia_assign_roles(players):
    p = players[:]
    random.shuffle(p)
    mafia_cnt, doctor_cnt, detective_cnt, _ = mafia_role_counts(len(players))
    roles = {}
    idx = 0
    for _ in range(mafia_cnt):
        roles[p[idx]] = "mafia"
        idx += 1
    for _ in range(doctor_cnt):
        roles[p[idx]] = "doctor"
        idx += 1
    for _ in range(detective_cnt):
        roles[p[idx]] = "detective"
        idx += 1
    while idx < len(p):
        roles[p[idx]] = "citizen"
        idx += 1
    return roles

def mafia_alive_mafia_count(game):
    return sum(1 for uid in game["alive"] if game["roles"].get(uid) == "mafia")

def mafia_alive_citizen_count(game):
    return sum(1 for uid in game["alive"] if game["roles"].get(uid) != "mafia")

def mafia_check_winner(game):
    m = mafia_alive_mafia_count(game)
    c = mafia_alive_citizen_count(game)
    if m <= 0:
        return "citizens"
    if m >= c:
        return "mafia"
    return None

def mafia_render_text(game):
    phase_title = {
        "lobby": "🎭 Мафия - Лобби",
        "night": "🌙 Мафия - Ночь",
        "day": "☀️ Мафия - День",
        "ended": "🏁 Мафия - Конец игры",
    }.get(game.get("phase"), "🎭 Мафия")
    text = f"{phase_title}\n\n"
    text += f"Раунд: {game.get('round', 1)}\n"
    text += f"Игроки: {len(game.get('players', []))} (живых: {len(game.get('alive', []))})\n\n"
    text += "Живые игроки:\n"
    for uid in game.get("alive", []):
        text += f"- {game['names'].get(uid, 'Игрок')}\n"
    if game.get("last_event"):
        text += f"\n{game['last_event']}"
    if game.get("phase") == "lobby":
        text += "\n\nНужно 4-10 игроков. Создатель нажимает «Старт»."
    elif game.get("phase") == "night":
        text += "\n\nНочные роли делают действия. Нажмите «Моя роль», чтобы посмотреть роль."
    elif game.get("phase") == "day":
        text += "\n\nДневное голосование: выберите подозреваемого."
    return text

def mafia_build_lobby_kb(gid):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➕ Присоединиться", callback_data=f"mafia_join_{gid}"))
    kb.add(types.InlineKeyboardButton("▶️ Старт", callback_data=f"mafia_start_{gid}"))
    kb.add(types.InlineKeyboardButton("🎭 Моя роль", callback_data=f"mafia_role_{gid}"))
    return kb

def mafia_build_night_kb(gid, game):
    kb = types.InlineKeyboardMarkup()
    for uid in game.get("alive", []):
        if game["roles"].get(uid) != "mafia":
            kb.add(types.InlineKeyboardButton(f"🔪 Убить: {game['names'].get(uid,'Игрок')}", callback_data=f"mafia_nkill_{gid}_{uid}"))
    for uid in game.get("alive", []):
        kb.add(types.InlineKeyboardButton(f"💊 Лечить: {game['names'].get(uid,'Игрок')}", callback_data=f"mafia_heal_{gid}_{uid}"))
    for uid in game.get("alive", []):
        kb.add(types.InlineKeyboardButton(f"🕵️ Проверить: {game['names'].get(uid,'Игрок')}", callback_data=f"mafia_check_{gid}_{uid}"))
    kb.add(types.InlineKeyboardButton("🎭 Моя роль", callback_data=f"mafia_role_{gid}"))
    return kb

def mafia_build_day_kb(gid, game):
    kb = types.InlineKeyboardMarkup()
    for uid in game.get("alive", []):
        kb.add(types.InlineKeyboardButton(f"🗳 Голос: {game['names'].get(uid,'Игрок')}", callback_data=f"mafia_vote_{gid}_{uid}"))
    kb.add(types.InlineKeyboardButton("🎭 Моя роль", callback_data=f"mafia_role_{gid}"))
    return kb

def mafia_resolve_night(game):
    target = game["night"].get("kill")
    healed = game["night"].get("heal")
    killed_uid = None
    if target and target in game["alive"] and target != healed:
        game["alive"].remove(target)
        killed_uid = target
        game["last_event"] = f"🌙 Ночью убит: {game['names'].get(target,'Игрок')}"
    else:
        game["last_event"] = "🌙 Ночью никто не погиб."
    game["phase"] = "day"
    game["votes"] = {}
    game["night"] = {"kill": None, "heal": None, "check": None}
    return killed_uid

def mafia_resolve_day(game):
    tally = {}
    for _, target in game.get("votes", {}).items():
        tally[target] = tally.get(target, 0) + 1
    if not tally:
        game["last_event"] = "☀️ Голосов нет. Никто не изгнан."
    else:
        max_votes = max(tally.values())
        top = [uid for uid, v in tally.items() if v == max_votes]
        if len(top) != 1:
            game["last_event"] = "☀️ Ничья в голосовании. Никто не изгнан."
        else:
            out_uid = top[0]
            if out_uid in game["alive"]:
                game["alive"].remove(out_uid)
            role = game["roles"].get(out_uid, "citizen")
            role_ru = {"mafia": "мафия", "doctor": "доктор", "detective": "детектив", "citizen": "мирный"}[role]
            game["last_event"] = f"☀️ Изгнан: {game['names'].get(out_uid,'Игрок')} ({role_ru})."
    game["phase"] = "night"
    game["round"] += 1
    game["votes"] = {}
    game["night"] = {"kill": None, "heal": None, "check": None}

DEFAULT_LANG = "ru"

def t(user_id, key):
    # Simple localization helper (fallback returns key)
    TEXT = {
        "main_menu": "Добро пожаловать в бот с мини-играми! Выберите игру или функцию из меню ниже.",
    }
    return TEXT.get(key, key)

# ------------------- /start -------------------
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    update_user_streak(uid, message.from_user.first_name or message.from_user.username or str(uid))

    # Mark user as started for notifications
    user = get_user(uid)
    data = load_data()
    data["users"][str(uid)]["started"] = True
    save_data(data)

    # require subscription
    if REQUIRED_CHANNEL and not is_user_subscribed(uid):
        url = _channel_url() or "https://t.me/"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📣 Подписаться", url=url))
        bot.send_message(message.chat.id, "⚠️ Подпишитесь на канал, чтобы использовать этого бота.", reply_markup=kb)
        return

    # show localized main menu
    menu_kb = main_menu_keyboard()
    bot.send_message(message.chat.id, t(uid, "main_menu"), reply_markup=menu_kb)

@bot.message_handler(commands=["topusers"])
def topusers_cmd(message):
    uid = message.from_user.id
    update_user_streak(uid, message.from_user.first_name or message.from_user.username or str(uid))

    d = load_data()
    users = d.get("users", {})
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    rows = []
    for uid_str, rec in users.items():
        if not isinstance(rec, dict):
            continue
        streak = int(rec.get("streak_current", 0) or 0)
        last_day = rec.get("streak_last_day")
        if streak <= 0:
            continue
        # "Не сбивается серия": активность сегодня или вчера.
        if last_day not in (today, yesterday):
            continue
        name = rec.get("display_name") or f"user_{uid_str}"
        rows.append((streak, name, last_day))

    if not rows:
        bot.send_message(message.chat.id, "Пока нет активных серий. Начните использовать бота ежедневно.")
        return

    rows.sort(key=lambda x: (-x[0], x[1].lower()))
    top = rows[:15]
    text = "🏆 *Топ пользователей по серии*\n"
    text += "_Серия считается по дням активности в боте._\n\n"
    for i, (streak, name, last_day) in enumerate(top, 1):
        status = "✅ сегодня" if last_day == today else "⌛ вчера"
        text += f"{i}. {name} — {streak} дн. ({status})\n"

    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=["settext"])
def settext_cmd(message):
    uid = message.from_user.id

    if uid not in user_sys_settings:
        user_sys_settings[uid] = {
            "msg": "Ваше сообщение",
            "btn": "ОК",
            "title": "Заголовок",
            "gui": "Текст внутри GUI"
        }

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("1. Изменить текст сообщения", callback_data="set_msg"))
    kb.add(types.InlineKeyboardButton("2. Изменить текст кнопки", callback_data="set_btn"))
    kb.add(types.InlineKeyboardButton("3. Изменить заголовок сообщения", callback_data="set_title"))
    kb.add(types.InlineKeyboardButton("4. Изменить текст popup-окна", callback_data="set_gui"))

    bot.send_message(
        message.chat.id,
        "🔧 *Настройки системного уведомления*\nВыберите, что изменить:",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["messagenot"])
def messagenot_cmd(message):
    uid = message.from_user.id
    # only allow if subscribed
    if REQUIRED_CHANNEL and not is_user_subscribed(uid):
        url = _channel_url() or "https://t.me/"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("Подписаться", url=url))
        bot.send_message(message.chat.id, "⚠️ Для использования этой функции подпишитесь на канал.", reply_markup=kb)
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("1. Изменить текст сообщения", callback_data="messagenot_msg"))
    kb.add(types.InlineKeyboardButton("2. Изменить текст кнопки", callback_data="messagenot_btn"))
    kb.add(types.InlineKeyboardButton("3. Изменить тип кнопки", callback_data="messagenot_type"))
    kb.add(types.InlineKeyboardButton("4. Отправить всем", callback_data="messagenot_send"))
    bot.send_message(message.chat.id, "⚙️ Настройки рассылки — выберите действие:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data in ("messagenot_msg","messagenot_btn","messagenot_type","messagenot_send"))
def messagenot_callback(call):
    try:
        uid = call.from_user.id
        action = call.data.split("_")[1]
        if action == "msg":
            system_notify_wait[uid] = "broadcast_msg"
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "✏ Введите текст рассылки (сообщение):")
            return
        if action == "btn":
            system_notify_wait[uid] = "broadcast_btn"
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "✏ Введите текст кнопки:")
            return
        if action == "type":
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Ссылка", callback_data="messagenot_type_link"))
            kb.add(types.InlineKeyboardButton("Без кнопки", callback_data="messagenot_type_none"))
            safe_edit_message(call, "Выберите тип кнопки:", reply_markup=kb)
            bot.answer_callback_query(call.id)
            return
        if action == "send":
            bot.answer_callback_query(call.id, "Запускаю отправку...")
            d = load_data()
            users = d.get("users", {})
            sent = 0
            skipped = 0
            for uid_str, info in users.items():
                try:
                    dest = int(uid_str)
                    if not info.get("started"):
                        skipped += 1
                        continue
                    if REQUIRED_CHANNEL and not is_user_subscribed(dest):
                        skipped += 1
                        continue
                    # prepare keyboard
                    # prepare keyboard only if needed
                    btn_type = BROADCAST_SETTINGS.get("btn_type")
                    if btn_type == "link":
                        kb = types.InlineKeyboardMarkup()
                        kb.add(types.InlineKeyboardButton(BROADCAST_SETTINGS.get("btn_text","Открыть"), url=BROADCAST_SETTINGS.get("btn_link")))
                        bot.send_message(dest, BROADCAST_SETTINGS.get("msg", ""), reply_markup=kb)
                    elif btn_type == "callback":
                        kb = types.InlineKeyboardMarkup()
                        kb.add(types.InlineKeyboardButton(BROADCAST_SETTINGS.get("btn_text","Открыть"), callback_data="broadcast_open"))
                        bot.send_message(dest, BROADCAST_SETTINGS.get("msg", ""), reply_markup=kb)
                    else:
                        # no button
                        bot.send_message(dest, BROADCAST_SETTINGS.get("msg", ""))
                    sent += 1
                    time.sleep(0.05)
                except Exception:
                    skipped += 1
            bot.send_message(uid, f"Готово. Доставлено: {sent}, пропущено: {skipped}")
            return
    except Exception as e:
        print("MESSAGENOT ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка в редакторе сообщений")


@bot.callback_query_handler(func=lambda c: c.data in ("messagenot_type_link","messagenot_type_none"))
def messagenot_type_choice(call):
    try:
        uid = call.from_user.id
        if call.data.endswith("link"):
            system_notify_wait[uid] = "broadcast_btn_link"
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "✏ Введите ссылку для кнопки (напр. https://t.me/minigamesisbot):")
            return
        else:
            # set to "none" - remove button from future broadcasts
            BROADCAST_SETTINGS["btn_type"] = "none"
            BROADCAST_SETTINGS["btn_text"] = ""
            BROADCAST_SETTINGS["btn_link"] = ""
            # persist
            try:
                d = load_data()
                d["broadcast"] = BROADCAST_SETTINGS
                save_data(d)
            except Exception:
                pass
            bot.answer_callback_query(call.id, "Готово — кнопка будет убрана из рассылки.")
            bot.send_message(uid, "✅ Тип кнопки: без кнопки. При рассылке кнопка не будет отображаться.")
            return
    except Exception as e:
        print("TYPE CHOICE ERROR", e)
        bot.answer_callback_query(call.id, "Ошибка выбора типа")

@bot.callback_query_handler(func=lambda c: c.data == "broadcast_open")
def broadcast_open(call):
    # when user clicks callback button in broadcast message
    try:
        bot.answer_callback_query(call.id)
        bot.send_message(call.from_user.id, f"📌 Открытие рассылки:\n\n{BROADCAST_SETTINGS.get('msg','')}")
    except Exception as e:
        print("BROADCAST OPEN ERROR", e)

@bot.message_handler(commands=["mode"])
def set_mode(message):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💬 Чат", callback_data="mode_chat"))
    kb.add(types.InlineKeyboardButton("⚡ Кратко", callback_data="mode_short"))
    kb.add(types.InlineKeyboardButton("🧠 Подробно", callback_data="mode_long"))
    kb.add(types.InlineKeyboardButton("💻 Код", callback_data="mode_code"))

    bot.send_message(
        message.chat.id,
        "🎛 Выбери режим ответа AI:",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("mode_"))
def mode_callback(call):
    try:
        uid = call.from_user.id
        mode = call.data.split("_")[1]
        user_ai_mode[uid] = mode
        
        mode_names = {
            "chat": "💬 Чат",
            "short": "⚡ Кратко",
            "long": "🧠 Подробно",
            "code": "💻 Код"
        }
        
        bot.answer_callback_query(call.id, f"✅ Режим выбран: {mode_names.get(mode, mode)}")
        bot.edit_message_text(f"✅ Выбран режим: {mode_names.get(mode, mode)}", inline_message_id=call.inline_message_id)
    except Exception as e:
        print("MODE CALLBACK ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")

@bot.message_handler(commands=["anim"])
def toggle_anim(message):
    uid = message.from_user.id
    current_state = user_show_easter_egg.get(uid, False)
    user_show_easter_egg[uid] = not current_state
    
    if user_show_easter_egg[uid]:
        bot.send_message(message.chat.id, "🐣 Пасхалка включена! Теперь она будет отображаться в инлайн меню.\n\nЧтобы её выключить, напишите /anim")
    else:
        bot.send_message(message.chat.id, "🐣 Пасхалка отключена. Она больше не будет отображатся в меню.\n\nЧтобы её включить, напишите /anim")

@bot.message_handler(func=lambda m: m.text == "🧱 Тетрис")
def tetris(message):
    bot.send_message(message.chat.id, "Чтобы играть в тетрис — напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🕵️‍♀️ Прятки")
def hideandseek(message):
    bot.send_message(message.chat.id, "Чтобы играть в прятки — напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎭 Мафия")
def mafia(message):
    bot.send_message(message.chat.id, "Чтобы играть в мафию — напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "✖️ Крестики-нолики")
def ttt(message):
    bot.send_message(message.chat.id, "Чтобы играть в крестики-нолики — напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "💰 Миллионер")
def millionaire(message):
    bot.send_message(message.chat.id, "Чтобы играть в миллионер — напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "💬 Режим ИИ")
def ai_mode(message):
    bot.send_message(message.chat.id, "Чтобы использовать режим ИИ — напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🐣 Пасхалка")
def pashalka(message):
    bot.send_message(message.chat.id, "Чтобы запустить анимацию пасхалки - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🪙 Орёл или решка")
def orel(message):
    bot.send_message(message.chat.id, "Чтобы играть в орёл или решка - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🔔 Ваше уведомление")
def notification(message):
    bot.send_message(message.chat.id, "Чтобы настроить системное уведомление - напиши <code>/messagenot</code>", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🖥 TELOS v1.0")
def telos(message):
    uid = message.from_user.id
    st = _telos_get_state(uid)
    st["booted"] = True
    _telos_save_state(uid, st)
    bot.send_message(message.chat.id, _telos_home_text(uid), parse_mode="Markdown", reply_markup=telos_main_menu())

@bot.message_handler(func=lambda m: m.text == "🔢 Угадай число")
def ugadayka(message):
    bot.send_message(message.chat.id, "Чтобы играть в угадай число - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "✂ Камень-ножницы-бумага")
def rsp(message):
    bot.send_message(message.chat.id, "Чтобы играть в камень ножницы бумага - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🐍 Змейка")
def snake(message):
    bot.send_message(message.chat.id, "Чтобы играть в змейку - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎰 Казино")
def casino(message):
    bot.send_message(message.chat.id, "Чтобы запустить казино - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🐦 Flappy Bird")
def flappybird(message):
    bot.send_message(message.chat.id, "Чтобы играть в flappy Bird - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🔢 2048")
def dvsorokvosem(message):
    bot.send_message(message.chat.id, "Чтобы играть в 2048 - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🏓 Пинг-понг")
def pingpong(message):
    bot.send_message(message.chat.id, "Чтобы играть в пинг-понг - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(commands=["connect"])
def connect(message):
    bot.send_message(
        message.chat.id,
        "⚙️ <b>Подключение через Telegram Business</b>\n\n"
        "ВНИМАНИЕ! Сейчас в разработке!\n"
        "AI-функции в business-режиме отключены.\n\n"
        "<b>Доступные игры (этап 1):</b>\n"
        "• тетрис\n"
        "• 2048\n"
        "• кнб (камень-ножницы-бумага)\n"
        "• угадай число\n"
        "• казино\n"
        "• орёл или решка\n\n"
        "<b>Как подключить:</b>\n"
        "1. Скопируйте имя <code>@minigamesisbot</code>\n"
        "2. Откройте: Настройки → Telegram для бизнеса → Чат-боты\n"
        "3. Добавьте бота и примените настройки\n\n"
        "После подключения просто отправьте в бизнес-чат название игры.",
        parse_mode="HTML",
    )

@bot.message_handler(func=lambda m: m.text == "🚀 Поддержать автора")
def support(message):
        bot.send_message(message.chat.id, "Если вам нравится этот бот, вы можете поддержать автора отправив тон на адрес:\n\n💳 <code>UQDla14mdjvSsjI1KMJ8cktcbn-smuKXwmFJXPdRT95-k4qQ</code>\n\nЗаранее cпасибо вашу поддержку!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🕵️‍♀️ Прятки")
def hide_and_seek(message):
    bot.send_message(message.chat.id, "Чтобы играть в прятки - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🔤 Виселица")
def hangman_message(message):
    bot.send_message(message.chat.id, "Чтобы играть в Виселицу - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🔤 Викторина")
def quiz(message):
    bot.send_message(message.chat.id, "Чтобы играть в викторину - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "⚡ Комбо-битва")
def combo(message): 
    bot.send_message(message.chat.id, "Чтобы играть в комбо-битву - напиши <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎮 Играть")
def play(message):
    bot.send_message(message.chat.id, "Чтобы играть — используй инлайн через @YourBotUsername в любом чате!")

@bot.inline_handler(lambda q: q.query.strip() != "")
def ai_inline(query):
    uid = query.from_user.id
    update_user_streak(uid, query.from_user.first_name or query.from_user.username or str(uid))
    # require subscription for inline AI
    if REQUIRED_CHANNEL and not is_user_subscribed(uid):
        return inline_subscription_prompt(query)
    text = query.query.strip()

    allow, err = can_use_ai(uid)
    if not allow:
        bot.answer_inline_query(
            query.id,
            [types.InlineQueryResultArticle(
                id="nope",
                title="⚠️ Лимит",
                input_message_content=types.InputTextMessageContent(err)
            )],
            cache_time=1,
            is_personal=True
        )
        return

    req_id = uuid.uuid4().hex
    data = load_data()
    data["users"][str(uid)]["pending"][req_id] = {
        "q": text,
        "a": None,
        "status": "wait"
    }
    save_data(data)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📩 Получить ответ", callback_data=f"ai_{uid}_{req_id}"))

    result = types.InlineQueryResultArticle(
        id=req_id,
        title="🤖 Спросить ChatGPT",
        description=text[:60],
        input_message_content=types.InputTextMessageContent(
            f"💬 *Вопрос:*\n{text}",
            parse_mode="Markdown"
        ),
        reply_markup=kb
    )

    bot.answer_inline_query(query.id, [result], cache_time=1, is_personal=True)

# ------------------- INLINE MAIN (empty query) -------------------
@bot.inline_handler(lambda q: q.query.strip() == "")
def inline_handler(query):
    try:
        user = query.from_user
        update_user_streak(user.id, user.first_name or user.username or str(user.id))
        # require subscription for inline features
        if REQUIRED_CHANNEL and not is_user_subscribed(user.id):
            return inline_subscription_prompt(query)
        user_name = html.escape(user.first_name or "Игрок")
        starter_id = user.id
        results = []

        # ---------- RPS (Камень Ножницы Бумага) ----------


        # TTT
        join_markup = types.InlineKeyboardMarkup()
        join_markup.add(types.InlineKeyboardButton("Присоединиться ⭕", callback_data=f"ttt_join_{starter_id}"))
        ttext = f"🎮 Крестики-нолики\n❌ {user_name}\n⭕ — (ожидается)\nНажмите «Присоединиться ⭕», чтобы начать."
        results.append(types.InlineQueryResultArticle(
            id=f"ttt_{short_id()}", title="❌ Крестики-нолики",
            description="Крестики-нолики на 2 игрока",
            input_message_content=types.InputTextMessageContent(message_text=ttext, parse_mode="HTML"),
            reply_markup=join_markup))

        # Millionaire preview (creates short game id)
        qdata = random.choice(questions)
        gid = short_id()
        millionaire_games[gid] = {"question": qdata, "attempts": 3}
        markup_m = types.InlineKeyboardMarkup()
        for i, opt in enumerate(qdata["options"]):
            markup_m.add(types.InlineKeyboardButton(opt, callback_data=f"millionaire_{gid}_{i}"))
        results.append(types.InlineQueryResultArticle(
            id=f"millionaire_{gid}",
            title="💰 Миллионер",
            description="Ответьте на вопрос и проверьте свои знания",
            input_message_content=types.InputTextMessageContent(f"💰 {qdata['question']}\nОсталось попыток: 3"),
            reply_markup=markup_m
        ))

        # Easter (показывается если пользователь включил /anim)
        if user_show_easter_egg.get(starter_id, False):
            egg_markup = types.InlineKeyboardMarkup()
            egg_markup.add(types.InlineKeyboardButton("🐣 Пасхалка", callback_data="easter_egg"))
            results.append(types.InlineQueryResultArticle(
                id=f"egg_{short_id()}",
                title="🐣 Пасхалка",
                description="Анимация",
                input_message_content=types.InputTextMessageContent("🐣 Нажмите кнопку ниже"),
                reply_markup=egg_markup
            ))

        # Coin flip
        coin_m = types.InlineKeyboardMarkup()
        coin_m.add(types.InlineKeyboardButton("Бросить 🪙", callback_data="coin_flip"))
        results.append(types.InlineQueryResultArticle(
            id=f"coin_{short_id()}",
            title="🪙 Орёл или решка",
            description="Рандомный выбор между орлом и решкой",
            input_message_content=types.InputTextMessageContent("🪙 Орёл или решка?"),
            reply_markup=coin_m
        ))

        # TELOS OS
        results.append(types.InlineQueryResultArticle(
            id=f"os_{short_id()}",
            title="🖥 TELOS v1.1 (macOS)",
            description="Мини ОС в телеграме. Версия 1.1 с новыми функциями!",
            input_message_content=types.InputTextMessageContent("🖥 *TELOS v1.1*\nВыбирайте приложение:", parse_mode="Markdown"),
            reply_markup=telos_main_menu()
        ))

        # Guess number
        guess_m = types.InlineKeyboardMarkup()
        row = []
        for i in range(1, 11):
            row.append(types.InlineKeyboardButton(str(i), callback_data=f"guess_inline_{i}"))
            if i % 5 == 0:
                guess_m.row(*row)
                row = []
        results.append(types.InlineQueryResultArticle(
            id=f"guess_{short_id()}",
            title="🔢 Угадай число",
            description="От 1 до 10",
            input_message_content=types.InputTextMessageContent("🔢 Угадай число (1–10)"),
            reply_markup=guess_m
        ))

        # ---------- SYSTEM NOTIFICATION (inline preview) ----------
        # Если пользователь уже сохранил своё уведомление в ЛС через /settext -> set_...
        u_uid = query.from_user.id
        if u_uid in user_sys_settings:
            data = user_sys_settings[u_uid]
            # показываем только если хотя бы есть заголовок или текст — это настраиваемо
            if data.get("title") or data.get("msg"):
                sys_preview_id = short_id()
                btn_text = data.get("btn") or "Открыть"
                markup_sys = types.InlineKeyboardMarkup()
                # при клике откроется GUI автора (мы используем callback sysopen_{uid})
                markup_sys.add(types.InlineKeyboardButton(btn_text, callback_data=f"sysopen_{u_uid}_{sys_preview_id}"))
                results.append(types.InlineQueryResultArticle(
                    id=f"sys_{sys_preview_id}",
                    title="🔔 Системное уведомление",
                    description="Ваше уведомление",
                    input_message_content=types.InputTextMessageContent(
                        f"*{data.get('title','Системное уведомление')}*\n{data.get('msg','')}",
                        parse_mode="Markdown"
                    ),
                    reply_markup=markup_sys
                ))

        # Slot
        slot_m = types.InlineKeyboardMarkup()
        slot_m.add(types.InlineKeyboardButton("🎰 Крутить", callback_data="slot_spin"))
        results.append(types.InlineQueryResultArticle(
            id=f"slot_{short_id()}",
            title="🎰 Казино",
            description="Слот машина",
            input_message_content=types.InputTextMessageContent("🎰 Нажмите ниже для запуска!"),
            reply_markup=slot_m
        ))

        # Snake
        results.append(types.InlineQueryResultArticle(
            id=f"snake_{short_id()}",
            title="🐍 Змейка",
            description="Инлайн-змейка",
            input_message_content=types.InputTextMessageContent("🐍 Используйте кнопки для управления змейкой. "),
            reply_markup=snake_controls()
        ))

        # Tetris
        tgid = short_id()
        results.append(types.InlineQueryResultArticle(
            id=f"tetris_{tgid}",
            title="🧱 Тетрис",
            description="Обычный тетрис",
            input_message_content=types.InputTextMessageContent(
                "🧱 Тетрис\nНажмите кнопку «Старт», чтобы начать."
            ),
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("▶️ Старт", callback_data="tetris_new")
            )
        ))

        # Flappy preview
        fp_markup = types.InlineKeyboardMarkup()
        fp_markup.add(types.InlineKeyboardButton("⬆️ Прыжок (начать)", callback_data="flappy_new"))
        results.append(types.InlineQueryResultArticle(
            id=f"flappy_{short_id()}",
            title="🐦 Flappy Bird",
            description="Нажми, чтобы начать Flappy Bird",
            input_message_content=types.InputTextMessageContent("🐦 Flappy Bird\nНажмите кнопку, чтобы начать."),
            reply_markup=fp_markup
        ))

        # 2048 preview
        preview_markup = types.InlineKeyboardMarkup()
        preview_markup.row(types.InlineKeyboardButton("⬆️", callback_data="g2048_new_up"))
        preview_markup.row(types.InlineKeyboardButton("⬅️", callback_data="g2048_new_left"),
                           types.InlineKeyboardButton("➡️", callback_data="g2048_new_right"))
        preview_markup.row(types.InlineKeyboardButton("⬇️", callback_data="g2048_new_down"))
        results.append(types.InlineQueryResultArticle(
            id=f"g2048_{short_id()}",
            title="🔢 2048",
            description="",
            input_message_content=types.InputTextMessageContent("🔢 2048\nНажмите кнопку, чтобы начать."),
            reply_markup=preview_markup
        ))

        # Pong preview
        pgid = short_id()
        pm = types.InlineKeyboardMarkup()
        pm.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"pong_{pgid}_join"))
        results.append(types.InlineQueryResultArticle(
            id=f"pong_{pgid}",
            title="🏓 Пинг-понг (2 игрока)",
            description="Сейчас в разработке",
            input_message_content=types.InputTextMessageContent("🏓 Пинг-понг\nНажмите 'Присоединиться' чтобы игра началась."),
            reply_markup=pm
        ))

        # -------- HIDE & SEEK (Прятки) --------
        gid = short_id()
        hide_games[gid] = {
            "host": starter_id,
            "secret": None,
            "guesser": None,
            "attempts": 5,
            "finished": False
        }

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "🎯 Загадать клетку",
                callback_data=f"hide_set_{gid}"
            )
        )

        results.append(
            types.InlineQueryResultArticle(
                id=f"hide_{gid}",
                title="🕵️ Прятки",
                description="Загадайте клетку - другой игрок угадает",
                input_message_content=types.InputTextMessageContent(
                    "🕵️ *Прятки*\n\n"
                    "Игрок 1 загадывает клетку.\n"
                    "Игрок 2 угадывает за 5 попыток.",
                    parse_mode="Markdown"
                ),
                reply_markup=kb
            )
        )

        # Hangman (Виселица)
        hgid = short_id()
        hword = random.choice(list(HANGMAN_WORDS.keys()))
        hhint = HANGMAN_WORDS[hword]
        hangman_games[hgid] = {
            "word": hword,
            "hint": hhint,
            "guessed": set(),
            "wrong": set(),
            "attempts": 6,
            "hint_used": False
        }
        hgame = hangman_games[hgid]
        results.append(types.InlineQueryResultArticle(
            id=f"hangman_{hgid}",
            title="🔤 Виселица",
            description="Угадайте слово, выбирая буквы",
            input_message_content=types.InputTextMessageContent(render_hangman_state(hgame)),
            reply_markup=render_hangman_keyboard(hgid, hgame)
        ))

        # Викторина - кто быстрее
        qgid = short_id()
        qqdata = random.choice(QUIZ_QUESTIONS)
        quiz_games[qgid] = {
            "question": qqdata["q"],
            "answer": qqdata["a"].lower(),
            "p1": starter_id,
            "p1_name": query.from_user.first_name or "Игрок 1",
            "p1_name": query.from_user.first_name or "Игрок 1",
            "p2": None,
            "p1_input": "",
            "p2_input": "",
            "p1_answered": False,
            "p2_answered": False,
            "p1_correct": False,
            "p2_correct": False
        }
        
        qqkb = types.InlineKeyboardMarkup()
        qqkb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"quizgame_join_{qgid}"))
        results.append(types.InlineQueryResultArticle(
            id=f"quizgame_{qgid}",
            title="🧠 Викторина",
            description="Ответьте на вопрос первым!",
            input_message_content=types.InputTextMessageContent(
                f"🧠 *Викторина*\n\n"
                f"❓ {qqdata['q']}\n\n"
                f"Кто ответит первым правильно - выигрывает!",
                parse_mode="Markdown"
            ),
            reply_markup=qqkb
        ))

        # Комбо-битва
        cgid = short_id()
        combo_games[cgid] = {
            "p1": starter_id,
            "p1_name": query.from_user.first_name or "Игрок 1",
            "p1_name": query.from_user.first_name or "Игрок 1",
            "p2": None,
            "p1_choice": None,
            "p2_choice": None,
            "round": 1,
            "scores": {starter_id: 0},
            "choices": ["⚡ Молния", "🛡️ Щит", "🪨 Камень"]
        }
        
        ckb = types.InlineKeyboardMarkup()
        ckb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"combogame_join_{cgid}"))
        results.append(types.InlineQueryResultArticle(
            id=f"combogame_{cgid}",
            title="⚡ Комбо-битва",
            description="Выбирай атаку/защиту и побеждай!",
            input_message_content=types.InputTextMessageContent(
                f"⚡ *Комбо-битва*\n\n"
                f"Правила:\n"
                f"⚡ Молния > 🪨 Камень\n"
                f"🪨 Камень > 🛡️ Щит\n"
                f"🛡️ Щит > ⚡ Молния\n\n"
                f"Лучший из 3 раундов!",
                parse_mode="Markdown"
            ),
            reply_markup=ckb
        ))

        # Мафия
        mgid = short_id()
        host_name = query.from_user.first_name or "Игрок 1"
        mafia_games[mgid] = {
            "owner": starter_id,
            "players": [starter_id],
            "alive": [starter_id],
            "names": {starter_id: host_name},
            "roles": {},
            "phase": "lobby",
            "round": 1,
            "night": {"kill": None, "heal": None, "check": None},
            "votes": {},
            "last_event": "Лобби создано."
        }
        results.append(types.InlineQueryResultArticle(
            id=f"mafia_{mgid}",
            title="🎭 Мафия",
            description="Игра на роли: ночь и голосование днем",
            input_message_content=types.InputTextMessageContent(
                "🎭 Мафия\n\nСоздано лобби. Нажмите «Присоединиться», затем «Старт»."
            ),
            reply_markup=mafia_build_lobby_kb(mgid)
        ))

        bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

    except Exception as e:
        print("INLINE ERROR:", e)

# ------------------- Flappy (variant B) -------------------
def render_flappy_state(state):
    W, H = 10, 10
    field = [["⬛" for _ in range(W)] for _ in range(H)]
    for x, gap in state["pipes"]:
        for y in range(H):
            if not (gap <= y <= gap+2):
                if 0 <= x < W:
                    field[y][x] = "🟥"
    by = int(state["bird_y"])
    if 0 <= by < H:
        field[by][2] = "🐦"
    return "\n".join("".join(r) for r in field)

@bot.callback_query_handler(func=lambda c: c.data.startswith("flappy_"))
def flappy_callback(call):
    try:
        parts = call.data.split("_", 2)  # flappy_new OR flappy_<gid>_jump
        if parts[1] == "new":
            gid = short_id()
            games_flappy[gid] = {"bird_y":5, "pipes":[(9,3),(13,4)], "score":0}
            state = games_flappy[gid]
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬆️ Прыжок", callback_data=f"flappy_{gid}_jump"))
            bot.edit_message_text(f"🐦 Flappy Bird\nОчки: {state['score']}\n\n{render_flappy_state(state)}",
                                  inline_message_id=call.inline_message_id, reply_markup=markup)
            bot.answer_callback_query(call.id)
            return

        gid = parts[1]
        action = parts[2] if len(parts) > 2 else "jump"
        state = games_flappy.get(gid)
        if not state:
            bot.answer_callback_query(call.id, "Игра не найдена.")
            return

        # Advance simulation: pipes move left
        state["pipes"] = [(x-1, gap) for x,gap in state["pipes"]]
        if state["pipes"] and state["pipes"][-1][0] < 6:
            state["pipes"].append((9, random.randint(2,6)))

        # Player action
        if action == "jump":
            state["bird_y"] -= 2
        # gravity
        state["bird_y"] += 1

        # scoring: when pipe passes x==1 (just after bird) increment
        new_pipes = []
        for x,gap in state["pipes"]:
            if x >= 0:
                new_pipes.append((x,gap))
            if x == 1:
                state["score"] += 1
        state["pipes"] = new_pipes

        # collision
        by = state["bird_y"]
        collided = False
        if by < 0 or by >= 10:
            collided = True
        else:
            for x,gap in state["pipes"]:
                if x == 2:  # bird x pos is 2
                    if not (gap <= by <= gap+2):
                        collided = True
                        break

        if collided:
            bot.edit_message_text(f"💥 Вы проиграли! Очки: {state['score']}", inline_message_id=call.inline_message_id)
            games_flappy.pop(gid, None)
            bot.answer_callback_query(call.id, "Игра окончена")
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬆️ Прыжок", callback_data=f"flappy_{gid}_jump"))
        bot.edit_message_text(f"🐦 Flappy Bird\nОчки: {state['score']}\n\n{render_flappy_state(state)}",
                              inline_message_id=call.inline_message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    except Exception as e:
        print("FLAPPY ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка игры Flappy")


@bot.callback_query_handler(func=lambda c: c.data.startswith("guess_inline_"))
def guess_inline_callback(call):
    try:
        parts = call.data.split("_")
        # callback format: guess_inline_<number>
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Неверный формат данных")
            return
        try:
            guess = int(parts[2])
        except:
            bot.answer_callback_query(call.id, "Неверный выбор")
            return

        mid = call.inline_message_id
        if not mid:
            bot.answer_callback_query(call.id, "Эта игра доступна только в inline-режиме")
            return

        state = inline_guess_games.get(mid)
        if not state:
            state = {"target": random.randint(1, 10), "attempts": 3, "tried": []}
            inline_guess_games[mid] = state

        if guess == state["target"]:
            bot.edit_message_text(f"✅ Правильно! Загаданное число: {state['target']}", inline_message_id=mid)
            inline_guess_games.pop(mid, None)
            bot.answer_callback_query(call.id, "Правильно!")
            return

        state["attempts"] -= 1
        state["tried"].append(guess)
        if state["attempts"] <= 0:
            bot.edit_message_text(f"❌ Попытки кончились. Загаданное число: {state['target']}", inline_message_id=mid)
            inline_guess_games.pop(mid, None)
            bot.answer_callback_query(call.id, "Игра окончена")
            return

        hint = "меньше" if guess > state["target"] else "больше"
        # rebuild keyboard
        kb = types.InlineKeyboardMarkup()
        row = []
        for i in range(1, 11):
            row.append(types.InlineKeyboardButton(str(i), callback_data=f"guess_inline_{i}"))
            if i % 5 == 0:
                kb.row(*row)
                row = []

        bot.edit_message_text(
            f"🔢 Угадай число (1–10)\nПопыток осталось: {state['attempts']}\nТвое предположение: {guess} — {hint}",
            inline_message_id=mid,
            reply_markup=kb
        )
        bot.answer_callback_query(call.id, "Неправильно")

    except Exception as e:
        print("GUESS INLINE ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка игры Угадай число")


@bot.callback_query_handler(func=lambda c: c.data.startswith("snake_"))
def snake_callback(call):
    try:
        parts = call.data.split("_")
        if len(parts) < 2:
            bot.answer_callback_query(call.id, "Неверный формат")
            return
        action = parts[1]  # up/left/right/down

        mid = call.inline_message_id
        if not mid:
            bot.answer_callback_query(call.id, "Эта игра доступна только в inline-режиме")
            return

        state = inline_snake_games.get(mid)
        if not state:
            W, H = 8, 6
            init_x, init_y = W // 2, H // 2
            snake = [(init_x, init_y), (init_x - 1, init_y), (init_x - 2, init_y)]
            food = (random.randint(0, W - 1), random.randint(0, H - 1))
            while food in snake:
                food = (random.randint(0, W - 1), random.randint(0, H - 1))
            state = {"W": W, "H": H, "snake": snake, "dir": action, "food": food, "score": 0}
            inline_snake_games[mid] = state

        dirs = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        if action not in dirs:
            action = state.get("dir", "right")
        dx, dy = dirs[action]
        state["dir"] = action

        head_x, head_y = state["snake"][0]
        new_head = (head_x + dx, head_y + dy)

        W, H = state["W"], state["H"]
        # collision with walls or self
        if new_head[0] < 0 or new_head[0] >= W or new_head[1] < 0 or new_head[1] >= H or new_head in state["snake"]:
            bot.edit_message_text(f"💥 Вы проиграли! Очки: {state['score']}", inline_message_id=mid)
            inline_snake_games.pop(mid, None)
            bot.answer_callback_query(call.id, "Игра окончена")
            return

        # move
        state["snake"].insert(0, new_head)
        if new_head == state["food"]:
            state["score"] += 1
            food = (random.randint(0, W - 1), random.randint(0, H - 1))
            while food in state["snake"]:
                food = (random.randint(0, W - 1), random.randint(0, H - 1))
            state["food"] = food
        else:
            state["snake"].pop()

        # render
        field = [["⬛" for _ in range(W)] for _ in range(H)]
        fx, fy = state["food"]
        field[fy][fx] = "🍎"
        for idx, (sx, sy) in enumerate(state["snake"]):
            if 0 <= sy < H and 0 <= sx < W:
                field[sy][sx] = "🟢" if idx == 0 else "🟩"

        text = f"🐍 Змейка — очки: {state['score']}\n\n" + "\n".join("".join(row) for row in field)

        bot.edit_message_text(text, inline_message_id=mid, reply_markup=snake_controls())
        bot.answer_callback_query(call.id)

    except Exception as e:
        print("SNAKE ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка игры Змейка")

@bot.callback_query_handler(func=lambda c: c.data.startswith("hide_set_"))
def hide_set(call):
    gid = call.data.split("_")[2]
    game = hide_games.get(gid)

    if not game or call.from_user.id != game["host"]:
        bot.answer_callback_query(call.id, "❌ Только создатель игры")
        return

    kb = hide_keyboard(f"hide_secret_{gid}")

    bot.edit_message_text(
        "🎯 *Выбери клетку, где вы прячетесь:*",
        inline_message_id=call.inline_message_id,
        reply_markup=kb,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("hide_secret_"))
def hide_secret(call):
    _, _, gid, cell = call.data.split("_")
    cell = int(cell)
    game = hide_games.get(gid)

    if not game or call.from_user.id != game["host"]:
        return

    game["secret"] = cell

    kb = hide_keyboard(f"hide_guess_{gid}")

    bot.edit_message_text(
        "🔍 *Игрок 2, угадывай!*\nПопыток: 5",
        inline_message_id=call.inline_message_id,
        reply_markup=kb,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("hide_guess_"))
def hide_guess(call):
    parts = call.data.split("_")
    if len(parts) == 3:
        _, gid, cell = parts
    elif len(parts) == 4:
        _, _, gid, cell = parts
    else:
        bot.answer_callback_query(call.id, "❌ Неверный формат данных")
        return

    cell = int(cell)
    game = hide_games.get(gid)

    if not game or game["finished"]:
        bot.answer_callback_query(call.id, "Игра завершена")
        return

    # ❗ ЗАПРЕТ играть самому с собой
    if call.from_user.id == game["host"]:
        bot.answer_callback_query(call.id, "❌ Вы не можете угадывать свою же клетку")
        return

    # назначаем угадывающего один раз
    if game["guesser"] is None:
        game["guesser"] = call.from_user.id

    if call.from_user.id != game["guesser"]:
        bot.answer_callback_query(call.id, "❌ Сейчас ход другого игрока")
        return

    if game["attempts"] <= 0:
        game["finished"] = True
        bot.edit_message_text(
            f"💀 *Попытки закончились!*\nКлетка была: {game['secret'] + 1}",
            inline_message_id=call.inline_message_id,
            parse_mode="Markdown"
        )
        return

    kb = hide_keyboard(f"hide_guess_{gid}")

    # correct guess
    if game.get("secret") == cell:
        game["finished"] = True
        try:
            bot.edit_message_text(
                f"🎉 *Угадали!*\nКлетка: {cell + 1}",
                inline_message_id=call.inline_message_id,
                parse_mode="Markdown"
            )
        except telebot.apihelper.ApiTelegramException as e:
            msg = str(e).lower()
            if "message is not modified" in msg:
                bot.answer_callback_query(call.id, "✅ Уже отмечено")
                return
            raise
        bot.answer_callback_query(call.id, "🎉 Правильно")
        return

    # wrong guess — consume an attempt
    game["attempts"] = max(0, game.get("attempts", 0) - 1)
    if game["attempts"] <= 0:
        game["finished"] = True
        try:
            bot.edit_message_text(
                f"💀 *Попытки закончились!*\nКлетка была: {game.get('secret', 0) + 1}",
                inline_message_id=call.inline_message_id,
                parse_mode="Markdown"
            )
        except telebot.apihelper.ApiTelegramException as e:
            msg = str(e).lower()
            if "message is not modified" in msg:
                bot.answer_callback_query(call.id, "❌ Ничего не изменилось")
                return
            raise
        bot.answer_callback_query(call.id, "💀 Попытки кончились")
        return

    new_message = f"❌ Мимо!\n🔁 Осталось попыток: {game['attempts']}"
    try:
        bot.edit_message_text(
            new_message,
            inline_message_id=call.inline_message_id,
            reply_markup=kb
        )
    except telebot.apihelper.ApiTelegramException as e:
        msg = str(e).lower()
        if "message is not modified" in msg:
            bot.answer_callback_query(call.id, "❌ Ничего не изменилось")
            return
        raise
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rps_mode_"))
def rps_choose_mode(call):
    _, _, mode, gid = call.data.split("_")

    game = rps_games.get(gid)
    if not game:
        bot.answer_callback_query(call.id, "Игра не найдена")
        return

    game["mode"] = mode

    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🪨", callback_data=f"rps_move_{gid}_rock"),
        types.InlineKeyboardButton("📄", callback_data=f"rps_move_{gid}_paper"),
        types.InlineKeyboardButton("✂️", callback_data=f"rps_move_{gid}_scissors")
    )

    bot.edit_message_text(
        "Выбери свой ход:",
        inline_message_id=call.inline_message_id,
        reply_markup=kb
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rps_join_"))
def rps_join(call):
    gid = call.data.split("_")[2]
    game = rps_games.get(gid)

    if not game:
        bot.answer_callback_query(call.id, "Игра не найдена")
        return

    if call.from_user.id == game["host"]:
        bot.answer_callback_query(call.id, "Нужен другой игрок")
        return

    game["guest"] = call.from_user.id

    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🪨", callback_data=f"rps_move_{gid}_rock"),
        types.InlineKeyboardButton("📄", callback_data=f"rps_move_{gid}_paper"),
        types.InlineKeyboardButton("✂️", callback_data=f"rps_move_{gid}_scissors")
    )

    bot.edit_message_text(
        "👥 *Игра началась!*\n\nОба игрока, выбирайте ход:",
        inline_message_id=call.inline_message_id,
        parse_mode="Markdown",
        reply_markup=kb
    )
    bot.answer_callback_query(call.id)

# ------------------- AI HANDLER -------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("ai_"))
def ai_callback(call):
    try:
        _, uid, rid = call.data.split("_")
        uid = int(uid)

        data = load_data()
        user = data["users"].get(str(uid))
        if not user:
            bot.answer_callback_query(call.id, "Данные пользователя не найдены")
            return

        req = user["pending"].get(rid)
        if not req:
            bot.answer_callback_query(call.id, "Запрос устарел")
            return

        # если ещё не считали — запускаем
        if req["status"] == "wait":
            req["status"] = "process"
            save_data(data)

            def work():
                try:
                    prompt = req["q"]
                    answer = ask_ai(prompt, uid)
                    inc_user_count(uid)
                
                    req["a"] = answer
                    req["status"] = "done"
                    save_data(data)

                except Exception as e:
                    req["a"] = f"Ошибка AI: {e}"
                    req["status"] = "done"
                    save_data(data)

            Thread(target=work, daemon=True).start()
            bot.answer_callback_query(call.id, "⏳ Готовлю ответ…")
            return

        # если готово
        if req["status"] == "done":
            answer = req["a"]

            # 🔹 КОРОТКИЙ → alert
            if len(answer) <= 180:
                bot.answer_callback_query(call.id, "✅ Ответ готов!")
                bot.send_message(call.from_user.id, f"🤖 Ответ:\n\n{answer[:4000]}")

                return

            # 🔹 ДЛИННЫЙ → редактируем inline сообщение
            text = (
                "🤖 *Ответ ChatGPT:*\n\n"
                + answer[:3900]  # запас
            )

            bot.edit_message_text(
                text,
                inline_message_id=call.inline_message_id,
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id)
            return

    except Exception as e:
        print("AI CALLBACK ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка при получении ответа")

# ------------------- TTT HANDLER -------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("ttt_join_"))
def ttt_join(call):
    try:
        # data format: ttt_join_{host_id}
        parts = call.data.split("_")
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Неверные данные.")
            return
        host_id = int(parts[2])
        guest_id = call.from_user.id

        if host_id == guest_id:
            bot.answer_callback_query(call.id, "Вы не можете играть сами с собой!")
            return

        # create game id
        gid = short_id()

        # try to fetch display names (store them now)
        host_name = _user_display_name_from_id(host_id)
        guest_name = call.from_user.username or call.from_user.first_name or f"Player_{guest_id}"

        # initial game state: scores start at 0
        inline_ttt_games[gid] = {
            "board": [" "] * 9,
            "players": [host_id, guest_id],   # players[0] -> ❌, players[1] -> ⭕
            "names": {host_id: host_name, guest_id: guest_name},
            "scores": {host_id: 0, guest_id: 0},
            # make guest (⭕) go first to match example "Ходит: ⭕"
            "turn": guest_id
        }

        game = inline_ttt_games[gid]
        text = ttt_render_header(game) + ttt_render_board(game["board"])
        kb = ttt_build_keyboard(gid, game["board"])

        bot.edit_message_text(text, inline_message_id=call.inline_message_id, reply_markup=kb, parse_mode=None)
        bot.answer_callback_query(call.id, "Игра началась! Удачи.")
    except Exception as e:
        print("TTT JOIN ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка при создании игры TTT.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("rps_move_"))
def rps_move(call):
    _, _, gid, move = call.data.split("_")
    uid = call.from_user.id

    game = rps_games.get(gid)
    if not game:
        bot.answer_callback_query(call.id, "Игра завершена")
        return

    # ход игрока
    game["moves"][uid] = move

    # 🤖 ПРОТИВ БОТА
    if game["mode"] == "bot":
        bot_move = random.choice(["rock", "paper", "scissors"])

        def win(a, b):
            return (a == "rock" and b == "scissors") or \
                   (a == "scissors" and b == "paper") or \
                   (a == "paper" and b == "rock")

        if move == bot_move:
            res = "🤝 Ничья"
        elif win(move, bot_move):
            res = "🎉 Вы победили!"
        else:
            res = "😢 Вы проиграли"

        bot.edit_message_text(
            f"Вы: {move}\nБот: {bot_move}\n\n{res}",
            inline_message_id=call.inline_message_id
        )
        rps_games.pop(gid, None)
        return

    # 👥 PVP — ждём второго игрока
    bot.edit_message_text(
        "⏳ Ожидаем ход второго игрока...",
        inline_message_id=call.inline_message_id
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ttt_move_"))
def ttt_move(call):
    try:
        # data: ttt_move_{gid}_{cell}
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Неверные данные хода.")
            return
        gid = parts[2]
        cell = int(parts[3])
        game = inline_ttt_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена или завершена.")
            return

        uid = call.from_user.id
        if uid not in game["players"]:
            bot.answer_callback_query(call.id, "Вы не участник этой игры.")
            return

        if uid != game["turn"]:
            bot.answer_callback_query(call.id, "Сейчас не ваш ход!")
            return

        if not (0 <= cell < 9):
            bot.answer_callback_query(call.id, "Неверная клетка.")
            return

        if game["board"][cell].strip():
            bot.answer_callback_query(call.id, "Клетка уже занята!")
            return

        # decide symbol
        symbol = "❌" if uid == game["players"][0] else "⭕"
        game["board"][cell] = symbol

        # check win
        b = game["board"]
        def win(bd, s):
            patterns = [
                (0,1,2),(3,4,5),(6,7,8),
                (0,3,6),(1,4,7),(2,5,8),
                (0,4,8),(2,4,6)
            ]
            for a,bp,c in patterns:
                if bd[a] == bd[bp] == bd[c] == s:
                    return True
            return False

        if win(b, symbol):
            # increment winner score
            winner_id = uid
            game["scores"][winner_id] = game["scores"].get(winner_id, 0) + 1
            title = f"🎉 Победил {symbol} — {game['names'].get(winner_id, _user_display_name_from_id(winner_id))}!"
            # show final board and scores
            text = title + "\n\n" + ttt_render_header(game) + ttt_render_board(game["board"])
            # keep scores but reset board for next round only on restart; here we display final and keep game entry to allow restart
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔁 Сыграть ещё", callback_data=f"ttt_restart_{gid}"))
            bot.edit_message_text(text, inline_message_id=call.inline_message_id, reply_markup=kb)
            # remove the game board but keep scores so restart can reuse
            game["board"] = [" "] * 9
            game["turn"] = game["players"][0]  # default who starts next (you can change)
            bot.answer_callback_query(call.id, "Победа!")
            return

        # check draw
        if " " not in b:
            text = "🤝 Ничья!\n\n" + ttt_render_header(game) + ttt_render_board(game["board"])
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔁 Сыграть ещё", callback_data=f"ttt_restart_{gid}"))
            bot.edit_message_text(text, inline_message_id=call.inline_message_id, reply_markup=kb)
            game["board"] = [" "] * 9
            game["turn"] = game["players"][0]
            bot.answer_callback_query(call.id, "Ничья!")
            return

        # next turn
        game["turn"] = game["players"][1] if uid == game["players"][0] else game["players"][0]

        # render updated board
        text = ttt_render_header(game) + ttt_render_board(game["board"])
        kb = ttt_build_keyboard(gid, game["board"])
        bot.edit_message_text(text, inline_message_id=call.inline_message_id, reply_markup=kb)
        bot.answer_callback_query(call.id, "Ход сделан.")
    except Exception as e:
        print("TTT MOVE ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка в ходе крестиков-ноликов.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ttt_restart_"))
def ttt_restart(call):
    try:
        parts = call.data.split("_")
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Неверные данные рестарта.")
            return
        gid = parts[2]
        game = inline_ttt_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена.")
            return
        # reset board but keep scores and names
        game["board"] = [" "] * 9
        # let O (players[1]) start next as before or alternate if you like
        game["turn"] = game["players"][1]
        text = ttt_render_header(game) + ttt_render_board(game["board"])
        kb = ttt_build_keyboard(gid, game["board"])
        bot.edit_message_text(text, inline_message_id=call.inline_message_id, reply_markup=kb)
        bot.answer_callback_query(call.id, "Новая партия — удачи!")
    except Exception as e:
        print("TTT RESTART ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка при рестарте игры.")

# ------------------- 2048 -------------------
def spawn_tile(board):
    empty = [(y, x) for y in range(4) for x in range(4) if board[y][x] == 0]
    if not empty:
        return board
    y, x = random.choice(empty)
    board[y][x] = 2 if random.random() < 0.9 else 4
    return board

def render_2048(board):
    COLORS = {
        0:   "⬜",   # пустая
        2:   "🟫",
        4:   "🟫",
        8:   "🟧",
        16:  "🟧",
        32:  "🟧",
        64:  "🟨",
        128: "🟨",
        256: "🟦",
        512: "🟦",
        1024: "🟪",
        2048: "🟧"
    }

    def cell(n):
        color = COLORS.get(n, "🟪")
        num = str(n) if n != 0 else ""
        return f"{color}{num.center(4)}{color}"

    top = "┌" + "───────" * 4 + "┐"
    sep = "├" + "───────" * 4 + "┤"
    bot = "└" + "───────" * 4 + "┘"

    lines = [top]
    for i, row in enumerate(board):
        line = "│"
        for c in row:
            line += cell(c)
        line += "│"
        lines.append(line)
        if i < 3:
            lines.append(sep)
    lines.append(bot)

    return "\n".join(lines)

def move_row_left(row):
    new = [v for v in row if v != 0]
    res = []
    i = 0
    while i < len(new):
        if i+1 < len(new) and new[i] == new[i+1]:
            res.append(new[i]*2)
            i += 2
        else:
            res.append(new[i])
            i += 1
    res += [0]*(4-len(res))
    return res

def move_board(board, direction):
    moved = False
    new = [[board[y][x] for x in range(4)] for y in range(4)]
    if direction in ("left","right"):
        for y in range(4):
            row = list(new[y])
            if direction == "right":
                row = row[::-1]
            moved_row = move_row_left(row)
            if direction == "right":
                moved_row = moved_row[::-1]
            if moved_row != new[y]:
                moved = True
            new[y] = moved_row
    else:
        cols = [[new[y][x] for y in range(4)] for x in range(4)]
        for x in range(4):
            col = cols[x]
            if direction == "down":
                col = col[::-1]
            moved_col = move_row_left(col)
            if direction == "down":
                moved_col = moved_col[::-1]
            for y in range(4):
                if new[y][x] != moved_col[y]:
                    moved = True
                new[y][x] = moved_col[y]
    return new, moved

# ------------------- TETRIS -------------------
TETRIS_SHAPES = [
    [[1, 1, 1, 1]],               # I
    [[1, 1], [1, 1]],             # O
    [[1, 1, 1], [0, 1, 0]],       # T
    [[1, 1, 1], [1, 0, 0]],       # L
    [[1, 1, 1], [0, 0, 1]],       # J
    [[1, 1, 0], [0, 1, 1]],       # S
    [[0, 1, 1], [1, 1, 0]],       # Z
    [[1, 1, 1]],                  # mini I
    [[1], [1], [1]],              # mini I vertical
    [[1, 1], [1, 0]],             # small L
    [[1, 1], [0, 1]],             # small J
    [[1, 1, 1], [1, 0, 1]],       # U
    [[0, 1, 0], [1, 1, 1], [0, 1, 0]],  # plus
]
TETRIS_COLORS = ["🟥", "🟧", "🟨", "🟩", "🟦", "🟪", "🟫", "⬜"]

def tetris_new_state():
    st = {
        "w": 10,
        "h": 14,
        "board": [[0]*10 for _ in range(14)],
        "piece": None,
        "score": 0,
        "over": False
    }
    tetris_spawn_piece(st)
    return st

def tetris_can_place(state, px, py, shape):
    for sy, row in enumerate(shape):
        for sx, v in enumerate(row):
            if not v:
                continue
            x = px + sx
            y = py + sy
            if x < 0 or x >= state["w"] or y < 0 or y >= state["h"]:
                return False
            if state["board"][y][x]:
                return False
    return True

def tetris_spawn_piece(state):
    shape = random.choice(TETRIS_SHAPES)
    color = random.randint(1, len(TETRIS_COLORS))
    px = (state["w"] - len(shape[0])) // 2
    py = 0
    if not tetris_can_place(state, px, py, shape):
        state["over"] = True
        return False
    state["piece"] = {"x": px, "y": py, "shape": shape, "color": color}
    return True

def tetris_lock_piece(state):
    p = state.get("piece")
    if not p:
        return
    for sy, row in enumerate(p["shape"]):
        for sx, v in enumerate(row):
            if v:
                state["board"][p["y"] + sy][p["x"] + sx] = p.get("color", 1)
    state["piece"] = None

def tetris_clear_lines(state):
    new_board = []
    cleared = 0
    for row in state["board"]:
        if all(c == 1 for c in row):
            cleared += 1
        else:
            new_board.append(row)
    while len(new_board) < state["h"]:
        new_board.insert(0, [0]*state["w"])
    state["board"] = new_board
    if cleared:
        state["score"] += cleared * 100
    return cleared

def tetris_move(state, dx):
    if state.get("over") or not state.get("piece"):
        return False
    p = state["piece"]
    nx = p["x"] + dx
    if tetris_can_place(state, nx, p["y"], p["shape"]):
        p["x"] = nx
        return True
    return False

def tetris_drop(state):
    if state.get("over") or not state.get("piece"):
        return False
    p = state["piece"]
    while tetris_can_place(state, p["x"], p["y"] + 1, p["shape"]):
        p["y"] += 1
    tetris_lock_piece(state)
    tetris_clear_lines(state)
    tetris_spawn_piece(state)
    return True

def tetris_render(state):
    w, h = state["w"], state["h"]
    view = [[state["board"][y][x] for x in range(w)] for y in range(h)]
    active = [[False]*w for _ in range(h)]
    p = state.get("piece")
    if p:
        for sy, row in enumerate(p["shape"]):
            for sx, v in enumerate(row):
                if v:
                    y = p["y"] + sy
                    x = p["x"] + sx
                    if 0 <= y < h and 0 <= x < w:
                        view[y][x] = p.get("color", 1)
                        active[y][x] = True
    lines = []
    for y in range(h):
        row = []
        for x in range(w):
            if view[y][x] == 0:
                row.append("⬛")
                continue
            idx = max(1, min(view[y][x], len(TETRIS_COLORS))) - 1
            cell = TETRIS_COLORS[idx]
            # Active falling piece is highlighted for better readability.
            if active[y][x]:
                row.append(cell)
            else:
                row.append(cell)
        lines.append("".join(row))
    text = f"🧱 Тетрис\nОчки: {state['score']}\n\n" + "\n".join(lines)
    if state.get("over"):
        text += "\n\n💀 Игра окончена"
    return text

def tetris_controls(gid, over=False):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("⬅️", callback_data=f"tetris_{gid}_left"),
        types.InlineKeyboardButton("➡️", callback_data=f"tetris_{gid}_right")
    )
    kb.row(types.InlineKeyboardButton("⬇️ Отпустить", callback_data=f"tetris_{gid}_drop"))
    if over:
        kb.row(types.InlineKeyboardButton("🔁 Новая игра", callback_data="tetris_new"))
    return kb

def tetris_retry_after_seconds(err):
    msg = str(err).lower()
    marker = "retry after "
    if marker not in msg:
        return None
    tail = msg.split(marker, 1)[1]
    num = []
    for ch in tail:
        if ch.isdigit():
            num.append(ch)
        else:
            break
    if not num:
        return None
    try:
        return int("".join(num))
    except Exception:
        return None

def tetris_safe_edit(call, gid, st, force=False):
    now = time.time()
    next_edit_at = st.get("next_edit_at", 0.0)
    if (not force) and now < next_edit_at:
        return False
    try:
        text = tetris_render(st)
        kb = tetris_controls(gid, over=st.get("over", False))
        if getattr(call, "inline_message_id", None):
            bot.edit_message_text(
                text,
                inline_message_id=call.inline_message_id,
                reply_markup=kb
            )
        elif getattr(call, "message", None):
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=kb
            )
        else:
            return False
        st["next_edit_at"] = time.time() + 0.12
        return True
    except Exception as e:
        wait = tetris_retry_after_seconds(e)
        if wait:
            st["next_edit_at"] = time.time() + wait + 0.2
            return False
        raise

@bot.inline_handler(lambda q: q.query.lower() == "2048" or q.query.strip() == "2048")
def inline_2048(query):
    # require subscription
    update_user_streak(query.from_user.id, query.from_user.first_name or query.from_user.username or str(query.from_user.id))
    if REQUIRED_CHANNEL and not is_user_subscribed(query.from_user.id):
        return inline_subscription_prompt(query)
    board = [[0]*4 for _ in range(4)]
    board = spawn_tile(board); board = spawn_tile(board)
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("⬆️", callback_data="g2048_new_up"))
    markup.row(types.InlineKeyboardButton("⬅️", callback_data="g2048_new_left"),
               types.InlineKeyboardButton("➡️", callback_data="g2048_new_right"))
    markup.row(types.InlineKeyboardButton("⬇️", callback_data="g2048_new_down"))
    results = [types.InlineQueryResultArticle(
        id=f"g2048_preview_{short_id()}",
        title="🔢 2048",
        description="Нажми стрелку, чтобы начать",
        input_message_content=types.InputTextMessageContent("🔢 2048\nНажми кнопку, чтобы начать."),
        reply_markup=markup
    )]
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

@bot.inline_handler(lambda q: q.query.lower() == "tetris" or q.query.lower() == "тетрис")
def inline_tetris(query):
    update_user_streak(query.from_user.id, query.from_user.first_name or query.from_user.username or str(query.from_user.id))
    if REQUIRED_CHANNEL and not is_user_subscribed(query.from_user.id):
        return inline_subscription_prompt(query)
    gid = short_id()
    results = [types.InlineQueryResultArticle(
        id=f"tetris_preview_{gid}",
        title="🧱 Тетрис",
        description="Кнопки влево/вправо/отпустить",
        input_message_content=types.InputTextMessageContent("🧱 Тетрис\nНажмите «Старт»."),
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("▶️ Старт", callback_data="tetris_new")
        )
    )]
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rps_"))
def rps_callback(call):
    try:
        _, gid, user_choice = call.data.split("_")

        game = rps_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "❌ Игра устарела")
            return

        bot_choice = random.choice(["rock", "paper", "scissors"])

        icons = {
            "rock": "🪨 Камень",
            "paper": "📄 Бумага",
            "scissors": "✂️ Ножницы"
        }

        # определяем результат
        if user_choice == bot_choice:
            result = "🤝 Ничья!"
        elif (
            (user_choice == "rock" and bot_choice == "scissors") or
            (user_choice == "scissors" and bot_choice == "paper") or
            (user_choice == "paper" and bot_choice == "rock")
        ):
            result = "🎉 Ты победил!"
        else:
            result = "😢 Ты проиграл"

        text = (
            "✂️ *Камень • Ножницы • Бумага*\n\n"
            f"👤 Ты: {icons[user_choice]}\n"
            f"🤖 Бот: {icons[bot_choice]}\n\n"
            f"{result}"
        )

        # кнопка "ещё раз"
        new_gid = short_id()
        rps_games[new_gid] = {"uid": call.from_user.id}

        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("🪨 Камень", callback_data=f"rps_{new_gid}_rock"),
            types.InlineKeyboardButton("📄 Бумага", callback_data=f"rps_{new_gid}_paper"),
            types.InlineKeyboardButton("✂️ Ножницы", callback_data=f"rps_{new_gid}_scissors")
        )

        bot.edit_message_text(
            text,
            inline_message_id=call.inline_message_id,
            parse_mode="Markdown",
            reply_markup=kb
        )

        bot.answer_callback_query(call.id)

    except Exception as e:
        print("RPS ERROR:", e)
        bot.answer_callback_query(call.id, "❌ Ошибка игры")

@bot.callback_query_handler(func=lambda c: c.data in ["set_msg", "set_btn", "set_title", "set_gui"])
def sys_set_field(call):
    field = call.data.replace("set_", "")  # msg, btn, title, gui
    uid = call.from_user.id

    system_notify_wait[uid] = field
    bot.answer_callback_query(call.id)
    bot.send_message(uid, f"✏ Введите новое значение для поля: {field}")

@bot.callback_query_handler(func=lambda c: c.data == "tetris_new" or c.data.startswith("tetris_"))
def tetris_callback(call):
    try:
        data = call.data
        if data == "tetris_new":
            gid = short_id()
            games_tetris[gid] = tetris_new_state()
            st = games_tetris[gid]
            ok = tetris_safe_edit(call, gid, st, force=True)
            if not ok:
                bot.answer_callback_query(call.id, "Подождите 1-2 секунды и нажмите Старт снова", show_alert=True)
                return
            bot.answer_callback_query(call.id, "Тетрис запущен")
            return

        parts = data.split("_", 2)  # tetris_<gid>_<action>
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Неверные данные")
            return
        gid = parts[1]
        action = parts[2]
        st = games_tetris.get(gid)
        if not st:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return

        if st.get("over"):
            tetris_safe_edit(call, gid, st, force=True)
            bot.answer_callback_query(call.id, "Игра завершена")
            return

        if action == "left":
            tetris_move(st, -1)
            bot.answer_callback_query(call.id)
        elif action == "right":
            tetris_move(st, 1)
            bot.answer_callback_query(call.id)
        elif action == "drop":
            bot.answer_callback_query(call.id, "Блок отпущен")
            # Fast smooth drop animation (instead of instant teleport).
            if st.get("piece") and not st.get("over"):
                p = st["piece"]
                start_y = p["y"]
                end_y = start_y
                while tetris_can_place(st, p["x"], end_y + 1, p["shape"]):
                    end_y += 1
                dist = end_y - start_y
                if dist > 0:
                    frames = min(4, dist)
                    last_y = p["y"]
                    for i in range(1, frames + 1):
                        ny = start_y + (dist * i) // frames
                        if ny == last_y:
                            continue
                        p["y"] = ny
                        last_y = ny
                        tetris_safe_edit(call, gid, st)
                        time.sleep(0.07)
                tetris_lock_piece(st)
                tetris_clear_lines(st)
                tetris_spawn_piece(st)
        else:
            bot.answer_callback_query(call.id)

        tetris_safe_edit(call, gid, st, force=True)
    except Exception as e:
        print("TETRIS ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка Тетриса")


@bot.callback_query_handler(func=lambda c: c.data.startswith("g2048_"))
def g2048_callback(call):
    try:
        parts = call.data.split("_", 2)
        # g2048_new_left OR g2048_<gid>_left
        if parts[1] == "new":
            gid = short_id()
            board = [[0]*4 for _ in range(4)]
            board = spawn_tile(board); board = spawn_tile(board)
            games_2048[gid] = {"board": board}
            direction = parts[2]
        else:
            gid = parts[1]
            direction = parts[2]
            if gid not in games_2048:
                bot.answer_callback_query(call.id, "Игра не найдена")
                return
            board = games_2048[gid]["board"]

        new_board, moved = move_board(board, direction)
        if moved:
            new_board = spawn_tile(new_board)
        games_2048[gid] = {"board": new_board}

        flat = sum(new_board, [])
        if 2048 in flat:
            bot.edit_message_text("🎉 Вы собрали 2048! Победа!", inline_message_id=call.inline_message_id)
            games_2048.pop(gid, None)
            bot.answer_callback_query(call.id)
            return

        moves_possible = False
        for y in range(4):
            for x in range(4):
                if new_board[y][x] == 0:
                    moves_possible = True
                if x<3 and new_board[y][x] == new_board[y][x+1]:
                    moves_possible = True
                if y<3 and new_board[y][x] == new_board[y+1][x]:
                    moves_possible = True
        if not moves_possible:
            bot.edit_message_text("💀 Game over — ходов нет.", inline_message_id=call.inline_message_id)
            games_2048.pop(gid, None)
            bot.answer_callback_query(call.id)
            return

        # render controls
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("⬆️", callback_data=f"g2048_{gid}_up"))
        markup.row(types.InlineKeyboardButton("⬅️", callback_data=f"g2048_{gid}_left"),
                   types.InlineKeyboardButton("➡️", callback_data=f"g2048_{gid}_right"))
        markup.row(types.InlineKeyboardButton("⬇️", callback_data=f"g2048_{gid}_down"))
        bot.edit_message_text(f"🔢 2048\n\n{render_2048(new_board)}", inline_message_id=call.inline_message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    except Exception as e:
        print("2048 ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка 2048")

# ------------------- Pong (2 players) -------------------
def render_pong_state(state):
    W, H = 11, 7
    field = [["⬛" for _ in range(W)] for _ in range(H)]
    p1x, p2x = 1, 9
    p1pos, p2pos = state["paddles"][0], state["paddles"][1]
    if 0 <= p1pos < H:
        field[p1pos][p1x] = "🟦"
    if 0 <= p2pos < H:
        field[p2pos][p2x] = "🟩"
    bx, by = state["ball"][0], state["ball"][1]
    if 0 <= bx < W and 0 <= by < H:
        field[by][bx] = "⚪"
    return "\n".join("".join(r) for r in field)

@bot.inline_handler(lambda q: q.query.lower() == "pong" or q.query.strip() == "pong" or q.query.lower() == "ping-pong")
def inline_pong(query):
    # require subscription
    update_user_streak(query.from_user.id, query.from_user.first_name or query.from_user.username or str(query.from_user.id))
    if REQUIRED_CHANNEL and not is_user_subscribed(query.from_user.id):
        return inline_subscription_prompt(query)
    gid = short_id()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"pong_{gid}_join"))
    results = [types.InlineQueryResultArticle(
        id=f"pong_preview_{gid}",
        title="🏓 Пинг-понг (2 игрока)",
        description="Нажмите 'Присоединиться' чтобы стать игроком",
        input_message_content=types.InputTextMessageContent("🏓 Пинг-понг\nНажмите 'Присоединиться' чтобы игра началась."),
        reply_markup=markup
    )]
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("pong_"))
def pong_callback(call):
    try:
        parts = call.data.split("_", 2)
        gid = parts[1]
        action = parts[2] if len(parts) > 2 else ""
        state = games_pong.get(gid)
        if action == "join":
            if state is None:
                state = {"players":[None,None], "paddles":[3,3], "ball":[5,3,-1,0], "started":False}
                games_pong[gid] = state
            uid = call.from_user.id
            if uid in state["players"]:
                bot.answer_callback_query(call.id, "Вы уже в игре")
                return
            if state["players"][0] is None:
                state["players"][0] = uid
                msg = "Вы — Игрок 1 (слева)"
            elif state["players"][1] is None:
                state["players"][1] = uid
                msg = "Вы — Игрок 2 (справа)"
            else:
                bot.answer_callback_query(call.id, "Комната полна")
                return
            if state["players"][0] and state["players"][1]:
                markup = types.InlineKeyboardMarkup()
                markup.row(types.InlineKeyboardButton("⬅️", callback_data=f"pong_{gid}_L"),
                           types.InlineKeyboardButton("➡️", callback_data=f"pong_{gid}_R"))
                markup.add(types.InlineKeyboardButton("Старт", callback_data=f"pong_{gid}_start"))
                bot.edit_message_text("Игроки присоединились. Нажмите Старт.", inline_message_id=call.inline_message_id, reply_markup=markup)
            else:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"pong_{gid}_join"))
                bot.edit_message_text(f"{msg}\nОжидаем второго игрока...", inline_message_id=call.inline_message_id, reply_markup=markup)
            bot.answer_callback_query(call.id, msg)
            return

        if state is None:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return
        uid = call.from_user.id
        if uid not in state["players"]:
            bot.answer_callback_query(call.id, "Вы не участник игры")
            return

        if action in ("L","R"):
            pidx = 0 if uid == state["players"][0] else 1
            if action == "L":
                state["paddles"][pidx] = max(0, state["paddles"][pidx] - 1)
            else:
                state["paddles"][pidx] = min(6, state["paddles"][pidx] + 1)
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("⬅️", callback_data=f"pong_{gid}_L"),
                       types.InlineKeyboardButton("➡️", callback_data=f"pong_{gid}_R"))
            bot.edit_message_text(render_pong_state(state), inline_message_id=call.inline_message_id, reply_markup=markup)
            bot.answer_callback_query(call.id, "Paddle moved")
            return

        if action == "start":
            if state["started"]:
                bot.answer_callback_query(call.id, "Игра уже запущена")
                return
            state["started"] = True
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("⬅️", callback_data=f"pong_{gid}_L"),
                       types.InlineKeyboardButton("➡️", callback_data=f"pong_{gid}_R"))
            bot.edit_message_text(render_pong_state(state), inline_message_id=call.inline_message_id, reply_markup=markup)
            bot.answer_callback_query(call.id, "Старт!")
            return

        bot.answer_callback_query(call.id)
    except Exception as e:
        print("PONG ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка Pong")

# ------------------- MILLIONAIRE HANDLER -------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("millionaire_"))
def millionaire_callback(call):
    try:
        _, game_id, index = call.data.split("_")
        index = int(index)
        game = millionaire_games.get(game_id)
        if not game:
            bot.answer_callback_query(call.id, "Игра завершена!")
            return
        question = game["question"]
        answer = question["options"][index]
        if answer == question["answer"]:
            bot.edit_message_text(f"🎉 Правильно! Ответ: {answer}", inline_message_id=call.inline_message_id)
            millionaire_games.pop(game_id, None)
            return
        game["attempts"] -= 1
        if game["attempts"] == 0:
            bot.edit_message_text(f"💀 Вы проиграли!\nПравильный ответ: {question['answer']}", inline_message_id=call.inline_message_id)
            millionaire_games.pop(game_id, None)
            return
        markup = types.InlineKeyboardMarkup()
        for i, option in enumerate(question["options"]):
            markup.add(types.InlineKeyboardButton(option, callback_data=f"millionaire_{game_id}_{i}"))
        bot.edit_message_text(f"💰 {question['question']}\nОсталось попыток: {game['attempts']}", inline_message_id=call.inline_message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    except Exception as e:
        print("MILL ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка Миллионера")

# ------------------- MINESWEEPER -------------------
minesweeper_games = {}

def generate_minesweeper_board(size=5, mines=5):
    board = [[0 for _ in range(size)] for _ in range(size)]
    mine_positions = random.sample([(i, j) for i in range(size) for j in range(size)], mines)
    for x, y in mine_positions:
        board[x][y] = -1
        for dx in [-1,0,1]:
            for dy in [-1,0,1]:
                nx, ny = x+dx, y+dy
                if 0 <= nx < size and 0 <= ny < size and board[nx][ny] != -1:
                    board[nx][ny] += 1
    return board, mine_positions

def generate_minesweeper_board(size=5, mines=5):
    board = [[0 for _ in range(size)] for _ in range(size)]
    mine_positions = random.sample([(i, j) for i in range(size) for j in range(size)], mines)
    for x, y in mine_positions:
        board[x][y] = -1
        for dx in [-1,0,1]:
            for dy in [-1,0,1]:
                nx, ny = x+dx, y+dy
                if 0 <= nx < size and 0 <= ny < size and board[nx][ny] != -1:
                    board[nx][ny] += 1
    return board, mine_positions

# ------------------- HANGMAN (Виселица) -------------------
def render_hangman(game):
    word = game["word"]
    guessed = game["guessed"]
    wrong = game["wrong"]
    attempts = game["attempts"]
    
    # Show guessed letters
    display = ""
    for letter in word:
        if letter.lower() in guessed:
            display += letter.upper() + " "
        else:
            display += "_ "
    
    # Hangman ASCII art
    stages = [
        """
           ------
           |    |
           |
           |
           |
           |
        --------""",
        """
           ------
           |    |
           |    O
           |
           |
           |
        --------""",
        """
           ------
           |    |
           |    O
           |    |
           |
           |
        --------""",
        """
           ------
           |    |
           |    O
           |   \\|
           |
           |
        --------""",
        """
           ------
           |    |
           |    O
           |   \\|/
           |
           |
        --------""",
        """
           ------
           |    |
           |    O
           |   \\|/
           |    |
           |
        --------""",
        """
           ------
           |    |
           |    O
           |   \\|/
           |    |
           |   / \\
        --------"""
    ]
    
    wrong_count = len(wrong)
    stage = min(wrong_count, len(stages) - 1)
    
    text = stages[stage] + "\n\n"
    text += f"Слово: {display}\n"
    text += f"Неправильные: {', '.join(sorted([c.upper() for c in wrong])) if wrong else '(нет)'}\n"
    text += f"Осталось попыток: {attempts - wrong_count}\n"
    
    return text

def render_hangman_state(game):
    word = game["word"]
    guessed = game["guessed"]
    wrong = game["wrong"]
    attempts = game["attempts"]
    wrong_count = len(wrong)
    
    # Show guessed letters
    display = ""
    for letter in word:
        if letter.lower() in guessed:
            display += letter.upper() + " "
        else:
            display += "_ "
    
    # Hangman stages with proper ASCII art
    hangman_stages = [
        # Stage 0 - empty gallows
        "┌─────┐\n│     |\n│\n│\n│\n│\n└─────",
        # Stage 1 - head
        "┌─────┐\n│     |\n│     O\n│\n│\n│\n└─────",
        # Stage 2 - body
        "┌─────┐\n│     |\n│     O\n│     |\n│\n│\n└─────",
        # Stage 3 - left arm
        "┌─────┐\n│     |\n│     O\n│    \\|\n│\n│\n└─────",
        # Stage 4 - right arm
        "┌─────┐\n│     |\n│     O\n│    \\|/\n│\n│\n└─────",
        # Stage 5 - left leg
        "┌─────┐\n│     |\n│     O\n│    \\|/\n│     |\n│\n└─────",
        # Stage 6 - right leg (game over)
        "┌─────┐\n│     |\n│     O\n│    \\|/\n│     |\n│    / \\\n└─────"
    ]
    
    stage = min(wrong_count, len(hangman_stages) - 1)
    text = "```\n" + hangman_stages[stage] + "\n```\n\n"
    text += f"Слово: `{display}`\n"
    text += f"Ошибки: {', '.join(sorted([c.upper() for c in wrong])) if wrong else '-'}\n"
    text += f"Попыток: {attempts - wrong_count}/{attempts}\n"
    
    if game.get("hint_used"):
        text += f"\n💡 Подсказка: {game.get('hint', '')}"
    
    return text

def render_hangman_keyboard(gid, game):
    kb = types.InlineKeyboardMarkup()
    word = game["word"]
    guessed = game["guessed"]
    wrong = game["wrong"]
    attempts = game["attempts"]
    wrong_count = len(wrong)
    hint_used = game.get("hint_used", False)
    
    # Check win/loss
    if wrong_count >= attempts:
        kb.add(types.InlineKeyboardButton("🔄 Новая игра", callback_data="hangman_new"))
        return kb
    
    word_guessed = all(letter.lower() in guessed for letter in word)
    if word_guessed:
        kb.add(types.InlineKeyboardButton("🔄 Новая игра", callback_data="hangman_new"))
        return kb
    
    # Hint button
    if not hint_used:
        kb.add(types.InlineKeyboardButton("💡 Подсказка", callback_data=f"hangman_hint_{gid}"))
    else:
        kb.add(types.InlineKeyboardButton("✓ Подсказка использована", callback_data="none"))
    
    # Create alphabet buttons
    alphabet = "абвгдежзийклмнопрстуфхцчшщъыьэюя"
    row = []
    for letter in alphabet:
        if letter in guessed or letter in wrong:
            # Disabled/already guessed
            row.append(types.InlineKeyboardButton("✓", callback_data="none"))
        else:
            row.append(types.InlineKeyboardButton(letter.upper(), callback_data=f"hangman_{gid}_{letter}"))
        
        if len(row) == 5:
            kb.row(*row)
            row = []
    
    if row:
        kb.row(*row)
    
    kb.add(types.InlineKeyboardButton("🔄 Новая игра", callback_data="hangman_new"))
    return kb

@bot.inline_handler(lambda q: q.query.lower() == "hangman")
def inline_hangman(query):
    update_user_streak(query.from_user.id, query.from_user.first_name or query.from_user.username or str(query.from_user.id))
    if REQUIRED_CHANNEL and not is_user_subscribed(query.from_user.id):
        return inline_subscription_prompt(query)
    
    word = random.choice(HANGMAN_WORDS)
    gid = short_id()
    hangman_games[gid] = {
        "word": word,
        "guessed": set(),
        "wrong": set(),
        "attempts": 6
    }
    
    game = hangman_games[gid]
    
    results = [types.InlineQueryResultArticle(
        id=f"hangman_{gid}",
        title="🔤 Виселица",
        description="Угадайте слово, выбирая буквы!",
        input_message_content=types.InputTextMessageContent(render_hangman_state(game)),
        reply_markup=render_hangman_keyboard(gid, game)
    )]
    
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("hangman_"))
def hangman_callback(call):
    try:
        parts = call.data.split("_")
        action = parts[1]
        
        if action == "new":
            word = random.choice(list(HANGMAN_WORDS.keys()))
            hint = HANGMAN_WORDS[word]
            gid = short_id()
            hangman_games[gid] = {
                "word": word,
                "hint": hint,
                "guessed": set(),
                "wrong": set(),
                "attempts": 6,
                "hint_used": False
            }
            game = hangman_games[gid]
            bot.edit_message_text(
                render_hangman_state(game),
                inline_message_id=call.inline_message_id,
                reply_markup=render_hangman_keyboard(gid, game)
            )
            bot.answer_callback_query(call.id, "Новая игра!")
            return
        
        if action == "hint":
            gid = parts[2]
            game = hangman_games.get(gid)
            if not game:
                bot.answer_callback_query(call.id, "Игра завершена!")
                return
            
            if game.get("hint_used"):
                bot.answer_callback_query(call.id, "Подсказка уже использована!")
                return
            
            game["hint_used"] = True
            bot.edit_message_text(
                render_hangman_state(game),
                inline_message_id=call.inline_message_id,
                reply_markup=render_hangman_keyboard(gid, game)
            )
            bot.answer_callback_query(call.id, f"💡 {game.get('hint', '')}")
            return
        
        # Letter guess
        gid = parts[1]
        letter = parts[2]
        
        game = hangman_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра завершена!")
            return
        
        word = game["word"]
        guessed = game["guessed"]
        wrong = game["wrong"]
        attempts = game["attempts"]
        wrong_count = len(wrong)
        
        # Check win/loss
        if wrong_count >= attempts:
            bot.answer_callback_query(call.id, f"Игра окончена! Слово: {word.upper()}")
            return
        
        word_guessed = all(l.lower() in guessed for l in word)
        if word_guessed:
            bot.answer_callback_query(call.id, "Вы уже выиграли!")
            return
        
        # Process guess
        if letter in guessed or letter in wrong:
            bot.answer_callback_query(call.id, "Вы уже выбрали эту букву!")
            return
        
        if letter.lower() in word.lower():
            guessed.add(letter)
            bot.answer_callback_query(call.id, "✅ Верно!")
        else:
            wrong.add(letter)
            bot.answer_callback_query(call.id, "❌ Неверно!")
        
        # Check win
        word_guessed = all(l.lower() in guessed for l in word)
        
        text = render_hangman_state(game)
        
        if word_guessed:
            text += "\n\n🎉 Вы выиграли! Слово: " + word.upper()
        elif len(wrong) >= attempts:
            text += f"\n\n💀 Вы проиграли! Слово: {word.upper()}"
        
        bot.edit_message_text(
            text,
            inline_message_id=call.inline_message_id,
            reply_markup=render_hangman_keyboard(gid, game)
        )
        
    except Exception as e:
        print("HANGMAN ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка Виселицы")

def render_minesweeper_board(board, revealed):
    size = len(board)
    display = ""
    for i in range(size):
        for j in range(size):
            if (i, j) in revealed:
                if board[i][j] == -1:
                    display += "💣 "
                elif board[i][j] == 0:
                    display += "⬜ "
                else:
                    display += f"{board[i][j]}️⃣ "
            else:
                display += "⬛ "
        display += "\n"
    return display

# ------------------- СЛОВЕСНАЯ ДУЭЛЬ (Игра в слова) -------------------
@bot.inline_handler(lambda q: q.query.lower() == "слова" or q.query.lower() == "word_duel")
def inline_word_duel(query):
    update_user_streak(query.from_user.id, query.from_user.first_name or query.from_user.username or str(query.from_user.id))
    if REQUIRED_CHANNEL and not is_user_subscribed(query.from_user.id):
        return inline_subscription_prompt(query)
    
    gid = short_id()
    first_word = random.choice(WORD_LIST)
    word_games[gid] = {
        "word": first_word,
        "player1": query.from_user.id,
            "p1_name": query.from_user.first_name or "Игрок 1",
        "player2": None,
        "scores": {}
    }
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"wordgame_join_{gid}"))
    
    results = [types.InlineQueryResultArticle(
        id=f"wordgame_{gid}",
        title="📝 Словесная дуэль",
        description="Пишите слова, начиная с последней буквы",
        input_message_content=types.InputTextMessageContent(
            f"📝 *Словесная дуэль*\n\n"
            f"Первое слово: `{first_word.upper()}`\n\n"
            f"Следующий игрок должен написать слово, начинающееся на '{first_word[-1].upper()}'\n\n"
            f"Давайте играть!",
            parse_mode="Markdown"
        ),
        reply_markup=kb
    )]
    
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)
# ------------------- ВИКТОРИНА "КТО БЫСТРЕЕ" -------------------
@bot.inline_handler(lambda q: q.query.lower() == "викторина" or q.query.lower() == "quiz")
def inline_quiz_game(query):
    update_user_streak(query.from_user.id, query.from_user.first_name or query.from_user.username or str(query.from_user.id))
    if REQUIRED_CHANNEL and not is_user_subscribed(query.from_user.id):
        return inline_subscription_prompt(query)
    
    gid = short_id()
    qdata = random.choice(QUIZ_QUESTIONS)
    
    quiz_games[gid] = {
        "question": qdata["q"],
        "answer": qdata["a"].lower(),
        "p1": query.from_user.id,
        "p1_name": query.from_user.first_name or "Игрок 1",
        "p2": None,
        "p1_input": "",
        "p2_input": "",
        "p1_answered": False,
        "p2_answered": False,
        "p1_correct": False,
        "p2_correct": False
    }
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"quizgame_join_{gid}"))
    
    results = [types.InlineQueryResultArticle(
        id=f"quizgame_{gid}",
        title="🧠 Викторина - кто быстрее",
        description="Ответьте на вопрос первым!",
        input_message_content=types.InputTextMessageContent(
            f"🧠 *Викторина*\n\n"
            f"❓ {qdata['q']}\n\n"
            f"Кто ответит первым правильно - выигрывает!",
            parse_mode="Markdown"
        ),
        reply_markup=kb
    )]
    
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

# ------------------- КОМБО-БИТВА -------------------
@bot.inline_handler(lambda q: q.query.lower() == "комбо" or q.query.lower() == "combo")
def inline_combo_battle(query):
    update_user_streak(query.from_user.id, query.from_user.first_name or query.from_user.username or str(query.from_user.id))
    if REQUIRED_CHANNEL and not is_user_subscribed(query.from_user.id):
        return inline_subscription_prompt(query)
    
    gid = short_id()
    combo_games[gid] = {
        "p1": query.from_user.id,
        "p1_name": query.from_user.first_name or "Игрок 1",
        "p2": None,
        "p1_choice": None,
        "p2_choice": None,
        "round": 1,
        "scores": {query.from_user.id: 0},
        "choices": ["⚡ Молния", "🛡️ Щит", "🪨 Камень"]
    }
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"combogame_join_{gid}"))
    
    results = [types.InlineQueryResultArticle(
        id=f"combogame_{gid}",
        title="⚡ Комбо-битва",
        description="Выбирай атаку/защиту и побеждай!",
        input_message_content=types.InputTextMessageContent(
            f"⚡ *Комбо-битва*\n\n"
            f"Правила:\n"
            f"⚡ Молния побеждает 🪨 Камень\n"
            f"🪨 Камень побеждает 🛡️ Щит\n"
            f"🛡️ Щит побеждает ⚡ Молнию\n\n"
            f"Лучший из 3 раундов!",
            parse_mode="Markdown"
        ),
        reply_markup=kb
    )]
    
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

@bot.inline_handler(lambda q: q.query.lower() == "мафия" or q.query.lower() == "mafia")
def inline_mafia_game(query):
    update_user_streak(query.from_user.id, query.from_user.first_name or query.from_user.username or str(query.from_user.id))
    if REQUIRED_CHANNEL and not is_user_subscribed(query.from_user.id):
        return inline_subscription_prompt(query)

    gid = short_id()
    host_id = query.from_user.id
    host_name = query.from_user.first_name or "Игрок 1"
    mafia_games[gid] = {
        "owner": host_id,
        "players": [host_id],
        "alive": [host_id],
        "names": {host_id: host_name},
        "roles": {},
        "phase": "lobby",
        "round": 1,
        "night": {"kill": None, "heal": None, "check": None},
        "votes": {},
        "last_event": "Лобби создано."
    }

    results = [types.InlineQueryResultArticle(
        id=f"mafia_{gid}",
        title="🎭 Мафия",
        description="Нужно 4-10 игроков",
        input_message_content=types.InputTextMessageContent(
            "🎭 Мафия\n\nСоздано лобби. Нажмите «Присоединиться», затем «Старт»."
        ),
        reply_markup=mafia_build_lobby_kb(gid)
    )]
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

# ------------------- CALLBACK HANDLERS ДЛЯ НОВЫХ ИГР -------------------

@bot.callback_query_handler(func=lambda c: c.data.startswith("mafia_"))
def mafia_callback(call):
    try:
        parts = call.data.split("_")
        action = parts[1] if len(parts) > 1 else ""
        gid = parts[2] if len(parts) > 2 else ""
        game = mafia_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return

        uid = call.from_user.id
        uname = call.from_user.first_name or "Игрок"

        if action == "join":
            if game.get("phase") != "lobby":
                bot.answer_callback_query(call.id, "Игра уже началась", show_alert=True)
                return
            if uid not in game["players"]:
                if len(game["players"]) >= 10:
                    bot.answer_callback_query(call.id, "Лобби заполнено (макс. 10)", show_alert=True)
                    return
                game["players"].append(uid)
                game["alive"].append(uid)
            game["names"][uid] = uname
            game["last_event"] = f"Присоединился: {uname}"
            safe_edit_message(call, mafia_render_text(game), reply_markup=mafia_build_lobby_kb(gid))
            bot.answer_callback_query(call.id, "Вы в игре")
            return

        if action == "start":
            if uid != game.get("owner"):
                bot.answer_callback_query(call.id, "Только создатель может начать", show_alert=True)
                return
            if game.get("phase") != "lobby":
                bot.answer_callback_query(call.id, "Игра уже идет")
                return
            n = len(game.get("players", []))
            if n < 4:
                bot.answer_callback_query(call.id, "Нужно минимум 4 игрока", show_alert=True)
                return
            game["roles"] = mafia_assign_roles(game["players"])
            game["phase"] = "night"
            game["last_event"] = "Игра началась. Наступила ночь."
            safe_edit_message(call, mafia_render_text(game), reply_markup=mafia_build_night_kb(gid, game))
            bot.answer_callback_query(call.id, "Старт")
            return

        if action == "role":
            role = game.get("roles", {}).get(uid)
            if not role:
                bot.answer_callback_query(call.id, "Роль пока не назначена", show_alert=True)
                return
            ru = {"mafia": "Мафия", "doctor": "Доктор", "detective": "Детектив", "citizen": "Мирный"}
            bot.answer_callback_query(call.id, f"Ваша роль: {ru.get(role, role)}", show_alert=True)
            return

        if uid not in game.get("alive", []):
            bot.answer_callback_query(call.id, "Вы выбыли из игры", show_alert=True)
            return

        if action in ("nkill", "heal", "check"):
            if game.get("phase") != "night":
                bot.answer_callback_query(call.id, "Сейчас не ночь", show_alert=True)
                return
            if len(parts) < 4:
                bot.answer_callback_query(call.id, "Неверные данные")
                return
            target = int(parts[3])
            if target not in game.get("alive", []):
                bot.answer_callback_query(call.id, "Цель недоступна", show_alert=True)
                return
            role = game["roles"].get(uid)
            if action == "nkill":
                if role != "mafia":
                    bot.answer_callback_query(call.id, "Это действие доступно только мафии", show_alert=True)
                    return
                if game["roles"].get(target) == "mafia":
                    bot.answer_callback_query(call.id, "Нельзя выбрать мафию", show_alert=True)
                    return
                game["night"]["kill"] = target
                bot.answer_callback_query(call.id, f"Цель выбрана: {game['names'].get(target,'Игрок')}")
            elif action == "heal":
                if role != "doctor":
                    bot.answer_callback_query(call.id, "Это действие доступно только доктору", show_alert=True)
                    return
                game["night"]["heal"] = target
                bot.answer_callback_query(call.id, f"Лечение: {game['names'].get(target,'Игрок')}")
            else:
                if role != "detective":
                    bot.answer_callback_query(call.id, "Это действие доступно только детективу", show_alert=True)
                    return
                game["night"]["check"] = target
                is_mafia = game["roles"].get(target) == "mafia"
                res = "мафия" if is_mafia else "не мафия"
                bot.answer_callback_query(call.id, f"{game['names'].get(target,'Игрок')} — {res}", show_alert=True)

            need_kill = any(game["roles"].get(x) == "mafia" for x in game["alive"])
            need_heal = any(game["roles"].get(x) == "doctor" for x in game["alive"])
            need_check = any(game["roles"].get(x) == "detective" for x in game["alive"])
            ready = (not need_kill or game["night"].get("kill") is not None) and \
                    (not need_heal or game["night"].get("heal") is not None) and \
                    (not need_check or game["night"].get("check") is not None)
            if ready:
                mafia_resolve_night(game)
                winner = mafia_check_winner(game)
                if winner:
                    game["phase"] = "ended"
                    game["last_event"] += "\n🏁 Победили " + ("мирные" if winner == "citizens" else "мафия")
                    safe_edit_message(call, mafia_render_text(game))
                else:
                    safe_edit_message(call, mafia_render_text(game), reply_markup=mafia_build_day_kb(gid))
            return

        if action == "vote":
            if game.get("phase") != "day":
                bot.answer_callback_query(call.id, "Сейчас не день", show_alert=True)
                return
            if len(parts) < 4:
                bot.answer_callback_query(call.id, "Неверные данные")
                return
            target = int(parts[3])
            if target not in game.get("alive", []):
                bot.answer_callback_query(call.id, "Цель недоступна", show_alert=True)
                return
            game["votes"][uid] = target
            bot.answer_callback_query(call.id, f"Голос принят: {game['names'].get(target,'Игрок')}")
            if len(game["votes"]) >= len(game.get("alive", [])):
                mafia_resolve_day(game)
                winner = mafia_check_winner(game)
                if winner:
                    game["phase"] = "ended"
                    game["last_event"] += "\n🏁 Победили " + ("мирные" if winner == "citizens" else "мафия")
                    safe_edit_message(call, mafia_render_text(game))
                else:
                    safe_edit_message(call, mafia_render_text(game), reply_markup=mafia_build_night_kb(gid, game))
            return

        bot.answer_callback_query(call.id)
    except Exception as e:
        print("MAFIA CALLBACK ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка Мафии")

# Словесная дуэль - присоединение
@bot.callback_query_handler(func=lambda c: c.data.startswith("wordgame_join_"))
def wordgame_join(call):
    try:
        gid = call.data.split("_")[2]
        game = word_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return
        
        if game["player2"] is None:
            game["player2"] = call.from_user.id
            game["p2_name"] = call.from_user.first_name or "Игрок 2"
            game["scores"][call.from_user.id] = 0
            game["scores"][game["player1"]] = 0
            
            text = f"📝 *Словесная дуэль*\n\n"
            text += f"Слово: `{game['word'].upper()}`\n"
            text += f"{game.get('p1_name', 'Игрок 1')}\n"
            text += f"{game.get('p2_name', 'Игрок 2')}\n\n"
            text += f"⏳ Ожидание начала игры...\n"
            text += f"Следующее слово должно начинаться на '{game['word'][-1].upper()}'\n\n"
            text += f"Оба игрока готовы! Поиграем!"
            
            # Клавиатура для ввода
            kb = types.InlineKeyboardMarkup()
            row = []
            for i, letter in enumerate("абвгдежзийклмнопрстуфхцчшщъыьэюя"):
                if i % 5 == 0 and i > 0:
                    kb.row(*row)
                    row = []
                row.append(types.InlineKeyboardButton(letter.upper(), callback_data=f"word_{gid}_{letter}"))
            if row:
                kb.row(*row)
            kb.add(types.InlineKeyboardButton("✅ Отправить слово", callback_data=f"word_{gid}_submit"))
            
            bot.edit_message_text(text, inline_message_id=call.inline_message_id, parse_mode="Markdown", reply_markup=kb)
            bot.answer_callback_query(call.id, "✅ Вы присоединились!")
        else:
            bot.answer_callback_query(call.id, "Игрок уже присоединился", show_alert=True)
    except Exception as e:
        print("WORDGAME JOIN ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")

# Опиши эмодзи - присоединение
@bot.callback_query_handler(func=lambda c: c.data.startswith("emojigame_join_"))
def emojigame_join(call):
    try:
        gid = call.data.split("_")[2]
        game = emoji_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return
        
        if game["p2"] is None:
            game["p2"] = call.from_user.id
            game["p2_name"] = call.from_user.first_name or "Игрок 2"
            game["scores"][call.from_user.id] = 0
            game["scores"][game["p1"]] = 0
            
            text = f"🎨 *Опиши эмодзи*\n\n"
            text += f"⏳ Ожидание второго игрока...\n\n"
            text += f"{game.get('p1_name', 'Игрок 1')} (описывает)\n"
            text += f"{game.get('p2_name', 'Игрок 2')} (угадывает)\n\n"
            text += f"Слово: `{game['word'].upper()}`\n\n"
            text += f"{game.get('p1_name', 'Игрок 1')} описывает слово эмодзи, {game.get('p2_name', 'Игрок 2')} угадывает!"
            
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("⏭️ Готово к описанию", callback_data=f"emoji_{gid}_ready"))
            
            bot.edit_message_text(text, inline_message_id=call.inline_message_id, parse_mode="Markdown", reply_markup=kb)
            bot.answer_callback_query(call.id, "✅ Вы присоединились!")
        else:
            bot.answer_callback_query(call.id, "Игрок уже присоединился", show_alert=True)
    except Exception as e:
        print("EMOJIGAME JOIN ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")

# Викторина - присоединение
@bot.callback_query_handler(func=lambda c: c.data.startswith("quizgame_join_"))
def quizgame_join(call):
    try:
        gid = call.data.split("_")[2]
        game = quiz_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return

        if "players" not in game:
            p1 = game.get("p1")
            p2 = game.get("p2")
            players = []
            if p1 is not None:
                players.append(p1)
            if p2 is not None and p2 not in players:
                players.append(p2)
            game["players"] = players
            game["names"] = game.get("names", {})
            if p1 is not None:
                game["names"].setdefault(p1, game.get("p1_name", "Игрок 1"))
            if p2 is not None:
                game["names"].setdefault(p2, game.get("p2_name", "Игрок 2"))
            game["inputs"] = game.get("inputs", {})
            game["answered"] = game.get("answered", {})
            game["correct"] = game.get("correct", {})
            game["max_players"] = 4
            game["started"] = len(players) >= 2
            game["locked"] = False
            game["owner"] = players[0] if players else None

        players = game["players"]
        names = game["names"]
        max_players = game.get("max_players", 4)
        owner = game.get("owner")

        if call.from_user.id in players:
            if not game.get("started"):
                p1_name = names.get(players[0], "Игрок 1")
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"quizgame_join_{gid}"))
                if owner == call.from_user.id:
                    kb.add(types.InlineKeyboardButton("▶️ Старт", callback_data=f"quizgame_start_{gid}"))
                text = f"🧠 *Викторина*\n\n"
                text += f"❓ {game['question']}\n\n"
                text += f"⏳ Ожидание игроков... (2-4)\n\n"
                text += f"{p1_name}\n\n"
                text += f"Нажмите «Присоединиться», чтобы начать игру."
                safe_edit_message(call, text, reply_markup=kb, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "Ожидаем игроков", show_alert=False)
            return

        if game.get("locked"):
            bot.answer_callback_query(call.id, "Игра уже началась", show_alert=True)
            return

        if len(players) >= max_players:
            bot.answer_callback_query(call.id, "Игра заполнена (максимум 4)", show_alert=False)
            return

        uid = call.from_user.id
        players.append(uid)
        names[uid] = call.from_user.first_name or f"Игрок {len(players)}"
        game["inputs"].setdefault(uid, "")
        game["answered"].setdefault(uid, False)
        game["correct"].setdefault(uid, False)

        if len(players) >= 2:
            game["started"] = True

        text = f"🧠 *Викторина*\n\n"
        text += f"❓ {game['question']}\n\n"
        text += f"Игроки ({len(players)}/{max_players}):\n\n"
        for pid in players:
            name = names.get(pid, "Игрок")
            status = "✅ ответ готов" if game["answered"].get(pid) else "⌨️ вводит" if game.get("started") else "⏳ ждёт"
            text += f"- {name}: {status}\n\n"
        text += "\nНабирайте ответ на клавиатуре ниже." if game.get("started") else "\nЖдём ещё игроков..."

        kb = types.InlineKeyboardMarkup()
        if game.get("started"):
            alphabet = "абвгдеёжзийклмнопрстуфхцчшщъyэюя".replace('y','й')
            row = []
            for i, letter in enumerate(alphabet):
                if i % 6 == 0 and i > 0:
                    kb.row(*row)
                    row = []
                row.append(types.InlineKeyboardButton(letter.upper(), callback_data=f"quiz_{gid}_{letter}"))
            if row:
                kb.row(*row)
            digits_row = [types.InlineKeyboardButton(str(i), callback_data=f"quiz_{gid}_{i}") for i in range(10)]
            kb.row(*digits_row)
            kb.row(types.InlineKeyboardButton("⌫", callback_data=f"quiz_{gid}_back"),
                   types.InlineKeyboardButton("✅ Готово", callback_data=f"quiz_{gid}_submit"))
        else:
            kb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"quizgame_join_{gid}"))
            if owner == call.from_user.id:
                kb.add(types.InlineKeyboardButton("▶️ Старт", callback_data=f"quizgame_start_{gid}"))

        safe_edit_message(call, text, reply_markup=kb, parse_mode="Markdown")
        bot.answer_callback_query(call.id, "✅ Вы присоединились!")
    except Exception as e:
        print("QUIZGAME JOIN ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")

@bot.callback_query_handler(func=lambda c: c.data.startswith("quizgame_start_"))
def quizgame_start(call):
    try:
        gid = call.data.split("_")[2]
        game = quiz_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return
        owner = game.get("owner")
        if call.from_user.id != owner:
            bot.answer_callback_query(call.id, "Только создатель может начать", show_alert=True)
            return
        if len(game.get("players", [])) < 2:
            bot.answer_callback_query(call.id, "Нужно минимум 2 игрока", show_alert=False)
            return
        game["started"] = True

        players = game["players"]
        names = game["names"]
        text = f"🧠 *Викторина*\n\n"
        text += f"❓ {game['question']}\n\n"
        text += f"Игроки ({len(players)}/{game.get('max_players',4)}):\n\n"
        for pid in players:
            name = names.get(pid, "Игрок")
            status = "✅ ответ готов" if game["answered"].get(pid) else "⌨️ вводит"
            text += f"- {name}: {status}\n\n"
        text += "\nНабирайте ответ на клавиатуре ниже."

        kb = types.InlineKeyboardMarkup()
        alphabet = "абвгдеёжзийклмнопрстуфхцчшщъyэюя".replace('y','й')
        row = []
        for i, letter in enumerate(alphabet):
            if i % 6 == 0 and i > 0:
                kb.row(*row)
                row = []
            row.append(types.InlineKeyboardButton(letter.upper(), callback_data=f"quiz_{gid}_{letter}"))
        if row:
            kb.row(*row)
        digits_row = [types.InlineKeyboardButton(str(i), callback_data=f"quiz_{gid}_{i}") for i in range(10)]
        kb.row(*digits_row)
        kb.row(types.InlineKeyboardButton("⌫", callback_data=f"quiz_{gid}_back"),
               types.InlineKeyboardButton("✅ Готово", callback_data=f"quiz_{gid}_submit"))

        safe_edit_message(call, text, reply_markup=kb, parse_mode="Markdown")
        bot.answer_callback_query(call.id, "Игра началась")
    except Exception as e:
        print("QUIZGAME START ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")

# Викторина - ввод/отправка ответа
@bot.callback_query_handler(func=lambda c: c.data.startswith("quiz_"))
def quiz_input(call):
    try:
        parts = call.data.split("_", 2)
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Неверные данные")
            return
        gid = parts[1]
        token = parts[2]
        game = quiz_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return

        if "players" not in game:
            p1 = game.get("p1")
            p2 = game.get("p2")
            players = []
            if p1 is not None:
                players.append(p1)
            if p2 is not None and p2 not in players:
                players.append(p2)
            game["players"] = players
            game["names"] = game.get("names", {})
            if p1 is not None:
                game["names"].setdefault(p1, game.get("p1_name", "Игрок 1"))
            if p2 is not None:
                game["names"].setdefault(p2, game.get("p2_name", "Игрок 2"))
            game["inputs"] = game.get("inputs", {})
            game["answered"] = game.get("answered", {})
            game["correct"] = game.get("correct", {})
            game["max_players"] = 4
            game["started"] = len(players) >= 2
            game["locked"] = False
            game["owner"] = players[0] if players else None

        players = game["players"]
        names = game["names"]

        uid = call.from_user.id
        if uid not in players:
            bot.answer_callback_query(call.id, "Вы не участник этой игры", show_alert=True)
            return

        if not game.get("started"):
            bot.answer_callback_query(call.id, "Ждём игроков...", show_alert=False)
            return

        if game["answered"].get(uid):
            bot.answer_callback_query(call.id, "Вы уже ответили", show_alert=False)
            return

        if token == "submit":
            answer = (game["inputs"].get(uid, "") or "").strip().lower()
            if not answer:
                bot.answer_callback_query(call.id, "Введите ответ", show_alert=False)
                return

            game["locked"] = True
            game["answered"][uid] = True
            game["correct"][uid] = (answer == game.get("answer", "").lower())

            if game["correct"][uid]:
                winner = names.get(uid, "Игрок")
                text = f"🎉 {winner} выиграл!\n\n"
                text += f"❓ {game['question']}\n\n"
                text += f"✅ Ответ: {game['answer']}"
                safe_edit_message(call, text, parse_mode="Markdown")
                quiz_games.pop(gid, None)
                return

            if all(game["answered"].get(p, False) for p in players):
                text = f"🤷 Никто не угадал.\n\n"
                text += f"❓ {game['question']}\n\n"
                text += f"✅ Ответ: {game['answer']}"
                safe_edit_message(call, text, parse_mode="Markdown")
                quiz_games.pop(gid, None)
                return

            bot.answer_callback_query(call.id, "Неверно. Ждём ответы остальных.")
            return

        if token == "back":
            cur = game["inputs"].get(uid, "")
            game["inputs"][uid] = cur[:-1]
        else:
            cur = game["inputs"].get(uid, "")
            if len(cur) >= 32:
                bot.answer_callback_query(call.id, "Слишком длинный ответ", show_alert=False)
                return
            game["inputs"][uid] = cur + token

        text = f"🧠 *Викторина*\n\n"
        text += f"❓ {game['question']}\n\n"
        text += f"Игроки ({len(players)}/{game.get('max_players',4)}):\n\n"
        for pid in players:
            name = names.get(pid, "Игрок")
            status = "✅ ответ готов" if game["answered"].get(pid) else "⌨️ вводит"
            text += f"- {name}: {status}\n\n"
        text += "\nНажмите «Готово», когда закончите."

        kb = types.InlineKeyboardMarkup()
        alphabet = "абвгдеёжзийклмнопрстуфхцчшщъyэюя".replace('y','й')
        row = []
        for i, letter in enumerate(alphabet):
            if i % 6 == 0 and i > 0:
                kb.row(*row)
                row = []
            row.append(types.InlineKeyboardButton(letter.upper(), callback_data=f"quiz_{gid}_{letter}"))
        if row:
            kb.row(*row)
        digits_row = [types.InlineKeyboardButton(str(i), callback_data=f"quiz_{gid}_{i}") for i in range(10)]
        kb.row(*digits_row)
        kb.row(types.InlineKeyboardButton("⌫", callback_data=f"quiz_{gid}_back"),
               types.InlineKeyboardButton("✅ Готово", callback_data=f"quiz_{gid}_submit"))

        safe_edit_message(call, text, reply_markup=kb, parse_mode="Markdown")
        bot.answer_callback_query(call.id, f"Ваш ответ: {game['inputs'][uid]}")
    except Exception as e:
        print("QUIZ INPUT ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")

# Комбо-битва - присоединение
@bot.callback_query_handler(func=lambda c: c.data.startswith("combogame_join_"))
def combogame_join(call):
    try:
        gid = call.data.split("_")[2]
        game = combo_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return
        
        if call.from_user.id == game.get("p1"):
            p1_name = game.get("p1_name", "Игрок 1")
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"combogame_join_{gid}"))
            text = f"⚡ *Комбо-битва*\n\n"
            text += f"⏳ Ожидание второго игрока...\n\n"
            text += f"{p1_name}\n\n"
            text += f"Нажмите «Присоединиться», чтобы начать игру."
            safe_edit_message(call, text, reply_markup=kb, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "Ожидаем второго игрока", show_alert=False)
            return

        if game["p2"] is None:
            game["p2"] = call.from_user.id
            game["p2_name"] = call.from_user.first_name or "Игрок 2"
            game["scores"][call.from_user.id] = 0
            
            kb = types.InlineKeyboardMarkup()
            kb.row(
                types.InlineKeyboardButton("⚡ Молния", callback_data=f"combo_{gid}_lightning"),
                types.InlineKeyboardButton("🛡️ Щит", callback_data=f"combo_{gid}_shield"),
                types.InlineKeyboardButton("🪨 Камень", callback_data=f"combo_{gid}_rock")
            )
            
            p1_name = game.get("p1_name", "Игрок 1")
            p2_name = game.get("p2_name", "Игрок 2")
            text = f"⚡ *Комбо-битва*\n\n"
            text += f"✅ Оба игрока готовы!\n\n"
            text += f"{p1_name}\n"
            text += f"{p2_name}\n\n"
            text += f"Раунд 1 из 3\n\n"
            text += f"Правила:\n"
            text += f"⚡ > 🪨\n"
            text += f"🪨 > 🛡️\n"
            text += f"🛡️ > ⚡\n\n"
            text += f"{p1_name} выбирает атаку:"
            
            bot.edit_message_text(text, inline_message_id=call.inline_message_id, parse_mode="Markdown", reply_markup=kb)
            bot.answer_callback_query(call.id, "✅ Вы присоединились!")
        else:
            bot.answer_callback_query(call.id, "Игрок уже присоединился", show_alert=False)
    except Exception as e:
        print("COMBOGAME JOIN ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")

# Комбо-битва - выбор атаки
@bot.callback_query_handler(func=lambda c: c.data.startswith("combo_"))
def combo_choice(call):
    try:
        parts = call.data.split("_")
        gid = parts[1]
        choice_map = {"lightning": "⚡ Молния", "shield": "🛡️ Щит", "rock": "🪨 Камень"}
        choice = parts[2]
        
        game = combo_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return
        
        uid = call.from_user.id
        p1_name = game.get("p1_name", "Игрок 1")
        p2_name = game.get("p2_name", "Игрок 2")
        
        # Определяем кто игрок
        if uid == game["p1"]:
            if game.get("p2") is None:
                bot.answer_callback_query(call.id, "Ждём второго игрока", show_alert=False)
                return
            if game["p1_choice"] is None:
                game["p1_choice"] = choice
                bot.answer_callback_query(call.id, f"✅ Вы выбрали: {choice_map.get(choice, choice)}")

                # Если оба игрока выбрали
                if game["p2_choice"] is not None:
                    # Определяем победителя
                    rules = {
                        "lightning": {"rock": True, "shield": False},
                        "shield": {"lightning": True, "rock": False},
                        "rock": {"shield": True, "lightning": False}
                    }
                    
                    p1_win = rules[game["p1_choice"]].get(game["p2_choice"], False) if game["p1_choice"] != game["p2_choice"] else None
                    
                    if p1_win is None:  # Ничья
                        result = "🤝 Ничья!"
                    elif p1_win:
                        result = f"🎉 {p1_name} выигрывает раунд!"
                        game["scores"][game["p1"]] += 1
                    else:
                        result = f"🎉 {p2_name} выигрывает раунд!"
                        game["scores"][game["p2"]] += 1
                    
                    text = f"⚡ *Результат раунда {game['round']} из 3*\n\n"
                    text += f"{p1_name}: {choice_map.get(game['p1_choice'], game['p1_choice'])}\n"
                    text += f"{p2_name}: {choice_map.get(game['p2_choice'], game['p2_choice'])}\n\n"
                    text += f"{result}\n\n"
                    text += f"Счёт: {p1_name}: {game['scores'].get(game['p1'], 0)} - {p2_name}: {game['scores'].get(game['p2'], 0)}"
                    
                    if game["round"] < 3:
                        game["round"] += 1
                        game["p1_choice"] = None
                        game["p2_choice"] = None
                        kb = types.InlineKeyboardMarkup()
                        kb.row(
                            types.InlineKeyboardButton("⚡ Молния", callback_data=f"combo_{gid}_lightning"),
                            types.InlineKeyboardButton("🛡️ Щит", callback_data=f"combo_{gid}_shield"),
                            types.InlineKeyboardButton("🪨 Камень", callback_data=f"combo_{gid}_rock")
                        )
                        text += f"\n\nРаунд {game['round']} - Выбирайте:"
                        bot.edit_message_text(text, inline_message_id=call.inline_message_id, parse_mode="Markdown", reply_markup=kb)
                    else:
                        p1_score = game["scores"].get(game["p1"], 0)
                        p2_score = game["scores"].get(game["p2"], 0)
                        if p1_score > p2_score:
                            text += f"\n\n🏆 {p1_name} победил!"
                        elif p2_score > p1_score:
                            text += f"\n\n🏆 {p2_name} победил!"
                        else:
                            text += f"\n\n🤝 Ничья!"
                        bot.edit_message_text(text, inline_message_id=call.inline_message_id, parse_mode="Markdown")
                else:
                    # Ждём второго игрока
                    text = f"⚡ *Комбо-битва*\n\n"
                    text += f"Раунд {game['round']} из 3\n\n"
                    text += f"{p1_name}: ✅ выбрал\n"
                    text += f"{p2_name}: ⏳ ждём выбор\n\n"
                    text += f"{p2_name} выбирает атаку:"
                    kb = types.InlineKeyboardMarkup()
                    kb.row(
                        types.InlineKeyboardButton("⚡ Молния", callback_data=f"combo_{gid}_lightning"),
                        types.InlineKeyboardButton("🛡️ Щит", callback_data=f"combo_{gid}_shield"),
                        types.InlineKeyboardButton("🪨 Камень", callback_data=f"combo_{gid}_rock")
                    )
                    bot.edit_message_text(text, inline_message_id=call.inline_message_id, parse_mode="Markdown", reply_markup=kb)
            else:
                bot.answer_callback_query(call.id, "Вы уже выбрали!", show_alert=False)
        
        elif uid == game["p2"]:
            if game.get("p1") is None:
                bot.answer_callback_query(call.id, "Ждём первого игрока", show_alert=False)
                return
            if game["p2_choice"] is None:
                game["p2_choice"] = choice
                bot.answer_callback_query(call.id, f"✅ Вы выбрали: {choice_map.get(choice, choice)}")

                # Если оба игрока выбрали
                if game["p1_choice"] is not None:
                    rules = {
                        "lightning": {"rock": True, "shield": False},
                        "shield": {"lightning": True, "rock": False},
                        "rock": {"shield": True, "lightning": False}
                    }
                    
                    p1_win = rules[game["p1_choice"]].get(game["p2_choice"], False) if game["p1_choice"] != game["p2_choice"] else None
                    
                    if p1_win is None:
                        result = "🤝 Ничья!"
                    elif p1_win:
                        result = f"🎉 {p1_name} выигрывает раунд!"
                        game["scores"][game["p1"]] += 1
                    else:
                        result = f"🎉 {p2_name} выигрывает раунд!"
                        game["scores"][game["p2"]] += 1
                    
                    text = f"⚡ *Результат раунда {game['round']} из 3*\n\n"
                    text += f"{p1_name}: {choice_map.get(game['p1_choice'], game['p1_choice'])}\n"
                    text += f"{p2_name}: {choice_map.get(game['p2_choice'], game['p2_choice'])}\n\n"
                    text += f"{result}\n\n"
                    text += f"Счёт: {p1_name}: {game['scores'].get(game['p1'], 0)} - {p2_name}: {game['scores'].get(game['p2'], 0)}"
                    
                    if game["round"] < 3:
                        game["round"] += 1
                        game["p1_choice"] = None
                        game["p2_choice"] = None
                        kb = types.InlineKeyboardMarkup()
                        kb.row(
                            types.InlineKeyboardButton("⚡ Молния", callback_data=f"combo_{gid}_lightning"),
                            types.InlineKeyboardButton("🛡️ Щит", callback_data=f"combo_{gid}_shield"),
                            types.InlineKeyboardButton("🪨 Камень", callback_data=f"combo_{gid}_rock")
                        )
                        text += f"\n\nРаунд {game['round']} - Выбирайте:"
                        bot.edit_message_text(text, inline_message_id=call.inline_message_id, parse_mode="Markdown", reply_markup=kb)
                    else:
                        p1_score = game["scores"].get(game["p1"], 0)
                        p2_score = game["scores"].get(game["p2"], 0)
                        if p1_score > p2_score:
                            text += f"\n\n🏆 {p1_name} победил!"
                        elif p2_score > p1_score:
                            text += f"\n\n🏆 {p2_name} победил!"
                        else:
                            text += f"\n\n🤝 Ничья!"
                        bot.edit_message_text(text, inline_message_id=call.inline_message_id, parse_mode="Markdown")
                else:
                    # Ждём первого игрока
                    text = f"⚡ *Комбо-битва*\n\n"
                    text += f"Раунд {game['round']} из 3\n\n"
                    text += f"{p1_name}: ⏳ ждём выбор\n"
                    text += f"{p2_name}: ✅ выбрал\n\n"
                    text += f"{p1_name} выбирает атаку:"
                    kb = types.InlineKeyboardMarkup()
                    kb.row(
                        types.InlineKeyboardButton("⚡ Молния", callback_data=f"combo_{gid}_lightning"),
                        types.InlineKeyboardButton("🛡️ Щит", callback_data=f"combo_{gid}_shield"),
                        types.InlineKeyboardButton("🪨 Камень", callback_data=f"combo_{gid}_rock")
                    )
                    bot.edit_message_text(text, inline_message_id=call.inline_message_id, parse_mode="Markdown", reply_markup=kb)
            else:
                bot.answer_callback_query(call.id, "Вы уже выбрали!", show_alert=False)
    except Exception as e:
        print("COMBO CHOICE ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")

@bot.inline_handler(lambda q: q.query.lower() == "minesweeper")
def inline_minesweeper(query):
    # require subscription
    update_user_streak(query.from_user.id, query.from_user.first_name or query.from_user.username or str(query.from_user.id))
    if REQUIRED_CHANNEL and not is_user_subscribed(query.from_user.id):
        return inline_subscription_prompt(query)
    size = 5
    mines = 5
    board, mine_positions = generate_minesweeper_board(size, mines)
    gid = short_id()
    minesweeper_games[gid] = {"board": board, "revealed": set(), "mine_positions": mine_positions}
    markup = types.InlineKeyboardMarkup()
    for i in range(size):
        row = []
        for j in range(size):
            row.append(types.InlineKeyboardButton("⬛", callback_data=f"minesweeper_{gid}_{i}_{j}"))
        markup.row(*row)
    results = [types.InlineQueryResultArticle(
        id=f"minesweeper_{gid}",
        title="💣 Сапёр",
        description="Откройте клетки, избегая мин!",
        input_message_content=types.InputTextMessageContent(f"💣 Сапёр\n{render_minesweeper_board(board, set())}"),
        reply_markup=markup
    )]
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("minesweeper_"))
def minesweeper_callback(call):
    try:
        _, gid, x, y = call.data.split("_")
        x, y = int(x), int(y)
        game = minesweeper_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра завершена!")
            return
        board = game["board"]; revealed = game["revealed"]; mine_positions = game["mine_positions"]
        if (x, y) in mine_positions:
            bot.edit_message_text(f"💥 Вы наткнулись на мину!\n\n{render_minesweeper_board(board, revealed.union(mine_positions))}", inline_message_id=call.inline_message_id)
            minesweeper_games.pop(gid, None)
            bot.answer_callback_query(call.id)
            return
        revealed.add((x, y))
        if len(revealed) == len(board)*len(board) - len(mine_positions):
            bot.edit_message_text(f"🎉 Вы выиграли!\n\n{render_minesweeper_board(board, revealed.union(mine_positions))}", inline_message_id=call.inline_message_id)
            minesweeper_games.pop(gid, None)
            bot.answer_callback_query(call.id)
            return
        markup = types.InlineKeyboardMarkup()
        for i in range(len(board)):
            row = []
            for j in range(len(board)):
                if (i, j) in revealed:
                    row.append(types.InlineKeyboardButton("⬜", callback_data="none"))
                else:
                    row.append(types.InlineKeyboardButton("⬛", callback_data=f"minesweeper_{gid}_{i}_{j}"))
            markup.row(*row)
        bot.edit_message_text(f"💣 Сапёр\n{render_minesweeper_board(board, revealed)}", inline_message_id=call.inline_message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    except Exception as e:
        print("MINE ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка сапёра")

# ------------------- TELOS OS CALLBACKS -------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("os_"))
def telos_callbacks(call):
    try:
        data = call.data
        uid = call.from_user.id
        st = _telos_get_state(uid)

        if data == "os_back":
            safe_edit_message(call, _telos_home_text(uid), reply_markup=telos_main_menu(), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data == "os_boot":
            st["booted"] = True
            _telos_save_state(uid, st)
            safe_edit_message(call, _telos_home_text(uid), reply_markup=telos_main_menu(), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if not st.get("booted", True):
            boot_kb = types.InlineKeyboardMarkup()
            boot_kb.add(types.InlineKeyboardButton("▶️ Запустить", callback_data="os_boot"))
            safe_edit_message(call, "⏻ *TELOS выключен*\nНажмите Запустить.", reply_markup=boot_kb, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data == "os_files":
            files = st.get("files", [])
            body = "\n".join([f"{i+1}. `{x.get('name', 'file.txt')}`" for i, x in enumerate(files[:10])]) if files else "(пусто)"
            safe_edit_message(call, "*Файлы*\n\n" + body, reply_markup=_telos_files_kb(st), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data == "os_files_new":
            telos_input_wait[uid] = {"action": "new_file"}
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "Отправьте файл в формате: `имя.txt | содержимое`", parse_mode="Markdown")
            return

        if data == "os_files_clear":
            st["files"] = []
            _telos_save_state(uid, st)
            safe_edit_message(call, "*Файлы*\n\n(пусто)", reply_markup=_telos_files_kb(st), parse_mode="Markdown")
            bot.answer_callback_query(call.id, "Файлы очищены")
            return

        if data.startswith("os_file_"):
            idx = int(data.split("_")[2])
            files = st.get("files", [])
            if idx < 0 or idx >= len(files):
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)
                return
            fobj = files[idx]
            safe_edit_message(call, f"*{fobj.get('name', 'file.txt')}*\n\n{fobj.get('content', '(пусто)')[:1500]}", reply_markup=_telos_files_kb(st), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data == "os_notes":
            notes = st.get("notes", [])
            body = "\n".join([f"{i+1}. {str(x)[:80]}" for i, x in enumerate(notes[:10])]) if notes else "(нет заметок)"
            safe_edit_message(call, "*Заметки*\n\n" + body, reply_markup=_telos_notes_kb(st), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data == "os_notes_add":
            telos_input_wait[uid] = {"action": "new_note"}
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "Введите текст заметки:")
            return

        if data == "os_notes_clear":
            st["notes"] = []
            _telos_save_state(uid, st)
            safe_edit_message(call, "*Заметки*\n\n(нет заметок)", reply_markup=_telos_notes_kb(st), parse_mode="Markdown")
            bot.answer_callback_query(call.id, "Заметки очищены")
            return

        if data.startswith("os_note_"):
            idx = int(data.split("_")[2])
            notes = st.get("notes", [])
            if idx < 0 or idx >= len(notes):
                bot.answer_callback_query(call.id, "Заметка не найдена", show_alert=True)
                return
            safe_edit_message(call, f"*Заметка #{idx+1}*\n\n{str(notes[idx])[:1500]}", reply_markup=_telos_notes_kb(st), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data == "os_games":
            safe_edit_message(call, "*Игры внутри TELOS*\nВыберите игру:", reply_markup=_telos_games_kb(), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data == "os_game_coin":
            bot.answer_callback_query(call.id, random.choice(["🪙 Орёл", "🪙 Решка"]), show_alert=True)
            return

        if data == "os_game_slot":
            symbols = ["🍒", "🍋", "🍉", "⭐", "💎", "7️⃣"]
            roll = " | ".join([random.choice(symbols) for _ in range(3)])
            picks = roll.split(" | ")
            if picks[0] == picks[1] == picks[2]:
                result = "🎉 Джекпот!"
            elif len(set(picks)) == 2:
                result = "✨ Почти!"
            else:
                result = "🎲 Ещё раз?"
            bot.answer_callback_query(call.id, f"{roll}\n{result}", show_alert=True)
            return

        if data == "os_game_rps":
            safe_edit_message(call, "*Камень-ножницы-бумага*\nВыберите ход:", reply_markup=_telos_rps_kb(), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data.startswith("os_game_rps_"):
            user_move = data.split("_")[3]
            bot_move = random.choice(["rock", "paper", "scissors"])
            icon = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
            if user_move == bot_move:
                res = "🤝 Ничья"
            elif (user_move == "rock" and bot_move == "scissors") or (user_move == "paper" and bot_move == "rock") or (user_move == "scissors" and bot_move == "paper"):
                res = "🎉 Победа"
            else:
                res = "😢 Поражение"
            bot.answer_callback_query(call.id, f"Вы: {icon[user_move]} | Бот: {icon[bot_move]}\n{res}", show_alert=True)
            return

        if data == "os_game_guess":
            st.setdefault("mini_games", {})["guess_target"] = random.randint(1, 10)
            _telos_save_state(uid, st)
            safe_edit_message(call, "*Угадай число*\nВыберите число от 1 до 10:", reply_markup=_telos_guess_kb(), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data == "os_game_dice":
            value = random.randint(1, 6)
            faces = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
            bot.answer_callback_query(call.id, f"🎲 Выпало: {faces[value]} ({value})", show_alert=True)
            return

        if data.startswith("os_game_guess_pick_"):
            try:
                pick = int(data.split("_")[4])
            except Exception:
                bot.answer_callback_query(call.id, "Ошибка выбора", show_alert=True)
                return
            target = st.setdefault("mini_games", {}).get("guess_target")
            if not isinstance(target, int):
                bot.answer_callback_query(call.id, "Сначала запустите игру «Угадай число»", show_alert=True)
                return
            if pick == target:
                st["mini_games"]["guess_target"] = None
                _telos_save_state(uid, st)
                bot.answer_callback_query(call.id, f"🎉 Верно! Это {target}", show_alert=True)
            else:
                hint = "меньше" if pick > target else "больше"
                bot.answer_callback_query(call.id, f"❌ Неверно. Загаданное число {hint}.", show_alert=True)
            return

        if data == "os_terminal":
            hist = st.get("terminal_history", [])
            body = "\n".join(hist[-8:]) if hist else "(пусто)"
            safe_edit_message(call, "*Терминал*\n\n`" + body + "`", reply_markup=_telos_terminal_kb(), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data.startswith("os_term_"):
            cmd = data.replace("os_term_", "")
            if cmd == "input":
                telos_input_wait[uid] = {"action": "term_input"}
                bot.answer_callback_query(call.id)
                bot.send_message(uid, "Введите команду терминала:")
                return
            out = _telos_run_command(st, cmd)
            st.setdefault("terminal_history", []).append(f"$ {cmd}")
            st["terminal_history"].append(out)
            st["terminal_history"] = st["terminal_history"][-20:]
            _telos_save_state(uid, st)
            safe_edit_message(call, "*Терминал*\n\n`" + "\n".join(st["terminal_history"][-8:]) + "`", reply_markup=_telos_terminal_kb(), parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if data == "os_settings":
            s = st.get("settings", {})
            safe_edit_message(
                call,
                "*Настройки*\n\n"
                f"Имя ОС: *{s.get('os_name', 'TELOS')}*\n"
                f"Тема: *{s.get('theme', 'classic')}*",
                reply_markup=_telos_settings_kb(),
                parse_mode="Markdown",
            )
            bot.answer_callback_query(call.id)
            return

        if data == "os_set_name":
            telos_input_wait[uid] = {"action": "set_os_name"}
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "Введите новое имя ОС (до 24 символов):")
            return

        if data == "os_set_theme":
            theme = st.get("settings", {}).get("theme", "classic")
            st["settings"]["theme"] = "neon" if theme == "classic" else "classic"
            _telos_save_state(uid, st)
            bot.answer_callback_query(call.id, f"Тема: {st['settings']['theme']}")
            safe_edit_message(call, _telos_home_text(uid), reply_markup=telos_main_menu(), parse_mode="Markdown")
            return

        if data == "os_set_reset":
            st = _telos_default_state()
            _telos_save_state(uid, st)
            bot.answer_callback_query(call.id, "TELOS сброшен")
            safe_edit_message(call, _telos_home_text(uid), reply_markup=telos_main_menu(), parse_mode="Markdown")
            return

        if data == "os_shutdown":
            st["booted"] = False
            _telos_save_state(uid, st)
            boot_kb = types.InlineKeyboardMarkup()
            boot_kb.add(types.InlineKeyboardButton("▶️ Запустить", callback_data="os_boot"))
            safe_edit_message(call, "⏻ *TELOS выключен*", reply_markup=boot_kb, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        bot.answer_callback_query(call.id)
    except Exception as e:
        print("TELOS CALLBACK ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")

# ------------------- Easter / Coin / Slot / Snake handlers (minimal) -------------------
@bot.callback_query_handler(func=lambda c: c.data == "easter_egg")
def easter_inline(call):
    bot.answer_callback_query(call.id, "Пасхалка!")
    Thread(target=play_inline_easter_egg, args=(call.inline_message_id,)).start()

@bot.callback_query_handler(func=lambda c: c.data.startswith("sysopen_"))
def sys_open(call):
    try:
        parts = call.data.split("_", 2)  # sysopen_{owner_uid}_{sid}
        owner_uid = int(parts[1])
        if owner_uid not in user_sys_settings:
            bot.answer_callback_query(call.id, "Данные не найдены.")
            return

        gui_text = user_sys_settings[owner_uid].get("gui", "Пусто")
        # Telegram alert text is limited; trim to avoid API errors.
        alert_text = gui_text[:190] if len(gui_text) > 190 else gui_text
        bot.answer_callback_query(call.id, alert_text or "Пусто", show_alert=True)
    except Exception as e:
        print("SYS OPEN ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка")


@bot.callback_query_handler(func=lambda c: c.data == "coin_flip")
def coin_flip(call):
    res = random.choice(["🪙 Орёл","🪙 Решка"])
    bot.edit_message_text(f"Результат: {res}", inline_message_id=call.inline_message_id)
    bot.answer_callback_query(call.id, res)

@bot.callback_query_handler(func=lambda c: c.data == "slot_spin")
def slot_spin(call):
    symbols = ["🍒", "🍋", "🍉", "⭐", "💎", "7️⃣"]
    roll = [random.choice(symbols) for _ in range(3)]
    text = f"| {' | '.join(roll)} |"
    if roll.count("7️⃣") == 3:
        text += "\n💥💥💥"
    elif len(set(roll)) == 1:
        text += "\n✨✨✨"
    elif len(set(roll)) == 2:
        text += "\n✨✨"
    else:
        text += "\n🎲"
    bot.edit_message_text(f"🎰 результат\n {text}\n", inline_message_id=call.inline_message_id,
                          reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🎰 Ещё раз", callback_data="slot_spin")))
    bot.answer_callback_query(call.id, "Крутим 🎲")

# ------------------- small helpers used earlier -------------------
def play_inline_easter_egg(inline_id):
    frames = [
    "8=✊===D 🤨",
    "8==✊==D 🤨",
    "8===✊=D 🤨",
    "8====✊D 🤨",
    "8===✊=D 🤨",
    "8==✊==D 🤨",
    "8=✊===D 🤨",
    "8==✊==D 🥲",
    "8===✊=D 🥲",
    "8====✊D💦 🥲",
    "8===✊=D 🥲",
    "8====✊D💦 ☺️",
    "8===✊=D 😊",
    "8====✊D💦 😊",
    "8===✊=D 😊",
    "8====✊D💦 😊",
    "8=====D ☺️",
    "конец "
    ]
    for frame in frames:
        try:
            bot.edit_message_text(frame, inline_message_id=inline_id)
            time.sleep(0.5)
        except:
            break

@bot.message_handler(func=lambda m: m.from_user.id in telos_input_wait)
def telos_save_input(message):
    uid = message.from_user.id
    text = (message.text or "").strip()
    wait = telos_input_wait.pop(uid, None)
    if not wait:
        return

    st = _telos_get_state(uid)
    action = wait.get("action")

    if action == "new_note":
        if text:
            st.setdefault("notes", []).append(text[:500])
            st["notes"] = st["notes"][-100:]
            _telos_save_state(uid, st)
            bot.send_message(uid, "✅ Заметка добавлена")
        else:
            bot.send_message(uid, "❌ Пустая заметка не сохранена")
        return

    if action == "new_file":
        if "|" in text:
            name, content = text.split("|", 1)
            name = name.strip()[:40] or f"file_{len(st.get('files', []))+1}.txt"
            content = content.strip()[:1500]
        else:
            name = f"file_{len(st.get('files', []))+1}.txt"
            content = text[:1500]
        st.setdefault("files", []).append({"name": name, "content": content})
        st["files"] = st["files"][-100:]
        _telos_save_state(uid, st)
        bot.send_message(uid, f"✅ Файл `{name}` сохранён", parse_mode="Markdown")
        return

    if action == "set_os_name":
        st.setdefault("settings", {})["os_name"] = (text[:24] if text else "TELOS")
        _telos_save_state(uid, st)
        bot.send_message(uid, f"✅ Имя ОС: *{st['settings']['os_name']}*", parse_mode="Markdown")
        return

    if action == "term_input":
        out = _telos_run_command(st, text)
        st.setdefault("terminal_history", []).append(f"$ {text}")
        st["terminal_history"].append(out)
        st["terminal_history"] = st["terminal_history"][-20:]
        _telos_save_state(uid, st)
        bot.send_message(uid, f"`$ {text}`\n`{out}`", parse_mode="Markdown")
        return

    bot.send_message(uid, "❌ Неизвестное действие TELOS")

@bot.message_handler(func=lambda m: m.from_user.id in system_notify_wait)
def sys_save_value(message):
    uid = message.from_user.id
    field = system_notify_wait.pop(uid)

    if uid not in user_sys_settings:
        user_sys_settings[uid] = {"msg": "", "btn": "", "title": "", "gui": ""}

    # Broadcast (global) fields start with "broadcast_"
    if field.startswith("broadcast_"):
        # map field names
        if field == "broadcast_msg":
            BROADCAST_SETTINGS["msg"] = message.text
        elif field == "broadcast_btn":
            BROADCAST_SETTINGS["btn_text"] = message.text
        elif field == "broadcast_btn_link":
            BROADCAST_SETTINGS["btn_link"] = message.text
            BROADCAST_SETTINGS["btn_type"] = "link"
        elif field == "broadcast_btn_callback":
            BROADCAST_SETTINGS["btn_text"] = message.text
            BROADCAST_SETTINGS["btn_type"] = "callback"

        # persist broadcast settings into data file
        d = load_data()
        d["broadcast"] = BROADCAST_SETTINGS
        save_data(d)
        bot.send_message(uid, "✅ Broadcast сохранён!")
        return

    # per-user system settings
    user_sys_settings[uid][field] = message.text
    bot.send_message(uid, "✅ Сохранено!")

    # ------------------- Flask keepalive -------------------
app = Flask('')
@app.route('/')
def home(): return "✅ если ты это видишь - Бот работает"
def run_flask(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    import requests, time
    url = "https://d249d7e4-7f3e-4dad-9329-793903bd08c3-00-q6aqz7jdva7t.riker.replit.dev/"
    while True:
        try: requests.get(url)
        except: pass
        time.sleep(300)

# ------------------- START -------------------
if __name__ == "__main__":
    start_premium_watcher(bot)  # запустится фоновой нитью
    Thread(target=run_flask).start()
    Thread(target=keep_alive, daemon=True).start()
    print("✅ Бот запущен")
    bot.infinity_polling()

