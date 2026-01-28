import asyncio
import json
import os
import random
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from supabase import create_client, Client

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
STARS_PRICE = int(os.getenv("STARS_PRICE", 1000))

# Initialize bot and database
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Load translations
with open("locales.json", "r", encoding="utf-8") as f:
    LOCALES = json.load(f)

# Referral bonuses by level
REFERRAL_BONUSES = {
    1: 0.40,  # 40%
    2: 0.20,  # 20%
    3: 0.10,  # 10%
    4: 0.05,  # 5%
    5: 0.03   # 3%
}

# Rank thresholds
RANKS = {
    "Novato": {"min": 0, "bonus": 0},
    "Cazador": {"min": 3, "bonus": 5},
    "Maestro": {"min": 10, "bonus": 10},
    "Leyenda": {"min": 30, "bonus": 15}
}

def t(lang: str, key: str, **kwargs) -> str:
    """Get translated text"""
    text = LOCALES.get(lang, LOCALES["en"]).get(key, key)
    return text.format(**kwargs) if kwargs else text

async def get_user(telegram_id: int) -> Optional[dict]:
    """Get user from database"""
    result = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
    return result.data[0] if result.data else None

async def create_user(telegram_id: int, username: str, referrer_id: Optional[str] = None, language: str = "en") -> dict:
    """Create new user"""
    data = {
        "telegram_id": telegram_id,
        "username": username,
        "language": language,
        "referrer_id": referrer_id
    }
    result = supabase.table("users").insert(data).execute()
    return result.data[0]

async def update_user_language(telegram_id: int, language: str):
    """Update user language"""
    supabase.table("users").update({"language": language}).eq("telegram_id", telegram_id).execute()

async def has_active_subscription(user: dict) -> bool:
    """Check if user has active VIP access"""
    if not user.get("paid_until"):
        return False
    paid_until = datetime.fromisoformat(user["paid_until"].replace("Z", "+00:00"))
    return paid_until > datetime.now()

async def add_transaction(user_id: str, amount: int, trans_type: str, from_user_id: Optional[str] = None, level: Optional[int] = None):
    """Add transaction to database"""
    data = {
        "user_id": user_id,
        "amount": amount,
        "type": trans_type,
        "from_user_id": from_user_id,
        "level": level
    }
    supabase.table("transactions").insert(data).execute()

async def update_balance(user_id: str, amount: int):
    """Update user balance"""
    user_data = supabase.table("users").select("*").eq("id", user_id).execute().data[0]
    new_balance = user_data["stars_balance"] + amount
    new_total = user_data["total_earned"] + amount

    supabase.table("users").update({
        "stars_balance": new_balance,
        "total_earned": new_total
    }).eq("id", user_id).execute()

async def calculate_rank(referrals_count: int) -> str:
    """Calculate user rank based on referrals"""
    for rank in reversed(list(RANKS.keys())):
        if referrals_count >= RANKS[rank]["min"]:
            return rank
    return "Novato"

async def get_rank_bonus(rank: str) -> int:
    """Get bonus percentage for rank"""
    return RANKS.get(rank, RANKS["Novato"])["bonus"]

async def process_referral_bonuses(new_user_id: str, payment_amount: int):
    """Process bonuses for all referral levels"""
    new_user = supabase.table("users").select("*").eq("id", new_user_id).execute().data[0]

    current_referrer_id = new_user.get("referrer_id")
    level = 1

    while current_referrer_id and level <= 5:
        bonus_percent = REFERRAL_BONUSES[level]
        bonus_amount = int(payment_amount * bonus_percent)

        # Get referrer data
        referrer = supabase.table("users").select("*").eq("id", current_referrer_id).execute().data[0]

        # Apply rank bonus
        rank_bonus = await get_rank_bonus(referrer["rank"])
        final_bonus = int(bonus_amount * (1 + rank_bonus / 100))

        # Apply new year bonus if active
        if referrer.get("new_year_bonus") and level == 1:
            final_bonus *= 2

        # Update balance
        await update_balance(current_referrer_id, final_bonus)
        await add_transaction(current_referrer_id, final_bonus, "referral_bonus", new_user_id, level)

        # Update referrals count for level 1
        if level == 1:
            new_count = referrer["referrals_count"] + 1
            new_rank = await calculate_rank(new_count)

            supabase.table("users").update({
                "referrals_count": new_count,
                "rank": new_rank
            }).eq("id", current_referrer_id).execute()

            # Check for rank up
            if new_rank != referrer["rank"]:
                lang = referrer["language"]
                rank_name = t(lang, f"ranks.{new_rank}")
                bonus = await get_rank_bonus(new_rank)
                await bot.send_message(
                    referrer["telegram_id"],
                    t(lang, "rank_up", rank=rank_name, bonus=bonus)
                )

            # Check for mystery chest (every 10 refs)
            if new_count % 10 == 0:
                prize = random.choices(
                    [100, 300, 500, 1000],
                    weights=[50, 30, 15, 5]
                )[0]

                await update_balance(current_referrer_id, prize)
                await add_transaction(current_referrer_id, prize, "mystery_chest")

                supabase.table("mystery_chests").insert({
                    "user_id": current_referrer_id,
                    "chest_number": new_count // 10,
                    "prize": prize
                }).execute()

                lang = referrer["language"]
                await bot.send_message(
                    referrer["telegram_id"],
                    t(lang, "mystery_chest", prize=prize)
                )

            # Update weekly stats
            week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
            supabase.table("weekly_stats").upsert({
                "user_id": current_referrer_id,
                "week_start": str(week_start),
                "referrals_this_week": new_count
            }, on_conflict="user_id,week_start").execute()

        # Move to next level
        current_referrer_id = referrer.get("referrer_id")
        level += 1

def get_main_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Generate main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton(text=t(lang, "my_profile"), callback_data="profile")],
        [InlineKeyboardButton(text=t(lang, "referrals"), callback_data="referrals")],
        [InlineKeyboardButton(text=t(lang, "leaderboard"), callback_data="leaderboard")],
        [InlineKeyboardButton(text=t(lang, "withdraw"), callback_data="withdraw")],
        [InlineKeyboardButton(text=t(lang, "buy_access"), callback_data="buy_access")],
        [InlineKeyboardButton(text=t(lang, "settings"), callback_data="settings")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_language_keyboard() -> InlineKeyboardMarkup:
    """Generate language selection keyboard"""
    keyboard = [
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")],
        [InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton(text="🇧🇷 Português", callback_data="lang_pt")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command"""
    telegram_id = message.from_user.id
    username = message.from_user.username or f"user_{telegram_id}"

    # Extract referral code
    args = message.text.split()
    referrer_id = None

    if len(args) > 1:
        ref_code = args[1]
        if ref_code.startswith("ref_"):
            ref_telegram_id = int(ref_code.replace("ref_", ""))
            referrer = await get_user(ref_telegram_id)
            if referrer:
                referrer_id = referrer["id"]

    # Get or create user
    user = await get_user(telegram_id)

    if not user:
        # New user - show language selection
        await message.answer(
            t("en", "start_welcome"),
            reply_markup=get_language_keyboard()
        )
        # Store referrer for later (after language selection)
        if referrer_id:
            # Temporary storage in message
            message.bot.data = {"pending_referrer": referrer_id, "telegram_id": telegram_id, "username": username}
    else:
        # Existing user
        lang = user["language"]
        await message.answer(
            t(lang, "main_menu"),
            reply_markup=get_main_keyboard(lang)
        )

@dp.callback_query(F.data.startswith("lang_"))
async def process_language_selection(callback: types.CallbackQuery):
    """Handle language selection"""
    lang = callback.data.split("_")[1]
    telegram_id = callback.from_user.id
    username = callback.from_user.username or f"user_{telegram_id}"

    user = await get_user(telegram_id)

    if not user:
        # New user - create account
        referrer_id = getattr(callback.bot, 'data', {}).get("pending_referrer")
        user = await create_user(telegram_id, username, referrer_id, lang)
    else:
        # Update language
        await update_user_language(telegram_id, lang)
        user["language"] = lang

    await callback.message.edit_text(
        t(lang, "language_selected"),
        reply_markup=None
    )

    # Show welcome message with explanation
    await callback.message.answer(
        t(lang, "welcome_message"),
        parse_mode="HTML"
    )

    # Show main menu
    await callback.message.answer(
        t(lang, "main_menu"),
        reply_markup=get_main_keyboard(lang)
    )

@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    """Show user profile"""
    user = await get_user(callback.from_user.id)
    lang = user["language"]

    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{user['telegram_id']}"
    paid_until = user.get("paid_until")

    if paid_until:
        paid_until = datetime.fromisoformat(paid_until.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    else:
        paid_until = "Not active"

    # Get rank translation
    ranks_dict = LOCALES.get(lang, LOCALES["en"]).get("ranks", {})
    rank_name = ranks_dict.get(user['rank'], user['rank'])

    await callback.message.edit_text(
        t(lang, "profile_text",
          rank=rank_name,
          balance=user["stars_balance"],
          total_earned=user["total_earned"],
          referrals_count=user["referrals_count"],
          paid_until=paid_until,
          ref_link=ref_link),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« " + t(lang, "main_menu"), callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "main_menu")
async def show_main_menu(callback: types.CallbackQuery):
    """Show main menu"""
    user = await get_user(callback.from_user.id)
    lang = user["language"]

    await callback.message.edit_text(
        t(lang, "main_menu"),
        reply_markup=get_main_keyboard(lang)
    )

@dp.callback_query(F.data == "settings")
async def show_settings(callback: types.CallbackQuery):
    """Show settings"""
    user = await get_user(callback.from_user.id)
    lang = user["language"]

    lang_names = {"en": "English", "es": "Español", "pt": "Português"}

    await callback.message.edit_text(
        t(lang, "settings_text", language=lang_names[lang]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "change_language"), callback_data="change_lang")],
            [InlineKeyboardButton(text="« " + t(lang, "main_menu"), callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "change_lang")
async def change_language(callback: types.CallbackQuery):
    """Change language"""
    await callback.message.edit_text(
        "🌐 Choose language / Elige idioma / Escolha idioma:",
        reply_markup=get_language_keyboard()
    )

async def main():
    """Start bot"""
    print("Bot started! 🚀")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
