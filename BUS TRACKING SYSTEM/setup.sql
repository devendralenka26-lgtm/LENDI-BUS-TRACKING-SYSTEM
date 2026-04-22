-- Database Structure for College Bus Ride Status PWA

-- 1. Routes Table
CREATE TABLE public.routes (
    id SERIAL PRIMARY KEY,
    route_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Buses Table
CREATE TABLE public.buses (
    id SERIAL PRIMARY KEY,
    bus_number VARCHAR(50) UNIQUE NOT NULL,
    driver_id INTEGER, -- We'll add FK later after Users table is created to avoid circular reasoning
    route_id INTEGER REFERENCES public.routes(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Stops Table
CREATE TABLE public.stops (
    id SERIAL PRIMARY KEY,
    route_id INTEGER REFERENCES public.routes(id) ON DELETE CASCADE,
    stop_name VARCHAR(100) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    stop_order INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Users Table (Admin, Driver, Student)
CREATE TABLE public.users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL, -- Will store bcrypt hash
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'driver', 'student')),
    bus_id INTEGER REFERENCES public.buses(id) ON DELETE SET NULL, -- Assigned bus for student or driver
    stop_id INTEGER REFERENCES public.stops(id) ON DELETE SET NULL, -- Default stop for student
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add constraints to Buses now that users table is defined
ALTER TABLE public.buses 
ADD CONSTRAINT fk_driver_id FOREIGN KEY (driver_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- 5. Live Locations Table (UPSERT Table)
CREATE TABLE public.live_locations (
    bus_id INTEGER PRIMARY KEY REFERENCES public.buses(id) ON DELETE CASCADE,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    speed DOUBLE PRECISION DEFAULT 0.0,
    heading DOUBLE PRECISION DEFAULT 0.0,
    is_trip_active BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Alerts Table
CREATE TABLE public.alerts (
    id SERIAL PRIMARY KEY,
    bus_id INTEGER REFERENCES public.buses(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. Delays Table
CREATE TABLE public.delays (
    id SERIAL PRIMARY KEY,
    bus_id INTEGER REFERENCES public.buses(id) ON DELETE CASCADE,
    delay_time INTEGER NOT NULL, -- Delay in seconds
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Optional: Create initial admin user 
-- Password hash is for 'admin123'
CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO public.users (name, email, password, role) 
VALUES (
    'System Administrator',
    'admin@lendi.edu.in',
    crypt('admin123', gen_salt('bf', 12)),
    'admin'
) ON CONFLICT (email) DO NOTHING;
