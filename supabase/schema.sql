-- supabase/schema.sql
-- Run this in the Supabase SQL Editor to create the research_reports table.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.research_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    query TEXT NOT NULL,
    intent TEXT,
    status TEXT NOT NULL DEFAULT 'success',
    analysis TEXT,
    stock_data JSONB,
    company_info JSONB,
    financial_summary JSONB,
    history JSONB,
    news JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for fast retrieval of recent reports
CREATE INDEX IF NOT EXISTS idx_research_reports_created_at
    ON public.research_reports (created_at DESC);

-- Enable Row Level Security (RLS) with NO public read/write policies.
-- Server-side access uses the service-role / secret key configured in .env.
ALTER TABLE public.research_reports ENABLE ROW LEVEL SECURITY;

-- Grant server-side privileges to service_role only (no public/anon grants).
GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.research_reports TO service_role;

-- Persistent duplicate-prevention table for automated daily email deliveries
CREATE TABLE IF NOT EXISTS public.daily_email_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    recipient TEXT NOT NULL,
    message_id TEXT,
    report_id UUID REFERENCES public.research_reports(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_daily_email_delivery UNIQUE (run_date, ticker, recipient)
);

ALTER TABLE public.daily_email_deliveries ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.daily_email_deliveries TO service_role;
