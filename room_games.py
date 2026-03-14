import random
import time
from threading import Thread
from telebot import types

# Room-only games (no inline). Keep keys unique and stable.
ROOM_VOTE_GAMES = [
    ("room_rps", "Камень-ножницы-бумага"),
    ("room_duel", "Быстрая дуэль"),
    ("room_bship", "Морской бой"),
    ("room_quiz", "Викторина"),
    ("room_combo", "Комбо-битва"),
    ("room_mafia", "Мафия"),
]

# In-memory state for room games
_room_rps_state = {}    # code -> {"players": [uid], "names": {uid: name}, "moves": {uid: move}}
_room_duel_state = {}   # code -> {"players": set(uid), "names": {uid: name}, "ready": set(uid)}
_room_bship_state = {}  # code -> {"chat_id": int, "players": [uid], "names": {uid: name}, "turn": uid, "ships": {uid:set}, "shots": {uid:set}}
_room_quiz_state = {}   # code -> {"chat_id": int, "players": set(uid), "names": {uid: name}, "scores": {uid:int}, "qidx": int}
_room_combo_state = {}  # code -> {"chat_id": int, "players": [uid], "names": {uid: name}, "moves": {uid: move}, "hp": {uid:int}}
_room_mafia_state = {}  # code -> {"chat_id": int, "players": set(uid), "names": {uid: name}, "votes": {uid:uid}, "mafia": uid}


def is_room_game(game_key):
    return any(k == game_key for k, _ in ROOM_VOTE_GAMES)


def room_game_start_text(game_key):
    if game_key == "room_rps":
        return "Игра в чате. Нажмите «Присоединиться», затем выберите ход."
    if game_key == "room_duel":
        return "Игра в чате. Нажмите «Присоединиться», затем «Готов». Победитель выбирается случайно."
    if game_key == "room_bship":
        return "Игра в чате. Нужны 2 игрока. Ходы вводятся сообщением: A1–E5."
    if game_key == "room_quiz":
        return "Игра в чате. Нажмите «Присоединиться». Вопросы появятся ниже."
    if game_key == "room_combo":
        return "Игра в чате. Нажмите «Присоединиться», затем выбирайте приемы."
    if game_key == "room_mafia":
        return "Игра в чате. Нажмите «Присоединиться». После старта — голосование."
    return "Игра в чате."


def room_game_launch(bot, chat_id, code, room=None):
    game_key = room.get("game") if isinstance(room, dict) else None
    if game_key == "room_rps":
        _room_rps_launch(bot, chat_id, code)
        return True
    if game_key == "room_duel":
        _room_duel_launch(bot, chat_id, code)
        return True
    if game_key == "room_bship":
        _room_bship_launch(bot, chat_id, code)
        return True
    if game_key == "room_quiz":
        _room_quiz_launch(bot, chat_id, code)
        return True
    if game_key == "room_combo":
        _room_combo_launch(bot, chat_id, code)
        return True
    if game_key == "room_mafia":
        _room_mafia_launch(bot, chat_id, code)
        return True
    return False


def _display_name(user):
    if not user:
        return "Игрок"
    if getattr(user, "username", None):
        return f"@{user.username}"
    return user.first_name or f"user_{user.id}"


def _room_rps_launch(bot, chat_id, code):
    _room_rps_state[code] = {"players": [], "names": {}, "moves": {}}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🤝 Присоединиться", callback_data=f"roomrps_join_{code}"))
    bot.send_message(chat_id, "🎮 Камень-ножницы-бумага\nНужны 2 игрока.", reply_markup=kb)


def _room_duel_launch(bot, chat_id, code):
    _room_duel_state[code] = {"players": set(), "names": {}, "ready": set()}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🤝 Присоединиться", callback_data=f"roomduel_join_{code}"))
    bot.send_message(chat_id, "⚔️ Быстрая дуэль\nНужны минимум 2 игрока.", reply_markup=kb)


def _room_bship_launch(bot, chat_id, code):
    _room_bship_state[code] = {
        "chat_id": chat_id,
        "players": [],
        "names": {},
        "turn": None,
        "ships": {},
        "shots": {},
    }
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🤝 Присоединиться", callback_data=f"roombship_join_{code}"))
    bot.send_message(chat_id, "🚢 Морской бой\nНужны 2 игрока. Вводите ходы как A1–E5.", reply_markup=kb)


def _room_quiz_launch(bot, chat_id, code):
    _room_quiz_state[code] = {"chat_id": chat_id, "players": set(), "names": {}, "scores": {}, "qidx": 0}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🤝 Присоединиться", callback_data=f"roomquiz_join_{code}"))
    bot.send_message(chat_id, "🧠 Викторина\nНажмите «Присоединиться», затем «Старт».", reply_markup=kb)


def _room_combo_launch(bot, chat_id, code):
    _room_combo_state[code] = {"chat_id": chat_id, "players": [], "names": {}, "moves": {}, "hp": {}}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🤝 Присоединиться", callback_data=f"roomcombo_join_{code}"))
    bot.send_message(chat_id, "🥊 Комбо-битва\nНужны 2 игрока.", reply_markup=kb)


def _room_mafia_launch(bot, chat_id, code):
    _room_mafia_state[code] = {"chat_id": chat_id, "players": set(), "names": {}, "votes": {}, "mafia": None}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🤝 Присоединиться", callback_data=f"roommafia_join_{code}"))
    bot.send_message(chat_id, "🕵️ Мафия\nНужны минимум 3 игрока.", reply_markup=kb)


def register_room_game_handlers(bot):
    @bot.callback_query_handler(func=lambda c: c.data.startswith("roomrps_join_"))
    def room_rps_join(call):
        code = call.data.split("_", 2)[2]
        st = _room_rps_state.setdefault(code, {"players": [], "names": {}, "moves": {}})
        uid = call.from_user.id
        st["names"][uid] = _display_name(call.from_user)
        if uid in st["players"]:
            bot.answer_callback_query(call.id, "Вы уже в игре.")
            return
        if len(st["players"]) >= 2:
            bot.answer_callback_query(call.id, "В игре уже 2 игрока.")
            return
        st["players"].append(uid)
        bot.answer_callback_query(call.id, "Вы в игре!")
        if len(st["players"]) == 2:
            kb = types.InlineKeyboardMarkup()
            kb.row(
                types.InlineKeyboardButton("🪨 Камень", callback_data=f"roomrps_move_{code}_rock"),
                types.InlineKeyboardButton("📄 Бумага", callback_data=f"roomrps_move_{code}_paper"),
                types.InlineKeyboardButton("✂️ Ножницы", callback_data=f"roomrps_move_{code}_scissors"),
            )
            bot.send_message(call.message.chat.id, "Ходы: выберите вариант.", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roomrps_move_"))
    def room_rps_move(call):
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Ошибка данных.")
            return
        code = parts[2]
        move = parts[3]
        st = _room_rps_state.get(code)
        if not st:
            bot.answer_callback_query(call.id, "Игра не найдена.")
            return
        uid = call.from_user.id
        if uid not in st["players"]:
            bot.answer_callback_query(call.id, "Вы не участвуете в этой партии.")
            return
        if uid in st["moves"]:
            bot.answer_callback_query(call.id, "Вы уже сделали ход.")
            return
        if move not in ("rock", "paper", "scissors"):
            bot.answer_callback_query(call.id, "Неверный ход.")
            return
        st["moves"][uid] = move
        bot.answer_callback_query(call.id, "Ход принят.")

        if len(st["moves"]) < 2:
            return

        p1, p2 = st["players"][0], st["players"][1]
        m1, m2 = st["moves"].get(p1), st["moves"].get(p2)
        if not m1 or not m2:
            return

        res = _rps_result(m1, m2)
        if res == 0:
            text = "🤝 Ничья!"
        elif res == 1:
            text = f"🎉 Победил {st['names'].get(p1, p1)}"
        else:
            text = f"🎉 Победил {st['names'].get(p2, p2)}"
        bot.send_message(call.message.chat.id, text)
        _room_rps_state.pop(code, None)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roomduel_join_"))
    def room_duel_join(call):
        code = call.data.split("_", 2)[2]
        st = _room_duel_state.setdefault(code, {"players": set(), "names": {}, "ready": set()})
        uid = call.from_user.id
        st["players"].add(uid)
        st["names"][uid] = _display_name(call.from_user)
        bot.answer_callback_query(call.id, "Вы в дуэли!")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ Готов", callback_data=f"roomduel_ready_{code}"))
        bot.send_message(call.message.chat.id, "Нажмите «Готов», когда будете готовы.", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roomduel_ready_"))
    def room_duel_ready(call):
        code = call.data.split("_", 2)[2]
        st = _room_duel_state.get(code)
        if not st:
            bot.answer_callback_query(call.id, "Игра не найдена.")
            return
        uid = call.from_user.id
        st["ready"].add(uid)
        bot.answer_callback_query(call.id, "Принято.")
        if len(st["ready"]) >= 2:
            winner = random.choice(list(st["ready"]))
            bot.send_message(call.message.chat.id, f"🏆 Победил {st['names'].get(winner, winner)}")
            _room_duel_state.pop(code, None)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roombship_join_"))
    def room_bship_join(call):
        code = call.data.split("_", 2)[2]
        st = _room_bship_state.setdefault(
            code,
            {"chat_id": call.message.chat.id, "players": [], "names": {}, "turn": None, "ships": {}, "shots": {}},
        )
        uid = call.from_user.id
        if uid in st["players"]:
            bot.answer_callback_query(call.id, "Вы уже в игре.")
            return
        if len(st["players"]) >= 2:
            bot.answer_callback_query(call.id, "В игре уже 2 игрока.")
            return
        st["players"].append(uid)
        st["names"][uid] = _display_name(call.from_user)
        bot.answer_callback_query(call.id, "Вы в игре!")
        if len(st["players"]) == 2:
            _bship_init_round(bot, st)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roomquiz_join_"))
    def room_quiz_join(call):
        code = call.data.split("_", 2)[2]
        st = _room_quiz_state.setdefault(
            code,
            {"chat_id": call.message.chat.id, "players": set(), "names": {}, "scores": {}, "qidx": 0, "answered": {}},
        )
        uid = call.from_user.id
        st["players"].add(uid)
        st["names"][uid] = _display_name(call.from_user)
        st["scores"].setdefault(uid, 0)
        bot.answer_callback_query(call.id, "Вы в викторине!")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("▶️ Старт", callback_data=f"roomquiz_start_{code}"))
        bot.send_message(call.message.chat.id, "Когда все подключились — жмите «Старт».", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roomquiz_start_"))
    def room_quiz_start(call):
        code = call.data.split("_", 2)[2]
        st = _room_quiz_state.get(code)
        if not st:
            bot.answer_callback_query(call.id, "Игра не найдена.")
            return
        if len(st["players"]) < 1:
            bot.answer_callback_query(call.id, "Нужен хотя бы 1 игрок.")
            return
        bot.answer_callback_query(call.id, "Стартуем!")
        _quiz_next_question(bot, code)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roomquiz_ans_"))
    def room_quiz_answer(call):
        parts = call.data.split("_")
        if len(parts) < 5:
            bot.answer_callback_query(call.id, "Ошибка.")
            return
        code = parts[2]
        qidx = int(parts[3])
        ans = int(parts[4])
        st = _room_quiz_state.get(code)
        if not st or st.get("qidx") != qidx:
            bot.answer_callback_query(call.id, "Этот вопрос уже завершен.")
            return
        uid = call.from_user.id
        if uid not in st["players"]:
            bot.answer_callback_query(call.id, "Вы не в игре.")
            return
        answered = st.setdefault("answered", {}).setdefault(qidx, set())
        if uid in answered:
            bot.answer_callback_query(call.id, "Вы уже ответили.")
            return
        answered.add(uid)
        if _QUIZ_QUESTIONS[qidx]["answer"] == ans:
            st["scores"][uid] = st["scores"].get(uid, 0) + 1
            bot.answer_callback_query(call.id, "Верно!")
        else:
            bot.answer_callback_query(call.id, "Неверно.")

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roomcombo_join_"))
    def room_combo_join(call):
        code = call.data.split("_", 2)[2]
        st = _room_combo_state.setdefault(
            code, {"chat_id": call.message.chat.id, "players": [], "names": {}, "moves": {}, "hp": {}}
        )
        uid = call.from_user.id
        if uid in st["players"]:
            bot.answer_callback_query(call.id, "Вы уже в игре.")
            return
        if len(st["players"]) >= 2:
            bot.answer_callback_query(call.id, "В игре уже 2 игрока.")
            return
        st["players"].append(uid)
        st["names"][uid] = _display_name(call.from_user)
        bot.answer_callback_query(call.id, "Вы в игре!")
        if len(st["players"]) == 2:
            st["hp"] = {st["players"][0]: 3, st["players"][1]: 3}
            _combo_prompt_moves(bot, call.message.chat.id, code)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roomcombo_move_"))
    def room_combo_move(call):
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Ошибка.")
            return
        code = parts[2]
        move = parts[3]
        st = _room_combo_state.get(code)
        if not st:
            bot.answer_callback_query(call.id, "Игра не найдена.")
            return
        uid = call.from_user.id
        if uid not in st["players"]:
            bot.answer_callback_query(call.id, "Вы не участвуете.")
            return
        if move not in ("punch", "kick", "block"):
            bot.answer_callback_query(call.id, "Неверный прием.")
            return
        st["moves"][uid] = move
        bot.answer_callback_query(call.id, "Принято.")
        if len(st["moves"]) < 2:
            return
        _combo_resolve_round(bot, call.message.chat.id, code)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roommafia_join_"))
    def room_mafia_join(call):
        code = call.data.split("_", 2)[2]
        st = _room_mafia_state.setdefault(
            code, {"chat_id": call.message.chat.id, "players": set(), "names": {}, "votes": {}, "mafia": None}
        )
        uid = call.from_user.id
        st["players"].add(uid)
        st["names"][uid] = _display_name(call.from_user)
        bot.answer_callback_query(call.id, "Вы в мафии!")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("▶️ Старт", callback_data=f"roommafia_start_{code}"))
        bot.send_message(call.message.chat.id, "Когда все подключились — жмите «Старт».", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roommafia_start_"))
    def room_mafia_start(call):
        code = call.data.split("_", 2)[2]
        st = _room_mafia_state.get(code)
        if not st or len(st["players"]) < 3:
            bot.answer_callback_query(call.id, "Нужно минимум 3 игрока.")
            return
        mafia = random.choice(list(st["players"]))
        st["mafia"] = mafia
        bot.answer_callback_query(call.id, "Старт!")
        bot.send_message(call.message.chat.id, f"Мафия назначена. Голосуем!")
        _mafia_vote_prompt(bot, call.message.chat.id, code)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("roommafia_vote_"))
    def room_mafia_vote(call):
        parts = call.data.split("_")
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Ошибка.")
            return
        code = parts[2]
        target = int(parts[3])
        st = _room_mafia_state.get(code)
        if not st:
            bot.answer_callback_query(call.id, "Игра не найдена.")
            return
        uid = call.from_user.id
        if uid not in st["players"]:
            bot.answer_callback_query(call.id, "Вы не участник.")
            return
        st["votes"][uid] = target
        bot.answer_callback_query(call.id, "Голос учтен.")
        if len(st["votes"]) == len(st["players"]):
            _mafia_finish(bot, call.message.chat.id, code)

    @bot.message_handler(func=lambda m: bool(m.chat) and m.chat.type in ("group", "supergroup") and bool(_find_bship_code_by_chat(m.chat.id)))
    def room_bship_message_router(message):
        text = (message.text or "").strip().upper()
        if len(text) != 2:
            return
        code = _find_bship_code_by_chat(message.chat.id)
        if not code:
            return
        st = _room_bship_state.get(code)
        if not st:
            return
        _bship_handle_shot(bot, message, st, text)


_QUIZ_QUESTIONS = [
    {"q": "Столица Франции?", "opts": ["Лион", "Париж", "Марсель", "Нант"], "answer": 1},
    {"q": "2 + 2 = ?", "opts": ["3", "4", "5", "6"], "answer": 1},
    {"q": "Самая большая планета?", "opts": ["Марс", "Земля", "Юпитер", "Венера"], "answer": 2},
    {"q": "Сколько дней в неделе?", "opts": ["5", "6", "7", "8"], "answer": 2},
    {"q": "Что из этого — язык программирования?", "opts": ["Python", "Violet", "Mercury", "Omega"], "answer": 0},
]


def _quiz_next_question(bot, code):
    st = _room_quiz_state.get(code)
    if not st:
        return
    qidx = st.get("qidx", 0)
    if qidx >= len(_QUIZ_QUESTIONS):
        _quiz_finish(bot, st["chat_id"], code)
        return
    q = _QUIZ_QUESTIONS[qidx]
    kb = types.InlineKeyboardMarkup()
    for i, opt in enumerate(q["opts"]):
        kb.add(types.InlineKeyboardButton(opt, callback_data=f"roomquiz_ans_{code}_{qidx}_{i}"))
    bot.send_message(st["chat_id"], f"❓ {q['q']}", reply_markup=kb)

    def finalize():
        time.sleep(20)
        st2 = _room_quiz_state.get(code)
        if not st2 or st2.get("qidx") != qidx:
            return
        st2["qidx"] = qidx + 1
        _quiz_next_question(bot, code)

    Thread(target=finalize, daemon=True).start()


def _quiz_finish(bot, chat_id, code):
    st = _room_quiz_state.get(code)
    if not st:
        return
    scores = st.get("scores", {})
    if not scores:
        bot.send_message(chat_id, "Викторина завершена. Нет ответов.")
    else:
        top = max(scores.values())
        winners = [uid for uid, sc in scores.items() if sc == top]
        names = ", ".join([st["names"].get(uid, str(uid)) for uid in winners])
        bot.send_message(chat_id, f"🏆 Победители: {names} (очки: {top})")
    _room_quiz_state.pop(code, None)


def _combo_prompt_moves(bot, chat_id, code):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("👊 Удар", callback_data=f"roomcombo_move_{code}_punch"),
        types.InlineKeyboardButton("🦵 Пинок", callback_data=f"roomcombo_move_{code}_kick"),
        types.InlineKeyboardButton("🛡 Блок", callback_data=f"roomcombo_move_{code}_block"),
    )
    bot.send_message(chat_id, "Выберите прием:", reply_markup=kb)


def _combo_resolve_round(bot, chat_id, code):
    st = _room_combo_state.get(code)
    if not st:
        return
    p1, p2 = st["players"][0], st["players"][1]
    m1, m2 = st["moves"].get(p1), st["moves"].get(p2)
    if not m1 or not m2:
        return
    res = _rps_result(_combo_to_rps(m1), _combo_to_rps(m2))
    if res == 1:
        st["hp"][p2] -= 1
        bot.send_message(chat_id, f"Раунд за {st['names'].get(p1, p1)}")
    elif res == 2:
        st["hp"][p1] -= 1
        bot.send_message(chat_id, f"Раунд за {st['names'].get(p2, p2)}")
    else:
        bot.send_message(chat_id, "Раунд вничью")
    st["moves"] = {}
    if st["hp"][p1] <= 0 or st["hp"][p2] <= 0:
        winner = p1 if st["hp"][p1] > st["hp"][p2] else p2
        bot.send_message(chat_id, f"🏆 Победил {st['names'].get(winner, winner)}")
        _room_combo_state.pop(code, None)
        return
    bot.send_message(chat_id, f"HP: {st['names'].get(p1, p1)}={st['hp'][p1]} | {st['names'].get(p2, p2)}={st['hp'][p2]}")
    _combo_prompt_moves(bot, chat_id, code)


def _combo_to_rps(move):
    return {"punch": "rock", "kick": "scissors", "block": "paper"}[move]


def _mafia_vote_prompt(bot, chat_id, code):
    st = _room_mafia_state.get(code)
    if not st:
        return
    kb = types.InlineKeyboardMarkup()
    for uid in st["players"]:
        name = st["names"].get(uid, str(uid))
        kb.add(types.InlineKeyboardButton(name, callback_data=f"roommafia_vote_{code}_{uid}"))
    bot.send_message(chat_id, "Голосование: выберите игрока.", reply_markup=kb)

    def finalize():
        time.sleep(25)
        st2 = _room_mafia_state.get(code)
        if not st2:
            return
        _mafia_finish(bot, chat_id, code)

    Thread(target=finalize, daemon=True).start()


def _mafia_finish(bot, chat_id, code):
    st = _room_mafia_state.get(code)
    if not st:
        return
    votes = st.get("votes", {})
    if not votes:
        bot.send_message(chat_id, "Голосов нет. Победила мафия.")
        _room_mafia_state.pop(code, None)
        return
    tally = {}
    for _, target in votes.items():
        tally[target] = tally.get(target, 0) + 1
    target = max(tally, key=tally.get)
    if target == st.get("mafia"):
        bot.send_message(chat_id, f"🎉 Мафия поймана! Победа граждан.")
    else:
        mafia_name = st["names"].get(st.get("mafia"), "мафия")
        bot.send_message(chat_id, f"💀 Мафия победила. Мафия была: {mafia_name}")
    _room_mafia_state.pop(code, None)


def _bship_init_round(bot, st):
    players = st["players"]
    st["ships"][players[0]] = _bship_place_ships()
    st["ships"][players[1]] = _bship_place_ships()
    st["shots"][players[0]] = set()
    st["shots"][players[1]] = set()
    st["turn"] = players[0]
    bot.send_message(st["chat_id"], f"Игра началась! Первый ход: {st['names'].get(players[0], players[0])}.")


def _bship_place_ships():
    cells = set()
    while len(cells) < 3:
        r = random.choice("ABCDE")
        c = random.randint(1, 5)
        cells.add(f"{r}{c}")
    return cells


def _find_bship_code_by_chat(chat_id):
    for code, st in _room_bship_state.items():
        if st.get("chat_id") == chat_id:
            return code
    return None


def _bship_handle_shot(bot, message, st, text):
    uid = message.from_user.id
    if uid != st.get("turn"):
        return
    if text[0] not in "ABCDE" or text[1] not in "12345":
        return
    if text in st["shots"].get(uid, set()):
        bot.send_message(st["chat_id"], "Эта клетка уже была.")
        return
    st["shots"][uid].add(text)
    opponent = st["players"][1] if st["players"][0] == uid else st["players"][0]
    if text in st["ships"][opponent]:
        st["ships"][opponent].remove(text)
        bot.send_message(st["chat_id"], f"💥 Попадание! {st['names'].get(uid, uid)}")
        if not st["ships"][opponent]:
            bot.send_message(st["chat_id"], f"🏆 Победил {st['names'].get(uid, uid)}")
            _room_bship_state.pop(_find_bship_code_by_chat(st["chat_id"]), None)
            return
    else:
        bot.send_message(st["chat_id"], "Мимо.")
    st["turn"] = opponent
    bot.send_message(st["chat_id"], f"Ход: {st['names'].get(opponent, opponent)}")


def _rps_result(m1, m2):
    if m1 == m2:
        return 0
    wins = {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}
    return 1 if (m1, m2) in wins else 2
