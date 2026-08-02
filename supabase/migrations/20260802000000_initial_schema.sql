-- Day 19 Supabase Database Schema Migration
-- Production schema for Authorized Vehicles, Detection Logs, and Recognition Activity

-- Enable UUID generation extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Authorized Vehicles Table
CREATE TABLE IF NOT EXISTS public.authorized_vehicles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plate_number VARCHAR(32) NOT NULL UNIQUE,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'BLOCKED')),
    valid_from TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast allowlist lookup
CREATE INDEX IF NOT EXISTS idx_authorized_vehicles_plate ON public.authorized_vehicles (plate_number);
CREATE INDEX IF NOT EXISTS idx_authorized_vehicles_status ON public.authorized_vehicles (status);

-- 2. Detection Logs Table
CREATE TABLE IF NOT EXISTS public.detection_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    correlation_id VARCHAR(64) NOT NULL UNIQUE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    normalized_plate VARCHAR(32),
    raw_ocr_text TEXT,
    confidence REAL,
    decision VARCHAR(32) NOT NULL CHECK (decision IN ('AUTHORIZED', 'UNAUTHORIZED', 'MANUAL_REVIEW')),
    reason_code VARCHAR(64) NOT NULL,
    evidence_storage_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for history queries, statistics, and audit filters
CREATE INDEX IF NOT EXISTS idx_detection_logs_timestamp ON public.detection_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_detection_logs_decision ON public.detection_logs (decision);
CREATE INDEX IF NOT EXISTS idx_detection_logs_plate ON public.detection_logs (normalized_plate);

-- 3. Recognition Activity Table
CREATE TABLE IF NOT EXISTS public.recognition_activity (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(64) NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recognition_activity_timestamp ON public.recognition_activity (timestamp DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE public.authorized_vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.detection_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recognition_activity ENABLE ROW LEVEL SECURITY;

-- Read-only service policies for application access
CREATE POLICY "Allow server select on authorized_vehicles" ON public.authorized_vehicles
    FOR SELECT USING (true);

CREATE POLICY "Allow server select on detection_logs" ON public.detection_logs
    FOR SELECT USING (true);

CREATE POLICY "Allow server select on recognition_activity" ON public.recognition_activity
    FOR SELECT USING (true);

-- Storage Bucket Creation & Policy Guidance
-- Bucket Name: detection-evidence (Private bucket)
-- Service Role: FULL CONTROL
-- Anon Role: Restricted signed-URL access only (TTL: 300s)
