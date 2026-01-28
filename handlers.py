# Additional handlers for referrals, payments, leaderboard, etc.
from datetime import datetime, timedelta
from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot import dp, bot, supabase, t, get_user, STARS_PRICE, ADMIN_ID, add_transaction, update_balance, process_referral_bonuses, has_active_subscription

# States for withdrawal
class WithdrawStates(StatesGroup):
    waiting_for_amount = State()

@dp.callback_query(F.data == "referrals")
async def show_referrals(callback: types.CallbackQuery):
    """Show referral stats"""
    user = await get_user(callback.from_user.id)
    lang = user["language"]

    if not await has_active_subscription(user):
        await callback.answer(t(lang, "no_access"), show_alert=True)
        return

    # Get referral tree using SQL function
    result = supabase.rpc("get_referral_tree", {"root_user_id": user["id"], "max_level": 5}).execute()

    # Count refs by level and calculate earnings
    levels = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    earnings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for ref in result.data:
        level = ref["level"]
        levels[level] += 1

        # Calculate potential earnings from this ref
        ref_user = supabase.table("users").select("total_earned").eq("id", ref["user_id"]).execute().data
        if ref_user:
            ref_earnings = ref_user[0]["total_earned"]
            bonus_percent = {1: 0.40, 2: 0.20, 3: 0.10, 4: 0.05, 5: 0.03}[level]
            earnings[level] += int(ref_earnings * bonus_percent)

    total_earned = sum(earnings.values())

    await callback.message.edit_text(
        t(lang, "referrals_text",
          level1=levels[1], level1_earned=earnings[1],
          level2=levels[2], level2_earned=earnings[2],
          level3=levels[3], level3_earned=earnings[3],
          level4=levels[4], level4_earned=earnings[4],
          level5=levels[5], level5_earned=earnings[5],
          total=total_earned),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« " + t(lang, "main_menu"), callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "leaderboard")
async def show_leaderboard(callback: types.CallbackQuery):
    """Show weekly leaderboard"""
    user = await get_user(callback.from_user.id)
    lang = user["language"]

    # Get current week start
    week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())

    # Get top 10 users this week
    result = supabase.table("weekly_stats").select("*, users(username, telegram_id)").eq("week_start", str(week_start)).order("referrals_this_week", desc=True).limit(10).execute()

    leaderboard_text = ""
    for idx, stat in enumerate(result.data, 1):
        username = stat["users"]["username"] if stat.get("users") else "Unknown"
        refs = stat["referrals_this_week"]

        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        leaderboard_text += f"{medal} {username} — {refs} refs\n"

    if not leaderboard_text:
        leaderboard_text = "No data yet... Be the first! 🚀"

    # Calculate time until next reset
    next_week = week_start + timedelta(days=7)
    days_left = (next_week - datetime.now().date()).days

    await callback.message.edit_text(
        t(lang, "leaderboard_text",
          leaderboard=leaderboard_text,
          reset_time=f"{days_left} days"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« " + t(lang, "main_menu"), callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "withdraw")
async def start_withdraw(callback: types.CallbackQuery, state: FSMContext):
    """Start withdrawal process"""
    user = await get_user(callback.from_user.id)
    lang = user["language"]

    if not await has_active_subscription(user):
        await callback.answer(t(lang, "no_access"), show_alert=True)
        return

    await callback.message.edit_text(
        t(lang, "withdraw_text", balance=user["stars_balance"]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« " + t(lang, "main_menu"), callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )

    await state.set_state(WithdrawStates.waiting_for_amount)

@dp.message(WithdrawStates.waiting_for_amount)
async def process_withdraw(message: types.Message, state: FSMContext):
    """Process withdrawal amount"""
    user = await get_user(message.from_user.id)
    lang = user["language"]

    try:
        amount = int(message.text)

        if amount < 100:
            await message.answer(t(lang, "withdraw_min"))
            return

        if amount > user["stars_balance"]:
            await message.answer(t(lang, "withdraw_insufficient"))
            return

        # Create withdrawal request
        supabase.table("withdrawal_requests").insert({
            "user_id": user["id"],
            "amount": amount,
            "status": "pending"
        }).execute()

        # Deduct from balance
        supabase.table("users").update({
            "stars_balance": user["stars_balance"] - amount
        }).eq("id", user["id"]).execute()

        await message.answer(
            t(lang, "withdraw_success", amount=amount),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(lang, "main_menu"), callback_data="main_menu")]
            ])
        )

        # Notify admin
        await bot.send_message(
            ADMIN_ID,
            t("en", "admin_new_withdrawal",
              username=user["username"],
              user_id=user["telegram_id"],
              amount=amount,
              balance=user["stars_balance"])
        )

        await state.clear()

    except ValueError:
        await message.answer("❌ Invalid amount. Enter a number.")

@dp.callback_query(F.data == "buy_access")
async def process_payment(callback: types.CallbackQuery):
    """Process Stars payment"""
    user = await get_user(callback.from_user.id)
    lang = user["language"]

    # Create invoice with translated text
    prices = [LabeledPrice(label=t(lang, "invoice_label"), amount=STARS_PRICE)]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=t(lang, "invoice_title"),
        description=t(lang, "invoice_description"),
        payload=f"vip_access_{user['id']}",
        provider_token="",  # Empty for Stars
        currency="XTR",  # Telegram Stars currency
        prices=prices
    )

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    """Handle pre-checkout"""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    """Handle successful payment"""
    user = await get_user(message.from_user.id)
    lang = user["language"]

    # Update subscription
    paid_until = datetime.now() + timedelta(days=7)

    supabase.table("users").update({
        "paid_until": paid_until.isoformat()
    }).eq("id", user["id"]).execute()

    # Add transaction
    await add_transaction(user["id"], STARS_PRICE, "payment")

    # Process referral bonuses
    await process_referral_bonuses(user["id"], STARS_PRICE)

    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{user['telegram_id']}"

    await message.answer(
        t(lang, "payment_success", ref_link=ref_link),
        parse_mode="HTML"
    )

# Admin commands
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    """Admin panel"""
    if message.from_user.id != ADMIN_ID:
        return

    # Get pending withdrawals
    pending = supabase.table("withdrawal_requests").select("*, users(username, telegram_id)").eq("status", "pending").execute()

    if not pending.data:
        await message.answer("No pending withdrawals.")
        return

    text = "💰 <b>Pending Withdrawals:</b>\n\n"

    for req in pending.data:
        username = req["users"]["username"]
        telegram_id = req["users"]["telegram_id"]
        amount = req["amount"]
        created = datetime.fromisoformat(req["created_at"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")

        text += f"• {username} (@{telegram_id})\n"
        text += f"  Amount: {amount} ⭐\n"
        text += f"  Date: {created}\n"
        text += f"  /approve_{req['id'][:8]} | /reject_{req['id'][:8]}\n\n"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    """Show bot stats (admin only)"""
    if message.from_user.id != ADMIN_ID:
        return

    # Total users
    total_users = supabase.table("users").select("id", count="exact").execute()
    user_count = total_users.count

    # Active VIP users
    now = datetime.now().isoformat()
    active_vip = supabase.table("users").select("id", count="exact").gt("paid_until", now).execute()
    vip_count = active_vip.count

    # Total transactions
    total_trans = supabase.table("transactions").select("amount").execute()
    total_revenue = sum(t["amount"] for t in total_trans.data)

    # Pending withdrawals
    pending_w = supabase.table("withdrawal_requests").select("amount").eq("status", "pending").execute()
    pending_amount = sum(w["amount"] for w in pending_w.data)

    text = f"""
📊 <b>Bot Statistics</b>

👥 Total Users: {user_count}
💎 Active VIP: {vip_count}
💰 Total Revenue: {total_revenue} ⭐
⏳ Pending Withdrawals: {pending_amount} ⭐
    """

    await message.answer(text, parse_mode="HTML")
