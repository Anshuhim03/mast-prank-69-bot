import os
import json
import time
import random
import requests
from datetime import datetime, date
from typing import Dict, Any

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============================================
# CONFIG
# ============================================

BOT_NAME = "Mast Prank 69"
BOT_USERNAME = "@Faydauthaobot"

TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN missing! Add it in Replit Secrets.")

# Admin
DEFAULT_ADMIN_IDS = ["1631555366"]
ADMIN_IDS_ENV = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = (
    [x.strip() for x in ADMIN_IDS_ENV.split(",") if x.strip().isdigit()]
    if ADMIN_IDS_ENV
    else DEFAULT_ADMIN_IDS
)

# Storage files (Replit)
USERS_FILE = "users.json"
STATS_FILE = "stats.json"
SETTINGS_FILE = "settings.json"

REQUEST_TIMEOUT = 10

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ============================================
# JSON UTILITIES
# ============================================

def safe_load_json(path: str, default: Any) -> Any:
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def safe_save_json(path: str, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_settings() -> Dict[str, Any]:
    default = {"maintenance": False}
    s = safe_load_json(SETTINGS_FILE, default)
    s.setdefault("maintenance", False)
    return s

def save_settings(s: Dict[str, Any]) -> None:
    safe_save_json(SETTINGS_FILE, s)

def get_users() -> Dict[str, Any]:
    return safe_load_json(USERS_FILE, {})

def save_users(users: Dict[str, Any]) -> None:
    safe_save_json(USERS_FILE, users)

def get_stats() -> Dict[str, Any]:
    default = {
        "started_at": int(time.time()),
        "total_messages": 0,
        "commands": {
            "start": 0,
            "quote": 0,
            "joke": 0,
            "fact": 0,
            "daily": 0,
            "help": 0,
            "ping": 0,
        }
    }
    st = safe_load_json(STATS_FILE, default)
    st.setdefault("started_at", int(time.time()))
    st.setdefault("total_messages", 0)
    st.setdefault("commands", default["commands"])
    for k in default["commands"]:
        st["commands"].setdefault(k, 0)
    return st

def save_stats(st: Dict[str, Any]) -> None:
    safe_save_json(STATS_FILE, st)

# ============================================
# HELPERS
# ============================================

def is_admin(user_id: int) -> bool:
    return str(user_id) in ADMIN_IDS

def track_user(message) -> None:
    try:
        users = get_users()
        uid = str(message.from_user.id)
        if uid not in users:
            users[uid] = {
                "user_id": message.from_user.id,
                "first_name": message.from_user.first_name or "",
                "username": message.from_user.username or "",
                "joined_at": datetime.now().isoformat(timespec="seconds")
            }
            save_users(users)
    except Exception:
        pass

def inc_message_stats() -> None:
    st = get_stats()
    st["total_messages"] += 1
    save_stats(st)

def inc_command(cmd: str) -> None:
    st = get_stats()
    st["commands"][cmd] = st["commands"].get(cmd, 0) + 1
    save_stats(st)

def gatekeep(message) -> bool:
    settings = get_settings()
    if settings.get("maintenance") and not is_admin(message.from_user.id):
        bot.reply_to(message, "🛠 Bot is under maintenance. Please try later.")
        return False
    return True

# ============================================
# API FUNCTIONS (FREE)
# ============================================

def api_get_json(url: str) -> Any:
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()

def get_quote() -> str:
    data = api_get_json("https://api.quotable.io/quotes/random")
    q = data[0].get("content", "No quote found.")
    a = data[0].get("author", "Unknown")
    return f'💡 <b>Quote</b>\n\n“{q}”\n— <i>{a}</i>'

def get_joke() -> str:
    data = api_get_json("https://v2.jokeapi.dev/joke/Any?safe-mode&type=single,twopart&lang=en")
    if data.get("error"):
        return "⚠️ Joke API error. Try again."

    if data.get("type") == "single":
        return f"😂 <b>Joke</b>\n\n{data.get('joke', 'No joke found.')}"

    return (
        "😂 <b>Joke</b>\n\n"
        f"{data.get('setup', '...')}\n\n<b>{data.get('delivery', '...')}</b>"
    )

def get_fact() -> str:
    data = api_get_json("https://uselessfacts.jsph.pl/api/v2/facts/random?language=en")
    return f"🧠 <b>Fact</b>\n\n{data.get('text', 'No fact found.')}"

def get_daily_pack() -> str:
    seed = int(date.today().strftime("%Y%m%d"))
    random.seed(seed)
    lines = [
        "आज कमाओ, कल नहीं।",
        "Consistency beats talent.",
        "Do it scared.",
        "Action creates confidence.",
        "Small steps daily = big results.",
        "Discipline is freedom.",
    ]
    picked = random.choice(lines)
    return (
        f"⭐ <b>Daily Pack</b> ({date.today().strftime('%d-%m-%Y')})\n\n"
        f"✅ <i>{picked}</i>\n\n"
        "Try: /quote /joke /fact"
    )

# ============================================
# BUTTON MENUS
# ============================================

def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("💡 Quote", callback_data="get_quote"),
        InlineKeyboardButton("😂 Joke", callback_data="get_joke"),
    )
    kb.add(
        InlineKeyboardButton("🧠 Fact", callback_data="get_fact"),
        InlineKeyboardButton("⭐ Daily", callback_data="get_daily"),
    )
    kb.add(InlineKeyboardButton("ℹ️ Help", callback_data="get_help"))
    return kb

def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
        InlineKeyboardButton("📢 Broadcast Help", callback_data="admin_broadcast_help"),
    )
    kb.add(InlineKeyboardButton("🛠 Toggle Maintenance", callback_data="admin_maintenance"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_home"))
    return kb

# ============================================
# USER COMMANDS
# ============================================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    track_user(message)
    inc_message_stats()
    inc_command("start")
    if not gatekeep(message):
        return

    name = message.from_user.first_name or "Friend"
    text = (
        f"👋 Hello <b>{name}</b>\n\n"
        f"Welcome to <b>{BOT_NAME}</b> ({BOT_USERNAME})\n\n"
        "Commands:\n"
        "• /quote\n• /joke\n• /fact\n• /daily\n• /help\n"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb())

@bot.message_handler(commands=["help"])
def cmd_help(message):
    track_user(message)
    inc_message_stats()
    inc_command("help")
    if not gatekeep(message):
        return
    bot.reply_to(
        message,
        "ℹ️ <b>Help</b>\n\n"
        "Commands:\n"
        "/quote /joke /fact /daily /ping\n\n"
        "Admin:\n/admin",
        reply_markup=main_menu_kb()
    )

@bot.message_handler(commands=["ping"])
def cmd_ping(message):
    track_user(message)
    inc_message_stats()
    inc_command("ping")
    if not gatekeep(message):
        return
    bot.reply_to(message, "✅ Pong! Bot is alive.")

@bot.message_handler(commands=["quote"])
def cmd_quote(message):
    track_user(message)
    inc_message_stats()
    inc_command("quote")
    if not gatekeep(message):
        return
    try:
        bot.send_message(message.chat.id, get_quote(), reply_markup=main_menu_kb())
    except Exception:
        bot.send_message(message.chat.id, "⚠️ Quote fetch failed. Try again.")

@bot.message_handler(commands=["joke"])
def cmd_joke(message):
    track_user(message)
    inc_message_stats()
    inc_command("joke")
    if not gatekeep(message):
        return
    try:
        bot.send_message(message.chat.id, get_joke(), reply_markup=main_menu_kb())
    except Exception:
        bot.send_message(message.chat.id, "⚠️ Joke fetch failed. Try again.")

@bot.message_handler(commands=["fact"])
def cmd_fact(message):
    track_user(message)
    inc_message_stats()
    inc_command("fact")
    if not gatekeep(message):
        return
    try:
        bot.send_message(message.chat.id, get_fact(), reply_markup=main_menu_kb())
    except Exception:
        bot.send_message(message.chat.id, "⚠️ Fact fetch failed. Try again.")

@bot.message_handler(commands=["daily"])
def cmd_daily(message):
    track_user(message)
    inc_message_stats()
    inc_command("daily")
    if not gatekeep(message):
        return
    bot.send_message(message.chat.id, get_daily_pack(), reply_markup=main_menu_kb())

# ============================================
# ADMIN COMMANDS
# ============================================

@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    track_user(message)
    inc_message_stats()
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access denied.")
        return

    s = get_settings()
    txt = (
        "🛡 <b>Admin Panel</b>\n\n"
        f"Maintenance: <b>{'ON' if s.get('maintenance') else 'OFF'}</b>\n\n"
        "Choose:"
    )
    bot.send_message(message.chat.id, txt, reply_markup=admin_menu_kb())

@bot.message_handler(commands=["stats"])
def cmd_stats(message):
    track_user(message)
    inc_message_stats()
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access denied.")
        return

    users = get_users()
    st = get_stats()
    up = int(time.time()) - int(st.get("started_at", int(time.time())))
    up_h = up // 3600
    up_m = (up % 3600) // 60

    cmds = st.get("commands", {})
    txt = (
        "📊 <b>Bot Stats</b>\n\n"
        f"👥 Users: <b>{len(users)}</b>\n"
        f"💬 Messages: <b>{st.get('total_messages', 0)}</b>\n"
        f"⏳ Uptime: <b>{up_h}h {up_m}m</b>\n\n"
        "Commands:\n"
        f"/start: {cmds.get('start', 0)}\n"
        f"/quote: {cmds.get('quote', 0)}\n"
        f"/joke: {cmds.get('joke', 0)}\n"
        f"/fact: {cmds.get('fact', 0)}\n"
        f"/daily: {cmds.get('daily', 0)}\n"
        f"/help: {cmds.get('help', 0)}\n"
        f"/ping: {cmds.get('ping', 0)}\n"
    )
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    track_user(message)
    inc_message_stats()

    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access denied.")
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(message, "Usage:\n<code>/broadcast Your message</code>")
        return

    msg = parts[1].strip()
    users = get_users()

    ok, fail = 0, 0
    bot.reply_to(message, f"📢 Sending to <b>{len(users)}</b> users...")

    for uid in list(users.keys()):
        try:
            bot.send_message(int(uid), f"📢 <b>Message</b>\n\n{msg}")
            ok += 1
        except Exception:
            fail += 1

    bot.send_message(message.chat.id, f"✅ Done!\nSent: <b>{ok}</b>\nFailed: <b>{fail}</b>")

@bot.message_handler(commands=["maintenance"])
def cmd_maintenance(message):
    track_user(message)
    inc_message_stats()

    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access denied.")
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: <code>/maintenance on</code> or <code>/maintenance off</code>")
        return

    val = parts[1].strip().lower()
    s = get_settings()

    if val == "on":
        s["maintenance"] = True
    elif val == "off":
        s["maintenance"] = False
    else:
        bot.reply_to(message, "Usage: <code>/maintenance on</code> or <code>/maintenance off</code>")
        return

    save_settings(s)
    bot.reply_to(message, f"🛠 Maintenance: <b>{'ON' if s['maintenance'] else 'OFF'}</b>")

# ============================================
# CALLBACKS (BUTTONS)
# ============================================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    try:
        uid = call.from_user.id

        if call.data == "get_quote":
            bot.answer_callback_query(call.id, "Quote...")
            bot.send_message(call.message.chat.id, get_quote(), reply_markup=main_menu_kb())
            return

        if call.data == "get_joke":
            bot.answer_callback_query(call.id, "Joke...")
            bot.send_message(call.message.chat.id, get_joke(), reply_markup=main_menu_kb())
            return

        if call.data == "get_fact":
            bot.answer_callback_query(call.id, "Fact...")
            bot.send_message(call.message.chat.id, get_fact(), reply_markup=main_menu_kb())
            return

        if call.data == "get_daily":
            bot.answer_callback_query(call.id, "Daily...")
            bot.send_message(call.message.chat.id, get_daily_pack(), reply_markup=main_menu_kb())
            return

        if call.data == "get_help":
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                "ℹ️ Use menu / commands:\n/quote /joke /fact /daily /ping\n\nAdmin: /admin",
                reply_markup=main_menu_kb()
            )
            return

        if call.data == "back_home":
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "🏠 Main Menu", reply_markup=main_menu_kb())
            return

        # admin callbacks
        if call.data.startswith("admin_"):
            if not is_admin(uid):
                bot.answer_callback_query(call.id, "Access denied.")
                return

            if call.data == "admin_stats":
                bot.answer_callback_query(call.id)
                users = get_users()
                st = get_stats()
                up = int(time.time()) - int(st.get("started_at", int(time.time())))
                bot.send_message(call.message.chat.id, f"📊 Users: <b>{len(users)}</b>\n⏳ Uptime: <b>{up//3600}h</b>")
                return

            if call.data == "admin_broadcast_help":
                bot.answer_callback_query(call.id)
                bot.send_message(call.message.chat.id, "📢 Use:\n<code>/broadcast your message</code>")
                return

            if call.data == "admin_maintenance":
                bot.answer_callback_query(call.id)
                s = get_settings()
                s["maintenance"] = not s.get("maintenance", False)
                save_settings(s)
                bot.send_message(call.message.chat.id, f"🛠 Maintenance: <b>{'ON' if s['maintenance'] else 'OFF'}</b>")
                return

    except Exception:
        try:
            bot.answer_callback_query(call.id, "⚠️ Error")
        except Exception:
            pass

# ============================================
# FALLBACK
# ============================================

@bot.message_handler(func=lambda m: True)
def fallback(message):
    track_user(message)
    inc_message_stats()
    if not gatekeep(message):
        return
    bot.reply_to(message, "Use /start ✅", reply_markup=main_menu_kb())

# ============================================
# RUN SAFE LOOP
# ============================================

def run_forever():
    while True:
        try:
            print("✅ Bot started polling...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("❌ Polling crashed:", e)
            time.sleep(5)
