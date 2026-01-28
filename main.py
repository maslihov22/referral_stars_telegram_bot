"""
Telegram Stars MLM Referral Bot
Вирусная реферальная система с геймификацией для LATAM
"""
import asyncio
import sys
from bot import dp, bot
import handlers  # Import handlers to register them

# Fix for Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    """Start bot"""
    print("=" * 50)
    print("🌟 Stars MLM Bot Started!")
    print("=" * 50)
    print("📱 Bot is running...")
    print("🔥 Ready to make money! 💰")
    print("=" * 50)

    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
