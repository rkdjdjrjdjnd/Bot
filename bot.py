import telebot
import sqlite3
import random
import time
import threading
from datetime import datetime, timedelta
from telebot import types
from telebot import apihelper

TOKEN = "1780243305:p9fmlhBKF4ksFcRmK_7dDsPRn0W0cyeFqvk"
ADMIN_ID = 1780243305

apihelper.API_URL = "http://31.59.102.218:8081/bot{0}/{1}"

user_last_action = {}
ANTI_FLOOD_COOLDOWN = 5
user_steps = {}

def check_flood(user_id):
    if user_id == ADMIN_ID:
        return True, 0
    current_time = time.time()
    if user_id in user_last_action:
        last_action = user_last_action[user_id]
        if current_time - last_action < ANTI_FLOOD_COOLDOWN:
            return False, round(ANTI_FLOOD_COOLDOWN - (current_time - last_action), 1)
    user_last_action[user_id] = current_time
    return True, 0

bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("giveaways.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
cur.execute("CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, ban_time TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, code INTEGER UNIQUE, prize TEXT, description TEXT, creator_id INTEGER, channel TEXT, created_at TEXT, active INTEGER DEFAULT 1, end_date TEXT, winners_count INTEGER DEFAULT 1, max_participants INTEGER DEFAULT 999999)")
cur.execute("CREATE TABLE IF NOT EXISTS participants (id INTEGER PRIMARY KEY AUTOINCREMENT, giveaway_id INTEGER, user_id INTEGER, username TEXT, joined_at TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS ratings (user_id INTEGER PRIMARY KEY, username TEXT, wins INTEGER DEFAULT 0, participations INTEGER DEFAULT 0)")
cur.execute("CREATE TABLE IF NOT EXISTS channels (channel TEXT PRIMARY KEY, creator_id INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS user_stats (user_id INTEGER PRIMARY KEY, daily_giveaways INTEGER DEFAULT 0, last_reset TEXT)")

conn.commit()

def get_db():
    return sqlite3.connect("giveaways.db", check_same_thread=False)

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    cur.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
    return cur.fetchone() is not None

def is_banned(user_id):
    cur.execute("SELECT ban_time FROM blacklist WHERE user_id=?", (user_id,))
    result = cur.fetchone()
    if not result:
        return False
    try:
        ban_time = datetime.fromisoformat(result[0])
        if datetime.now() < ban_time:
            return True
        cur.execute("DELETE FROM blacklist WHERE user_id=?", (user_id,))
        conn.commit()
        return False
    except:
        return False

def get_user_limit(user_id):
    if user_id == ADMIN_ID or is_admin(user_id):
        return 999
    return 50

def generate_code():
    while True:
        code = random.randint(100000, 999999)
        cur.execute("SELECT code FROM giveaways WHERE code=?", (code,))
        if not cur.fetchone():
            return code

def create_giveaway(creator_id, prize, description="", channel="", end_date=None, winners_count=1, max_participants=999999):
    conn = get_db()
    cur = conn.cursor()
    code = generate_code()
    end_date_str = end_date.isoformat() if end_date else None
    cur.execute("INSERT INTO giveaways (code, prize, description, creator_id, channel, created_at, end_date, winners_count, max_participants) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (code, prize, description, creator_id, channel, datetime.now().isoformat(), end_date_str, winners_count, max_participants))
    conn.commit()
    g_id = cur.lastrowid
    conn.close()
    return g_id, code

def get_giveaway_by_code(code):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, code, prize, description, creator_id, channel, created_at, active, end_date, winners_count, max_participants FROM giveaways WHERE code=? AND active=1", (code,))
    result = cur.fetchone()
    conn.close()
    return result

def get_giveaway_info(g_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, code, prize, description, creator_id, channel, created_at, active, end_date, winners_count, max_participants FROM giveaways WHERE id=?", (g_id,))
    result = cur.fetchone()
    conn.close()
    return result

def add_participant(g_id, user_id, username):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT creator_id FROM giveaways WHERE id=?", (g_id,))
    result = cur.fetchone()
    if result and result[0] == user_id:
        conn.close()
        return False, "❌ Вы создатель этого конкурса! Не можете участвовать."
    
    cur.execute("SELECT max_participants, active FROM giveaways WHERE id=?", (g_id,))
    result = cur.fetchone()
    if result:
        max_participants, active = result
        if active == 1 and max_participants and max_participants > 0:
            cur.execute("SELECT COUNT(*) FROM participants WHERE giveaway_id=?", (g_id,))
            count = cur.fetchone()[0]
            if count >= max_participants:
                conn.close()
                return False, f"❌ Достигнут лимит участников ({max_participants})!"
    
    cur.execute("SELECT * FROM participants WHERE giveaway_id=? AND user_id=?", (g_id, user_id))
    if cur.fetchone():
        conn.close()
        return False, "⚠️ Вы уже участвуете!"
    
    cur.execute("INSERT INTO participants (giveaway_id, user_id, username, joined_at) VALUES (?, ?, ?, ?)",
                (g_id, user_id, username, datetime.now().isoformat()))
    cur.execute("INSERT OR REPLACE INTO ratings (user_id, username, participations) VALUES (?, ?, COALESCE((SELECT participations FROM ratings WHERE user_id=?), 0) + 1)",
                (user_id, username, user_id))
    conn.commit()
    conn.close()
    return True, "✅ Вы участвуете!"

def get_participants_count(g_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM participants WHERE giveaway_id=?", (g_id,))
    result = cur.fetchone()[0]
    conn.close()
    return result

def get_participants(g_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username FROM participants WHERE giveaway_id=?", (g_id,))
    result = cur.fetchall()
    conn.close()
    return result

def delete_giveaway(g_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM participants WHERE giveaway_id=?", (g_id,))
    cur.execute("DELETE FROM giveaways WHERE id=?", (g_id,))
    conn.commit()
    conn.close()
    return True

def finish_giveaway(g_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT winners_count, creator_id, prize, code FROM giveaways WHERE id=?", (g_id,))
    result = cur.fetchone()
    if not result:
        conn.close()
        return None
    
    winners_count, creator_id, prize, code = result
    
    cur.execute("SELECT user_id, username FROM participants WHERE giveaway_id=?", (g_id,))
    participants = cur.fetchall()
    
    if not participants:
        conn.close()
        return None
    
    if len(participants) < winners_count:
        winners = participants
    else:
        winners = random.sample(participants, winners_count)
    
    cur.execute("UPDATE giveaways SET active=0 WHERE id=?", (g_id,))
    
    winner_ids = []
    for winner in winners:
        cur.execute("INSERT OR REPLACE INTO ratings (user_id, username, wins) VALUES (?, ?, COALESCE((SELECT wins FROM ratings WHERE user_id=?), 0) + 1)",
                    (winner[0], winner[1], winner[0]))
        winner_ids.append(winner[0])
    
    conn.commit()
    conn.close()
    
    try:
        winner_text = "\n".join([f"• @{w[1] or w[0]}" for w in winners])
        
        bot.send_message(
            creator_id,
            f"🏆 **ВАШ КОНКУРС ЗАВЕРШЁН!**\n\n"
            f"🎁 Приз: {prize}\n"
            f"🔑 Код: {code}\n\n"
            f"🎉 **Победители:**\n{winner_text}"
        )
        
        for user_id, username in participants:
            if user_id in winner_ids:
                bot.send_message(
                    user_id,
                    f"🎉 **ВЫ ПОБЕДИЛИ В КОНКУРСЕ!**\n\n"
                    f"🎁 Приз: {prize}\n"
                    f"🔑 Код: {code}\n\n"
                    f"🏆 Поздравляем!"
                )
            else:
                bot.send_message(
                    user_id,
                    f"😔 **КОНКУРС ЗАВЕРШЁН**\n\n"
                    f"🎁 Приз: {prize}\n"
                    f"🔑 Код: {code}\n\n"
                    f"🏆 Победители:\n{winner_text}\n\n"
                    f"🍀 Удачи в следующий раз!"
                )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомлений: {e}")
    
    delete_giveaway(g_id)
    return winners

def get_time_remaining(end_date_str):
    if not end_date_str:
        return None
    try:
        end_dt = datetime.fromisoformat(end_date_str)
        remaining = end_dt - datetime.now()
        if remaining.total_seconds() <= 0:
            return "⏳ Окончание: скоро!"
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"⏳ Окончание: через {hours}ч {minutes}м"
        else:
            return f"⏳ Окончание: через {minutes}м {seconds}с"
    except:
        return None

def format_giveaway(g_id, code):
    info = get_giveaway_info(g_id)
    if not info:
        return None
    
    g_id, code, prize, description, creator_id, channel, created_at, active, end_date, winners_count, max_participants = info
    count = get_participants_count(g_id)
    
    text = f"🎁 **РОЗЫГРЫШ** 🎁\n\n"
    text += f"🔑 **Код входа:** `{code}`\n"
    text += f"🏆 **Приз:** {prize}\n"
    if description:
        text += f"📝 **Описание:** {description}\n"
    if channel:
        text += f"📢 **Канал:** {channel}\n"
    
    if active == 1:
        if end_date:
            time_str = get_time_remaining(end_date)
            if time_str:
                text += f"{time_str}\n"
        text += f"🏅 **Победителей:** {winners_count}\n"
        text += f"👥 **Участников:** {count}\n"
    else:
        text += f"✅ **Завершён!**\n"
    
    return text

def get_giveaway_keyboard(g_id, in_channel=False, user_id=None):
    info = get_giveaway_info(g_id)
    if not info:
        return None
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    if info[7] != 1:
        return keyboard
    
    count = get_participants_count(g_id)
    
    if user_id and info[4] != user_id:
        keyboard.add(
            types.InlineKeyboardButton(
                f"✅ УЧАСТВОВАТЬ [{count}]",
                callback_data=f"join_{g_id}"
            )
        )
    
    if user_id and info[4] == user_id:
        keyboard.row(
            types.InlineKeyboardButton("🏆 Завершить", callback_data=f"finish_{g_id}"),
            types.InlineKeyboardButton("📊 Участники", callback_data=f"members_{g_id}")
        )
        keyboard.add(types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{g_id}"))
    
    return keyboard

def auto_post_to_channel(channel, g_id, code):
    text = format_giveaway(g_id, code)
    if not text:
        return False
    keyboard = get_giveaway_keyboard(g_id, in_channel=True)
    try:
        bot.send_message(channel, text, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=False)
        return True
    except:
        return False

def check_daily_limit(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT daily_giveaways, last_reset FROM user_stats WHERE user_id=?", (user_id,))
    result = cur.fetchone()
    today = datetime.now().date().isoformat()
    if not result:
        cur.execute("INSERT INTO user_stats (user_id, daily_giveaways, last_reset) VALUES (?, 0, ?)",
                    (user_id, today))
        conn.commit()
        conn.close()
        max_limit = get_user_limit(user_id)
        return True, 0, max_limit
    daily_giveaways, last_reset = result
    if last_reset != today:
        cur.execute("UPDATE user_stats SET daily_giveaways=0, last_reset=? WHERE user_id=?",
                    (today, user_id))
        conn.commit()
        daily_giveaways = 0
    conn.close()
    max_limit = get_user_limit(user_id)
    remaining = max_limit - daily_giveaways
    if daily_giveaways >= max_limit:
        return False, daily_giveaways, remaining
    return True, daily_giveaways, remaining

def increment_giveaway_count(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE user_stats SET daily_giveaways = daily_giveaways + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def add_channel(channel, creator_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO channels (channel, creator_id) VALUES (?, ?)", (channel, creator_id))
    conn.commit()
    conn.close()

def remove_channel(channel, creator_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE channel=? AND creator_id=?", (channel, creator_id))
    conn.commit()
    conn.close()

def get_my_channels(creator_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT channel FROM channels WHERE creator_id=?", (creator_id,))
    result = cur.fetchall()
    conn.close()
    return [row[0] for row in result]

def channel_exists(channel, creator_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT channel FROM channels WHERE channel=? AND creator_id=?", (channel, creator_id))
    result = cur.fetchone()
    conn.close()
    return result is not None

def main_menu(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("🎁 Создать розыгрыш", callback_data="create_giveaway"),
        types.InlineKeyboardButton("🔑 Войти по коду", callback_data="enter_code"),
        types.InlineKeyboardButton("📢 Мои каналы", callback_data="my_channels"),
        types.InlineKeyboardButton("🏆 Топ участников", callback_data="top_rating"),
        types.InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return keyboard
  @bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id

    allowed, wait_time = check_flood(user_id)
    if not allowed:
        bot.reply_to(message, f"⏳ Подождите {wait_time} сек!")
        return

    if is_banned(user_id):
        bot.reply_to(message, "🚫 Вы заблокированы!")
        return

    first_name = message.from_user.first_name or "Гость"

    welcome_text = (
        f"🏆 **ДОБРО ПОЖАЛОВАТЬ!**\n\n"
        f"✨ Привет, **{first_name}**!\n\n"
        f"⬇️ **Выберите действие:**"
    )
    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    data = call.data
    
    if is_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 Вы заблокированы!", show_alert=True)
        return

    if data == "back_main":
        start(call.message)
        return

    if data == "create_giveaway":
        user_steps[user_id] = {"step": "prize"}
        bot.send_message(call.message.chat.id, "🎁 Введите **приз** для розыгрыша:")
        bot.answer_callback_query(call.id)
        return

    if data == "enter_code":
        bot.send_message(call.message.chat.id, "🔑 Введите **код** конкурса (6 цифр):")
        user_steps[user_id] = {"step": "enter_code"}
        bot.answer_callback_query(call.id)
        return

    if data == "my_channels":
        channels = get_my_channels(user_id)
        if not channels:
            text = "📭 У вас нет добавленных каналов\n\nДобавьте канал командой:\n/addchannel @канал"
            bot.send_message(call.message.chat.id, text)
        else:
            text = "📢 **Мои каналы:**\n\n"
            for ch in channels:
                text += f"• {ch}\n"
            text += "\n\nУдалить канал:\n/delchannel @канал"
            bot.send_message(call.message.chat.id, text)
        bot.answer_callback_query(call.id)
        return

    if data == "top_rating":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT username, wins FROM ratings ORDER BY wins DESC LIMIT 10")
        result = cur.fetchall()
        conn.close()
        if not result:
            bot.send_message(call.message.chat.id, "📊 Топ пуст")
        else:
            text = "🏆 **ТОП УЧАСТНИКОВ**\n\n"
            for i, (username, wins) in enumerate(result, 1):
                if wins > 0:
                    text += f"{i}. {username or 'Аноним'} — 🏅{wins}\n"
            bot.send_message(call.message.chat.id, text)
        bot.answer_callback_query(call.id)
        return

    if data == "help":
        text = (
            "❓ **Помощь:**\n\n"
            "🎁 /start — Главное меню\n"
            "🎁 Создать розыгрыш — Создать новый конкурс\n"
            "🔑 Войти по коду — Посмотреть конкурс по коду\n"
            "📢 Мои каналы — Список ваших каналов\n"
            "🏆 Топ участников — Рейтинг победителей\n\n"
            "📌 <b>Как создать розыгрыш:</b>\n"
            "1. Нажмите «Создать розыгрыш»\n"
            "2. Введите приз\n"
            "3. Введите описание\n"
            "4. Укажите канал (или пропустите)\n"
            "5. Укажите дату окончания (или пропустите)\n"
            "6. Выберите количество победителей (1-10)\n\n"
            "✅ Готово! Вы получите КОД для участников!\n\n"
            "📌 <b>Участники вводят код в меню «Войти по коду»</b>\n"
            "📌 <b>Создатель НЕ может участвовать в своём конкурсе!</b>\n"
            "📌 <b>После завершения конкурса - все получают уведомления!</b>"
        )
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return

    if data.startswith("join_"):
        g_id = int(data.split("_")[1])
        success, msg = add_participant(g_id, user_id, call.from_user.username or call.from_user.first_name)
        bot.answer_callback_query(call.id, msg, show_alert=True)
        if success:
            info = get_giveaway_info(g_id)
            code = info[1] if info else 0
            text = format_giveaway(g_id, code)
            keyboard = get_giveaway_keyboard(g_id, user_id=user_id)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=False)
        return

    if data.startswith("members_"):
        g_id = int(data.split("_")[1])
        info = get_giveaway_info(g_id)
        if not info or info[4] != user_id:
            bot.answer_callback_query(call.id, "⛔ Только создатель!", show_alert=True)
            return
        participants = get_participants(g_id)
        if not participants:
            bot.answer_callback_query(call.id, "👥 Нет участников", show_alert=True)
            return
        text = f"📊 **Участники ({len(participants)}):**\n\n"
        for i, (uid, username) in enumerate(participants, 1):
            name = f"@{username}" if username else str(uid)
            text += f"{i}. {name}\n"
        bot.send_message(call.message.chat.id, text)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("finish_"):
        g_id = int(data.split("_")[1])
        info = get_giveaway_info(g_id)
        if not info or info[4] != user_id:
            bot.answer_callback_query(call.id, "⛔ Только создатель!", show_alert=True)
            return
        winners = finish_giveaway(g_id)
        if not winners:
            bot.answer_callback_query(call.id, "❌ Нет участников!", show_alert=True)
            return
        bot.answer_callback_query(call.id, "✅ Конкурс завершён! Все участники уведомлены.")
        return

    if data.startswith("cancel_"):
        g_id = int(data.split("_")[1])
        info = get_giveaway_info(g_id)
        if not info or info[4] != user_id:
            bot.answer_callback_query(call.id, "⛔ Только создатель!", show_alert=True)
            return
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE giveaways SET active=0 WHERE id=?", (g_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text(f"❌ Розыгрыш отменён", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

@bot.message_handler(commands=['addchannel'])
def add_channel_command(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) < 2:
        bot.reply_to(message, "❌ Использование: /addchannel @канал")
        return
    
    channel = args[1]
    if not channel.startswith('@'):
        channel = '@' + channel
    
    try:
        chat = bot.get_chat(channel)
        if chat.type not in ["channel", "supergroup"]:
            bot.reply_to(message, "❌ Это не канал!")
            return
    except:
        bot.reply_to(message, "❌ Канал не найден! Убедитесь что бот админ канала.")
        return
    
    add_channel(channel, user_id)
    bot.reply_to(message, f"✅ Канал {channel} добавлен!")

@bot.message_handler(commands=['delchannel'])
def del_channel_command(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) < 2:
        bot.reply_to(message, "❌ Использование: /delchannel @канал")
        return
    
    channel = args[1]
    if not channel.startswith('@'):
        channel = '@' + channel
    
    if not channel_exists(channel, user_id):
        bot.reply_to(message, "❌ Канал не найден в вашем списке!")
        return
    
    remove_channel(channel, user_id)
    bot.reply_to(message, f"✅ Канал {channel} удалён!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if is_banned(user_id):
        bot.reply_to(message, "🚫 Вы заблокированы!")
        return

    if user_id not in user_steps:
        return
    
    step = user_steps[user_id]
    text = message.text.strip()
    
    if step.get("step") == "enter_code":
        try:
            code = int(text)
            if code < 100000 or code > 999999:
                bot.reply_to(message, "❌ Код должен быть 6-значным (100000-999999)!")
                return
            
            giveaway = get_giveaway_by_code(code)
            if not giveaway:
                bot.reply_to(message, "❌ Конкурс с таким кодом не найден или уже завершён!")
                return
            
            g_id = giveaway[0]
            info = get_giveaway_info(g_id)
            code = info[1]
            
            text_msg = format_giveaway(g_id, code)
            keyboard = get_giveaway_keyboard(g_id, user_id=user_id)
            bot.send_message(chat_id, text_msg, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=False)
            
            bot.reply_to(message, f"🔑 Вы вошли в конкурс! Нажмите «УЧАСТВОВАТЬ» чтобы присоединиться.")
            
            del user_steps[user_id]
        except ValueError:
            bot.reply_to(message, "❌ Введите число (6 цифр)!")
        return
    
    if step.get("step") == "prize":
        step["prize"] = text
        step["step"] = "description"
        bot.reply_to(message, "📝 Введите **описание** (или '-' чтобы пропустить):")
        return

    if step.get("step") == "description":
        step["description"] = text if text != "-" else ""
        step["step"] = "channel"
        channels = get_my_channels(user_id)
        if channels:
            bot.reply_to(message, f"📢 Введите @канал для публикации\n\nВаши каналы:\n" + "\n".join(channels) + "\n\nИли '-' чтобы пропустить:")
        else:
            bot.reply_to(message, "📢 У вас нет каналов. Введите '-' чтобы пропустить или /addchannel @канал")
        return

    if step.get("step") == "channel":
        if text != "-":
            channel = text if text.startswith('@') else '@' + text
            if not channel_exists(channel, user_id):
                bot.reply_to(message, f"❌ Канал {channel} не найден! Добавьте: /addchannel {channel}")
                return
            step["channel"] = channel
        else:
            step["channel"] = ""
        step["step"] = "end_date"
        bot.reply_to(message, "⏰ Введите дату окончания (ДД.ММ.ГГГГ ЧЧ:ММ) или '-' чтобы пропустить:")
        return

    if step.get("step") == "end_date":
        if text != "-":
            try:
                step["end_date"] = datetime.strptime(text, "%d.%m.%Y %H:%M")
            except:
                bot.reply_to(message, "❌ Неверный формат! Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
                return
        else:
            step["end_date"] = None
        step["step"] = "winners_count"
        bot.reply_to(message, "🏅 Сколько **победителей**? (1-10):")
        return

    if step.get("step") == "winners_count":
        try:
            winners_count = int(text)
            if winners_count < 1 or winners_count > 10:
                bot.reply_to(message, "❌ Введите число от 1 до 10!")
                return
            step["winners_count"] = winners_count
            
            can_create, used, remaining = check_daily_limit(user_id)
            if not can_create:
                bot.reply_to(message, f"❌ Лимит ({used+remaining}) исчерпан!")
                del user_steps[user_id]
                return
            
            g_id, code = create_giveaway(
                user_id,
                step["prize"],
                step.get("description", ""),
                step.get("channel", ""),
                step.get("end_date"),
                step["winners_count"],
                999999
            )
            increment_giveaway_count(user_id)
            
            text_msg = format_giveaway(g_id, code)
            keyboard = get_giveaway_keyboard(g_id, user_id=user_id)
            bot.send_message(chat_id, text_msg, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=False)
            
            channels = get_my_channels(user_id)
            sent = 0
            for ch in channels:
                if auto_post_to_channel(ch, g_id, code):
                    sent += 1
            
            if sent > 0:
                bot.send_message(chat_id, f"✅ Розыгрыш отправлен в {sent} каналов!")
            
            bot.send_message(
                chat_id,
                f"🔑 <b>Код для участников:</b>\n<code>{code}</code>\n\n"
                f"📋 Отправьте этот код участникам!\n\n"
                f"📌 Участники вводят код в меню «Войти по коду»\n"
                f"📌 Создатель НЕ может участвовать в своём конкурсе!\n"
                f"📌 После завершения все получат уведомления!",
                parse_mode="HTML"
            )
            
            del user_steps[user_id]
            
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {e}")
            del user_steps[user_id]

if __name__ == "__main__":
    print("🚀 БОТ ЗАПУЩЕН!")
    print(f"👑 Админ: {ADMIN_ID}")
    bot.polling(none_stop=True)
