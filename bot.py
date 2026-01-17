import os
import json
import time
import random
import requests
from datetime import datetime, date
from typing import Dict, Any, List

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# CONFIG
# =========================

BOT_NAME = "Mast Prank 69"
BOT_USERNAME = "@Faydauthaobot"

# Admin IDs (comma-separated in env optional)
DEFAULT_ADMIN_IDS = ["1631555366"]

TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN missing! Set it as environment variable.")

ADMIN_IDS_ENV = os.getenv("ADMIN_IDS", "").strip()
if ADMIN_IDS_ENV:
    ADMIN_IDS = [x.strip() for x in ADMIN_IDS_ENV.split(",") if x.strip().isdigit()]
else:
    ADMIN_IDS = DEFAULT_ADMIN_IDS

# Channel for force join (optional)
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL", "").strip()  # e.g. @yourchannel
# Control flags
DATA_DIR = os.getenv("DATA_DIR", ".").strip()  # Koyeb FS is ephemeral; still ok for demo

USERS_FILE = os.path.join(DATA_DIR, "users.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

REQUEST_TIMEOUT = 10

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")


# =========================
# UTIL: JSON STORE
# =========================

def _safe_load_json(path: str, default: Any) -> Any:
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _safe_save_json(path: str, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # If write fails on some env, we won't crash bot.
        pass


def get_settings() -> Dict[str, Any]:
    default = {
        "maintenance": False,
        "forcejoin": False,
        "channel": FORCE_JOIN_CHANNEL or ""
    }
    settings = _safe_load_json(SETTINGS_FILE, default)
    # Ensure keys exist
    for k, v in default.items():
        settings.setdefault(k, v)
    return settings


def save_settings(settings: Dict[str, Any]) -> None:
    _safe_save_json(SETTINGS_FILE, settings)


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
            "ping": 0
        }
    }
    stats = _safe_load_json(STATS_FILE, default)
    stats.setdefault("started_at", int(time.time()))
    stats.setdefault("total_messages", 0)
    stats.setdefault("commands", default["commands"])
    for cmd in default["commands"].keys():
        stats["commands"].setdefault(cmd, 0)
    return stats


def save_stats(stats: Dict[str, Any]) -> None:
    _safe_save_json(STATS_FILE, stats)


def get_users() -> Dict[str, Any]:
    # key = user_id str
    default = {}
    return _safe_load_json(USERS_FILE, default)


def save_users(users: Dict[str, Any]) -> None:
    _safe_save_json(USERS_FILE, users)


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
    stats = get_stats()
    stats["total_messages"] += 1
    save_stats(stats)


def inc_command(cmd: str) -> None:
    stats = get_stats()
    stats["commands"].setdefault(cmd, 0)
    stats["commands"][cmd] += 1
    save_stats(stats)


def is_admin(user_id: int) -> bool:
    return str(user_id) in ADMIN_IDS


# =========================
# FORCE JOIN CHECK
# =========================

def must_force_join() -> bool:
    settings = get_settings()
    return bool(settings.get("forcejoin"))


def get_force_channel() -> str:
    settings = get_settings()
    return (settings.get("channel") or "").strip()


def check_user_joined_channel(user_id: int, channel: str) -> bool:
    """
    Requires bot to be admin in the channel for reliable status.
    """
    try:
        member = bot.get_chat_member(channel, user_id)
        # statuses: creator, administrator, member, restricted, left, kicked
        return member.status in ("creator", "administrator", "member")
    except Exception:
        # If can't verify, fail-open to avoid blocking users due to permissions
        return True


def join_gate_message(channel: str) -> str:
    return (
        "🔒 <b>Access Locked</b>\n\n"
        "Use this bot only after joining our channel.\n"
        f"👉 Join: {channel}\n\n"
        "Then come back and press /start again."
    )


def join_gate_keyboard(channel: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{channel.replace('@', '')}"))
    kb.add(InlineKeyboardButton("🔄 I Joined, Continue", callback_data="joined_continue"))
    return kb


def gatekeep(message) -> bool:
    """
    Returns True if user is allowed to proceed.
    """
    settings = get_settings()

    # Maintenance blocks all except admin
    if settings.get("maintenance") and not is_admin(message.from_user.id):
        bot.reply_to(message, "🛠 Bot is under maintenance. Please try again later.")
        return False

    # Force-join blocks
    if must_force_join() and not is_admin(message.from_user.id):
        channel = get_force_channel()
        if channel:
            ok = check_user_joined_channel(message.from_user.id, channel)
            if not ok:
                bot.send_message(message.chat.id, join_gate_message(channel), reply_markup=join_gate_keyboard(channel))
                return False

    return True


# =========================
# API FUNCTIONS
# =========================

def api_get_json(url: str) -> Any:
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_quote() -> str:
    # Quotable random quote
    data = api_get_json("https://api.quotable.io/quotes/random")
    q = data[0].get("content", "No quote found.")
    a = data[0].get("author", "Unknown")
    return f'💡 <b>Quote</b>\n\n“{q}”\n— <i>{a}</i>'


def get_joke() -> str:
    # JokeAPI safe-mode, english
    # Returns either single joke or setup+delivery
    url = "https://v2.jokeapi.dev/joke/Any?safe-mode&type=single,twopart&lang=en"
    data = api_get_json(url)

    if data.get("error"):
        return "⚠️ Joke API error. Try again."

    if data.get("type") == "single":
        joke = data.get("joke", "No joke found.")
        return f"😂 <b>Joke</b>\n\n{joke}"

    setup = data.get("setup", "Setup missing.")
    delivery = data.get("delivery", "Delivery missing.")
    return f"😂 <b>Joke</b>\n\n{setup}\n\n<b>{delivery}</b>"


def get_fact() -> str:
    # uselessfacts API
    data = api_get_json("https://uselessfacts.jsph.pl/api/v2/facts/random?language=en")
    fact = data.get("text", "No fact found.")
    return f"🧠 <b>Fact</b>\n\n{fact}"


def get_daily_pack() -> str:
    """
    Deterministic daily content based on date.
    Not calling APIs repeatedly for daily -> stable.
    """
    seed = int(date.today().strftime("%Y%m%d"))
    random.seed(seed)

    daily_lines = [
        "आज कमाओ, कल नहीं।",
        "Consistency beats talent.",
        "Do it scared.",
        "Action creates confidence.",
        "Small steps daily = big results.",
        "Discipline is freedom."
    ]

    picked = random.choice(daily_lines)
    return (
        f"⭐ <b>Daily Pack</b> ({date.today().strftime('%d-%m-%Y')})\n\n"
        f"✅ <i>{picked}</i>\n\n"
        "Use /quote /joke /fact for more."
    )


# =========================
# KEYBOARDS
# =========================

def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("💡 Quote", callback_data="get_quote"),
        InlineKeyboardButton("😂 Joke", callback_data="get_joke")
    )
    kb.add(
        InlineKeyboardButton("🧠 Fact", callback_data="get_fact"),
        InlineKeyboardButton("⭐ Daily", callback_data="get_daily")
    )
    kb.add(InlineKeyboardButton("ℹ️ Help", callback_data="get_help"))
    return kb


def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
        InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_help")
    )
    kb.add(
        InlineKeyboardButton("🛠 Maintenance", callback_data="admin_maintenance"),
        InlineKeyboardButton("🔒 Force-Join", callback_data="admin_forcejoin")
    )
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_home"))
    return kb


# =========================
# COMMAND HANDLERS
# =========================

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
        "Use the menu below or commands:\n"
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

    txt = (
        "ℹ️ <b>Help</b>\n\n"
        "Commands:\n"
        "• /start - Open menu\n"
        "• /quote - Random quote\n"
        "• /joke - Random joke\n"
        "• /fact - Random fact\n"
        "• /daily - Daily pack\n"
        "• /ping - Bot status\n\n"
        "Admin:\n"
        "• /admin - Admin panel"
    )
    bot.reply_to(message, txt, reply_markup=main_menu_kb())


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


# =========================
# ADMIN COMMANDS
# =========================

@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    track_user(message)
    inc_message_stats()
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access denied.")
        return

    settings = get_settings()
    channel = settings.get("channel") or "Not set"
    txt = (
        "🛡 <b>Admin Panel</b>\n\n"
        f"• Maintenance: <b>{'ON' if settings.get('maintenance') else 'OFF'}</b>\n"
        f"• Force-Join: <b>{'ON' if settings.get('forcejoin') else 'OFF'}</b>\n"
        f"• Channel: <b>{channel}</b>\n\n"
        "Choose an option:"
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
    stats = get_stats()
    up = int(time.time()) - int(stats.get("started_at", int(time.time())))
    up_h = up // 3600
    up_m = (up % 3600) // 60

    cmds = stats.get("commands", {})
    txt = (
        "📊 <b>Bot Stats</b>\n\n"
        f"👥 Users: <b>{len(users)}</b>\n"
        f"💬 Total messages: <b>{stats.get('total_messages', 0)}</b>\n"
        f"⏳ Uptime: <b>{up_h}h {up_m}m</b>\n\n"
        "Commands:\n"
        f"• /start: {cmds.get('start', 0)}\n"
        f"• /quote: {cmds.get('quote', 0)}\n"
        f"• /joke: {cmds.get('joke', 0)}\n"
        f"• /fact: {cmds.get('fact', 0)}\n"
        f"• /daily: {cmds.get('daily', 0)}\n"
        f"• /help: {cmds.get('help', 0)}\n"
        f"• /ping: {cmds.get('ping', 0)}\n"
    )
    bot.send_message(message.chat.id, txt)


@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    """
    Usage:
    /broadcast hello everyone
    """
    track_user(message)
    inc_message_stats()
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access denied.")
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(
            message,
            "📢 <b>Broadcast usage</b>\n\n"
            "<code>/broadcast Your message here</code>"
        )
        return

    msg = parts[1].strip()
    users = get_users()

    ok = 0
    fail = 0

    bot.reply_to(message, f"📢 Broadcasting to <b>{len(users)}</b> users...")

    for uid_str in users.keys():
        try:
            bot.send_message(int(uid_str), f"📢 <b>Message</b>\n\n{msg}")
            ok += 1
        except Exception:
            fail += 1

    bot.send_message(
        message.chat.id,
        f"✅ Broadcast done.\n\nSent: <b>{ok}</b>\nFailed: <b>{fail}</b>"
    )


@bot.message_handler(commands=["maintenance"])
def cmd_maintenance(message):
    """
    /maintenance on
    /maintenance off
    """
    track_user(message)
    inc_message_stats()
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access denied.")
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: <code>/maintenance on</code> or <code>/maintenance off</code>")
        return

    settings = get_settings()
    val = parts[1].strip().lower()

    if val == "on":
        settings["maintenance"] = True
    elif val == "off":
        settings["maintenance"] = False
    else:
        bot.reply_to(message, "Usage: <code>/maintenance on</code> or <code>/maintenance off</code>")
        return

    save_settings(settings)
    bot.reply_to(message, f"🛠 Maintenance is now <b>{'ON' if settings['maintenance'] else 'OFF'}</b>")


@bot.message_handler(commands=["forcejoin"])
def cmd_forcejoin(message):
    """
    /forcejoin on
    /forcejoin off
    """
    track_user(message)
    inc_message_stats()
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access denied.")
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: <code>/forcejoin on</code> or <code>/forcejoin off</code>")
        return

    settings = get_settings()
    val = parts[1].strip().lower()

    if val == "on":
        settings["forcejoin"] = True
    elif val == "off":
        settings["forcejoin"] = False
    else:
        bot.reply_to(message, "Usage: <code>/forcejoin on</code> or <code>/forcejoin off</code>")
        return

    save_settings(settings)
    bot.reply_to(message, f"🔒 Force-Join is now <b>{'ON' if settings['forcejoin'] else 'OFF'}</b>")


@bot.message_handler(commands=["setchannel"])
def cmd_setchannel(message):
    """
    /setchannel @yourchannel
    """
    track_user(message)
    inc_message_stats()
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Access denied.")
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: <code>/setchannel @YourChannel</code>")
        return

    ch = parts[1].strip()
    if not ch.startswith("@"):
        bot.reply_to(message, "Channel must start with @, e.g. <code>@YourChannel</code>")
        return

    settings = get_settings()
    settings["channel"] = ch
    save_settings(settings)

    bot.reply_to(message, f"✅ Channel set to <b>{ch}</b>")


# =========================
# CALLBACK HANDLERS (BUTTONS)
# =========================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    try:
        uid = call.from_user.id

        # common actions
        if call.data == "get_quote":
            if must_force_join() and not is_admin(uid):
                ch = get_force_channel()
                if ch and not check_user_joined_channel(uid, ch):
                    bot.answer_callback_query(call.id, "Join channel first.")
                    bot.send_message(call.message.chat.id, join_gate_message(ch), reply_markup=join_gate_keyboard(ch))
                    return
            bot.answer_callback_query(call.id, "Fetching quote...")
            bot.send_message(call.message.chat.id, get_quote(), reply_markup=main_menu_kb())
            return

        if call.data == "get_joke":
            if must_force_join() and not is_admin(uid):
                ch = get_force_channel()
                if ch and not check_user_joined_channel(uid, ch):
                    bot.answer_callback_query(call.id, "Join channel first.")
                    bot.send_message(call.message.chat.id, join_gate_message(ch), reply_markup=join_gate_keyboard(ch))
                    return
            bot.answer_callback_query(call.id, "Fetching joke...")
            bot.send_message(call.message.chat.id, get_joke(), reply_markup=main_menu_kb())
            return

        if call.data == "get_fact":
            if must_force_join() and not is_admin(uid):
                ch = get_force_channel()
                if ch and not check_user_joined_channel(uid, ch):
                    bot.answer_callback_query(call.id, "Join channel first.")
                    bot.send_message(call.message.chat.id, join_gate_message(ch), reply_markup=join_gate_keyboard(ch))
                    return
            bot.answer_callback_query(call.id, "Fetching fact...")
            bot.send_message(call.message.chat.id, get_fact(), reply_markup=main_menu_kb())
            return

        if call.data == "get_daily":
            bot.answer_callback_query(call.id, "Daily pack ready.")
            bot.send_message(call.message.chat.id, get_daily_pack(), reply_markup=main_menu_kb())
            return

        if call.data == "get_help":
            bot.answer_callback_query(call.id)
            txt = (
                "ℹ️ <b>Help</b>\n\n"
                "Commands:\n"
                "• /quote\n• /joke\n• /fact\n• /daily\n• /ping\n\n"
                "Admin:\n"
                "• /admin"
            )
            bot.send_message(call.message.chat.id, txt, reply_markup=main_menu_kb())
            return

        if call.data == "back_home":
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "🏠 Main Menu", reply_markup=main_menu_kb())
            return

        if call.data == "joined_continue":
            bot.answer_callback_query(call.id, "✅ Verified (or bypassed). Try /start.")
            bot.send_message(call.message.chat.id, "Now use /start ✅")
            return

        # Admin panel callbacks
        if call.data.startswith("admin_"):
            if not is_admin(uid):
                bot.answer_callback_query(call.id, "Access denied.")
                return

            settings = get_settings()

            if call.data == "admin_stats":
                bot.answer_callback_query(call.id)
                # Use /stats output quickly
                users = get_users()
                stats = get_stats()
                up = int(time.time()) - int(stats.get("started_at", int(time.time())))
                up_h = up // 3600
                up_m = (up % 3600) // 60
                bot.send_message(
                    call.message.chat.id,
                    f"📊 Users: <b>{len(users)}</b>\n"
                    f"💬 Messages: <b>{stats.get('total_messages', 0)}</b>\n"
                    f"⏳ Uptime: <b>{up_h}h {up_m}m</b>"
                )
                return

            if call.data == "admin_broadcast_help":
                bot.answer_callback_query(call.id)
                bot.send_message(
                    call.message.chat.id,
                    "📢 Broadcast usage:\n\n<code>/broadcast Your message here</code>"
                )
                return

            if call.data == "admin_maintenance":
                bot.answer_callback_query(call.id)
                state = settings.get("maintenance")
                settings["maintenance"] = not state
                save_settings(settings)
                bot.send_message(
                    call.message.chat.id,
                    f"🛠 Maintenance: <b>{'ON' if settings['maintenance'] else 'OFF'}</b>"
                )
                return

            if call.data == "admin_forcejoin":
                bot.answer_callback_query(call.id)
                state = settings.get("forcejoin")
                settings["forcejoin"] = not state
                save_settings(settings)
                bot.send_message(
                    call.message.chat.id,
                    f"🔒 Force-Join: <b>{'ON' if settings['forcejoin'] else 'OFF'}</b>\n"
                    f"Channel: <b>{settings.get('channel') or 'Not set'}</b>\n\n"
                    "Set channel with:\n<code>/setchannel @YourChannel</code>"
                )
                return

    except Exception:
        # never crash callbacks
        try:
            bot.answer_callback_query(call.id, "⚠️ Error occurred.")
        except Exception:
            pass


# =========================
# FALLBACK TEXT HANDLER
# =========================

@bot.message_handler(func=lambda m: True)
def all_messages(message):
    track_user(message)
    inc_message_stats()

    # gatekeep for normal messages too
    if not gatekeep(message):
        return

    # Reply with menu + hints
    bot.reply_to(
        message,
        "Use menu / commands:\n/quote /joke /fact /daily /help",
        reply_markup=main_menu_kb()
    )


# =========================
# RUN LOOP (KOYEB SAFE)
# =========================

def run_forever():
    while True:
        try:
            print("✅ Bot starting polling...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("❌ Polling crashed:", e)
            time.sleep(5)


if __name__ == "__main__":
    run_forever()
