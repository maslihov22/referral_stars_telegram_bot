# Telegram Stars Referral & Rewards Bot

Telegram bot implementing a multi-tier referral rewards program with gamification and multi-language support (EN / ES / PT-BR). Built with Python (aiogram), Supabase (PostgreSQL) and native Telegram Stars payments.

## Features

### Referral rewards (5 configurable tiers)
Referrers earn a configurable percentage of payments made by users they invited, across up to 5 referral levels (40% / 20% / 10% / 5% / 3% by default).

### Gamification
- **Rank system** — Novato / Cazador / Maestro / Leyenda ranks based on referral count, each adding a payout bonus (+5% to +15%).
- **Reward chests** — every 10th referral opens a chest with a randomized Stars prize.
- **Weekly leaderboard** — top-3 referrers receive bonus Stars.
- **Seasonal promotions** — time-limited multiplier bonuses.

### Multi-language
- English, Español, Português — all strings live in `locales.json`.

### Admin tools
- `/admin` — withdrawal request queue
- `/stats` — users, active VIPs, revenue, pending payouts
- `/approve_XXXXXXXX` / `/reject_XXXXXXXX` — payout moderation

## Tech stack

- **Python + aiogram** — bot framework, async handlers
- **Supabase (PostgreSQL)** — users, referrals, payouts (`database_schema.sql`)
- **Telegram Stars** — native in-app payments
- **dotenv-based config** — see `.env.example`

## Setup

### 1. Create a Telegram bot
1. Open [@BotFather](https://t.me/BotFather), send `/newbot`
2. Set name and username, copy the token
3. Enable Stars payments: `/setpayments` → select the bot

### 2. Set up Supabase
1. Create a project at [supabase.com](https://supabase.com)
2. Run `database_schema.sql` in the SQL Editor
3. Copy `Project URL` and the `anon/public` key from Project Settings → API

### 3. Configure environment

```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_ID=123456789
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
STARS_PRICE=1000
WEEK_DURATION=7
```

Get your Telegram ID from [@userinfobot](https://t.me/userinfobot).

### 4. Install and run

```bash
pip install -r requirements.txt
python main.py
```

## Customization

**Referral tier percentages** — [bot.py:38-44](bot.py#L38-L44):

```python
REFERRAL_BONUSES = {
    1: 0.40,
    2: 0.20,
    3: 0.10,
    4: 0.05,
    5: 0.03
}
```

**VIP price** — `STARS_PRICE` in `.env`.

**Rank thresholds** — [bot.py:47-52](bot.py#L47-L52):

```python
RANKS = {
    "Novato": {"min": 0, "bonus": 0},
    "Cazador": {"min": 3, "bonus": 5},
    "Maestro": {"min": 10, "bonus": 10},
    "Leyenda": {"min": 30, "bonus": 15}
}
```

**Translations** — edit `locales.json`.

## Monitoring

Built-in metrics via `/stats`: total users, active VIPs, revenue, pending withdrawals.

Ad-hoc analytics through Supabase SQL, e.g. top referrers:

```sql
SELECT username, referrals_count, total_earned
FROM users
ORDER BY referrals_count DESC
LIMIT 10;
```

## Troubleshooting

- **"Supabase connection failed"** — check `SUPABASE_URL` / `SUPABASE_KEY`, make sure the schema was applied.
- **"Unauthorized" on payment** — enable Telegram Stars via @BotFather (`/setpayments`).
- **Bot not responding** — check `BOT_TOKEN`, make sure no second instance is running.
- **Referrals not counted** — verify the referral link format and the `process_referral_bonuses` logs.

---

*Educational / portfolio project demonstrating referral mechanics, Telegram Stars payments and Supabase integration. Any production deployment of referral-reward systems must comply with Telegram's Terms of Service and applicable local regulations.*
