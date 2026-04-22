-- WARNING: THIS WILL PERMANENTLY ERASE ALL LIVE TRACKING, ALERTS, DELAYS, USERS, STOPS, BUSES, AND ROUTES.
-- Only execute this in your Supabase SQL Editor if you are completely sure.

-- 1. Wipe all relational tables safely using CASCADE
TRUNCATE TABLE public.alerts CASCADE;
TRUNCATE TABLE public.delays CASCADE;
TRUNCATE TABLE public.live_locations CASCADE;
TRUNCATE TABLE public.users CASCADE;
TRUNCATE TABLE public.stops CASCADE;
TRUNCATE TABLE public.buses CASCADE;
TRUNCATE TABLE public.routes CASCADE;

-- 2. Modify the Buses schema to strictly enforce having a total_stops variable
ALTER TABLE public.buses ADD COLUMN total_stops INTEGER NOT NULL DEFAULT 0;

-- 3. Re-inject the master administrator so you aren't permanently locked out
CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO public.users (name, email, password, role) 
VALUES (
    'System Administrator',
    'admin@lendi.edu.in',
    crypt('admin123', gen_salt('bf', 12)),
    'admin'
) ON CONFLICT (email) DO NOTHING;
