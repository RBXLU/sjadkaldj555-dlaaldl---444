import random
import time
from telebot import types


BUSINESS_GAME_ALIASES = {
    "tetris": {
        "тетрис", "tetris", "игра тетрис", "play tetris",
    },
    "g2048": {
        "2048", "игра 2048", "две тысячи сорок восемь",
    },
    "rps": {
        "кнб", "камень ножницы бумага", "камень-ножницы-бумага",
        "rps", "rock paper scissors",
    },
    "guess": {
        "угадай число", "guess", "guess number",
    },
    "slot": {
        "казино", "слот", "slot", "casino",
    },
    "coin": {
        "орел или решка", "орёл или решка", "монетка", "coin", "coin flip",
    },
}

_business_runtime = {
    "games_2048": {},
    "games_tetris": {},
    "games_guess": {},
}


def _normalize_text(text):
    if not text:
        return ""
    t = text.strip().lower().replace("ё", "е")
    while "  " in t:
        t = t.replace("  ", " ")
    t = t.replace("-", " ")
    return t


def _short_id():
    return str(int(time.time() * 1000))


def is_business_game_trigger(text: str):
    norm = _normalize_text(text)
    if not norm:
        return False, ""
    for game_id, aliases in BUSINESS_GAME_ALIASES.items():
        if norm in aliases:
            return True, game_id
    return False, ""


def _is_business_message(message):
    # Fallback-friendly business detection for different library versions.
    return bool(
        getattr(message, "business_connection_id", None)
        or getattr(message, "business_connection", None)
        or getattr(message, "sender_business_bot", None)
    )


def _render_2048(board):
    icons = {
        0: "⬜", 2: "🟩", 4: "🟨", 8: "🟧", 16: "🟥",
        32: "🟪", 64: "🟫", 128: "🟦", 256: "🟦", 512: "🟦",
        1024: "🟦", 2048: "🟩",
    }
    lines = []
    for row in board:
        line = []
        for v in row:
            line.append(f"{icons.get(v, '🟪')}{str(v) if v else ''}".ljust(4))
        lines.append(" ".join(line))
    return "🔢 2048\n\n" + "\n".join(lines)


def _spawn_2048(board):
    empty = [(y, x) for y in range(4) for x in range(4) if board[y][x] == 0]
    if not empty:
        return board
    y, x = random.choice(empty)
    board[y][x] = 2 if random.random() < 0.9 else 4
    return board


def _move_row_left_2048(row):
    new = [v for v in row if v != 0]
    out = []
    i = 0
    while i < len(new):
        if i + 1 < len(new) and new[i] == new[i + 1]:
            out.append(new[i] * 2)
            i += 2
        else:
            out.append(new[i])
            i += 1
    out += [0] * (4 - len(out))
    return out


def _move_board_2048(board, direction):
    moved = False
    new = [[board[y][x] for x in range(4)] for y in range(4)]
    if direction in ("left", "right"):
        for y in range(4):
            row = list(new[y])
            if direction == "right":
                row = row[::-1]
            moved_row = _move_row_left_2048(row)
            if direction == "right":
                moved_row = moved_row[::-1]
            if moved_row != new[y]:
                moved = True
            new[y] = moved_row
    else:
        for x in range(4):
            col = [new[y][x] for y in range(4)]
            if direction == "down":
                col = col[::-1]
            moved_col = _move_row_left_2048(col)
            if direction == "down":
                moved_col = moved_col[::-1]
            for y in range(4):
                if new[y][x] != moved_col[y]:
                    moved = True
                new[y][x] = moved_col[y]
    return new, moved


def _kb_2048(gid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("⬆️", callback_data=f"biz_2048_{gid}_up"))
    kb.row(
        types.InlineKeyboardButton("⬅️", callback_data=f"biz_2048_{gid}_left"),
        types.InlineKeyboardButton("➡️", callback_data=f"biz_2048_{gid}_right"),
    )
    kb.row(types.InlineKeyboardButton("⬇️", callback_data=f"biz_2048_{gid}_down"))
    return kb


def _new_tetris_state():
    st = {
        "w": 10,
        "h": 14,
        "board": [[0] * 10 for _ in range(14)],
        "piece": None,
        "over": False,
    }
    _spawn_tetris_piece(st)
    return st


_TETRIS_SHAPES = [
    [[1, 1, 1, 1]], [[1, 1], [1, 1]], [[1, 1, 1], [0, 1, 0]],
    [[1, 1, 1], [1, 0, 0]], [[1, 1, 1], [0, 0, 1]],
    [[1, 1, 0], [0, 1, 1]], [[0, 1, 1], [1, 1, 0]],
]
_TETRIS_COLORS = ["🟥", "🟧", "🟨", "🟩", "🟦", "🟪", "🟫"]


def _can_place_tetris(st, px, py, shape):
    for sy, row in enumerate(shape):
        for sx, v in enumerate(row):
            if not v:
                continue
            x = px + sx
            y = py + sy
            if x < 0 or x >= st["w"] or y < 0 or y >= st["h"]:
                return False
            if st["board"][y][x]:
                return False
    return True


def _spawn_tetris_piece(st):
    shape = random.choice(_TETRIS_SHAPES)
    color = random.randint(1, len(_TETRIS_COLORS))
    px = (st["w"] - len(shape[0])) // 2
    py = 0
    if not _can_place_tetris(st, px, py, shape):
        st["over"] = True
        return False
    st["piece"] = {"x": px, "y": py, "shape": shape, "color": color}
    return True


def _lock_tetris_piece(st):
    p = st.get("piece")
    if not p:
        return
    for sy, row in enumerate(p["shape"]):
        for sx, v in enumerate(row):
            if v:
                st["board"][p["y"] + sy][p["x"] + sx] = p["color"]
    st["piece"] = None


def _clear_tetris_lines(st):
    board = []
    for row in st["board"]:
        if not all(c > 0 for c in row):
            board.append(row)
    while len(board) < st["h"]:
        board.insert(0, [0] * st["w"])
    st["board"] = board


def _drop_tetris(st):
    p = st.get("piece")
    if not p or st.get("over"):
        return
    while _can_place_tetris(st, p["x"], p["y"] + 1, p["shape"]):
        p["y"] += 1
    _lock_tetris_piece(st)
    _clear_tetris_lines(st)
    _spawn_tetris_piece(st)


def _move_tetris(st, dx):
    p = st.get("piece")
    if not p or st.get("over"):
        return
    nx = p["x"] + dx
    if _can_place_tetris(st, nx, p["y"], p["shape"]):
        p["x"] = nx


def _render_tetris(st):
    view = [[st["board"][y][x] for x in range(st["w"])] for y in range(st["h"])]
    p = st.get("piece")
    if p:
        for sy, row in enumerate(p["shape"]):
            for sx, v in enumerate(row):
                if v:
                    y = p["y"] + sy
                    x = p["x"] + sx
                    if 0 <= y < st["h"] and 0 <= x < st["w"]:
                        view[y][x] = p["color"]
    lines = []
    for y in range(st["h"]):
        row = []
        for x in range(st["w"]):
            v = view[y][x]
            row.append(_TETRIS_COLORS[v - 1] if v > 0 else "⬛")
        lines.append("".join(row))
    text = "🧱 Тетрис (Business)\n\n" + "\n".join(lines)
    if st.get("over"):
        text += "\n\n💀 Игра окончена"
    return text


def _kb_tetris(gid, over=False):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("⬅️", callback_data=f"biz_tetris_{gid}_left"),
        types.InlineKeyboardButton("➡️", callback_data=f"biz_tetris_{gid}_right"),
    )
    kb.row(types.InlineKeyboardButton("⬇️ Отпустить", callback_data=f"biz_tetris_{gid}_drop"))
    if over:
        kb.row(types.InlineKeyboardButton("🔁 Новая игра", callback_data=f"biz_tetris_{gid}_new"))
    return kb


def _kb_rps(gid):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🪨", callback_data=f"biz_rps_{gid}_rock"),
        types.InlineKeyboardButton("📄", callback_data=f"biz_rps_{gid}_paper"),
        types.InlineKeyboardButton("✂️", callback_data=f"biz_rps_{gid}_scissors"),
    )
    return kb


def _kb_guess(gid):
    kb = types.InlineKeyboardMarkup()
    row = []
    for i in range(1, 11):
        row.append(types.InlineKeyboardButton(str(i), callback_data=f"biz_guess_{gid}_{i}"))
        if i % 5 == 0:
            kb.row(*row)
            row = []
    return kb


def _kb_slot():
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🎰 Крутить", callback_data="biz_slot_spin")
    )


def _kb_coin():
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🪙 Бросить", callback_data="biz_coin_flip")
    )


def start_business_game(bot, message, game_id: str):
    if game_id == "coin":
        bot.send_message(message.chat.id, "🪙 Орёл или решка", reply_markup=_kb_coin())
        return
    if game_id == "slot":
        bot.send_message(message.chat.id, "🎰 Казино", reply_markup=_kb_slot())
        return
    if game_id == "rps":
        gid = _short_id()
        bot.send_message(message.chat.id, "✂️ Камень-ножницы-бумага\nВыберите ход:", reply_markup=_kb_rps(gid))
        return
    if game_id == "guess":
        gid = _short_id()
        _business_runtime["games_guess"][gid] = random.randint(1, 10)
        bot.send_message(message.chat.id, "🔢 Угадай число от 1 до 10", reply_markup=_kb_guess(gid))
        return
    if game_id == "g2048":
        gid = _short_id()
        b = [[0] * 4 for _ in range(4)]
        b = _spawn_2048(b)
        b = _spawn_2048(b)
        _business_runtime["games_2048"][gid] = b
        bot.send_message(message.chat.id, _render_2048(b), reply_markup=_kb_2048(gid))
        return
    if game_id == "tetris":
        gid = _short_id()
        st = _new_tetris_state()
        _business_runtime["games_tetris"][gid] = st
        bot.send_message(message.chat.id, _render_tetris(st), reply_markup=_kb_tetris(gid, over=st.get("over", False)))
        return


def register_business_handlers(
    bot,
    *,
    required_channel=None,
    is_user_subscribed=None,
    strict_business_only=False,
):
    def _allowed(uid):
        if not required_channel:
            return True
        if not callable(is_user_subscribed):
            return True
        try:
            return bool(is_user_subscribed(uid))
        except Exception:
            return False

    def _business_text_filter(m):
        text = (getattr(m, "text", "") or "").strip()
        if not text:
            return False
        # Never intercept bot commands like /start, /connect, etc.
        if text.startswith("/"):
            return False
        # In strict mode, only business-context messages.
        if strict_business_only:
            return _is_business_message(m)
        # In fallback mode, accept business messages OR explicit game triggers.
        ok, _ = is_business_game_trigger(text)
        return _is_business_message(m) or ok

    @bot.message_handler(func=_business_text_filter)
    def _business_entry(m):
        if not _allowed(m.from_user.id):
            return
        ok, game_id = is_business_game_trigger(m.text or "")
        if not ok:
            # In business mode: ignore unknown text (no AI).
            return
        start_business_game(bot, m, game_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("biz_"))
    def _business_callbacks(call):
        try:
            data = call.data
            if data == "biz_coin_flip":
                res = random.choice(["🪙 Орёл", "🪙 Решка"])
                bot.edit_message_text(
                    f"Результат: {res}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=_kb_coin(),
                )
                bot.answer_callback_query(call.id, res)
                return

            if data == "biz_slot_spin":
                symbols = ["🍒", "🍋", "🍉", "⭐", "💎", "7️⃣"]
                roll = [random.choice(symbols) for _ in range(3)]
                text = f"| {' | '.join(roll)} |"
                if roll.count("7️⃣") == 3:
                    text += "\n🎉 Джекпот!"
                elif len(set(roll)) == 1:
                    text += "\n🎉 Три одинаковых!"
                bot.edit_message_text(
                    f"🎰 Казино\n{text}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=_kb_slot(),
                )
                bot.answer_callback_query(call.id)
                return

            if data.startswith("biz_rps_"):
                _, _, gid, move = data.split("_", 3)
                bot_move = random.choice(["rock", "paper", "scissors"])
                icons = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
                if move == bot_move:
                    result = "🤝 Ничья"
                elif (move == "rock" and bot_move == "scissors") or (move == "scissors" and bot_move == "paper") or (move == "paper" and bot_move == "rock"):
                    result = "🎉 Победа"
                else:
                    result = "😢 Поражение"
                bot.edit_message_text(
                    f"✂️ КНБ\nВы: {icons[move]}\nБот: {icons[bot_move]}\n\n{result}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=_kb_rps(gid),
                )
                bot.answer_callback_query(call.id)
                return

            if data.startswith("biz_guess_"):
                _, _, gid, pick = data.split("_", 3)
                target = _business_runtime["games_guess"].get(gid)
                if target is None:
                    bot.answer_callback_query(call.id, "Игра устарела", show_alert=True)
                    return
                pick = int(pick)
                if pick == target:
                    text = f"🎉 Верно! Загаданное число: {target}"
                    _business_runtime["games_guess"].pop(gid, None)
                else:
                    hint = "меньше" if pick > target else "больше"
                    text = f"❌ Неверно. Попробуйте {hint}."
                bot.edit_message_text(
                    f"🔢 Угадай число\n{text}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=_kb_guess(gid) if gid in _business_runtime["games_guess"] else None,
                )
                bot.answer_callback_query(call.id)
                return

            if data.startswith("biz_2048_"):
                _, _, gid, direction = data.split("_", 3)
                board = _business_runtime["games_2048"].get(gid)
                if board is None:
                    bot.answer_callback_query(call.id, "Игра устарела", show_alert=True)
                    return
                nb, moved = _move_board_2048(board, direction)
                if moved:
                    nb = _spawn_2048(nb)
                _business_runtime["games_2048"][gid] = nb
                bot.edit_message_text(
                    _render_2048(nb),
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=_kb_2048(gid),
                )
                bot.answer_callback_query(call.id)
                return

            if data.startswith("biz_tetris_"):
                _, _, gid, action = data.split("_", 3)
                st = _business_runtime["games_tetris"].get(gid)
                if st is None:
                    bot.answer_callback_query(call.id, "Игра устарела", show_alert=True)
                    return
                if action == "new":
                    st = _new_tetris_state()
                    _business_runtime["games_tetris"][gid] = st
                elif action == "left":
                    _move_tetris(st, -1)
                elif action == "right":
                    _move_tetris(st, 1)
                elif action == "drop":
                    _drop_tetris(st)
                bot.edit_message_text(
                    _render_tetris(st),
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=_kb_tetris(gid, over=st.get("over", False)),
                )
                bot.answer_callback_query(call.id)
                return

            bot.answer_callback_query(call.id)
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка Business-игры", show_alert=True)
