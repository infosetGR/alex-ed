-- Alex Financial Planner Database Schema
-- Version: 001
-- Description: Initial schema for multi-user financial planning platform

-- Create alex schema
CREATE SCHEMA IF NOT EXISTS alex;

-- Note: Using gen_random_uuid() which is built into PostgreSQL 13+
-- No extension required

-- Minimal users table (Clerk handles auth)
CREATE TABLE IF NOT EXISTS alex.users (
    clerk_user_id VARCHAR(255) PRIMARY KEY,
    display_name VARCHAR(255),
    years_until_retirement INTEGER,
    target_retirement_income DECIMAL(12,2),  -- Annual income goal
    
    -- Allocation targets for rebalancing (stored as JSON)
    asset_class_targets JSONB DEFAULT '{"equity": 70, "fixed_income": 30}',
    region_targets JSONB DEFAULT '{"north_america": 50, "international": 50}',
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Reference data for instruments
CREATE TABLE IF NOT EXISTS alex.instruments (
    symbol VARCHAR(20) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    instrument_type VARCHAR(50),  -- 'equity', 'etf', 'mutual_fund', 'bond_fund'
    current_price DECIMAL(12,4),  -- Current price for portfolio calculations
    
    -- Allocation percentages (0-100, stored as JSON)
    allocation_regions JSONB DEFAULT '{}',      -- {"north_america": 60, "europe": 20, "asia": 20}
    allocation_sectors JSONB DEFAULT '{}',      -- {"technology": 30, "healthcare": 20, ...}
    allocation_asset_class JSONB DEFAULT '{}',  -- {"equity": 80, "fixed_income": 20}
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- User's investment accounts
CREATE TABLE IF NOT EXISTS alex.accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_user_id VARCHAR(255) REFERENCES alex.users(clerk_user_id) ON DELETE CASCADE,
    account_name VARCHAR(255) NOT NULL,     -- "401k", "Roth IRA"
    account_purpose TEXT,                    -- "Long-term retirement savings"
    cash_balance DECIMAL(12,2) DEFAULT 0,   -- Uninvested cash
    cash_interest DECIMAL(5,4) DEFAULT 0,   -- Annual interest rate (0.045 = 4.5%)
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Current positions in each account
CREATE TABLE IF NOT EXISTS alex.positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES alex.accounts(id) ON DELETE CASCADE,
    symbol VARCHAR(20) REFERENCES alex.instruments(symbol),
    quantity DECIMAL(20,8) NOT NULL,        -- Supports fractional shares
    as_of_date DATE DEFAULT CURRENT_DATE,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Ensure no duplicate positions per account
    UNIQUE(account_id, symbol)
);

-- Jobs tracking for async analysis
CREATE TABLE IF NOT EXISTS alex.jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_user_id VARCHAR(255) REFERENCES alex.users(clerk_user_id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL,          -- 'portfolio_analysis', 'rebalance', 'projection'
    status VARCHAR(20) DEFAULT 'pending',    -- 'pending', 'running', 'completed', 'failed'
    request_payload JSONB,                   -- Input parameters
    
    -- Separate fields for each agent's results (no merging needed)
    report_payload JSONB,                    -- Reporter agent's markdown analysis
    charts_payload JSONB,                    -- Charter agent's visualization data
    retirement_payload JSONB,                -- Retirement agent's projections
    summary_payload JSONB,                   -- Planner's final summary/metadata
    
    error_message TEXT,
    
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_accounts_user ON alex.accounts(clerk_user_id);
CREATE INDEX IF NOT EXISTS idx_positions_account ON alex.positions(account_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON alex.positions(symbol);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON alex.jobs(clerk_user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON alex.jobs(status);

-- Create update timestamp trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add update triggers to tables with updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON alex.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_instruments_updated_at BEFORE UPDATE ON alex.instruments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_accounts_updated_at BEFORE UPDATE ON alex.accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON alex.positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_jobs_updated_at BEFORE UPDATE ON alex.jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();