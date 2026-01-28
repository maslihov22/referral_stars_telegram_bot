-- Supabase Database Schema
-- Скопируй это в SQL Editor в Supabase Dashboard

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    language TEXT DEFAULT 'en',
    referrer_id UUID REFERENCES users(id),
    stars_balance INTEGER DEFAULT 0,
    total_earned INTEGER DEFAULT 0,
    rank TEXT DEFAULT 'Novato',
    referrals_count INTEGER DEFAULT 0,
    paid_until TIMESTAMP,
    new_year_bonus BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Transactions table
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) NOT NULL,
    amount INTEGER NOT NULL,
    type TEXT NOT NULL, -- 'payment', 'referral_bonus', 'mystery_chest', 'rank_bonus', 'leaderboard_prize'
    from_user_id UUID REFERENCES users(id),
    level INTEGER, -- referral level (1-5)
    created_at TIMESTAMP DEFAULT NOW()
);

-- Withdrawal requests table
CREATE TABLE withdrawal_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP
);

-- Leaderboard tracking (weekly)
CREATE TABLE weekly_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) NOT NULL,
    week_start DATE NOT NULL,
    referrals_this_week INTEGER DEFAULT 0,
    prize_awarded BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id, week_start)
);

-- Mystery chests tracking
CREATE TABLE mystery_chests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) NOT NULL,
    chest_number INTEGER NOT NULL, -- каждый 10-й реферал
    prize INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_referrer_id ON users(referrer_id);
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_created_at ON transactions(created_at);
CREATE INDEX idx_weekly_stats_week ON weekly_stats(week_start);
CREATE INDEX idx_withdrawal_status ON withdrawal_requests(status);

-- Function to get referral network depth
CREATE OR REPLACE FUNCTION get_referral_tree(root_user_id UUID, max_level INT DEFAULT 5)
RETURNS TABLE (
    user_id UUID,
    level INT,
    telegram_id BIGINT,
    username TEXT
) AS $$
WITH RECURSIVE referral_tree AS (
    -- Base case: direct referrals (level 1)
    SELECT
        u.id,
        1 as level,
        u.telegram_id,
        u.username
    FROM users u
    WHERE u.referrer_id = root_user_id

    UNION ALL

    -- Recursive case: get next level referrals
    SELECT
        u.id,
        rt.level + 1,
        u.telegram_id,
        u.username
    FROM users u
    INNER JOIN referral_tree rt ON u.referrer_id = rt.id
    WHERE rt.level < max_level
)
SELECT * FROM referral_tree;
$$ LANGUAGE SQL;
