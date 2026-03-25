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
from room_games import (
    ROOM_VOTE_GAMES,
    is_room_game,
    room_game_start_text,
    room_game_launch,
    register_room_game_handlers,
)

# ---------- BOT SETUP ----------
TOKEN = "8317148699:AAET2FOHnMzozQ9OiaRglOBewXCq4ziDd_U"
bot = telebot.TeleBot(TOKEN)
bot.delete_webhook()
try:
    INLINE_BOT_USERNAME = bot.get_me().username or "minigamesisbot"
except Exception:
    INLINE_BOT_USERNAME = "minigamesisbot"
register_room_game_handlers(bot)

# ---------- CONFIGURATION ----------
GROQ_API_KEY = "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"
groq_client = Groq(api_key=GROQ_API_KEY)

FREE_DAILY_QUOTA = 10
PREMIUM_DAYS = 30

DATA_FILE = "ai_users.json"
# Название канала для обязательной подписки (если нужно)
REQUIRED_CHANNEL = "@minigamesbottgk"  # или None
SUPPORT_ADMIN_IDS_RAW = os.getenv("SUPPORT_ADMIN_IDS", "5782683757")
SUPPORT_ADMIN_IDS = {
    int(x.strip())
    for x in str(SUPPORT_ADMIN_IDS_RAW).split(",")
    if x.strip().isdigit()
}

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
ROOM_FREE_TITLE = "Свободно"
ROOM_TTL_SECONDS = 3600
ROOM_CODE_LEN = 5
ROOM_VOTE_SECONDS = 60
ROOM_MESSAGE_BUFFER = 0
def _ensure_data_file(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "users": {},
                "premium": {},
                "ai_cache": {},
                "stats": {},
                "global_game_stats": {},
                "rooms": {"pool": [], "active": {}, "free_title": ROOM_FREE_TITLE},
            }, f, ensure_ascii=False, indent=2)

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"users": {}}, f)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("users", {})
    data.setdefault("global_game_stats", {})
    data.setdefault("premium", {})
    data.setdefault("rooms", {"pool": [], "active": {}, "free_title": ROOM_FREE_TITLE})
    return data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

try:
    dtmp = load_data()
    if dtmp.get("broadcast"):
        BROADCAST_SETTINGS.update(dtmp.get("broadcast"))
except Exception:
    pass

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
    _check_achievements(user_id, rec)
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

GAME_TITLES = {
    "rps": "Камень-ножницы-бумага",
    "ttt": "Крестики-нолики",
    "millionaire": "Миллионер",
    "coin": "Орел или решка",
    "wordle": "Wordle",
    "bship": "Морской бой",
    "chess": "Шахматы",
    "guess": "Угадай число",
    "slot": "Казино",
    "snake": "Змейка",
    "tetris": "Тетрис",
    "flappy": "Flappy Bird",
    "g2048": "2048",
    "pong": "Пинг-понг",
    "hangman": "Виселица",
    "minesweeper": "Сапер",
    "quizgame": "Викторина",
    "combogame": "Комбо-битва",
    "mafia": "Мафия",
    "wordgame": "Словесная дуэль",
    "reaction": "Блиц-реакция",
    "blackjack": "Блэкджек",
    "room_rps": "Камень-ножницы-бумага (чат)",
    "room_duel": "Быстрая дуэль (чат)",
    "room_bship": "Морской бой (чат)",
    "room_quiz": "Викторина (чат)",
    "room_combo": "Комбо-битва (чат)",
    "room_mafia": "Мафия (чат)",
}

SHOP_ITEMS = {
    "avatar_fire": {"name": "Аватар: Огонь", "type": "avatar", "value": "🔥", "price": 40},
    "avatar_star": {"name": "Аватар: Звезда", "type": "avatar", "value": "⭐", "price": 40},
    "avatar_robot": {"name": "Аватар: Робот", "type": "avatar", "value": "🤖", "price": 50},
    "frame_gold": {"name": "Рамка: Золото", "type": "frame", "value": "gold", "price": 60},
    "frame_neon": {"name": "Рамка: Неон", "type": "frame", "value": "neon", "price": 70},
    "theme_dark": {"name": "Тема: Dark", "type": "theme", "value": "dark", "price": 50},
    "theme_cyber": {"name": "Тема: Cyber", "type": "theme", "value": "cyber", "price": 80},
    "victory_crown": {"name": "Эффект победы: Корона", "type": "victory", "value": "👑", "price": 90},
    "victory_trophy": {"name": "Эффект победы: Кубок", "type": "victory", "value": "🏆", "price": 90},
}


def _ensure_profile_fields(rec):
    if not isinstance(rec, dict):
        rec = {}
    if not isinstance(rec.get("inventory"), list):
        rec["inventory"] = []
    if "coins" not in rec:
        rec["coins"] = 0
    if not isinstance(rec.get("achievements"), dict):
        rec["achievements"] = {}
    if "rooms_created" not in rec:
        rec["rooms_created"] = 0
    rec["avatar_emoji"] = str(rec.get("avatar_emoji") or "🙂")
    rec["frame_style"] = str(rec.get("frame_style") or "base")
    rec["theme_style"] = str(rec.get("theme_style") or "classic")
    rec["victory_emoji"] = str(rec.get("victory_emoji") or "🎉")
    return rec

ACHIEVEMENTS = {
    "first_game": {"title": "Первый шаг", "desc": "Сыграть 1 игру"},
    "gamer_20": {"title": "Игроман", "desc": "Сыграть 20 игр"},
    "gamer_100": {"title": "Марафон", "desc": "Сыграть 100 игр"},
    "collector_5": {"title": "Коллекционер", "desc": "Сыграть в 5 разных игр"},
    "streak_7": {"title": "Ритм", "desc": "Серия 7 дней"},
    "coins_200": {"title": "Копилка", "desc": "Накопить 200 монет"},
    "coins_1000": {"title": "Мешок монет", "desc": "Накопить 1000 монет"},
    "room_creator": {"title": "Хозяин комнаты", "desc": "Создать 1 комнату"},
    "blackjack_5": {"title": "Везунчик", "desc": "Выиграть 5 партий в блэкджек"},
}

def _distinct_games_count(rec):
    gstats = rec.get("game_stats", {}) if isinstance(rec.get("game_stats", {}), dict) else {}
    return len([k for k, v in gstats.items() if int((v or {}).get("played", 0) or 0) > 0])

def _get_blackjack_wins(rec):
    gstats = rec.get("game_stats", {}) if isinstance(rec.get("game_stats", {}), dict) else {}
    row = gstats.get("blackjack", {}) if isinstance(gstats.get("blackjack", {}), dict) else {}
    return int(row.get("wins", 0) or 0)

def _check_achievements(uid, rec=None):
    d = load_data()
    users = d.setdefault("users", {})
    rec = _ensure_profile_fields(rec or users.setdefault(str(uid), {}))
    achievements = rec.setdefault("achievements", {})

    total_games = int(rec.get("games_total", 0) or 0)
    streak_best = int(rec.get("streak_best", 0) or 0)
    coins = int(rec.get("coins", 0) or 0)
    distinct_games = _distinct_games_count(rec)
    rooms_created = int(rec.get("rooms_created", 0) or 0)
    bj_wins = _get_blackjack_wins(rec)

    checks = {
        "first_game": total_games >= 1,
        "gamer_20": total_games >= 20,
        "gamer_100": total_games >= 100,
        "collector_5": distinct_games >= 5,
        "streak_7": streak_best >= 7,
        "coins_200": coins >= 200,
        "coins_1000": coins >= 1000,
        "room_creator": rooms_created >= 1,
        "blackjack_5": bj_wins >= 5,
    }

    changed = False
    for key, ok in checks.items():
        if ok and key not in achievements:
            achievements[key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            changed = True

    if changed:
        rec["achievements"] = achievements
        users[str(uid)] = rec
        save_data(d)
    return rec

def _record_game_play(user_id, game_key, display_name=None, session_id=None):
    if not game_key:
        return
    d = load_data()
    users = d.setdefault("users", {})
    rec = users.setdefault(str(user_id), {})
    rec = _ensure_profile_fields(rec)
    if display_name:
        rec["display_name"] = str(display_name)[:64]

    gstats = rec.setdefault("game_stats", {})
    if not isinstance(gstats, dict):
        gstats = {}
        rec["game_stats"] = gstats
    row = gstats.setdefault(game_key, {"played": 0, "wins": 0, "losses": 0, "draws": 0})
    row["played"] = int(row.get("played", 0) or 0) + 1

    rec["games_total"] = int(rec.get("games_total", 0) or 0) + 1
    history = rec.setdefault("match_history", [])
    if not isinstance(history, list):
        history = []
    history.append({
        "game": game_key,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session": str(session_id or ""),
    })
    rec["match_history"] = history[-50:]
    rec["coins"] = int(rec.get("coins", 0) or 0) + 2

    global_stats = d.setdefault("global_game_stats", {})
    global_stats[game_key] = int(global_stats.get(game_key, 0) or 0) + 1
    save_data(d)
    _check_achievements(user_id, rec)

def _record_game_play_once(user_id, game_key, session_id, display_name=None):
    if not game_key:
        return
    sid = str(session_id or "").strip()
    if not sid:
        _record_game_play(user_id, game_key, display_name=display_name, session_id=session_id)
        return
    d = load_data()
    users = d.setdefault("users", {})
    rec = users.setdefault(str(user_id), {})
    seen = rec.setdefault("tracked_sessions", [])
    if not isinstance(seen, list):
        seen = []
    uniq = f"{game_key}:{sid}"
    if uniq in seen:
        return
    seen.append(uniq)
    rec["tracked_sessions"] = seen[-1000:]
    users[str(user_id)] = rec
    save_data(d)
    _record_game_play(user_id, game_key, display_name=display_name, session_id=session_id)

def _record_game_result(user_id, game_key, result):
    if result not in ("wins", "losses", "draws"):
        return
    d = load_data()
    users = d.setdefault("users", {})
    rec = users.setdefault(str(user_id), {})
    rec = _ensure_profile_fields(rec)
    gstats = rec.setdefault("game_stats", {})
    if not isinstance(gstats, dict):
        gstats = {}
        rec["game_stats"] = gstats
    row = gstats.setdefault(game_key, {"played": 0, "wins": 0, "losses": 0, "draws": 0})
    row[result] = int(row.get(result, 0) or 0) + 1
    gstats[game_key] = row
    rec["game_stats"] = gstats
    users[str(user_id)] = rec
    save_data(d)
    _check_achievements(user_id, rec)

def _game_from_inline_result_id(result_id):
    rid = str(result_id or "").strip().lower()
    if not rid:
        return None
    prefixes = [
        "rps_", "ttt_", "millionaire_", "coin_", "wordle_", "bship_", "chess_",
        "guess_", "slot_", "snake_", "tetris_", "g2048_", "pong_",
        "hangman_", "minesweeper_", "quizgame_", "combogame_", "mafia_", "wordgame_",
    ]
    for p in prefixes:
        if rid.startswith(p):
            return p[:-1]
    return None

def _track_callback_game_play(call):
    try:
        data = str(call.data or "")
        uid = call.from_user.id
        name = call.from_user.first_name or call.from_user.username or str(uid)
        parts = data.split("_")
        game_key = None
        sid = None

        if data.startswith("rps_move_") and len(parts) >= 3:
            game_key, sid = "rps", parts[2]
        elif data.startswith("rps_join_") and len(parts) >= 3:
            game_key, sid = "rps", parts[2]
        elif data.startswith("rps_") and len(parts) >= 2:
            game_key, sid = "rps", parts[1]
        elif data.startswith("ttt_move_") and len(parts) >= 3:
            game_key, sid = "ttt", parts[2]
        elif data.startswith("ttt_restart_") and len(parts) >= 3:
            game_key, sid = "ttt", parts[2]
        elif data.startswith("ttt_join_") and len(parts) >= 3:
            game_key, sid = "ttt", parts[2]
        elif data.startswith("millionaire_") and len(parts) >= 3:
            game_key, sid = "millionaire", parts[1]
        elif data.startswith("wrdl_") and len(parts) >= 3:
            game_key, sid = "wordle", parts[2]
        elif data.startswith("bship_") and len(parts) >= 3:
            game_key, sid = "bship", parts[2]
        elif data.startswith("chess_") and len(parts) >= 3:
            game_key, sid = "chess", parts[2]
        elif data.startswith("g2048_"):
            game_key = "g2048"
            sid = parts[1] if len(parts) >= 3 and parts[1] != "new" else None
        elif data.startswith("tetris_"):
            game_key = "tetris"
            sid = parts[1] if len(parts) >= 3 and parts[1] != "new" else None
        elif data.startswith("pong_") and len(parts) >= 3:
            game_key, sid = "pong", parts[1]
        elif data.startswith("hangman_"):
            game_key = "hangman"
            sid = parts[1] if len(parts) >= 3 and parts[1] != "new" else None
        elif data.startswith("minesweeper_") and len(parts) >= 3:
            game_key, sid = "minesweeper", parts[1]
        elif data.startswith("quizgame_") and len(parts) >= 3:
            game_key, sid = "quizgame", parts[2]
        elif data.startswith("quiz_") and len(parts) >= 3:
            game_key, sid = "quizgame", parts[1]
        elif data.startswith("combogame_") and len(parts) >= 3:
            game_key, sid = "combogame", parts[2]
        elif data.startswith("combo_") and len(parts) >= 3:
            game_key, sid = "combogame", parts[1]
        elif data.startswith("mafia_") and len(parts) >= 3:
            game_key, sid = "mafia", parts[2]
        elif data.startswith("wordgame_join_") and len(parts) >= 3:
            game_key, sid = "wordgame", parts[2]
        elif data.startswith("emojigame_join_") and len(parts) >= 3:
            game_key, sid = "wordgame", parts[2]
        elif data.startswith("guess_inline_"):
            game_key = "guess"
        elif data == "coin_flip":
            game_key = "coin"
        elif data == "slot_spin":
            game_key = "slot"
        elif data.startswith("snake_"):
            game_key = "snake"

        if not game_key:
            return
        if not sid:
            sid = call.inline_message_id or (
                f"{call.message.chat.id}:{call.message.message_id}" if call.message else ""
            )
        _record_game_play_once(uid, game_key, sid, display_name=name)
    except Exception as e:
        print("CALLBACK TRACK ERROR:", e)

def _render_profile_text(uid):
    d = load_data()
    user = d.get("users", {}).get(str(uid), {}) or {}
    user = _ensure_profile_fields(user)
    total = int(user.get("games_total", 0) or 0)
    coins = int(user.get("coins", 0) or 0)
    ach_count = len(user.get("achievements", {}) if isinstance(user.get("achievements", {}), dict) else {})
    gstats = user.get("game_stats", {}) if isinstance(user.get("game_stats", {}), dict) else {}
    history = user.get("match_history", []) if isinstance(user.get("match_history", []), list) else []
    display_name = user.get("display_name") or f"user_{uid}"
    avatar = user.get("avatar_emoji", "🙂")
    frame_style = user.get("frame_style", "base")
    theme_style = user.get("theme_style", "classic")
    victory_emoji = user.get("victory_emoji", "🎉")

    fav_game = "—"
    fav_count = 0
    wins_total = 0
    losses_total = 0
    draws_total = 0
    for gk, row in gstats.items():
        played = int((row or {}).get("played", 0) or 0)
        wins_total += int((row or {}).get("wins", 0) or 0)
        losses_total += int((row or {}).get("losses", 0) or 0)
        draws_total += int((row or {}).get("draws", 0) or 0)
        if played > fav_count:
            fav_count = played
            fav_game = GAME_TITLES.get(gk, gk)
    rated_games = wins_total + losses_total
    winrate = (wins_total * 100.0 / rated_games) if rated_games > 0 else 0.0

    lines = [
        f"{avatar} Профиль: {display_name}",
        f"🎮 Всего сыграно: {total}",
        f"🪙 Монеты: {coins}",
        f"🏆 Достижения: {ach_count}/{len(ACHIEVEMENTS)}",
        f"🏅 Любимая игра: {fav_game}" + (f" ({fav_count})" if fav_count else ""),
        f"📈 Winrate: {winrate:.1f}% (W:{wins_total} L:{losses_total} D:{draws_total})",
        f"🎨 Оформление: рамка={frame_style}, тема={theme_style}, победа={victory_emoji}",
    ]
    if gstats:
        lines.append("")
        lines.append("📊 Статистика по играм:")
        rows = sorted(gstats.items(), key=lambda kv: int((kv[1] or {}).get("played", 0) or 0), reverse=True)
        for gk, row in rows:
            played = int((row or {}).get("played", 0) or 0)
            if played <= 0:
                continue
            title = GAME_TITLES.get(gk, gk)
            lines.append(f"• {title}: {played}")
    else:
        lines.append("")
        lines.append("📊 Статистика по играм: пока пусто")

    if history:
        lines.append("")
        lines.append("🕓 Последние матчи:")
        for item in history[-10:][::-1]:
            gk = str(item.get("game", ""))
            title = GAME_TITLES.get(gk, gk or "Игра")
            at = str(item.get("at", ""))
            lines.append(f"• {title} — {at}")

    return "\n".join(lines)

def _render_achievements_text(uid):
    d = load_data()
    user = d.get("users", {}).get(str(uid), {}) or {}
    user = _ensure_profile_fields(user)
    unlocked = user.get("achievements", {}) if isinstance(user.get("achievements", {}), dict) else {}

    total = len(ACHIEVEMENTS)
    unlocked_count = len(unlocked)
    lines = [f"🏆 Достижения: {unlocked_count}/{total}"]
    if unlocked:
        lines.append("")
        lines.append("✅ Открыты:")
        for key, meta in ACHIEVEMENTS.items():
            if key in unlocked:
                when = unlocked.get(key, "")
                lines.append(f"• {meta['title']} — {meta['desc']}" + (f" ({when})" if when else ""))
    locked = [k for k in ACHIEVEMENTS.keys() if k not in unlocked]
    if locked:
        lines.append("")
        lines.append("🔒 Закрыты:")
        for key in locked:
            meta = ACHIEVEMENTS[key]
            lines.append(f"• {meta['title']} — {meta['desc']}")
    return "\n".join(lines)

# ------------------- ROOMS -------------------

def _rooms_get_data():
    d = load_data()
    rooms = d.setdefault("rooms", {"pool": [], "active": {}, "free_title": ROOM_FREE_TITLE})
    rooms.setdefault("pool", [])
    rooms.setdefault("active", {})
    rooms.setdefault("free_title", ROOM_FREE_TITLE)
    return d, rooms

def _room_generate_code(rooms):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    active = rooms.get("active", {}) if isinstance(rooms.get("active", {}), dict) else {}
    while True:
        code = "".join(random.choice(alphabet) for _ in range(ROOM_CODE_LEN))
        if code not in active:
            return code

def _room_pick_free_chat(rooms):
    pool = rooms.get("pool", []) if isinstance(rooms.get("pool", []), list) else []
    active = rooms.get("active", {}) if isinstance(rooms.get("active", {}), dict) else {}
    busy = {r.get("chat_id") for r in active.values() if isinstance(r, dict)}
    for chat_id in pool:
        if chat_id not in busy:
            return chat_id
    return None

def _room_find_by_chat(rooms, chat_id):
    active = rooms.get("active", {}) if isinstance(rooms.get("active", {}), dict) else {}
    for code, room in active.items():
        if isinstance(room, dict) and room.get("chat_id") == chat_id:
            return code, room
    return None, None

def _room_game_start_text(game_key):
    if is_room_game(game_key):
        return room_game_start_text(game_key)
    if game_key == "ttt":
        return f"Запуск: напишите <code>@{INLINE_BOT_USERNAME}</code> и выберите крестики-нолики."
    if game_key == "chess":
        return f"Запуск: напишите <code>@{INLINE_BOT_USERNAME}</code> и выберите шахматы."
    if game_key == "bship":
        return f"Запуск: напишите <code>@{INLINE_BOT_USERNAME}</code> и выберите морской бой."
    if game_key == "mafia":
        return f"Запуск: напишите <code>@{INLINE_BOT_USERNAME}</code> и выберите Мафию."
    if game_key == "wordgame":
        return f"Запуск: напишите <code>@{INLINE_BOT_USERNAME}</code> и выберите словесную дуэль."
    if game_key == "quizgame":
        return f"Запуск: напишите <code>@{INLINE_BOT_USERNAME}</code> и выберите Викторину."
    if game_key == "combogame":
        return f"Запуск: напишите <code>@{INLINE_BOT_USERNAME}</code> и выберите комбо-битву."
    return "Игра выбрана."

def _room_inline_query_for_game(game_key):
    if is_room_game(game_key):
        return ""
    mapping = {
        "ttt": "крестики-нолики",
        "chess": "шахматы",
        "bship": "морской бой",
        "mafia": "мафия",
        "wordgame": "словесная дуэль",
        "quizgame": "викторина",
        "combogame": "комбо-битва",
    }
    return mapping.get(game_key, "")

def _room_launch_kb(game_key):
    query = _room_inline_query_for_game(game_key)
    if not query:
        return None
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("▶️ Запустить игру", switch_inline_query_current_chat=query))
    return kb

def _room_post_game_prompt(chat_id, code):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Да", callback_data=f"room_continue_yes_{code}"),
        types.InlineKeyboardButton("❌ Нет", callback_data=f"room_continue_no_{code}")
    )
    try:
        msg = bot.send_message(chat_id, "🔁 Продолжаем?", reply_markup=kb)
        _room_track_message_id(chat_id, getattr(msg, "message_id", None))
    except Exception:
        pass

def _room_game_end_kb(code):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏁 Игра завершена", callback_data=f"room_game_end_{code}"))
    return kb

def _room_track_message_id(chat_id, message_id):
    if not chat_id or not message_id:
        return
    msg_list = room_messages.setdefault(chat_id, [])
    msg_list.append(message_id)
    if ROOM_MESSAGE_BUFFER and len(msg_list) > ROOM_MESSAGE_BUFFER:
        room_messages[chat_id] = msg_list[-ROOM_MESSAGE_BUFFER:]

def _room_start_vote(chat_id, code):
    options = [title for _, title in ROOM_VOTE_GAMES]
    keys = [key for key, _ in ROOM_VOTE_GAMES]
    try:
        msg = bot.send_poll(chat_id, "Выберите игру голосованием:", options, is_anonymous=False, allows_multiple_answers=False)
        poll_id = msg.poll.id
        _room_track_message_id(chat_id, msg.message_id)
    except Exception:
        poll_id = None
        msg = None
    d, rooms = _rooms_get_data()
    room = rooms.get("active", {}).get(code, {}) if isinstance(rooms.get("active", {}), dict) else {}
    room["vote_options"] = keys
    if poll_id:
        room["poll_id"] = poll_id
        room_polls[poll_id] = {"code": code, "options": keys}
    rooms["active"][code] = room
    save_data(d)

    def finalize():
        time.sleep(ROOM_VOTE_SECONDS)
        _room_finalize_vote(code)
    Thread(target=finalize, daemon=True).start()

def _room_finalize_vote(code):
    d, rooms = _rooms_get_data()
    room = rooms.get("active", {}).get(code)
    if not isinstance(room, dict):
        return
    if room.get("game"):
        return
    options = room.get("vote_options", [])
    votes = room.get("votes", {})
    if not options:
        return
    tally = {i: 0 for i in range(len(options))}
    if isinstance(votes, dict):
        for _, opt in votes.items():
            try:
                idx = int(opt)
                if idx in tally:
                    tally[idx] += 1
            except Exception:
                pass
    if tally and max(tally.values()) > 0:
        top = [i for i, v in tally.items() if v == max(tally.values())]
        winner_idx = random.choice(top)
    else:
        winner_idx = random.randrange(0, len(options))
    chosen_key = options[winner_idx]
    room["game"] = chosen_key
    room["status"] = "active"
    rooms["active"][code] = room
    save_data(d)
    try:
        msg1 = bot.send_message(
            room["chat_id"],
            f"✅ Выбрана игра: {GAME_TITLES.get(chosen_key, chosen_key)}\n\n{_room_game_start_text(chosen_key)}",
            parse_mode="HTML"
        )
        _room_track_message_id(room["chat_id"], getattr(msg1, "message_id", None))
        launch_kb = _room_launch_kb(chosen_key)
        if launch_kb:
            msg_launch = bot.send_message(
                room["chat_id"],
                "Нажмите, чтобы сразу открыть игру в этом чате:",
                reply_markup=launch_kb
            )
            _room_track_message_id(room["chat_id"], getattr(msg_launch, "message_id", None))
        msg2 = bot.send_message(
            room["chat_id"],
            "Когда закончите партию, нажмите кнопку ниже.",
            reply_markup=_room_game_end_kb(code)
        )
        _room_track_message_id(room["chat_id"], getattr(msg2, "message_id", None))
    except Exception:
        pass

    # авто-запуск для локальных игр
    try:
        if is_room_game(chosen_key):
            room_game_launch(bot, room["chat_id"], code, room)
            return
        if chosen_key == "reaction":
            _reaction_start(room["chat_id"], room.get("creator_id"))
        elif chosen_key == "blackjack":
            state = _bj_new_game(room.get("creator_id"), room["chat_id"])
            gid = short_id()
            blackjack_games[gid] = state
            text = _bj_render_text(state, reveal_dealer=state.get("status") != "playing")
            kb = _bj_keyboard(gid, state.get("status"))
            msg = bot.send_message(room["chat_id"], text, reply_markup=kb)
            _room_track_message_id(room["chat_id"], getattr(msg, "message_id", None))
    except Exception:
        pass

def _room_close(code, reason=""):
    d, rooms = _rooms_get_data()
    active = rooms.get("active", {}) if isinstance(rooms.get("active", {}), dict) else {}
    room = active.pop(code, None)
    if not isinstance(room, dict):
        return False
    chat_id = room.get("chat_id")

    try:
        old_link = room.get("invite_link")
        if old_link:
            bot.revoke_chat_invite_link(chat_id, old_link)
        bot.create_chat_invite_link(chat_id)
    except Exception:
        pass

    try:
        bot.set_chat_title(chat_id, rooms.get("free_title", ROOM_FREE_TITLE))
    except Exception:
        pass

    participants = set(room.get("participants", []) or [])
    participants.update(room_participants.get(chat_id, set()))
    for uid in participants:
        try:
            bot.kick_chat_member(chat_id, uid)
            bot.unban_chat_member(chat_id, uid)
        except Exception:
            pass

    for mid in room_messages.get(chat_id, []):
        try:
            bot.delete_message(chat_id, mid)
        except Exception:
            pass

    room_messages.pop(chat_id, None)
    room_participants.pop(chat_id, None)
    rooms["active"] = active
    save_data(d)

    try:
        bot.send_message(chat_id, f"⏳ Пати закрыто. {('Причина: ' + reason) if reason else ''}\nГруппа освобождена.")
    except Exception:
        pass
    return True

def _rooms_watchdog():
    while True:
        try:
            d, rooms = _rooms_get_data()
            active = rooms.get("active", {}) if isinstance(rooms.get("active", {}), dict) else {}
            now_ts = time.time()
            for code, room in list(active.items()):
                if not isinstance(room, dict):
                    continue
                ends_at = float(room.get("ends_at") or 0)
                if ends_at and now_ts >= ends_at:
                    _room_close(code, reason="таймер 1 час")
        except Exception:
            pass
        time.sleep(30)


def _shop_menu_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛍 Открыть магазин", callback_data="shop_open"))
    return kb


def _shop_render_text(uid):
    d = load_data()
    rec = d.setdefault("users", {}).setdefault(str(uid), {})
    rec = _ensure_profile_fields(rec)
    save_data(d)
    owned = set(rec.get("inventory", []))
    lines = [f"🛍 Магазин", f"Ваш баланс: {int(rec.get('coins', 0) or 0)} монет", "", "Доступные товары:"]
    for item_id, item in SHOP_ITEMS.items():
        mark = "✅ куплено" if item_id in owned else f"{item['price']} 🪙"
        lines.append(f"• {item['name']} — {mark}")
    return "\n".join(lines)


def _shop_items_kb(uid):
    d = load_data()
    rec = d.setdefault("users", {}).setdefault(str(uid), {})
    rec = _ensure_profile_fields(rec)
    save_data(d)
    owned = set(rec.get("inventory", []))
    kb = types.InlineKeyboardMarkup()
    for item_id, item in SHOP_ITEMS.items():
        if item_id in owned:
            kb.add(types.InlineKeyboardButton(f"Применить: {item['name']}", callback_data=f"shop_apply_{item_id}"))
        else:
            kb.add(types.InlineKeyboardButton(f"Купить: {item['name']} ({item['price']}🪙)", callback_data=f"shop_buy_{item_id}"))
    kb.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="shop_open"))
    return kb

def has_premium(uid):
    user = get_user(uid)
    return user["premium_until"] > time.time()

def can_use_ai(uid):
    user = get_user(uid)
    if has_premium(uid):
        return True, None
    cnt = int(user.get("count", 0) or 0)
    if cnt < FREE_DAILY_QUOTA:
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
    rec = d.setdefault("users", {}).setdefault(str(user_id), {})
    today = date.today().isoformat()
    # unified reset for both counters
    if rec.get("date") != today:
        rec["date"] = today
        rec["count"] = 0
    if rec.get("daily_date") != today:
        rec["daily_date"] = today
        rec["daily_count"] = 0
    # increment both (backward compatibility)
    rec["count"] = int(rec.get("count", 0) or 0) + 1
    rec["daily_count"] = int(rec.get("daily_count", 0) or 0) + 1
    d.setdefault("users", {})[str(user_id)] = rec
    save_data(d)
    return rec["count"]

def pong_game_loop(gid, inline_id):
    while gid in games_pong:
        state = games_pong.get(gid)
        if not state:
            break
        if not state.get("started"):
            time.sleep(0.35)
            continue

        _pong_step(state)
        try:
            bot.edit_message_text(
                _render_pong_text(state),
                inline_message_id=inline_id,
                reply_markup=_pong_controls_markup(
                    gid,
                    started=state.get("started", False),
                    game_over=state.get("winner") is not None,
                ),
            )
        except Exception:
            break

        if state.get("winner"):
            games_pong.pop(gid, None)
            break
        time.sleep(0.6)

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

def _is_group_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
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
support_chat_wait = {}      # uid -> "moderator" | "issue"
admin_wait = {}            # uid -> {"action": "..."}
millionaire_games = {}   # short_id -> {"question":..., "attempts":int}
user_show_easter_egg = {}  # uid -> bool (для управления отображением пасхалки)
pm_flappy_games = {}  # uid -> local flappy state for private chat
games_2048 = {}     # gid -> {"board": [[int]]}
games_pong = {}     # gid -> {"players":[id_or_None,id_or_None],"paddles":[y1,y2],"ball":[x,y,dx,dy],"started":bool}
user_ai_mode = {}  # user_id -> mode
rps_games = {}  # game_id -> {"uid": int}
hide_games = {}
hangman_games = {}  # gid -> {"word": str, "guessed": set(), "wrong": set(), "attempts": int}
mafia_games = {}    # gid -> mafia game state
games_tetris = {}   # gid -> {"w","h","board","piece","score","over"}
reaction_games = {}  # gid -> {"uid","chat_id","started","start_at","msg_id","inline_id"}
blackjack_games = {}  # gid -> {"uid","chat_id","status","deck","player","dealer"}
room_polls = {}  # poll_id -> {"code": str, "options": [game_key]}
room_messages = {}  # chat_id -> [message_id]
room_participants = {}  # chat_id -> set(user_id)

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
wordle_games = {}  # gid -> {"owner": int, "target": str, "attempts": list, "current": str, "status": str}
chess_games = {}  # gid -> chess game state
battleship_games = {}  # gid -> battleship game state

WORDLE_WORDS = [
    "абзац", "аванс", "аврал", "автор", "агент", "адрес", "азарт", "актер",
    "акция", "алмаз", "аллея", "амбар", "ангел", "арбат", "арбуз", "арена",
    "архив", "астра", "атлас", "багаж", "багет", "байка", "балет", "балка",
    "банан", "банка", "барин", "башня", "берег", "билет", "блеск", "блюдо",
    "бобер", "богач", "бокал", "бочка", "брешь", "бровь", "брюки", "буква",
    "буран", "бутон", "вагон", "вдова", "весна", "ветер", "ветка", "вечер",
    "вилка", "вирус", "вишня", "влага", "взлет", "видео", "визит", "виток",
    "вокал", "волна", "время", "входы", "выдох", "выход", "гений", "герой",
    "глава", "глина", "голод", "голос", "гонка", "город", "горох", "гость",
    "графа", "гроза", "груша", "дебют", "дверь", "девиз", "декор", "диван",
    "дождь", "доска", "доход", "драка", "дрема", "дрель", "дымка", "жажда",
    "жизнь", "живот", "жираф", "завод", "загар", "закон", "замок", "запах",
    "заряд", "зебра", "земля", "зерно", "зверь", "зубок", "игрок", "идеал",
    "износ", "искра", "исход", "какао", "казна", "камин", "канат", "канон",
    "капля", "карта", "катер", "кепка", "киоск", "кисть", "кивок", "класс",
    "книга", "кобра", "ковер", "койка", "кольт", "конус", "копия", "корка",
    "корма", "кошка", "краса", "крона", "крупа", "крыло", "купол", "курок",
    "кухня", "ласка", "лавка", "лазер", "лампа", "лапша", "левша", "лента",
    "лимон", "линия", "лодка", "ложка", "локон", "лучик", "лыжня", "магия",
    "майка", "майор", "манго", "манеж", "марка", "маска", "масса", "медик",
    "мелок", "место", "метод", "метро", "мечта", "мираж", "минус", "миска",
    "модем", "мойка", "мороз", "моряк", "мосты", "мотор", "музей", "набор",
    "навык", "напев", "наряд", "нация", "недра", "нерпа", "нитка", "ночка",
    "номер", "норма", "носок", "ножик", "облик", "обман", "обмен", "образ",
    "обувь", "обряд", "огонь", "океан", "оклад", "окрас", "олень", "омлет",
    "опека", "орден", "осень", "отдых", "отель", "ответ", "отзыв", "отряд",
    "очерк", "падеж", "пакет", "палец", "палка", "панно", "парус", "паста",
    "пауза", "певец", "пенал", "перец", "песня", "печка", "пиала", "пилот",
    "пирог", "пламя", "плита", "повар", "повод", "поезд", "поиск", "показ",
    "полет", "полка", "порог", "порыв", "поток", "почка", "почва", "поэма",
    "право", "проза", "птица", "пчела", "пульт", "пункт", "пучок", "радар",
    "район", "раунд", "ребро", "рейка", "робот", "ролик", "роман", "рубин",
    "рубль", "ручей", "ручка", "рыбак", "рынок", "садик", "салют", "сапог",
    "сахар", "сборы", "свеча", "север", "секта", "семья", "сетка", "синий",
    "сироп", "скала", "сквер", "склад", "скрип", "скука", "слава", "слеза",
    "слово", "слуга", "слюна", "смесь", "снова", "сокол", "сосна", "совет",
    "спазм", "спина", "спорт", "спуск", "спрос", "среда", "старт", "стена",
    "страж", "стихи", "стриж", "струя", "сумка", "сушка", "суета", "судно",
    "сфера", "сцена", "сыщик", "тайна", "такси", "танго", "танец", "театр",
    "телец", "тембр", "тепло", "тесто", "тираж", "товар", "тонус", "топаз",
    "топор", "торец", "точка", "трава", "трель", "тропа", "труба", "тучка",
    "туман", "турок", "уголь", "удача", "уклад", "улика", "уроки", "устои",
    "утиль", "утром", "факел", "фауна", "ферма", "фикус", "финик", "фирма",
    "флора", "фокус", "форма", "фраза", "халва", "хвост", "хижак", "хитон",
    "хлеба", "холод", "хомяк", "хорек", "хруст", "цветы", "цифра", "цапля",
    "центр", "чайка", "часть", "чашка", "череп", "честь", "чехол", "число",
    "чулок", "шайба", "шаман", "шапка", "шарик", "шепот", "школа", "шорох",
    "шпага", "штиль", "шторм", "шторы", "шутка", "щенок", "щепка", "щетка",
    "щиток", "экран", "эскиз", "этажи", "этика", "юниор", "юрист", "ягода",
    "ямщик", "ясень"
]

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

# ------------------- BLITZ REACTION -------------------
def _reaction_keyboard(gid):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚡ ЖМИ!", callback_data=f"reaction_hit_{gid}"))
    return kb

def _reaction_edit(state, text, reply_markup=None):
    try:
        if state.get("inline_id"):
            bot.edit_message_text(text, inline_message_id=state["inline_id"], reply_markup=reply_markup)
        elif state.get("msg_id") and state.get("chat_id"):
            bot.edit_message_text(text, chat_id=state["chat_id"], message_id=state["msg_id"], reply_markup=reply_markup)
    except Exception:
        pass

def _reaction_start(chat_id, uid):
    gid = short_id()
    state = {"uid": uid, "chat_id": chat_id, "started": False, "start_at": None, "msg_id": None, "inline_id": None}
    reaction_games[gid] = state
    try:
        msg = bot.send_message(chat_id, "⚡ Блиц-реакция\nЖдите сигнала и нажмите кнопку!", reply_markup=_reaction_keyboard(gid))
        state["msg_id"] = msg.message_id
        _room_track_message_id(chat_id, msg.message_id)
    except Exception:
        state["msg_id"] = None

    def trigger():
        time.sleep(random.uniform(2.0, 5.0))
        if gid not in reaction_games:
            return
        st = reaction_games[gid]
        st["started"] = True
        st["start_at"] = time.time()
        reaction_games[gid] = st
        _reaction_edit(st, "⚡ СИГНАЛ! ЖМИ СЕЙЧАС!", reply_markup=_reaction_keyboard(gid))

    Thread(target=trigger, daemon=True).start()
    return gid

# ------------------- BLACKJACK -------------------
BJ_SUITS = ["♠", "♥", "♦", "♣"]
BJ_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

def _bj_make_deck():
    return [(r, s) for s in BJ_SUITS for r in BJ_RANKS]

def _bj_card_value(rank):
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)

def _bj_hand_value(hand):
    total = 0
    aces = 0
    for r, _ in hand:
        val = _bj_card_value(r)
        total += val
        if r == "A":
            aces += 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def _bj_card_str(card):
    r, s = card
    return f"{r}{s}"

def _bj_render_text(state, reveal_dealer=False):
    player = state.get("player", [])
    dealer = state.get("dealer", [])
    player_val = _bj_hand_value(player)
    if reveal_dealer:
        dealer_cards = " ".join(_bj_card_str(c) for c in dealer)
        dealer_val = _bj_hand_value(dealer)
        dealer_line = f"🃏 Дилер: {dealer_cards} ({dealer_val})"
    else:
        if dealer:
            dealer_cards = _bj_card_str(dealer[0]) + " ??"
        else:
            dealer_cards = "??"
        dealer_line = f"🃏 Дилер: {dealer_cards}"
    player_cards = " ".join(_bj_card_str(c) for c in player) if player else "—"
    return (
        "🃏 Блэкджек\n"
        f"{dealer_line}\n"
        f"🙂 Вы: {player_cards} ({player_val})"
    )

def _bj_keyboard(gid, status):
    kb = types.InlineKeyboardMarkup()
    if status == "playing":
        kb.row(
            types.InlineKeyboardButton("➕ Взять", callback_data=f"bj_hit_{gid}"),
            types.InlineKeyboardButton("🛑 Стоп", callback_data=f"bj_stand_{gid}")
        )
    else:
        kb.add(types.InlineKeyboardButton("🔁 Новая партия", callback_data=f"bj_new_{gid}"))
    return kb

def _bj_new_game(uid, chat_id):
    deck = _bj_make_deck()
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    state = {
        "uid": uid,
        "chat_id": chat_id,
        "deck": deck,
        "player": player,
        "dealer": dealer,
        "status": "playing",
        "result": None,
        "recorded": False,
    }
    player_val = _bj_hand_value(player)
    dealer_val = _bj_hand_value(dealer)
    if player_val == 21:
        state["status"] = "ended"
        if dealer_val == 21:
            state["result"] = "draws"
        else:
            state["result"] = "wins"
    return state

def _wordle_new_game(owner_id):
    return {
        "owner": owner_id,
        "target": random.choice(WORDLE_WORDS),
        "attempts": [],
        "current": "",
        "status": "playing",
    }

def _wordle_eval_guess(guess, target):
    marks = ["⬛"] * 5
    rem = {}
    for i in range(5):
        if guess[i] == target[i]:
            marks[i] = "🟩"
        else:
            rem[target[i]] = rem.get(target[i], 0) + 1
    for i in range(5):
        if marks[i] == "🟩":
            continue
        ch = guess[i]
        if rem.get(ch, 0) > 0:
            marks[i] = "🟨"
            rem[ch] -= 1
    return marks

def _wordle_render_text(game):
    lines = []
    for row in game.get("attempts", []):
        lines.append(f"{row['guess'].upper()}  {''.join(row['marks'])}")
    while len(lines) < 6:
        lines.append("_____  ⬜⬜⬜⬜⬜")

    text = "🟩 Wordle\n\n"
    text += "\n".join(lines)
    text += f"\n\nТекущий ввод: {(game.get('current') or '').upper() or '_____'}"
    text += f"\nПопыток: {len(game.get('attempts', []))}/6"
    if game.get("status") == "won":
        text += "\n\n🎉 Победа! Вы угадали слово."
    elif game.get("status") == "lost":
        text += f"\n\n💀 Поражение. Слово: {game.get('target','').upper()}"
    else:
        text += "\n\nВведите слово из 5 букв и нажмите «✅ Готово»."
    return text

def _wordle_keyboard(gid, game):
    kb = types.InlineKeyboardMarkup()
    if game.get("status") != "playing":
        kb.add(types.InlineKeyboardButton("🔄 Новая игра", callback_data=f"wrdl_new_{gid}"))
        return kb

    for row in ("йцукенгшщзх", "фывапролджэ", "ячсмитьбю"):
        kb.row(*[types.InlineKeyboardButton(ch.upper(), callback_data=f"wrdl_l_{gid}_{ch}") for ch in row])
    kb.row(
        types.InlineKeyboardButton("⌫", callback_data=f"wrdl_back_{gid}"),
        types.InlineKeyboardButton("✅ Готово", callback_data=f"wrdl_submit_{gid}")
    )
    return kb

def start_wordle_in_chat(chat_id, owner_id):
    gid = short_id()
    game = _wordle_new_game(owner_id)
    wordle_games[gid] = game
    bot.send_message(chat_id, _wordle_render_text(game), reply_markup=_wordle_keyboard(gid, game))

def _chess_new_game(owner_id, owner_name=None):
    board = [
        ["br", "bn", "bb", "bq", "bk", "bb", "bn", "br"],
        ["bp", "bp", "bp", "bp", "bp", "bp", "bp", "bp"],
        [None, None, None, None, None, None, None, None],
        [None, None, None, None, None, None, None, None],
        [None, None, None, None, None, None, None, None],
        [None, None, None, None, None, None, None, None],
        ["wp", "wp", "wp", "wp", "wp", "wp", "wp", "wp"],
        ["wr", "wn", "wb", "wq", "wk", "wb", "wn", "wr"],
    ]
    return {
        "owner": owner_id,
        "p1": owner_id,
        "p1_name": owner_name or str(owner_id),
        "p2": None,
        "p2_name": None,
        "turn": "w",
        "board": board,
        "selected": None,
        "status": "waiting",  # waiting, playing, ended
        "winner": None,
    }

def _chess_lost_counts(game):
    board = game["board"]
    white_now = 0
    black_now = 0
    for r in range(8):
        for c in range(8):
            piece = board[r][c]
            if not piece:
                continue
            if piece[0] == "w":
                white_now += 1
            else:
                black_now += 1
    # сколько фигур у этой стороны забрали
    return (16 - white_now), (16 - black_now)

def _chess_piece_emoji(piece):
    mapping = {
        "wp": "♙", "wr": "♖", "wn": "♘", "wb": "♗", "wq": "♕", "wk": "♔",
        "bp": "♟", "br": "♜", "bn": "♞", "bb": "♝", "bq": "♛", "bk": "♚",
    }
    return mapping.get(piece, "·")

def _chess_in_bounds(r, c):
    return 0 <= r < 8 and 0 <= c < 8

def _chess_get_player_color(game, user_id):
    if user_id == game.get("p1"):
        return "w"
    if user_id == game.get("p2"):
        return "b"
    return None

def _chess_legal_moves(board, r, c):
    piece = board[r][c]
    if not piece:
        return []
    color = piece[0]
    kind = piece[1]
    enemy = "b" if color == "w" else "w"
    moves = []

    def add_line(dr, dc):
        nr, nc = r + dr, c + dc
        while _chess_in_bounds(nr, nc):
            target = board[nr][nc]
            if target is None:
                moves.append((nr, nc))
            else:
                if target[0] == enemy:
                    moves.append((nr, nc))
                break
            nr += dr
            nc += dc

    if kind == "p":
        step = -1 if color == "w" else 1
        start_row = 6 if color == "w" else 1
        nr = r + step
        if _chess_in_bounds(nr, c) and board[nr][c] is None:
            moves.append((nr, c))
            nr2 = r + 2 * step
            if r == start_row and _chess_in_bounds(nr2, c) and board[nr2][c] is None:
                moves.append((nr2, c))
        for dc in (-1, 1):
            nc = c + dc
            if _chess_in_bounds(nr, nc) and board[nr][nc] is not None and board[nr][nc][0] == enemy:
                moves.append((nr, nc))
    elif kind == "n":
        for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
            nr, nc = r + dr, c + dc
            if not _chess_in_bounds(nr, nc):
                continue
            target = board[nr][nc]
            if target is None or target[0] == enemy:
                moves.append((nr, nc))
    elif kind == "b":
        add_line(1, 1)
        add_line(1, -1)
        add_line(-1, 1)
        add_line(-1, -1)
    elif kind == "r":
        add_line(1, 0)
        add_line(-1, 0)
        add_line(0, 1)
        add_line(0, -1)
    elif kind == "q":
        add_line(1, 1)
        add_line(1, -1)
        add_line(-1, 1)
        add_line(-1, -1)
        add_line(1, 0)
        add_line(-1, 0)
        add_line(0, 1)
        add_line(0, -1)
    elif kind == "k":
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if not _chess_in_bounds(nr, nc):
                    continue
                target = board[nr][nc]
                if target is None or target[0] == enemy:
                    moves.append((nr, nc))
    return moves

def _chess_apply_move(game, fr, fc, tr, tc):
    board = game["board"]
    piece = board[fr][fc]
    target = board[tr][tc]
    board[tr][tc] = piece
    board[fr][fc] = None
    if piece in ("wp", "bp") and (tr == 0 or tr == 7):
        board[tr][tc] = piece[0] + "q"
    if target in ("wk", "bk"):
        game["status"] = "ended"
        game["winner"] = piece[0]
    else:
        game["turn"] = "b" if game["turn"] == "w" else "w"
    game["selected"] = None

def _chess_render_text(game):
    board = game["board"]
    w_lost, b_lost = _chess_lost_counts(game)
    p1_name = game.get("p1_name") or str(game.get("p1", "Игрок 1"))
    p2_name = game.get("p2_name") or (str(game.get("p2")) if game.get("p2") else "ожидается")
    lines = []
    for r in range(8):
        rank = 8 - r
        row = []
        for c in range(8):
            row.append(_chess_piece_emoji(board[r][c]))
        lines.append(f"{rank} " + " ".join(row))
    lines.append("  a b c d e f g h")
    text = "♟ Шахматы\n\n"
    text += f"Белые: {p1_name} | Цвет: белый | Потеряно фигур: {w_lost}\n"
    text += f"Черные: {p2_name} | Цвет: черный | Потеряно фигур: {b_lost}\n\n"
    text += "\n".join(lines)

    if game.get("status") == "waiting":
        text += "\n\nОжидание второго игрока."
    elif game.get("status") == "ended":
        winner = "Белые" if game.get("winner") == "w" else "Черные"
        text += f"\n\nПобеда: {winner}"
    else:
        turn_name = "Белые" if game.get("turn") == "w" else "Черные"
        text += f"\n\nХод: {turn_name}"
    return text

def _chess_keyboard(gid, game):
    kb = types.InlineKeyboardMarkup(row_width=8)
    if game.get("status") == "waiting":
        kb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"chess_join_{gid}"))
        return kb
    if game.get("status") == "ended":
        kb.add(types.InlineKeyboardButton("Новая партия", callback_data=f"chess_new_{gid}"))
        return kb
    selected = game.get("selected")
    legal = set()
    if selected:
        sr, sc = selected
        legal = set(_chess_legal_moves(game["board"], sr, sc))
    for r in range(8):
        row = []
        for c in range(8):
            piece = game["board"][r][c]
            mark = _chess_piece_emoji(piece)
            if selected == (r, c):
                mark = "🔷"
            elif (r, c) in legal:
                mark = "🟩"
            row.append(types.InlineKeyboardButton(mark, callback_data=f"chess_c_{gid}_{r}_{c}"))
        kb.row(*row)
    kb.add(types.InlineKeyboardButton("Сброс выбора", callback_data=f"chess_reset_{gid}"))
    return kb

# ------------------- KEYBOARDS -------------------
def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✖️ Крестики-нолики", "💰 Миллионер")
    kb.add("💬 Режим ИИ", "🐣 Пасхалка")
    kb.add("🪙 Орёл или решка", "🖥 TELOS v1.0")
    kb.add("🔢 Угадай число", "✂ Камень-ножницы-бумага")
    kb.add("⚡ Блиц-реакция", "🃏 Блэкджек")
    kb.add("🐍 Змейка", "🎰 Казино")
    kb.add("🐦 Flappy Bird", "🔢 2048")
    kb.add("🏓 Пинг-понг", "🕵️‍♀️ Прятки")
    kb.add("🔤 Виселица", "💣 Сапёр")
    kb.add("🔤 Викторина", "♟ Шахматы")
    kb.add("⚡ Комбо-битва", "🔔 Ваше уведомление")
    kb.add("🎭 Мафия", "🧱 Тетрис")
    kb.add("🟢 Wordle")
    kb.add("🏆 Достижения", "🏠 Пати")
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
    if not prompt.strip():
        return "⚠️ Напиши вопрос текстом"

    mode = user_ai_mode.get(user_id, "chat")
    system_prompt = AI_MODES.get(mode, AI_MODES["chat"])

    def _is_retryable_ai_error(err: Exception) -> bool:
        msg = str(err).lower()
        retry_markers = (
            "client_responce_parse_failed",
            "client_response_parse_failed",
            "timeout",
            "timed out",
            "connection",
            "temporar",
            "429",
            "rate limit",
            "service unavailable",
            "bad gateway",
        )
        return any(marker in msg for marker in retry_markers)

    last_err = None
    for attempt in range(3):
        try:
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
            last_err = e
            print(f"AI ERROR attempt {attempt + 1}/3:", repr(e))
            if attempt < 2 and _is_retryable_ai_error(e):
                time.sleep(1.2 + attempt)
                continue
            break

    print("AI FINAL ERROR:", repr(last_err))
    return "❌ Временная ошибка AI-сервиса. Нажмите «Обновить» или «Получить ответ» ещё раз."

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
        "main_menu": "Добро пожаловать в бота с мини играми!",
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
    bot.send_message(message.chat.id, t(uid, "main_menu"), reply_markup=_start_info_kb())
    bot.send_message(message.chat.id, "Выберите игру или функцию из меню ниже.", reply_markup=menu_kb)

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

@bot.chosen_inline_handler(func=lambda r: True)
def chosen_inline_track(result):
    return

@bot.message_handler(commands=["profile"])
def profile_cmd(message):
    uid = message.from_user.id
    update_user_streak(uid, message.from_user.first_name or message.from_user.username or str(uid))
    bot.send_message(message.chat.id, _render_profile_text(uid))


@bot.message_handler(commands=["shop"])
def shop_cmd(message):
    uid = message.from_user.id
    bot.send_message(message.chat.id, _shop_render_text(uid), reply_markup=_shop_items_kb(uid))


@bot.callback_query_handler(func=lambda c: c.data.startswith("shop_"))
def shop_callbacks(call):
    try:
        uid = call.from_user.id
        data = call.data
        if data == "shop_open":
            safe_edit_message(call, _shop_render_text(uid), reply_markup=_shop_items_kb(uid))
            bot.answer_callback_query(call.id)
            return

        parts = data.split("_", 2)
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Неверные данные")
            return
        action = parts[1]
        item_id = parts[2]
        item = SHOP_ITEMS.get(item_id)
        if not item:
            bot.answer_callback_query(call.id, "Товар не найден")
            return

        d = load_data()
        rec = d.setdefault("users", {}).setdefault(str(uid), {})
        rec = _ensure_profile_fields(rec)
        inv = rec.setdefault("inventory", [])
        coins = int(rec.get("coins", 0) or 0)

        if action == "buy":
            if item_id in inv:
                bot.answer_callback_query(call.id, "Уже куплено")
            elif coins < int(item["price"]):
                bot.answer_callback_query(call.id, "Недостаточно монет")
            else:
                rec["coins"] = coins - int(item["price"])
                inv.append(item_id)
                d["users"][str(uid)] = rec
                save_data(d)
                bot.answer_callback_query(call.id, f"Покупка: {item['name']}")
            safe_edit_message(call, _shop_render_text(uid), reply_markup=_shop_items_kb(uid))
            return

        if action == "apply":
            if item_id not in inv:
                bot.answer_callback_query(call.id, "Сначала купите товар")
                return
            if item["type"] == "avatar":
                rec["avatar_emoji"] = item["value"]
            elif item["type"] == "frame":
                rec["frame_style"] = item["value"]
            elif item["type"] == "theme":
                rec["theme_style"] = item["value"]
            elif item["type"] == "victory":
                rec["victory_emoji"] = item["value"]
            d["users"][str(uid)] = rec
            save_data(d)
            safe_edit_message(call, _shop_render_text(uid), reply_markup=_shop_items_kb(uid))
            bot.answer_callback_query(call.id, f"Применено: {item['name']}")
            return

        bot.answer_callback_query(call.id, "Неизвестное действие")
    except Exception as e:
        print("SHOP CALLBACK ERROR:", e)
        try:
            bot.answer_callback_query(call.id, "Ошибка магазина")
        except Exception:
            pass

def _admin_panel_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📊 Сводка", callback_data="admin_stats"))
    kb.add(types.InlineKeyboardButton("👥 Все игроки", callback_data="admin_users"))
    kb.add(types.InlineKeyboardButton("📈 Популярные игры", callback_data="admin_games"))
    kb.add(types.InlineKeyboardButton("💰 Топ по монетам", callback_data="admin_coins"))
    kb.add(types.InlineKeyboardButton("🏠 Комнаты", callback_data="admin_rooms"))
    kb.add(types.InlineKeyboardButton("🧹 Закрыть комнату", callback_data="admin_close_room"))
    kb.add(types.InlineKeyboardButton("🏆 Достижения", callback_data="admin_achievements"))
    kb.add(types.InlineKeyboardButton("📣 Рассылка", callback_data="admin_broadcast"))
    return kb

def _broadcast_menu_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("1. Изменить текст сообщения", callback_data="messagenot_msg"))
    kb.add(types.InlineKeyboardButton("2. Изменить текст кнопки", callback_data="messagenot_btn"))
    kb.add(types.InlineKeyboardButton("3. Изменить тип кнопки", callback_data="messagenot_type"))
    kb.add(types.InlineKeyboardButton("4. Отправить всем", callback_data="messagenot_send"))
    return kb

def _send_broadcast_menu(chat_id):
    bot.send_message(chat_id, "⚙️ Настройки рассылки — выберите действие:", reply_markup=_broadcast_menu_kb())

@bot.message_handler(commands=["adminpanel"])
def admin_panel_cmd(message):
    uid = message.from_user.id
    if uid not in SUPPORT_ADMIN_IDS:
        bot.send_message(message.chat.id, "⛔ Доступ запрещен.")
        return
    bot.send_message(message.chat.id, "🛠 Админ-панель", reply_markup=_admin_panel_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_"))
def admin_panel_callbacks(call):
    uid = call.from_user.id
    if uid not in SUPPORT_ADMIN_IDS:
        try:
            bot.answer_callback_query(call.id, "Нет доступа", show_alert=True)
        except Exception:
            pass
        return

    data = call.data
    if data == "admin_stats":
        d = load_data()
        users = d.get("users", {})
        total_users = len(users)
        total_games = 0
        total_coins = 0
        premium_count = 0
        now_ts = time.time()
        for rec in users.values():
            if not isinstance(rec, dict):
                continue
            total_games += int(rec.get("games_total", 0) or 0)
            total_coins += int(rec.get("coins", 0) or 0)
            if int(rec.get("premium_until", 0) or 0) > now_ts:
                premium_count += 1
        rooms = d.get("rooms", {})
        pool_count = len(rooms.get("pool", []) or [])
        active_count = len(rooms.get("active", {}) or {})
        text = (
            "📊 Сводка\n\n"
            f"👥 Пользователей: {total_users}\n"
            f"🎮 Сыграно игр: {total_games}\n"
            f"🪙 Монет в системе: {total_coins}\n"
            f"💎 Премиум активен: {premium_count}\n"
            f"🏠 Комнаты: активные {active_count}, пул {pool_count}\n"
        )
        safe_edit_message(call, text, reply_markup=_admin_panel_kb())
        return
    if data == "admin_users":
        d = load_data()
        users = d.get("users", {})
        rows = []
        for uid_str, rec in users.items():
            if not isinstance(rec, dict):
                continue
            total = int(rec.get("games_total", 0) or 0)
            name = rec.get("display_name") or f"user_{uid_str}"
            rows.append((total, str(name), uid_str))
        rows.sort(key=lambda x: (-x[0], x[1].lower()))
        text = f"👥 Всего пользователей: {len(users)}\n\n"
        if rows:
            text += "Топ по сыгранным играм:\n"
            for i, (total, name, uid_str) in enumerate(rows[:20], 1):
                text += f"{i}. {name} (ID {uid_str}) — {total}\n"
        else:
            text += "Нет данных."
        safe_edit_message(call, text, reply_markup=_admin_panel_kb())
        return

    if data == "admin_games":
        d = load_data()
        global_stats = d.get("global_game_stats", {})
        rows = sorted(global_stats.items(), key=lambda kv: int(kv[1] or 0), reverse=True)
        text = "📈 Популярные игры:\n\n"
        if rows:
            for i, (gk, cnt) in enumerate(rows[:20], 1):
                text += f"{i}. {GAME_TITLES.get(gk, gk)} — {int(cnt or 0)}\n"
        else:
            text += "Пока нет статистики."
        safe_edit_message(call, text, reply_markup=_admin_panel_kb())
        return

    if data == "admin_coins":
        d = load_data()
        users = d.get("users", {})
        rows = []
        for uid_str, rec in users.items():
            if not isinstance(rec, dict):
                continue
            coins = int(rec.get("coins", 0) or 0)
            name = rec.get("display_name") or f"user_{uid_str}"
            rows.append((coins, str(name), uid_str))
        rows.sort(key=lambda x: (-x[0], x[1].lower()))
        text = "💰 Топ по монетам:\n\n"
        if rows:
            for i, (coins, name, uid_str) in enumerate(rows[:20], 1):
                text += f"{i}. {name} (ID {uid_str}) — {coins}\n"
        else:
            text += "Пока нет данных."
        safe_edit_message(call, text, reply_markup=_admin_panel_kb())
        return

    if data == "admin_rooms":
        d = load_data()
        rooms = d.get("rooms", {})
        active = rooms.get("active", {}) or {}
        text = "🏠 Активные комнаты:\n\n"
        if active:
            for code, room in active.items():
                if not isinstance(room, dict):
                    continue
                chat_id = room.get("chat_id")
                creator = room.get("creator_name") or room.get("creator_id")
                ends_at = room.get("ends_at")
                ends_str = datetime.fromtimestamp(ends_at).strftime("%Y-%m-%d %H:%M:%S") if ends_at else "—"
                text += f"• {code} | chat {chat_id} | {creator} | до {ends_str}\n"
        else:
            text += "Нет активных комнат."
        safe_edit_message(call, text, reply_markup=_admin_panel_kb())
        return

    if data == "admin_close_room":
        admin_wait[uid] = {"action": "close_room"}
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        bot.send_message(uid, "Введите код комнаты для закрытия (например: A1B2C):")
        return

    if data == "admin_achievements":
        d = load_data()
        users = d.get("users", {})
        counts = {k: 0 for k in ACHIEVEMENTS.keys()}
        for rec in users.values():
            if not isinstance(rec, dict):
                continue
            ach = rec.get("achievements", {})
            if not isinstance(ach, dict):
                continue
            for key in counts.keys():
                if key in ach:
                    counts[key] += 1
        text = "🏆 Достижения (кол-во открытий):\n\n"
        for key, meta in ACHIEVEMENTS.items():
            text += f"• {meta['title']}: {counts.get(key, 0)}\n"
        safe_edit_message(call, text, reply_markup=_admin_panel_kb())
        return

    if data == "admin_broadcast":
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        _send_broadcast_menu(call.message.chat.id if call.message else uid)
        return

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

    _send_broadcast_menu(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith(("messagenot_msg","messagenot_btn","messagenot_type","messagenot_send")))
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


@bot.callback_query_handler(func=lambda c: c.data.startswith("messagenot_type_link"))
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
    bot.send_message(message.chat.id, "Чтобы играть в тетрис — напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🕵️‍♀️ Прятки")
def hideandseek(message):
    bot.send_message(message.chat.id, "Чтобы играть в прятки — напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎭 Мафия")
def mafia(message):
    bot.send_message(message.chat.id, "Чтобы играть в мафию — напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "✖️ Крестики-нолики")
def ttt(message):
    bot.send_message(message.chat.id, "Чтобы играть в крестики-нолики — напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "💰 Миллионер")
def millionaire(message):
    bot.send_message(message.chat.id, "Чтобы играть в миллионер — напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🟢 Wordle")
def wordle(message):
    bot.send_message(message.chat.id, "Чтобы играть в Wordle — напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "♟ Шахматы")
def chess_menu(message):
    bot.send_message(message.chat.id, "Чтобы играть в шахматы — напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "💬 Режим ИИ")
def ai_mode(message):
    bot.send_message(message.chat.id, f"Чтобы использовать режим ИИ — напишите <code>@{INLINE_BOT_USERNAME}</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Информация о боте")
def bot_info(message):
    bot.send_message(
        message.chat.id,
        "Этот бот создан для мини-игр в Telegram.\n"
        "Он позволяет играть одному и с друзьями через inline-режим, "
        "а также использовать дополнительные функции: профиль, поддержку и рассылку.",
    )

@bot.message_handler(func=lambda m: m.text == "📋 Скопировать username")
def copy_bot_username(message):
    bot.send_message(
        message.chat.id,
        f"Username бота: <code>@{INLINE_BOT_USERNAME}</code>\n"
        "Нажмите и удерживайте, чтобы скопировать.",
        parse_mode="HTML",
    )

@bot.message_handler(func=lambda m: m.text == "📖 Инструкция")
def bot_instruction(message):
    bot.send_message(
        message.chat.id,
        "Как играть:\n"
        "1. В любом чате введите <code>@{}</code>\n"
        "2. Выберите игру из inline-списка\n"
        "3. Отправьте игру в чат и нажимайте кнопки\n"
        "4. Для личной статистики используйте /profile".format(INLINE_BOT_USERNAME),
        parse_mode="HTML",
    )

@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile_button(message):
    uid = message.from_user.id
    update_user_streak(uid, message.from_user.first_name or message.from_user.username or str(uid))
    bot.send_message(message.chat.id, _render_profile_text(uid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("start_"))
def start_info_callbacks(call):
    try:
        data = call.data
        if data == "start_info":
            safe_edit_message(
                call,
                "Этот бот создан для мини-игр в Telegram.\n"
                "Он позволяет играть одному и с друзьями, "
                "полностью бесплатно!",
                reply_markup=_start_info_kb(),
            )
        elif data == "start_instruction":
            safe_edit_message(
                call,
                "Инструкция:\n"
                "1. Скопируйте юзернейм <code>@{}</code>\n"
                "2. Выберите игру из списка\n"
                "3. Нажмите на игру\n"
                "4. Играйте!".format(INLINE_BOT_USERNAME),
                parse_mode="HTML",
                reply_markup=_start_info_kb(),
            )
        elif data == "start_username":
            safe_edit_message(
                call,
                f"Скопировать юзернейм:\n<code>@{INLINE_BOT_USERNAME}</code>\n"
                "Нажмите и удерживайте юзернейм, затем выберите «Копировать».",
                parse_mode="HTML",
                reply_markup=_start_info_kb(),
            )
        elif data == "start_profile":
            uid = call.from_user.id
            update_user_streak(uid, call.from_user.first_name or call.from_user.username or str(uid))
            safe_edit_message(call, _render_profile_text(uid), reply_markup=_start_info_kb())
        elif data == "start_shop":
            uid = call.from_user.id
            safe_edit_message(call, _shop_render_text(uid), reply_markup=_shop_items_kb(uid))
        elif data == "start_support":
            safe_edit_message(call, _support_text(), reply_markup=_support_menu_kb())
        bot.answer_callback_query(call.id)
    except Exception as e:
        print("START INFO CALLBACK ERROR:", e)
        try:
            bot.answer_callback_query(call.id, "Ошибка")
        except Exception:
            pass

@bot.message_handler(func=lambda m: m.text == "🐣 Пасхалка")
def pashalka(message):
    bot.send_message(message.chat.id, "Чтобы запустить анимацию пасхалки - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🪙 Орёл или решка")
def orel(message):
    bot.send_message(message.chat.id, "Чтобы играть в орёл или решка - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🔔 Ваше уведомление")
def notification(message):
    bot.send_message(message.chat.id, "Чтобы настроить системное уведомление - напишите <code>/settext</code>", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🖥 TELOS v1.0")
def telos(message):
    uid = message.from_user.id
    st = _telos_get_state(uid)
    st["booted"] = True
    _telos_save_state(uid, st)
    bot.send_message(message.chat.id, _telos_home_text(uid), parse_mode="Markdown", reply_markup=telos_main_menu())

@bot.message_handler(func=lambda m: m.text == "🔢 Угадай число")
def ugadayka(message):
    bot.send_message(message.chat.id, "Чтобы играть в угадай число - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "✂ Камень-ножницы-бумага")
def rsp(message):
    bot.send_message(message.chat.id, f"Чтобы играть в камень ножницы бумага - напишите <code>@{INLINE_BOT_USERNAME}</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🐍 Змейка")
def snake(message):
    bot.send_message(message.chat.id, "Чтобы играть в змейку - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎰 Казино")
def casino(message):
    bot.send_message(message.chat.id, "Чтобы запустить казино - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

def _start_flappy_pm(chat_id, user_id):
    state = _new_flappy_state()
    state["chat_id"] = chat_id
    state["owner_id"] = user_id
    state["message_id"] = None
    state["loop_running"] = False
    sent = bot.send_message(chat_id, _render_flappy_pm_text(state), reply_markup=_flappy_pm_markup(user_id))
    state["message_id"] = sent.message_id
    pm_flappy_games[user_id] = state
    return state

@bot.message_handler(commands=["flappy"])
def flappybird_command(message):
    if message.chat.type != "private":
        bot.send_message(message.chat.id, f"Эту версию Flappy Bird лучше запускать в ЛС с ботом: <code>@{INLINE_BOT_USERNAME}</code>", parse_mode="HTML")
        return
    _start_flappy_pm(message.chat.id, message.from_user.id)

@bot.message_handler(func=lambda m: m.text == "🐦 Flappy Bird")
def flappybird(message):
    if message.chat.type != "private":
        bot.send_message(message.chat.id, "Чтобы играть в flappy Bird - откройте ЛС с ботом и нажмите эту кнопку там.")
        return
    _start_flappy_pm(message.chat.id, message.from_user.id)

@bot.message_handler(func=lambda m: m.text == "🔢 2048")
def dvsorokvosem(message):
    bot.send_message(message.chat.id, "Чтобы играть в 2048 - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🏓 Пинг-понг")
def pingpong(message):
    bot.send_message(message.chat.id, "Чтобы играть в пинг-понг - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

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
        f"1. Скопируйте имя <code>@{INLINE_BOT_USERNAME}</code>\n"
        "2. Откройте: Настройки → Telegram для бизнеса → Чат-боты\n"
        "3. Добавьте бота и примените настройки\n\n"
        "После подключения просто отправьте в бизнес-чат название игры.",
        parse_mode="HTML",
    )

def _support_text():
    return "🛠 Выберите действие:"

def _is_support_admin(uid):
    return uid in SUPPORT_ADMIN_IDS

def _support_menu_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💬 Написать модератору", callback_data="support_mode_moderator"))
    kb.add(types.InlineKeyboardButton("🐞 Отправить проблему", callback_data="support_mode_issue"))
    return kb

def _support_mode_prompt(mode):
    if mode == "moderator":
        return (
            "💬 Режим: написать модератору.\n"
            "Отправьте сообщение одним текстом.\n"
            "Для отмены: /cancelsupport"
        )
    return (
        "🐞 Режим: отправить проблему.\n"
        "Пришлите описание, скриншот или видео (можно с подписью).\n"
        "Для отмены: /cancelsupport"
    )

def _start_info_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("ℹ️ Информация о боте", callback_data="start_info"),
        types.InlineKeyboardButton("📖 Инструкция", callback_data="start_instruction"),
    )
    kb.row(
        types.InlineKeyboardButton("📋 Скопировать юзернейм", callback_data="start_username"),
        types.InlineKeyboardButton("👤 Профиль", callback_data="start_profile"),
    )
    kb.row(
        types.InlineKeyboardButton("🛍 Магазин", callback_data="start_shop"),
        types.InlineKeyboardButton("🛠 Поддержка", callback_data="start_support"),
    )
    return kb

@bot.message_handler(commands=["support"])
def support_command(message):
    bot.send_message(message.chat.id, _support_text(), reply_markup=_support_menu_kb())

@bot.message_handler(func=lambda m: m.text == "🛠 Поддержка")
def support_menu(message):
    bot.send_message(message.chat.id, _support_text(), reply_markup=_support_menu_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("support_mode_"))
def support_mode_callback(call):
    mode = call.data.split("_", 2)[2] if "_" in call.data else ""
    if mode not in ("moderator", "issue"):
        try:
            bot.answer_callback_query(call.id, "Неизвестный режим")
        except Exception:
            pass
        return
    if not SUPPORT_ADMIN_IDS:
        try:
            bot.answer_callback_query(call.id, "Поддержка через модераторов недоступна", show_alert=True)
        except Exception:
            pass
        return
    uid = call.from_user.id
    support_chat_wait[uid] = mode
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    bot.send_message(uid, _support_mode_prompt(mode))

@bot.message_handler(commands=["cancelsupport"])
def cancel_support_chat(message):
    support_chat_wait.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "❌ Режим поддержки отменён.")

@bot.message_handler(commands=["reply"])
def support_admin_reply(message):
    uid = message.from_user.id
    if not _is_support_admin(uid):
        return
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        bot.send_message(
            message.chat.id,
            "Формат: /reply <user_id> <текст>\nПример: /reply 123456789 Здравствуйте, проверяем проблему."
        )
        return
    target_uid = int(parts[1])
    reply_text = parts[2].strip()
    if not reply_text:
        bot.send_message(message.chat.id, "Текст ответа пуст.")
        return
    try:
        bot.send_message(target_uid, f"💬 Ответ поддержки:\n{reply_text}")
        bot.send_message(message.chat.id, f"✅ Ответ отправлен пользователю {target_uid}.")
    except Exception:
        bot.send_message(message.chat.id, "❌ Не удалось отправить ответ пользователю.")

@bot.message_handler(func=lambda m: m.text == "🚀 Поддержать автора")
def support_donate(message):
    bot.send_message(message.chat.id, "Если вам нравится этот бот, вы можете поддержать автора отправив тон на адрес:\n\n💳 <code>UQDla14mdjvSsjI1KMJ8cktcbn-smuKXwmFJXPdRT95-k4qQ</code>\n\nЗаранее cпасибо вашу поддержку!", parse_mode="HTML")

@bot.message_handler(commands=["achievements"])
def achievements_cmd(message):
    bot.send_message(message.chat.id, _render_achievements_text(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🏆 Достижения")
def achievements_btn(message):
    bot.send_message(message.chat.id, _render_achievements_text(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "🏠 Пати")
def room_menu_btn(message):
    bot.send_message(
        message.chat.id,
        "🏠 Пати:\n"
        "• Создать: /party\n"
        "• Войти по коду: /party_join <КОД>\n"
        "• Статус в группе: /party_status\n"
        "• Для админов групп: /party_register или /party_unregister"
    )

@bot.message_handler(commands=["party_register"])
def room_register_cmd(message):
    if message.chat.type not in ("group", "supergroup"):
        bot.send_message(message.chat.id, "Команду /party_register можно использовать только в группе.")
        return
    if not _is_group_admin(message.chat.id, message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Только администратор может зарегистрировать пати.")
        return
    d, rooms = _rooms_get_data()
    pool = rooms.get("pool", [])
    if message.chat.id not in pool:
        pool.append(message.chat.id)
    rooms["pool"] = pool
    rooms["free_title"] = rooms.get("free_title", ROOM_FREE_TITLE)
    save_data(d)
    try:
        bot.set_chat_title(message.chat.id, rooms.get("free_title", ROOM_FREE_TITLE))
    except Exception:
        pass
    bot.send_message(message.chat.id, "✅ Группа зарегистрирована как пати. Статус: свободно.")

@bot.message_handler(commands=["room_unregister"])
def room_unregister_cmd(message):
    if message.chat.type not in ("group", "supergroup"):
        bot.send_message(message.chat.id, "Команду /room_unregister можно использовать только в группе.")
        return
    if not _is_group_admin(message.chat.id, message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Только администратор может удалить комнату из пула.")
        return
    d, rooms = _rooms_get_data()
    pool = rooms.get("pool", [])
    if message.chat.id in pool:
        pool = [cid for cid in pool if cid != message.chat.id]
        rooms["pool"] = pool
        save_data(d)
        bot.send_message(message.chat.id, "✅ Группа удалена из пула комнат.")
    else:
        bot.send_message(message.chat.id, "ℹ️ Эта группа не зарегистрирована.")

@bot.message_handler(commands=["room_status"])
def room_status_cmd(message):
    if message.chat.type not in ("group", "supergroup"):
        bot.send_message(message.chat.id, "Команда доступна только в группе.")
        return
    d, rooms = _rooms_get_data()
    code, room = _room_find_by_chat(rooms, message.chat.id)
    if not room:
        bot.send_message(message.chat.id, "ℹ️ Эта группа сейчас свободна.")
        return
    ends_at = room.get("ends_at")
    ends_str = datetime.fromtimestamp(ends_at).strftime("%Y-%m-%d %H:%M:%S") if ends_at else "—"
    bot.send_message(message.chat.id, f"🔒 Пати занят\nКод: {code}\nДо: {ends_str}")

@bot.message_handler(commands=["end"])
def room_end_cmd(message):
    if message.chat.type not in ("group", "supergroup"):
        bot.send_message(message.chat.id, "Команда /end работает только в группе.")
        return
    if not _is_group_admin(message.chat.id, message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Только администратор может завершить пати.")
        return
    d, rooms = _rooms_get_data()
    code, room = _room_find_by_chat(rooms, message.chat.id)
    if not room:
        bot.send_message(message.chat.id, "ℹ️ В этой группе нет активной пати.")
        return
    bot.send_message(message.chat.id, "⏳ Завершаю пати и очищаю участников...")
    _room_close(code, reason="завершено вручную")

@bot.message_handler(commands=["party_create"])
def party_create_cmd(message):
    if message.chat.type != "private":
        bot.send_message(message.chat.id, "Создание пати доступно только в личных сообщениях.")
        return
    d, rooms = _rooms_get_data()
    chat_id = _room_pick_free_chat(rooms)
    if not chat_id:
        bot.send_message(message.chat.id, "❌ Нет свободных групп. Попробуйте через 5 минут.")
        return
    code = _room_generate_code(rooms)
    creator = message.from_user
    creator_name = creator.username or creator.first_name or f"user_{creator.id}"
    now_ts = time.time()
    room = {
        "code": code,
        "chat_id": chat_id,
        "creator_id": creator.id,
        "creator_name": creator_name,
        "created_at": now_ts,
        "ends_at": now_ts + ROOM_TTL_SECONDS,
        "status": "voting",
        "participants": [creator.id],
    }
    rooms["active"][code] = room
    save_data(d)

    try:
        bot.set_chat_title(chat_id, creator_name[:64])
    except Exception:
        pass

    invite_link = None
    try:
        invite = bot.create_chat_invite_link(chat_id)
        invite_link = invite.invite_link if invite else None
    except Exception:
        invite_link = None

    if invite_link:
        d3, rooms3 = _rooms_get_data()
        room3 = rooms3.get("active", {}).get(code, {})
        if isinstance(room3, dict):
            room3["invite_link"] = invite_link
            rooms3["active"][code] = room3
            save_data(d3)
        bot.send_message(
            message.chat.id,
            f"✅ Пати создан!\nКод: {code}\nСсылка для входа: {invite_link}\n"
            "В группе запускается голосование за игру."
        )
    else:
        bot.send_message(
            message.chat.id,
            f"✅ Пати создан!\nКод: {code}\n"
            "Не удалось создать ссылку — проверьте права бота в группе."
        )

    # обновим статистику
    d2 = load_data()
    rec = d2.setdefault("users", {}).setdefault(str(creator.id), {})
    rec = _ensure_profile_fields(rec)
    rec["rooms_created"] = int(rec.get("rooms_created", 0) or 0) + 1
    d2["users"][str(creator.id)] = rec
    save_data(d2)
    _check_achievements(creator.id, rec)

    try:
        bot.send_message(chat_id, f"🏠 Пати создан для {creator_name}\nКод пати: {code}\nГолосование за игру стартует сейчас.")
    except Exception:
        pass
    _room_start_vote(chat_id, code)

@bot.message_handler(commands=["room_join"])
def room_join_cmd(message):
    if message.chat.type != "private":
        bot.send_message(message.chat.id, "Вход по коду доступен только в личных сообщениях.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Использование: /room_join <КОД>")
        return
    code = parts[1].strip().upper()
    d, rooms = _rooms_get_data()
    room = rooms.get("active", {}).get(code)
    if not isinstance(room, dict):
        bot.send_message(message.chat.id, "❌ Пати с таким кодом не найден.")
        return
    if time.time() > float(room.get("ends_at") or 0):
        bot.send_message(message.chat.id, "❌ Пати уже закрыто.")
        return
    chat_id = room.get("chat_id")
    invite_link = room.get("invite_link")
    if not invite_link:
        try:
            invite = bot.create_chat_invite_link(chat_id)
            invite_link = invite.invite_link if invite else None
        except Exception:
            invite_link = None
        if invite_link:
            room["invite_link"] = invite_link
            rooms["active"][code] = room
            save_data(d)
    if invite_link:
        bot.send_message(message.chat.id, f"✅ Вход по коду {code}:\n{invite_link}")
    else:
        bot.send_message(message.chat.id, "❌ Не удалось создать ссылку. Проверьте права бота в группе.")
    room_participants.setdefault(chat_id, set()).add(message.from_user.id)
    if isinstance(room.get("participants", []), list) and message.from_user.id not in room.get("participants", []):
        room["participants"].append(message.from_user.id)
        rooms["active"][code] = room
        save_data(d)

@bot.poll_answer_handler()
def room_poll_answer_handler(poll_answer):
    try:
        poll_id = poll_answer.poll_id
        info = room_polls.get(poll_id)
        if not info:
            return
        code = info.get("code")
        option_ids = poll_answer.option_ids or []
        if not option_ids:
            return
        d, rooms = _rooms_get_data()
        room = rooms.get("active", {}).get(code)
        if not isinstance(room, dict):
            return
        votes = room.get("votes", {})
        if not isinstance(votes, dict):
            votes = {}
        votes[str(poll_answer.user.id)] = int(option_ids[0])
        room["votes"] = votes
        rooms["active"][code] = room
        save_data(d)
        room_participants.setdefault(room.get("chat_id"), set()).add(poll_answer.user.id)
    except Exception:
        pass

# ------------------- BLITZ REACTION HANDLERS -------------------
@bot.message_handler(commands=["reaction"])
def reaction_cmd(message):
    _reaction_start(message.chat.id, message.from_user.id)

@bot.message_handler(func=lambda m: m.text == "⚡ Блиц-реакция")
def reaction_btn(message):
    _reaction_start(message.chat.id, message.from_user.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("reaction_hit_"))
def reaction_hit_callback(call):
    try:
        gid = call.data.split("_", 2)[2]
        state = reaction_games.get(gid)
        if not state:
            bot.answer_callback_query(call.id, "Игра не найдена.")
            return
        if call.from_user.id != state.get("uid"):
            bot.answer_callback_query(call.id, "Это не ваша игра.")
            return
        if not state.get("started"):
            bot.answer_callback_query(call.id, "Слишком рано!")
            return
        rt_ms = int((time.time() - state.get("start_at", time.time())) * 1000)
        text = f"⚡ Реакция: {rt_ms} мс"
        _reaction_edit(state, text)
        _record_game_play(call.from_user.id, "reaction", display_name=call.from_user.first_name or call.from_user.username or str(call.from_user.id), session_id=f"reaction_{gid}")
        reaction_games.pop(gid, None)
        try:
            if call.message and call.message.chat and call.message.chat.type in ("group", "supergroup"):
                d, rooms = _rooms_get_data()
                code, room = _room_find_by_chat(rooms, call.message.chat.id)
                if room and room.get("game") == "reaction":
                    _room_post_game_prompt(call.message.chat.id, code)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Готово!")
    except Exception:
        try:
            bot.answer_callback_query(call.id, "Ошибка.")
        except Exception:
            pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("reaction_begin_"))
def reaction_begin_callback(call):
    try:
        gid = call.data.split("_", 2)[2]
        state = reaction_games.get(gid)
        if not state:
            state = {"uid": call.from_user.id, "chat_id": None, "started": False, "start_at": None, "msg_id": None, "inline_id": None}
        if call.from_user.id != state.get("uid"):
            bot.answer_callback_query(call.id, "Это не ваша игра.")
            return
        state["inline_id"] = call.inline_message_id
        state["started"] = False
        state["start_at"] = None
        reaction_games[gid] = state
        _reaction_edit(state, "⚡ Блиц-реакция\nЖдите сигнала и нажмите кнопку!", reply_markup=_reaction_keyboard(gid))

        def trigger():
            time.sleep(random.uniform(2.0, 5.0))
            if gid not in reaction_games:
                return
            st = reaction_games[gid]
            st["started"] = True
            st["start_at"] = time.time()
            reaction_games[gid] = st
            _reaction_edit(st, "⚡ СИГНАЛ! ЖМИ СЕЙЧАС!", reply_markup=_reaction_keyboard(gid))

        Thread(target=trigger, daemon=True).start()
        bot.answer_callback_query(call.id)
    except Exception:
        try:
            bot.answer_callback_query(call.id, "Ошибка.")
        except Exception:
            pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("room_continue_"))
def room_continue_callback(call):
    try:
        parts = call.data.split("_")
        if len(parts) < 4:
            return
        action = parts[2]
        code = parts[3]
        d, rooms = _rooms_get_data()
        room = rooms.get("active", {}).get(code)
        if not isinstance(room, dict):
            bot.answer_callback_query(call.id, "Пати не найден.")
            return
        if action == "yes":
            room["game"] = None
            room["status"] = "voting"
            room["votes"] = {}
            room["poll_id"] = None
            rooms["active"][code] = room
            save_data(d)
            _room_start_vote(room["chat_id"], code)
            bot.answer_callback_query(call.id, "Новое голосование запущено.")
            return
        if action == "no":
            _room_close(code, reason="завершено игроками")
            bot.answer_callback_query(call.id, "Пати закрыто.")
            return
    except Exception:
        try:
            bot.answer_callback_query(call.id, "Ошибка.")
        except Exception:
            pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("room_game_end_"))
def room_game_end_callback(call):
    try:
        code = call.data.split("_", 3)[3]
        d, rooms = _rooms_get_data()
        room = rooms.get("active", {}).get(code)
        if not isinstance(room, dict):
            bot.answer_callback_query(call.id, "Пати не найден.")
            return
        _room_post_game_prompt(room["chat_id"], code)
        bot.answer_callback_query(call.id, "Ок, что дальше?")
    except Exception:
        try:
            bot.answer_callback_query(call.id, "Ошибка.")
        except Exception:
            pass

# ------------------- BLACKJACK HANDLERS -------------------
@bot.message_handler(commands=["blackjack"])
def blackjack_cmd(message):
    state = _bj_new_game(message.from_user.id, message.chat.id)
    gid = short_id()
    blackjack_games[gid] = state
    reveal = state.get("status") != "playing"
    text = _bj_render_text(state, reveal_dealer=reveal)
    kb = _bj_keyboard(gid, state.get("status"))
    msg = bot.send_message(message.chat.id, text, reply_markup=kb)
    try:
        if message.chat.type in ("group", "supergroup"):
            _room_track_message_id(message.chat.id, getattr(msg, "message_id", None))
    except Exception:
        pass
    if state.get("status") == "ended":
        _record_game_play(message.from_user.id, "blackjack", display_name=message.from_user.first_name or message.from_user.username or str(message.from_user.id), session_id=f"blackjack_{gid}")
        _record_game_result(message.from_user.id, "blackjack", state.get("result") or "draws")

@bot.message_handler(func=lambda m: m.text == "🃏 Блэкджек")
def blackjack_btn(message):
    blackjack_cmd(message)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bj_"))
def blackjack_callback(call):
    try:
        parts = call.data.split("_")
        if len(parts) < 3:
            return
        action = parts[1]
        gid = parts[2]
        state = blackjack_games.get(gid)
        if not state:
            bot.answer_callback_query(call.id, "Игра не найдена.")
            return
        if call.from_user.id != state.get("uid"):
            bot.answer_callback_query(call.id, "Это не ваша игра.")
            return

        if action == "new":
            state = _bj_new_game(call.from_user.id, call.message.chat.id)
            blackjack_games[gid] = state
            text = _bj_render_text(state, reveal_dealer=False)
            kb = _bj_keyboard(gid, state.get("status"))
            safe_edit_message(call, text, reply_markup=kb)
            bot.answer_callback_query(call.id)
            return

        if state.get("status") != "playing":
            bot.answer_callback_query(call.id, "Партия уже завершена.")
            return

        if action == "hit":
            deck = state.get("deck", [])
            if deck:
                state["player"].append(deck.pop())
            state["deck"] = deck
            player_val = _bj_hand_value(state.get("player", []))
            if player_val > 21:
                state["status"] = "ended"
                state["result"] = "losses"
            blackjack_games[gid] = state

        if action == "stand":
            deck = state.get("deck", [])
            dealer = state.get("dealer", [])
            while _bj_hand_value(dealer) < 17 and deck:
                dealer.append(deck.pop())
            state["dealer"] = dealer
            state["deck"] = deck
            pval = _bj_hand_value(state.get("player", []))
            dval = _bj_hand_value(dealer)
            if dval > 21 or pval > dval:
                state["result"] = "wins"
            elif pval < dval:
                state["result"] = "losses"
            else:
                state["result"] = "draws"
            state["status"] = "ended"
            blackjack_games[gid] = state

        reveal = state.get("status") != "playing"
        text = _bj_render_text(state, reveal_dealer=reveal)
        kb = _bj_keyboard(gid, state.get("status"))
        safe_edit_message(call, text, reply_markup=kb)

        if state.get("status") == "ended" and not state.get("recorded"):
            state["recorded"] = True
            blackjack_games[gid] = state
            _record_game_play(call.from_user.id, "blackjack", display_name=call.from_user.first_name or call.from_user.username or str(call.from_user.id), session_id=f"blackjack_{gid}")
            _record_game_result(call.from_user.id, "blackjack", state.get("result") or "draws")
            try:
                if call.message and call.message.chat and call.message.chat.type in ("group", "supergroup"):
                    d, rooms = _rooms_get_data()
                    code, room = _room_find_by_chat(rooms, call.message.chat.id)
                    if room and room.get("game") == "blackjack":
                        _room_post_game_prompt(call.message.chat.id, code)
            except Exception:
                pass
        bot.answer_callback_query(call.id)
    except Exception:
        try:
            bot.answer_callback_query(call.id, "Ошибка.")
        except Exception:
            pass

@bot.message_handler(func=lambda m: m.text == "🕵️‍♀️ Прятки")
def hide_and_seek(message):
    bot.send_message(message.chat.id, "Чтобы играть в прятки - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🔤 Виселица")
def hangman_message(message):
    bot.send_message(message.chat.id, "Чтобы играть в Виселицу - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "💣 Сапёр")
def minesweeper_message(message):
    uid = message.from_user.id
    _record_game_play(uid, "minesweeper", display_name=message.from_user.first_name or message.from_user.username or str(uid), session_id=f"chat_{message.chat.id}_{int(time.time())}")
    start_minesweeper_in_chat(message.chat.id)

@bot.message_handler(func=lambda m: m.text == "🔤 Викторина")
def quiz(message):
    bot.send_message(message.chat.id, "Чтобы играть в викторину - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "⚡ Комбо-битва")
def combo(message): 
    bot.send_message(message.chat.id, "Чтобы играть в комбо-битву - напишите <code>@minigamesisbot</code> в любом чате!", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎮 Играть")
def play(message):
    bot.send_message(message.chat.id, "Чтобы играть — используй инлайн через @YourBotUsername в любом чате!")


def _ai_prompt_status_text(status):
    mapping = {
        "wait": "⏳ ожидание..",
        "process": "⏳ ответ генерируется..",
        "done": "✅ готово",
    }
    return mapping.get(status, "⏳ ожидание..")


def _ai_prompt_message(question, status, answer=None):
    text = (
        f"💬 Вопрос:\n{str(question or '').strip()}\n\n"
        f"Статус: {_ai_prompt_status_text(status)}"
    )
    if status == "done":
        text += "\n\n🤖 Ответ:\n" + str(answer or "")
    return text


def _ai_prompt_kb(uid, rid):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("📩 Получить ответ", callback_data=f"ai_{uid}_{rid}"),
        types.InlineKeyboardButton("🔄 Обновить", callback_data=f"ai_refresh_{uid}_{rid}"),
    )
    return kb


@bot.inline_handler(lambda q: q.query.strip() != "")
def ai_inline(query):
    uid = query.from_user.id
    update_user_streak(uid, query.from_user.first_name or query.from_user.username or str(uid))
    # require subscription for inline AI
    if REQUIRED_CHANNEL and not is_user_subscribed(uid):
        return inline_subscription_prompt(query)
    text = query.query.strip()
    normalized = text.lower().strip()
    if normalized in ("\u043c\u043e\u0440\u0441\u043a\u043e\u0439 \u0431\u043e\u0439", "\u043c\u043e\u0440\u0441\u043a\u043e\u0439\u0431\u043e\u0439", "battleship", "bship"):
        bgid = short_id()
        battleship_games[bgid] = _bship_new_game(uid, query.from_user.first_name or query.from_user.username or str(uid))
        result = types.InlineQueryResultArticle(
            id=f"bship_{bgid}",
            title="\U0001f6a2 \u041c\u043e\u0440\u0441\u043a\u043e\u0439 \u0431\u043e\u0439",
            description="\u041f\u043e\u0448\u0430\u0433\u043e\u0432\u0430\u044f \u0438\u0433\u0440\u043e\u043a\u043e\u0432",
            input_message_content=types.InputTextMessageContent(_bship_public_text(battleship_games[bgid])),
            reply_markup=_bship_public_keyboard(bgid, battleship_games[bgid]),
        )
        bot.answer_inline_query(query.id, [result], cache_time=1, is_personal=True)
        return


    if normalized in ("шахматы", "шах", "chess"):
        cgid = short_id()
        chess_games[cgid] = _chess_new_game(uid, query.from_user.first_name or query.from_user.username or str(uid))
        result = types.InlineQueryResultArticle(
            id=f"chess_{cgid}",
            title="♟ Шахматы",
            description="Классические шахматы 1 на 1",
            input_message_content=types.InputTextMessageContent(_chess_render_text(chess_games[cgid])),
            reply_markup=_chess_keyboard(cgid, chess_games[cgid]),
        )
        bot.answer_inline_query(query.id, [result], cache_time=1, is_personal=True)
        return

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

    kb = _ai_prompt_kb(uid, req_id)

    result = types.InlineQueryResultArticle(
        id=req_id,
        title="🤖 Спросить ChatGPT",
        description=text[:60],
        input_message_content=types.InputTextMessageContent(_ai_prompt_message(text, "wait")),
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
        rgid = short_id()
        rps_games[rgid] = {"uid": starter_id}
        rps_markup = types.InlineKeyboardMarkup()
        rps_markup.row(
            types.InlineKeyboardButton("🪨 Камень", callback_data=f"rps_{rgid}_rock"),
            types.InlineKeyboardButton("📄 Бумага", callback_data=f"rps_{rgid}_paper"),
            types.InlineKeyboardButton("✂️ Ножницы", callback_data=f"rps_{rgid}_scissors")
        )
        results.append(types.InlineQueryResultArticle(
            id=f"rps_{rgid}",
            title="✂ Камень-ножницы-бумага",
            description="Сыграйте против бота",
            input_message_content=types.InputTextMessageContent(
                "✂️ *Камень • Ножницы • Бумага*\nВыберите ход:",
                parse_mode="Markdown"
            ),
            reply_markup=rps_markup
        ))


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

        # Wordle
        wgid = short_id()
        wgame = _wordle_new_game(starter_id)
        wordle_games[wgid] = wgame
        results.append(types.InlineQueryResultArticle(
            id=f"wordle_{wgid}",
            title="🟩 Wordle",
            description="Угадайте слово из 5 букв за 6 попыток",
            input_message_content=types.InputTextMessageContent(_wordle_render_text(wgame)),
            reply_markup=_wordle_keyboard(wgid, wgame)
        ))

        # Blitz Reaction
        rgid = short_id()
        reaction_games[rgid] = {"uid": starter_id, "chat_id": None, "started": False, "start_at": None, "msg_id": None, "inline_id": None}
        rmarkup = types.InlineKeyboardMarkup()
        rmarkup.add(types.InlineKeyboardButton("▶️ Начать", callback_data=f"reaction_begin_{rgid}"))
        results.append(types.InlineQueryResultArticle(
            id=f"reaction_{rgid}",
            title="⚡ Блиц-реакция",
            description="Проверка скорости реакции",
            input_message_content=types.InputTextMessageContent("⚡ Блиц-реакция\nНажмите «Начать», затем ждите сигнал."),
            reply_markup=rmarkup
        ))

        # Blackjack
        bjid = short_id()
        bjstate = _bj_new_game(starter_id, None)
        blackjack_games[bjid] = bjstate
        results.append(types.InlineQueryResultArticle(
            id=f"blackjack_{bjid}",
            title="🃏 Блэкджек",
            description="Карты против дилера",
            input_message_content=types.InputTextMessageContent(_bj_render_text(bjstate, reveal_dealer=bjstate.get("status") != "playing")),
            reply_markup=_bj_keyboard(bjid, bjstate.get("status"))
        ))

        # Battleship
        bgid = short_id()
        battleship_games[bgid] = _bship_new_game(starter_id, user.first_name or user.username or str(starter_id))
        results.append(types.InlineQueryResultArticle(
            id=f"bship_{bgid}",
            title="\U0001f6a2 \u041c\u043e\u0440\u0441\u043a\u043e\u0439 \u0431\u043e\u0439",
            description="\u041f\u043e\u0448\u0430\u0433\u043e\u0432\u0430\u044f \u0438\u0433\u0440\u043e\u043a\u043e\u0432",
            input_message_content=types.InputTextMessageContent(_bship_public_text(battleship_games[bgid])),
            reply_markup=_bship_public_keyboard(bgid, battleship_games[bgid])
        ))

        # Chess
        cgid = short_id()
        chess_games[cgid] = _chess_new_game(starter_id, user.first_name or user.username or str(starter_id))
        results.append(types.InlineQueryResultArticle(
            id=f"chess_{cgid}",
            title="♟ Шахматы",
            description="Классические шахматы 1 на 1",
            input_message_content=types.InputTextMessageContent(_chess_render_text(chess_games[cgid])),
            reply_markup=_chess_keyboard(cgid, chess_games[cgid])
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

        # Minesweeper (Сапёр)
        mgid = short_id()
        msize = 5
        mmines = 5
        mboard, mmine_positions = generate_minesweeper_board(msize, mmines)
        minesweeper_games[mgid] = {"board": mboard, "revealed": set(), "mine_positions": mmine_positions}
        mmarkup = _minesweeper_build_markup(mgid, mboard, set())
        results.append(types.InlineQueryResultArticle(
            id=f"minesweeper_{mgid}",
            title="💣 Сапёр",
            description="Откройте клетки, избегая мин",
            input_message_content=types.InputTextMessageContent(f"💣 Сапёр\n{render_minesweeper_board(mboard, set())}"),
            reply_markup=mmarkup
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

def _new_flappy_state():
    return {
        "bird_y": 5,
        "velocity": 0.0,
        "pipes": [(9, 3), (14, 4)],
        "score": 0,
        "started": False,
        "over": False,
        "loop_running": False,
        "inline_id": None,
    }

def _flappy_step(state):
    state["velocity"] = min(2.6, state.get("velocity", 0.0) + 0.6)
    state["bird_y"] += state["velocity"]

    new_pipes = []
    for pipe in state.get("pipes", []):
        x, gap = pipe
        x -= 1
        if x >= -1:
            new_pipes.append((x, gap))
        if x == 1:
            state["score"] += 1
    state["pipes"] = new_pipes

    if not state["pipes"] or state["pipes"][-1][0] <= 5:
        state["pipes"].append((9, random.randint(1, 6)))

    by = int(round(state["bird_y"]))
    if by < 0 or by >= 10:
        state["over"] = True
        state["started"] = False
        return

    for x, gap in state["pipes"]:
        if x == 2 and not (gap <= by <= gap + 2):
            state["over"] = True
            state["started"] = False
            return

def _flappy_pm_markup(uid, game_over=False):
    markup = types.InlineKeyboardMarkup()
    if game_over:
        markup.row(
            types.InlineKeyboardButton("🔄 Ещё раз", callback_data=f"flappy_pm_{uid}_restart"),
            types.InlineKeyboardButton("❌ Закрыть", callback_data=f"flappy_pm_{uid}_close"),
        )
        return markup
    markup.row(
        types.InlineKeyboardButton("▶️ Старт", callback_data=f"flappy_pm_{uid}_start"),
        types.InlineKeyboardButton("⬆️ Прыжок", callback_data=f"flappy_pm_{uid}_jump"),
    )
    markup.add(types.InlineKeyboardButton("❌ Закрыть", callback_data=f"flappy_pm_{uid}_close"))
    return markup

def _render_flappy_pm_text(state):
    lines = [
        "🐦 Flappy Bird в ЛС",
        f"Очки: {state['score']}",
    ]
    if state.get("over"):
        lines.append("Игра окончена.")
    elif not state.get("started"):
        lines.append("Нажмите «Старт», затем жмите «Прыжок».")
    lines.append("")
    lines.append(render_flappy_state(state))
    return "\n".join(lines)

def _edit_flappy_pm(uid):
    state = pm_flappy_games.get(uid)
    if not state:
        return False
    chat_id = state.get("chat_id")
    message_id = state.get("message_id")
    if not chat_id or not message_id:
        return False
    try:
        bot.edit_message_text(
            _render_flappy_pm_text(state),
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=_flappy_pm_markup(uid, game_over=state.get("over", False)),
        )
        return True
    except Exception as e:
        msg = str(e)
        if "message is not modified" in msg or "specified new message content and reply markup are exactly the same" in msg:
            return True
        print("FLAPPY PM EDIT ERROR:", e)
        return False

def flappy_pm_loop(uid):
    while uid in pm_flappy_games:
        state = pm_flappy_games.get(uid)
        if not state:
            break
        if not state.get("started") or state.get("over"):
            time.sleep(0.25)
            continue
        _flappy_step(state)
        if not _edit_flappy_pm(uid):
            break
        if state.get("over"):
            break
        time.sleep(0.8)

@bot.callback_query_handler(func=lambda c: c.data.startswith("flappy_pm_"))
def flappy_pm_callback(call):
    try:
        parts = str(call.data or "").split("_", 3)  # flappy_pm_<uid>_<action>
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Некорректная команда")
            return
        owner_id = int(parts[2])
        action = parts[3]
        uid = call.from_user.id

        if uid != owner_id:
            bot.answer_callback_query(call.id, "Это не ваша игра", show_alert=True)
            return

        state = pm_flappy_games.get(owner_id)
        if action == "restart":
            state = _new_flappy_state()
            state["chat_id"] = call.message.chat.id
            state["message_id"] = call.message.message_id
            state["owner_id"] = owner_id
            pm_flappy_games[owner_id] = state
            _edit_flappy_pm(owner_id)
            bot.answer_callback_query(call.id, "Новая игра")
            return

        if action == "close":
            pm_flappy_games.pop(owner_id, None)
            try:
                bot.edit_message_text("🐦 Flappy Bird закрыт.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception:
                pass
            bot.answer_callback_query(call.id, "Закрыто")
            return

        if not state:
            state = _new_flappy_state()
            state["chat_id"] = call.message.chat.id
            state["message_id"] = call.message.message_id
            state["owner_id"] = owner_id
            pm_flappy_games[owner_id] = state

        if action == "start":
            if state.get("started"):
                bot.answer_callback_query(call.id, "Игра уже идёт")
                return
            state["started"] = True
            state["over"] = False
            state["velocity"] = 0.0
            _edit_flappy_pm(owner_id)
            if not state.get("loop_running"):
                state["loop_running"] = True
                Thread(target=flappy_pm_loop, args=(owner_id,), daemon=True).start()
            bot.answer_callback_query(call.id, "Старт!")
            return

        if action == "jump":
            if state.get("over"):
                bot.answer_callback_query(call.id, "Игра окончена")
                return
            if not state.get("started"):
                state["started"] = True
                if not state.get("loop_running"):
                    state["loop_running"] = True
                    Thread(target=flappy_pm_loop, args=(owner_id,), daemon=True).start()
            state["velocity"] = -1.8
            _edit_flappy_pm(owner_id)
            bot.answer_callback_query(call.id, "Прыжок!")
            return

        bot.answer_callback_query(call.id)
    except Exception as e:
        print("FLAPPY PM ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка Flappy Bird")

@bot.callback_query_handler(func=lambda c: c.data.startswith("guess_inline_"))
def guess_inline_callback(call):
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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
        parts = call.data.split("_")
        action = "get"
        if len(parts) == 4 and parts[1] == "refresh":
            _, _, uid, rid = parts
            action = "refresh"
        elif len(parts) == 3:
            _, uid, rid = parts
        else:
            bot.answer_callback_query(call.id, "Неверные данные")
            return

        uid = int(uid)
        if call.from_user.id != uid:
            bot.answer_callback_query(call.id, "Это не ваш запрос")
            return

        data = load_data()
        user = data["users"].get(str(uid))
        if not user:
            bot.answer_callback_query(call.id, "Данные пользователя не найдены")
            return

        req = user.get("pending", {}).get(rid)
        if not req:
            bot.answer_callback_query(call.id, "Запрос устарел")
            return
        status = str(req.get("status", "wait")).strip().lower()
        if status not in ("wait", "process", "done"):
            status = "wait"
        if req.get("status") != status:
            req["status"] = status
            save_data(data)

        # Для кнопки "Обновить" только читаем статус из JSON.
        if action == "refresh":
            if status == "done":
                safe_edit_message(call, _ai_prompt_message(req.get("q"), "done", req.get("a")), reply_markup=_ai_prompt_kb(uid, rid))
                bot.answer_callback_query(call.id, "✅ Ответ готов")
            elif status == "process":
                safe_edit_message(call, _ai_prompt_message(req.get("q"), "process"), reply_markup=_ai_prompt_kb(uid, rid))
                bot.answer_callback_query(call.id, "⏳ Ответ ещё генерируется…")
            else:
                safe_edit_message(call, _ai_prompt_message(req.get("q"), "wait"), reply_markup=_ai_prompt_kb(uid, rid))
                bot.answer_callback_query(call.id, "⏳ Ожидание запуска")
            return

        # если ещё не считали — запускаем
        if status == "wait":
            allow, err = can_use_ai(uid)
            if not allow:
                bot.answer_callback_query(call.id, err, show_alert=True)
                return
            req["status"] = "process"
            req["started_at"] = int(time.time())
            save_data(data)

            def work():
                try:
                    prompt = req["q"]
                    answer = ask_ai(prompt, uid)
                    d2 = load_data()
                    u2 = d2.setdefault("users", {}).setdefault(str(uid), {})
                    pending2 = u2.setdefault("pending", {})
                    req2 = pending2.get(rid)
                    if req2 is None:
                        return
                    if req2.get("status") != "process":
                        return

                    # списываем лимит только после фактического получения ответа
                    today = date.today().isoformat()
                    if u2.get("date") != today:
                        u2["date"] = today
                        u2["count"] = 0
                    if u2.get("daily_date") != today:
                        u2["daily_date"] = today
                        u2["daily_count"] = 0
                    u2["count"] = int(u2.get("count", 0) or 0) + 1
                    u2["daily_count"] = int(u2.get("daily_count", 0) or 0) + 1

                    req2["a"] = answer
                    req2["status"] = "done"
                    save_data(d2)

                except Exception as e:
                    d3 = load_data()
                    u3 = d3.setdefault("users", {}).setdefault(str(uid), {})
                    pending3 = u3.setdefault("pending", {})
                    req3 = pending3.get(rid)
                    if req3 is not None:
                        req3["a"] = "❌ Временная ошибка AI-сервиса. Нажмите «Обновить» или «Получить ответ» ещё раз."
                        req3["status"] = "done"
                        save_data(d3)

            Thread(target=work, daemon=True).start()
            safe_edit_message(call, _ai_prompt_message(req.get("q"), "process"), reply_markup=_ai_prompt_kb(uid, rid))
            bot.answer_callback_query(call.id, "⏳ Готовлю ответ…")
            return

        if status == "process":
            started_at = int(req.get("started_at", 0) or 0)
            if started_at and (int(time.time()) - started_at) > 180:
                req["status"] = "done"
                req["a"] = "❌ Ответ не был получен вовремя (таймаут 3 минуты). Нажмите «Получить ответ» ещё раз."
                save_data(data)
                safe_edit_message(call, _ai_prompt_message(req.get("q"), "done", req.get("a")), reply_markup=_ai_prompt_kb(uid, rid))
                bot.answer_callback_query(call.id, "⌛ Таймаут запроса")
                return
            safe_edit_message(call, _ai_prompt_message(req.get("q"), "process"), reply_markup=_ai_prompt_kb(uid, rid))
            bot.answer_callback_query(call.id, "⏳ Ответ ещё генерируется…")
            return

        # если готово
        if status == "done":
            answer = req["a"]
            safe_edit_message(call, _ai_prompt_message(req.get("q"), "done", answer), reply_markup=_ai_prompt_kb(uid, rid))
            bot.answer_callback_query(call.id, "✅ Ответ готов!")
            return

    except Exception as e:
        print("AI CALLBACK ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка при получении ответа")

# ------------------- TTT HANDLER -------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("ttt_join_"))
def ttt_join(call):
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
    try:
        _, gid, user_choice = call.data.split("_")

        game = rps_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "❌ Игра устарела")
            return
        if game.get("uid") != call.from_user.id:
            bot.answer_callback_query(call.id, "Эта партия не ваша")
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

        rps_games.pop(gid, None)
        bot.answer_callback_query(call.id, "Игра окончена")
        return

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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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

def _new_pong_state():
    return {
        "players": [None, None],
        "paddles": [3, 3],
        "ball": [5, 3, -1, 1],
        "started": False,
        "score": [0, 0],
        "winner": None,
        "loop_running": False,
        "inline_id": None,
    }

def _pong_controls_markup(gid, started=False, game_over=False):
    markup = types.InlineKeyboardMarkup()
    if game_over:
        markup.add(types.InlineKeyboardButton("🔄 Новая игра", callback_data=f"pong_{gid}_restart"))
        return markup
    markup.row(
        types.InlineKeyboardButton("⬆️", callback_data=f"pong_{gid}_U"),
        types.InlineKeyboardButton("⬇️", callback_data=f"pong_{gid}_D"),
    )
    if not started:
        markup.add(types.InlineKeyboardButton("▶️ Старт", callback_data=f"pong_{gid}_start"))
    return markup

def _render_pong_text(state):
    score = state.get("score", [0, 0])
    lines = [
        "🏓 Пинг-понг",
        f"Счёт: {score[0]} : {score[1]}",
    ]
    if state.get("winner") is not None:
        winner_idx = state["winner"] + 1
        side = "слева" if state["winner"] == 0 else "справа"
        lines.append(f"Победил Игрок {winner_idx} ({side})")
    elif not state.get("started"):
        lines.append("Подключитесь вдвоём и нажмите «Старт».")
    lines.append("")
    lines.append(render_pong_state(state))
    return "\n".join(lines)

def _pong_reset_ball(state, direction=None):
    dx = direction if direction in (-1, 1) else random.choice([-1, 1])
    dy = random.choice([-1, 1])
    state["ball"] = [5, random.randint(1, 5), dx, dy]

def _pong_step(state):
    W, H = 11, 7
    p1x, p2x = 1, 9
    bx, by, dx, dy = state["ball"]
    bx += dx
    by += dy

    if by <= 0:
        by = 0
        dy = 1
    elif by >= H - 1:
        by = H - 1
        dy = -1

    if bx == p1x and by == state["paddles"][0]:
        dx = 1
        bx = p1x + 1
    elif bx == p2x and by == state["paddles"][1]:
        dx = -1
        bx = p2x - 1
    elif bx < 0:
        state["score"][1] += 1
        if state["score"][1] >= 5:
            state["winner"] = 1
            state["started"] = False
        else:
            _pong_reset_ball(state, direction=1)
            return
    elif bx >= W:
        state["score"][0] += 1
        if state["score"][0] >= 5:
            state["winner"] = 0
            state["started"] = False
        else:
            _pong_reset_ball(state, direction=-1)
            return

    state["ball"] = [bx, by, dx, dy]

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
        input_message_content=types.InputTextMessageContent("🏓 Пинг-понг\nНажмите 'Присоединиться', дождитесь второго игрока и начните матч."),
        reply_markup=markup
    )]
    bot.answer_inline_query(query.id, results, cache_time=1, is_personal=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("pong_"))
def pong_callback(call):
    _track_callback_game_play(call)
    try:
        parts = call.data.split("_", 2)
        gid = parts[1]
        action = parts[2] if len(parts) > 2 else ""
        state = games_pong.get(gid)
        if action == "join":
            if state is None:
                state = _new_pong_state()
                games_pong[gid] = state
            state["inline_id"] = call.inline_message_id
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
                bot.answer_callback_query(call.id, "Пати заполнен.")
                return
            if state["players"][0] and state["players"][1]:
                safe_edit_message(call, _render_pong_text(state), reply_markup=_pong_controls_markup(gid, started=False))
            else:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"pong_{gid}_join"))
                safe_edit_message(call, f"{msg}\nОжидаем второго игрока...", reply_markup=markup)
            bot.answer_callback_query(call.id, msg)
            return

        if state is None:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return
        state["inline_id"] = call.inline_message_id or state.get("inline_id")
        uid = call.from_user.id
        if uid not in state["players"]:
            bot.answer_callback_query(call.id, "Вы не участник игры")
            return

        if action == "restart":
            games_pong[gid] = _new_pong_state()
            games_pong[gid]["inline_id"] = state.get("inline_id")
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"pong_{gid}_join"))
            safe_edit_message(call, "🏓 Пинг-понг\nНажмите 'Присоединиться' чтобы игра началась.", reply_markup=markup)
            bot.answer_callback_query(call.id, "Игра сброшена")
            return

        if action in ("U", "D"):
            pidx = 0 if uid == state["players"][0] else 1
            if action == "U":
                state["paddles"][pidx] = max(0, state["paddles"][pidx] - 1)
            else:
                state["paddles"][pidx] = min(6, state["paddles"][pidx] + 1)
            safe_edit_message(call, _render_pong_text(state), reply_markup=_pong_controls_markup(gid, started=state.get("started", False)))
            bot.answer_callback_query(call.id, "Платформа сдвинута")
            return

        if action == "start":
            if state["started"]:
                bot.answer_callback_query(call.id, "Игра уже запущена")
                return
            if not all(state["players"]):
                bot.answer_callback_query(call.id, "Нужны 2 игрока")
                return
            state["started"] = True
            _pong_reset_ball(state)
            safe_edit_message(call, _render_pong_text(state), reply_markup=_pong_controls_markup(gid, started=True))
            if not state.get("loop_running") and state.get("inline_id"):
                state["loop_running"] = True
                Thread(target=pong_game_loop, args=(gid, state["inline_id"]), daemon=True).start()
            bot.answer_callback_query(call.id, "Старт!")
            return

        bot.answer_callback_query(call.id)
    except Exception as e:
        print("PONG ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка Pong")

# ------------------- MILLIONAIRE HANDLER -------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("millionaire_"))
def millionaire_callback(call):
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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

def _minesweeper_build_markup(gid, board, revealed):
    markup = types.InlineKeyboardMarkup()
    for i in range(len(board)):
        row = []
        for j in range(len(board)):
            if (i, j) in revealed:
                row.append(types.InlineKeyboardButton("⬜", callback_data="none"))
            else:
                row.append(types.InlineKeyboardButton("⬛", callback_data=f"minesweeper_{gid}_{i}_{j}"))
        markup.row(*row)
    return markup

def start_minesweeper_in_chat(chat_id):
    size = 5
    mines = 5
    board, mine_positions = generate_minesweeper_board(size, mines)
    gid = short_id()
    revealed = set()
    minesweeper_games[gid] = {"board": board, "revealed": revealed, "mine_positions": mine_positions}
    bot.send_message(
        chat_id,
        f"💣 Сапёр\n{render_minesweeper_board(board, revealed)}",
        reply_markup=_minesweeper_build_markup(gid, board, revealed),
    )

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
    _track_callback_game_play(call)
    def _safe_ack(text=None, show_alert=False):
        try:
            bot.answer_callback_query(call.id, text, show_alert=show_alert)
        except Exception as e:
            msg = str(e)
            if "query is too old" in msg or "query ID is invalid" in msg:
                return
            print("MAFIA ACK ERROR:", e)

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
            if game.get("status") != "waiting":
                bot.answer_callback_query(call.id, "Игра уже началась", show_alert=True)
                return
            if uid == game.get("p1"):
                bot.answer_callback_query(call.id, "Нужен второй игрок")
                return
            game["p2"] = uid
            game["p2_name"] = call.from_user.first_name or call.from_user.username or str(uid)
            size = game.get("size", 5)
            ships_count = game.get("ships_count", 5)
            game.setdefault("ships", {})[uid] = _bship_random_ships(size, ships_count)
            game.setdefault("shots", {})[uid] = set()
            game["status"] = "playing"
            game["turn"] = game.get("p1")

            ok1, ok2 = _bship_sync_views(gid, game, call=call)
            if not ok1 or not ok2:
                _safe_ack("Партия началась. Если нет поля в ЛС — откройте чат с ботом и нажмите Start", show_alert=True)
            else:
                _safe_ack("Партия началась. Поля отправлены в ЛС")
            return

        if action == "new":
            if uid not in (game.get("p1"), game.get("p2")):
                _safe_ack("\u042d\u0442\u043e \u043d\u0435 \u0432\u0430\u0448\u0430 \u043f\u0430\u0440\u0442\u0438\u044f")
                return

            size = game.get("size", 5)
            ships_count = game.get("ships_count", 5)
            p1 = game.get("p1")
            p2 = game.get("p2")

            if not p2:
                game.update(_bship_new_game(p1, game.get("p1_name", "\u0418\u0433\u0440\u043e\u043a 1"), size=size, ships_count=ships_count))
                game["turn"] = uid
                game["shots"] = {p1: set()}
            else:
                game["status"] = "playing"
                game["ships"] = {
                    p1: _bship_random_ships(size, ships_count),
                    p2: _bship_random_ships(size, ships_count),
                }
                game["shots"] = {p1: set(), p2: set()}
            game["turn"] = p1
            game["winner"] = None

            _bship_sync_views(gid, game, call=call)
            _safe_ack("Новая партия. Обновил поля в ЛС")
            return

        if action == "shot":
            if len(parts) < 5:
                _safe_ack("Неверный ход")
                return
            if game.get("status") != "playing":
                _safe_ack("Партия не начата")
                return
            if uid != game.get("turn"):
                _safe_ack("Сейчас не ваш ход")
                return
            if uid not in (game.get("p1"), game.get("p2")):
                _safe_ack("Вы не участник этой партии")
                return

            r = int(parts[3])
            c = int(parts[4])
            size = game.get("size", 5)
            if r < 0 or c < 0 or r >= size or c >= size:
                _safe_ack("Некорректная клетка")
                return

            enemy = game.get("p2") if uid == game.get("p1") else game.get("p1")
            if not enemy:
                _safe_ack("Ожидаем второго игрока")
                return

            my_shots = game.setdefault("shots", {}).setdefault(uid, set())
            if (r, c) in my_shots:
                _safe_ack("Вы уже стреляли сюда")
                return

            my_shots.add((r, c))
            enemy_ships = game.setdefault("ships", {}).setdefault(enemy, set())

            if (r, c) in enemy_ships:
                if enemy_ships.issubset(my_shots):
                    game["status"] = "ended"
                    game["winner"] = uid
                    _bship_sync_views(gid, game, call=call)
                    _safe_ack("Попадание! Вы победили")
                    return
                _safe_ack("Попадание! Ходите еще")
            else:
                game["turn"] = enemy
                _safe_ack("Мимо")

            _bship_sync_views(gid, game, call=call)
            return

        _safe_ack()
    except Exception as e:
        print("MAFIA CALLBACK ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка Мафии")

# Словесная дуэль - присоединение
@bot.callback_query_handler(func=lambda c: c.data.startswith("wordgame_join_"))
def wordgame_join(call):
    _track_callback_game_play(call)
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
            for i, letter in enumerate("абвгдежзийклмнопрстуфхцчшщъyэюя".replace('y','й')):
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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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
        text += f"Игроки ({len(players)}/{game.get('max_players',4)}):\n\n"
        for pid in players:
            name = names.get(pid, "Игрок")
            status = "✅ ответ готов" if game["answered"].get(pid) else "⌨️ вводит"
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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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
    _track_callback_game_play(call)
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

@bot.callback_query_handler(func=lambda c: c.data.startswith("wrdl_"))
def wordle_callback(call):
    _track_callback_game_play(call)
    try:
        parts = call.data.split("_", 3)
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Неверные данные")
            return

        action = parts[1]
        gid = parts[2]
        game = wordle_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return

        if call.from_user.id != game.get("owner"):
            bot.answer_callback_query(call.id, "Это не ваша игра", show_alert=True)
            return

        if action == "new":
            game = _wordle_new_game(call.from_user.id)
            wordle_games[gid] = game
            safe_edit_message(call, _wordle_render_text(game), reply_markup=_wordle_keyboard(gid, game))
            bot.answer_callback_query(call.id, "Новая игра")
            return

        if game.get("status") != "playing":
            bot.answer_callback_query(call.id, "Игра завершена")
            return

        if action == "l":
            if len(parts) < 4:
                bot.answer_callback_query(call.id, "Неверная буква")
                return
            ch = (parts[3] or "").lower()
            if len(ch) != 1:
                bot.answer_callback_query(call.id, "Неверная буква")
                return
            cur = game.get("current", "")
            if len(cur) < 5:
                game["current"] = cur + ch
            safe_edit_message(call, _wordle_render_text(game), reply_markup=_wordle_keyboard(gid, game))
            bot.answer_callback_query(call.id, game["current"].upper())
            return

        if action == "back":
            game["current"] = (game.get("current", "") or "")[:-1]
            safe_edit_message(call, _wordle_render_text(game), reply_markup=_wordle_keyboard(gid, game))
            bot.answer_callback_query(call.id)
            return

        if action == "submit":
            guess = (game.get("current", "") or "").lower()
            if len(guess) != 5:
                bot.answer_callback_query(call.id, "Введите 5 букв")
                return
            if guess not in WORDLE_WORDS:
                bot.answer_callback_query(call.id, "Слова нет в словаре")
                return
            marks = _wordle_eval_guess(guess, game["target"])
            game["attempts"].append({"guess": guess, "marks": marks})
            game["current"] = ""
            if guess == game["target"]:
                game["status"] = "won"
            elif len(game["attempts"]) >= 6:
                game["status"] = "lost"
            safe_edit_message(call, _wordle_render_text(game), reply_markup=_wordle_keyboard(gid, game))
            bot.answer_callback_query(call.id)
            return

        bot.answer_callback_query(call.id)
    except Exception as e:
        print("WORDLE CALLBACK ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка Wordle")

def _bship_random_ships(size=5, ships_count=5):
    max_cells = max(1, size * size)
    ships_count = max(1, min(ships_count, max_cells))
    ships = set()
    while len(ships) < ships_count:
        ships.add((random.randint(0, size - 1), random.randint(0, size - 1)))
    return ships


def _bship_norm_cells(value):
    out = set()
    if isinstance(value, set):
        iterable = value
    elif isinstance(value, (list, tuple)):
        iterable = value
    else:
        return out
    for item in iterable:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            try:
                out.add((int(item[0]), int(item[1])))
            except Exception:
                pass
    return out


def _bship_new_game(owner_id, owner_name, size=5, ships_count=5):
    size = max(3, min(8, int(size)))
    ships_count = max(1, min(int(ships_count), size * size))
    return {
        "p1": owner_id,
        "p2": None,
        "p1_name": owner_name,
        "p2_name": "",
        "size": size,
        "ships_count": ships_count,
        "ships": {owner_id: _bship_random_ships(size, ships_count)},
        "shots": {owner_id: set()},
        "turn": owner_id,
        "status": "waiting",
        "winner": None,
    }


def _bship_ensure_game_shape(game):
    if not isinstance(game, dict):
        return False
    if not isinstance(game.get("ships"), dict):
        game["ships"] = {}
    if not isinstance(game.get("shots"), dict):
        game["shots"] = {}
    game["size"] = max(3, min(8, int(game.get("size", 5) or 5)))
    game["ships_count"] = max(1, min(int(game.get("ships_count", 5) or 5), game["size"] * game["size"]))
    game["status"] = game.get("status") if game.get("status") in ("waiting", "playing", "ended") else "waiting"

    p1 = game.get("p1")
    p2 = game.get("p2")
    if p1 is None:
        return False

    if not game.get("p1_name"):
        game["p1_name"] = str(p1)
    if p2 is not None and not game.get("p2_name"):
        game["p2_name"] = str(p2)

    game["ships"][p1] = _bship_norm_cells(game["ships"].get(p1))
    game["shots"][p1] = _bship_norm_cells(game["shots"].get(p1))
    if not game["ships"][p1]:
        game["ships"][p1] = _bship_random_ships(game["size"], game["ships_count"])

    if p2 is not None:
        game["ships"][p2] = _bship_norm_cells(game["ships"].get(p2))
        game["shots"][p2] = _bship_norm_cells(game["shots"].get(p2))
        if not game["ships"][p2]:
            game["ships"][p2] = _bship_random_ships(game["size"], game["ships_count"])

    if game.get("turn") not in (p1, p2):
        game["turn"] = p1

    if game["status"] == "playing" and p2 is None:
        game["status"] = "waiting"

    if game["status"] == "waiting":
        game["winner"] = None
    return True


def _bship_cell_view(is_own, has_ship, was_shot_by_self, was_shot_by_enemy):
    if is_own:
        if has_ship and was_shot_by_enemy:
            return "💥"
        if has_ship:
            return "🚢"
        if was_shot_by_enemy:
            return "•"
        return "▫️"
    if was_shot_by_self:
        return "💥" if has_ship else "•"
    return "❔"


def _bship_public_text(game):
    _bship_ensure_game_shape(game)
    size = game.get("size", 5)
    ships_count = game.get("ships_count", 5)
    p1 = game.get("p1")
    p2 = game.get("p2")
    p1_name = game.get("p1_name", "Игрок 1")
    p2_name = game.get("p2_name", "Игрок 2") if p2 else "Ожидание второго игрока"
    text = f"🚢 Морской бой ({size}x{size})\nКораблей: {ships_count} у каждого\n\n{p1_name} vs {p2_name}\n"
    if game.get("status") == "waiting":
        text += "\nНажмите «Присоединиться», чтобы начать."
    elif game.get("status") == "ended":
        winner = game.get("winner")
        winner_name = p1_name if winner == p1 else game.get("p2_name", "Игрок 2")
        text += f"\nПобедитель: {winner_name}"
    else:
        turn_uid = game.get("turn")
        turn_name = p1_name if turn_uid == p1 else p2_name
        text += f"\nХод: {turn_name}"
    text += "\n\nПоля скрыты. Играйте через личные сообщения с ботом."
    return text


def _bship_public_keyboard(gid, game):
    _bship_ensure_game_shape(game)
    kb = types.InlineKeyboardMarkup()
    if game.get("status") == "waiting":
        kb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"bship_join_{gid}"))
    kb.add(types.InlineKeyboardButton("Открыть ЛС", callback_data=f"bship_dm_{gid}"))
    if game.get("status") == "ended":
        kb.add(types.InlineKeyboardButton("Новая партия", callback_data=f"bship_new_{gid}"))
    return kb


def _bship_render_text(game, viewer_id):
    _bship_ensure_game_shape(game)
    size = game.get("size", 5)
    ships_count = game.get("ships_count", 5)
    p1 = game.get("p1")
    p2 = game.get("p2")
    p1_name = game.get("p1_name", "Игрок 1")
    p2_name = game.get("p2_name", "Игрок 2")

    text = f"🚢 Морской бой ({size}x{size})\nКораблей: {ships_count} у каждого\n\n"
    text += f"{p1_name} vs {p2_name}\n"

    if game.get("status") == "waiting":
        text += "\nНажмите «Присоединиться», чтобы начать."
        return text

    if game.get("status") == "ended":
        winner = game.get("winner")
        winner_name = p1_name if winner == p1 else p2_name
        text += f"\nПобедитель: {winner_name}\n"
    else:
        turn_uid = game.get("turn")
        turn_name = p1_name if turn_uid == p1 else p2_name
        text += f"\nХод: {turn_name}\n"

    if viewer_id not in (p1, p2):
        text += "\n(Вы не участник этой партии)"
        return text

    enemy = p2 if viewer_id == p1 else p1
    ships = game["ships"]
    shots_map = game["shots"]
    my_ships = ships.get(viewer_id, set())
    enemy_ships = ships.get(enemy, set())
    my_shots = shots_map.get(viewer_id, set())
    enemy_shots = shots_map.get(enemy, set())

    text += "\nЛегенда: 🚢 корабль, 💥 попадание, • мимо, ▫️ пусто, ❔ неизвестно\n"

    text += "\nВаше поле\n"
    for r in range(size):
        row = []
        for c in range(size):
            has_ship = (r, c) in my_ships
            row.append(_bship_cell_view(True, has_ship, False, (r, c) in enemy_shots))
        text += "".join(row) + "\n"

    text += "\nПоле соперника\n"
    for r in range(size):
        row = []
        for c in range(size):
            has_ship = (r, c) in enemy_ships
            row.append(_bship_cell_view(False, has_ship, (r, c) in my_shots, False))
        text += "".join(row) + "\n"

    return text


def _bship_keyboard(gid, game, viewer_id):
    _bship_ensure_game_shape(game)
    kb = types.InlineKeyboardMarkup()
    status = game.get("status")

    if status == "waiting":
        kb.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"bship_join_{gid}"))
        return kb

    if status == "ended":
        kb.add(types.InlineKeyboardButton("Новая партия", callback_data=f"bship_new_{gid}"))
        return kb

    p1 = game.get("p1")
    p2 = game.get("p2")
    if viewer_id not in (p1, p2):
        return kb

    if viewer_id != game.get("turn"):
        kb.add(types.InlineKeyboardButton("Ход соперника", callback_data="none"))
        return kb

    size = game.get("size", 5)
    shots = game.get("shots", {}).get(viewer_id, set())
    for r in range(size):
        row = []
        for c in range(size):
            if (r, c) in shots:
                row.append(types.InlineKeyboardButton("•", callback_data="none"))
            else:
                row.append(types.InlineKeyboardButton("▫️", callback_data=f"bship_shot_{gid}_{r}_{c}"))
        kb.row(*row)
    return kb


def _bship_store_public_anchor(game, call):
    if getattr(call, "inline_message_id", None):
        game["public_inline_id"] = call.inline_message_id
    elif getattr(call, "message", None) and getattr(call.message.chat, "type", None) != "private":
        game["public_chat_id"] = call.message.chat.id
        game["public_message_id"] = call.message.message_id


def _bship_edit_public_view(gid, game, call=None):
    text = _bship_public_text(game)
    kb = _bship_public_keyboard(gid, game)
    try:
        inline_id = game.get("public_inline_id")
        if inline_id:
            bot.edit_message_text(text, inline_message_id=inline_id, reply_markup=kb)
            return
        chat_id = game.get("public_chat_id")
        message_id = game.get("public_message_id")
        if chat_id and message_id:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=kb)
            return
        if call is not None and (getattr(call, "inline_message_id", None) or (getattr(call, "message", None) and getattr(call.message.chat, "type", None) != "private")):
            safe_edit_message(call, text, reply_markup=kb)
    except Exception as e:
        msg = str(e)
        if "message is not modified" not in msg and "exactly the same" not in msg:
            print("BATTLESHIP PUBLIC VIEW ERROR:", e)


def _bship_send_or_edit_private(gid, game, uid):
    if uid not in (game.get("p1"), game.get("p2")):
        return False
    text = _bship_render_text(game, uid)
    kb = _bship_keyboard(gid, game, uid)
    pm = game.setdefault("pm", {})
    cur = pm.get(uid) if isinstance(pm, dict) else None
    try:
        if isinstance(cur, dict) and cur.get("chat_id") and cur.get("message_id"):
            bot.edit_message_text(
                text,
                chat_id=cur["chat_id"],
                message_id=cur["message_id"],
                reply_markup=kb,
            )
            return True
    except Exception as e:
        print("BATTLESHIP PRIVATE EDIT ERROR:", e)
    try:
        msg = bot.send_message(uid, text, reply_markup=kb)
        pm[uid] = {"chat_id": msg.chat.id, "message_id": msg.message_id}
        return True
    except Exception as e:
        print("BATTLESHIP PRIVATE SEND ERROR:", e)
        return False


def _bship_sync_views(gid, game, call=None):
    _bship_edit_public_view(gid, game, call=call)
    p1 = game.get("p1")
    p2 = game.get("p2")
    ok_p1 = _bship_send_or_edit_private(gid, game, p1) if p1 is not None else False
    ok_p2 = _bship_send_or_edit_private(gid, game, p2) if p2 is not None else False
    return ok_p1, ok_p2


@bot.callback_query_handler(func=lambda c: c.data == "none")
def noop_callback(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("bship_"))
def battleship_callback(call):
    _track_callback_game_play(call)
    def _safe_ack(text=None, show_alert=False):
        try:
            bot.answer_callback_query(call.id, text, show_alert=show_alert)
        except Exception as e:
            msg = str(e)
            if "query is too old" in msg or "query ID is invalid" in msg:
                return
            print("BATTLESHIP ACK ERROR:", e)

    try:
        parts = call.data.split("_")
        if len(parts) < 3:
            _safe_ack("Неверные данные")
            return

        action = parts[1]
        gid = parts[2]
        game = battleship_games.get(gid)
        if not game:
            _safe_ack("Игра не найдена")
            return
        if not _bship_ensure_game_shape(game):
            _safe_ack("Игра повреждена")
            return
        _bship_store_public_anchor(game, call)

        uid = call.from_user.id

        if action == "dm":
            if uid not in (game.get("p1"), game.get("p2")):
                _safe_ack("Вы не участник этой партии", show_alert=True)
                return
            if _bship_send_or_edit_private(gid, game, uid):
                _safe_ack("Отправил поле в ЛС")
            else:
                _safe_ack("Не могу написать в ЛС. Откройте чат с ботом и нажмите Start", show_alert=True)
            return

        if action == "join":
            if game.get("status") != "waiting":
                _safe_ack("Игра уже началась")
                return
            if uid == game.get("p1"):
                _safe_ack("Нужен второй игрок")
                return

            game["p2"] = uid
            game["p2_name"] = call.from_user.first_name or call.from_user.username or str(uid)
            size = game.get("size", 5)
            ships_count = game.get("ships_count", 5)
            game.setdefault("ships", {})[uid] = _bship_random_ships(size, ships_count)
            game.setdefault("shots", {})[uid] = set()
            game["status"] = "playing"
            game["turn"] = game.get("p1")

            ok1, ok2 = _bship_sync_views(gid, game, call=call)
            if not ok1 or not ok2:
                _safe_ack("Партия началась. Если нет поля в ЛС — откройте чат с ботом и нажмите Start", show_alert=True)
            else:
                _safe_ack("Партия началась. Поля отправлены в ЛС")
            return

        if action == "new":
            if uid not in (game.get("p1"), game.get("p2")):
                _safe_ack("\u042d\u0442\u043e \u043d\u0435 \u0432\u0430\u0448\u0430 \u043f\u0430\u0440\u0442\u0438\u044f")
                return

            size = game.get("size", 5)
            ships_count = game.get("ships_count", 5)
            p1 = game.get("p1")
            p2 = game.get("p2")

            if not p2:
                game.update(_bship_new_game(p1, game.get("p1_name", "\u0418\u0433\u0440\u043e\u043a 1"), size=size, ships_count=ships_count))
                game["turn"] = uid
                game["shots"] = {p1: set()}
            else:
                game["status"] = "playing"
                game["ships"] = {
                    p1: _bship_random_ships(size, ships_count),
                    p2: _bship_random_ships(size, ships_count),
                }
                game["shots"] = {p1: set(), p2: set()}
            game["turn"] = p1
            game["winner"] = None

            _bship_sync_views(gid, game, call=call)
            _safe_ack("Новая партия. Обновил поля в ЛС")
            return

        if action == "shot":
            if len(parts) < 5:
                _safe_ack("Неверный ход")
                return
            if game.get("status") != "playing":
                _safe_ack("Партия не начата")
                return
            if uid != game.get("turn"):
                _safe_ack("Сейчас не ваш ход")
                return
            if uid not in (game.get("p1"), game.get("p2")):
                _safe_ack("Вы не участник этой партии")
                return

            r = int(parts[3])
            c = int(parts[4])
            size = game.get("size", 5)
            if r < 0 or c < 0 or r >= size or c >= size:
                _safe_ack("Некорректная клетка")
                return

            enemy = game.get("p2") if uid == game.get("p1") else game.get("p1")
            if not enemy:
                _safe_ack("Ожидаем второго игрока")
                return

            my_shots = game.setdefault("shots", {}).setdefault(uid, set())
            if (r, c) in my_shots:
                _safe_ack("Вы уже стреляли сюда")
                return

            my_shots.add((r, c))
            enemy_ships = game.setdefault("ships", {}).setdefault(enemy, set())

            if (r, c) in enemy_ships:
                if enemy_ships.issubset(my_shots):
                    game["status"] = "ended"
                    game["winner"] = uid
                    _bship_sync_views(gid, game, call=call)
                    _safe_ack("Попадание! Вы победили")
                    return
                _safe_ack("Попадание! Ходите еще")
            else:
                game["turn"] = enemy
                _safe_ack("Мимо")

            _bship_sync_views(gid, game, call=call)
            return

        _safe_ack()
    except Exception as e:
        print("BATTLESHIP CALLBACK ERROR:", e)
        _safe_ack("\u041e\u0448\u0438\u0431\u043a\u0430 \u041c\u043e\u0440\u0441\u043a\u043e\u0433\u043e \u0431\u043e\u044f")


@bot.callback_query_handler(func=lambda c: c.data.startswith("chess_"))
def chess_callback(call):
    _track_callback_game_play(call)
    try:
        parts = call.data.split("_")
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Неверные данные")
            return

        action = parts[1]
        gid = parts[2]
        game = chess_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра не найдена")
            return

        uid = call.from_user.id

        if action == "join":
            if game.get("status") != "waiting":
                bot.answer_callback_query(call.id, "Игра уже началась")
                return
            if uid == game.get("p1"):
                bot.answer_callback_query(call.id, "Нужен второй игрок")
                return
            game["p2"] = uid
            game["p2_name"] = call.from_user.first_name or call.from_user.username or str(uid)
            game["status"] = "playing"
            safe_edit_message(call, _chess_render_text(game), reply_markup=_chess_keyboard(gid, game))
            bot.answer_callback_query(call.id, "Партия началась")
            return

        if action == "new":
            if uid not in (game.get("p1"), game.get("p2")):
                bot.answer_callback_query(call.id, "Это не ваша партия")
                return
            new_game = _chess_new_game(uid, call.from_user.first_name or call.from_user.username or str(uid))
            chess_games[gid] = new_game
            safe_edit_message(call, _chess_render_text(new_game), reply_markup=_chess_keyboard(gid, new_game))
            bot.answer_callback_query(call.id, "Новая партия")
            return

        if action == "reset":
            if game.get("status") != "playing":
                bot.answer_callback_query(call.id)
                return
            if uid not in (game.get("p1"), game.get("p2")):
                bot.answer_callback_query(call.id, "Это не ваша партия")
                return
            game["selected"] = None
            safe_edit_message(call, _chess_render_text(game), reply_markup=_chess_keyboard(gid, game))
            bot.answer_callback_query(call.id, "Сброшено")
            return

        if action == "c":
            if len(parts) < 5:
                bot.answer_callback_query(call.id, "Неверный ход")
                return
            if game.get("status") != "playing":
                bot.answer_callback_query(call.id, "Партия не начата")
                return

            player_color = _chess_get_player_color(game, uid)
            if player_color is None:
                bot.answer_callback_query(call.id, "Вы не участник этой партии")
                return
            if player_color != game.get("turn"):
                bot.answer_callback_query(call.id, "Сейчас не ваш ход")
                return

            r = int(parts[3])
            c = int(parts[4])
            if not _chess_in_bounds(r, c):
                bot.answer_callback_query(call.id, "Некорректная клетка")
                return

            board = game["board"]
            selected = game.get("selected")

            if selected:
                sr, sc = selected
                legal = set(_chess_legal_moves(board, sr, sc))
                if (r, c) in legal:
                    _chess_apply_move(game, sr, sc, r, c)
                    safe_edit_message(call, _chess_render_text(game), reply_markup=_chess_keyboard(gid, game))
                    bot.answer_callback_query(call.id, "Ход выполнен")
                    return
                target = board[r][c]
                if target and target[0] == player_color:
                    game["selected"] = (r, c)
                    safe_edit_message(call, _chess_render_text(game), reply_markup=_chess_keyboard(gid, game))
                    bot.answer_callback_query(call.id, "Фигура выбрана")
                    return
                bot.answer_callback_query(call.id, "Сюда ходить нельзя")
                return

            piece = board[r][c]
            if not piece:
                bot.answer_callback_query(call.id, "Выберите свою фигуру")
                return
            if piece[0] != player_color:
                bot.answer_callback_query(call.id, "Это фигура соперника")
                return
            game["selected"] = (r, c)
            safe_edit_message(call, _chess_render_text(game), reply_markup=_chess_keyboard(gid, game))
            bot.answer_callback_query(call.id, "Фигура выбрана")
            return

        bot.answer_callback_query(call.id)
    except Exception as e:
        print("CHESS CALLBACK ERROR:", e)
        bot.answer_callback_query(call.id, "Ошибка шахмат")

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
    _track_callback_game_play(call)
    try:
        _, gid, x, y = call.data.split("_")
        x, y = int(x), int(y)
        game = minesweeper_games.get(gid)
        if not game:
            bot.answer_callback_query(call.id, "Игра завершена!")
            return
        board = game["board"]; revealed = game["revealed"]; mine_positions = game["mine_positions"]
        if (x, y) in mine_positions:
            safe_edit_message(call, f"💥 Вы наткнулись на мину!\n\n{render_minesweeper_board(board, revealed.union(mine_positions))}")
            minesweeper_games.pop(gid, None)
            bot.answer_callback_query(call.id)
            return
        revealed.add((x, y))
        if len(revealed) == len(board)*len(board) - len(mine_positions):
            safe_edit_message(call, f"🎉 Вы выиграли!\n\n{render_minesweeper_board(board, revealed.union(mine_positions))}")
            minesweeper_games.pop(gid, None)
            bot.answer_callback_query(call.id)
            return
        markup = _minesweeper_build_markup(gid, board, revealed)
        safe_edit_message(call, f"💣 Сапёр\n{render_minesweeper_board(board, revealed)}", reply_markup=markup)
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
                result = "🎲"
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
            bot.send_message(uid, f"Тема: {st['settings']['theme']}")
            safe_edit_message(call, _telos_home_text(uid), reply_markup=telos_main_menu(), parse_mode="Markdown")
            return

        if data == "os_set_reset":
            st = _telos_default_state()
            _telos_save_state(uid, st)
            bot.send_message(uid, "TELOS сброшен")
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
    _track_callback_game_play(call)
    res = random.choice(["🪙 Орёл","🪙 Решка"])
    bot.edit_message_text(f"Результат: {res}", inline_message_id=call.inline_message_id)
    bot.answer_callback_query(call.id, res)

@bot.callback_query_handler(func=lambda c: c.data == "slot_spin")
def slot_spin(call):
    _track_callback_game_play(call)
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

@bot.message_handler(func=lambda m: m.from_user.id in support_chat_wait, content_types=["text", "photo", "video"])
def support_user_message(message):
    uid = message.from_user.id
    mode = support_chat_wait.get(uid)
    text = (message.text or "").strip()
    caption = (message.caption or "").strip()
    if message.content_type == "text" and (not text or text.startswith("/")):
        return

    if mode == "moderator" and message.content_type != "text":
        bot.send_message(message.chat.id, "В режиме модератора отправьте текстовое сообщение.")
        return

    support_chat_wait.pop(uid, None)
    user_link = f"@{message.from_user.username}" if message.from_user.username else "без username"
    user_name = message.from_user.first_name or "Пользователь"
    mode_label = "Модератору" if mode == "moderator" else "Проблема"
    payload = (
        f"📩 <b>Новое обращение в поддержку</b>\n"
        f"Тип: <b>{mode_label}</b>\n"
        f"ID: <code>{uid}</code>\n"
        f"Имя: {html.escape(user_name)}\n"
        f"Username: {html.escape(user_link)}\n"
        f"Контент: <b>{message.content_type}</b>\n\n"
        f"<i>Ответить:</i> <code>/reply {uid} ваш_ответ</code>"
    )

    sent = 0
    for admin_id in SUPPORT_ADMIN_IDS:
        try:
            bot.send_message(admin_id, payload, parse_mode="HTML")
            # Forward original message so moderator sees exact user text/media.
            bot.forward_message(admin_id, message.chat.id, message.message_id)
            if caption and message.content_type in ("photo", "video"):
                bot.send_message(admin_id, f"Подпись:\n{html.escape(caption)}", parse_mode="HTML")
            sent += 1
        except Exception:
            pass

    if sent:
        bot.send_message(message.chat.id, "✅ Сообщение отправлено в поддержку. Ожидайте ответ здесь в боте.")
    else:
        bot.send_message(message.chat.id, "❌ Сейчас нет доступных операторов поддержки.")

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

@bot.message_handler(func=lambda m: m.from_user.id in admin_wait)
def admin_wait_input(message):
    uid = message.from_user.id
    wait = admin_wait.pop(uid, None)
    if not wait:
        return
    action = wait.get("action")
    if action == "close_room":
        code = (message.text or "").strip().upper()
        if not code:
            bot.send_message(uid, "Код пуст.")
            return
        ok = _room_close(code, reason="закрыто админом")
        if ok:
            bot.send_message(uid, f"✅ Пати {code} закрыто.")
        else:
            bot.send_message(uid, f"❌ Пати {code} не найдено.")
        return

@bot.message_handler(func=lambda m: m.chat and m.chat.type in ("group", "supergroup"))
def room_track_messages(message):
    try:
        d, rooms = _rooms_get_data()
        code, room = _room_find_by_chat(rooms, message.chat.id)
        if not room:
            return
        chat_id = message.chat.id
        msg_list = room_messages.setdefault(chat_id, [])
        msg_list.append(message.message_id)
        if ROOM_MESSAGE_BUFFER and len(msg_list) > ROOM_MESSAGE_BUFFER:
            room_messages[chat_id] = msg_list[-ROOM_MESSAGE_BUFFER:]
        room_participants.setdefault(chat_id, set()).add(message.from_user.id)
        participants = room.get("participants", [])
        if isinstance(participants, list) and message.from_user.id not in participants:
            participants.append(message.from_user.id)
            room["participants"] = participants
            rooms["active"][code] = room
            save_data(d)
    except Exception:
        pass

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
    Thread(target=_rooms_watchdog, daemon=True).start()
    print("✅ Бот запущен")
    bot.infinity_polling()
